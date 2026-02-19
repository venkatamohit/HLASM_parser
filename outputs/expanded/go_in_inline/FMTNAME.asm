* CHUNK : FMTNAME
* TYPE  : ENTRY
* SOURCE: tests/fixtures/go_in_inline.hlasm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,FNSAVE+4
LA    13,FNSAVE
TR    WRKNAME,UPRTAB      Translate to uppercase
L     13,FNSAVE+4
LM    14,12,12(13)
BR    14
