# HLASM Parser

A Python parser for IBM **High Level Assembler (HLASM)** code that expands
macros, copybooks, and subroutine dependencies into structured **chunks**.

Inspired by the architecture of [tape-z](https://github.com/avishek-sen-gupta/tape-z)
(Java/ANTLR4), rewritten entirely in Python with no external parser dependencies.

---

## Features

| Feature | Details |
|---|---|
| **Column-correct parsing** | Respects HLASM fixed-column format (cols 1-8 label, 9+ instruction) |
| **72-column truncation** | Sequence numbers in cols 73+ are silently dropped |
| **Macro expansion** | Expands `<NAME>_Assembler_Copybook.txt` files with parameter substitution |
| **Continuation lines** | Joins lines continued at column 16 |
| **Labeled block grouping** | Groups source into named sections (subroutines, CSECT, DSECT, macros) |
| **Instruction parsing** | Parses opcode + operands (nested parens, quoted strings, literals) |
| **Dependency tracking** | Extracts CALL / LINK / XCTL / BAL / BAS targets as chunk dependencies |
| **Dependency graph** | Builds a directed `DEPENDS_ON` graph across files |
| **JSON / text output** | CLI supports both formats |
| **Recursive analysis** | Optionally follows CALL targets to their source files |

---

## Installation

```bash
pip install -e ".[dev]"          # development install with test deps
pip install -e ".[graph]"        # with NetworkX for richer dependency queries
```

Requires Python 3.11+.

---

## Quick Start

### Python API

```python
from hlasm_parser import HlasmAnalysis

analysis = HlasmAnalysis(copybook_path="./macros")

# Analyse a single file
chunks = analysis.analyze_file("my_program.asm")

for chunk in chunks:
    print(f"{chunk.label:20s} {chunk.chunk_type:12s} "
          f"{len(chunk.instructions):4d} instrs  deps={chunk.dependencies}")
```

### CLI

```bash
python -m hlasm_parser SOURCE [OPTIONS]
```

#### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--copybook-path DIR` | `-c` | — | Directory containing macro copybook files |
| `--external-path DIR` | `-e` | — | Directory searched when resolving `CALL`/`LINK`/`XCTL` targets |
| `--output FILE` | `-o` | stdout | Write output to a file instead of stdout |
| `--format` | `-f` | `json` | Output format: `json` or `text` |
| `--recursive` | `-r` | off | Follow CALL/LINK targets and analyse their source files too |
| `--missing-deps-log FILE` | — | — | Write unresolved-dependency details to a JSON file (see below) |
| `--cfg` | — | off | Emit a Control Flow Graph instead of chunk output |
| `--cfg-format` | — | `dot` | CFG format when `--cfg` is set: `dot`, `json`, or `mermaid` |
| `--verbose` | `-v` | off | Enable DEBUG logging |

#### Getting chunks – single file

```bash
# JSON (default) – prints a list of chunk objects
python -m hlasm_parser program.asm --copybook-path ./macros

# Human-readable table
python -m hlasm_parser program.asm -c ./macros -f text

# Save to file
python -m hlasm_parser program.asm -c ./macros -o chunks.json
```

Single-file JSON output is an array of chunk objects:

```json
[
  {
    "label": "PAYROLL",
    "chunk_type": "CSECT",
    "source_file": "program.asm",
    "instruction_count": 42,
    "dependencies": ["CALCBASE", "PRINTPAY"],
    "instructions": [ ... ]
  }
]
```

#### Getting chunks – recursive (follows CALL dependencies)

```bash
# Follow every CALL/LINK target into its own source file
python -m hlasm_parser program.asm -c ./macros -e ./programs --recursive

# Save recursive output to file
python -m hlasm_parser program.asm -c ./macros -e ./programs -r -o result.json
```

Recursive JSON output is an object keyed by file path:

```json
{
  "files": {
    "programs/PAYROLL.asm":  [ { "label": "PAYROLL", ... } ],
    "programs/CALCBASE.asm": [ { "label": "CALCBASE", ... } ]
  },
  "missing_dependencies": []
}
```

#### Handling missing dependency files

When a `CALL` target cannot be resolved to a source file, the parser
**continues creating chunks for all files that were found** and records
the gaps. Missing deps are always shown in the output and on stderr:

```bash
# Show missing deps in output; also save a dedicated JSON report
python -m hlasm_parser program.asm -e ./programs -r \
    --missing-deps-log missing.json
```

stderr (always printed when deps are missing):
```
WARNING: 2 unresolved dependencies (chunks created for all found files):
  [MISSING] SUBPROG1             referenced from HLASM_ROOT in program.asm (searched: ./programs)
  [MISSING] SUBPROG2             referenced from HLASM_ROOT in program.asm (searched: ./programs)
  Missing-dep log written to: missing.json
```

`missing.json`:
```json
{
  "unresolved_count": 2,
  "missing_dependencies": [
    {
      "dep_name": "SUBPROG1",
      "referenced_from_file": "program.asm",
      "referenced_in_chunk": "HLASM_ROOT",
      "search_path": "./programs"
    }
  ]
}
```

Text output (`-f text`) appends a table at the end:
```
════════════════════════════════════════════════════════════
  MISSING DEPENDENCIES (2 unresolved)
════════════════════════════════════════════════════════════
  SYMBOL                CHUNK                 SOURCE FILE
  ────────────────────  ────────────────────  ──────────────────────────
  SUBPROG1              HLASM_ROOT            program.asm
  SUBPROG2              HLASM_ROOT            program.asm

  Chunks for all FOUND files were created normally.
  The symbols above could not be resolved in: ./programs
```

---

## Light Parser

The **Light Parser** is a fast, focused alternative to the full pipeline.
Instead of doing complete instruction parsing, it uses a small set of
call-pattern regexes and `IN` / `OUT` source markers to extract subroutine
chunks and build a call graph — with no external dependencies.

Use it when your codebase follows the GO / L / VTRAN + IN/OUT convention and
you need quick chunk extraction without full macro expansion.

### How it works

```
Driver file  (lines start..end)
      │
      ▼  extract main block
      │
      ▼  scan for call patterns:
      │    GO / GOIF / GOIFNOT <name>
      │    L  Rx,=V(<name>)
      │    L  <name>           (plain Link)
      │    VTRAN seq,type,<name>,id   (translation-table entry, 3rd operand)
      │
      ▼  for each <name> – BFS search for:
      │    <name>  IN … OUT   (primary – inline subroutine block)
      │    <name>  EQU  *     (fallback – translation/dispatch table)
      │
      ▼  recurse into each found block
      │
      ▼  write <name>.txt chunks + flow.json / cfg.dot / cfg.mmd
```

### Python API

```python
from hlasm_parser.pipeline.light_parser import LightParser

lp = LightParser(
    driver_path="MAINPROG.asm",   # file containing the main flow
    deps_dir="./deps",            # searched recursively for subroutine files
    output_dir="./chunks",        # where .txt chunks are written
)

# Extract lines 59-115 of the driver as the "main" block, then BFS-resolve
lp.run(start_line=59, end_line=115)

# Inspect results
print(lp.flow)          # {"main": ["VALIDATE", "PROCESS", ...], ...}
print(lp.missing)       # names that could not be found in any file

# Serialise the call graph
lp.to_json_str()        # JSON string  → flow.json
lp.to_dot()             # Graphviz DOT → cfg.dot
lp.to_mermaid()         # Mermaid      → cfg.mmd
```

### Output files

| File | Description |
|---|---|
| `main.txt` | Raw source lines of the extracted main block |
| `<NAME>.txt` | Raw source lines of each resolved subroutine chunk |
| `flow.json` | BFS call graph + chunk line counts + missing targets |
| `cfg.dot` | Graphviz DOT call graph (render with `dot -Tpng cfg.dot`) |
| `cfg.mmd` | Mermaid flowchart (paste into any Mermaid renderer) |

### `flow.json` structure

```json
{
  "entry": "main",
  "flow": {
    "main":     ["VALIDATE", "PROCESS", "CONVERT"],
    "VALIDATE": ["DBREAD", "ERRORS"],
    "PROCESS":  ["FORMAT", "DBWRITE", "ERRORS"]
  },
  "chunk_line_counts": {
    "main": 57, "VALIDATE": 84, "PROCESS": 97
  },
  "missing": []
}
```

### Call patterns detected

| Pattern | Example | Captured name |
|---|---|---|
| `GO` / `GOIF` / `GOIFNOT` | `GO    VALIDATE` | `VALIDATE` |
| V-type address constant | `L     R15,=V(CONVERT)` | `CONVERT` |
| Plain Link | `L     EXTSUB` | `EXTSUB` |
| VTRAN dispatch entry | `VTRAN 05,0,TCR050,1001` | `TCR050` |

### Chunk boundary rules

| Source pattern | Behaviour |
|---|---|
| `NAME  IN` … `OUT` | Primary form. Block starts at IN, ends at (and includes) OUT. |
| `NAME  IN` … next `NAME IN` | OUT omitted – block ends just before the next IN header. |
| `NAME  EQU  *` | Fallback for translation tables. Block extends until the next labeled statement (non-blank col 1). IN/OUT always wins if both exist. |

### EQU * translation tables

A common HLASM pattern links to a dispatch table rather than a subroutine:

```hlasm
         L     R15,=V(VTRANTAB)    Load address of translation table
         BALR  R14,R15

VTRANTAB EQU   *                   ← captured as a chunk (EQU * fallback)
         VTRAN 05,0,TCR050,1001    ← TCR050 extracted as a BFS target
         VTRAN 05,0,TCR051,1002    ← TCR051 extracted as a BFS target
NEXTLBL  DS    0H                  ← table ends here (labeled statement)
```

The Light Parser captures `VTRANTAB` as an EQU * chunk, then resolves
`TCR050` and `TCR051` via their normal `IN` / `OUT` blocks (which may live
in the driver file or in any file under `deps_dir`).

### Running the sample suite

A ready-made payroll example lives under `tests/fixtures/light_parser/sample_suite/`:

```bash
python - <<'EOF'
from hlasm_parser.pipeline.light_parser import LightParser
from pathlib import Path

lp = LightParser(
    driver_path="tests/fixtures/light_parser/sample_suite/MAINPROG.asm",
    deps_dir="tests/fixtures/light_parser/sample_suite/deps",
    output_dir="tests/fixtures/light_parser/sample_suite/chunks",
)
lp.run(59, 115)

out = Path("tests/fixtures/light_parser/sample_suite/chunks")
(out / "flow.json").write_text(lp.to_json_str())
(out / "cfg.dot").write_text(lp.to_dot())
(out / "cfg.mmd").write_text(lp.to_mermaid())

print(lp.to_json_str())
EOF
```

Pre-generated outputs for the sample suite are committed under
`tests/fixtures/light_parser/sample_suite/chunks/`.

---


The parser applies five sequential passes (matching tape-z's pipeline):

```
Source file
    │
    ▼  DiscardAfter72Pass           – truncate to 72 columns
    │
    ▼  MacroExpansionParsePass      – inline copybook content
    │                                 (skipped if no copybook-path given)
    │
    ▼  LineContinuationCollapsePass – join continuation lines
    │
    ▼  LLMSanitisePass              – strip trailing whitespace
    │
    ▼  LabelBlockPass               – group into labelled blocks
    │
    ▼  Chunker                      – parse instructions, extract deps
    │
    ▼  List[Chunk]
```

---

## Chunk Structure

```python
@dataclass
class Chunk:
    label: str                    # Labeled block name (e.g. "PROCESS1")
    chunk_type: str               # CSECT | DSECT | SUBROUTINE | MACRO
    source_file: str              # Path to the source file
    instructions: List[ParsedInstruction]
    dependencies: List[str]       # Symbols this chunk calls / branches to
```

Each `ParsedInstruction` carries `opcode`, `operands`, `comment`,
`instruction_type` (BRANCH / CALL / SECTION / DATA / MACRO_CTRL / INSTRUCTION),
and the `raw_text`.

---

## Macro Copybook Format

Place copybooks in a directory and name them `<MACRONAME>_Assembler_Copybook.txt`:

```
         MACRO
&LABEL   PRINTMSG &MSG,&LEN
* Body – &MSG and &LEN are substituted at expansion time
         LA    0,&MSG
         LA    1,&LEN
         SVC   35
         MEND
```

---

## Running Tests

```bash
pytest                              # all 343 tests
pytest -v --tb=short                # verbose
pytest tests/test_parser.py         # single module
pytest tests/test_light_parser.py   # light parser only
```

---

## Project Structure

```
hlasm_parser/
├── models.py              – CodeElement, LabelledBlock, ParsedInstruction, Chunk, MissingDependency
├── passes/
│   ├── discard_after_72.py
│   ├── copybook_processor.py
│   ├── macro_expansion.py
│   ├── label_block.py
│   ├── line_continuation.py
│   └── sanitise.py
├── parser/
│   └── instruction_parser.py
├── pipeline/
│   ├── mnemonics.py
│   ├── extract_blocks.py
│   ├── dependency_map.py
│   ├── hlasm_analysis.py
│   └── light_parser.py    – lightweight GO/L/VTRAN + IN/OUT chunk extractor
├── chunker/
│   └── chunker.py
└── cli.py
tests/
├── fixtures/
│   ├── light_parser/
│   │   ├── driver.asm     – inline subroutine fixture
│   │   ├── deps/          – external subroutine files
│   │   └── sample_suite/  – payroll example (MAINPROG + deps + pre-built chunks)
│   └── ...                – other HLASM sample files + macro copybooks
├── test_light_parser.py
├── test_passes.py
├── test_parser.py
├── test_copybook.py
├── test_pipeline.py
├── test_chunker.py
└── test_integration.py
```

---

## License

MIT
