* CHUNK : CALCBASE
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/programs/PAYROLL.asm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,CBSAVE+4
LA    13,CBSAVE
L     2,0(1)           Load hours-worked field
M     2,=F'1000'       Multiply by hourly rate (cents)
ST    3,BASEPAY        Store base pay result
MVI   PAYFLAG,X'01'   Mark pay calculated
L     13,CBSAVE+4
LM    14,12,12(13)
BR    14
