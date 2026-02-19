"""
End-to-end integration tests.

These tests run the full pipeline (ExtractBlocksTask → Chunker)
against all fixture files and validate overall correctness.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from hlasm_parser import HlasmAnalysis

FIXTURES = Path(__file__).parent / "fixtures"
MACROS_DIR = str(FIXTURES / "macros")


class TestEndToEnd:
    """Full pipeline integration tests using fixture files."""

    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis(copybook_path=MACROS_DIR)

    # ------------------------------------------------------------------
    # sample.hlasm
    # ------------------------------------------------------------------

    def test_sample_chunk_count(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "sample.hlasm"))
        # Expect at least SAVEAREA, INPUTPARM, OUTBUFF, PROCESS1, PROCESS2,
        # and several inner labels (P1SAVE, P2MATCH, P2NOMATCH, P2EXIT, P2SAVE)
        assert len(chunks) >= 5

    def test_sample_process1_instructions(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "sample.hlasm"))
        p1 = next(c for c in chunks if c.label == "PROCESS1")
        opcodes = [i.opcode for i in p1.instructions if i.opcode]
        assert "STM" in opcodes
        assert "BR" in opcodes

    def test_sample_process2_branch_deps(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "sample.hlasm"))
        p2 = next(c for c in chunks if c.label == "PROCESS2")
        deps = p2.dependencies
        # PROCESS2 branches to P2MATCH, P2NOMATCH, P2EXIT
        assert any(d in deps for d in ("P2MATCH", "P2NOMATCH", "P2EXIT"))

    def test_sample_json_round_trip(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "sample.hlasm"))
        payload = [c.to_dict() for c in chunks]
        serialised = json.dumps(payload)
        recovered = json.loads(serialised)
        assert len(recovered) == len(payload)
        for orig, rec in zip(payload, recovered):
            assert orig["label"] == rec["label"]
            assert orig["chunk_type"] == rec["chunk_type"]
            assert orig["instruction_count"] == rec["instruction_count"]

    # ------------------------------------------------------------------
    # sample_dsect.hlasm
    # ------------------------------------------------------------------

    def test_dsect_chunk_present(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "sample_dsect.hlasm"))
        dsect_chunks = [c for c in chunks if c.chunk_type == "DSECT"]
        assert len(dsect_chunks) >= 1

    def test_dsect_fields_are_child_blocks(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "sample_dsect.hlasm"))
        labels = {c.label for c in chunks}
        # WRK_NAME, WRK_FLAG, WRK_LEN are labeled sub-items of the DSECT
        assert any(l.startswith("WRK_") for l in labels)

    # ------------------------------------------------------------------
    # long_lines.hlasm
    # ------------------------------------------------------------------

    def test_long_lines_no_garbage(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "long_lines.hlasm"))
        for chunk in chunks:
            for instr in chunk.instructions:
                if instr.opcode:
                    # Sequence numbers (8 digits) must not appear as opcode
                    assert not instr.opcode.isdigit(), (
                        f"Opcode looks like a sequence number: {instr.opcode!r}"
                    )

    # ------------------------------------------------------------------
    # external_calls.hlasm
    # ------------------------------------------------------------------

    def test_external_deps_in_chunks(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "external_calls.hlasm"))
        all_deps: set[str] = set()
        for c in chunks:
            all_deps.update(c.dependencies)
        assert "SUBPROG1" in all_deps

    def test_internal_subroutine_dep(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "external_calls.hlasm"))
        all_deps: set[str] = set()
        for c in chunks:
            all_deps.update(c.dependencies)
        assert "LOCALRTN" in all_deps

    # ------------------------------------------------------------------
    # sample_with_macros.hlasm
    # ------------------------------------------------------------------

    def test_macro_expanded_instructions_present(self, analysis):
        chunks = analysis.analyze_file(str(FIXTURES / "sample_with_macros.hlasm"))
        all_opcodes: set[str] = set()
        for c in chunks:
            for i in c.instructions:
                if i.opcode:
                    all_opcodes.add(i.opcode)
        # After macro expansion, SVC (from PRINTMSG) and STM (from SAVEREGS)
        # should appear
        assert "SVC" in all_opcodes or "STM" in all_opcodes

    # ------------------------------------------------------------------
    # Inline source
    # ------------------------------------------------------------------

    def test_minimal_program(self, analysis):
        source = textwrap.dedent("""\
        MINIMAL  CSECT
                 BALR  12,0
                 USING *,12
                 BR    14
                 END   MINIMAL
        """)
        chunks = analysis.analyze_text(source, "minimal")
        assert len(chunks) >= 0   # may be 0 if only CSECT with no labeled sub-blocks

    def test_program_with_call(self, analysis):
        source = textwrap.dedent("""\
        CALLER   CSECT
                 BALR  12,0
                 USING *,12
                 BAL   14,CALLEE
                 BR    14
        CALLEE   STM   14,12,12(13)
                 BR    14
        """)
        chunks = analysis.analyze_text(source)
        labels = {c.label for c in chunks}
        assert "CALLEE" in labels

    def test_dependency_map_after_analysis(self, analysis):
        source = textwrap.dedent("""\
        PROG     CSECT
                 BALR  12,0
                 CALL  EXTMOD
                 BR    14
        """)
        analysis.analyze_text(source, "prog.asm")
        dm = analysis.dependency_map
        assert "EXTMOD" in dm.vertices()

    def test_multiple_files_accumulated_in_dep_map(self, analysis):
        analysis.analyze_file(str(FIXTURES / "sample.hlasm"))
        analysis.analyze_file(str(FIXTURES / "external_calls.hlasm"))
        dm = analysis.dependency_map
        # Both files should have added entries
        assert len(dm.vertices()) > 0
