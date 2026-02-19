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

## Pipeline

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
pytest                         # all 231 tests
pytest -v --tb=short           # verbose
pytest tests/test_parser.py    # single module
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
│   └── hlasm_analysis.py
├── chunker/
│   └── chunker.py
└── cli.py
tests/
├── fixtures/              – sample HLASM files + macro copybooks
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
