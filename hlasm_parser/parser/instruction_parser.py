"""
InstructionParser
=================

Parses a single HLASM instruction text (with the 8-char label zone already
stripped) into a :class:`~hlasm_parser.models.ParsedInstruction`.

HLASM instruction format (after label-zone removal):
  ``  OPCODE  OPERAND1,OPERAND2,...  [remarks / comment]``

Operand parsing handles:
  * Nested parentheses: ``D(B)``, ``D(X,B,L)``, ``(R2,R3)``
  * Character / hex literals: ``C'TEXT'``, ``X'FF'``, ``B'1010'``
  * Self-defining terms with parens: ``=A(LABEL)``, ``=F'4'``
  * Arithmetic sub-expressions: ``LENGTH-1``, ``FIELD+4``
  * The first unquoted, non-parenthesised space terminates the operand list;
    anything after that is the *remarks* field.

Instruction type classification:

+----------------+----------------------------------------------------------+
| Type           | Representative opcodes                                   |
+================+==========================================================+
| BRANCH         | B BC BE BNE BH BL BM BNH BNL BNZ BZ BO BNO BP BNP      |
|                | BR J JC JE JNE JH JL JNH JNL JZ JNZ JO JNO JM JNM JP   |
|                | JNP NOP NOPR                                             |
+----------------+----------------------------------------------------------+
| CALL           | BAL BALR BAS BASR CALL LINK XCTL GO GOIF GOIFNOT       |
+----------------+----------------------------------------------------------+
| SECTION        | CSECT DSECT RSECT COM LOCTR START                        |
+----------------+----------------------------------------------------------+
| DATA           | DC DS DXD EQU ORG LTORG DROP USING END ENTRY EXTRN      |
+----------------+----------------------------------------------------------+
| MACRO_CTRL     | MACRO MEND MEXIT MNOTE COPY AREAD ANOP AGO AIF ACTR     |
|                | GBLA GBLB GBLC LCLA LCLB LCLC SETA SETB SETC            |
+----------------+----------------------------------------------------------+
| COMMENT        | Lines starting with ``*``                                |
+----------------+----------------------------------------------------------+
| INSTRUCTION    | Everything else                                          |
+----------------+----------------------------------------------------------+
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

from ..models import ParsedInstruction

# ---------------------------------------------------------------------------
# Opcode classification sets
# ---------------------------------------------------------------------------

BRANCH_OPCODES: Set[str] = {
    "B", "BC", "BCT", "BCTR",
    "BE", "BNE", "BH", "BL", "BNH", "BNL",
    "BZ", "BNZ", "BO", "BNO", "BM", "BNM", "BP", "BNP",
    "BR",
    "J", "JC", "JE", "JNE", "JH", "JL", "JNH", "JNL",
    "JZ", "JNZ", "JO", "JNO", "JM", "JNM", "JP", "JNP",
    "NOP", "NOPR",
    "BCR",
    "BXH", "BXLE",
}

CALL_OPCODES: Set[str] = {
    "BAL", "BALR", "BAS", "BASR",
    "CALL", "LINK", "XCTL",
    # Shop-specific branch-and-link macro family
    "GO", "GOIF", "GOIFNOT", "GOEQ", "GONE", "GOGT", "GOLT", "GOGE", "GOLE",
}

# Subroutine / function entry-point marker opcodes.
# ``<label>  IN`` marks where a named subroutine body begins.
# ``<label>  OUT`` (or ``RETURN``) marks normal exit.
ENTRY_MARKER_OPCODES: Set[str] = {
    "IN",
    "OUT",
}

SECTION_OPCODES: Set[str] = {
    "CSECT", "DSECT", "RSECT", "COM", "LOCTR", "START",
}

DATA_OPCODES: Set[str] = {
    "DC", "DS", "DXD",
    "EQU",
    "ORG", "LTORG",
    "DROP", "USING",
    "END",
    "ENTRY", "EXTRN", "WXTRN",
    "PRINT", "PUNCH", "TITLE", "SPACE", "EJECT",
    "PUSH", "POP",
    "REPRO",
}

MACRO_CTRL_OPCODES: Set[str] = {
    "MACRO", "MEND", "MEXIT", "MNOTE",
    "COPY", "AREAD", "ACTR", "ANOP",
    "AGO", "AIF", "AINSERT",
    "GBLA", "GBLB", "GBLC",
    "LCLA", "LCLB", "LCLC",
    "SETA", "SETB", "SETC",
}


def _classify(opcode: Optional[str]) -> str:
    if not opcode:
        return "EMPTY"
    op = opcode.upper()
    if op in BRANCH_OPCODES:
        return "BRANCH"
    if op in CALL_OPCODES:
        return "CALL"
    if op in ENTRY_MARKER_OPCODES:
        return "ENTRY_MARKER"
    if op in SECTION_OPCODES:
        return "SECTION"
    if op in DATA_OPCODES:
        return "DATA"
    if op in MACRO_CTRL_OPCODES:
        return "MACRO_CTRL"
    return "INSTRUCTION"


# ---------------------------------------------------------------------------
# Parser class
# ---------------------------------------------------------------------------


class InstructionParser:
    """
    Stateless parser that converts a raw HLASM instruction string (label zone
    already removed) into a :class:`ParsedInstruction`.
    """

    def parse(self, text: str, label: Optional[str] = None) -> ParsedInstruction:
        """
        Parse *text* (the portion of an HLASM line after the 8-char label zone)
        into a :class:`ParsedInstruction`.

        Parameters
        ----------
        text:
            The instruction text, e.g. ``"STM   14,12,12(13)"`` or
            ``"B     LOOP"`` or ``"DC    C'HELLO'"``
        label:
            The label taken from the label zone (cols 1-8), if any.

        Returns
        -------
        ParsedInstruction
        """
        stripped = text.strip()

        if not stripped:
            return ParsedInstruction(
                label=label,
                opcode=None,
                operands=[],
                comment=None,
                raw_text=text,
                instruction_type="EMPTY",
            )

        # Comment line (should normally be caught upstream, but handle here too)
        if stripped.startswith("*"):
            return ParsedInstruction(
                label=label,
                opcode=None,
                operands=[],
                comment=stripped[1:].strip(),
                raw_text=text,
                instruction_type="COMMENT",
            )

        opcode, operands_str, comment = self._split_fields(stripped)
        operands = self._parse_operands(operands_str) if operands_str else []

        return ParsedInstruction(
            label=label,
            opcode=opcode,
            operands=operands,
            comment=comment,
            raw_text=text,
            instruction_type=_classify(opcode),
        )

    # ------------------------------------------------------------------
    # Field splitting
    # ------------------------------------------------------------------

    def _split_fields(
        self, text: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Split ``text`` into ``(opcode, operands, comment)``.

        The *opcode* is the first whitespace-delimited token.
        The *operands* string ends at the first unquoted space that is not
        inside parentheses.  Anything after that is the *comment* (remarks).
        """
        parts = text.split(None, 1)
        opcode = parts[0].upper()

        if len(parts) == 1:
            return opcode, None, None

        rest = parts[1]
        op_end = self._find_operands_end(rest)
        operands_str = rest[:op_end].strip() or None
        comment = rest[op_end:].strip() or None
        return opcode, operands_str, comment

    @staticmethod
    def _find_operands_end(text: str) -> int:
        """
        Return the index in *text* where the operands field ends (i.e. the
        position of the first unquoted, non-parenthesised space character).
        """
        in_quote = False
        quote_char: Optional[str] = None
        depth = 0

        for i, ch in enumerate(text):
            if in_quote:
                if ch == quote_char:
                    in_quote = False
            elif ch in ("'", '"'):
                in_quote = True
                quote_char = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(depth - 1, 0)
            elif ch == " " and depth == 0:
                return i

        return len(text)

    # ------------------------------------------------------------------
    # Operand splitting
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_operands(operands_str: str) -> List[str]:
        """
        Split a comma-delimited operand string into individual operands,
        respecting nested parentheses and quoted strings.

        Examples
        --------
        >>> InstructionParser._parse_operands("14,12,12(13)")
        ['14', '12', '12(13)']
        >>> InstructionParser._parse_operands("C'HELLO,WORLD',80")
        ["C'HELLO,WORLD'", '80']
        """
        operands: List[str] = []
        current: List[str] = []
        in_quote = False
        quote_char: Optional[str] = None
        depth = 0

        for ch in operands_str:
            if in_quote:
                current.append(ch)
                if ch == quote_char:
                    in_quote = False
            elif ch in ("'", '"'):
                in_quote = True
                quote_char = ch
                current.append(ch)
            elif ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth = max(depth - 1, 0)
                current.append(ch)
            elif ch == "," and depth == 0:
                token = "".join(current).strip()
                if token:
                    operands.append(token)
                current = []
            else:
                current.append(ch)

        last = "".join(current).strip()
        if last:
            operands.append(last)

        return operands
