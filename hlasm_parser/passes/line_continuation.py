"""
LineContinuationCollapsePass
============================

Collapses HLASM continuation lines into single logical lines.

HLASM line continuation rules:
  * A source statement that cannot fit within columns 1–71 may be continued
    on the next line.
  * The *continued* line has a non-blank continuation character in **column 72**
    (after 72-char truncation this character is already dropped, so we detect
    continuation differently: a continuation *next* line has blanks in
    columns 1–15 and content starting at column 16).
  * This pass joins such lines so that later passes see a single logical line.

Implementation notes
--------------------
After :class:`DiscardAfter72Pass` columns 73+ are already gone.  We detect
a continuation line as one where:
  - Columns 1–15 are **all blanks** (label zone + op-code zone are empty), AND
  - Content begins at column 16 or later.

The continuation content is appended to the *previous logical line* (with a
single space separator if needed).
"""
from __future__ import annotations

from typing import List

_CONTINUATION_INDENT = 15   # Columns 1-15 are blank = continuation


class LineContinuationCollapsePass:
    """Joins HLASM continuation lines with their logical predecessor."""

    def run(self, lines: List[str]) -> List[str]:
        """
        Collapse continuation lines.

        Parameters
        ----------
        lines:
            Source lines (already truncated to 72 columns, sanitised).

        Returns
        -------
        List[str]
            Possibly shorter list with continuation lines merged in.
        """
        result: List[str] = []
        for line in lines:
            if self._is_continuation(line) and result:
                # Append continuation content to the previous line
                continuation_content = line[_CONTINUATION_INDENT:].rstrip()
                if continuation_content:
                    result[-1] = result[-1].rstrip() + " " + continuation_content.lstrip()
            else:
                result.append(line)
        return result

    @staticmethod
    def _is_continuation(line: str) -> bool:
        """
        A line is a continuation if columns 1–15 are blank and column 16
        (index 15) onwards has content.
        """
        if len(line) <= _CONTINUATION_INDENT:
            return False
        prefix = line[:_CONTINUATION_INDENT]
        return prefix.strip() == "" and line[_CONTINUATION_INDENT:].strip() != ""
