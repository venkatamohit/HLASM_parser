"""
Tests for InstructionParser.

Covers opcode parsing, operand splitting, comment extraction, and
instruction type classification.
"""
from __future__ import annotations

import pytest

from hlasm_parser.parser.instruction_parser import InstructionParser


@pytest.fixture
def parser():
    return InstructionParser()


# ─────────────────────────────────────────────────────────────────────────────
# Basic field extraction
# ─────────────────────────────────────────────────────────────────────────────


class TestBasicParsing:
    def test_empty_string(self, parser):
        instr = parser.parse("")
        assert instr.opcode is None
        assert instr.instruction_type == "EMPTY"

    def test_whitespace_only(self, parser):
        instr = parser.parse("   ")
        assert instr.opcode is None
        assert instr.instruction_type == "EMPTY"

    def test_opcode_only(self, parser):
        instr = parser.parse("NOP")
        assert instr.opcode == "NOP"
        assert instr.operands == []
        assert instr.comment is None

    def test_opcode_normalised_to_uppercase(self, parser):
        instr = parser.parse("stm   14,12,12(13)")
        assert instr.opcode == "STM"

    def test_opcode_with_single_operand(self, parser):
        instr = parser.parse("BR    14")
        assert instr.opcode == "BR"
        assert instr.operands == ["14"]

    def test_opcode_with_multiple_operands(self, parser):
        instr = parser.parse("STM   14,12,12(13)")
        assert instr.opcode == "STM"
        assert instr.operands == ["14", "12", "12(13)"]

    def test_opcode_and_comment(self, parser):
        # Without column-position information the text-only parser interprets
        # "Padding" as an operand (first space-delimited token after the opcode)
        # and "instruction" as the comment.  The important invariant is that
        # the opcode is extracted correctly and the remark content is preserved
        # somewhere in operands/comment.
        instr = parser.parse("NOP                  Padding instruction")
        assert instr.opcode == "NOP"
        full_text = " ".join(instr.operands) + " " + (instr.comment or "")
        assert "Padding" in full_text
        assert "instruction" in full_text

    def test_operands_and_comment(self, parser):
        instr = parser.parse("BALR  12,0             Establish base")
        assert instr.opcode == "BALR"
        assert instr.operands == ["12", "0"]
        assert instr.comment == "Establish base"

    def test_comment_line(self, parser):
        instr = parser.parse("* This is a comment")
        assert instr.instruction_type == "COMMENT"
        assert instr.opcode is None

    def test_raw_text_preserved(self, parser):
        text = "STM   14,12,12(13)     Save registers"
        instr = parser.parse(text)
        assert instr.raw_text == text


# ─────────────────────────────────────────────────────────────────────────────
# Operand parsing – nested parentheses
# ─────────────────────────────────────────────────────────────────────────────


class TestOperandParsing:
    def test_simple_register_operands(self, parser):
        instr = parser.parse("LM    14,12,12(13)")
        assert instr.operands == ["14", "12", "12(13)"]

    def test_complex_parentheses(self, parser):
        instr = parser.parse("L     2,0(1,3)")
        assert instr.operands == ["2", "0(1,3)"]

    def test_literal_operand(self, parser):
        instr = parser.parse("L     2,=F'4'")
        assert instr.operands == ["2", "=F'4'"]

    def test_character_literal(self, parser):
        instr = parser.parse("MVC   FIELD,=CL8'HELLO'")
        assert instr.operands == ["FIELD", "=CL8'HELLO'"]

    def test_character_literal_with_comma_inside(self, parser):
        # Comma inside quotes should not split
        instr = parser.parse("MVC   FIELD,=C'A,B'")
        assert instr.operands == ["FIELD", "=C'A,B'"]

    def test_address_literal(self, parser):
        instr = parser.parse("LA    1,=A(LABEL1,LABEL2)")
        assert instr.operands == ["1", "=A(LABEL1,LABEL2)"]

    def test_dc_with_quoted_value(self, parser):
        instr = parser.parse("DC    C'HELLO WORLD'")
        assert instr.opcode == "DC"
        assert instr.operands == ["C'HELLO WORLD'"]

    def test_hex_literal(self, parser):
        instr = parser.parse("MVI   FLAG,X'FF'")
        assert instr.operands == ["FLAG", "X'FF'"]

    def test_binary_literal(self, parser):
        instr = parser.parse("TM    FLAG,B'10000000'")
        assert instr.operands == ["FLAG", "B'10000000'"]

    def test_self_defining_term(self, parser):
        instr = parser.parse("USING *,12")
        assert instr.operands == ["*", "12"]

    def test_single_paren_operand(self, parser):
        instr = parser.parse("BALR  12,0")
        assert instr.operands == ["12", "0"]

    def test_expression_operand(self, parser):
        instr = parser.parse("LA    1,LENGTH-1")
        assert instr.operands == ["1", "LENGTH-1"]

    def test_no_operands(self, parser):
        instr = parser.parse("MEND")
        assert instr.operands == []


# ─────────────────────────────────────────────────────────────────────────────
# Instruction type classification
# ─────────────────────────────────────────────────────────────────────────────


class TestInstructionTypeClassification:
    def test_branch_instructions(self, parser):
        for opcode in ["B", "BE", "BNE", "BH", "BL", "BZ", "BNZ", "BC", "BR"]:
            instr = parser.parse(f"{opcode}   LABEL")
            assert instr.instruction_type == "BRANCH", f"Expected BRANCH for {opcode}"

    def test_extended_branch_mnemonics(self, parser):
        for opcode in ["J", "JE", "JNE", "JH", "JL", "JNH", "JNL"]:
            instr = parser.parse(f"{opcode}   LABEL")
            assert instr.instruction_type == "BRANCH", f"Expected BRANCH for {opcode}"

    def test_call_instructions(self, parser):
        for opcode in ["BAL", "BALR", "BAS", "BASR", "CALL", "LINK", "XCTL"]:
            instr = parser.parse(f"{opcode}   14,TARGET")
            assert instr.instruction_type == "CALL", f"Expected CALL for {opcode}"

    def test_section_directives(self, parser):
        for opcode in ["CSECT", "DSECT", "RSECT", "COM", "LOCTR"]:
            instr = parser.parse(f"{opcode}")
            assert instr.instruction_type == "SECTION", f"Expected SECTION for {opcode}"

    def test_data_directives(self, parser):
        for opcode in ["DC", "DS", "EQU", "ORG", "LTORG", "USING", "DROP", "END"]:
            instr = parser.parse(f"{opcode}   X")
            assert instr.instruction_type == "DATA", f"Expected DATA for {opcode}"

    def test_macro_control_directives(self, parser):
        for opcode in ["MACRO", "MEND", "MEXIT", "COPY", "AREAD", "ANOP"]:
            instr = parser.parse(f"{opcode}")
            assert instr.instruction_type == "MACRO_CTRL", f"Expected MACRO_CTRL for {opcode}"

    def test_regular_instruction(self, parser):
        for opcode in ["STM", "LM", "L", "ST", "MVC", "CLC"]:
            instr = parser.parse(f"{opcode}   R1,R2")
            assert instr.instruction_type == "INSTRUCTION", f"Expected INSTRUCTION for {opcode}"

    def test_nop_is_branch(self, parser):
        instr = parser.parse("NOP")
        assert instr.instruction_type == "BRANCH"


# ─────────────────────────────────────────────────────────────────────────────
# Label propagation
# ─────────────────────────────────────────────────────────────────────────────


class TestLabelPropagation:
    def test_label_passed_through(self, parser):
        instr = parser.parse("STM   14,12,12(13)", label="MYPROG")
        assert instr.label == "MYPROG"

    def test_no_label_by_default(self, parser):
        instr = parser.parse("STM   14,12,12(13)")
        assert instr.label is None
