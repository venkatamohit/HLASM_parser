* CHUNK : HLTHDED
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/DEDUCTNS
* DEPS  : HHLTEXIT
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,HHSAVE+4
LA    13,HHSAVE
TM    PAYFLAG,X'02'    Check valid record flag
BNO   HHLTEXIT         Skip if record not valid
L     2,BASEPAY        Load gross pay
M     2,=F'3'          Multiply by 3
D     2,=F'100'        Divide by 100
ST    3,HLTAMT         Store health amount
A     3,DEDAMT         Add to total deductions
ST    3,DEDAMT         Store updated total
