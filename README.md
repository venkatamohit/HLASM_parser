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
# JSON output (default)
python -m hlasm_parser program.asm --copybook-path ./macros

# Human-readable text
python -m hlasm_parser program.asm -c ./macros -f text

# Recursively follow CALL dependencies
python -m hlasm_parser program.asm -c ./macros -e ./programs -r -o result.json
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
pytest                         # all 141 tests
pytest -v --tb=short           # verbose
pytest tests/test_parser.py    # single module
```

---

## Project Structure

```
hlasm_parser/
├── models.py              – CodeElement, LabelledBlock, ParsedInstruction, Chunk
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
