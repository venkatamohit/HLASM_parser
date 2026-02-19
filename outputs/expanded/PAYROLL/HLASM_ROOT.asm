* CHUNK : HLASM_ROOT
* TYPE  : CSECT
* SOURCE: tests/fixtures/programs/PAYROLL.asm
* DEPS  : INITWS, VALIDATE, CALCBASE, TAXCALC, DEDUCTNS, PRTREORT, RPTWRITE
*──────────────────────────────────────────────────────────────────
CSECT
STM   14,12,12(13)     Save all registers
BALR  12,0             Establish base register
USING *,12
ST    13,PAYSAVE+4     Chain save areas
LA    13,PAYSAVE
GO    INITWS
GO    VALIDATE
LA    1,EMPREC         Load employee record address
BAL   14,CALCBASE
GO    TAXCALC
GO    DEDUCTNS
LA    1,OUTBUFF        Load output buffer address
BAL   14,PRTREORT
GO    RPTWRITE
L     13,PAYSAVE+4
LM    14,12,12(13)
BR    14
