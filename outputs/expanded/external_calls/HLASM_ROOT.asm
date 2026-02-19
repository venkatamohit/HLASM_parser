* CHUNK : HLASM_ROOT
* TYPE  : CSECT
* SOURCE: tests/fixtures/external_calls.hlasm
* DEPS  : SUBPROG1, SUBPROG2, LOCALRTN
*──────────────────────────────────────────────────────────────────
CSECT
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,ECSAVE+4
LA    13,ECSAVE
LA    1,PARMLIST
CALL  SUBPROG1
LINK  EP=SUBPROG2
BAL   14,LOCALRTN
L     13,ECSAVE+4
LM    14,12,12(13)
BR    14
