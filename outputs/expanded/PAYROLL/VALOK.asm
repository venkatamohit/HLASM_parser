* CHUNK : VALOK
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/programs/PAYROLL.asm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
DS    0H
L     13,VLSAVE+4
LM    14,12,12(13)
BR    14
