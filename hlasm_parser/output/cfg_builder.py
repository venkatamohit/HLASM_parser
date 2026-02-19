"""
cfg_builder.py
==============

Build and render a **Control Flow Graph** (CFG) from the output of
:meth:`~hlasm_parser.pipeline.hlasm_analysis.HlasmAnalysis.analyze_with_dependencies`.

Graph semantics
---------------
* **Nodes** – one per program (source file).  The "driver" is the root file
  passed to ``analyze_with_dependencies``.
* **Edges** – a directed call edge from program A to program B whenever any
  chunk in A has an instruction that calls / branches to a symbol that resolves
  to B.
* **Color coding**

  ==========  =======  ================================================
  Status      Color    Meaning
  ==========  =======  ================================================
  ``driver``  Blue     The root / entry-point program.
  ``present`` Green    Dependency whose source file was found & analysed.
  ``missing`` Red      Dependency referenced but whose file was not found.
  ==========  =======  ================================================

Outputs
-------
* **DOT** (Graphviz) – renderable with ``dot -Tsvg -o out.svg graph.dot``.
* **JSON** – machine-readable graph for web renderers or further processing.
* **Mermaid** – embeddable in GitHub Markdown / Notion / Confluence.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..models import Chunk

# ---------------------------------------------------------------------------
# Colour + shape constants
# ---------------------------------------------------------------------------

_FILL = {
    "driver":  "#2E86AB",   # steel blue
    "present": "#27AE60",   # emerald green
    "missing": "#E74C3C",   # alizarin red
}
_FONT = {"driver": "white", "present": "white", "missing": "white"}
_DOT_STYLE = {
    "driver":  "filled",
    "present": "filled",
    "missing": "filled,dashed",
}
_DOT_SHAPE = {
    "driver":  "doubleoctagon",
    "present": "box",
    "missing": "box",
}
_EDGE_COLOR = {
    "present": "#444444",
    "missing": "#E74C3C",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CFGNode:
    """A single node in the control flow graph (one per program)."""

    id: str             # Unique stable ID, e.g. "PAYROLL"
    label: str          # Display label
    status: str         # "driver" | "present" | "missing"
    file_path: str      # Absolute/relative path (empty string when missing)
    chunk_types: List[str] = field(default_factory=list)  # e.g. ["CSECT", "SUBROUTINE"]


@dataclass
class CFGEdge:
    """A directed call edge between two program nodes."""

    from_id: str            # Caller program ID
    to_id: str              # Callee program ID
    call_types: List[str]   # Opcodes used (e.g. ["CALL", "BAL"])
    from_chunks: List[str]  # Chunk labels within the caller that make this call
    to_status: str          # "present" | "missing" (mirrors target node status)


@dataclass
class ControlFlowGraph:
    """Complete program-level control flow graph."""

    driver: str             # ID of the driver / root node
    nodes: List[CFGNode]
    edges: List[CFGEdge]


# ---------------------------------------------------------------------------
# Helper: find the opcode that calls a given target within a chunk
# ---------------------------------------------------------------------------

_STRIP_PARENS_RE = re.compile(r"^\((.+)\)$")


def _clean_operand(token: str) -> str:
    """Strip parentheses and keyword= prefixes from an operand token."""
    t = token.strip()
    m = _STRIP_PARENS_RE.match(t)
    if m:
        t = m.group(1).strip()
    if "=" in t:
        _, _, t = t.partition("=")
        t = t.strip()
        m = _STRIP_PARENS_RE.match(t)
        if m:
            t = m.group(1).strip()
    return t.upper()


def _find_call_opcode(chunk: Chunk, dep_label: str) -> Optional[str]:
    """
    Return the opcode of the first instruction in *chunk* that references
    *dep_label* as a call target.  Returns ``None`` if not found.
    """
    dep_upper = dep_label.upper()
    for instr in chunk.instructions:
        if not instr.opcode:
            continue
        for operand in instr.operands:
            if _clean_operand(operand) == dep_upper:
                return instr.opcode.upper()
    return None


# ---------------------------------------------------------------------------
# CFGBuilder
# ---------------------------------------------------------------------------

class CFGBuilder:
    """
    Build a program-level :class:`ControlFlowGraph` from analysis results.

    Parameters
    ----------
    results:
        The ``Dict[str, List[Chunk]]`` returned by
        :meth:`~hlasm_parser.pipeline.hlasm_analysis.HlasmAnalysis.analyze_with_dependencies`.
    driver_file:
        The root source file that was passed as the entry point.
    """

    def build(
        self,
        results: Dict[str, List[Chunk]],
        driver_file: str,
    ) -> ControlFlowGraph:
        """
        Build and return the :class:`ControlFlowGraph`.

        Program-level semantics
        ~~~~~~~~~~~~~~~~~~~~~~~
        * Each present file in *results* becomes a **green** node (or **blue**
          for the driver).
        * Any dependency that couldn't be resolved to a file becomes a **red**
          missing node.
        * Cross-file call edges are labelled with the opcode(s) and source
          chunk(s) responsible.
        * Local (intra-program) calls are **not** shown at this level.
        """
        driver_stem = Path(driver_file).stem.upper()

        # Map: chunk_label.upper() → file_path  (for all resolved files)
        label_to_file: Dict[str, str] = {}
        for fp, chunks in results.items():
            for chunk in chunks:
                label_to_file[chunk.label.upper()] = fp

        # Map: file_path → set of chunk_types
        file_chunk_types: Dict[str, List[str]] = defaultdict(list)
        for fp, chunks in results.items():
            for chunk in chunks:
                file_chunk_types[fp].append(chunk.chunk_type)

        # Map: file_path → node id (stem.upper())
        file_to_node_id: Dict[str, str] = {
            fp: Path(fp).stem.upper() for fp in results
        }

        # ----------------------------------------------------------------
        # Walk every chunk in every file and collect cross-program calls
        # ----------------------------------------------------------------
        # edge_key → (set_of_opcodes, set_of_from_chunks, to_status)
        EdgeKey = Tuple[str, str]  # (from_node_id, to_node_id)
        edge_opcodes: Dict[EdgeKey, Set[str]] = defaultdict(set)
        edge_chunks: Dict[EdgeKey, Set[str]] = defaultdict(set)
        edge_status: Dict[EdgeKey, str] = {}
        missing_nodes: Dict[str, CFGNode] = {}  # id → CFGNode for missing deps

        for fp, chunks in results.items():
            from_id = file_to_node_id[fp]

            for chunk in chunks:
                for dep in chunk.dependencies:
                    dep_upper = dep.upper()

                    # Determine where this dep lives
                    to_file = label_to_file.get(dep_upper)

                    if to_file is None:
                        # Not found in any analysed file → MISSING
                        to_id = dep_upper
                        status = "missing"
                        if to_id not in missing_nodes:
                            missing_nodes[to_id] = CFGNode(
                                id=to_id,
                                label=dep,
                                status="missing",
                                file_path="",
                                chunk_types=[],
                            )
                    elif to_file == fp:
                        # Same file → local subroutine call, skip at program level
                        continue
                    else:
                        # Cross-file → PRESENT
                        to_id = file_to_node_id[to_file]
                        status = "present"

                    key: EdgeKey = (from_id, to_id)
                    opcode = _find_call_opcode(chunk, dep) or "CALL"
                    edge_opcodes[key].add(opcode)
                    edge_chunks[key].add(chunk.label)
                    edge_status[key] = status

        # ----------------------------------------------------------------
        # Build node list
        # ----------------------------------------------------------------
        nodes: List[CFGNode] = []
        for fp, chunks in results.items():
            node_id = file_to_node_id[fp]
            status = "driver" if node_id == driver_stem else "present"
            ctypes = sorted(set(file_chunk_types[fp]))
            nodes.append(CFGNode(
                id=node_id,
                label=node_id,
                status=status,
                file_path=fp,
                chunk_types=ctypes,
            ))

        # Add missing nodes (stable sort by id)
        nodes.extend(sorted(missing_nodes.values(), key=lambda n: n.id))

        # ----------------------------------------------------------------
        # Build edge list
        # ----------------------------------------------------------------
        edges: List[CFGEdge] = []
        for (from_id, to_id), opcodes in edge_opcodes.items():
            edges.append(CFGEdge(
                from_id=from_id,
                to_id=to_id,
                call_types=sorted(opcodes),
                from_chunks=sorted(edge_chunks[(from_id, to_id)]),
                to_status=edge_status[(from_id, to_id)],
            ))

        # Stable sort: driver edges first, then by (from, to)
        edges.sort(key=lambda e: (0 if e.from_id == driver_stem else 1, e.from_id, e.to_id))

        return ControlFlowGraph(driver=driver_stem, nodes=nodes, edges=edges)

    # ------------------------------------------------------------------
    # DOT (Graphviz) renderer
    # ------------------------------------------------------------------

    def to_dot(self, graph: ControlFlowGraph, title: str = "") -> str:
        """Render *graph* as a Graphviz DOT string."""
        lines: List[str] = []
        title = title or f"{graph.driver} Control Flow Graph"

        lines += [
            f'digraph "{graph.driver}_CFG" {{',
            f'    label="{title}";',
            '    labelloc=t;',
            '    rankdir=TB;',
            '    compound=true;',
            '    node [fontname="Courier New", fontsize=11, margin="0.2,0.1"];',
            '    edge [fontname="Courier New", fontsize=9];',
            '',
        ]

        # Legend subgraph
        lines += [
            '    subgraph cluster_legend {',
            '        label="Legend"; style=dashed; color="#AAAAAA";',
            '        fontname="Courier New"; fontsize=9;',
            '        L_driver  [label="Driver\\n(entry point)", '
            f'shape=doubleoctagon, style=filled, fillcolor="{_FILL["driver"]}", fontcolor=white, fontsize=9];',
            '        L_present [label="Present\\n(file found)",   '
            f'shape=box, style=filled, fillcolor="{_FILL["present"]}", fontcolor=white, fontsize=9];',
            '        L_missing [label="Missing\\n(not found)",   '
            f'shape=box, style="filled,dashed", fillcolor="{_FILL["missing"]}", fontcolor=white, fontsize=9];',
            '        L_driver -> L_present [style=invis];',
            '        L_present -> L_missing [style=invis];',
            '    }',
            '',
        ]

        # Nodes
        for node in graph.nodes:
            ctypes = ", ".join(node.chunk_types) if node.chunk_types else ""
            if node.status == "driver":
                node_label = f"{node.label}\\n[DRIVER]"
                if ctypes:
                    node_label += f"\\n{ctypes}"
            elif node.status == "missing":
                node_label = f"{node.label}\\n[NOT FOUND]"
            else:
                node_label = node.label
                if ctypes:
                    node_label += f"\\n{ctypes}"

            attrs = (
                f'label="{node_label}", '
                f'shape={_DOT_SHAPE[node.status]}, '
                f'style="{_DOT_STYLE[node.status]}", '
                f'fillcolor="{_FILL[node.status]}", '
                f'fontcolor="{_FONT[node.status]}"'
            )
            lines.append(f'    "{node.id}" [{attrs}];')

        lines.append('')

        # Edges
        for edge in graph.edges:
            opcodes_str = " | ".join(edge.call_types)
            chunks_str = ", ".join(edge.from_chunks)
            edge_label = f"{opcodes_str}\\n({chunks_str})"
            color = _EDGE_COLOR.get(edge.to_status, "#444444")
            style = "dashed" if edge.to_status == "missing" else "solid"
            lines.append(
                f'    "{edge.from_id}" -> "{edge.to_id}" '
                f'[label="{edge_label}", color="{color}", style={style}];'
            )

        lines.append('}')
        return '\n'.join(lines) + '\n'

    # ------------------------------------------------------------------
    # JSON renderer
    # ------------------------------------------------------------------

    def to_json(self, graph: ControlFlowGraph) -> dict:
        """Render *graph* as a JSON-serialisable dictionary."""
        return {
            "driver": graph.driver,
            "nodes": [
                {
                    "id": n.id,
                    "label": n.label,
                    "status": n.status,
                    "color": _FILL[n.status],
                    "file_path": n.file_path,
                    "chunk_types": n.chunk_types,
                }
                for n in graph.nodes
            ],
            "edges": [
                {
                    "from": e.from_id,
                    "to": e.to_id,
                    "call_types": e.call_types,
                    "from_chunks": e.from_chunks,
                    "to_status": e.to_status,
                    "color": _EDGE_COLOR.get(e.to_status, "#444444"),
                }
                for e in graph.edges
            ],
        }

    def to_json_str(self, graph: ControlFlowGraph, indent: int = 2) -> str:
        """Return *graph* serialised to a JSON string."""
        return json.dumps(self.to_json(graph), indent=indent)

    # ------------------------------------------------------------------
    # Mermaid renderer
    # ------------------------------------------------------------------

    def to_mermaid(self, graph: ControlFlowGraph, title: str = "") -> str:
        """
        Render *graph* as a Mermaid flowchart (embeddable in GitHub Markdown).

        Colour coding uses ``classDef`` directives.  Paste the output inside
        a ````` ```mermaid ``` ``` fenced code block.
        """
        lines: List[str] = []
        title = title or f"{graph.driver} Control Flow Graph"

        lines += [
            "---",
            f'title: "{title}"',
            "---",
            "flowchart TD",
        ]

        # Nodes
        for node in graph.nodes:
            safe_id = re.sub(r"[^A-Za-z0-9_]", "_", node.id)
            if node.status == "driver":
                lbl = f"{node.label}\\nDRIVER"
            elif node.status == "missing":
                lbl = f"{node.label}\\nNOT FOUND"
            else:
                lbl = node.label
            lines.append(f'    {safe_id}["{lbl}"]:::{node.status}')

        lines.append('')

        # Edges
        for edge in graph.edges:
            from_id = re.sub(r"[^A-Za-z0-9_]", "_", edge.from_id)
            to_id   = re.sub(r"[^A-Za-z0-9_]", "_", edge.to_id)
            opcodes = " | ".join(edge.call_types)
            chunks  = ", ".join(edge.from_chunks)
            if edge.to_status == "missing":
                lines.append(f'    {from_id} -.->|"{opcodes}\\n{chunks}"| {to_id}')
            else:
                lines.append(f'    {from_id} -->|"{opcodes}\\n{chunks}"| {to_id}')

        lines.append('')
        lines.append('    classDef driver  fill:#2E86AB,color:#fff,stroke:#1a5276')
        lines.append('    classDef present fill:#27AE60,color:#fff,stroke:#1e8449')
        lines.append('    classDef missing fill:#E74C3C,color:#fff,stroke:#922b21,stroke-dasharray:5 5')

        return '\n'.join(lines) + '\n'
