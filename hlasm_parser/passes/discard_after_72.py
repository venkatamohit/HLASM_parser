"""
DiscardAfter72Pass
==================

Truncates each source line to 72 characters.

IBM mainframe HLASM source files use a fixed-column format:
  - Columns  1–8  : Name (label) field
  - Columns  9    : (blank separator)
  - Columns 10–14 : Operation field
  - Columns 15    : (blank separator)
  - Columns 16–71 : Operand / remarks field
  - Columns 72+   : Sequence number field (ignored by the assembler)

Discarding columns 73+ is the first normalisation step before any other
processing takes place, matching the behaviour of tape-z's DiscardAfter72Pass.
"""
from __future__ import annotations

from typing import List


class DiscardAfter72Pass:
    """Truncates every line in the input to a maximum of 72 characters."""

    COLUMN_LIMIT: int = 72

    def run(self, lines: List[str]) -> List[str]:
        """
        Apply the pass to a list of source lines.

        Parameters
        ----------
        lines:
            Raw lines read from an HLASM source file (newlines already stripped).

        Returns
        -------
        List[str]
            The same lines with each line capped at 72 characters.
        """
        return [line[: self.COLUMN_LIMIT] for line in lines]
