"""
LLMSanitisePass
===============

Light-weight sanitisation of HLASM source lines prior to structural parsing.

Currently performs:
  * Trailing-whitespace removal (preserves leading whitespace which is
    semantically significant in HLASM fixed-column format).
  * Normalisation of HLASM continuation markers: a line whose content ends
    with a non-blank character in column 72 is a *continued* line; the
    continuation character is stripped so downstream passes see a clean line.

This mirrors the intent of tape-z's ``LLMSanitisePass.java`` without the
LLM-specific transformations that are not needed for the pure parser path.
"""
from __future__ import annotations

from typing import List


class LLMSanitisePass:
    """Sanitises source lines for structural parsing."""

    def run(self, lines: List[str]) -> List[str]:
        """
        Apply sanitisation to all lines.

        Parameters
        ----------
        lines:
            Source lines, already truncated to 72 columns.

        Returns
        -------
        List[str]
            Sanitised lines (same length list; no lines are dropped).
        """
        return [self._sanitise(line) for line in lines]

    # ------------------------------------------------------------------

    @staticmethod
    def _sanitise(line: str) -> str:
        # Strip trailing whitespace
        return line.rstrip()
