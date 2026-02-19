* CHUNK : TAXAPPLY
* TYPE  : SUBROUTINE
* SOURCE: tests/fixtures/programs/TAXCALC
* DEPS  : APPLYRT, DEDUCTNS
*──────────────────────────────────────────────────────────────────
DS    0H
GO    APPLYRT
GO    DEDUCTNS
L     3,BASEPAY
S     3,TAXAMT
S     3,DEDAMT
ST    3,NETPAY
L     13,TCSAVE+4
LM    14,12,12(13)
BR    14
