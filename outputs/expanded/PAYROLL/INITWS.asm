* CHUNK : INITWS
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/PAYROLL.asm
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,IWSAVE+4
LA    13,IWSAVE
MVC   EMPREC,=CL80' '      Clear employee record
MVC   OUTBUFF,=CL133' '    Clear output line
MVI   PAYFLAG,X'00'        Clear flags
XC    BASEPAY,BASEPAY      Zero base pay
XC    NETPAY,NETPAY        Zero net pay
L     13,IWSAVE+4
LM    14,12,12(13)
BR    14
