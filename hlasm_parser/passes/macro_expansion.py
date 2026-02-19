"""
MacroExpansionParsePass
=======================

Expands macro calls in HLASM source by inlining copybook content.

Algorithm (mirrors tape-z's ``MacroExpansionParsePass.java``):

1.  Lines starting with ``*``         → comment; pass through unchanged.
2.  Empty lines                        → pass through unchanged.
3.  Lines whose first token is a known assembler mnemonic
                                       → pass through unchanged.
4.  All other lines are potential macro calls:
    a.  Split into whitespace-delimited tokens.
    b.  First token  = macro name candidate (could be a label).
        Second token = macro name candidate (if first was a label).
    c.  Look up ``{copybook_path}/{MACRONAME}_Assembler_Copybook.txt``.
    d.  If found → expand via :class:`HLASMCopybookProcessor` and wrap
        the result with ``* MACRO_EXPANSION_START/END`` marker comments.
    e.  If not found → pass the line through unchanged.

The set of ``known_mnemonics`` is supplied at construction time and prevents
genuine assembler instructions from being mistaken for macro calls.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Set

from .copybook_processor import HLASMCopybookProcessor

logger = logging.getLogger(__name__)


class MacroExpansionParsePass:
    """
    Inline-expands HLASM macro calls using copybook files.

    Parameters
    ----------
    mnemonics:
        Set of known HLASM mnemonics / assembler directives.  Lines whose
        first (or second) token matches one of these are never treated as
        macro calls.
    copybook_path:
        Directory that contains ``<NAME>_Assembler_Copybook.txt`` files.
    """

    MARKER_START = "* MACRO_EXPANSION_START:"
    MARKER_END   = "* MACRO_EXPANSION_END:"

    def __init__(self, mnemonics: Set[str], copybook_path: str) -> None:
        self._mnemonics = {m.upper() for m in mnemonics}
        self._copybook_dir = Path(copybook_path) if copybook_path else None
        self._processor = HLASMCopybookProcessor()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, lines: List[str]) -> List[str]:
        """
        Process all source lines, expanding macro calls in-place.

        Parameters
        ----------
        lines:
            Source lines (already truncated to 72 columns).

        Returns
        -------
        List[str]
            Potentially longer list of lines with macros expanded.
        """
        result: List[str] = []
        for line in lines:
            result.extend(self._process_line(line))
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_line(self, line: str) -> List[str]:
        """Return the (possibly expanded) lines for a single input line."""

        # Pass through empty lines
        if not line.strip():
            return [line]

        # Pass through comment lines (col 1 == '*')
        if line.startswith("*"):
            return [line]

        tokens = line.split()
        if not tokens:
            return [line]

        first = tokens[0].upper()

        # If the first token is a known mnemonic, the line is a regular
        # instruction (e.g. "         STM   14,12,12(13)").
        if first in self._mnemonics:
            return [line]

        # If the *second* token is a known mnemonic this is a labeled
        # instruction (e.g. "LOOP     B     TOP").
        if len(tokens) >= 2 and tokens[1].upper() in self._mnemonics:
            return [line]

        # ------------------------------------------------------------------
        # Potential macro call – check for copybook with first token as name
        # ------------------------------------------------------------------
        if self._copybook_dir is not None:
            expanded = self._try_expand(tokens, first, tokens)
            if expanded is not None:
                return expanded

            # Also try second token when first looks like a label
            if len(tokens) >= 2:
                second = tokens[1].upper()
                expanded = self._try_expand(tokens[1:], second, tokens)
                if expanded is not None:
                    return expanded

        # Nothing matched – keep original
        return [line]

    def _try_expand(
        self,
        details: List[str],
        macro_name: str,
        original_tokens: List[str],
    ) -> List[str] | None:
        """
        Attempt to expand *macro_name* from the copybook directory.

        Returns the list of expanded lines (with markers) or *None* when no
        matching copybook is found.
        """
        if not self._copybook_dir:
            return None

        copybook_file = self._copybook_dir / f"{macro_name}_Assembler_Copybook.txt"
        if not copybook_file.exists():
            return None

        logger.info("Expanding macro %r from %s", macro_name, copybook_file)
        expanded = self._processor.run(copybook_file, details)

        if expanded is None:
            logger.warning(
                "Copybook processor returned None for %r; keeping original line",
                macro_name,
            )
            return None

        result: List[str] = [f"{self.MARKER_START} {macro_name}"]
        result.extend(expanded)
        result.append(f"{self.MARKER_END} {macro_name}")
        return result
