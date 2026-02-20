* ================================================================
* AUDIT  –  Payroll Audit Trail Writer Subroutine
* ================================================================
*
* Called by: MAINPROG  (L R15,=V(AUDIT))
*            REPORT    (GO AUDIT)
*            FORMAT    (GO AUDIT)
* Calls:     (none – leaf subroutine)
*
* Function:
*   Writes a time-stamped audit record to the AUDITLOG VSAM
*   ESDS (Entry-Sequenced Data Set).  Each record captures:
*     - Timestamp  (date YYYYMMDD + time HHMMSSTH)
*     - Program ID (MAINPROG)
*     - Calling module (from AUDITMOD field)
*     - Employee ID (EMPLID)
*     - Action code (AUDITACT: 'V'=Validate, 'P'=Process,
*                    'R'=Report, 'F'=Format, 'W'=Write)
*     - Net pay amount (EMNPAY)
*     - Status  ('OK' or 'ER')
*
*   The AUDITLOG is opened at program start and closed at end.
*   Records are written sequentially (ESDS PUT).
*
* Entry:
*   AUDITMOD  CL8  – module that triggered the audit call
*   AUDITACT  CL1  – action code character
*   EMPLID    CL8  – current employee identifier
*   EMNPAY    PL8  – net pay (for financial audit)
*   ERRFLAG   X    – X'00'=OK, X'FF'=error
* ================================================================
*
AUDIT    IN
         STM   R14,R12,12(R13)
         BALR  R12,0
         USING *,R12
         ST    R13,AUDSAVE+4
         LA    R13,AUDSAVE
*
* ---- Get current timestamp ----------------------------------
         TIME  DEC                 Get date+time in packed decimal
         ST    R0,AUDTIMEW         Time  00HHMMSSTH packed
         ST    R1,AUDDATEW         Date  00YYDDDFF  packed
*
* ---- Build the audit record ---------------------------------
         MVC   AUDREC,=CL100' '   Clear the record buffer
*
* ---- Date YYYYMMDD (convert Julian to Gregorian) ------------
         ZAP   AUDJDATE,AUDDATEW  Load Julian date
         CVD   R1,AUDCVDW          Convert to packed for editing
         UNPK  AUDDATE(7),AUDCVDW+4(4)
         OI    AUDDATE+6,X'F0'
         MVC   AUDREC+0(8),AUDDATE
*
* ---- Time HHMMSSTH ----------------------------------------
         UNPK  AUDTIME(9),AUDTIMEW(5)
         OI    AUDTIME+8,X'F0'
         MVC   AUDREC+8(8),AUDTIME
*
* ---- Program ID, calling module, employee, action -----------
         MVC   AUDREC+16(8),=CL8'MAINPROG'
         MVC   AUDREC+24(8),AUDITMOD
         MVC   AUDREC+32(8),EMPLID
         MVC   AUDREC+40(1),AUDITACT
*
* ---- Net pay amount (for financial audit integrity) ---------
         MVC   AUDREC+41(8),EMNPAY
*
* ---- Status code -------------------------------------------
         CLI   ERRFLAG,X'FF'       Is there an active error?
         BE    AUDSTERR
         MVC   AUDREC+49(2),=CL2'OK'
         B     AUDWRIT
AUDSTERR DS    0H
         MVC   AUDREC+49(2),=CL2'ER'
*
* ---- Write to AUDITLOG VSAM ESDS ---------------------------
AUDWRIT  DS    0H
         TM    AUDLOG+48,X'10'     Is AUDITLOG open?
         BZ    AUDCLOSED           No – skip write silently
         PUT   RPL=AUDWRPL         Sequential PUT to ESDS
         LTR   R15,R15
         BNZ   AUDFAIL             Write failed – bump error count
         LA    R4,1
         A     R4,AUDWRCTR
         ST    R4,AUDWRCTR         Increment write counter
         B     AUDEXIT
*
AUDFAIL  DS    0H
         LA    R4,1
         A     R4,AUDERRCTR
         ST    R4,AUDERRCTR        Increment error counter
*
AUDCLOSED DS   0H
* ---- Exit --------------------------------------------------
AUDEXIT  DS    0H
         L     R13,AUDSAVE+4
         LM    R14,R12,12(R13)
         XR    R15,R15
         BR    R14
         OUT
*
* ---- Local working storage ---------------------------------
AUDSAVE  DC    18F'0'
AUDTIMEW DC    F'0'               Raw time word
AUDDATEW DC    F'0'               Raw date word (Julian)
AUDCVDW  DC    D'0'               CVD work doubleword
AUDJDATE DC    PL4'0'             Julian date work field
AUDDATE  DC    CL8' '             Formatted date YYYYMMDD
AUDTIME  DC    CL9' '             Formatted time HHMMSSTH
AUDREC   DC    CL100' '           Audit record buffer
*
* ---- Shared audit-control fields ---------------------------
AUDITMOD DC    CL8' '             Calling-module name (caller sets)
AUDITACT DC    CL1'?'             Action code         (caller sets)
AUDWRCTR DC    F'0'               Total successful writes this run
AUDERRCTR DC   F'0'               Total write errors  this run
*
* ---- VSAM RPL for sequential PUT to ESDS ------------------
AUDWRPL  RPL   ACB=AUDLOG,AREA=AUDREC,AREALEN=100,                    X
               OPTCD=(SEQ,SYN,ADR)
*
AUDLOG   ACB   DDNAME=AUDITLOG,MACRF=(SEQ,ADR),STRNO=1
*
         LTORG
