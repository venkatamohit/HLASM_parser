* ================================================================
* MAINPROG  –  Employee Payroll Processing System  –  Main Driver
* ================================================================
*
* Overview
* --------
* This program controls the end-to-end payroll processing cycle
* for a batch run.  It reads an input file of employee records,
* validates each record, runs payroll calculations, converts
* currency amounts to a printable format, writes an audit trail,
* and finally generates a printed payroll summary report.
*
* Main flow (lines 59-115):
*   GO    VALIDATE       Validate each employee record
*   GO    PROCESS        Run payroll calculations
*   GO    REPORT         Generate report lines
*   GOIF  ERRHANDLE      Conditional branch on error
*   L     R15,=V(CONVERT) Link-call: currency conversion module
*   L     R15,=V(AUDIT)   Link-call: audit trail writer
*
* Register conventions
* --------------------
*   R12  Base register (established at entry)
*   R13  Save-area pointer
*   R14  Return address
*   R15  External link register / subroutine return code
*   R1   Parameter list pointer
*   R2-R10  Work registers
* ================================================================
*
MAINPROG CSECT
         BALR  R12,0              Establish base register
         USING *,R12              Tell assembler about base
* ---- Initialise save area ----------------------------------------
         ST    R14,MWSAVE+4       Save caller's R14
         LA    R13,MWSAVE         Point R13 to our save area
* ---- Clear all working fields ------------------------------------
         MVI   ERRFLAG,X'00'      Clear error indicator
         MVI   RPTFLAG,X'01'      Enable report generation
         MVI   RETCODE,X'00'      Clear return code byte
         MVC   CUREMPL,=CL8' '    Clear current employee ID
         MVC   PAYPER, =CL6' '    Clear pay-period field
         ZAP   TOTGROSS,=P'0'     Zero gross-pay accumulator
         ZAP   TOTNPAY, =P'0'     Zero net-pay accumulator
         ZAP   TOTTAX,  =P'0'     Zero tax accumulator
         ZAP   TOTDED,  =P'0'     Zero deductions accumulator
* ---- Open files --------------------------------------------------
         OPEN  (EMPFILE,(INPUT),PAYFILE,(OUTPUT),RPTFILE,(OUTPUT))
         LTR   R15,R15            Test open return code
         BNZ   OPENERR            Non-zero means open failed
* ---- Read first record -------------------------------------------
         GET   EMPFILE,INREC      Read first employee record
         LTR   R15,R15            Check read status
         BNZ   MAINEOF            Branch if no records
*
* ================================================================
* MAIN PROCESSING LOOP  (start-line=59  end-line=115)
* ================================================================
MAINLOOP DS    0H                 Top of main loop
*
* Step 1 – Validate the incoming employee record
         GO    VALIDATE            Validate data; sets ERRFLAG
         CLI   ERRFLAG,X'FF'      Did validation detect an error?
         BE    ERRHANDLE          Yes – handle it and skip to next
*
* Step 2 – Run payroll calculations for this employee
         GO    PROCESS             Calc gross, tax, deductions, net
         CLI   ERRFLAG,X'FF'      Did processing encounter an error?
         BE    ERRHANDLE          Yes – handle it
*
* Step 3 – Convert monetary amounts to printable packed/zoned form
         L     R15,=V(CONVERT)    Load address of CONVERT module
         BALR  R14,R15            Link-call to CONVERT
*
* Step 4 – Write audit record for this transaction
         L     R15,=V(AUDIT)      Load address of AUDIT module
         BALR  R14,R15            Link-call to AUDIT
*
* Step 5 – Generate report line if reporting is active
         TM    RPTFLAG,X'01'      Is reporting switched on?
         BO    DORPT              Yes – generate a report line
         B     ACCTOTL            No  – skip report generation
DORPT    DS    0H
         GO    REPORT              Write a report detail line
*
* Step 6 – Accumulate run totals
ACCTOTL  DS    0H
         AP    TOTGROSS,EMGROSS   Add this employee's gross pay
         AP    TOTNPAY, EMNPAY    Add net pay
         AP    TOTTAX,  EMTAX     Add tax
         AP    TOTDED,  EMDED     Add deductions
*
* Step 7 – Read next record and loop or exit
         GET   EMPFILE,INREC      Read next employee record
         LTR   R15,R15
         BZ    MAINLOOP           More records – go round again
         B     MAINEOF            End of input
*
* ================================================================
* Error handler – called via GOIF from within the loop
* ================================================================
ERRHANDLE DS   0H
         MVI   RETCODE,X'08'      Mark as error run
         L     R15,=V(ERRORS)     Link to the error handler module
         BALR  R14,R15
         MVI   ERRFLAG,X'00'      Reset flag and continue
         B     ACCTOTL            Rejoin main flow after error
*
* ================================================================
* End-of-file – write totals report and close files
* ================================================================
MAINEOF  DS    0H
         GO    REPORT              Write summary totals report
         CLOSE (EMPFILE,,PAYFILE,,RPTFILE)
         B     MAINEND
*
OPENERR  DS    0H
         MVI   RETCODE,X'12'      File-open failure return code
*
* ================================================================
* Program exit
* ================================================================
MAINEND  DS    0H
         L     R13,MWSAVE+4       Restore caller's save pointer
         LM    R14,R12,12(R13)    Restore all caller registers
         XR    R15,R15            Set return code 0
         BR    R14                Return to operating system
*
* ================================================================
* Working-storage data areas
* ================================================================
MWSAVE   DC    18F'0'             Standard 72-byte save area
ERRFLAG  DC    X'00'              Error flag  (FF = error)
RPTFLAG  DC    X'01'              Report flag (01 = active)
RETCODE  DC    X'00'              Program return code
*
CUREMPL  DC    CL8' '             Current employee identifier
PAYPER   DC    CL6' '             Pay period  YYYYMM
*
TOTGROSS DC    PL8'0'             Run total – gross pay
TOTNPAY  DC    PL8'0'             Run total – net pay
TOTTAX   DC    PL8'0'             Run total – tax
TOTDED   DC    PL8'0'             Run total – deductions
*
* ================================================================
* Employee input record layout  (200 bytes)
* ================================================================
INREC    DS    0CL200
EMPLID   DS    CL8                Employee identifier
EMPLNM   DS    CL30               Full name
EMPLDPT  DS    CL4                Department code
EMPLGRD  DS    CL2                Pay grade (01-20)
EMPLTYP  DS    CL1                Employment type (F/P/T)
EMPLTAX  DS    CL1                Tax status  (S/M/X)
EMPLHRS  DS    PL4                Hours worked this period (packed)
EMPLRAT  DS    PL6                Hourly rate (packed, 2 dec)
EMPLSAL  DS    PL8                Annual salary (packed, 2 dec)
EMPLFIL  DS    CL136              Filler to 200 bytes
*
* ================================================================
* Pay-detail fields shared between subroutines
* ================================================================
EMGROSS  DC    PL8'0'             This employee's gross pay
EMNPAY   DC    PL8'0'             This employee's net pay
EMTAX    DC    PL8'0'             This employee's tax
EMDED    DC    PL8'0'             This employee's total deductions
EMFED    DC    PL8'0'             Federal tax portion
EMSTATE  DC    PL8'0'             State tax portion
EMHINS   DC    PL8'0'             Health insurance deduction
EMRET    DC    PL8'0'             Retirement deduction
*
* ================================================================
* Print / output work areas
* ================================================================
PRTLINE  DC    CL133' '           Printer output line buffer
PRTCTL   DC    CL1'1'             ANSI carriage-control character
PRTDATA  DC    CL132' '           Printable data portion
*
* ================================================================
* Equates
* ================================================================
R1       EQU   1
R2       EQU   2
R3       EQU   3
R4       EQU   4
R5       EQU   5
R6       EQU   6
R7       EQU   7
R8       EQU   8
R9       EQU   9
R10      EQU   10
R11      EQU   11
R12      EQU   12
R13      EQU   13
R14      EQU   14
R15      EQU   15
*
* ================================================================
* File DCBs
* ================================================================
EMPFILE  DCB   DDNAME=EMPFILE,MACRF=GM,DSORG=PS,EODAD=MAINEOF,       X
               LRECL=200,BLKSIZE=2000,RECFM=FB
PAYFILE  DCB   DDNAME=PAYFILE,MACRF=PM,DSORG=PS,                      X
               LRECL=200,BLKSIZE=2000,RECFM=FB
RPTFILE  DCB   DDNAME=RPTFILE,MACRF=PM,DSORG=PS,                      X
               LRECL=133,BLKSIZE=1330,RECFM=FBA
*
         LTORG
         END   MAINPROG
