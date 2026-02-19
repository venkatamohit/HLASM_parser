"""
export_chunks.py
================
Run the HLASM parser on one or more source files and write the **expanded
source text** for every chunk to individual ``.asm`` files under
``outputs/expanded/<source-stem>/``.

Each output file contains only the raw (macro-expanded, continuation-merged)
assembler lines for that chunk — exactly what you would paste into an LLM for
documentation.

Usage
-----
    python scripts/export_chunks.py \\
        --sources tests/fixtures/programs/PAYROLL.asm \\
                  tests/fixtures/programs/TAXCALC \\
        --copybook-path tests/fixtures/macros \\
        --external-path tests/fixtures/programs \\
        --recursive \\
        --output-dir outputs/expanded
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hlasm_parser.pipeline.extract_blocks import ExtractBlocksTask
from hlasm_parser.chunker.chunker import Chunker
from hlasm_parser.pipeline.hlasm_analysis import HlasmAnalysis


def _safe_stem(path: str) -> str:
    """Return a filesystem-safe stem for a source file path."""
    return Path(path).stem


def _chunk_to_source(chunk) -> str:
    """Return the expanded source lines for a chunk as a plain string."""
    lines = []
    for instr in chunk.instructions:
        line = instr.raw_text
        if line and line.strip():
            lines.append(line)
    return "\n".join(lines)


def export(
    source: str,
    copybook_path: str,
    external_path: str,
    recursive: bool,
    output_dir: Path,
) -> None:
    analysis = HlasmAnalysis(
        copybook_path=copybook_path,
        external_path=external_path,
    )

    if recursive:
        results = analysis.analyze_with_dependencies(source)
    else:
        results = {source: analysis.analyze_file(source)}

    for file_path, chunks in results.items():
        stem = _safe_stem(file_path)
        dest = output_dir / stem
        dest.mkdir(parents=True, exist_ok=True)

        for chunk in chunks:
            # Sanitise the label for use as a filename
            safe_label = chunk.label.replace("/", "_").replace("\\", "_") or "ROOT"
            out_file = dest / f"{safe_label}.asm"
            source_text = _chunk_to_source(chunk)

            header = (
                f"* CHUNK : {chunk.label}\n"
                f"* TYPE  : {chunk.chunk_type}\n"
                f"* SOURCE: {file_path}\n"
                f"* DEPS  : {', '.join(chunk.dependencies) or '(none)'}\n"
                f"*{'─' * 66}\n"
            )
            out_file.write_text(header + source_text + "\n", encoding="utf-8")
            print(f"  wrote {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export HLASM chunk source for LLM documentation"
    )
    parser.add_argument("--sources", nargs="+", required=True, metavar="FILE")
    parser.add_argument("--copybook-path", "-c", default="", metavar="DIR")
    parser.add_argument("--external-path", "-e", default="", metavar="DIR")
    parser.add_argument("--recursive", "-r", action="store_true")
    parser.add_argument(
        "--output-dir", "-o", default="outputs/expanded", metavar="DIR"
    )
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for src in args.sources:
        print(f"\n=== {src} ===")
        export(
            source=src,
            copybook_path=args.copybook_path,
            external_path=args.external_path,
            recursive=args.recursive,
            output_dir=out,
        )


if __name__ == "__main__":
    main()
