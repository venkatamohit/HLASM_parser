"""Light Parser – extract a line-range "main" block and recursively resolve
GO, L, and macro-based targets via IN / OUT markers.

Flow
----
1. Extract lines [start_line, end_line] from the driver file  →  ``main.txt``.
2. Scan those lines for call instructions:
     * ``GO <name>`` / ``GOIF <name>`` / ``GOIFNOT <name>``
     * ``L Rx,=V(name)``  V-type address constant (primary Link form).
     * ``L <name>``  plain Link where the operand is a bare identifier.
     * Macro invocations resolved from discovered ``MACRO ... MEND`` blocks.
3. For each *name*, search the driver + every file under *deps_dir* for a
   block delimited by ``<name>  IN`` … ``OUT`` (or the next ``IN`` marker).
   If no IN/OUT block is found, fall back to a ``<name>  EQU  *`` table
   (common for dispatch/translation anchors).  The EQU *
   block extends until the next labeled statement in the source.
4. Save each found block as ``<name>.txt`` in *output_dir* and recurse (BFS).
5. Expose the parent→children flow map via :meth:`to_json`, :meth:`to_dot`,
   and :meth:`to_mermaid`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# GO / GOIF / GOIFNOT in opcode position.
# Anchored to line start so that "go" appearing inside an inline comment
# (e.g. "... More records – go round again") is never matched.
# Accepts:  <label> GO ... or (spaces) GO ...
_GO_RE = re.compile(
    r"^(?:[A-Za-z@#$]\S{0,7}\s+|\s+)GO(?:IF(?:NOT)?)?\s+(\w+)",
    re.IGNORECASE,
)

# L Rx,=V(SUBNAME) / L Rx,=A(SUBNAME) – load callable address constant.
_V_LINK_RE = re.compile(r"^\s+L\s+\w+\s*,\s*=(?:V|A)\((\w+)\)", re.IGNORECASE)

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

# Matches ``NAME  EQU  *`` – translation/dispatch table anchor.
# Used as a fallback chunk boundary when no IN/OUT block exists for a name.
_EQU_STAR_RE_TEMPLATE = r"^{name}\s+EQU\s+\*"
_MACRO_START_RE = re.compile(r"^\s*(?:[A-Za-z@#$]\S{0,7}\s+)?MACRO\b", re.IGNORECASE)
_MEND_RE = re.compile(r"^\s*(?:[A-Za-z@#$]\S{0,7}\s+)?MEND\b", re.IGNORECASE)
_EJECT_RE = re.compile(r"^\s*(?:[A-Za-z@#$]\S{0,7}\s+)?EJECT\b", re.IGNORECASE)

# Generic dispatch-style macro pattern with a target as the 3rd operand.
# Example: FOO 05,0,TCR051,1002  ->  TCR051
_DISPATCH_STYLE_RE = re.compile(
    r"^[0-9]+$|^X'[0-9A-F]+'$|^C'.*'$",
    re.IGNORECASE,
)


def _in_pattern(name: str) -> re.Pattern[str]:
    """Return a compiled pattern that matches ``<name>  IN`` at line start."""
    return re.compile(rf"^{re.escape(name)}\s+IN\b", re.IGNORECASE)


@dataclass
class MacroDefinition:
    name: str
    source_file: str
    header_line: str
    parameters: list[str]
    lines: list[str]
    call_params: list[str]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_file": self.source_file,
            "header_line": self.header_line,
            "parameters": self.parameters,
            "call_params": self.call_params,
            "line_count": len(self.lines),
        }


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
        # macro name -> macro definition
        self.macros: dict[str, MacroDefinition] = {}
        # symbol aliases from EQU (e.g. VALUE EQU TCR051)
        self.equ_aliases: dict[str, str] = {}
        # nodes that represent macro chunks in the graph
        self.macro_nodes: set[str] = set()
        # node -> tags for serialised graph output
        self.node_tags: dict[str, list[str]] = {"main": ["entry"]}
        # node -> chunk kind (sub|macro)
        self.chunk_kinds: dict[str, str] = {"main": "sub"}

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
        self.macros = self._discover_macros()
        self.equ_aliases = self._discover_equ_aliases()
        self.macro_nodes = set(self.macros.keys())
        self._write_macro_chunks()

        main_lines = self._extract_range(self.driver_path, start_line, end_line)
        self._save_chunk("main", main_lines)
        self.flow["main"] = []

        queue: list[tuple[str, list[str]]] = [("main", main_lines)]
        visited: set[str] = {"main"}

        while queue:
            parent, lines = queue.pop(0)
            for macro_name, macro_targets in self._find_macro_calls(lines, self.macros):
                # Never create a self-referencing edge (macro body scanning
                # can see its own prototype line as an apparent invocation).
                if macro_name == parent:
                    continue
                if macro_name not in self.flow[parent]:
                    self.flow[parent].append(macro_name)
                self.flow.setdefault(macro_name, [])
                self.node_tags[macro_name] = ["macro"]
                self.chunk_kinds[macro_name] = "macro"
                if macro_name not in visited:
                    visited.add(macro_name)
                    queue.append((macro_name, self.macros[macro_name].lines))
                for target in macro_targets:
                    if target not in self.flow[macro_name]:
                        self.flow[macro_name].append(target)
                    self._resolve_target(target, visited, queue)

            for target in self._find_go_targets(
                lines, self.macros, include_known_macros=False
            ):
                if target not in self.flow[parent]:
                    self.flow[parent].append(target)
                self._resolve_target(target, visited, queue)

        self._write_macro_catalog()

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """Return a serialisable dict describing the extracted flow."""
        return {
            "entry": "main",
            "flow": self.flow,
            "chunk_line_counts": {n: len(ls) for n, ls in self.chunks.items()},
            "macro_catalog": [m.to_dict() for m in self.macros.values()],
            "node_tags": self.node_tags,
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
            if name in missing_set:
                colour = "red"
                shape = "box"
            elif name in self.macro_nodes:
                colour = "khaki"
                shape = "component"
            else:
                colour = "lightblue"
                shape = "box"
            lines.append(f'  "{name}" [style=filled fillcolor={colour} shape={shape}];')
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
        if self.macro_nodes:
            lines.append("  classDef macro fill:#f4e8a5,stroke:#7f6a00,stroke-width:1px;")
            for name in sorted(self.macro_nodes):
                if name in self.flow:
                    lines.append(f"  class {name} macro;")
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
    def _find_go_targets(
        lines: list[str],
        macro_catalog: dict[str, MacroDefinition] | None = None,
        *,
        include_known_macros: bool = True,
    ) -> list[str]:
        """Return subroutine names called via GO, L, or macro calls in *lines*.

        Handles:
        * ``GO <name>`` / ``GOIF <name>`` / ``GOIFNOT <name>``
        * ``L Rx,=V(<name>)``  V-type address constant Link (primary form).
        * ``L <name>``  plain Link where the operand is a bare identifier,
          distinguished from Load-register by the absence of a comma or
          parenthesis.  Register aliases R0–R15 are excluded.
        * macro calls discovered from ``MACRO`` definitions.
        * generic dispatch-style macro calls where the 3rd operand is symbolic.
        """
        seen: set[str] = set()
        targets: list[str] = []
        macro_catalog = macro_catalog or {}
        macro_names = set(macro_catalog.keys())

        def _add(name: str) -> None:
            name = name.upper()
            if name not in seen:
                seen.add(name)
                targets.append(name)

        for line in lines:
            if line.startswith("*"):   # full-line comment
                continue
            # GO / GOIF / GOIFNOT (opcode-position only – not inside comments)
            m = _GO_RE.match(line)
            if m:
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
            _, opcode, operand_field = LightParser._split_statement(line)
            if not opcode:
                continue
            op_u = opcode.upper()
            operands = LightParser._split_operands(operand_field)

            if include_known_macros and op_u in macro_names:
                for target in LightParser._targets_from_known_macro_call(
                    macro_catalog[op_u], operands
                ):
                    _add(target)
                continue

            for target in LightParser._targets_from_dispatch_style_macro(operands):
                _add(target)
            # EQU alias line: NAME EQU TARGET  -> follow TARGET in BFS
            if op_u == "EQU":
                alias_ops = LightParser._split_operands(operand_field)
                if alias_ops:
                    rhs = alias_ops[0].strip()
                    if rhs != "*" and LightParser._looks_symbolic(rhs):
                        _add(rhs)

        return targets

    @staticmethod
    def _find_macro_calls(
        lines: list[str], macro_catalog: dict[str, MacroDefinition]
    ) -> list[tuple[str, list[str]]]:
        out: list[tuple[str, list[str]]] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        macro_names = set(macro_catalog.keys())
        for line in lines:
            if line.startswith("*"):
                continue
            label, opcode, operand_field = LightParser._split_statement(line)
            if not opcode:
                continue
            # Skip macro prototype/header lines (label is a symbolic &-parameter).
            # These live inside the MACRO…MEND block itself and are not call sites.
            if label.startswith("&"):
                continue
            op_u = opcode.upper()
            if op_u not in macro_names:
                continue
            operands = LightParser._split_operands(operand_field)
            targets = LightParser._targets_from_known_macro_call(
                macro_catalog[op_u], operands
            )
            key = (op_u, tuple(targets))
            if key in seen:
                continue
            seen.add(key)
            out.append((op_u, targets))
        return out

    @staticmethod
    def _split_statement(line: str) -> tuple[str, str, str]:
        text = line.rstrip("\n")
        if not text or text.lstrip().startswith("*"):
            return "", "", ""
        body = text.split("*", 1)[0].rstrip()
        if not body:
            return "", "", ""
        parts = body.split()
        if not parts:
            return "", "", ""
        if text and text[0].isspace():
            opcode = parts[0]
            operands = body.split(opcode, 1)[1].strip() if len(parts) > 1 else ""
            return "", opcode, operands
        if len(parts) == 1:
            return parts[0], "", ""
        label = parts[0]
        opcode = parts[1]
        pos = body.find(opcode)
        operands = body[pos + len(opcode):].strip() if pos >= 0 else ""
        return label, opcode, operands

    @staticmethod
    def _split_operands(operand_text: str) -> list[str]:
        if not operand_text:
            return []
        out: list[str] = []
        cur: list[str] = []
        depth = 0
        quote: str | None = None
        for ch in operand_text:
            if quote:
                cur.append(ch)
                if ch == quote:
                    quote = None
                continue
            if ch in ("'", '"'):
                quote = ch
                cur.append(ch)
                continue
            if ch == "(":
                depth += 1
                cur.append(ch)
                continue
            if ch == ")":
                depth = max(0, depth - 1)
                cur.append(ch)
                continue
            if ch == "," and depth == 0:
                out.append("".join(cur).strip())
                cur = []
                continue
            cur.append(ch)
        if cur:
            out.append("".join(cur).strip())
        return [o for o in out if o]

    @staticmethod
    def _looks_symbolic(value: str) -> bool:
        v = value.strip().upper()
        if not v:
            return False
        if v.startswith("&"):
            return False
        if v.startswith("="):
            return False
        if "(" in v or ")" in v:
            return False
        if _REGISTER_RE.match(v):
            return False
        if _DISPATCH_STYLE_RE.match(v):
            return False
        return bool(re.fullmatch(r"[A-Z@#$][A-Z0-9@#$]{0,7}", v))

    @staticmethod
    def _targets_from_known_macro_call(
        macro: MacroDefinition, operands: list[str]
    ) -> list[str]:
        # Prefer explicit call-site parameter usage learned from macro body.
        by_param: dict[str, str] = {}
        for i, p in enumerate(macro.parameters):
            if i < len(operands):
                by_param[p.upper()] = operands[i].strip()
        out: list[str] = []
        for param in macro.call_params:
            actual = by_param.get(param.upper(), "")
            if LightParser._looks_symbolic(actual):
                out.append(actual.upper())
        if out:
            return list(dict.fromkeys(out))

        # Fallback for macros with no explicit GO/L pattern in body:
        # accept every symbolic operand from the call.
        generic = [o.upper() for o in operands if LightParser._looks_symbolic(o)]
        return list(dict.fromkeys(generic))

    @staticmethod
    def _targets_from_dispatch_style_macro(operands: list[str]) -> list[str]:
        # Generic fallback for macro-like table entries:
        # <num>,<num>,<symbol>,<num>  => treat 3rd arg as callee.
        if len(operands) < 4:
            return []
        first, second, third, fourth = [o.strip() for o in operands[:4]]
        if not first.isdigit() or not second.isdigit() or not fourth.isdigit():
            return []
        if not LightParser._looks_symbolic(third):
            return []
        return [third.upper()]

    def _search_files(self) -> Iterator[Path]:
        """Yield driver file first, then every file under *deps_dir*."""
        yield self.driver_path
        if self.deps_dir and self.deps_dir.is_dir():
            for f in sorted(self.deps_dir.rglob("*")):
                if f.is_file():
                    yield f

    def _discover_macros(self) -> dict[str, MacroDefinition]:
        macros: dict[str, MacroDefinition] = {}
        for src in self._search_files():
            try:
                lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            i = 0
            while i < len(lines):
                line = lines[i]
                if not _MACRO_START_RE.match(line):
                    i += 1
                    continue
                mend_idx = None
                for k in range(i + 1, len(lines)):
                    if _MEND_RE.match(lines[k]):
                        mend_idx = k
                        break
                # Not a macro definition block (likely an invocation-like line).
                if mend_idx is None:
                    i += 1
                    continue
                header_i = i
                name = ""
                operands = ""

                inline_name, inline_operands = self._parse_macro_header(line)
                if inline_name:
                    name = inline_name
                    operands = inline_operands
                else:
                    header_i = i + 1
                    while header_i < len(lines):
                        hdr = lines[header_i]
                        if hdr.strip() and not hdr.lstrip().startswith("*"):
                            break
                        header_i += 1
                    if header_i >= len(lines):
                        break
                    next_name, next_operands = self._parse_macro_header(lines[header_i])
                    if next_name:
                        name = next_name
                        operands = next_operands
                if not name:
                    i = header_i + 1
                    continue
                params = [
                    p.split("=", 1)[0].strip().upper()
                    for p in self._split_operands(operands)
                    if p.strip().startswith("&")
                ]
                block = lines[i: header_i + 1]
                j = header_i + 1
                while j < len(lines):
                    block.append(lines[j])
                    if _MEND_RE.match(lines[j]):
                        break
                    j += 1
                call_params = self._infer_macro_call_params(block, params)
                if name not in macros:
                    macros[name] = MacroDefinition(
                        name=name,
                        source_file=str(src),
                        header_line=lines[header_i],
                        parameters=params,
                        lines=block,
                        call_params=call_params,
                    )
                i = j + 1
        return macros

    def _parse_macro_header(self, line: str) -> tuple[str, str]:
        """Return (macro_name, operands_text) from a macro prototype/header line."""
        raw = line.rstrip()
        if not raw or raw.lstrip().startswith("*"):
            return "", ""
        header_body = raw.strip()
        parts = header_body.split()
        if not parts:
            return "", ""

        name_token = ""

        # Form A: line contains the MACRO keyword and then name, e.g.
        #   MACRO .* OPEN &P1,&P2
        #   MACRO &LBL OPEN &P1,&P2
        macro_idx = -1
        for idx, tok in enumerate(parts):
            if tok.upper() == "MACRO":
                macro_idx = idx
                break
        if macro_idx >= 0:
            for tok in parts[macro_idx + 1:]:
                t = tok.strip().rstrip(",")
                if not t or t.startswith("&"):
                    continue
                if re.fullmatch(r"[A-Za-z@#$][A-Za-z0-9@#$]{0,7}", t):
                    name_token = t
                    break
        else:
            # Form B: classic prototype after a standalone MACRO line:
            #   &LABEL OPEN &P1,&P2
            #   OPEN &P1,&P2
            if parts[0].startswith("&") and len(parts) >= 2:
                cand = parts[1]
            else:
                cand = parts[0]
            if re.fullmatch(r"[A-Za-z@#$][A-Za-z0-9@#$]{0,7}", cand):
                name_token = cand

        if not name_token:
            return "", ""

        name = name_token.strip().upper()
        if name_token in header_body:
            operands = header_body.split(name_token, 1)[1].strip()
        else:
            operands = ""
        return name, operands

    def _discover_equ_aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for src in self._search_files():
            try:
                lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                label, opcode, operands = self._split_statement(line)
                if not label or opcode.upper() != "EQU":
                    continue
                first = self._split_operands(operands)
                if not first:
                    continue
                rhs = first[0].strip().upper()
                if rhs == "*":
                    continue
                if not self._looks_symbolic(rhs):
                    continue
                aliases[label.upper()] = rhs
        return aliases

    def _resolve_equ_alias(self, name: str) -> str:
        cur = name.upper()
        seen: set[str] = set()
        while cur in self.equ_aliases and cur not in seen:
            seen.add(cur)
            nxt = self.equ_aliases[cur]
            if not nxt:
                break
            cur = nxt
        return cur

    def _infer_macro_call_params(
        self, macro_lines: list[str], formal_params: list[str]
    ) -> list[str]:
        wanted: list[str] = []
        formals = {p.upper() for p in formal_params}
        go_param_re = re.compile(
            r"^(?:[A-Za-z@#$]\S{0,7}\s+|\s+)GO(?:IF(?:NOT)?)?\s+(&[A-Za-z0-9@#$]+)",
            re.IGNORECASE,
        )
        v_param_re = re.compile(
            r"^\s+L\s+\w+\s*,\s*=V\((&[A-Za-z0-9@#$]+)\)",
            re.IGNORECASE,
        )
        l_param_re = re.compile(
            r"^\s+L\s+(&[A-Za-z0-9@#$]+)\s*(?:\*.*)?$",
            re.IGNORECASE,
        )
        for line in macro_lines:
            m = go_param_re.match(line)
            if m:
                key = m.group(1).strip().upper()
                if key in formals and key not in wanted:
                    wanted.append(key)
            m = v_param_re.match(line)
            if m:
                key = m.group(1).strip().upper()
                if key in formals and key not in wanted:
                    wanted.append(key)
            m = l_param_re.match(line)
            if m:
                key = m.group(1).strip().upper()
                if key in formals and key not in wanted:
                    wanted.append(key)
        return wanted

    def _write_macro_chunks(self) -> None:
        for macro in self.macros.values():
            self.chunk_kinds[macro.name] = "macro"
            self._save_chunk(macro.name, macro.lines, kind="macro")

    def _write_macro_catalog(self) -> None:
        payload = {
            "macro_count": len(self.macros),
            "macros": [m.to_dict() for m in self.macros.values()],
        }
        (self.output_dir / "macros.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def _find_subroutine(self, name: str) -> list[str] | None:
        """Search all source files for a ``<name>  IN … OUT`` block.

        If no IN/OUT block is found, falls back to a ``<name>  EQU ...``
        table/anchor block (common for dispatch tables).  The EQU block
        block ends immediately before the next labeled statement (a line
        whose first character is not a space, tab, or ``*``).

        Returns the lines of the block, or ``None`` if *name* is not found.
        """
        in_re = _in_pattern(name)
        equ_re = re.compile(
            rf"^{re.escape(name)}\s+EQU\b", re.IGNORECASE
        )
        equ_candidate: list[str] | None = None   # best EQU match seen so far

        for f in self._search_files():
            try:
                all_lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(all_lines):
                # Primary: IN / OUT block
                if in_re.match(line):
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

                # Secondary: EQU anchor block (kept as candidate; IN/OUT wins)
                if equ_candidate is None and equ_re.match(line):
                    _, op, operand_field = self._split_statement(line)
                    ops = self._split_operands(operand_field) if op.upper() == "EQU" else []
                    rhs = ops[0].strip().upper() if ops else ""
                    if rhs and rhs != "*":
                        # For alias-style EQU, capture only the EQU line.
                        equ_candidate = [line]
                        continue
                    block = [line]
                    for j in range(i + 1, len(all_lines)):
                        next_line = all_lines[j]
                        # Stop before the next labeled statement (non-blank col-1
                        # that is not a comment).  This is the natural end of
                        # an EQU * data table.
                        if next_line and next_line[0] not in (" ", "\t", "*"):
                            break
                        block.append(next_line)
                        if _EJECT_RE.match(next_line):
                            break
                    equ_candidate = block

        return equ_candidate  # None if neither form was found

    def _resolve_target(
        self,
        target: str,
        visited: set[str],
        queue: list[tuple[str, list[str]]],
    ) -> None:
        if target in visited:
            return
        visited.add(target)
        if target in self.macros:
            sub_lines = self.macros[target].lines
            self.node_tags[target] = ["macro"]
            self.chunk_kinds[target] = "macro"
        else:
            sub_lines = self._find_subroutine(target)
            self.chunk_kinds[target] = "sub"
        self.flow.setdefault(target, [])
        if sub_lines is None:
            self.missing.append(target)
            return
        self._save_chunk(target, sub_lines, kind=self.chunk_kinds.get(target, "sub"))
        queue.append((target, sub_lines))

    def _save_chunk(self, name: str, lines: list[str], kind: str = "sub") -> None:
        self.chunks[name] = lines
        (self.output_dir / f"{name}_{kind}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
