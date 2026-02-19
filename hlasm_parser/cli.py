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
--verbose, -v         Enable DEBUG logging.

Examples
--------
::

    python -m hlasm_parser.cli program.asm --copybook-path ./macros
    python -m hlasm_parser.cli program.asm -c ./macros -f text
    python -m hlasm_parser.cli program.asm -c ./macros -r -o result.json
"""
from __future__ import annotations

import argparse
import json
import logging
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
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    return p


def _format_text(data: object) -> str:
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

    if isinstance(data, dict):
        for path, chunk_list in data.items():
            lines.append(f"\n{'═'*60}\n  File: {path}\n{'═'*60}")
            _render_chunks(chunk_list)
    else:
        _render_chunks(data)  # type: ignore[arg-type]

    return "\n".join(lines)


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

    if args.recursive:
        results = analysis.analyze_with_dependencies(args.source)
        output_data: object = {
            path: [c.to_dict() for c in chunks]
            for path, chunks in results.items()
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


if __name__ == "__main__":
    sys.exit(main())
