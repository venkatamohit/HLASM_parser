* CHUNK : RPTWRITE
* TYPE  : ENTRY
* SOURCE: tests/fixtures/programs/RPTWRITE
* DEPS  : HDRBLD, TAXCALC, FMTLINE
*──────────────────────────────────────────────────────────────────
IN
STM   14,12,12(13)
BALR  12,0
USING *,12
ST    13,RWSAVE+4
LA    13,RWSAVE
LA    1,HDRBUFF        Load header buffer address
BAL   14,HDRBLD
GO    TAXCALC
GO    FMTLINE
MVC   OUTREC,OUTBUFF   Move formatted line to output
L     13,RWSAVE+4
LM    14,12,12(13)
BR    14
