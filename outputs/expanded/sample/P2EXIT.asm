* CHUNK : P2EXIT
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/sample.hlasm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
DS    0H
L     13,P2SAVE+4
LM    14,12,12(13)
BR    14
