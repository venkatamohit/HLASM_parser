"""
Standard HLASM mnemonic / directive set.

Used by :class:`~hlasm_parser.pipeline.extract_blocks.ExtractBlocksTask` to
prevent genuine assembler instructions from being treated as macro calls during
the :class:`~hlasm_parser.passes.macro_expansion.MacroExpansionParsePass`.
"""
from __future__ import annotations

STANDARD_MNEMONICS: frozenset[str] = frozenset(
    {
        # ── Machine instructions (z/Architecture) ────────────────────────
        "A", "AH", "AHY", "AL", "ALC", "ALCR", "ALFI", "ALGFI", "ALG",
        "ALGR", "ALSI", "ALGSI", "ALR", "ALSIH", "AR", "AGR", "AGFI", "AGH",
        "AY",
        "B", "BAL", "BALR", "BAS", "BASR", "BC", "BCR", "BCT", "BCTR",
        "BE", "BH", "BL", "BM", "BNE", "BNH", "BNL", "BNM", "BNO", "BNP",
        "BNZ", "BO", "BP", "BR", "BXH", "BXLE", "BZ",
        "C", "CH", "CHY", "CL", "CLC", "CLCL", "CLCLE", "CLI", "CLIY",
        "CLM", "CLMY", "CLST", "CLR", "CLY", "CR", "CS", "CDS", "CDSG",
        "CSG", "CSY", "CY", "CGIT", "CGIJNE",
        "D", "DR", "DP",
        "EX", "EXRL",
        "IC", "ICM", "ICMY", "IILH", "IILL", "IIHL", "IIHH", "IIHF", "IILF",
        "J", "JC", "JE", "JH", "JL", "JM", "JNE", "JNH", "JNL", "JNM",
        "JNO", "JNP", "JNZ", "JO", "JP", "JZ",
        "L", "LA", "LAM", "LAY", "LB", "LBR", "LCR", "LCGR", "LDR",
        "LH", "LHI", "LHR", "LHRL", "LHY", "LGBR", "LGDR", "LGFR", "LGHI",
        "LGR", "LGRL", "LLC", "LLCR", "LLH", "LLHR", "LM", "LMH", "LMY",
        "LNR", "LPR", "LR", "LRL", "LT", "LTR", "LY",
        "M", "MH", "MHI", "MR", "MS", "MSR", "MSY", "MVC", "MVCL", "MVCLE",
        "MVCLU", "MVI", "MVIY", "MVN", "MVO", "MVZ", "MVST",
        "N", "NC", "NI", "NIY", "NR", "NY", "NOP", "NOPR",
        "O", "OC", "OI", "OIY", "OR", "OY",
        "PACK",
        "S", "SH", "SHY", "SL", "SLA", "SLDA", "SLDL", "SLL", "SLFI",
        "SLGFI", "SLR", "SR", "SRA", "SRDA", "SRDL", "SRL", "ST", "STC",
        "STCM", "STCMY", "STH", "STHY", "STM", "STMH", "STMY", "STY", "SY",
        "T", "TM", "TMH", "TML", "TMY", "TR", "TRT",
        "UNPK", "UNPKU",
        "X", "XC", "XI", "XIY", "XR", "XY",
        "ZAP",
        # ── Privileged / system instructions ─────────────────────────────
        "DIAG", "LCTL", "PTLB", "SSCH", "STCK", "STCKF", "STCTL",
        "STSCH", "SVC", "TIME",
        # ── Assembler directives / pseudo-ops ────────────────────────────
        "CSECT", "DSECT", "RSECT", "COM", "LOCTR", "START",
        "DC", "DS", "DXD",
        "EQU",
        "USING", "DROP",
        "ORG", "LTORG",
        "END",
        "ENTRY", "EXTRN", "WXTRN",
        "COPY",
        "MACRO", "MEND", "MEXIT", "MNOTE",
        "AREAD", "ACTR", "ANOP",
        "AGO", "AIF", "AINSERT",
        "GBLA", "GBLB", "GBLC",
        "LCLA", "LCLB", "LCLC",
        "SETA", "SETB", "SETC",
        "PRINT", "PUNCH", "TITLE", "SPACE", "EJECT",
        "PUSH", "POP",
        "REPRO",
        # ── Common IBM system macros (OS/390 / z/OS) ─────────────────────
        "WTO", "WTOR",
        "GETMAIN", "FREEMAIN", "STORAGE",
        "CALL", "LINK", "XCTL", "LOAD", "DELETE", "IDENTIFY",
        "OPEN", "CLOSE", "GET", "PUT", "READ", "WRITE", "CHECK", "POINT",
        "NOTE", "BLDL", "FIND",
        "POST", "WAIT",
        "ATTACH", "DETACH",
        "STIMER", "TTIMER",
        "ENQ", "DEQ", "RESERVE",
        "ABEND", "SNAP", "SETRP",
        "TIME",
        "MODESET",
        "SAVE", "RETURN",
        "RDJFCB", "SETPRT",
        "FREEBUF", "GETBUF",
        "MODCB", "SHOWCB", "TESTCB",
        "IKJDYNP",
        # ── Shop-specific GO / IN subroutine-call convention ─────────────
        # GO target   – branch-and-link to a named subroutine
        # GOIF/GOIFNOT/GOEQ/GONE/… – conditional variants of GO
        # IN          – subroutine entry-point marker  (<label> IN)
        # OUT         – subroutine exit marker         (<label> OUT)
        "GO", "GOIF", "GOIFNOT",
        "GOEQ", "GONE", "GOGT", "GOLT", "GOGE", "GOLE",
        "IN", "OUT",
    }
)
