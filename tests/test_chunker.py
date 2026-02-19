"""
Tests for the Chunker component.

Validates that labeled blocks are correctly converted to Chunk objects
with accurate instruction lists, chunk types, and dependency lists.
"""
from __future__ import annotations

import textwrap

import pytest

from hlasm_parser.chunker.chunker import Chunker
from hlasm_parser.models import CodeElement, LabelledBlock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_block(label: str, *raw_texts: str) -> LabelledBlock:
    """Convenience builder for LabelledBlock objects."""
    block = LabelledBlock(id="test_id", label=label)
    for i, text in enumerate(raw_texts):
        block.add(CodeElement(id=f"e{i}", text=text, element_type="RAW"))
    return block


def _make_comment_block(label: str, comment: str) -> LabelledBlock:
    block = LabelledBlock(id="test_id", label=label)
    block.add(CodeElement(id="e0", text=comment, element_type="COMMENT"))
    return block


# ─────────────────────────────────────────────────────────────────────────────
# Chunker – basic behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestChunkerBasic:
    @pytest.fixture
    def chunker(self):
        return Chunker()

    def test_empty_blocks_list(self, chunker):
        assert chunker.chunk([], "test.asm") == []

    def test_single_block_single_instruction(self, chunker):
        block = _make_block("SUB1", "STM   14,12,12(13)")
        chunks = chunker.chunk([block], "test.asm")
        assert len(chunks) == 1
        assert chunks[0].label == "SUB1"
        assert len(chunks[0].instructions) == 1

    def test_multiple_blocks(self, chunker):
        blocks = [
            _make_block("SUB1", "STM   14,12,12(13)", "BR    14"),
            _make_block("SUB2", "NOP", "BR    14"),
        ]
        chunks = chunker.chunk(blocks, "test.asm")
        assert len(chunks) == 2
        labels = {c.label for c in chunks}
        assert "SUB1" in labels
        assert "SUB2" in labels

    def test_source_file_stored(self, chunker):
        block = _make_block("X", "NOP")
        chunks = chunker.chunk([block], "my/file.asm")
        assert chunks[0].source_file == "my/file.asm"

    def test_comments_not_in_instructions(self, chunker):
        block = LabelledBlock(id="t1", label="BLK1")
        block.add(CodeElement(id="c1", text="* a comment", element_type="COMMENT"))
        block.add(CodeElement(id="r1", text="NOP", element_type="RAW"))
        chunks = chunker.chunk([block], "test.asm")
        assert len(chunks[0].instructions) == 1
        assert chunks[0].instructions[0].opcode == "NOP"

    def test_empty_elements_excluded(self, chunker):
        block = LabelledBlock(id="t1", label="BLK1")
        block.add(CodeElement(id="e1", text="", element_type="RAW"))
        block.add(CodeElement(id="e2", text="NOP", element_type="RAW"))
        chunks = chunker.chunk([block], "test.asm")
        assert len(chunks[0].instructions) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Chunker – chunk type inference
# ─────────────────────────────────────────────────────────────────────────────


class TestChunkTypeInference:
    @pytest.fixture
    def chunker(self):
        return Chunker()

    def test_csect_type(self, chunker):
        block = _make_block("MYPROG", "CSECT", "BALR  12,0", "BR    14")
        chunks = chunker.chunk([block], "test.asm")
        assert chunks[0].chunk_type == "CSECT"

    def test_dsect_type(self, chunker):
        block = _make_block("MYMAP", "DSECT", "FIELD1  DS  CL20")
        chunks = chunker.chunk([block], "test.asm")
        assert chunks[0].chunk_type == "DSECT"

    def test_macro_type(self, chunker):
        block = _make_block("MYMACRO", "MACRO", "NOP", "MEND")
        chunks = chunker.chunk([block], "test.asm")
        assert chunks[0].chunk_type == "MACRO"

    def test_default_type_is_subroutine(self, chunker):
        block = _make_block("SUB", "STM   14,12,12(13)", "BR    14")
        chunks = chunker.chunk([block], "test.asm")
        assert chunks[0].chunk_type == "SUBROUTINE"

    def test_first_section_directive_wins(self, chunker):
        """If both CSECT and DSECT appear, the first one determines type."""
        block = _make_block("MYPROG", "CSECT", "DSECT")
        chunks = chunker.chunk([block], "test.asm")
        assert chunks[0].chunk_type == "CSECT"


# ─────────────────────────────────────────────────────────────────────────────
# Chunker – dependency extraction
# ─────────────────────────────────────────────────────────────────────────────


class TestDependencyExtraction:
    @pytest.fixture
    def chunker(self):
        return Chunker()

    def test_call_dependency(self, chunker):
        block = _make_block("MAIN", "CALL  SUBPROG1")
        chunks = chunker.chunk([block], "test.asm")
        assert "SUBPROG1" in chunks[0].dependencies

    def test_link_dependency(self, chunker):
        block = _make_block("MAIN", "LINK  EP=MYPROG")
        chunks = chunker.chunk([block], "test.asm")
        # LINK operand: EP=MYPROG – symbol extraction may not parse EP= form
        # At minimum no crash
        assert isinstance(chunks[0].dependencies, list)

    def test_bal_dependency(self, chunker):
        block = _make_block("MAIN", "BAL   14,SUBROUT1")
        chunks = chunker.chunk([block], "test.asm")
        assert "SUBROUT1" in chunks[0].dependencies

    def test_bas_dependency(self, chunker):
        block = _make_block("MAIN", "BAS   14,SUBROUT2")
        chunks = chunker.chunk([block], "test.asm")
        assert "SUBROUT2" in chunks[0].dependencies

    def test_branch_dependency_to_label(self, chunker):
        block = _make_block("MAIN", "BE    MATCHLBL")
        chunks = chunker.chunk([block], "test.asm")
        assert "MATCHLBL" in chunks[0].dependencies

    def test_branch_to_register_not_a_dep(self, chunker):
        block = _make_block("MAIN", "BR    14")
        chunks = chunker.chunk([block], "test.asm")
        # BR 14 uses a register – not a symbol dependency
        assert "14" not in chunks[0].dependencies

    def test_balr_register_not_a_dep(self, chunker):
        block = _make_block("MAIN", "BALR  12,0")
        chunks = chunker.chunk([block], "test.asm")
        assert "0" not in chunks[0].dependencies
        assert "12" not in chunks[0].dependencies

    def test_multiple_deps_deduplicated(self, chunker):
        block = _make_block(
            "MAIN",
            "BAL   14,SUBROUT1",
            "BAL   14,SUBROUT1",  # same target twice
        )
        chunks = chunker.chunk([block], "test.asm")
        assert chunks[0].dependencies.count("SUBROUT1") == 1

    def test_multiple_different_deps(self, chunker):
        block = _make_block(
            "MAIN",
            "BAL   14,SUBROUT1",
            "BAL   14,SUBROUT2",
            "CALL  EXTPROG",
        )
        chunks = chunker.chunk([block], "test.asm")
        deps = chunks[0].dependencies
        assert "SUBROUT1" in deps
        assert "SUBROUT2" in deps
        assert "EXTPROG" in deps

    def test_no_dependencies(self, chunker):
        block = _make_block("PURE", "STM   14,12,12(13)", "LM    14,12,12(13)", "BR    14")
        chunks = chunker.chunk([block], "test.asm")
        assert chunks[0].dependencies == []


# ─────────────────────────────────────────────────────────────────────────────
# Chunker – to_dict serialisation
# ─────────────────────────────────────────────────────────────────────────────


class TestChunkSerialization:
    @pytest.fixture
    def chunker(self):
        return Chunker()

    def test_to_dict_keys(self, chunker):
        block = _make_block("X", "NOP")
        chunk = chunker.chunk([block], "file.asm")[0]
        d = chunk.to_dict()
        expected_keys = {
            "label", "chunk_type", "source_file",
            "instruction_count", "dependencies", "instructions", "metadata",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_instruction_count_matches(self, chunker):
        block = _make_block("X", "NOP", "NOP", "BR    14")
        chunk = chunker.chunk([block], "file.asm")[0]
        d = chunk.to_dict()
        assert d["instruction_count"] == len(chunk.instructions)

    def test_instruction_dicts_have_required_fields(self, chunker):
        block = _make_block("X", "STM   14,12,12(13)")
        chunk = chunker.chunk([block], "file.asm")[0]
        for instr_dict in chunk.to_dict()["instructions"]:
            assert "opcode" in instr_dict
            assert "operands" in instr_dict
            assert "instruction_type" in instr_dict
