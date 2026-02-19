* CHUNK : FMTLINE
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/RPTWRITE
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,FLSAVE+4
LA    13,FLSAVE
MVC   OUTBUFF,=CL133' '         Clear line
MVC   OUTBUFF+1(8),EMPREC       Employee ID (cols 2-9)
MVC   OUTBUFF+10(20),EMPREC+8   Employee name (cols 11-30)
CVD   3,FLWORK
MVC   OUTBUFF+40(12),=X'402020206B2020206B202060'
ED    OUTBUFF+40(12),FLWORK+3
L     3,NETPAY
CVD   3,FLWORK
MVC   OUTBUFF+55(12),=X'402020206B2020206B202060'
ED    OUTBUFF+55(12),FLWORK+3
AH    0,LINENO                   Increment line counter
STH   0,LINENO
L     13,FLSAVE+4
LM    14,12,12(13)
BR    14
