"""
Tests for HLASMCopybookProcessor and MacroExpansionParsePass.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from hlasm_parser.passes.copybook_processor import HLASMCopybookProcessor
from hlasm_parser.passes.macro_expansion import MacroExpansionParsePass
from hlasm_parser.pipeline.mnemonics import STANDARD_MNEMONICS

FIXTURES = Path(__file__).parent / "fixtures"
MACROS_DIR = FIXTURES / "macros"


# ─────────────────────────────────────────────────────────────────────────────
# HLASMCopybookProcessor
# ─────────────────────────────────────────────────────────────────────────────


class TestHLASMCopybookProcessor:
    @pytest.fixture
    def processor(self):
        return HLASMCopybookProcessor()

    def test_printmsg_no_params(self, processor):
        """Macro with no parameters – body returned unchanged."""
        copybook = MACROS_DIR / "PRINTMSG_Assembler_Copybook.txt"
        # Call with just the macro name token
        result = processor.run(copybook, ["PRINTMSG"])
        assert result is not None
        assert any("SVC" in line for line in result)

    def test_printmsg_with_params(self, processor):
        """Parameters substituted correctly."""
        copybook = MACROS_DIR / "PRINTMSG_Assembler_Copybook.txt"
        result = processor.run(copybook, ["PRINTMSG", "MYMSG,20"])
        assert result is not None
        joined = "\n".join(result)
        assert "MYMSG" in joined
        assert "20" in joined
        # Original parameter names should be replaced
        assert "&MSG" not in joined
        assert "&LEN" not in joined

    def test_saveregs_with_param(self, processor):
        copybook = MACROS_DIR / "SAVEREGS_Assembler_Copybook.txt"
        result = processor.run(copybook, ["SAVEREGS", "MYSAVE"])
        assert result is not None
        joined = "\n".join(result)
        assert "MYSAVE" in joined
        assert "&SAVEAREA" not in joined

    def test_nonexistent_file_returns_none(self, processor):
        result = processor.run(Path("/nonexistent/MISSING_Assembler_Copybook.txt"), [])
        assert result is None

    def test_result_truncated_to_72_cols(self, processor, tmp_path):
        """Expanded lines must not exceed 72 characters."""
        copybook = tmp_path / "LONG_Assembler_Copybook.txt"
        copybook.write_text(
            "         MACRO\n"
            "&LABEL   LONG  &PARAM\n"
            "* " + "A" * 80 + "\n"
            "         MEND\n"
        )
        result = processor.run(copybook, ["LONG", "VALUE"])
        assert result is not None
        assert all(len(line) <= 72 for line in result)

    def test_too_few_params_filled_with_empty(self, processor, tmp_path):
        """Missing actual params are substituted with empty string."""
        copybook = tmp_path / "MULTI_Assembler_Copybook.txt"
        copybook.write_text(
            "         MACRO\n"
            "&L       MULTI &P1,&P2,&P3\n"
            "         MVC   &P1,&P2\n"
            "         LA    1,&P3\n"
            "         MEND\n"
        )
        result = processor.run(copybook, ["MULTI", "FIELD1"])
        assert result is not None
        joined = "\n".join(result)
        assert "FIELD1" in joined


# ─────────────────────────────────────────────────────────────────────────────
# MacroExpansionParsePass
# ─────────────────────────────────────────────────────────────────────────────


class TestMacroExpansionParsePass:
    def _pass(self, copybook_path=str(MACROS_DIR)):
        return MacroExpansionParsePass(STANDARD_MNEMONICS, copybook_path)

    def test_comment_lines_pass_through(self):
        p = self._pass()
        lines = ["* This is a comment", "* Another comment"]
        assert p.run(lines) == lines

    def test_empty_lines_pass_through(self):
        p = self._pass()
        lines = ["", "   ", ""]
        assert p.run(lines) == lines

    def test_mnemonic_lines_pass_through(self):
        """Lines whose first token is a known mnemonic are not expanded."""
        p = self._pass()
        lines = [
            "         STM   14,12,12(13)",
            "         BALR  12,0",
            "LOOP     NOP",
        ]
        result = p.run(lines)
        assert result == lines

    def test_labeled_mnemonic_lines_pass_through(self):
        p = self._pass()
        line = "LOOP     B     LOOP"
        result = p.run([line])
        assert result == [line]

    def test_macro_expanded_with_markers(self):
        p = self._pass()
        result = p.run(["         PRINTMSG GREETING,13"])
        joined = "\n".join(result)
        assert "MACRO_EXPANSION_START" in joined
        assert "MACRO_EXPANSION_END" in joined
        assert "SVC" in joined

    def test_macro_params_substituted(self):
        p = self._pass()
        result = p.run(["         SAVEREGS MYSAVE"])
        joined = "\n".join(result)
        assert "MYSAVE" in joined
        assert "&SAVEAREA" not in joined

    def test_unknown_token_passes_through(self):
        """A token with no matching copybook is passed through unchanged."""
        p = self._pass()
        line = "         UNKNOWNMACRO  P1,P2"
        result = p.run([line])
        assert result == [line]

    def test_no_copybook_path_skips_expansion(self):
        p = MacroExpansionParsePass(STANDARD_MNEMONICS, "")
        lines = ["         PRINTMSG GREETING,13"]
        result = p.run(lines)
        assert result == lines

    def test_expansion_inserted_inline(self):
        """Expanded macro lines are inserted between their markers."""
        p = self._pass()
        lines = [
            "         STM   14,12,12(13)",
            "         PRINTMSG GREETING,13",
            "         BR    14",
        ]
        result = p.run(lines)
        # Original surrounding instructions should still be there
        assert any("STM" in l for l in result)
        assert any("BR" in l for l in result)
        # Expansion should be between them
        assert any("MACRO_EXPANSION_START" in l for l in result)
        assert any("MACRO_EXPANSION_END" in l for l in result)
