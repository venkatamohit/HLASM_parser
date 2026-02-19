"""
HLASMDependencyMap
==================

Maintains a directed graph of inter-module ``DEPENDS_ON`` relationships and
a registry of already-analysed programs.

This is a Python port of tape-z's ``HLASMDependencyMap.java``.  Instead of
JGraphT the implementation uses Python's standard :mod:`collections` (for the
registry) and a simple adjacency-set representation for the dependency graph,
avoiding the need for an external graph library in the core module.

If NetworkX is available it is used for richer graph operations (transitive
closure, etc.), but the class degrades gracefully when NetworkX is not present.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import networkx as nx  # type: ignore[import]
    _HAS_NX = True
except ImportError:
    _HAS_NX = False


class HLASMDependencyMap:
    """
    Tracks dependency relationships between HLASM source modules.

    Attributes
    ----------
    resolved:
        Maps a program path / name to its analysis result (any object).
    """

    def __init__(self) -> None:
        self.resolved: Dict[str, Any] = {}
        # Adjacency list: src → set of dest
        self._edges: Dict[str, Set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Dependency graph operations
    # ------------------------------------------------------------------

    def add_call_dependency(self, src: str, dest: str) -> None:
        """Record that *src* calls / depends on *dest*."""
        self._edges[src].add(dest)
        # Ensure dest appears as a vertex even if it has no outgoing edges
        if dest not in self._edges:
            self._edges[dest] = set()

    def get_direct_dependencies(self, program: str) -> Set[str]:
        """Return the set of programs that *program* directly depends on."""
        return set(self._edges.get(program, set()))

    def get_all_dependencies(self, program: str) -> Set[str]:
        """
        Return the transitive closure of dependencies for *program*.

        Uses NetworkX if available, otherwise performs a BFS.
        """
        if _HAS_NX:
            g = self._to_nx()
            if program not in g:
                return set()
            return set(nx.descendants(g, program))

        # BFS fallback
        visited: Set[str] = set()
        queue = list(self._edges.get(program, set()))
        while queue:
            node = queue.pop()
            if node not in visited:
                visited.add(node)
                queue.extend(self._edges.get(node, set()))
        return visited

    def vertices(self) -> Set[str]:
        """All known program names (nodes in the dependency graph)."""
        nodes: Set[str] = set(self._edges.keys())
        for deps in self._edges.values():
            nodes.update(deps)
        return nodes

    def edges(self) -> List[Tuple[str, str]]:
        """All (src, dest) dependency pairs."""
        result: List[Tuple[str, str]] = []
        for src, dests in self._edges.items():
            for dest in dests:
                result.append((src, dest))
        return result

    # ------------------------------------------------------------------
    # Registry operations
    # ------------------------------------------------------------------

    def put(self, program_path: str, analysis_result: Any) -> None:
        """Store an analysis result for *program_path*."""
        self.resolved[program_path] = analysis_result

    def get(self, program_path: str) -> Optional[Any]:
        """Retrieve the analysis result for *program_path* (or None)."""
        return self.resolved.get(program_path)

    def contains(self, program_path: str) -> bool:
        """Return True if *program_path* has already been analysed."""
        return program_path in self.resolved

    def dependency_symbols(self) -> Set[str]:
        """Return all registered program paths."""
        return set(self.resolved.keys())

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vertices": sorted(self.vertices()),
            "edges": [{"src": s, "dest": d} for s, d in sorted(self.edges())],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_nx(self):  # type: ignore[return]
        """Convert to a NetworkX DiGraph (only called when NX is available)."""
        g = nx.DiGraph()
        for src, dests in self._edges.items():
            g.add_node(src)
            for dest in dests:
                g.add_edge(src, dest)
        return g
