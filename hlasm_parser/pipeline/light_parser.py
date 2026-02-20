"""Light Parser – extract a line-range "main" block and recursively resolve
GO and L (Link) subroutine targets via IN / OUT markers.

Flow
----
1. Extract lines [start_line, end_line] from the driver file  →  ``main.txt``.
2. Scan those lines for call instructions:
     * ``GO <name>`` / ``GOIF <name>`` / ``GOIFNOT <name>``
     * ``L Rx,=V(name)``  V-type address constant (primary Link form).
     * ``L <name>``  plain Link where the operand is a bare identifier.
3. For each *name*, search the driver + every file under *deps_dir* for a
   block delimited by ``<name>  IN`` … ``OUT`` (or the next ``IN`` marker).
4. Save each found block as ``<name>.txt`` in *output_dir* and recurse (BFS).
5. Expose the parent→children flow map via :meth:`to_json`, :meth:`to_dot`,
   and :meth:`to_mermaid`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

# GO / GOIF / GOIFNOT – first operand is always the target subroutine name
_GO_RE = re.compile(r"\bGO(?:IF(?:NOT)?)?\s+(\w+)", re.IGNORECASE)

# L Rx,=V(SUBNAME) – the primary Link form: load an external subroutine
# address via a V-type address constant, e.g.  L     R15,=V(EXTSUB)
_V_LINK_RE = re.compile(r"^\s+L\s+\w+\s*,\s*=V\((\w+)\)", re.IGNORECASE)

# L <name> as a plain Link call (no register / no comma).
#   • Leading whitespace  →  L is in opcode column, not label column.
#   • Operand is a plain HLASM identifier (letters/digits/@/#/$, 1–8 chars).
#   • Nothing else on the line (no comma / parenthesis = not a Load-register).
_LINK_RE = re.compile(
    r"^\s+L\s+([A-Za-z@#$][A-Za-z0-9@#$]{0,7})\s*(?:\*.*)?$",
    re.IGNORECASE,
)

# Register aliases R0–R15 that would otherwise look like plain Link targets.
_REGISTER_RE = re.compile(r"^R(?:1[0-5]|[0-9])$", re.IGNORECASE)

# Matches OUT in opcode position (with optional leading label or spaces)
_OUT_RE = re.compile(r"^\s*(?:\w+\s+)?OUT\b", re.IGNORECASE)

# Matches the start of *any* IN block (used as a fallback stop condition)
_ANY_IN_RE = re.compile(r"^\w+\s+IN\b", re.IGNORECASE)


def _in_pattern(name: str) -> re.Pattern[str]:
    """Return a compiled pattern that matches ``<name>  IN`` at line start."""
    return re.compile(rf"^{re.escape(name)}\s+IN\b", re.IGNORECASE)


class LightParser:
    """Lightweight subroutine extractor driven by GO / L / IN / OUT markers.

    Parameters
    ----------
    driver_path:
        Primary HLASM source file that contains (or calls) the main flow.
    deps_dir:
        Directory (searched recursively) for external subroutine files.
        Pass ``None`` to search only *driver_path*.
    output_dir:
        Folder where extracted ``.txt`` chunk files are written.
    """

    def __init__(
        self,
        driver_path: str | Path,
        deps_dir: str | Path | None,
        output_dir: str | Path,
    ) -> None:
        self.driver_path = Path(driver_path)
        self.deps_dir = Path(deps_dir) if deps_dir else None
        self.output_dir = Path(output_dir)

        # name → raw source lines
        self.chunks: dict[str, list[str]] = {}
        # name → ordered list of child names
        self.flow: dict[str, list[str]] = {}
        # names that could not be located in any search file
        self.missing: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, start_line: int, end_line: int) -> None:
        """Extract the main block then recursively resolve all GO and L targets.

        Parameters
        ----------
        start_line / end_line:
            1-indexed, inclusive line numbers within *driver_path*.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        main_lines = self._extract_range(self.driver_path, start_line, end_line)
        self._save_chunk("main", main_lines)
        self.flow["main"] = []

        queue: list[tuple[str, list[str]]] = [("main", main_lines)]
        visited: set[str] = {"main"}

        while queue:
            parent, lines = queue.pop(0)
            for target in self._find_go_targets(lines):
                if target not in self.flow[parent]:
                    self.flow[parent].append(target)
                if target in visited:
                    continue
                visited.add(target)

                sub_lines = self._find_subroutine(target)
                self.flow.setdefault(target, [])
                if sub_lines is None:
                    self.missing.append(target)
                else:
                    self._save_chunk(target, sub_lines)
                    queue.append((target, sub_lines))

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """Return a serialisable dict describing the extracted flow."""
        return {
            "entry": "main",
            "flow": self.flow,
            "chunk_line_counts": {n: len(ls) for n, ls in self.chunks.items()},
            "missing": self.missing,
        }

    def to_json_str(self) -> str:
        return json.dumps(self.to_json(), indent=2)

    def to_dot(self) -> str:
        """Return a Graphviz DOT string for the subroutine call graph."""
        missing_set = set(self.missing)
        lines = [
            "digraph LightParserCFG {",
            "  rankdir=TB;",
            '  node [shape=box fontname="Courier"];',
        ]
        for name in self.flow:
            colour = "red" if name in missing_set else "lightblue"
            lines.append(f'  "{name}" [style=filled fillcolor={colour}];')
        for parent, children in self.flow.items():
            for child in children:
                lines.append(f'  "{parent}" -> "{child}";')
        lines.append("}")
        return "\n".join(lines)

    def to_mermaid(self) -> str:
        """Return a Mermaid flowchart string."""
        lines = ["flowchart TD"]
        for parent, children in self.flow.items():
            for child in children:
                lines.append(f"  {parent} --> {child}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_range(path: Path, start: int, end: int) -> list[str]:
        """Return lines *start*–*end* (1-indexed, inclusive) from *path*."""
        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return all_lines[max(0, start - 1): end]

    @staticmethod
    def _find_go_targets(lines: list[str]) -> list[str]:
        """Return subroutine names called via GO or L in *lines* (order preserved).

        Handles:
        * ``GO <name>`` / ``GOIF <name>`` / ``GOIFNOT <name>``
        * ``L <name>``  where the operand is a plain identifier (Link call),
          distinguished from the Load-register opcode by the absence of a
          comma or parenthesis in the operand field.  Register aliases R0–R15
          are excluded to avoid false positives.
        """
        seen: set[str] = set()
        targets: list[str] = []

        def _add(name: str) -> None:
            name = name.upper()
            if name not in seen:
                seen.add(name)
                targets.append(name)

        for line in lines:
            if line.startswith("*"):   # full-line comment
                continue
            # GO / GOIF / GOIFNOT
            for m in _GO_RE.finditer(line):
                _add(m.group(1))
            # L Rx,=V(SUBNAME) – V-type address constant Link (primary form)
            m = _V_LINK_RE.match(line)
            if m:
                _add(m.group(1))
                continue   # already handled this line
            # L <name> – plain Link (no register, no comma)
            m = _LINK_RE.match(line)
            if m and not _REGISTER_RE.match(m.group(1)):
                _add(m.group(1))

        return targets

    def _search_files(self) -> Iterator[Path]:
        """Yield driver file first, then every file under *deps_dir*."""
        yield self.driver_path
        if self.deps_dir and self.deps_dir.is_dir():
            for f in sorted(self.deps_dir.rglob("*")):
                if f.is_file():
                    yield f

    def _find_subroutine(self, name: str) -> list[str] | None:
        """Search all source files for a ``<name>  IN … OUT`` block.

        Returns the lines of the block (inclusive of the IN line and the OUT
        line), or ``None`` if *name* is not found anywhere.
        """
        in_re = _in_pattern(name)
        for f in self._search_files():
            try:
                all_lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(all_lines):
                if not in_re.match(line):
                    continue
                block = [line]
                for j in range(i + 1, len(all_lines)):
                    next_line = all_lines[j]
                    block.append(next_line)
                    if _OUT_RE.match(next_line):
                        return block          # normal end: OUT found
                    # Fallback: stop before the next IN block starts
                    if _ANY_IN_RE.match(next_line):
                        block.pop()           # don't include the next IN header
                        return block
                return block                  # EOF without OUT or next IN
        return None

    def _save_chunk(self, name: str, lines: list[str]) -> None:
        self.chunks[name] = lines
        (self.output_dir / f"{name}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
