"""
HlasmAnalysis
=============

Full HLASM code analysis pipeline.

Combines :class:`~hlasm_parser.pipeline.extract_blocks.ExtractBlocksTask`
(block extraction) with :class:`~hlasm_parser.chunker.chunker.Chunker`
(chunk production) and :class:`~hlasm_parser.pipeline.dependency_map.HLASMDependencyMap`
(inter-module dependency tracking).

Supports both single-file and recursive multi-file analysis (following
subroutine / CALL dependencies to their source files).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..chunker.chunker import Chunker
from ..models import Chunk, MissingDependency
from ..pipeline.dependency_map import HLASMDependencyMap
from ..pipeline.extract_blocks import ExtractBlocksTask

logger = logging.getLogger(__name__)

# Maximum recursion depth when following dependencies
_MAX_DEPTH = 20


class HlasmAnalysis:
    """
    High-level facade for HLASM code analysis.

    Parameters
    ----------
    copybook_path:
        Directory containing ``<NAME>_Assembler_Copybook.txt`` macro files.
        Leave empty to skip macro expansion.
    external_path:
        Directory to search when resolving CALL / LINK / XCTL target program
        names to actual source files.  Leave empty to disable dependency
        following.
    """

    def __init__(
        self,
        copybook_path: str = "",
        external_path: str = "",
    ) -> None:
        self.copybook_path = copybook_path
        self.external_path = external_path
        self._extractor = ExtractBlocksTask()
        self._chunker = Chunker()
        self.dependency_map = HLASMDependencyMap()
        #: Populated by :meth:`analyze_with_dependencies` – one entry for
        #: every dependency symbol that could not be resolved to a source file.
        self.missing_deps: List[MissingDependency] = []

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def analyze_file(self, file_path: str) -> List[Chunk]:
        """
        Analyse a single HLASM source *file*.

        Parameters
        ----------
        file_path:
            Path to the HLASM source file.

        Returns
        -------
        List[Chunk]
            One chunk per labeled block found in the file.
        """
        blocks = self._extractor.sections(file_path, self.copybook_path)
        chunks = self._chunker.chunk(blocks, source_file=file_path)
        self._record_dependencies(file_path, chunks)
        return chunks

    def analyze_text(
        self,
        source: str,
        source_name: str = "<inline>",
    ) -> List[Chunk]:
        """
        Analyse HLASM source supplied as a **string**.

        Parameters
        ----------
        source:
            Raw HLASM source code.
        source_name:
            A label used as the ``source_file`` field in returned chunks.

        Returns
        -------
        List[Chunk]
        """
        blocks = self._extractor.sections_from_text(source, self.copybook_path)
        chunks = self._chunker.chunk(blocks, source_file=source_name)
        self._record_dependencies(source_name, chunks)
        return chunks

    def analyze_with_dependencies(
        self,
        file_path: str,
    ) -> Dict[str, List[Chunk]]:
        """
        Analyse a file **and** recursively follow its CALL / LINK / XCTL
        dependencies to their source files.

        Parameters
        ----------
        file_path:
            Root HLASM source file.

        Returns
        -------
        Dict[str, List[Chunk]]
            Mapping from file path to its chunks (includes the root file and
            all reachable dependency files).
        """
        self.missing_deps = []          # reset for each top-level call
        results: Dict[str, List[Chunk]] = {}
        self._analyze_recursive(file_path, results, depth=0)
        if self.missing_deps:
            logger.warning(
                "%d unresolved dependenc%s – run with --missing-deps-log to save details",
                len(self.missing_deps),
                "y" if len(self.missing_deps) == 1 else "ies",
            )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _analyze_recursive(
        self,
        file_path: str,
        results: Dict[str, List[Chunk]],
        depth: int,
    ) -> None:
        if depth > _MAX_DEPTH:
            logger.warning("Max recursion depth (%d) reached for %s", _MAX_DEPTH, file_path)
            return

        if file_path in results:
            return  # Already processed

        resolved = Path(file_path)
        if not resolved.exists():
            logger.warning("Source file not found: %s", file_path)
            return

        logger.info("Analysing (depth=%d): %s", depth, file_path)
        chunks = self.analyze_file(file_path)
        results[file_path] = chunks

        # Build a set of all chunk labels that are already known (from all
        # analysed files including the current one).  A dep that matches a
        # known label is a local/internal call – not a missing external file.
        known_labels: Set[str] = {
            c.label.upper()
            for existing_chunks in results.values()
            for c in existing_chunks
        }
        known_labels.update(c.label.upper() for c in chunks)

        # Follow dependencies
        seen_deps: Set[str] = set()
        for chunk in chunks:
            for dep in chunk.dependencies:
                if dep in seen_deps:
                    continue
                seen_deps.add(dep)
                dep_path = self._resolve_dependency(dep)
                if dep_path:
                    if dep_path not in results:
                        self._analyze_recursive(dep_path, results, depth + 1)
                elif dep.upper() not in known_labels:
                    # Could not find a source file AND not a local label.
                    # Chunk creation continues; the gap is recorded for reporting.
                    missing = MissingDependency(
                        dep_name=dep,
                        referenced_from_file=file_path,
                        referenced_in_chunk=chunk.label,
                        search_path=self.external_path,
                    )
                    self.missing_deps.append(missing)
                    logger.warning("Unresolved dependency: %s", missing)

    def _resolve_dependency(self, dep_name: str) -> Optional[str]:
        """
        Try to locate the source file for a dependency symbol name.

        Tries common HLASM file extensions in the configured ``external_path``
        directory.
        """
        if not self.external_path:
            return None

        search_dir = Path(self.external_path)
        for ext in (".asm", ".hlasm", ".s", ".ASM", ".HLASM", ""):
            candidate = search_dir / f"{dep_name}{ext}"
            if candidate.exists():
                return str(candidate)

        logger.debug("Could not resolve dependency %r in %s", dep_name, self.external_path)
        return None

    def _record_dependencies(self, source: str, chunks: List[Chunk]) -> None:
        for chunk in chunks:
            for dep in chunk.dependencies:
                self.dependency_map.add_call_dependency(source, dep)
