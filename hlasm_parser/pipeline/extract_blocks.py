"""
ExtractBlocksTask
=================

Orchestrates the HLASM source-processing pipeline and returns a list of
:class:`~hlasm_parser.models.LabelledBlock` objects representing the labeled
sections found in the source.

Pipeline stages (mirrors tape-z's ``ExtractBlocksTask.java`` / ``HlasmCodeAnalysis.java``):

1. :class:`~hlasm_parser.passes.discard_after_72.DiscardAfter72Pass`
   – Truncate all lines to 72 characters.
2. :class:`~hlasm_parser.passes.macro_expansion.MacroExpansionParsePass`
   – Expand macro calls by inlining copybook content (skipped if no
   ``copybook_path`` is supplied).
3. :class:`~hlasm_parser.passes.line_continuation.LineContinuationCollapsePass`
   – Join continuation lines into single logical lines.
4. :class:`~hlasm_parser.passes.sanitise.LLMSanitisePass`
   – Strip trailing whitespace and other minor normalisation.
5. :class:`~hlasm_parser.passes.label_block.LabelBlockPass`
   – Group lines into labeled blocks.

The returned list contains only the *named* blocks (direct children of the
root); the root block itself (which holds any unlabeled prologue lines) is
not included unless it has content.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Set

from ..models import LabelledBlock
from ..passes.discard_after_72 import DiscardAfter72Pass
from ..passes.label_block import LabelBlockPass
from ..passes.line_continuation import LineContinuationCollapsePass
from ..passes.macro_expansion import MacroExpansionParsePass
from ..passes.sanitise import LLMSanitisePass
from .mnemonics import STANDARD_MNEMONICS

logger = logging.getLogger(__name__)


class ExtractBlocksTask:
    """
    High-level entry point for the HLASM parsing pipeline.

    Parameters
    ----------
    mnemonics:
        Set of known HLASM mnemonic strings.  Defaults to
        :data:`~hlasm_parser.pipeline.mnemonics.STANDARD_MNEMONICS`.
    """

    def __init__(self, mnemonics: Optional[Set[str]] = None) -> None:
        self._mnemonics: Set[str] = (
            set(mnemonics) if mnemonics is not None else set(STANDARD_MNEMONICS)
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def sections(
        self,
        file_path: str,
        copybook_path: str = "",
    ) -> List[LabelledBlock]:
        """
        Parse an HLASM source **file** and return its labeled sections.

        Parameters
        ----------
        file_path:
            Absolute or relative path to the ``.asm`` / ``.hlasm`` source file.
        copybook_path:
            Directory containing ``<NAME>_Assembler_Copybook.txt`` macro files.
            Pass an empty string to skip macro expansion.

        Returns
        -------
        List[LabelledBlock]
        """
        logger.info("Parsing file: %s", file_path)
        source_path = Path(file_path)
        lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return self._run_pipeline(lines, copybook_path)

    def sections_from_text(
        self,
        source: str,
        copybook_path: str = "",
    ) -> List[LabelledBlock]:
        """
        Parse HLASM source supplied as a **string** and return labeled sections.

        Parameters
        ----------
        source:
            Raw HLASM source text.
        copybook_path:
            Directory containing copybook files (may be empty).

        Returns
        -------
        List[LabelledBlock]
        """
        lines = source.splitlines()
        return self._run_pipeline(lines, copybook_path)

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(
        self,
        lines: List[str],
        copybook_path: str,
    ) -> List[LabelledBlock]:
        from ..models import CodeElement

        # Stage 1 – column truncation
        lines = DiscardAfter72Pass().run(lines)

        # Stage 2 – macro expansion (only when a copybook directory is given)
        if copybook_path:
            lines = MacroExpansionParsePass(self._mnemonics, copybook_path).run(lines)

        # Stage 3 – join continuation lines
        lines = LineContinuationCollapsePass().run(lines)

        # Stage 4 – sanitise
        lines = LLMSanitisePass().run(lines)

        # Stage 5 – label-block grouping
        root = LabelBlockPass().run(lines)

        result: List[LabelledBlock] = []

        # Include the root (prologue) block when it has substantive content.
        # The prologue contains instructions that precede the first named label
        # (e.g. the main program body referencing subroutines via BAL/CALL).
        prologue = [
            c for c in root.children
            if not isinstance(c, LabelledBlock)
            and c.element_type not in ("COMMENT", "EMPTY")
            and c.text.strip()
        ]
        if prologue:
            result.append(root)

        # All named child blocks (flat list – same as tape-z's sections())
        named: List[LabelledBlock] = [
            child for child in root.children if isinstance(child, LabelledBlock)
        ]
        result.extend(named)

        logger.info(
            "Extracted %d blocks (%s prologue + %d named)",
            len(result),
            "with" if prologue else "no",
            len(named),
        )
        return result
