"""
Core data models for the HLASM parser.

Mirrors the domain model from tape-z (Java) translated to Python dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Code element types
# ---------------------------------------------------------------------------

ELEMENT_TYPES = {
    "RAW",            # Unprocessed source line
    "COMMENT",        # Comment line
    "EMPTY",          # Empty / blank line
    "INSTRUCTION",    # Parsed HLASM instruction
    "LABELLED_BLOCK", # A block of code with a label header
    "EXTERNAL_CALL",  # Call to an external program
    "MACRO_START",    # Start-of-macro-expansion marker
    "MACRO_END",      # End-of-macro-expansion marker
}


@dataclass
class CodeElement:
    """Base unit of parsed source code."""

    id: str
    text: str
    element_type: str
    children: List[CodeElement] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add(self, child: CodeElement) -> None:
        self.children.append(child)

    def __repr__(self) -> str:
        return f"CodeElement(type={self.element_type!r}, text={self.text!r})"


@dataclass
class LabelledBlock(CodeElement):
    """
    A named block of code elements.

    All direct children of the root LabelledBlock are the top-level
    labeled sections of the HLASM source.
    """

    label: str = ""

    def __init__(self, id: str, label: str, element_type: str = "LABELLED_BLOCK"):
        super().__init__(id=id, text=label, element_type=element_type)
        self.label = label

    def __repr__(self) -> str:
        return (
            f"LabelledBlock(label={self.label!r}, "
            f"children={len(self.children)})"
        )


# ---------------------------------------------------------------------------
# Parsed instruction
# ---------------------------------------------------------------------------

# Broad categories for instructions
INSTRUCTION_CATEGORIES = {
    "BRANCH",      # B, BC, BE, BNE …
    "CALL",        # BAL, BALR, BAS, BASR, CALL, LINK, XCTL
    "RETURN",      # BR 14 / BCR 15,14 used as return
    "SECTION",     # CSECT, DSECT, RSECT, COM, LOCTR
    "DATA",        # DC, DS, EQU, ORG, LTORG
    "MACRO",       # MACRO, MEND, MEXIT, MNOTE, COPY
    "INSTRUCTION", # All other machine instructions
    "COMMENT",     # Inline comment
    "EMPTY",       # Blank / empty line
}


@dataclass
class ParsedInstruction:
    """A single HLASM instruction broken into its fields."""

    label: Optional[str]
    opcode: Optional[str]
    operands: List[str]
    comment: Optional[str]
    raw_text: str
    instruction_type: str = "INSTRUCTION"

    def __repr__(self) -> str:
        return (
            f"ParsedInstruction(opcode={self.opcode!r}, "
            f"operands={self.operands}, type={self.instruction_type!r})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "opcode": self.opcode,
            "operands": self.operands,
            "comment": self.comment,
            "instruction_type": self.instruction_type,
            "raw_text": self.raw_text,
        }


# ---------------------------------------------------------------------------
# Missing dependency record
# ---------------------------------------------------------------------------


@dataclass
class MissingDependency:
    """
    A dependency symbol that could not be resolved to a source file.

    Collected by :class:`~hlasm_parser.pipeline.hlasm_analysis.HlasmAnalysis`
    during recursive analysis and exposed via ``analysis.missing_deps``.
    """

    dep_name: str              # Symbol referenced (e.g. "SUBPROG1")
    referenced_from_file: str  # Source file that contains the reference
    referenced_in_chunk: str   # Label of the chunk making the call
    search_path: str           # Directory that was searched (empty if none)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dep_name": self.dep_name,
            "referenced_from_file": self.referenced_from_file,
            "referenced_in_chunk": self.referenced_in_chunk,
            "search_path": self.search_path,
        }

    def __str__(self) -> str:
        loc = f"{self.referenced_in_chunk} in {Path(self.referenced_from_file).name}"
        hint = f" (searched: {self.search_path})" if self.search_path else ""
        return f"{self.dep_name:<20} referenced from {loc}{hint}"


# ---------------------------------------------------------------------------
# Chunk – the final output unit
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """
    A logical chunk of HLASM code.

    One chunk corresponds to one labeled block (subroutine, CSECT section,
    macro body, etc.) after macro expansion.  Each chunk carries its parsed
    instructions and the list of external symbols it depends on.
    """

    label: str
    instructions: List[ParsedInstruction]
    dependencies: List[str]
    source_file: str
    chunk_type: str          # CSECT | DSECT | SUBROUTINE | MACRO | ROOT
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"Chunk(label={self.label!r}, type={self.chunk_type!r}, "
            f"instructions={len(self.instructions)}, "
            f"deps={self.dependencies})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "chunk_type": self.chunk_type,
            "source_file": self.source_file,
            "instruction_count": len(self.instructions),
            "dependencies": self.dependencies,
            "instructions": [i.to_dict() for i in self.instructions],
            "metadata": self.metadata,
        }
