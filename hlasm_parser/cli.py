"""
HLASM Parser – command-line interface
======================================

Usage
-----
::

    python -m hlasm_parser.cli SOURCE [OPTIONS]

Options
-------
--copybook-path, -c   Directory containing macro copybook files.
--external-path, -e   Directory for resolving external CALL targets.
--output, -o          Output file path (default: stdout).
--format, -f          Output format: ``json`` (default) or ``text``.
--recursive, -r       Follow and analyse dependency files.
--split-output, -s    Write one .asm file per chunk into a folder.
--missing-deps-log    Write unresolved-dependency report to a JSON file.
--cfg                 Emit a Control Flow Graph instead of chunk output.
--cfg-format          CFG format: dot (default), json, or mermaid.
--light-parser        Lightweight line-range + GO/IN/OUT extraction mode.
--start-line N        First line of the main block (used with --light-parser).
--end-line N          Last line of the main block (used with --light-parser).
--verbose, -v         Enable DEBUG logging.

Examples
--------
::

    python -m hlasm_parser.cli program.asm --copybook-path ./macros
    python -m hlasm_parser.cli program.asm -c ./macros -f text
    python -m hlasm_parser.cli program.asm -c ./macros -r -o result.json
    python -m hlasm_parser.cli program.asm -e ./pgms -r --missing-deps-log missing.json
    python -m hlasm_parser.cli program.asm -c ./macros -e ./pgms -s ./my_chunks
    python -m hlasm_parser.cli driver.asm -c ./deps --light-parser --start-line 10 --end-line 50 -s ./chunks
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from .pipeline.hlasm_analysis import HlasmAnalysis


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hlasm_parser",
        description="HLASM Parser – parse HLASM source and extract chunks",
    )
    p.add_argument("source", help="HLASM source file to parse")
    p.add_argument(
        "--copybook-path", "-c",
        default="",
        metavar="DIR",
        help="Directory containing macro copybook files",
    )
    p.add_argument(
        "--external-path", "-e",
        default="",
        metavar="DIR",
        help="Directory for resolving external program references",
    )
    p.add_argument(
        "--output", "-o",
        default="-",
        metavar="FILE",
        help="Output file (default: stdout)",
    )
    p.add_argument(
        "--format", "-f",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    p.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Recursively resolve and analyse dependency files",
    )
    p.add_argument(
        "--missing-deps-log",
        default="",
        metavar="FILE",
        help=(
            "Write unresolved dependency details to FILE as JSON. "
            "Chunk creation continues for all found files regardless of this flag; "
            "missing dependencies are always shown in the output."
        ),
    )
    p.add_argument(
        "--cfg",
        action="store_true",
        help=(
            "Generate a Control Flow Graph instead of chunk output. "
            "Implies --recursive.  Use --cfg-format to choose the output format."
        ),
    )
    p.add_argument(
        "--cfg-format",
        choices=["dot", "json", "mermaid"],
        default="dot",
        metavar="FMT",
        help="CFG output format when --cfg is set: dot (default), json, or mermaid",
    )
    p.add_argument(
        "--split-output", "-s",
        default="",
        metavar="DIR",
        help=(
            "Write one .asm file per chunk into DIR/<source-stem>/<label>.asm "
            "instead of producing a single combined output file."
        ),
    )
    p.add_argument(
        "--light-parser",
        action="store_true",
        help=(
            "Enable lightweight line-range extraction mode.  Requires "
            "--start-line, --end-line, and --split-output (output directory).  "
            "Uses --copybook-path as the dependencies search directory."
        ),
    )
    p.add_argument(
        "--start-line",
        type=int,
        default=0,
        metavar="N",
        help="First line of the main block to extract (1-indexed, inclusive). "
             "Used with --light-parser.",
    )
    p.add_argument(
        "--end-line",
        type=int,
        default=0,
        metavar="N",
        help="Last line of the main block to extract (1-indexed, inclusive). "
             "Used with --light-parser.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    return p


def _format_text(data: object, missing_deps: list[dict] | None = None) -> str:
    lines: list[str] = []

    def _render_chunks(chunk_list: list[dict]) -> None:
        for c in chunk_list:
            lines.append(
                f"\n{'─'*60}\n"
                f"  Label : {c['label']}\n"
                f"  Type  : {c['chunk_type']}\n"
                f"  File  : {c['source_file']}\n"
                f"  Instrs: {c['instruction_count']}\n"
                f"  Deps  : {', '.join(c['dependencies']) or '(none)'}"
            )
            for instr in c["instructions"]:
                op = instr["opcode"] or ""
                operands = ", ".join(instr["operands"])
                lines.append(f"    {op:<8} {operands}")

    # Render chunk sections (files dict or flat list)
    if isinstance(data, dict):
        files = data.get("files", data)  # support both wrapped and legacy format
        for path, chunk_list in files.items():
            lines.append(f"\n{'═'*60}\n  File: {path}\n{'═'*60}")
            _render_chunks(chunk_list)
    else:
        _render_chunks(data)  # type: ignore[arg-type]

    # Missing dependency section (always shown when present)
    deps = missing_deps or (data.get("missing_dependencies") if isinstance(data, dict) else None) or []
    if deps:
        lines.append(f"\n{'═'*60}")
        lines.append(f"  MISSING DEPENDENCIES ({len(deps)} unresolved)")
        lines.append(f"{'═'*60}")
        lines.append(f"  {'SYMBOL':<20}  {'CHUNK':<20}  SOURCE FILE")
        lines.append(f"  {'─'*20}  {'─'*20}  {'─'*30}")
        for d in deps:
            fname = Path(d["referenced_from_file"]).name
            lines.append(
                f"  {d['dep_name']:<20}  {d['referenced_in_chunk']:<20}  {fname}"
            )
        lines.append(
            f"\n  Chunks for all FOUND files were created normally."
            f"\n  The symbols above could not be resolved"
            + (f" in: {deps[0]['search_path']}" if deps[0]["search_path"] else ".")
        )

    return "\n".join(lines)


def _safe_filename(label: str, fallback: str = "ROOT") -> str:
    """Convert an arbitrary HLASM label into a safe filename stem.

    - Keeps ASCII letters, digits, hyphens, and dots.
    - Replaces every other character (spaces, $, #, @, (, ), /, \\, …) with ``_``.
    - Collapses runs of ``_`` into one and strips leading/trailing ``_``.
    - Falls back to *fallback* when the result would be empty.
    """
    safe = re.sub(r"[^A-Za-z0-9\-.]", "_", label)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe or fallback


def _write_split_output(results: dict, output_dir: Path) -> None:
    """Write one .asm file per chunk into output_dir/<source-stem>/<label>.asm."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_path, chunks in results.items():
        stem = _safe_filename(Path(file_path).stem, fallback="PROGRAM")
        dest = output_dir / stem
        dest.mkdir(parents=True, exist_ok=True)
        seen: dict[str, int] = {}
        for chunk in chunks:
            base = _safe_filename(chunk.label, fallback="ROOT")
            # Disambiguate collisions that arise after sanitisation
            if base in seen:
                seen[base] += 1
                safe_label = f"{base}_{seen[base]}"
            else:
                seen[base] = 0
                safe_label = base
            out_file = dest / f"{safe_label}.asm"
            lines = [
                instr.raw_text
                for instr in chunk.instructions
                if instr.raw_text and instr.raw_text.strip()
            ]
            header = (
                f"* CHUNK : {chunk.label}\n"
                f"* TYPE  : {chunk.chunk_type}\n"
                f"* SOURCE: {file_path}\n"
                f"* DEPS  : {', '.join(chunk.dependencies) or '(none)'}\n"
                f"*{'─' * 66}\n"
            )
            out_file.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
            print(f"  wrote {out_file}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    analysis = HlasmAnalysis(
        copybook_path=args.copybook_path,
        external_path=args.external_path,
    )

    # ------------------------------------------------------------------
    # CFG mode
    # ------------------------------------------------------------------
    if args.cfg:
        from .output.cfg_builder import CFGBuilder
        results = analysis.analyze_with_dependencies(args.source)
        _report_missing(analysis, args.missing_deps_log)
        builder = CFGBuilder()
        graph = builder.build(results, args.source)
        fmt = args.cfg_format
        if fmt == "dot":
            output_text = builder.to_dot(graph)
        elif fmt == "mermaid":
            output_text = builder.to_mermaid(graph)
        else:
            output_text = builder.to_json_str(graph)

        if args.output == "-":
            print(output_text)
        else:
            Path(args.output).write_text(output_text, encoding="utf-8")
            print(f"CFG written to {args.output}", file=sys.stderr)
        return 0

    # ------------------------------------------------------------------
    # Light-parser mode
    # ------------------------------------------------------------------
    if args.light_parser:
        from .pipeline.light_parser import LightParser

        errors: list[str] = []
        if not args.start_line:
            errors.append("--start-line is required with --light-parser")
        if not args.end_line:
            errors.append("--end-line is required with --light-parser")
        if not args.split_output:
            errors.append("--split-output DIR is required with --light-parser")
        if errors:
            for e in errors:
                print(f"error: {e}", file=sys.stderr)
            return 2

        base = Path(args.split_output)
        chunks_dir = base / "chunks"
        cfg_dir = base / "cfg"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        lp = LightParser(
            driver_path=args.source,
            deps_dir=args.copybook_path or None,
            output_dir=chunks_dir,
        )
        lp.run(args.start_line, args.end_line)

        # Always write JSON flow into cfg/
        flow_file = cfg_dir / "flow.json"
        flow_file.write_text(lp.to_json_str(), encoding="utf-8")
        print(f"  flow  → {flow_file}", file=sys.stderr)

        # Write CFG in the requested format (default dot) into cfg/
        fmt = args.cfg_format
        if fmt == "mermaid":
            cfg_text = lp.to_mermaid()
            cfg_suffix = ".mmd"
        elif fmt == "json":
            cfg_text = lp.to_json_str()
            cfg_suffix = "_cfg.json"
        else:
            cfg_text = lp.to_dot()
            cfg_suffix = ".dot"
        cfg_file = cfg_dir / f"cfg{cfg_suffix}"
        cfg_file.write_text(cfg_text, encoding="utf-8")
        print(f"  cfg   → {cfg_file}", file=sys.stderr)

        if lp.missing:
            print(
                f"\nWARNING: {len(lp.missing)} unresolved target(s): "
                + ", ".join(lp.missing),
                file=sys.stderr,
            )
        return 0

    # ------------------------------------------------------------------
    # Normal chunk-analysis mode
    # ------------------------------------------------------------------
    missing_deps_dicts: list[dict] = []

    if args.recursive or args.split_output:
        results = analysis.analyze_with_dependencies(args.source)
        missing_deps_dicts = [m.to_dict() for m in analysis.missing_deps]
        _report_missing(analysis, args.missing_deps_log)

        # --split-output: one .asm file per chunk, skip single-file output
        if args.split_output:
            _write_split_output(results, Path(args.split_output))
            return 0

        output_data: object = {
            "files": {
                path: [c.to_dict() for c in chunks]
                for path, chunks in results.items()
            },
            "missing_dependencies": missing_deps_dicts,
        }
    else:
        chunks = analysis.analyze_file(args.source)
        output_data = [c.to_dict() for c in chunks]

    if args.format == "json":
        output_text = json.dumps(output_data, indent=2)
    else:
        output_text = _format_text(output_data)

    if args.output == "-":
        print(output_text)
    else:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Output written to {args.output}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# Helper: report missing deps to stderr + optional log file
# ---------------------------------------------------------------------------

def _report_missing(analysis: HlasmAnalysis, log_file: str) -> None:
    """Print missing-dep summary to stderr and optionally write a JSON log."""
    missing = analysis.missing_deps
    if not missing:
        return

    print(
        f"\nWARNING: {len(missing)} unresolved dependenc"
        f"{'y' if len(missing) == 1 else 'ies'} (chunks created for all found files):",
        file=sys.stderr,
    )
    for m in missing:
        print(f"  [MISSING] {m}", file=sys.stderr)

    if log_file:
        log_data = {
            "unresolved_count": len(missing),
            "missing_dependencies": [m.to_dict() for m in missing],
        }
        Path(log_file).write_text(json.dumps(log_data, indent=2), encoding="utf-8")
        print(f"  Missing-dep log written to: {log_file}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
