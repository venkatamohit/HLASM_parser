* ================================================================
* PROCESS  –  Payroll Calculation Subroutine
* ================================================================
*
* Called by: MAINPROG  (GO PROCESS)
* Calls:     GO    FORMAT          Format calculated amounts
*            L     R15,=V(DBWRITE) Write pay detail to database
*            GOIF  ERRORS          Handle calculation error
*
* Function:
*   Performs all payroll arithmetic for one employee record:
*     1. Calculate gross pay (hourly or salaried)
*     2. Compute federal and state income tax
*     3. Calculate FICA (Social Security + Medicare)
*     4. Deduct health insurance and retirement contributions
*     5. Derive net pay = gross - all deductions
*     6. Format amounts and write the pay-detail database row
*
* Packed-decimal fields updated:
*   EMGROSS, EMTAX, EMFED, EMSTATE, EMHINS, EMRET, EMNPAY, EMDED
* ================================================================
*
PROCESS  IN
         STM   R14,R12,12(R13)    Save all registers
         BALR  R12,0
         USING *,R12
         ST    R13,PRSAVE+4
         LA    R13,PRSAVE
*
* ---- Step 1: Compute gross pay ---------------------------------
         CLI   EMPLTYP,C'F'       Full-time salaried?
         BE    PRSAL              Yes – use annual salary
         CLI   EMPLTYP,C'P'       Part-time hourly?
         BE    PRHRLY             Yes – use hourly rate
         CLI   EMPLTYP,C'T'       Temporary hourly?
         BE    PRHRLY
*
PRSAL    DS    0H                 Salaried calculation
         ZAP   EMGROSS,EMPLSAL    Start with annual salary
         DP    EMGROSS,=P'26'     Divide by 26 pay periods
         ZAP   EMGROSS,EMGROSS(8) Keep quotient only
         B     PRTAX
*
PRHRLY   DS    0H                 Hourly calculation
         ZAP   PRWORK1,EMPLHRS    Copy hours worked
         MP    PRWORK1,EMPLRAT    Multiply by hourly rate
         ZAP   EMGROSS,PRWORK1    Store as gross pay
*
* ---- Step 2: Compute federal income tax (simplified) ----------
PRTAX    DS    0H
         ZAP   EMFED,EMGROSS      Copy gross pay
         MP    EMFED,=P'22'       Apply 22% federal rate
         DP    EMFED,=P'100'      Divide by 100
         ZAP   EMFED,EMFED(8)     Keep quotient
*
* ---- Step 3: Compute state income tax (5%) --------------------
         ZAP   EMSTATE,EMGROSS
         MP    EMSTATE,=P'5'
         DP    EMSTATE,=P'100'
         ZAP   EMSTATE,EMSTATE(8)
*
* ---- Step 4: Compute FICA (7.65% employee share) --------------
         ZAP   PRFICA,EMGROSS
         MP    PRFICA,=P'765'
         DP    PRFICA,=P'10000'
         ZAP   PRFICA,PRFICA(8)
*
* ---- Step 5: Fixed deductions (health, retirement) ------------
         ZAP   EMHINS,=P'24500'   Health insurance flat $245.00
         ZAP   EMRET,EMGROSS      Retirement = 4% of gross
         MP    EMRET,=P'4'
         DP    EMRET,=P'100'
         ZAP   EMRET,EMRET(8)
*
* ---- Step 6: Compute totals and net pay -----------------------
         ZAP   EMTAX,EMFED
         AP    EMTAX,EMSTATE
         AP    EMTAX,PRFICA
*
         ZAP   EMDED,EMTAX
         AP    EMDED,EMHINS
         AP    EMDED,EMRET
*
         ZAP   EMNPAY,EMGROSS
         SP    EMNPAY,EMDED       Net = Gross - all deductions
*
* ---- Sanity check: net pay must be positive -------------------
         CP    EMNPAY,=P'0'
         BL    PRNEGERR           Negative net pay – raise error
*
* ---- Step 7: Format amounts for output ------------------------
         GO    FORMAT              Format all monetary fields
*
* ---- Step 8: Write pay-detail record to database --------------
         L     R15,=V(DBWRITE)    Link to DB write module
         BALR  R14,R15
         LTR   R15,R15            Did DB write succeed?
         BNZ   PRDBWER            No – handle DB write error
*
         B     PREXIT
*
* ---- Error paths ----------------------------------------------
PRNEGERR DS    0H
         MVC   ERRMSG2,=CL40'Net pay is negative – data error  '
         MVI   ERRFLAG,X'FF'
         GOIF  ERRORS             Handle the error
         B     PREXIT
*
PRDBWER  DS    0H
         MVC   ERRMSG2,=CL40'Database write failed              '
         MVI   ERRFLAG,X'FF'
         GOIF  ERRORS
*
* ---- Exit ----------------------------------------------------
PREXIT   DS    0H
         L     R13,PRSAVE+4
         LM    R14,R12,12(R13)
         BR    R14
         OUT
*
* ---- Local working storage -----------------------------------
PRSAVE   DC    18F'0'
PRWORK1  DC    PL12'0'            General packed-decimal work area
PRFICA   DC    PL8'0'             FICA (Social Security) amount
ERRMSG2  DC    CL40' '
PRWKFL   DC    X'00'              Local work flag
PRCTR    DC    F'0'               Loop counter
*
         LTORG
