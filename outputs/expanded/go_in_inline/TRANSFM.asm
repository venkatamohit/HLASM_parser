* CHUNK : TRANSFM
* TYPE  : ENTRY
* SOURCE: tests/fixtures/go_in_inline.hlasm
* DEPS  : FMTNAME
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,TRSAVE+4
LA    13,TRSAVE
GO    FMTNAME
MVC   WRKBUFF,WRKNAME     Copy to output buffer
L     13,TRSAVE+4
LM    14,12,12(13)
BR    14
