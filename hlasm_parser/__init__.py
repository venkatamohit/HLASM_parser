"""
HLASM Parser
============

A Python parser for IBM High Level Assembler (HLASM) code that expands
macros, copybooks, and subroutine dependencies into structured *chunks*.

Architecture mirrors the tape-z Java project (github.com/avishek-sen-gupta/tape-z)
but is implemented entirely in Python.

Quick start
-----------
>>> from hlasm_parser import HlasmAnalysis
>>> analysis = HlasmAnalysis(copybook_path="./macros")
>>> chunks = analysis.analyze_file("my_program.asm")
>>> for chunk in chunks:
...     print(chunk.label, chunk.chunk_type, len(chunk.instructions))
"""

from .models import Chunk, CodeElement, LabelledBlock, ParsedInstruction
from .pipeline.extract_blocks import ExtractBlocksTask
from .pipeline.hlasm_analysis import HlasmAnalysis
from .chunker.chunker import Chunker

__version__ = "0.1.0"
__all__ = [
    "Chunk",
    "CodeElement",
    "LabelledBlock",
    "ParsedInstruction",
    "ExtractBlocksTask",
    "HlasmAnalysis",
    "Chunker",
]
