* ================================================================
* REPORT  –  Payroll Report Generation Subroutine
* ================================================================
*
* Called by: MAINPROG  (GO REPORT)
* Calls:     GO    FORMAT          Format amounts for printing
*            GO    AUDIT           Write report-generation audit
*
* Function:
*   Builds and writes one or more lines to the payroll summary
*   report.  On each employee pass it writes a detail line.
*   On the end-of-file pass it writes subtotal and grand-total
*   lines.  Every report write triggers an audit entry.
*
*   Report line format (133 bytes, ANSI carriage control):
*     Pos 1     : ANSI carriage-control character
*     Pos 2-9   : Employee ID
*     Pos 11-40 : Employee name
*     Pos 42-47 : Department code / grade
*     Pos 49-62 : Gross pay (edited ZZZ,ZZZ,ZZ9.99-)
*     Pos 64-77 : Tax amount (edited)
*     Pos 79-92 : Deductions (edited)
*     Pos 94-107: Net pay (edited)
*     Pos 109-132: Remarks / period info
* ================================================================
*
REPORT   IN
         STM   R14,R12,12(R13)
         BALR  R12,0
         USING *,R12
         ST    R13,RPSAVE+4
         LA    R13,RPSAVE
*
* ---- Determine which type of report line to produce ----------
         CLI   EMPLID,C' '        Is employee ID blank?
         BE    RPTTOTAL           Yes – produce totals line
*
* ---- Detail line --------------------------------------------
         MVC   PRTCTL,=C'0'       Double-space before line
         MVC   PRTDATA,=CL132' '  Clear print line
*
* ---- Format all monetary amounts ---------------------------
         GO    FORMAT              Invoke the formatter
*
* ---- Fill employee detail fields ---------------------------
         MVC   PRTDATA+0(8),EMPLID
         MVC   PRTDATA+10(30),EMPLNM
         MVC   PRTDATA+41(4),EMPLDPT
         MVC   PRTDATA+46(2),EMPLGRD
*
* ---- Move formatted monetary fields into print line --------
         MVC   PRTDATA+48(14),FMTGRSS    Formatted gross pay
         MVC   PRTDATA+63(14),FMTTAX     Formatted tax
         MVC   PRTDATA+78(14),FMTDED     Formatted deductions
         MVC   PRTDATA+93(14),FMTNPAY    Formatted net pay
*
* ---- Write the detail line ---------------------------------
         PUT   RPTFILE,PRTLINE
*
* ---- Record this report event in the audit trail -----------
         GO    AUDIT               Write report-generated audit
*
         B     RPEXIT
*
* ---- Totals line --------------------------------------------
RPTTOTAL DS    0H
         MVC   PRTCTL,=C'1'       Page eject before totals
         MVC   PRTDATA,=CL132' '
         MVC   PRTDATA+0(20),=CL20'*** PAYROLL TOTALS **'
*
* ---- Format the run totals ---------------------------------
         ZAP   EMGROSS,TOTGROSS    Copy total to shared field
         ZAP   EMNPAY, TOTNPAY
         ZAP   EMTAX,  TOTTAX
         ZAP   EMDED,  TOTDED
         GO    FORMAT              Format the totals
*
         MVC   PRTDATA+48(14),FMTGRSS
         MVC   PRTDATA+63(14),FMTTAX
         MVC   PRTDATA+78(14),FMTDED
         MVC   PRTDATA+93(14),FMTNPAY
*
         PUT   RPTFILE,PRTLINE
*
* ---- Audit the end-of-run report ---------------------------
         GO    AUDIT               Audit the totals report write
*
* ---- Exit ---------------------------------------------------
RPEXIT   DS    0H
         L     R13,RPSAVE+4
         LM    R14,R12,12(R13)
         BR    R14
         OUT
*
* ---- Local working storage ----------------------------------
RPSAVE   DC    18F'0'
RPWORK   DC    CL80' '            Work area
RPFLAG   DC    X'00'              Report-type flag
RPLINNO  DC    H'0'               Current line number on page
RPPAGNO  DC    H'1'               Current page number
RPMAXLN  DC    H'55'              Maximum lines per page
*
* ---- Formatted output fields (populated by FORMAT) ----------
FMTGRSS  DC    CL14' '            Formatted gross pay
FMTTAX   DC    CL14' '            Formatted tax amount
FMTDED   DC    CL14' '            Formatted deductions
FMTNPAY  DC    CL14' '            Formatted net pay
FMTDATE  DC    CL8' '             Formatted date MMDDYYYY
FMTTIME  DC    CL6' '             Formatted time HHMMSS
*
* ---- Report headings ----------------------------------------
RPTHDR1  DC    CL133'1'
         ORG   RPTHDR1+1
         DC    CL40'         MAINPROG PAYROLL REPORT        '
         DC    CL40'         PAY PERIOD:                    '
         DC    CL52' '
         ORG
*
RPTHDR2  DC    CL133' '
         ORG   RPTHDR2+1
         DC    CL8'EMP-ID  '
         DC    CL2' '
         DC    CL30'NAME                          '
         DC    CL2' '
         DC    CL14'GROSS PAY     '
         DC    CL2' '
         DC    CL14'TAX           '
         DC    CL2' '
         DC    CL14'DEDUCTIONS    '
         DC    CL2' '
         DC    CL14'NET PAY       '
         ORG
*
         LTORG
