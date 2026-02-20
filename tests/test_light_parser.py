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
        assert (tmp_path / "main.txt").exists()

    def test_main_chunk_stored(self, lp):
        assert "main" in lp.chunks
        assert len(lp.chunks["main"]) == MAIN_END - MAIN_START + 1

    def test_external_suba_resolved(self, lp, tmp_path):
        assert (tmp_path / "SUBA.txt").exists()

    def test_external_subb_resolved(self, lp, tmp_path):
        assert (tmp_path / "SUBB.txt").exists()

    def test_inline_inlsub_resolved(self, lp, tmp_path):
        assert (tmp_path / "INLSUB.txt").exists()

    def test_nested_subc_resolved(self, lp, tmp_path):
        """SUBC is called by SUBA – must be resolved transitively."""
        assert (tmp_path / "SUBC.txt").exists()

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
        content = (tmp_path / "SUBA.txt").read_text()
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
        assert (out / "main.txt").exists()
        assert (out / "SUBA.txt").exists()
        assert (out / "flow.json").exists()
        assert (out / "cfg.dot").exists()

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
        assert (out / "cfg.mmd").exists()
        content = (out / "cfg.mmd").read_text()
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
        assert (tmp_path / "out" / "SUBD.txt").exists()

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
