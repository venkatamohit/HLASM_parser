* CHUNK : HLASM_ROOT
* TYPE  : CSECT
* SOURCE: tests/fixtures/sample_dsect.hlasm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
PROGRAM WITH DSECT AND CSECT
multiple section types, DSECT mapping
CSECT
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,PMSVAREA+4
LA    13,PMSVAREA
orage for work area and map it with DSECT
LA    2,WORKAREA
USING WORKMAPD,2
MVC   WRK_NAME,=CL20'DEFAULT NAME'
MVI   WRK_FLAG,X'01'
L     13,PMSVAREA+4
LM    14,12,12(13)
BR    14
