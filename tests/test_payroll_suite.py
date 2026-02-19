"""
Integration tests for the payroll sample suite.

Files under test
----------------
fixtures/programs/PAYROLL.asm
    Main driver program.  Contains:
    - Classic BAL subroutines in-file: CALCBASE, PRTREORT
    - GO/IN   subroutines in-file   : INITWS,   VALIDATE
    - External GO calls to          : TAXCALC, DEDUCTNS, RPTWRITE

fixtures/programs/TAXCALC  (no extension – subroutine / macro convention)
    External tax-calculation module.  Contains:
    - IN entry point          : TAXCALC
    - GO/IN subroutine in-file: APPLYRT
    - External GO call to     : DEDUCTNS

fixtures/programs/DEDUCTNS  (no extension)
    External deductions module (leaf – no external GO).  Contains:
    - IN entry point             : DEDUCTNS
    - GO/IN subroutines in-file  : HLTHDED, RETIRE

fixtures/programs/RPTWRITE  (no extension)
    External report-writer module.  Contains:
    - IN entry point          : RPTWRITE
    - GO/IN subroutine in-file: FMTLINE
    - Classic BAL subroutine  : HDRBLD
    - External GO call to     : TAXCALC
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hlasm_parser import HlasmAnalysis

FIXTURES = Path(__file__).parent / "fixtures"
PROGRAMS = FIXTURES / "programs"
MACROS   = str(FIXTURES / "macros")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _all_deps(chunks) -> set[str]:
    deps: set[str] = set()
    for c in chunks:
        deps.update(c.dependencies)
    return deps


def _labels(chunks) -> set[str]:
    return {c.label for c in chunks}


def _chunk(chunks, label: str):
    return next((c for c in chunks if c.label == label), None)


# ─────────────────────────────────────────────────────────────────────────────
# Main driver – PAYROLL.asm (standalone parse)
# ─────────────────────────────────────────────────────────────────────────────


class TestPayrollMainDriver:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis(copybook_path=MACROS)

    @pytest.fixture
    def chunks(self, analysis):
        return analysis.analyze_file(str(PROGRAMS / "PAYROLL.asm"))

    # --- block presence --------------------------------------------------

    def test_has_minimum_chunks(self, chunks):
        """At least CALCBASE, PRTREORT, INITWS, VALIDATE should be present."""
        assert len(chunks) >= 4

    def test_classic_bal_subroutines_present(self, chunks):
        labels = _labels(chunks)
        assert "CALCBASE" in labels, "Classic BAL subroutine CALCBASE missing"
        assert "PRTREORT" in labels, "Classic BAL subroutine PRTREORT missing"

    def test_go_in_subroutines_present(self, chunks):
        labels = _labels(chunks)
        assert "INITWS"   in labels, "GO/IN subroutine INITWS missing"
        assert "VALIDATE" in labels, "GO/IN subroutine VALIDATE missing"

    # --- chunk_type -------------------------------------------------------

    def test_calcbase_is_subroutine(self, chunks):
        cb = _chunk(chunks, "CALCBASE")
        assert cb is not None
        assert cb.chunk_type == "SUBROUTINE"

    def test_prtreort_is_subroutine(self, chunks):
        pr = _chunk(chunks, "PRTREORT")
        assert pr is not None
        assert pr.chunk_type == "SUBROUTINE"

    def test_initws_is_entry(self, chunks):
        iw = _chunk(chunks, "INITWS")
        assert iw is not None
        assert iw.chunk_type == "ENTRY"

    def test_validate_is_entry(self, chunks):
        vl = _chunk(chunks, "VALIDATE")
        assert vl is not None
        assert vl.chunk_type == "ENTRY"

    # --- internal dependencies -------------------------------------------

    def test_internal_bal_deps_tracked(self, chunks):
        deps = _all_deps(chunks)
        assert "CALCBASE" in deps, "BAL target CALCBASE not in dependencies"
        assert "PRTREORT" in deps, "BAL target PRTREORT not in dependencies"

    def test_internal_go_deps_tracked(self, chunks):
        deps = _all_deps(chunks)
        assert "INITWS"   in deps, "GO target INITWS not in dependencies"
        assert "VALIDATE" in deps, "GO target VALIDATE not in dependencies"

    # --- external dependencies -------------------------------------------

    def test_external_go_deps_tracked(self, chunks):
        deps = _all_deps(chunks)
        assert "TAXCALC"  in deps, "External GO TAXCALC not tracked"
        assert "DEDUCTNS" in deps, "External GO DEDUCTNS not tracked"
        assert "RPTWRITE" in deps, "External GO RPTWRITE not tracked"

    # --- instructions inside subroutines ---------------------------------

    def test_calcbase_has_instructions(self, chunks):
        cb = _chunk(chunks, "CALCBASE")
        opcodes = [i.opcode for i in cb.instructions if i.opcode]
        assert "STM" in opcodes
        assert "BR"  in opcodes

    def test_validate_has_branches(self, chunks):
        vl = _chunk(chunks, "VALIDATE")
        deps = vl.dependencies
        # VALIDATE branches to VALERR and VALOK
        assert any(d in deps for d in ("VALERR", "VALOK"))

    # --- JSON round-trip -------------------------------------------------

    def test_json_round_trip(self, chunks):
        import json
        payload = [c.to_dict() for c in chunks]
        recovered = json.loads(json.dumps(payload))
        assert len(recovered) == len(payload)
        for orig, rec in zip(payload, recovered):
            assert orig["label"]             == rec["label"]
            assert orig["chunk_type"]        == rec["chunk_type"]
            assert orig["instruction_count"] == rec["instruction_count"]


# ─────────────────────────────────────────────────────────────────────────────
# External module – TAXCALC  (subroutine, no extension)
# ─────────────────────────────────────────────────────────────────────────────


class TestTaxcalcModule:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis(external_path=str(PROGRAMS))

    @pytest.fixture
    def chunks(self, analysis):
        return analysis.analyze_file(str(PROGRAMS / "TAXCALC"))

    def test_taxcalc_entry_present(self, chunks):
        labels = _labels(chunks)
        assert "TAXCALC" in labels

    def test_taxcalc_entry_chunk_type(self, chunks):
        tc = _chunk(chunks, "TAXCALC")
        assert tc is not None
        assert tc.chunk_type == "ENTRY"

    def test_applyrt_in_subroutine_present(self, chunks):
        labels = _labels(chunks)
        assert "APPLYRT" in labels, "Inline IN subroutine APPLYRT missing"

    def test_applyrt_chunk_type_is_entry(self, chunks):
        ar = _chunk(chunks, "APPLYRT")
        assert ar is not None
        assert ar.chunk_type == "ENTRY"

    def test_applyrt_dependency_tracked(self, chunks):
        deps = _all_deps(chunks)
        assert "APPLYRT" in deps

    def test_external_deductns_dependency_tracked(self, chunks):
        deps = _all_deps(chunks)
        assert "DEDUCTNS" in deps, "External GO DEDUCTNS not tracked from TAXCALC"

    def test_applyrt_has_arithmetic_instructions(self, chunks):
        ar = _chunk(chunks, "APPLYRT")
        opcodes = [i.opcode for i in ar.instructions if i.opcode]
        # APPLYRT does a multiply and divide
        assert "M" in opcodes or "MR" in opcodes or "D" in opcodes or "DR" in opcodes


# ─────────────────────────────────────────────────────────────────────────────
# External module – DEDUCTNS  (subroutine, no extension; leaf – no external GO)
# ─────────────────────────────────────────────────────────────────────────────


class TestDeductnsModule:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis()

    @pytest.fixture
    def chunks(self, analysis):
        return analysis.analyze_file(str(PROGRAMS / "DEDUCTNS"))

    def test_deductns_entry_present(self, chunks):
        assert "DEDUCTNS" in _labels(chunks)

    def test_deductns_entry_chunk_type(self, chunks):
        dd = _chunk(chunks, "DEDUCTNS")
        assert dd is not None
        assert dd.chunk_type == "ENTRY"

    def test_hlthded_in_subroutine_present(self, chunks):
        assert "HLTHDED" in _labels(chunks), "Inline HLTHDED subroutine missing"

    def test_retire_in_subroutine_present(self, chunks):
        assert "RETIRE" in _labels(chunks), "Inline RETIRE subroutine missing"

    def test_hlthded_chunk_type_is_entry(self, chunks):
        hh = _chunk(chunks, "HLTHDED")
        assert hh is not None
        assert hh.chunk_type == "ENTRY"

    def test_retire_chunk_type_is_entry(self, chunks):
        rt = _chunk(chunks, "RETIRE")
        assert rt is not None
        assert rt.chunk_type == "ENTRY"

    def test_hlthded_dependency_tracked(self, chunks):
        assert "HLTHDED" in _all_deps(chunks)

    def test_retire_dependency_tracked(self, chunks):
        assert "RETIRE" in _all_deps(chunks)

    def test_no_external_go_dependencies(self, chunks):
        """DEDUCTNS is a leaf module – should have no external GO calls
        to programs outside this file."""
        # Internal labels that exist in the file
        internal = _labels(chunks)
        external_deps = _all_deps(chunks) - internal
        # May still have branch label deps (HHLTEXIT, RTEXIT); those are fine.
        # The key: no external program name like TAXCALC/RPTWRITE/PAYROLL.
        for prog in ("TAXCALC", "RPTWRITE", "PAYROLL"):
            assert prog not in external_deps, (
                f"{prog} should not be a dependency of DEDUCTNS"
            )


# ─────────────────────────────────────────────────────────────────────────────
# External module – RPTWRITE  (subroutine, no extension; mixed BAL + IN + external GO)
# ─────────────────────────────────────────────────────────────────────────────


class TestRptwriteModule:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis(external_path=str(PROGRAMS))

    @pytest.fixture
    def chunks(self, analysis):
        return analysis.analyze_file(str(PROGRAMS / "RPTWRITE"))

    def test_rptwrite_entry_present(self, chunks):
        assert "RPTWRITE" in _labels(chunks)

    def test_rptwrite_entry_chunk_type(self, chunks):
        rw = _chunk(chunks, "RPTWRITE")
        assert rw is not None
        assert rw.chunk_type == "ENTRY"

    def test_fmtline_in_subroutine_present(self, chunks):
        assert "FMTLINE" in _labels(chunks), "Inline GO/IN subroutine FMTLINE missing"

    def test_fmtline_chunk_type_is_entry(self, chunks):
        fl = _chunk(chunks, "FMTLINE")
        assert fl is not None
        assert fl.chunk_type == "ENTRY"

    def test_hdrbld_bal_subroutine_present(self, chunks):
        assert "HDRBLD" in _labels(chunks), "Classic BAL subroutine HDRBLD missing"

    def test_hdrbld_chunk_type_is_subroutine(self, chunks):
        hb = _chunk(chunks, "HDRBLD")
        assert hb is not None
        assert hb.chunk_type == "SUBROUTINE"

    def test_hdrbld_dependency_tracked(self, chunks):
        assert "HDRBLD" in _all_deps(chunks), "BAL target HDRBLD not tracked"

    def test_fmtline_dependency_tracked(self, chunks):
        assert "FMTLINE" in _all_deps(chunks), "GO target FMTLINE not tracked"

    def test_external_taxcalc_dependency_tracked(self, chunks):
        assert "TAXCALC" in _all_deps(chunks), "External GO TAXCALC not tracked"

    def test_fmtline_has_move_instructions(self, chunks):
        fl = _chunk(chunks, "FMTLINE")
        assert fl is not None
        opcodes = [i.opcode for i in fl.instructions if i.opcode]
        assert "MVC" in opcodes


# ─────────────────────────────────────────────────────────────────────────────
# Cross-file dependency resolution – analyze_with_dependencies
# ─────────────────────────────────────────────────────────────────────────────


class TestPayrollWithDependencies:
    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis(
            copybook_path=MACROS,
            external_path=str(PROGRAMS),
        )

    @pytest.fixture
    def results(self, analysis):
        return analysis.analyze_with_dependencies(
            str(PROGRAMS / "PAYROLL.asm")
        )

    # --- root file present -----------------------------------------------

    def test_root_file_in_results(self, results):
        assert str(PROGRAMS / "PAYROLL.asm") in results

    # --- direct external files resolved ----------------------------------

    def test_taxcalc_resolved(self, results):
        assert any("TAXCALC" in k for k in results), (
            f"TAXCALC not resolved; keys={set(results)}"
        )

    def test_deductns_resolved_directly(self, results):
        assert any("DEDUCTNS" in k for k in results), (
            f"DEDUCTNS (direct dep) not resolved; keys={set(results)}"
        )

    def test_rptwrite_resolved(self, results):
        assert any("RPTWRITE" in k for k in results), (
            f"RPTWRITE not resolved; keys={set(results)}"
        )

    # --- transitive resolution -------------------------------------------

    def test_deductns_resolved_transitively_via_taxcalc(self, results):
        """TAXCALC → DEDUCTNS: transitive dep must be resolved."""
        # DEDUCTNS appears as a direct dep of PAYROLL *and* TAXCALC,
        # so it must be in the result set.
        assert any("DEDUCTNS" in k for k in results)

    def test_taxcalc_resolved_via_rptwrite(self, results):
        """RPTWRITE → TAXCALC: even if TAXCALC already resolved, it must appear."""
        assert any("TAXCALC" in k for k in results)

    # --- chunk types in resolved files -----------------------------------

    def test_taxcalc_has_entry_chunk(self, results):
        key = next((k for k in results if "TAXCALC" in k), None)
        assert key is not None
        entry_chunks = [c for c in results[key] if c.chunk_type == "ENTRY"]
        assert len(entry_chunks) >= 1

    def test_deductns_has_two_entry_subroutines(self, results):
        key = next((k for k in results if "DEDUCTNS" in k), None)
        assert key is not None
        entry_labels = {c.label for c in results[key] if c.chunk_type == "ENTRY"}
        assert "HLTHDED" in entry_labels
        assert "RETIRE"  in entry_labels

    def test_rptwrite_has_mixed_chunk_types(self, results):
        key = next((k for k in results if "RPTWRITE" in k), None)
        assert key is not None
        type_map = {c.label: c.chunk_type for c in results[key]}
        assert type_map.get("FMTLINE") == "ENTRY"
        assert type_map.get("HDRBLD")  == "SUBROUTINE"

    # --- dependency map --------------------------------------------------

    def test_dependency_map_has_all_vertices(self, analysis, results):
        dm = analysis.dependency_map
        vertices = dm.vertices()
        assert any("TAXCALC"  in v for v in vertices)
        assert any("DEDUCTNS" in v for v in vertices)
        assert any("RPTWRITE" in v for v in vertices)

    def test_dependency_map_has_edges(self, analysis, results):
        dm = analysis.dependency_map
        d = dm.to_dict()
        assert "edges" in d
        assert len(d["edges"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Mixed call-style summary (inline source)
# ─────────────────────────────────────────────────────────────────────────────


class TestMixedStyleSummary:
    """Quick inline-source smoke test mirroring the payroll pattern."""

    @pytest.fixture
    def analysis(self):
        return HlasmAnalysis()

    def test_bal_and_go_in_same_program(self, analysis):
        import textwrap
        source = textwrap.dedent("""\
        DRIVER   CSECT
                 BALR  12,0
                 USING *,12
                 BAL   14,CLSUB    Classic BAL internal subroutine
                 GO    GOSUB       GO/IN internal subroutine
                 GO    EXTMOD      GO to external module
                 BR    14
        CLSUB    STM   14,12,12(13)
                 MVC   FIELD,=CL20'HELLO'
                 BR    14
        GOSUB    IN
                 STM   14,12,12(13)
                 MVI   FLAG,X'01'
                 BR    14
        FIELD    DS    CL20
        FLAG     DS    X
        """)
        chunks = analysis.analyze_text(source)
        labels = _labels(chunks)
        assert "CLSUB" in labels,  "Classic BAL sub CLSUB missing"
        assert "GOSUB" in labels,  "GO/IN sub GOSUB missing"

        assert _chunk(chunks, "CLSUB").chunk_type  == "SUBROUTINE"
        assert _chunk(chunks, "GOSUB").chunk_type  == "ENTRY"

        deps = _all_deps(chunks)
        assert "CLSUB"  in deps,  "BAL dep CLSUB not tracked"
        assert "GOSUB"  in deps,  "GO  dep GOSUB not tracked"
        assert "EXTMOD" in deps,  "External GO dep EXTMOD not tracked"
