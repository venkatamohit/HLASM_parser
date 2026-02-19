"""
export_cfg.py
=============

Generate Control Flow Graph files for one or more HLASM driver programs.

For each driver program the script produces three files under
``outputs/cfg/<driver-stem>/``:

* ``cfg.dot``    – Graphviz DOT source (render with ``dot -Tsvg -o cfg.svg cfg.dot``)
* ``cfg.json``   – Machine-readable graph (nodes + edges with colour codes)
* ``cfg.mmd``    – Mermaid flowchart (paste into a GitHub Markdown fenced block)

Color coding
~~~~~~~~~~~~
* **Blue  (driver)**   – The root / entry-point program.
* **Green (present)**  – Dependency whose source file was found and analysed.
* **Red   (missing)**  – Dependency referenced but whose file was not found.

Usage
-----
    python scripts/export_cfg.py \\
        --sources tests/fixtures/programs/PAYROLL.asm \\
                  tests/fixtures/programs/EXTPROG1.asm \\
        --external-path tests/fixtures/programs \\
        --copybook-path tests/fixtures/macros \\
        --output-dir outputs/cfg

Render to SVG (requires Graphviz installed)
-------------------------------------------
    dot -Tsvg outputs/cfg/PAYROLL/cfg.dot -o outputs/cfg/PAYROLL/cfg.svg
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hlasm_parser.output.cfg_builder import CFGBuilder
from hlasm_parser.pipeline.hlasm_analysis import HlasmAnalysis


def _try_render_svg(dot_path: Path) -> None:
    """Try to render the DOT file to SVG via Graphviz if available."""
    try:
        svg_path = dot_path.with_suffix(".svg")
        subprocess.run(
            ["dot", "-Tsvg", str(dot_path), "-o", str(svg_path)],
            check=True,
            capture_output=True,
        )
        print(f"    rendered {svg_path}")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass  # Graphviz not installed – silently skip


def export_one(
    driver: str,
    copybook_path: str,
    external_path: str,
    output_dir: Path,
    render_svg: bool,
) -> None:
    driver_stem = Path(driver).stem.upper()
    dest = output_dir / driver_stem
    dest.mkdir(parents=True, exist_ok=True)

    # Run analysis
    analysis = HlasmAnalysis(
        copybook_path=copybook_path,
        external_path=external_path,
    )
    results = analysis.analyze_with_dependencies(driver)

    present = list(results.keys())
    all_deps: set[str] = set()
    for chunks in results.values():
        for chunk in chunks:
            all_deps.update(chunk.dependencies)

    # Build graph
    builder = CFGBuilder()
    graph = builder.build(results, driver)

    # --- Summary ---
    n_present = sum(1 for n in graph.nodes if n.status == "present")
    n_missing = sum(1 for n in graph.nodes if n.status == "missing")
    print(f"  driver  : {driver_stem}")
    print(f"  present : {n_present}  missing: {n_missing}  edges: {len(graph.edges)}")

    # --- Write DOT ---
    dot_path = dest / "cfg.dot"
    dot_path.write_text(
        builder.to_dot(graph, title=f"{driver_stem} – Control Flow Graph"),
        encoding="utf-8",
    )
    print(f"  wrote   : {dot_path}")
    if render_svg:
        _try_render_svg(dot_path)

    # --- Write JSON ---
    json_path = dest / "cfg.json"
    json_path.write_text(builder.to_json_str(graph), encoding="utf-8")
    print(f"  wrote   : {json_path}")

    # --- Write Mermaid ---
    mmd_path = dest / "cfg.mmd"
    mmd_path.write_text(
        builder.to_mermaid(graph, title=f"{driver_stem} Control Flow Graph"),
        encoding="utf-8",
    )
    print(f"  wrote   : {mmd_path}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Export HLASM Control Flow Graphs (DOT / JSON / Mermaid)"
    )
    p.add_argument("--sources", "-s", nargs="+", required=True, metavar="FILE",
                   help="Driver HLASM source file(s)")
    p.add_argument("--copybook-path", "-c", default="", metavar="DIR")
    p.add_argument("--external-path", "-e", default="", metavar="DIR")
    p.add_argument("--output-dir", "-o", default="outputs/cfg", metavar="DIR")
    p.add_argument("--render-svg", action="store_true",
                   help="Attempt to auto-render DOT → SVG via Graphviz")
    args = p.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for src in args.sources:
        print(f"\n=== {src} ===")
        export_one(
            driver=src,
            copybook_path=args.copybook_path,
            external_path=args.external_path,
            output_dir=out,
            render_svg=args.render_svg,
        )


if __name__ == "__main__":
    main()
