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
Instead of complete instruction parsing it uses source-level markers and
dynamically discovered macro definitions to extract subroutine chunks and
build a call graph — with no external dependencies.

Use it when your codebase follows the GO / L / IN / OUT convention and you
need quick chunk extraction without full macro expansion.

### How it works

```
Driver file  (lines start..end)
      │
      ▼  scan all source files for MACRO…MEND blocks
      │    → builds macro catalog  (macros.json)
      │    → writes each macro as a chunk tagged [macro]
      │
      ▼  extract main block  →  main_sub.txt
      │
      ▼  scan for call patterns:
      │    GO / GOIF / GOIFNOT <name>
      │    L  Rx,=V(<name>)  /  L  Rx,=A(<name>)
      │    L  <name>                          (plain Link)
      │    <MacroName> operands               (known macro invocation –
      │                                        targets resolved from macro body)
      │
      ▼  for each <name> – BFS search for:
      │    <name>  IN … OUT   (primary – subroutine block)
      │    <name>  EQU  *     (fallback – dispatch/data table anchor)
      │
      ▼  recurse into each found block
      │
      ▼  write output:
           chunks/   <name>_sub.txt   each subroutine chunk
                     <name>_macro.txt each macro chunk
           cfg/      flow.json        BFS call graph
                     cfg.dot          Graphviz DOT
                     cfg.mmd          Mermaid flowchart
```

### Python API

```python
from hlasm_parser.pipeline.light_parser import LightParser

lp = LightParser(
    driver_path="MAINPROG.asm",   # file containing the main flow
    deps_dir="./deps",            # searched recursively for subroutine files
    output_dir="./out/chunks",    # where chunk .txt files are written
)

# Extract lines 59-115 of the driver as the "main" block, then BFS-resolve
lp.run(start_line=59, end_line=115)

# Inspect results
print(lp.flow)          # {"main": ["VALIDATE", "MYMACRO", ...], ...}
print(lp.macros)        # discovered macro definitions keyed by name
print(lp.missing)       # names that could not be found anywhere

# Serialise the call graph
lp.to_json_str()        # JSON  (flow + macro catalog + node tags)
lp.to_dot()             # Graphviz DOT
lp.to_mermaid()         # Mermaid flowchart
```

### Output structure

```
<split-output>/
├── chunks/
│   ├── main_sub.txt          main block
│   ├── <name>_sub.txt        each resolved subroutine
│   └── <name>_macro.txt      each discovered macro
└── cfg/
    ├── flow.json             BFS call graph + macro catalog + node tags
    ├── cfg.dot               Graphviz DOT  (render: dot -Tpng cfg.dot)
    └── cfg.mmd               Mermaid flowchart
```

### `flow.json` structure

```json
{
  "entry": "main",
  "flow": {
    "main":     ["VALIDATE", "MYMACRO", "PROCESS"],
    "MYMACRO":  ["TCR050", "TCR051"],
    "VALIDATE": ["DBREAD", "ERRORS"]
  },
  "chunk_line_counts": { "main": 57, "VALIDATE": 84 },
  "macro_catalog": [
    { "name": "MYMACRO", "parameters": ["&P1"], "line_count": 8 }
  ],
  "node_tags": { "main": ["entry"], "MYMACRO": ["macro"] },
  "missing": []
}
```

### Call patterns detected

| Pattern | Example | Captured name |
|---|---|---|
| `GO` / `GOIF` / `GOIFNOT` | `GO    VALIDATE` | `VALIDATE` |
| V/A-type address constant | `L     R15,=V(CONVERT)` | `CONVERT` |
| Plain Link | `L     EXTSUB` | `EXTSUB` |
| Known macro invocation | `MYMACRO TCR050,1001` | resolved from macro body |

### Macro discovery

The parser scans all source files (driver + `deps_dir`) for `MACRO … MEND`
blocks **before** starting the BFS.  Each discovered macro is:

- Saved as `<NAME>_macro.txt` in the chunks directory.
- Analysed for `GO`, `L`, and `L Rx,=V()` patterns that use formal
  parameters — the parameters involved are recorded as *call params*.
- Tagged `["macro"]` in `node_tags` so the graph can render macros
  differently from plain subroutines.

When the BFS encounters a macro invocation in source code, it maps the
actual operands to the macro's call params and resolves each resulting
symbol as a subroutine target.  This means any macro that dispatches to
subroutines via its parameters is handled automatically — no hardcoding
of specific macro names.

### EQU * dispatch tables

When `L Rx,=V(TABLENAME)` is seen and `TABLENAME` has no `IN`/`OUT` block,
the parser falls back to locating `TABLENAME  EQU  *`.  The table block
extends until the first `EJECT` directive (HLASM's natural page/section
separator).  Labeled statements inside the table are included.  Any macro
invocations inside that block are resolved the same way as in regular code.

`NAME EQU symbolname` (symbol alias, no `*`) captures only that single line.

### Chunk boundary rules

| Source pattern | Behaviour |
|---|---|
| `NAME  IN` … `OUT` | Primary form. Block starts at IN, ends at OUT (inclusive). |
| `NAME  IN` … next `NAME IN` | OUT omitted – block ends just before the next IN header. |
| `NAME  EQU  *` | Fallback for dispatch tables. Block extends until first EJECT. IN/OUT wins if both exist. |
| `NAME  EQU  sym` | Alias form. Captures only the single EQU line. |

### Nested flow JSON for documentation generation

The flat `flow.json` tells you *what* calls *what*, but to generate documentation
for (say) the main loop you still have to open each chunk file separately to see
what it does.  The **nested flow** format solves this by embedding every chunk's
source lines directly into a single hierarchical JSON tree.

#### What it contains

```
cfg/nested_flow.json
├── format        "nested_flow_v1"
├── entry         "main"
├── chunks        flat dict: name → { kind, tags, line_count, source_lines }
├── tree          recursive call tree (see below)
└── missing       names that could not be resolved
```

The `tree` node schema:

| Field | Description |
|---|---|
| `name` | Chunk name |
| `kind` | `"sub"` or `"macro"` |
| `tags` | e.g. `["entry"]`, `["macro"]` |
| `source_lines` | Raw HLASM source lines (present on first visit only) |
| `calls` | Ordered list of child nodes |
| `ref` | `true` when this node was already expanded higher up (shared callee) |

Nodes that are called from multiple places are **fully expanded on the first
visit** and appear as lightweight `{ "name": "…", "ref": true }` stubs on
subsequent visits, so the tree is finite even for programs with shared helpers.

#### Example

```json
{
  "format": "nested_flow_v1",
  "entry": "main",
  "chunks": {
    "main":     { "kind": "sub",   "tags": ["entry"],   "line_count": 57, "source_lines": ["…"] },
    "VALIDATE": { "kind": "sub",   "tags": [],          "line_count": 84, "source_lines": ["…"] },
    "MYMACRO":  { "kind": "macro", "tags": ["macro"],   "line_count": 12, "source_lines": ["…"] },
    "ERRORS":   { "kind": "sub",   "tags": [],          "line_count": 48, "source_lines": ["…"] }
  },
  "tree": {
    "name": "main", "kind": "sub", "tags": ["entry"],
    "source_lines": ["…"],
    "calls": [
      {
        "name": "VALIDATE", "kind": "sub", "tags": [],
        "source_lines": ["…"],
        "calls": [
          { "name": "ERRORS", "kind": "sub", "tags": [], "source_lines": ["…"], "calls": [] }
        ]
      },
      {
        "name": "MYMACRO", "kind": "macro", "tags": ["macro"],
        "source_lines": ["…"],
        "calls": [
          { "name": "TCR050", "kind": "sub", "source_lines": ["…"], "calls": [] }
        ]
      },
      { "name": "ERRORS", "ref": true }
    ]
  },
  "missing": []
}
```

#### Python API

```python
lp.run(59, 115)
nf = lp.to_nested_flow()        # dict
nf_str = lp.to_nested_flow_str()  # JSON string
```

#### CLI flag

Add `--nested-flow` to any `--light-parser` invocation:

```bash
python -m hlasm_parser DRIVER.asm \
    -c ./deps --light-parser \
    --start-line 59 --end-line 115 \
    -s ./out \
    --nested-flow
```

This writes `out/cfg/nested_flow.json` alongside the existing `flow.json` and
`cfg.dot`.

### CLI

```bash
python -m hlasm_parser DRIVER.asm \
    -c ./deps \
    --light-parser \
    --start-line 59 \
    --end-line 115 \
    -s ./out
```

Produces `out/chunks/` (all `.txt` chunk files) and `out/cfg/` (graph files).
Add `--cfg-format mermaid` to get `cfg.mmd` instead of `cfg.dot`.

### Running the sample suite

```python
from hlasm_parser.pipeline.light_parser import LightParser
from pathlib import Path

lp = LightParser(
    driver_path="tests/fixtures/light_parser/sample_suite/MAINPROG.asm",
    deps_dir="tests/fixtures/light_parser/sample_suite/deps",
    output_dir="tests/fixtures/light_parser/sample_suite/chunks",
)
lp.run(59, 115)

cfg = Path("tests/fixtures/light_parser/sample_suite/cfg")
cfg.mkdir(exist_ok=True)
(cfg / "flow.json").write_text(lp.to_json_str())
(cfg / "cfg.dot").write_text(lp.to_dot())
(cfg / "cfg.mmd").write_text(lp.to_mermaid())
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
pytest                              # all 373 tests
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
│   └── light_parser.py    – lightweight GO/L/macro + IN/OUT chunk extractor
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
