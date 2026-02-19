"""
Tests for individual HLASM processing passes.

Each test class corresponds to one pass module.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from hlasm_parser.passes.discard_after_72 import DiscardAfter72Pass
from hlasm_parser.passes.label_block import LabelBlockPass
from hlasm_parser.passes.line_continuation import LineContinuationCollapsePass
from hlasm_parser.passes.sanitise import LLMSanitisePass
from hlasm_parser.models import LabelledBlock, CodeElement


# ─────────────────────────────────────────────────────────────────────────────
# DiscardAfter72Pass
# ─────────────────────────────────────────────────────────────────────────────


class TestDiscardAfter72Pass:
    def _run(self, lines):
        return DiscardAfter72Pass().run(lines)

    def test_short_lines_unchanged(self):
        lines = ["         STM   14,12,12(13)", "LOOP     NOP"]
        assert self._run(lines) == lines

    def test_line_truncated_at_72(self):
        line = "A" * 80
        result = self._run([line])
        assert len(result[0]) == 72
        assert result[0] == "A" * 72

    def test_exactly_72_chars_unchanged(self):
        line = "B" * 72
        assert self._run([line]) == [line]

    def test_71_chars_unchanged(self):
        line = "C" * 71
        assert self._run([line]) == [line]

    def test_empty_lines_preserved(self):
        lines = ["", "   ", "TEST"]
        assert self._run(lines) == lines

    def test_multiple_lines_mixed_lengths(self):
        lines = ["A" * 100, "B" * 50, "C" * 72, "D" * 0]
        result = self._run(lines)
        assert len(result[0]) == 72
        assert len(result[1]) == 50
        assert len(result[2]) == 72
        assert len(result[3]) == 0

    def test_preserves_line_count(self):
        lines = ["X" * i for i in range(80)]
        result = self._run(lines)
        assert len(result) == len(lines)

    def test_sequence_numbers_stripped(self):
        # HLASM files often have sequence numbers in cols 73+.
        # Build a line > 72 chars: 32 content chars + 40 padding + 8-digit seq = 80.
        content = "         STM   14,12,12(13)     "  # 32 chars
        padding = " " * 40                             # 40 chars
        seq_num = "00000010"                           # 8 chars (cols 73-80)
        line = content + padding + seq_num
        assert len(line) == 80
        result = self._run([line])
        assert len(result[0]) == 72
        assert "00000010" not in result[0]


# ─────────────────────────────────────────────────────────────────────────────
# LineContinuationCollapsePass
# ─────────────────────────────────────────────────────────────────────────────


class TestLineContinuationCollapsePass:
    def _run(self, lines):
        return LineContinuationCollapsePass().run(lines)

    def test_normal_lines_unchanged(self):
        lines = [
            "LOOP     STM   14,12,12(13)",
            "         BALR  12,0",
        ]
        assert self._run(lines) == lines

    def test_continuation_line_merged(self):
        # A continuation line has blank cols 1-15 and content from col 16
        base = "         MVC   OUTPUT,"
        cont = "               INPUT"           # 15 leading spaces, content at 16
        result = self._run([base, cont])
        assert len(result) == 1
        assert "OUTPUT" in result[0]
        assert "INPUT" in result[0]

    def test_multiple_continuations_merged(self):
        lines = [
            "         MVC   A,",
            "               B,",
            "               C",
            "         BALR  12,0",
        ]
        result = self._run(lines)
        assert len(result) == 2
        assert "A," in result[0]
        assert "B," in result[0]
        assert "C" in result[0]

    def test_empty_lines_not_treated_as_continuation(self):
        lines = ["         NOP", "", "         BR    14"]
        result = self._run(lines)
        assert len(result) == 3

    def test_comment_lines_not_continuation(self):
        lines = ["         BALR  12,0", "* this is a comment"]
        result = self._run(lines)
        assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# LLMSanitisePass
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMSanitisePass:
    def _run(self, lines):
        return LLMSanitisePass().run(lines)

    def test_trailing_whitespace_removed(self):
        lines = ["         STM   14,12,12(13)   ", "LOOP     NOP   "]
        result = self._run(lines)
        assert result[0] == "         STM   14,12,12(13)"
        assert result[1] == "LOOP     NOP"

    def test_leading_whitespace_preserved(self):
        line = "         BALR  12,0"
        result = self._run([line])
        assert result[0].startswith("         ")

    def test_empty_lines_preserved(self):
        lines = ["", "   ", "TEST"]
        result = self._run(lines)
        assert result[0] == ""
        assert result[1] == ""   # trailing whitespace stripped
        assert result[2] == "TEST"

    def test_preserves_line_count(self):
        lines = ["line1  ", "line2", "line3   "]
        result = self._run(lines)
        assert len(result) == 3


# ─────────────────────────────────────────────────────────────────────────────
# LabelBlockPass
# ─────────────────────────────────────────────────────────────────────────────


SIMPLE_HLASM = """\
* Comment at top
MAINPROG CSECT
         STM   14,12,12(13)
         BALR  12,0
SAVEAREA DC    18F'0'
SUBROUT1 STM   14,12,12(13)
         BR    14
"""


class TestLabelBlockPass:
    def _run(self, source: str) -> LabelledBlock:
        lines = source.splitlines()
        return LabelBlockPass().run(lines)

    def test_root_block_created(self):
        root = self._run(SIMPLE_HLASM)
        assert root.label == "HLASM_ROOT"

    def test_labeled_blocks_become_children(self):
        root = self._run(SIMPLE_HLASM)
        labels = [c.label for c in root.children if isinstance(c, LabelledBlock)]
        assert "SAVEAREA" in labels
        assert "SUBROUT1" in labels

    def test_csect_does_not_create_extra_block(self):
        # CSECT lines should be added to the current block, not start a new one
        root = self._run(SIMPLE_HLASM)
        labels = [c.label for c in root.children if isinstance(c, LabelledBlock)]
        # "MAINPROG" should NOT appear as a child because the CSECT line is
        # swallowed without starting a new block
        assert "MAINPROG" not in labels

    def test_comment_lines_kept_as_comments(self):
        root = self._run(SIMPLE_HLASM)
        comments = [
            c for c in root.children if c.element_type == "COMMENT"
        ]
        assert len(comments) >= 1

    def test_unlabeled_instructions_go_to_current_block(self):
        source = textwrap.dedent("""\
        BLOCK1   STM   14,12,12(13)
                 BALR  12,0
                 BR    14
        """)
        root = self._run(source)
        block1_children = [
            c for c in root.children
            if isinstance(c, LabelledBlock) and c.label == "BLOCK1"
        ]
        assert len(block1_children) == 1
        # The unlabeled instructions should be in BLOCK1
        block1 = block1_children[0]
        texts = [c.text for c in block1.children if c.element_type == "RAW"]
        assert any("BALR" in t for t in texts)
        assert any("BR" in t for t in texts)

    def test_dsect_handled_without_new_block(self):
        source = textwrap.dedent("""\
        WORKMAPD DSECT
        FIELD1   DS    CL20
        FIELD2   DS    X
        """)
        root = self._run(source)
        # DSECT line goes to current block; FIELD1/FIELD2 become new blocks
        labels = [c.label for c in root.children if isinstance(c, LabelledBlock)]
        assert "FIELD1" in labels
        assert "FIELD2" in labels

    def test_local_labels_made_unique(self):
        source = textwrap.dedent("""\
        BLOCK1   STM   14,12,12(13)
        .LOCAL   DS    0H
        BLOCK2   STM   14,12,12(13)
        .LOCAL   DS    0H
        """)
        root = self._run(source)
        labels = [c.label for c in root.children if isinstance(c, LabelledBlock)]
        # Both .LOCAL labels should appear but with unique suffixes
        local_labels = [l for l in labels if l.startswith(".LOCAL")]
        assert len(local_labels) == 2
        assert local_labels[0] != local_labels[1]

    def test_sorted_label_zone_not_new_block(self):
        source = "SORTED   NOP\n         BR    14\n"
        root = self._run(source)
        # "SORTED" should not become a new block label
        labels = [c.label for c in root.children if isinstance(c, LabelledBlock)]
        assert "SORTED" not in labels

    def test_empty_source(self):
        root = self._run("")
        assert root.label == "HLASM_ROOT"
        assert root.children == []

    def test_only_comments(self):
        source = "* Line 1\n* Line 2\n* Line 3\n"
        root = self._run(source)
        assert not any(isinstance(c, LabelledBlock) for c in root.children)

    def test_flat_structure_all_blocks_under_root(self):
        """All named blocks must be direct children of root (not nested)."""
        source = textwrap.dedent("""\
        A        NOP
                 B     B_LABEL
        B_LABEL  NOP
                 B     C_LABEL
        C_LABEL  NOP
        """)
        root = self._run(source)
        block_labels = {c.label for c in root.children if isinstance(c, LabelledBlock)}
        assert "A" in block_labels
        assert "B_LABEL" in block_labels
        assert "C_LABEL" in block_labels
