* CHUNK : APPLYRT
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/TAXCALC
* DEPS  : (none)
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,ARSAVE+4
LA    13,ARSAVE
L     2,BASEPAY        Load gross pay
M     2,TAXRATE        Multiply by rate
D     2,=F'100'        Divide by 100 (get percentage)
ST    3,TAXAMT         Store tax amount
L     13,ARSAVE+4
LM    14,12,12(13)
BR    14
