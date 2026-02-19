* CHUNK : EXTPROG1
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/EXTPROG1.asm
* DEPS  : EXTPROG2
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,EP1SAVE+4
LA    13,EP1SAVE
MVC   EXTBUFF,=CL80'EXTPROG1 WAS HERE'
GO    EXTPROG2
L     13,EP1SAVE+4
LM    14,12,12(13)
BR    14
