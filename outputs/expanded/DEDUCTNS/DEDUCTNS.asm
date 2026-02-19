* CHUNK : DEDUCTNS
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/DEDUCTNS
* DEPS  : HLTHDED, RETIRE
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,DDSAVE+4
LA    13,DDSAVE
XC    DEDAMT,DEDAMT        Zero deduction accumulator
GO    HLTHDED
GO    RETIRE
L     13,DDSAVE+4
LM    14,12,12(13)
BR    14
