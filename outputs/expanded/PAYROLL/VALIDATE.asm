* CHUNK : VALIDATE
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/PAYROLL.asm
* DEPS  : VALERR, VALOK
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,VLSAVE+4
LA    13,VLSAVE
CLC   EMPREC(8),=CL8' '   Check if employee ID blank
BE    VALERR               Error if blank
CLC   EMPREC+8(4),=F'0'   Check hours > 0
BNH   VALERR               Error if zero or negative
MVI   PAYFLAG,X'02'        Mark record valid
B     VALOK
