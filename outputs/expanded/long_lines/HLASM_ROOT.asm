* CHUNK : HLASM_ROOT
* TYPE  : CSECT
* SOURCE: tests/fixtures/long_lines.hlasm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
CSECT
STM   14,12,12(13)     Save all registers
BALR  12,0             Establish addressability
USING *,12
BR    14               Return
END   LONGPROG
