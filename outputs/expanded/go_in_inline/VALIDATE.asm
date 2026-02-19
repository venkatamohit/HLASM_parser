* CHUNK : VALIDATE
* TYPE  : ENTRY
* SOURCE: tests/fixtures/go_in_inline.hlasm
* DEPS  : VALERR, EXTPROG3, VALOK
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)     Save registers
BALR  12,0
USING *,12
ST    13,VALSAVE+4
LA    13,VALSAVE
CLC   WRKNAME,=CL20' '    Check if name is blank
BE    VALERR               Branch if blank
MVI   WRKFLAG,X'01'       Set "valid" flag
GO    EXTPROG3
B     VALOK
