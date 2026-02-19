* CHUNK : PROCESS1
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/sample.hlasm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,P1SAVE+4
LA    13,P1SAVE
MVC   OUTBUFF,INPUTPARM   Copy input to output
LA    0,OUTBUFF
LA    1,80
L     13,P1SAVE+4
LM    14,12,12(13)
BR    14
