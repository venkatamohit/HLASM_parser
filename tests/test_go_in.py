"""
Tests for the shop-specific GO / IN subroutine-call convention.

Pattern
-------
Main program calls subroutines with::

    GO    MYSUB               unconditional call
    GOIF  MYSUB               conditional call (condition implied by prior test)
    GOIFNOT MYSUB,COND        conditional call with inline condition

Subroutine body begins with::

    MYSUB    IN               entry-point marker  (label zone + IN opcode)

Subroutines may be:

* **Inline** – defined in the same source file after the main program body.
* **External** – in a separate file named ``MYSUB.asm`` / ``MYSUB.hlasm``
  in the *external_path* directory.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from hlasm_parser import HlasmAnalysis
from hlasm_parser.parser.instruction_parser import (
    CALL_OPCODES,
    ENTRY_MARKER_OPCODES,
    InstructionParser,
)
from hlasm_parser.pipeline.extract_blocks import ExtractBlocksTask
from hlasm_parser.pipeline.mnemonics import STANDARD_MNEMONICS

FIXTURES   = Path(__file__).parent / "fixtures"
PROGRAMS   = FIXTURES / "programs"
MACROS_DIR = str(FIXTURES / "macros")


# ─────────────────────────────────────────────────────────────────────────────
# InstructionParser – GO family
# ─────────────────────────────────────────────────────────────────────────────


class TestGoInstructionParsing:
    @pytest.fixture
    def parser(self):
        return InstructionParser()

    # ── GO ───────────────────────────────────────────────────────────────────

    def test_go_classified_as_call(self, parser):
        instr = parser.parse("GO    VALIDATE")
        assert instr.instruction_type == "CALL"

    def test_go_opcode_extracted(self, parser):
        instr = parser.parse("GO    VALIDATE")
        assert instr.opcode == "GO"

    def test_go_target_is_first_operand(self, parser):
        instr = parser.parse("GO    MYSUB")
        assert instr.operands == ["MYSUB"]

    def test_goif_classified_as_call(self, parser):
        instr = parser.parse("GOIF  CLEANUP")
        assert instr.instruction_type == "CALL"

    def test_goif_target_extracted(self, parser):
        instr = parser.parse("GOIF  CLEANUP")
        assert instr.operands[0] == "CLEANUP"

    def test_goifnot_classified_as_call(self, parser):
        instr = parser.parse("GOIFNOT ERROUT,EQ")
        assert instr.instruction_type == "CALL"
        assert instr.operands[0] == "ERROUT"

    def test_go_in_call_opcodes_set(self):
        assert "GO" in CALL_OPCODES
        assert "GOIF" in CALL_OPCODES
        assert "GOIFNOT" in CALL_OPCODES

    # ── IN / OUT entry markers ───────────────────────────────────────────────

    def test_in_classified_as_entry_marker(self, parser):
        instr = parser.parse("IN")
        assert instr.instruction_type == "ENTRY_MARKER"

    def test_out_classified_as_entry_marker(self, parser):
        instr = parser.parse("OUT")
        assert instr.instruction_type == "ENTRY_MARKER"

    def test_in_in_entry_marker_opcodes_set(self):
        assert "IN" in ENTRY_MARKER_OPCODES
        assert "OUT" in ENTRY_MARKER_OPCODES


# ─────────────────────────────────────────────────────────────────────────────
# Mnemonics – GO / IN must not trigger macro expansion
# ─────────────────────────────────────────────────────────────────────────────


class TestGoInMnemonics:
    def test_go_in_standard_mnemonics(self):
        assert "GO" in STANDARD_MNEMONICS

    def test_in_in_standard_mnemonics(self):
        assert "IN" in STANDARD_MNEMONICS

    def test_goif_in_standard_mnemonics(self):
        assert "GOIF" in STANDARD_MNEMONICS

    def test_out_in_standard_mnemonics(self):
        assert "OUT" in STANDARD_MNEMONICS


# ─────────────────────────────────────────────────────────────────────────────
# LabelBlockPass – <label>  IN  creates a labeled block
# ─────────────────────────────────────────────────────────────────────────────


class TestGoInLabelBlocking:
    @pytest.fixture
    def task(self):
        return ExtractBlocksTask()

    def test_in_subroutine_becomes_labeled_block(self, task):
        source = textwrap.dedent("""\
        MAIN     CSECT
                 BALR  12,0
                 USING *,12
                 GO    MYSUB
                 BR    14
        MYSUB    IN
                 STM   14,12,12(13)
                 BR    14
        """)
        blocks = task.sections_from_text(source)
        labels = {b.label for b in blocks}
        assert "MYSUB" in labels

    def test_multiple_in_subroutines(self, task):
        source = textwrap.dedent("""\
        MAIN     CSECT
                 GO    SUBA
                 GO    SUBB
                 BR    14
        SUBA     IN
                 BR    14
        SUBB     IN
                 BR    14
        """)
        blocks = task.sections_from_text(source)
        labels = {b.label for b in blocks}
        assert "SUBA" in labels
        assert "SUBB" in labels

    def test_inline_fixture_parsed_without_error(self, task):
        blocks = task.sections(str(FIXTURES / "go_in_inline.hlasm"))
        assert len(blocks) > 0

    def test_inline_fixture_named_blocks(self, task):
        # HLASM label field is 8 chars max; fixture uses ≤8-char names.
        blocks = task.sections(str(FIXTURES / "go_in_inline.hlasm"))
        labels = {b.label for b in blocks}
        assert "VALIDATE" in labels   # 8 chars
        assert "TRANSFM"  in labels   # 7 chars (TRANSFORM truncated)
        assert "FMTNAME"  in labels   # 7 chars
        assert "CLEANUP"  in labels   # 7 chars


# ─────────────────────────────────────────────────────────────────────────────
# Chunker – chunk_type == "ENTRY" for <label>  IN  blocks
# ─────────────────────────────────────────────────────────────────────────────


class TestGoInChunkType:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis()

    def test_in_block_chunk_type_is_entry(self, analysis):
        source = textwrap.dedent("""\
        MAIN     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    IN
                 STM   14,12,12(13)
                 BR    14
        """)
        chunks = analysis.analyze_text(source)
        mysub = next((c for c in chunks if c.label == "MYSUB"), None)
        assert mysub is not None
        assert mysub.chunk_type == "ENTRY"

    def test_inline_fixture_all_in_blocks_are_entry(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "go_in_inline.hlasm"))
        entry_chunks = {c.label for c in chunks if c.chunk_type == "ENTRY"}
        # Labels in fixture are ≤8 chars (HLASM label-field constraint)
        assert "VALIDATE" in entry_chunks
        assert "TRANSFM"  in entry_chunks
        assert "FMTNAME"  in entry_chunks
        assert "CLEANUP"  in entry_chunks


# ─────────────────────────────────────────────────────────────────────────────
# Dependency extraction – GO creates dep on target
# ─────────────────────────────────────────────────────────────────────────────


class TestGoInDependencies:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis()

    def test_go_creates_dependency(self, analysis):
        source = textwrap.dedent("""\
        MAIN     CSECT
                 BALR  12,0
                 USING *,12
                 GO    VALIDATE
                 BR    14
        VALIDATE IN
                 BR    14
        """)
        chunks = analysis.analyze_text(source)
        all_deps: set[str] = set()
        for c in chunks:
            all_deps.update(c.dependencies)
        assert "VALIDATE" in all_deps

    def test_goif_creates_dependency(self, analysis):
        source = textwrap.dedent("""\
        MAIN     CSECT
                 TM    FLAG,X'01'
                 GOIF  CLEANUP
                 BR    14
        FLAG     DS    X
        CLEANUP  IN
                 BR    14
        """)
        chunks = analysis.analyze_text(source)
        all_deps: set[str] = set()
        for c in chunks:
            all_deps.update(c.dependencies)
        assert "CLEANUP" in all_deps

    def test_inline_fixture_go_deps_from_main(self, analysis):
        """The root prologue chunk must list all GO targets as dependencies."""
        chunks = analysis.analyze_file(str(FIXTURES / "go_in_inline.hlasm"))
        root = next((c for c in chunks if c.label == "HLASM_ROOT"), None)
        assert root is not None
        assert "VALIDATE" in root.dependencies
        assert "TRANSFM" in root.dependencies

    def test_inline_fixture_nested_go_dep(self, analysis):
        """TRANSFM calls FMTNAME via GO – that dep must appear."""
        chunks = analysis.analyze_file(str(FIXTURES / "go_in_inline.hlasm"))
        transform = next((c for c in chunks if c.label == "TRANSFM"), None)
        assert transform is not None
        assert "FMTNAME" in transform.dependencies

    def test_external_program_via_go(self, analysis):
        """GO EXTPROG1 where EXTPROG1 is not in the file → still tracked as dep."""
        chunks = analysis.analyze_file(str(FIXTURES / "go_in_inline.hlasm"))
        root = next((c for c in chunks if c.label == "HLASM_ROOT"), None)
        assert root is not None
        assert "EXTPROG1" in root.dependencies

    def test_goif_conditional_dep_tracked(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "go_in_inline.hlasm"))
        root = next((c for c in chunks if c.label == "HLASM_ROOT"), None)
        assert root is not None
        # GOIF CLEANUP is in the root prologue
        assert "CLEANUP" in root.dependencies


# ─────────────────────────────────────────────────────────────────────────────
# External file resolution – GO target resolved to separate file
# ─────────────────────────────────────────────────────────────────────────────


class TestGoInExternalFiles:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis(external_path=str(PROGRAMS))

    def test_external_program_resolved(self, analysis):
        """analyze_with_dependencies follows GO → EXTPROG1.asm."""
        results = analysis.analyze_with_dependencies(
            str(FIXTURES / "go_in_inline.hlasm")
        )
        resolved_files = set(results.keys())
        assert any("EXTPROG1" in f for f in resolved_files), (
            f"EXTPROG1 not resolved; resolved files: {resolved_files}"
        )

    def test_transitive_dependency_resolved(self, analysis):
        """EXTPROG1 calls EXTPROG2 via GO – both should be in the results."""
        results = analysis.analyze_with_dependencies(
            str(FIXTURES / "go_in_inline.hlasm")
        )
        resolved_files = set(results.keys())
        assert any("EXTPROG2" in f for f in resolved_files), (
            f"EXTPROG2 (transitive) not resolved; resolved files: {resolved_files}"
        )

    def test_extprog1_entry_chunk_type(self, analysis):
        """EXTPROG1's main block must have chunk_type ENTRY (it starts with IN)."""
        results = analysis.analyze_with_dependencies(
            str(FIXTURES / "go_in_inline.hlasm")
        )
        extprog1_key = next(
            (k for k in results if "EXTPROG1" in k), None
        )
        assert extprog1_key is not None
        entry_chunks = [c for c in results[extprog1_key] if c.chunk_type == "ENTRY"]
        assert len(entry_chunks) > 0

    def test_extprog1_depends_on_extprog2(self, analysis):
        """EXTPROG1 calls GO EXTPROG2 – that dep must be tracked."""
        results = analysis.analyze_with_dependencies(
            str(FIXTURES / "go_in_inline.hlasm")
        )
        extprog1_key = next(
            (k for k in results if "EXTPROG1" in k), None
        )
        assert extprog1_key is not None
        all_deps: set[str] = set()
        for c in results[extprog1_key]:
            all_deps.update(c.dependencies)
        assert "EXTPROG2" in all_deps

    def test_dependency_map_contains_chain(self, analysis):
        """Dependency map: main → EXTPROG1 → EXTPROG2."""
        analysis.analyze_with_dependencies(str(FIXTURES / "go_in_inline.hlasm"))
        dm = analysis.dependency_map
        vertices = dm.vertices()
        assert any("EXTPROG1" in v for v in vertices)
        assert any("EXTPROG2" in v for v in vertices)

    def test_standalone_external_file(self, analysis):
        """Parsing EXTPROG1.asm directly – entry chunk type recognised."""
        chunks = analysis.analyze_file(str(PROGRAMS / "EXTPROG1.asm"))
        entry_chunks = [c for c in chunks if c.chunk_type == "ENTRY"]
        assert len(entry_chunks) >= 1

    def test_standalone_external_dependencies(self, analysis):
        """Parsing EXTPROG1.asm directly – GO EXTPROG2 dep present."""
        chunks = analysis.analyze_file(str(PROGRAMS / "EXTPROG1.asm"))
        all_deps: set[str] = set()
        for c in chunks:
            all_deps.update(c.dependencies)
        assert "EXTPROG2" in all_deps


# ─────────────────────────────────────────────────────────────────────────────
# Mixed style – same file with both BAL and GO calls
# ─────────────────────────────────────────────────────────────────────────────


class TestMixedCallStyles:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis()

    def test_bal_and_go_both_tracked(self, analysis):
        source = textwrap.dedent("""\
        MIXED    CSECT
                 BALR  12,0
                 USING *,12
                 BAL   14,CLASSIC    Classic BAL subroutine call
                 GO    MODERN        Modern GO subroutine call
                 BR    14
        CLASSIC  STM   14,12,12(13)
                 BR    14
        MODERN   IN
                 STM   14,12,12(13)
                 BR    14
        """)
        chunks = analysis.analyze_text(source)
        labels  = {c.label for c in chunks}
        assert "CLASSIC" in labels
        assert "MODERN"  in labels

        classic = next(c for c in chunks if c.label == "CLASSIC")
        modern  = next(c for c in chunks if c.label == "MODERN")

        assert classic.chunk_type == "SUBROUTINE"
        assert modern.chunk_type  == "ENTRY"

        all_deps: set[str] = set()
        for c in chunks:
            all_deps.update(c.dependencies)
        assert "CLASSIC" in all_deps
        assert "MODERN"  in all_deps

    def test_in_block_contains_instructions(self, analysis):
        source = textwrap.dedent("""\
        PROG     CSECT
                 GO    DOWORK
                 BR    14
        DOWORK   IN
                 STM   14,12,12(13)
                 MVC   FIELD,=CL20' '
                 LM    14,12,12(13)
                 BR    14
        FIELD    DS    CL20
        """)
        chunks = analysis.analyze_text(source)
        sub = next((c for c in chunks if c.label == "DOWORK"), None)
        assert sub is not None
        opcodes = [i.opcode for i in sub.instructions if i.opcode]
        assert "STM" in opcodes
        assert "MVC" in opcodes
        assert "BR"  in opcodes
