"""
HLASMCopybookProcessor
======================

Reads a macro copybook file and performs parameter substitution.

Copybook file format (IBM HLASM macro definition):
  Line 0 : ``         MACRO``              (MACRO directive)
  Line 1 : ``[&LABEL]   MACRONAME  [&PARAM1[,&PARAM2 …]]``
                                           (prototype / header line)
  Lines 2+: Macro body (may reference &PARAM1, &PARAM2, … by name)
  Last line: ``         MEND``             (end of macro)

The processor:
  1. Reads the copybook file.
  2. Extracts parameter names from the prototype line (line index 1) using
     the pattern ``&\\w+``.
  3. Substitutes actual values supplied by the macro call into every body line.
  4. Re-applies the 72-column truncation after substitution.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from .discard_after_72 import DiscardAfter72Pass

logger = logging.getLogger(__name__)

_PARAM_RE = re.compile(r"&\w+")


class HLASMCopybookProcessor:
    """
    Expands a single macro by substituting actual parameters into the
    copybook body.

    This is a direct Python port of tape-z's ``HLASMCopybookProcessor.java``.
    """

    def run(
        self,
        macro_path: Path,
        macro_details: List[str],
    ) -> Optional[List[str]]:
        """
        Load and expand a macro copybook.

        Parameters
        ----------
        macro_path:
            Path to the ``<MACRONAME>_Assembler_Copybook.txt`` file.
        macro_details:
            Tokens split from the macro call line.  ``macro_details[0]`` is
            the macro name (or label); ``macro_details[1]`` (if present) is
            the raw comma-separated operand string, e.g. ``"P1,P2,P3"``.

        Returns
        -------
        List[str] | None
            Expanded source lines (truncated to 72 columns), or *None* on
            I/O error.
        """
        try:
            raw = macro_path.read_text(encoding="utf-8", errors="replace")
            lines: List[str] = raw.splitlines()
        except OSError as exc:
            logger.error("Failed to read copybook %s: %s", macro_path, exc)
            return None

        if len(lines) < 2:
            logger.debug("Copybook too short (%d lines): %s", len(lines), macro_path)
            return lines

        logger.debug("Processing macro copybook: %s", macro_path)

        # -- Extract formal parameter names from the prototype line (index 1) --
        formal_params: List[str] = _PARAM_RE.findall(lines[1])

        if not formal_params:
            logger.debug("No substitutable parameters found in %s", macro_path)
            return DiscardAfter72Pass().run(lines)

        # -- Parse actual parameter values from the call site ----------------
        if len(macro_details) >= 2:
            raw_values = macro_details[1].split(",")
            actual_values = [v.strip() for v in raw_values]
        else:
            actual_values = []

        # Pad actual values so every formal param has a (possibly empty) value
        while len(actual_values) < len(formal_params):
            actual_values.append("")

        logger.debug(
            "Parameter mapping for %s: %s",
            macro_path,
            list(zip(formal_params, actual_values)),
        )

        # -- Perform substitution in all lines --------------------------------
        result = list(lines)
        for param, value in zip(formal_params, actual_values):
            result = [line.replace(param, value) for line in result]

        logger.debug("Completed substitution for '%s'", macro_path)
        return DiscardAfter72Pass().run(result)
