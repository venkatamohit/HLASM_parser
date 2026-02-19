* CHUNK : CLEANUP
* TYPE  : ENTRY
* SOURCE: tests/fixtures/go_in_inline.hlasm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,CLSAVE+4
LA    13,CLSAVE
MVC   WRKBUFF,=CL80' '   Clear output buffer
MVC   WRKNAME,=CL20' '   Clear name
MVI   WRKFLAG,X'00'      Clear flag
L     13,CLSAVE+4
LM    14,12,12(13)
BR    14
