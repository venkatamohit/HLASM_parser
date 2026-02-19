* CHUNK : VALOK
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/go_in_inline.hlasm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
DS    0H
L     13,VALSAVE+4
LM    14,12,12(13)
BR    14
