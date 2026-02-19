* CHUNK : EXTPROG2
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/EXTPROG2.asm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,EP2SAVE+4
LA    13,EP2SAVE
MVI   EP2FLAG,X'01'      Signal completion
L     13,EP2SAVE+4
LM    14,12,12(13)
BR    14
