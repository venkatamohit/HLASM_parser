* CHUNK : PRTREORT
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/programs/PAYROLL.asm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,PRSAVE+4
LA    13,PRSAVE
MVC   0(133,1),=CL133' '    Clear output line
MVC   1(80,1),EMPREC         Copy employee data
CVD   3,WORKDBL              Convert pay to packed
MVC   50(12,1),=X'402020206B2020206B202060'
ED    50(12,1),WORKDBL+3     Edit pay amount
L     13,PRSAVE+4
LM    14,12,12(13)
BR    14
