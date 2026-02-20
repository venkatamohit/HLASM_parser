"""
Tests for LightParser – the lightweight GO/IN/OUT subroutine extractor.

Fixture layout
--------------
tests/fixtures/light_parser/
    driver.asm          Main driver; main GO calls are on lines 5-12.
    deps/
        SUBA.asm        External sub that calls SUBC (depth-2 test).
        SUBB.asm        Leaf external sub.
        SUBC.asm        Leaf external sub called by SUBA.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from hlasm_parser.pipeline.light_parser import LightParser

# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------

FIXTURES   = Path(__file__).parent / "fixtures" / "light_parser"
DRIVER     = FIXTURES / "driver.asm"
DEPS_DIR   = FIXTURES / "deps"

# Lines in driver.asm that contain the main GO calls (verified by line count)
MAIN_START = 5
MAIN_END   = 12


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_lp(tmp_path: Path, deps: str | Path | None = DEPS_DIR) -> LightParser:
    """Return a LightParser wired to the test fixture driver."""
    return LightParser(
        driver_path=DRIVER,
        deps_dir=deps,
        output_dir=tmp_path,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Static helper: _extract_range
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractRange:
    def test_correct_lines_returned(self, tmp_path):
        lp = _make_lp(tmp_path)
        lines = lp._extract_range(DRIVER, MAIN_START, MAIN_END)
        assert len(lines) == MAIN_END - MAIN_START + 1

    def test_first_line_is_csect(self, tmp_path):
        lp = _make_lp(tmp_path)
        lines = lp._extract_range(DRIVER, MAIN_START, MAIN_END)
        assert "CSECT" in lines[0]

    def test_last_line_is_br(self, tmp_path):
        lp = _make_lp(tmp_path)
        lines = lp._extract_range(DRIVER, MAIN_START, MAIN_END)
        assert "BR" in lines[-1]

    def test_start_before_1_clamped(self, tmp_path):
        lp = _make_lp(tmp_path)
        lines = lp._extract_range(DRIVER, 0, 2)
        # 0 is clamped to 0 index → same as start_line=1
        assert len(lines) == 2

    def test_single_line(self, tmp_path):
        lp = _make_lp(tmp_path)
        lines = lp._extract_range(DRIVER, 8, 8)
        assert len(lines) == 1
        assert "SUBA" in lines[0]


# ─────────────────────────────────────────────────────────────────────────────
# Static helper: _find_go_targets
# ─────────────────────────────────────────────────────────────────────────────


class TestFindGoTargets:
    def test_go_found(self):
        lines = ["         GO    MYSUB"]
        assert "MYSUB" in LightParser._find_go_targets(lines)

    def test_goif_found(self):
        lines = ["         GOIF  CLEANUP"]
        assert "CLEANUP" in LightParser._find_go_targets(lines)

    def test_goifnot_found(self):
        lines = ["         GOIFNOT ERROUT,EQ"]
        assert "ERROUT" in LightParser._find_go_targets(lines)

    def test_comment_line_skipped(self):
        lines = ["* GO SKIPME", "         GO    REALGO"]
        targets = LightParser._find_go_targets(lines)
        assert "SKIPME" not in targets
        assert "REALGO" in targets

    def test_order_preserved(self):
        lines = [
            "         GO    FIRST",
            "         GO    SECOND",
            "         GOIF  THIRD",
        ]
        targets = LightParser._find_go_targets(lines)
        assert targets == ["FIRST", "SECOND", "THIRD"]

    def test_deduplication(self):
        lines = ["         GO    SAME", "         GO    SAME"]
        targets = LightParser._find_go_targets(lines)
        assert targets.count("SAME") == 1

    def test_names_uppercased(self):
        lines = ["         GO    mysub"]
        targets = LightParser._find_go_targets(lines)
        assert "MYSUB" in targets
        assert "mysub" not in targets

    def test_empty_lines(self):
        assert LightParser._find_go_targets([]) == []
        assert LightParser._find_go_targets(["* just a comment"]) == []


# ─────────────────────────────────────────────────────────────────────────────
# _find_subroutine
# ─────────────────────────────────────────────────────────────────────────────


class TestFindSubroutine:
    def test_found_inline_in_driver(self, tmp_path):
        lp = _make_lp(tmp_path, deps=None)
        block = lp._find_subroutine("INLSUB")
        assert block is not None

    def test_found_in_deps_dir(self, tmp_path):
        lp = _make_lp(tmp_path)
        block = lp._find_subroutine("SUBA")
        assert block is not None

    def test_block_starts_with_in_line(self, tmp_path):
        lp = _make_lp(tmp_path)
        block = lp._find_subroutine("SUBA")
        assert block is not None
        assert "IN" in block[0]
        assert "SUBA" in block[0]

    def test_block_ends_at_out(self, tmp_path):
        lp = _make_lp(tmp_path)
        block = lp._find_subroutine("SUBA")
        assert block is not None
        assert "OUT" in block[-1]

    def test_inline_sub_ends_at_out(self, tmp_path):
        lp = _make_lp(tmp_path, deps=None)
        block = lp._find_subroutine("INLSUB")
        assert block is not None
        assert "OUT" in block[-1]

    def test_missing_returns_none(self, tmp_path):
        lp = _make_lp(tmp_path)
        assert lp._find_subroutine("NOSUCHSUB") is None

    def test_no_deps_dir_still_finds_inline(self, tmp_path):
        lp = _make_lp(tmp_path, deps=None)
        block = lp._find_subroutine("INLSUB")
        assert block is not None

    def test_no_deps_dir_misses_external(self, tmp_path):
        lp = _make_lp(tmp_path, deps=None)
        # SUBA is only in deps/SUBA.asm, not in driver
        assert lp._find_subroutine("SUBA") is None

    def test_fallback_stops_before_next_in(self, tmp_path):
        """Subroutine without explicit OUT stops before the next IN header."""
        src = textwrap.dedent("""\
        * no OUT here
        ALPHA    IN
                 MVI   0(13),X'00'
                 BR    14
        BETA     IN
                 BR    14
        """)
        driver = tmp_path / "no_out.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        block = lp._find_subroutine("ALPHA")
        assert block is not None
        # Must not include the BETA IN line
        assert not any("BETA" in ln and "IN" in ln for ln in block)


# ─────────────────────────────────────────────────────────────────────────────
# run() – integration
# ─────────────────────────────────────────────────────────────────────────────


class TestLightParserRun:
    @pytest.fixture
    def lp(self, tmp_path):
        parser = _make_lp(tmp_path)
        parser.run(MAIN_START, MAIN_END)
        return parser

    def test_main_txt_created(self, lp, tmp_path):
        assert (tmp_path / "main_sub.txt").exists()

    def test_main_chunk_stored(self, lp):
        assert "main" in lp.chunks
        assert len(lp.chunks["main"]) == MAIN_END - MAIN_START + 1

    def test_external_suba_resolved(self, lp, tmp_path):
        assert (tmp_path / "SUBA_sub.txt").exists()

    def test_external_subb_resolved(self, lp, tmp_path):
        assert (tmp_path / "SUBB_sub.txt").exists()

    def test_inline_inlsub_resolved(self, lp, tmp_path):
        assert (tmp_path / "INLSUB_sub.txt").exists()

    def test_nested_subc_resolved(self, lp, tmp_path):
        """SUBC is called by SUBA – must be resolved transitively."""
        assert (tmp_path / "SUBC_sub.txt").exists()

    def test_flow_has_main_entry(self, lp):
        assert "main" in lp.flow

    def test_main_calls_suba(self, lp):
        assert "SUBA" in lp.flow["main"]

    def test_main_calls_subb(self, lp):
        assert "SUBB" in lp.flow["main"]

    def test_main_calls_inlsub(self, lp):
        assert "INLSUB" in lp.flow["main"]

    def test_suba_calls_subc(self, lp):
        assert "SUBC" in lp.flow.get("SUBA", [])

    def test_subb_is_leaf(self, lp):
        assert lp.flow.get("SUBB", []) == []

    def test_subc_is_leaf(self, lp):
        assert lp.flow.get("SUBC", []) == []

    def test_no_missing_for_fully_resolved_fixture(self, lp):
        assert lp.missing == []

    def test_missing_tracked_when_not_found(self, tmp_path):
        src = "PROG CSECT\n         GO    GHOST\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert "GHOST" in lp.missing

    def test_circular_go_not_infinite(self, tmp_path):
        """Circular GO references must not cause infinite recursion."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    ALPHA
                 BR    14
        ALPHA    IN
                 GO    BETA
                 BR    14
                 OUT
        BETA     IN
                 GO    ALPHA
                 BR    14
                 OUT
        """)
        driver = tmp_path / "circular.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)   # Should complete without RecursionError
        assert "ALPHA" in lp.chunks
        assert "BETA" in lp.chunks

    def test_txt_files_contain_source_lines(self, lp, tmp_path):
        content = (tmp_path / "SUBA_sub.txt").read_text()
        assert "SUBA" in content
        assert "IN" in content


# ─────────────────────────────────────────────────────────────────────────────
# Output: JSON
# ─────────────────────────────────────────────────────────────────────────────


class TestLightParserJson:
    @pytest.fixture
    def data(self, tmp_path):
        lp = _make_lp(tmp_path)
        lp.run(MAIN_START, MAIN_END)
        return lp.to_json()

    def test_has_entry_key(self, data):
        assert data["entry"] == "main"

    def test_has_flow_key(self, data):
        assert "flow" in data

    def test_has_chunk_line_counts(self, data):
        assert "chunk_line_counts" in data
        assert "main" in data["chunk_line_counts"]

    def test_has_missing_key(self, data):
        assert "missing" in data

    def test_flow_suba_in_main_children(self, data):
        assert "SUBA" in data["flow"]["main"]

    def test_json_string_is_valid(self, tmp_path):
        lp = _make_lp(tmp_path)
        lp.run(MAIN_START, MAIN_END)
        parsed = json.loads(lp.to_json_str())
        assert parsed["entry"] == "main"


# ─────────────────────────────────────────────────────────────────────────────
# Output: DOT / CFG
# ─────────────────────────────────────────────────────────────────────────────


class TestLightParserDot:
    @pytest.fixture
    def dot(self, tmp_path):
        lp = _make_lp(tmp_path)
        lp.run(MAIN_START, MAIN_END)
        return lp.to_dot()

    def test_is_digraph(self, dot):
        assert "digraph" in dot

    def test_main_node_present(self, dot):
        assert '"main"' in dot

    def test_suba_node_present(self, dot):
        assert '"SUBA"' in dot

    def test_subc_node_present(self, dot):
        assert '"SUBC"' in dot

    def test_edge_main_to_suba(self, dot):
        assert '"main" -> "SUBA"' in dot

    def test_edge_suba_to_subc(self, dot):
        assert '"SUBA" -> "SUBC"' in dot

    def test_missing_node_coloured_red(self, tmp_path):
        src = "PROG CSECT\n         GO    GHOST\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)
        dot = lp.to_dot()
        assert "GHOST" in dot
        assert "red" in dot

    def test_resolved_nodes_coloured_lightblue(self, dot):
        assert "lightblue" in dot


# ─────────────────────────────────────────────────────────────────────────────
# Output: Mermaid
# ─────────────────────────────────────────────────────────────────────────────


class TestLightParserMermaid:
    @pytest.fixture
    def mmd(self, tmp_path):
        lp = _make_lp(tmp_path)
        lp.run(MAIN_START, MAIN_END)
        return lp.to_mermaid()

    def test_starts_with_flowchart(self, mmd):
        assert mmd.startswith("flowchart TD")

    def test_main_to_suba_edge(self, mmd):
        assert "main --> SUBA" in mmd

    def test_suba_to_subc_edge(self, mmd):
        assert "SUBA --> SUBC" in mmd


# ─────────────────────────────────────────────────────────────────────────────
# CLI integration
# ─────────────────────────────────────────────────────────────────────────────


class TestLightParserCli:
    def test_missing_start_line_exits_nonzero(self, tmp_path):
        from hlasm_parser.cli import main
        rc = main([
            str(DRIVER),
            "--light-parser",
            "--end-line", "12",
            "-s", str(tmp_path / "out"),
        ])
        assert rc != 0

    def test_missing_end_line_exits_nonzero(self, tmp_path):
        from hlasm_parser.cli import main
        rc = main([
            str(DRIVER),
            "--light-parser",
            "--start-line", "5",
            "-s", str(tmp_path / "out"),
        ])
        assert rc != 0

    def test_missing_split_output_exits_nonzero(self, tmp_path):
        from hlasm_parser.cli import main
        rc = main([
            str(DRIVER),
            "--light-parser",
            "--start-line", "5",
            "--end-line", "12",
        ])
        assert rc != 0

    def test_full_invocation_exits_zero(self, tmp_path):
        from hlasm_parser.cli import main
        out = tmp_path / "chunks"
        rc = main([
            str(DRIVER),
            "-c", str(DEPS_DIR),
            "--light-parser",
            "--start-line", str(MAIN_START),
            "--end-line", str(MAIN_END),
            "-s", str(out),
        ])
        assert rc == 0

    def test_full_invocation_creates_files(self, tmp_path):
        from hlasm_parser.cli import main
        out = tmp_path / "chunks"
        main([
            str(DRIVER),
            "-c", str(DEPS_DIR),
            "--light-parser",
            "--start-line", str(MAIN_START),
            "--end-line", str(MAIN_END),
            "-s", str(out),
        ])
        assert (out / "chunks" / "main_sub.txt").exists()
        assert (out / "chunks" / "SUBA_sub.txt").exists()
        assert (out / "cfg" / "flow.json").exists()
        assert (out / "cfg" / "cfg.dot").exists()

    def test_mermaid_cfg_format(self, tmp_path):
        from hlasm_parser.cli import main
        out = tmp_path / "chunks"
        main([
            str(DRIVER),
            "-c", str(DEPS_DIR),
            "--light-parser",
            "--start-line", str(MAIN_START),
            "--end-line", str(MAIN_END),
            "-s", str(out),
            "--cfg-format", "mermaid",
        ])
        assert (out / "cfg" / "cfg.mmd").exists()
        content = (out / "cfg" / "cfg.mmd").read_text()
        assert "flowchart TD" in content


# ─────────────────────────────────────────────────────────────────────────────
# L (Link) call detection
# ─────────────────────────────────────────────────────────────────────────────


class TestLinkCallDetection:
    """Tests for L <name> Link calls alongside GO calls in the same graph."""

    # ── _find_go_targets – L detection unit tests ─────────────────────────

    def test_l_link_found(self):
        lines = ["         L     MYLIB"]
        assert "MYLIB" in LightParser._find_go_targets(lines)

    def test_l_load_register_not_matched(self):
        """L R1,FIELD is a Load, not a Link – must be ignored."""
        lines = ["         L     R1,MYFIELD"]
        assert "R1" not in LightParser._find_go_targets(lines)
        assert "MYFIELD" not in LightParser._find_go_targets(lines)

    def test_l_load_with_base_displacement_not_matched(self):
        lines = ["         L     R2,0(R1)"]
        assert LightParser._find_go_targets(lines) == []

    def test_l_register_alias_excluded(self):
        """L R15 looks like a Link but R0-R15 are registers – must be skipped."""
        for reg in ("R0", "R1", "R9", "R10", "R15"):
            lines = [f"         L     {reg}"]
            assert reg.upper() not in LightParser._find_go_targets(lines), reg

    def test_l_in_label_column_not_matched(self):
        """L in the label column (no leading spaces) is not a Link opcode."""
        lines = ["L        DS    CL8"]
        assert LightParser._find_go_targets(lines) == []

    def test_l_with_inline_comment(self):
        lines = ["         L     MYSUB          * call MYSUB"]
        assert "MYSUB" in LightParser._find_go_targets(lines)

    def test_l_and_go_both_found_in_same_block(self):
        lines = [
            "         GO    SUBA",
            "         L     SUBD",
            "         GOIF  SUBB",
        ]
        targets = LightParser._find_go_targets(lines)
        assert "SUBA" in targets
        assert "SUBD" in targets
        assert "SUBB" in targets

    def test_l_order_preserved_with_go(self):
        lines = [
            "         L     FIRST",
            "         GO    SECOND",
        ]
        targets = LightParser._find_go_targets(lines)
        assert targets.index("FIRST") < targets.index("SECOND")

    def test_l_deduplicated(self):
        lines = ["         L     SAME", "         L     SAME"]
        assert LightParser._find_go_targets(lines).count("SAME") == 1

    # ── Integration: L target resolved from deps dir ───────────────────────

    def test_l_target_resolved_from_deps(self, tmp_path):
        """L SUBD in main flow → SUBD.txt created from deps/SUBD.asm."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    SUBA
                 L     SUBD
                 BR    14
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=DEPS_DIR, output_dir=tmp_path / "out")
        lp.run(1, 4)
        assert (tmp_path / "out" / "SUBD_sub.txt").exists()

    def test_l_target_in_flow(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    SUBA
                 L     SUBD
                 BR    14
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=DEPS_DIR, output_dir=tmp_path / "out")
        lp.run(1, 4)
        assert "SUBD" in lp.flow["main"]

    def test_l_and_go_share_same_graph(self, tmp_path):
        """GO and L targets both appear as children in the same flow node."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    SUBA
                 L     SUBD
                 BR    14
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=DEPS_DIR, output_dir=tmp_path / "out")
        lp.run(1, 4)
        children = lp.flow["main"]
        assert "SUBA" in children
        assert "SUBD" in children

    def test_l_inside_subroutine_resolved_recursively(self, tmp_path):
        """L call inside a GO-resolved subroutine must be followed transitively."""
        sube_src = textwrap.dedent("""\
        SUBE     IN
                 MVI   0(13),X'01'
                 BR    14
                 OUT
        """)
        (tmp_path / "SUBE.asm").write_text(sube_src)
        sub_src = textwrap.dedent("""\
        INNER    IN
                 L     SUBE
                 BR    14
                 OUT
        """)
        (tmp_path / "INNER.asm").write_text(sub_src)
        driver = tmp_path / "prog.asm"
        driver.write_text("PROG CSECT\n         GO    INNER\n         BR    14\n")
        lp = LightParser(driver_path=driver, deps_dir=tmp_path, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert "INNER" in lp.chunks
        assert "SUBE" in lp.chunks
        assert "SUBE" in lp.flow.get("INNER", [])

    def test_l_target_missing_tracked(self, tmp_path):
        src = "PROG CSECT\n         L     GHOST\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert "GHOST" in lp.missing

    def test_l_and_go_missing_both_tracked(self, tmp_path):
        src = "PROG CSECT\n         GO    NOGOSUB\n         L     NOLSUB\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 4)
        assert "NOGOSUB" in lp.missing
        assert "NOLSUB" in lp.missing

    # ── L Rx,=V(SUBNAME) – V-type address constant ───────────────────────────

    def test_v_constant_found(self):
        lines = ["         L     R15,=V(EXTSUB)"]
        assert "EXTSUB" in LightParser._find_go_targets(lines)

    def test_v_constant_with_r14(self):
        lines = ["         L     R14,=V(MYMOD)"]
        assert "MYMOD" in LightParser._find_go_targets(lines)

    def test_v_constant_case_insensitive(self):
        lines = ["         l     r15,=v(extsub)"]
        assert "EXTSUB" in LightParser._find_go_targets(lines)

    def test_v_constant_name_uppercased(self):
        lines = ["         L     R15,=V(extsub)"]
        targets = LightParser._find_go_targets(lines)
        assert "EXTSUB" in targets
        assert "extsub" not in targets

    def test_v_constant_with_spaces_around_comma(self):
        lines = ["         L     R15 , =V(EXTSUB)"]
        assert "EXTSUB" in LightParser._find_go_targets(lines)

    def test_v_constant_not_confused_with_load(self):
        """L R1,FIELD (no =V) must not match."""
        lines = ["         L     R1,FIELD"]
        assert "FIELD" not in LightParser._find_go_targets(lines)

    def test_v_constant_and_go_in_same_block(self):
        lines = [
            "         GO    SUBA",
            "         L     R15,=V(EXTSUB)",
        ]
        targets = LightParser._find_go_targets(lines)
        assert "SUBA" in targets
        assert "EXTSUB" in targets

    def test_v_constant_deduplication(self):
        lines = [
            "         L     R15,=V(SAME)",
            "         L     R14,=V(SAME)",
        ]
        assert LightParser._find_go_targets(lines).count("SAME") == 1

    def test_v_constant_resolved_from_deps(self, tmp_path):
        """L R15,=V(SUBD) → SUBD.txt created from deps/SUBD.asm."""
        src = "PROG CSECT\n         L     R15,=V(SUBD)\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=DEPS_DIR, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert (tmp_path / "out" / "SUBD_sub.txt").exists()

    def test_v_constant_in_flow(self, tmp_path):
        src = "PROG CSECT\n         L     R15,=V(SUBD)\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=DEPS_DIR, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert "SUBD" in lp.flow["main"]

    def test_v_constant_missing_tracked(self, tmp_path):
        src = "PROG CSECT\n         L     R15,=V(GHOST)\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert "GHOST" in lp.missing

    def test_v_constant_recursive(self, tmp_path):
        """=V(name) inside a resolved subroutine is followed transitively."""
        sube_src = "SUBE     IN\n         MVI   0(13),X'01'\n         BR    14\n         OUT\n"
        (tmp_path / "SUBE.asm").write_text(sube_src)
        sub_src = "INNER    IN\n         L     R15,=V(SUBE)\n         BR    14\n         OUT\n"
        (tmp_path / "INNER.asm").write_text(sub_src)
        driver = tmp_path / "prog.asm"
        driver.write_text("PROG CSECT\n         GO    INNER\n         BR    14\n")
        lp = LightParser(driver_path=driver, deps_dir=tmp_path, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert "SUBE" in lp.chunks
        assert "SUBE" in lp.flow.get("INNER", [])

    # ── DOT / CFG output ─────────────────────────────────────────────────────

    def test_l_target_in_dot(self, tmp_path):
        src = "PROG CSECT\n         L     SUBD\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=DEPS_DIR, output_dir=tmp_path / "out")
        lp.run(1, 3)
        dot = lp.to_dot()
        assert '"SUBD"' in dot
        assert '"main" -> "SUBD"' in dot

    def test_l_target_in_mermaid(self, tmp_path):
        src = "PROG CSECT\n         L     SUBD\n         BR    14\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=DEPS_DIR, output_dir=tmp_path / "out")
        lp.run(1, 3)
        mmd = lp.to_mermaid()
        assert "main --> SUBD" in mmd


# ─────────────────────────────────────────────────────────────────────────────
# EQU * table and VTRAN dispatch-table support
# ─────────────────────────────────────────────────────────────────────────────


class TestEqStarAndVtranSupport:
    """Tests for EQU * table detection and VTRAN dispatch-entry extraction.

    Pattern being tested
    --------------------
    Main code:
        L     R15,=V(VTRANTAB)    Load address of translation table
        BALR  R14,R15

    Table definition (EQU * anchor, no IN/OUT markers):
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
                 VTRAN 05,0,TCR051,1002
        NEXTLBL  DS    0H         ← table ends here (labeled statement)

    Subroutines referenced in the table (normal IN/OUT blocks):
        TCR050   IN
                 ...
                 OUT
    """

    # ── _find_go_targets: VTRAN unit tests ───────────────────────────────────

    def test_vtran_target_extracted(self):
        lines = ["         VTRAN 05,0,TCR050,1001"]
        assert "TCR050" in LightParser._find_go_targets(lines)

    def test_vtran_with_label_in_col1(self):
        lines = ["VTRLBL   VTRAN 05,0,TCR051,1002"]
        assert "TCR051" in LightParser._find_go_targets(lines)

    def test_vtran_case_insensitive(self):
        lines = ["         vtran 05,0,tcr052,1003"]
        assert "TCR052" in LightParser._find_go_targets(lines)

    def test_vtran_name_uppercased(self):
        lines = ["         VTRAN 05,0,tcr050,1001"]
        targets = LightParser._find_go_targets(lines)
        assert "TCR050" in targets
        assert "tcr050" not in targets

    def test_vtran_multiple_entries_order_preserved(self):
        lines = [
            "         VTRAN 05,0,TCR050,1001",
            "         VTRAN 05,0,TCR051,1002",
            "         VTRAN 05,0,TCR052,1003",
        ]
        assert LightParser._find_go_targets(lines) == ["TCR050", "TCR051", "TCR052"]

    def test_vtran_deduplicated(self):
        lines = [
            "         VTRAN 05,0,TCR050,1001",
            "         VTRAN 05,0,TCR050,1002",
        ]
        assert LightParser._find_go_targets(lines).count("TCR050") == 1

    def test_vtran_mixed_with_go_and_l(self):
        lines = [
            "         GO    SUBA",
            "         VTRAN 05,0,TCR050,1001",
            "         L     R15,=V(EXTSUB)",
        ]
        targets = LightParser._find_go_targets(lines)
        assert "SUBA" in targets
        assert "TCR050" in targets
        assert "EXTSUB" in targets

    def test_vtran_comment_line_skipped(self):
        lines = ["* VTRAN 05,0,SKIPME,0000"]
        assert "SKIPME" not in LightParser._find_go_targets(lines)

    # ── _find_subroutine: EQU * detection ────────────────────────────────────

    def test_equ_star_block_found(self, tmp_path):
        src = textwrap.dedent("""\
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
                 VTRAN 05,0,TCR051,1002
        NEXTLBL  DS    0H
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        block = lp._find_subroutine("VTRANTAB")
        assert block is not None

    def test_equ_star_block_first_line_has_equ(self, tmp_path):
        src = textwrap.dedent("""\
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
        NEXTLBL  DS    0H
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        block = lp._find_subroutine("VTRANTAB")
        assert block is not None
        assert "EQU" in block[0]
        assert "VTRANTAB" in block[0]

    def test_equ_star_block_ends_at_eject(self, tmp_path):
        """EQU * table ends at EJECT; labeled statements inside are included."""
        src = textwrap.dedent("""\
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
        INRTBL   DS    0H
                 BR    14
                 EJECT
        AFTEREJ  DS    0H
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        block = lp._find_subroutine("VTRANTAB")
        assert block is not None
        assert any("INRTBL" in ln for ln in block)           # labeled line inside → included
        assert any("EJECT" in ln.upper() for ln in block)   # EJECT is the boundary
        assert not any("AFTEREJ" in ln for ln in block)      # content after EJECT → excluded

    def test_equ_star_block_contains_vtran_entries(self, tmp_path):
        src = textwrap.dedent("""\
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
                 VTRAN 05,0,TCR051,1002
        NEXTLBL  DS    0H
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        block = lp._find_subroutine("VTRANTAB")
        assert block is not None
        assert any("TCR050" in ln for ln in block)
        assert any("TCR051" in ln for ln in block)

    def test_equ_star_missing_returns_none(self, tmp_path):
        src = "VTRANTAB EQU   *\n         VTRAN 05,0,TCR050,1001\nNEXTLBL  DS    0H\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        assert lp._find_subroutine("NOSUCH") is None

    def test_in_out_preferred_over_equ_star(self, tmp_path):
        """When both NAME IN and NAME EQU * exist, IN/OUT wins."""
        src = textwrap.dedent("""\
        MYSUB    IN
                 BR    14
                 OUT
        MYSUB    EQU   *
                 VTRAN 05,0,TCR050,1001
        NEXTLBL  DS    0H
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        block = lp._find_subroutine("MYSUB")
        assert block is not None
        assert any("IN" in ln for ln in block)
        assert any("OUT" in ln for ln in block)

    def test_equ_star_block_eof_without_next_label(self, tmp_path):
        """EQU * table at EOF (no following labeled statement) is captured."""
        src = "VTRANTAB EQU   *\n         VTRAN 05,0,TCR050,1001\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        block = lp._find_subroutine("VTRANTAB")
        assert block is not None
        assert any("TCR050" in ln for ln in block)

    # ── Integration: end-to-end flow ─────────────────────────────────────────

    def test_v_constant_to_equ_star_table_resolved(self, tmp_path):
        """L R15,=V(VTRANTAB) → VTRANTAB EQU * block captured as chunk."""
        driver_src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTRANTAB)
                 BALR  R14,R15
                 BR    14
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
        NEXTLBL  DS    0H
        """)
        tcr050_src = "TCR050   IN\n         MVI   0(13),X'00'\n         BR    14\n         OUT\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(driver_src)
        (tmp_path / "TCR050.asm").write_text(tcr050_src)
        lp = LightParser(driver_path=driver, deps_dir=tmp_path, output_dir=tmp_path / "out")
        lp.run(1, 4)
        assert "VTRANTAB" in lp.chunks
        assert "VTRANTAB" in lp.flow["main"]

    def test_vtran_subs_resolved_recursively(self, tmp_path):
        """VTRAN entries inside the EQU * table are BFS-resolved."""
        driver_src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTRANTAB)
                 BALR  R14,R15
                 BR    14
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
                 VTRAN 05,0,TCR051,1002
        NEXTLBL  DS    0H
        """)
        tcr050_src = "TCR050   IN\n         MVI   0(13),X'00'\n         BR    14\n         OUT\n"
        tcr051_src = "TCR051   IN\n         MVI   0(13),X'01'\n         BR    14\n         OUT\n"
        driver = tmp_path / "prog.asm"
        driver.write_text(driver_src)
        (tmp_path / "TCR050.asm").write_text(tcr050_src)
        (tmp_path / "TCR051.asm").write_text(tcr051_src)
        lp = LightParser(driver_path=driver, deps_dir=tmp_path, output_dir=tmp_path / "out")
        lp.run(1, 4)
        assert "TCR050" in lp.chunks
        assert "TCR051" in lp.chunks
        assert "TCR050" in lp.flow.get("VTRANTAB", [])
        assert "TCR051" in lp.flow.get("VTRANTAB", [])
        assert lp.missing == []

    def test_vtran_sub_in_driver_file_resolved(self, tmp_path):
        """TCR050 IN defined in the same driver file is found directly."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTRANTAB)
                 BALR  R14,R15
                 BR    14
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
        NEXTLBL  DS    0H
        TCR050   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 4)
        assert "TCR050" in lp.chunks
        assert lp.missing == []

    def test_vtrantab_txt_file_created(self, tmp_path):
        driver_src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTRANTAB)
                 BR    14
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
        NEXTLBL  DS    0H
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(driver_src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)
        assert (tmp_path / "out" / "VTRANTAB_sub.txt").exists()

    def test_vtran_table_in_dot_output(self, tmp_path):
        driver_src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTRANTAB)
                 BR    14
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
        NEXTLBL  DS    0H
        TCR050   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(driver_src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)
        dot = lp.to_dot()
        assert '"VTRANTAB"' in dot
        assert '"TCR050"' in dot
        assert '"main" -> "VTRANTAB"' in dot
        assert '"VTRANTAB" -> "TCR050"' in dot

    def test_vtran_table_in_mermaid_output(self, tmp_path):
        driver_src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTRANTAB)
                 BR    14
        VTRANTAB EQU   *
                 VTRAN 05,0,TCR050,1001
        NEXTLBL  DS    0H
        TCR050   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        driver.write_text(driver_src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=tmp_path / "out")
        lp.run(1, 3)
        mmd = lp.to_mermaid()
        assert "main --> VTRANTAB" in mmd
        assert "VTRANTAB --> TCR050" in mmd


class TestMacroCatalogAndTagging:
    def test_macro_catalog_and_macro_chunk_written(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 NUMCHK FIELD,8,TCR051
                 BR    14
        MACRO
        NUMCHK &OPR1,&LEN,&ERROR=
                 GO    &ERROR
                 MEND
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        assert (out / "macros.json").exists()
        assert (out / "NUMCHK_macro.txt").exists()
        macros = json.loads((out / "macros.json").read_text())
        names = [m["name"] for m in macros["macros"]]
        assert "NUMCHK" in names

    def test_macro_node_tagged_in_flow_and_graphs(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 NUMCHK FIELD,8,TCR051
                 BR    14
        MACRO
        NUMCHK &OPR1,&LEN,&ERROR=
                 GO    &ERROR
                 MEND
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        assert lp.flow["main"] == ["NUMCHK"]
        assert "TCR051" in lp.flow["NUMCHK"]
        assert lp.to_json()["node_tags"]["NUMCHK"] == ["macro"]

        dot = lp.to_dot()
        assert '"NUMCHK" [style=filled fillcolor=khaki shape=component];' in dot
        mmd = lp.to_mermaid()
        assert "class NUMCHK macro;" in mmd


class TestMacroHeaderAndEquAliasResolution:
    def test_macro_name_uses_opcode_not_symbolic_label(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 ALLOW FILEA,FILEB,TCR051
                 BR    14
        MACRO
        &LABEL   ALLOW &FILE1,&FILE2,&ERR=
                 GO    &ERR
                 MEND
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        macros = json.loads((out / "macros.json").read_text())
        names = [m["name"] for m in macros["macros"]]
        assert "ALLOW" in names
        assert "&LABEL" not in names
        assert (out / "ALLOW_macro.txt").exists()
        assert not (out / "&LABEL_macro.txt").exists()

    def test_l_v_target_resolves_via_equ_alias(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VALPTR)
                 BR    14
        VALPTR   EQU   TCR051
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        assert "VALPTR" in lp.flow["main"]
        assert "TCR051" in lp.flow.get("VALPTR", [])
        assert "VALPTR" in lp.chunks
        assert "TCR051" in lp.chunks
        assert "VALPTR" not in lp.missing

    def test_equ_alias_chain_resolved(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VALA)
                 BR    14
        VALA     EQU   VALB
        VALB     EQU   TCR051
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        assert "VALA" in lp.flow["main"]
        assert "VALB" in lp.flow.get("VALA", [])
        assert "TCR051" in lp.flow.get("VALB", [])
        assert "VALA" in lp.chunks
        assert "VALB" in lp.chunks
        assert "TCR051" in lp.chunks

    def test_alias_equ_chunk_is_single_line_only(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VALPTR)
                 BR    14
        VALPTR   EQU   TCR051
                 MACRO 12,0,ROUTINE1,1223
                 EJECT
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        assert lp.chunks.get("VALPTR") == ["VALPTR   EQU   TCR051"]

    def test_inline_macro_header_form_macro_dotstar_name(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 OPEN FILE1
                 BR    14
        MACRO .* OPEN
                 GO    TCR051
                 MEND
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        macros = json.loads((out / "macros.json").read_text())
        names = [m["name"] for m in macros["macros"]]
        assert "OPEN" in names
        assert (out / "OPEN_macro.txt").exists()

    def test_a_constant_equ_block_extracts_and_resolves_nested_routine(self, tmp_path):
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R1,=A(TESTMOD)
                 BR    14
        TESTMOD  EQU   *
                 MACRO 12,0,ROUTINE1,1223
                 MACRO 12,0,ROUTINE1,1223
        NEXTLBL  DS    0H
        ROUTINE1 IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 3)

        assert "TESTMOD" in lp.flow["main"]
        assert "ROUTINE1" in lp.flow.get("TESTMOD", [])
        assert lp.flow["main"].count("TESTMOD") == 1
        assert lp.flow["TESTMOD"].count("ROUTINE1") == 1
        assert "TESTMOD" in lp.chunks
        assert "ROUTINE1" in lp.chunks


# ─────────────────────────────────────────────────────────────────────────────
# Nested flow JSON for documentation generation
# ─────────────────────────────────────────────────────────────────────────────


def _inline_lp(tmp_path, driver_src: str, deps: dict[str, str] | None = None):
    """Helper: write inline source, run LightParser over all lines, return instance."""
    driver = tmp_path / "driver.asm"
    driver.write_text(driver_src)
    deps_dir = tmp_path / "deps"
    deps_dir.mkdir()
    for fname, content in (deps or {}).items():
        (deps_dir / fname).write_text(content)
    lp = LightParser(driver_path=driver, deps_dir=deps_dir, output_dir=tmp_path / "out")
    lp.run(1, driver_src.count("\n"))
    return lp


class TestNestedFlow:
    """Tests for LightParser.to_nested_flow() and to_nested_flow_str()."""

    # ── top-level structure ───────────────────────────────────────────────────

    def test_top_level_keys_present(self, tmp_path):
        src = "PROG  CSECT\n         GO    SUBA\n         BR    14\nSUBA  IN\n         BR    14\n         OUT\n"
        lp = _inline_lp(tmp_path, src)
        nf = lp.to_nested_flow()
        assert set(nf.keys()) >= {"format", "entry", "chunks", "tree", "missing"}

    def test_format_field(self, tmp_path):
        src = "PROG  CSECT\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        assert lp.to_nested_flow()["format"] == "nested_flow_v1"

    def test_entry_is_main(self, tmp_path):
        src = "PROG  CSECT\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        assert lp.to_nested_flow()["entry"] == "main"

    def test_missing_forwarded(self, tmp_path):
        src = "PROG  CSECT\n         GO    NOSUCH\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        assert "NOSUCH" in lp.to_nested_flow()["missing"]

    # ── flat chunks dict ──────────────────────────────────────────────────────

    def test_chunks_dict_contains_main(self, tmp_path):
        src = "PROG  CSECT\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        assert "main" in lp.to_nested_flow()["chunks"]

    def test_chunks_dict_has_source_lines(self, tmp_path):
        src = "PROG  CSECT\n         GO    SUBA\n         BR    14\nSUBA  IN\n         BR    14\n         OUT\n"
        lp = _inline_lp(tmp_path, src)
        chunks = lp.to_nested_flow()["chunks"]
        assert isinstance(chunks["main"]["source_lines"], list)
        assert len(chunks["main"]["source_lines"]) > 0
        assert isinstance(chunks["SUBA"]["source_lines"], list)

    def test_chunks_dict_has_kind_and_tags(self, tmp_path):
        src = "PROG  CSECT\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        entry = lp.to_nested_flow()["chunks"]["main"]
        assert entry["kind"] in ("sub", "macro")
        assert isinstance(entry["tags"], list)

    def test_chunks_dict_has_line_count(self, tmp_path):
        src = "PROG  CSECT\n         GO    SUBA\n         BR    14\nSUBA  IN\n         BR    14\n         OUT\n"
        lp = _inline_lp(tmp_path, src)
        chunks = lp.to_nested_flow()["chunks"]
        assert chunks["main"]["line_count"] == len(lp.chunks["main"])
        assert chunks["SUBA"]["line_count"] == len(lp.chunks["SUBA"])

    # ── tree root ─────────────────────────────────────────────────────────────

    def test_tree_root_is_main(self, tmp_path):
        src = "PROG  CSECT\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        assert lp.to_nested_flow()["tree"]["name"] == "main"

    def test_tree_root_has_source_lines(self, tmp_path):
        src = "PROG  CSECT\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        assert "source_lines" in tree
        assert isinstance(tree["source_lines"], list)

    def test_tree_root_has_calls_list(self, tmp_path):
        src = "PROG  CSECT\n         BR    14\n"
        lp = _inline_lp(tmp_path, src)
        assert isinstance(lp.to_nested_flow()["tree"]["calls"], list)

    # ── child expansion ───────────────────────────────────────────────────────

    def test_child_fully_expanded_on_first_visit(self, tmp_path):
        src = "PROG  CSECT\n         GO    SUBA\n         BR    14\nSUBA  IN\n         BR    14\n         OUT\n"
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        child = next(c for c in tree["calls"] if c["name"] == "SUBA")
        assert "source_lines" in child
        assert "calls" in child
        assert child.get("ref") is not True

    def test_nested_grandchild_expanded(self, tmp_path):
        src = textwrap.dedent("""\
        PROG  CSECT
                 GO    SUBA
                 BR    14
        SUBA  IN
                 GO    SUBB
                 BR    14
                 OUT
        SUBB  IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        suba = next(c for c in tree["calls"] if c["name"] == "SUBA")
        subb = next(c for c in suba["calls"] if c["name"] == "SUBB")
        assert "source_lines" in subb
        assert subb.get("ref") is not True

    # ── ref stubs for shared callees ──────────────────────────────────────────

    def test_shared_callee_is_ref_on_second_visit(self, tmp_path):
        """SHARED is called from both SUBA and SUBB; second encounter → ref stub."""
        src = textwrap.dedent("""\
        PROG  CSECT
                 GO    SUBA
                 GO    SUBB
                 BR    14
        SUBA  IN
                 GO    SHARED
                 BR    14
                 OUT
        SUBB  IN
                 GO    SHARED
                 BR    14
                 OUT
        SHARED IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        suba = next(c for c in tree["calls"] if c["name"] == "SUBA")
        subb = next(c for c in tree["calls"] if c["name"] == "SUBB")
        shared_via_suba = next(c for c in suba["calls"] if c["name"] == "SHARED")
        shared_via_subb = next(c for c in subb["calls"] if c["name"] == "SHARED")
        # Exactly one is fully expanded; the other is a ref stub.
        fully = [shared_via_suba, shared_via_subb]
        refs   = [n for n in fully if n.get("ref") is True]
        expanded = [n for n in fully if n.get("ref") is not True]
        assert len(refs) == 1
        assert len(expanded) == 1
        assert "source_lines" in expanded[0]

    def test_ref_stub_has_no_source_lines(self, tmp_path):
        src = textwrap.dedent("""\
        PROG  CSECT
                 GO    SUBA
                 GO    SUBB
                 BR    14
        SUBA  IN
                 GO    SHARED
                 BR    14
                 OUT
        SUBB  IN
                 GO    SHARED
                 BR    14
                 OUT
        SHARED IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        suba = next(c for c in tree["calls"] if c["name"] == "SUBA")
        subb = next(c for c in tree["calls"] if c["name"] == "SUBB")
        all_shared = [
            n for calls in (suba["calls"], subb["calls"])
            for n in calls if n["name"] == "SHARED"
        ]
        stub = next(n for n in all_shared if n.get("ref") is True)
        assert "source_lines" not in stub

    # ── macro nodes ───────────────────────────────────────────────────────────

    def test_macro_node_kind_is_macro(self, tmp_path):
        src = textwrap.dedent("""\
        PROG  CSECT
                 MYMAC SUBA
                 BR    14
                 MACRO
        &LBL     MYMAC &P1
                 GO    &P1
                 MEND
        SUBA  IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        nf = lp.to_nested_flow()
        # MYMAC should appear in the chunks catalogue as a macro
        if "MYMAC" in nf["chunks"]:
            assert nf["chunks"]["MYMAC"]["kind"] == "macro"

    def test_macro_node_tag_in_tree(self, tmp_path):
        src = textwrap.dedent("""\
        PROG  CSECT
                 MYMAC SUBA
                 BR    14
                 MACRO
        &LBL     MYMAC &P1
                 GO    &P1
                 MEND
        SUBA  IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        nf = lp.to_nested_flow()
        def find_node(node, name):
            if node["name"] == name:
                return node
            for child in node.get("calls", []):
                found = find_node(child, name)
                if found:
                    return found
            return None
        macro_node = find_node(nf["tree"], "MYMAC")
        if macro_node and not macro_node.get("ref"):
            assert "macro" in macro_node.get("tags", [])

    # ── JSON serialisation ────────────────────────────────────────────────────

    def test_to_nested_flow_str_is_valid_json(self, tmp_path):
        src = "PROG  CSECT\n         GO    SUBA\n         BR    14\nSUBA  IN\n         BR    14\n         OUT\n"
        lp = _inline_lp(tmp_path, src)
        parsed = json.loads(lp.to_nested_flow_str())
        assert parsed["format"] == "nested_flow_v1"

    def test_to_nested_flow_str_round_trips(self, tmp_path):
        src = "PROG  CSECT\n         GO    SUBA\n         BR    14\nSUBA  IN\n         BR    14\n         OUT\n"
        lp = _inline_lp(tmp_path, src)
        assert lp.to_nested_flow() == json.loads(lp.to_nested_flow_str())

    # ── CLI flag ──────────────────────────────────────────────────────────────

    def test_nested_flow_cli_creates_file(self, tmp_path):
        from hlasm_parser.cli import main
        out = tmp_path / "out"
        main([
            str(DRIVER),
            "-c", str(DEPS_DIR),
            "--light-parser",
            "--start-line", str(MAIN_START),
            "--end-line", str(MAIN_END),
            "-s", str(out),
            "--nested-flow",
        ])
        assert (out / "cfg" / "nested_flow.json").exists()

    def test_nested_flow_cli_file_is_valid_json(self, tmp_path):
        from hlasm_parser.cli import main
        out = tmp_path / "out"
        main([
            str(DRIVER),
            "-c", str(DEPS_DIR),
            "--light-parser",
            "--start-line", str(MAIN_START),
            "--end-line", str(MAIN_END),
            "-s", str(out),
            "--nested-flow",
        ])
        content = (out / "cfg" / "nested_flow.json").read_text()
        parsed = json.loads(content)
        assert parsed["format"] == "nested_flow_v1"
        assert "tree" in parsed
        assert "chunks" in parsed

    def test_nested_flow_not_written_without_flag(self, tmp_path):
        from hlasm_parser.cli import main
        out = tmp_path / "out"
        main([
            str(DRIVER),
            "-c", str(DEPS_DIR),
            "--light-parser",
            "--start-line", str(MAIN_START),
            "--end-line", str(MAIN_END),
            "-s", str(out),
        ])
        assert not (out / "cfg" / "nested_flow.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
# Call-order preservation and seq field
# ─────────────────────────────────────────────────────────────────────────────


class TestCallOrderAndSeq:
    """Verify that flow preserves source order and nested_flow exposes seq."""

    # ── source order in self.flow ─────────────────────────────────────────────

    def test_go_before_macro_order_preserved(self, tmp_path):
        """GO call on line 2, macro call on line 3 → GO target first in flow."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    SUBA
                 MYMAC TCR051
                 BR    14
        MACRO
        MYMAC &P1
                 GO    &P1
                 MEND
        SUBA     IN
                 BR    14
                 OUT
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 4)
        # SUBA (GO on line 2) must come before MYMAC (macro on line 3)
        assert lp.flow["main"].index("SUBA") < lp.flow["main"].index("MYMAC")

    def test_macro_before_go_order_preserved(self, tmp_path):
        """Macro call on line 2, GO call on line 3 → macro first in flow."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 MYMAC TCR051
                 GO    SUBA
                 BR    14
        MACRO
        MYMAC &P1
                 GO    &P1
                 MEND
        SUBA     IN
                 BR    14
                 OUT
        TCR051   IN
                 BR    14
                 OUT
        """)
        driver = tmp_path / "prog.asm"
        out = tmp_path / "out"
        driver.write_text(src)
        lp = LightParser(driver_path=driver, deps_dir=None, output_dir=out)
        lp.run(1, 4)
        # MYMAC (macro on line 2) must come before SUBA (GO on line 3)
        assert lp.flow["main"].index("MYMAC") < lp.flow["main"].index("SUBA")

    def test_multiple_go_calls_order_preserved(self, tmp_path):
        """Three sequential GO calls appear in source order in flow."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    FIRST
                 GO    SECOND
                 GO    THIRD
                 BR    14
        FIRST    IN
                 BR    14
                 OUT
        SECOND   IN
                 BR    14
                 OUT
        THIRD    IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        order = lp.flow["main"]
        assert order.index("FIRST") < order.index("SECOND") < order.index("THIRD")

    def test_l_v_target_comes_before_go_if_first_in_source(self, tmp_path):
        """L Rx,=V(NAME) on line 2, GO on line 3 → L target precedes GO target."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTAB)
                 GO    SUBA
                 BR    14
        VTAB     EQU   *
                 MACRO 05,0,TCR050,1001
                 EJECT
        SUBA     IN
                 BR    14
                 OUT
        TCR050   IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        order = lp.flow["main"]
        assert "VTAB" in order
        assert "SUBA" in order
        assert order.index("VTAB") < order.index("SUBA")

    # ── L targets visible in nested flow tree ────────────────────────────────

    def test_l_v_target_appears_in_nested_flow_tree(self, tmp_path):
        """L Rx,=V(NAME) target must show up as a call node in the tree."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(VTAB)
                 BR    14
        VTAB     EQU   *
                 05,0,TCR050,1001
                 EJECT
        TCR050   IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        call_names = [c["name"] for c in tree["calls"]]
        assert "VTAB" in call_names

    def test_plain_l_target_appears_in_nested_flow_tree(self, tmp_path):
        """Plain L <name> target must show up as a call node in the tree."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     MYSUB
                 BR    14
        MYSUB    IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        call_names = [c["name"] for c in tree["calls"]]
        assert "MYSUB" in call_names

    def test_l_target_has_source_lines_in_nested_flow(self, tmp_path):
        """L-resolved sub should have source_lines in its nested flow node."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 L     R15,=V(MYSUB)
                 BR    14
        MYSUB    IN
                 MVI   RESULT,C'Y'
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        mysub_node = next(c for c in tree["calls"] if c["name"] == "MYSUB")
        assert mysub_node.get("ref") is not True
        assert len(mysub_node.get("source_lines", [])) > 0

    # ── seq field ─────────────────────────────────────────────────────────────

    def test_seq_field_present_on_call_nodes(self, tmp_path):
        """Every node in the calls list must have a seq field."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    SUBA
                 GO    SUBB
                 BR    14
        SUBA     IN
                 BR    14
                 OUT
        SUBB     IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        for child in tree["calls"]:
            assert "seq" in child, f"Missing seq on node {child['name']}"

    def test_seq_values_are_one_indexed_and_sequential(self, tmp_path):
        """seq must be 1, 2, 3… matching the calls list position."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    FIRST
                 GO    SECOND
                 GO    THIRD
                 BR    14
        FIRST    IN
                 BR    14
                 OUT
        SECOND   IN
                 BR    14
                 OUT
        THIRD    IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        for i, child in enumerate(tree["calls"], start=1):
            assert child["seq"] == i

    def test_seq_matches_source_call_order(self, tmp_path):
        """seq=1 is the first routine called in source, seq=2 the second, etc."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    ALPHA
                 GO    BETA
                 BR    14
        ALPHA    IN
                 BR    14
                 OUT
        BETA     IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        alpha = next(c for c in tree["calls"] if c["name"] == "ALPHA")
        beta = next(c for c in tree["calls"] if c["name"] == "BETA")
        assert alpha["seq"] == 1
        assert beta["seq"] == 2

    def test_seq_on_ref_stub(self, tmp_path):
        """ref stubs (shared callees) also carry a seq field."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    SUBA
                 GO    SUBB
                 BR    14
        SUBA     IN
                 GO    SHARED
                 BR    14
                 OUT
        SUBB     IN
                 GO    SHARED
                 BR    14
                 OUT
        SHARED   IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        suba = next(c for c in tree["calls"] if c["name"] == "SUBA")
        subb = next(c for c in tree["calls"] if c["name"] == "SUBB")
        all_shared = [
            n for calls in (suba["calls"], subb["calls"])
            for n in calls if n["name"] == "SHARED"
        ]
        # Both occurrences of SHARED must have seq (one full, one ref stub)
        for node in all_shared:
            assert "seq" in node

    def test_seq_on_deeply_nested_grandchild(self, tmp_path):
        """seq is present on grandchild nodes too."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    SUBA
                 BR    14
        SUBA     IN
                 GO    SUBB
                 BR    14
                 OUT
        SUBB     IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        suba = next(c for c in tree["calls"] if c["name"] == "SUBA")
        subb = next(c for c in suba["calls"] if c["name"] == "SUBB")
        assert subb["seq"] == 1  # SUBB is the only (first) call inside SUBA


# ─────────────────────────────────────────────────────────────────────────────
# COPY directive, CSECT block, and copybook-file resolution
# ─────────────────────────────────────────────────────────────────────────────


class TestCopyAndCsectResolution:
    """COPY directive, CSECT block, and copybook file fallback strategies."""

    # ── COPY directive ────────────────────────────────────────────────────────

    def test_copy_directive_adds_copybook_to_flow(self, tmp_path):
        """COPY MYBOOK in main → MYBOOK appears as a child in flow["main"]."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        lp = _inline_lp(tmp_path, src)
        assert "MYBOOK" in lp.flow["main"]

    def test_copy_before_go_order_preserved(self, tmp_path):
        """COPY on line 2, GO on line 3 → MYBOOK precedes SUBA in flow."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 GO    SUBA
                 BR    14
        SUBA     IN
                 BR    14
                 OUT
        """)
        lp = _inline_lp(tmp_path, src)
        order = lp.flow["main"]
        assert "MYBOOK" in order
        assert "SUBA" in order
        assert order.index("MYBOOK") < order.index("SUBA")

    def test_copy_resolved_from_deps_file(self, tmp_path):
        """COPY MYBOOK → file deps/MYBOOK.cpy is found and captured as a chunk."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"MYBOOK.cpy": "* copybook content\n         DS    CL80\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        assert "MYBOOK" in lp.chunks
        assert "MYBOOK" not in lp.missing

    def test_copy_resolved_case_insensitive_filename(self, tmp_path):
        """Copybook file matching is case-insensitive on the stem."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"mybook.asm": "* lowercase file\n         DS    CL40\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        assert "MYBOOK" in lp.chunks
        assert "MYBOOK" not in lp.missing

    def test_copy_chunk_kind_is_copybook(self, tmp_path):
        """Resolved COPY targets get kind='copybook'."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"MYBOOK.cpy": "         DS    CL10\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        assert lp.chunk_kinds.get("MYBOOK") == "copybook"

    def test_copy_node_tagged_copybook(self, tmp_path):
        """Resolved COPY target has node_tags=['copybook']."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"MYBOOK.cpy": "         DS    CL10\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        assert lp.node_tags.get("MYBOOK") == ["copybook"]

    def test_copy_missing_when_no_file(self, tmp_path):
        """COPY UNKNOWN with no matching file → UNKNOWN in missing list."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  UNKNOWN
                 BR    14
        """)
        lp = _inline_lp(tmp_path, src)
        assert "UNKNOWN" in lp.missing

    def test_copybook_appears_in_nested_flow_tree(self, tmp_path):
        """Resolved COPY target appears in the nested flow tree."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"MYBOOK.cpy": "         DS    CL10\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        tree = lp.to_nested_flow()["tree"]
        names = [c["name"] for c in tree["calls"]]
        assert "MYBOOK" in names

    def test_copybook_kind_in_nested_flow_chunks(self, tmp_path):
        """Copybook kind 'copybook' is reflected in nested_flow chunks dict."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"MYBOOK.cpy": "         DS    CL10\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        chunks = lp.to_nested_flow()["chunks"]
        assert chunks["MYBOOK"]["kind"] == "copybook"

    def test_copybook_dot_coloured_lightgreen(self, tmp_path):
        """Copybook nodes are coloured lightgreen in DOT output."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"MYBOOK.cpy": "         DS    CL10\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        dot = lp.to_dot()
        assert "lightgreen" in dot

    def test_copybook_mermaid_has_classDef(self, tmp_path):
        """Mermaid output includes a copybook classDef when copybooks present."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 COPY  MYBOOK
                 BR    14
        """)
        deps = {"MYBOOK.cpy": "         DS    CL10\n"}
        lp = _inline_lp(tmp_path, src, deps=deps)
        mmd = lp.to_mermaid()
        assert "classDef copybook" in mmd
        assert "class MYBOOK copybook;" in mmd

    # ── CSECT block resolution ────────────────────────────────────────────────

    def test_csect_block_resolved_as_fallback(self, tmp_path):
        """<name> CSECT is found when no IN/OUT block exists for that name."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 MVI   FLAG,C'Y'
                 BR    14
                 DS    0F
        """)
        lp = _inline_lp(tmp_path, src)
        assert "MYSUB" in lp.chunks
        assert "MYSUB" not in lp.missing

    def test_csect_block_ends_at_ds_0f(self, tmp_path):
        """CSECT block stops at (and includes) DS 0F."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 MVI   FLAG,C'Y'
                 DS    0F
        NEXTLBL  DS    CL10
        """)
        lp = _inline_lp(tmp_path, src)
        chunk = lp.chunks.get("MYSUB", [])
        # DS 0F line is included
        assert any("DS" in ln and "0F" in ln for ln in chunk)
        # NEXTLBL line is NOT included
        assert not any("NEXTLBL" in ln for ln in chunk)

    def test_csect_block_ends_at_eject(self, tmp_path):
        """CSECT block stops before an EJECT directive."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 MVI   FLAG,C'Y'
                 EJECT
        AFTER    DS    CL10
        """)
        lp = _inline_lp(tmp_path, src)
        chunk = lp.chunks.get("MYSUB", [])
        assert not any("AFTER" in ln for ln in chunk)
        assert not any("EJECT" in ln for ln in chunk)

    def test_csect_block_stops_before_next_csect(self, tmp_path):
        """CSECT block does not bleed into the next CSECT definition."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 MVI   FLAG,C'Y'
                 BR    14
        OTHER    CSECT
                 MVI   FLAG2,C'N'
                 BR    14
        """)
        lp = _inline_lp(tmp_path, src)
        chunk = lp.chunks.get("MYSUB", [])
        assert not any("OTHER" in ln for ln in chunk)
        assert not any("FLAG2" in ln for ln in chunk)

    def test_csect_chunk_kind_is_csect(self, tmp_path):
        """CSECT-resolved targets get kind='csect'."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 BR    14
                 DS    0F
        """)
        lp = _inline_lp(tmp_path, src)
        assert lp.chunk_kinds.get("MYSUB") == "csect"

    def test_csect_node_tagged_csect(self, tmp_path):
        """CSECT-resolved targets have node_tags=['csect']."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 BR    14
                 DS    0F
        """)
        lp = _inline_lp(tmp_path, src)
        assert lp.node_tags.get("MYSUB") == ["csect"]

    def test_csect_appears_in_nested_flow_tree(self, tmp_path):
        """CSECT-resolved target appears in the nested flow tree."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 BR    14
                 DS    0F
        """)
        lp = _inline_lp(tmp_path, src)
        tree = lp.to_nested_flow()["tree"]
        names = [c["name"] for c in tree["calls"]]
        assert "MYSUB" in names

    def test_csect_dot_coloured_lightyellow(self, tmp_path):
        """CSECT nodes are coloured lightyellow in DOT output."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 BR    14
                 DS    0F
        """)
        lp = _inline_lp(tmp_path, src)
        dot = lp.to_dot()
        assert "lightyellow" in dot

    def test_csect_mermaid_has_classDef(self, tmp_path):
        """Mermaid output includes a csect classDef when CSECT nodes present."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    CSECT
                 BR    14
                 DS    0F
        """)
        lp = _inline_lp(tmp_path, src)
        mmd = lp.to_mermaid()
        assert "classDef csect" in mmd
        assert "class MYSUB csect;" in mmd

    def test_in_out_takes_priority_over_csect(self, tmp_path):
        """IN/OUT block wins over CSECT when both match the same name."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYSUB
                 BR    14
        MYSUB    IN
                 MVI   FLAG,C'Y'
                 OUT
        MYSUB    CSECT
                 MVI   FLAG,C'Z'
                 DS    0F
        """)
        lp = _inline_lp(tmp_path, src)
        chunk = lp.chunks.get("MYSUB", [])
        # Must have taken the IN/OUT version (contains 'Y' not 'Z')
        assert any("C'Y'" in ln for ln in chunk)
        assert not any("C'Z'" in ln for ln in chunk)
        assert lp.chunk_kinds.get("MYSUB") == "sub"

    def test_csect_in_deps_file_resolved(self, tmp_path):
        """CSECT block defined in a deps file is found and captured."""
        src = textwrap.dedent("""\
        PROG     CSECT
                 GO    MYMOD
                 BR    14
        """)
        deps = {
            "mymod.asm": textwrap.dedent("""\
            MYMOD    CSECT
                     MVI   X,C'A'
                     BR    14
                     DS    0F
            """),
        }
        lp = _inline_lp(tmp_path, src, deps=deps)
        assert "MYMOD" in lp.chunks
        assert "MYMOD" not in lp.missing
        assert lp.chunk_kinds.get("MYMOD") == "csect"
