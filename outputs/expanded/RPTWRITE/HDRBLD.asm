* CHUNK : HDRBLD
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/programs/RPTWRITE
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,HBSAVE+4
LA    13,HBSAVE
MVC   0(133,1),=CL133' '        Clear header line
MVC   1(30,1),=CL30'PAYROLL REGISTER'
AH    0,PAGENO                   Increment page number
STH   0,PAGENO
CVD   0,CVTWORK
MVC   120(5,1),=X'4020202120'
ED    120(5,1),CVTWORK+6        Edit page number
MVC   115(5,1),=CL5'PAGE:'
L     13,HBSAVE+4
LM    14,12,12(13)
BR    14
