* CHUNK : HLASM_ROOT
* TYPE  : CSECT
* SOURCE: tests/fixtures/go_in_inline.hlasm
* DEPS  : VALIDATE, TRANSFM, CLEANUP, EXTPROG1
*──────────────────────────────────────────────────────────────────
CSECT
BALR  12,0              Establish base register
USING *,12
MVC   WRKNAME,=CL20' '     Clear name field
MVI   WRKFLAG,X'00'        Clear flag
GO    VALIDATE
GO    TRANSFM
TM    WRKFLAG,X'01'
GOIF  CLEANUP
GO    EXTPROG1
BR    14
