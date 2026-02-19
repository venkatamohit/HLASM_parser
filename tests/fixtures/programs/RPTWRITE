* ============================================================
* RPTWRITE – Report-writer module
*
* Entry point:  RPTWRITE  IN
*
* Inline subroutine (GO/IN style):
*   FMTLINE   – format a single report detail line
*
* Inline subroutine (classic BAL style):
*   HDRBLD    – build report page header
*
* External dependency (GO → separate file):
*   TAXCALC   – re-verify tax figures before printing
*
* Called from: PAYROLL (main driver)
* ============================================================
RPTWRITE IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,RWSAVE+4
         LA    13,RWSAVE
*
* Build page header using classic BAL subroutine
         LA    1,HDRBUFF        Load header buffer address
         BAL   14,HDRBLD
*
* Verify tax figures are current (external module)
         GO    TAXCALC
*
* Format and write the detail line
         GO    FMTLINE
*
* Write output record (PUT macro placeholder)
         MVC   OUTREC,OUTBUFF   Move formatted line to output
*
         L     13,RWSAVE+4
         LM    14,12,12(13)
         BR    14
*
* ── Data areas ───────────────────────────────────────────────
RWSAVE   DC    18F'0'
HDRBUFF  DS    CL133            Page header line (ASA)
OUTREC   DS    CL133            Final output record
PAGENO   DC    H'0'             Current page number
LINENO   DC    H'0'             Current line number
*
* ============================================================
* HDRBLD – build the report page header (classic BAL sub)
* Called with R1 → header buffer (133 bytes)
* ============================================================
HDRBLD   STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,HBSAVE+4
         LA    13,HBSAVE
*
         MVC   0(133,1),=CL133' '        Clear header line
         MVC   1(30,1),=CL30'PAYROLL REGISTER'
         AH    0,PAGENO                   Increment page number
         STH   0,PAGENO
         CVD   0,CVTWORK
         MVC   120(5,1),=X'4020202120'
         ED    120(5,1),CVTWORK+6        Edit page number
         MVC   115(5,1),=CL5'PAGE:'
*
         L     13,HBSAVE+4
         LM    14,12,12(13)
         BR    14
*
HBSAVE   DC    18F'0'
CVTWORK  DS    D
*
* ============================================================
* FMTLINE – format one detail line (GO/IN subroutine)
* ============================================================
FMTLINE  IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,FLSAVE+4
         LA    13,FLSAVE
*
* Clear output line then fill each field
         MVC   OUTBUFF,=CL133' '         Clear line
         MVC   OUTBUFF+1(8),EMPREC       Employee ID (cols 2-9)
         MVC   OUTBUFF+10(20),EMPREC+8   Employee name (cols 11-30)
*
* Format base pay amount
         CVD   3,FLWORK
         MVC   OUTBUFF+40(12),=X'402020206B2020206B202060'
         ED    OUTBUFF+40(12),FLWORK+3
*
* Format net pay amount
         L     3,NETPAY
         CVD   3,FLWORK
         MVC   OUTBUFF+55(12),=X'402020206B2020206B202060'
         ED    OUTBUFF+55(12),FLWORK+3
*
         AH    0,LINENO                   Increment line counter
         STH   0,LINENO
*
         L     13,FLSAVE+4
         LM    14,12,12(13)
         BR    14
*
FLSAVE   DC    18F'0'
FLWORK   DS    D
*
         END   RPTWRITE
