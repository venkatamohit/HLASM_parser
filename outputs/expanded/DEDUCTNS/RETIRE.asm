* CHUNK : RETIRE
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/DEDUCTNS
* DEPS  : RTEXIT
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,RTSAVE+4
LA    13,RTSAVE
TM    PAYFLAG,X'02'    Check valid record flag
BNO   RTEXIT           Skip if not valid
L     2,BASEPAY        Load gross pay
M     2,=F'5'          Multiply by 5
D     2,=F'100'        Divide by 100
ST    3,RETAMT         Store retirement amount
A     3,DEDAMT         Add to total deductions
ST    3,DEDAMT         Store updated total
