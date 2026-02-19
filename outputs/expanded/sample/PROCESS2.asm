* CHUNK : PROCESS2
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/sample.hlasm
* DEPS  : P2MATCH, P2NOMATCH
*──────────────────────────────────────────────────────────────────
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,P2SAVE+4
LA    13,P2SAVE
CLC   INPUTPARM,=CL8'TESTDATA'
BE    P2MATCH              Branch if equal
B     P2NOMATCH            Branch if not equal
