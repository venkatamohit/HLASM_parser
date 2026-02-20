* ================================================================
* FORMAT  –  Monetary Amount Formatter Subroutine
* ================================================================
*
* Called by: PROCESS  (GO FORMAT)
*            REPORT   (GO FORMAT)
* Calls:     GO    AUDIT           Record formatting activity
*
* Function:
*   Converts packed-decimal monetary amounts held in the shared
*   fields (EMGROSS, EMNPAY, EMTAX, EMDED) into printable
*   edited character strings with comma insertion, decimal point,
*   and CR notation for negative values.
*
*   Input fields (packed decimal, 2 implied decimal places):
*     EMGROSS, EMNPAY, EMTAX, EMDED, EMFED, EMSTATE
*
*   Output fields (character, 14 bytes each):
*     FMTGRSS, FMTNPAY, FMTTAX, FMTDED, FMTFED, FMTSTATE
*
*   Edit mask used: X'402020206B2020206B202021204B2020'
*     Produces: ZZZ,ZZZ,ZZ9.99 (with leading-zero suppression)
*
* ================================================================
*
FORMAT   IN
         STM   R14,R12,12(R13)
         BALR  R12,0
         USING *,R12
         ST    R13,FMSAVE+4
         LA    R13,FMSAVE
*
* ---- Gross pay -----------------------------------------------
         MVC   FMTGRSS,FMMASK14   Load edit mask
         ED    FMTGRSS,EMGROSS     Edit gross pay
         TM    EMGROSS+7,X'0D'     Is it negative (packed sign D)?
         BNO   FMGGPOS             No – skip CR notation
         MVC   FMTGRSS+12(2),=C'CR'  Append credit notation
FMGGPOS  DS    0H
*
* ---- Net pay -------------------------------------------------
         MVC   FMTNPAY,FMMASK14
         ED    FMTNPAY,EMNPAY
         TM    EMNPAY+7,X'0D'
         BNO   FMNPPOS
         MVC   FMTNPAY+12(2),=C'CR'
FMNPPOS  DS    0H
*
* ---- Total tax -----------------------------------------------
         MVC   FMTTAX,FMMASK14
         ED    FMTTAX,EMTAX
         TM    EMTAX+7,X'0D'
         BNO   FMTXPOS
         MVC   FMTTAX+12(2),=C'CR'
FMTXPOS  DS    0H
*
* ---- Total deductions ----------------------------------------
         MVC   FMTDED,FMMASK14
         ED    FMTDED,EMDED
         TM    EMDED+7,X'0D'
         BNO   FMDEDPS
         MVC   FMTDED+12(2),=C'CR'
FMDEDPS  DS    0H
*
* ---- Federal tax ---------------------------------------------
         MVC   FMTFED,FMMASK14
         ED    FMTFED,EMFED
*
* ---- State tax -----------------------------------------------
         MVC   FMTSTATE,FMMASK14
         ED    FMTSTATE,EMSTATE
*
* ---- Format today's date and time for the report header ------
         TIME  BIN                 Get current time/date (R0=time, R1=date)
         ST    R0,FMTIMEW          Store time word
         ST    R1,FMDATEW          Store date word
*        Convert Julian date (R1) to Gregorian MMDDYYYY
         CVD   R1,FMDBLDW          Convert to packed decimal
         UNPK  FMTDATE(7),FMDBLDW+4(4)
         OI    FMTDATE+6,X'F0'     Fix zone of last byte
*
* ---- Audit this formatting operation ------------------------
         GO    AUDIT               Record that FORMAT was called
*
* ---- Exit ---------------------------------------------------
FMEXIT   DS    0H
         L     R13,FMSAVE+4
         LM    R14,R12,12(R13)
         BR    R14
         OUT
*
* ---- Local working storage ---------------------------------
FMSAVE   DC    18F'0'
FMTIMEW  DC    F'0'               Raw time word from TIME macro
FMDATEW  DC    F'0'               Raw date word from TIME macro
FMDBLDW  DC    D'0'               Doubleword for CVD
*
* ---- Edit masks --------------------------------------------
FMMASK14 DC    X'402020206B2020206B202021204B2020'
*                                  Format: ZZZ,ZZZ,ZZ9.99
*
* ---- Formatted output fields (written by this subroutine) --
FMTGRSS  DC    CL14' '            Formatted gross pay
FMTNPAY  DC    CL14' '            Formatted net pay
FMTTAX   DC    CL14' '            Formatted total tax
FMTDED   DC    CL14' '            Formatted total deductions
FMTFED   DC    CL14' '            Formatted federal tax
FMTSTATE DC    CL14' '            Formatted state tax
FMTDATE  DC    CL8' '             Formatted date  MMDDYYYY
FMTIME   DC    CL6' '             Formatted time  HHMMSS
FMWORK   DC    CL80' '            General work area
*
         LTORG
