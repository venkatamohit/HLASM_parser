* CHUNK : TAXCALC
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/TAXCALC
* DEPS  : TAXHI, TAXAPPLY
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,TCSAVE+4
LA    13,TCSAVE
L     2,BASEPAY        Load gross pay
C     2,=F'50000'      Compare with low threshold
BH    TAXHI            Branch if high earner
MVC   TAXRATE,=F'20'   20% standard rate
B     TAXAPPLY
