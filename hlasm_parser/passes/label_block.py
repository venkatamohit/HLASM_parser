"""
LabelBlockPass
==============

Groups HLASM source lines into hierarchically-labelled blocks.

HLASM fixed-column format (after 72-column truncation):
  - Columns 1–8  : **Name / Label** field
  - Columns 9+   : Operation + Operand + Remarks

Grouping rules (mirrors tape-z's ``LabelBlockPass.java``):

+----------------------------------------------------------+-----------------------+
| Condition                                                | Action                |
+==========================================================+=======================+
| ``isCSECT(line)`` or ``isDSECT(line)``                   | Add col 9+ to current |
+----------------------------------------------------------+-----------------------+
| Label zone is blank / only whitespace                    | Add col 9+ to current |
+----------------------------------------------------------+-----------------------+
| Label zone is ``"SORTED"``                               | Add col 9+ to current |
+----------------------------------------------------------+-----------------------+
| Label zone starts with ``"*"``                           | Comment → current     |
+----------------------------------------------------------+-----------------------+
| Label zone stripped starts with ``"&"``                  | Comment → current     |
+----------------------------------------------------------+-----------------------+
| Label zone starts with ``" "`` (space)                   | Add col 9+ to current |
+----------------------------------------------------------+-----------------------+
| Otherwise (non-blank, non-special label)                 | **Start new block**   |
|                                                          | Add col 9+ to it      |
+----------------------------------------------------------+-----------------------+

Notes
-----
* All top-level named blocks are direct children of the root node
  (flat structure, *not* nested).
* Local labels beginning with ``.`` are made unique by appending an ID suffix.
* EXEC SQL lines are passed through as-is (SQL pattern match).
"""
from __future__ import annotations

import logging
import re
from itertools import count
from typing import List

from ..models import CodeElement, LabelledBlock

logger = logging.getLogger(__name__)

_EXEC_SQL_RE = re.compile(r"^\s*EXEC\s+SQL", re.IGNORECASE)
_id_gen = count(1)


def _next_id() -> str:
    return f"elem_{next(_id_gen)}"


def _reset_ids() -> None:
    """Reset the global counter (used in tests to get deterministic IDs)."""
    global _id_gen
    _id_gen = count(1)


class LabelBlockPass:
    """
    Partitions HLASM source lines into a tree of :class:`LabelledBlock`
    objects rooted at ``HLASM_ROOT``.
    """

    def run(self, lines: List[str]) -> LabelledBlock:
        """
        Process source lines and return the root block.

        Parameters
        ----------
        lines:
            Sanitised HLASM source lines (no trailing whitespace).

        Returns
        -------
        LabelledBlock
            Root block whose ``children`` are the top-level named sections.
        """
        root = LabelledBlock(id=_next_id(), label="HLASM_ROOT")
        current: CodeElement = root

        for line in lines:
            if not line.strip():
                continue

            # Ensure we always have a full 8-char label zone to inspect
            label_zone = (line + " " * 8)[:8]
            rest = line[8:] if len(line) > 8 else ""

            # ----------------------------------------------------------------
            # Priority checks (same order as Java source)
            # ----------------------------------------------------------------
            if self._is_csect(line) or self._is_dsect(line):
                current.add(
                    CodeElement(id=_next_id(), text=rest.strip(), element_type="RAW")
                )

            elif label_zone.strip() in ("", "SORTED"):
                current.add(
                    CodeElement(id=_next_id(), text=rest.strip(), element_type="RAW")
                )

            elif label_zone.startswith("*"):
                current.add(
                    CodeElement(id=_next_id(), text=line, element_type="COMMENT")
                )

            elif label_zone.strip().startswith("&"):
                current.add(
                    CodeElement(id=_next_id(), text=line, element_type="COMMENT")
                )

            elif _EXEC_SQL_RE.match(line):
                # Embedded SQL – keep whole line intact
                current.add(
                    CodeElement(id=_next_id(), text=line, element_type="RAW")
                )

            elif label_zone.startswith(" "):
                # No label; continuation / unlabeled instruction
                current.add(
                    CodeElement(id=_next_id(), text=rest.strip(), element_type="RAW")
                )

            else:
                # Non-blank, non-comment, non-special → new labeled block
                label = label_zone.strip()
                # Make local labels unique to avoid collisions across sections
                if label.startswith("."):
                    label = f"{label}_{_next_id()}"

                new_block = LabelledBlock(id=_next_id(), label=label)
                root.add(new_block)        # Flat under root (not under current)
                current = new_block

                if rest.strip():
                    current.add(
                        CodeElement(
                            id=_next_id(), text=rest.strip(), element_type="RAW"
                        )
                    )

        return root

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_csect(line: str) -> bool:
        """True when the *operation* field (col 9+) begins with CSECT."""
        rest = (line[8:] if len(line) > 8 else "").strip()
        return rest.upper().startswith("CSECT")

    @staticmethod
    def _is_dsect(line: str) -> bool:
        """True when the *operation* field (col 9+) contains DSECT."""
        rest = (line[8:] if len(line) > 8 else "").strip()
        return "DSECT" in rest.upper()
