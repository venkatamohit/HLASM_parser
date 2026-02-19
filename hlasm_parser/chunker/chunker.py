"""
Chunker
=======

Converts a list of :class:`~hlasm_parser.models.LabelledBlock` objects (the
output of :class:`~hlasm_parser.pipeline.extract_blocks.ExtractBlocksTask`)
into :class:`~hlasm_parser.models.Chunk` objects.

Each chunk:

* Corresponds to exactly one labeled block.
* Has its ``instructions`` field populated by parsing every ``RAW``
  :class:`~hlasm_parser.models.CodeElement` with
  :class:`~hlasm_parser.parser.instruction_parser.InstructionParser`.
* Has its ``dependencies`` field populated from:
  - CALL / LINK / XCTL operands (external programs).
  - BAL / BALR / BAS / BASR target labels (internal subroutines).
  - Branch targets (B, BC, …) when they look like external symbols.
* Has its ``chunk_type`` inferred from the first section directive found
  (CSECT, DSECT, MACRO, etc.).
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set

from ..models import Chunk, CodeElement, LabelledBlock, ParsedInstruction
from ..parser.instruction_parser import (
    BRANCH_OPCODES,
    CALL_OPCODES,
    ENTRY_MARKER_OPCODES,
    InstructionParser,
)

logger = logging.getLogger(__name__)

# Opcodes that indicate a hard external dependency (external program name)
_EXTERNAL_CALL_OPCODES: Set[str] = {"CALL", "LINK", "XCTL", "LOAD", "DELETE"}

# Opcodes for internal subroutine calls (target is a label in the same file)
_INTERNAL_CALL_OPCODES: Set[str] = {"BAL", "BALR", "BAS", "BASR"}

# Shop-specific GO family – first operand is the subroutine/program name.
# GO target         – unconditional call
# GOIF/GOIFNOT/…    – conditional variants; first operand is still the target
_GO_OPCODES: Set[str] = {
    "GO", "GOIF", "GOIFNOT",
    "GOEQ", "GONE", "GOGT", "GOLT", "GOGE", "GOLE",
}

# Regex: a token that looks like a symbol / label (not a register or number)
_SYMBOL_RE = re.compile(r"^[A-Za-z@#$][A-Za-z0-9@#$_]*$")


def _is_symbol(token: str) -> bool:
    """Return True if *token* looks like an HLASM symbol / label."""
    return bool(_SYMBOL_RE.match(token))


def _strip_parens(token: str) -> str:
    """Remove enclosing parentheses, e.g. ``(PGMNAME)`` → ``PGMNAME``."""
    t = token.strip()
    if t.startswith("(") and t.endswith(")"):
        return t[1:-1].strip()
    return t


class Chunker:
    """
    Converts labeled blocks into fully-parsed :class:`~hlasm_parser.models.Chunk`
    objects.
    """

    def __init__(self) -> None:
        self._parser = InstructionParser()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def chunk(
        self,
        blocks: List[LabelledBlock],
        source_file: str = "<unknown>",
    ) -> List[Chunk]:
        """
        Convert *blocks* to chunks.

        Parameters
        ----------
        blocks:
            Named labeled blocks returned by
            :class:`~hlasm_parser.pipeline.extract_blocks.ExtractBlocksTask`.
        source_file:
            The path / name of the source file (stored in each chunk).

        Returns
        -------
        List[Chunk]
        """
        return [self._block_to_chunk(block, source_file) for block in blocks]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _block_to_chunk(self, block: LabelledBlock, source_file: str) -> Chunk:
        instructions: List[ParsedInstruction] = []
        dependencies: List[str] = []
        chunk_type = "SUBROUTINE"
        seen_deps: Dict[str, int] = {}   # dep → first-seen index (for order)

        for element in block.children:
            parsed = self._parse_element(element, block.label)
            if parsed is None:
                continue

            # Infer chunk type from first section / entry opcode encountered
            if parsed.opcode:
                op = parsed.opcode.upper()
                if op in ("CSECT", "RSECT") and chunk_type == "SUBROUTINE":
                    chunk_type = "CSECT"
                elif op == "DSECT" and chunk_type == "SUBROUTINE":
                    chunk_type = "DSECT"
                elif op == "MACRO" and chunk_type == "SUBROUTINE":
                    chunk_type = "MACRO"
                elif op in ("START",) and chunk_type == "SUBROUTINE":
                    chunk_type = "CSECT"
                elif op == "IN" and chunk_type == "SUBROUTINE":
                    # Shop convention: <label> IN marks a named subroutine entry.
                    chunk_type = "ENTRY"

            # Collect dependencies
            self._extract_deps(parsed, seen_deps)

            instructions.append(parsed)

        # Build ordered, deduplicated dependency list
        ordered_deps = sorted(seen_deps, key=lambda k: seen_deps[k])

        return Chunk(
            label=block.label,
            instructions=instructions,
            dependencies=ordered_deps,
            source_file=source_file,
            chunk_type=chunk_type,
        )

    def _parse_element(
        self,
        element: CodeElement,
        block_label: str,
    ) -> Optional[ParsedInstruction]:
        """Parse a single code element; return None for comments, blanks, nested blocks."""
        from ..models import LabelledBlock  # local import avoids circular ref

        # Root block may contain LabelledBlock children – skip them here
        if isinstance(element, LabelledBlock):
            return None
        if element.element_type in ("COMMENT", "EMPTY"):
            return None
        if not element.text.strip():
            return None

        parsed = self._parser.parse(element.text)

        if parsed.instruction_type not in ("COMMENT", "EMPTY"):
            return parsed

        return None

    def _extract_deps(
        self,
        instr: ParsedInstruction,
        seen: Dict[str, int],
    ) -> None:
        """Update *seen* with any dependency targets extracted from *instr*."""
        if not instr.opcode:
            return
        op = instr.opcode.upper()

        if op in _EXTERNAL_CALL_OPCODES:
            # CALL PROGNAME[,(parm1,parm2)],  LINK EP=PROGNAME, XCTL DE=PROGNAME
            for operand in instr.operands:
                target = _strip_parens(operand)
                # Handle keyword=value syntax (EP=PROGNAME, DE=PROGNAME, SF=...)
                if "=" in target:
                    kw, _, val = target.partition("=")
                    if kw.upper() in ("EP", "DE", "SF"):
                        target = _strip_parens(val.strip())
                if _is_symbol(target) and target not in seen:
                    seen[target] = len(seen)
                break  # Only the first operand contains the program name

        elif op in _INTERNAL_CALL_OPCODES:
            # BAL  R14,SUBROUTINE  or  BALR R14,R15
            # The branch target is the *last* operand for BAL/BAS,
            # and a register for BALR/BASR.
            operands = instr.operands
            if operands:
                if op in ("BAL", "BAS"):
                    # Second operand is the target label
                    target = operands[-1] if len(operands) >= 2 else operands[0]
                    target = _strip_parens(target)
                    if _is_symbol(target) and not target.startswith("R") and target not in seen:
                        seen[target] = len(seen)
                # BALR / BASR take register operands – skip

        elif op in _GO_OPCODES:
            # GO <target>              – unconditional subroutine call
            # GOIF <target>,<cond>    – conditional; target is first operand
            # GOIFNOT <target>,<cond> – same pattern
            if instr.operands:
                target = _strip_parens(instr.operands[0])
                if _is_symbol(target) and target not in seen:
                    seen[target] = len(seen)

        elif op in BRANCH_OPCODES and op not in ("BR", "BCR", "NOPR", "NOP"):
            # B LABEL, BE LABEL, etc. – only capture non-register targets
            operands = instr.operands
            if operands:
                target = operands[-1]
                target = _strip_parens(target)
                if _is_symbol(target) and target not in seen:
                    seen[target] = len(seen)
