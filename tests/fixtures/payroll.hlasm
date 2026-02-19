* ============================================================
* PAYROLL – Main driver program demonstrating mixed subroutine
*           call styles and cross-file dependencies.
*
* Inline subroutines (BAL / classic style):
*   CALCBASE  – calculate base pay
*   PRTREORT  – print report line
*
* Inline subroutines (GO / IN style):
*   INITWS    – initialise working storage
*   VALIDATE  – validate employee record
*
* External programs (GO → separate .asm files):
*   TAXCALC   – tax-calculation module  (TAXCALC.asm)
*   DEDUCTNS  – deductions module       (DEDUCTNS.asm)
*   RPTWRITE  – report-writer module    (RPTWRITE.asm)
* ============================================================
PAYROLL  CSECT
         STM   14,12,12(13)     Save all registers
         BALR  12,0             Establish base register
         USING *,12
         ST    13,PAYSAVE+4     Chain save areas
         LA    13,PAYSAVE
*
* --- Initialise working storage (GO/IN style) ---
         GO    INITWS
*
* --- Validate employee record (GO/IN style) ---
         GO    VALIDATE
*
* --- Calculate base pay (classic BAL style) ---
         LA    1,EMPREC         Load employee record address
         BAL   14,CALCBASE
*
* --- Apply tax calculation (external GO) ---
         GO    TAXCALC
*
* --- Apply deductions (external GO) ---
         GO    DEDUCTNS
*
* --- Print report (classic BAL style) ---
         LA    1,OUTBUFF        Load output buffer address
         BAL   14,PRTREORT
*
* --- Write report file (external GO) ---
         GO    RPTWRITE
*
* --- Normal exit ---
         L     13,PAYSAVE+4
         LM    14,12,12(13)
         BR    14
*
* ── Working storage ──────────────────────────────────────────
PAYSAVE  DC    18F'0'
EMPREC   DS    CL80             Employee record buffer
OUTBUFF  DS    CL133            Report output line (ASA)
PAYFLAG  DS    X                Processing flags
BASEPAY  DS    F                Base pay amount
NETPAY   DS    F                Net pay after deductions
*
* ============================================================
* CALCBASE – calculate base pay (classic BAL subroutine)
* Called with R1 → employee record
* ============================================================
CALCBASE STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,CBSAVE+4
         LA    13,CBSAVE
*
         L     2,0(1)           Load hours-worked field
         M     2,=F'1000'       Multiply by hourly rate (cents)
         ST    3,BASEPAY        Store base pay result
         MVI   PAYFLAG,X'01'   Mark pay calculated
*
         L     13,CBSAVE+4
         LM    14,12,12(13)
         BR    14
*
CBSAVE   DC    18F'0'
*
* ============================================================
* PRTREORT – format and print a report line (classic BAL)
* Called with R1 → output buffer
* ============================================================
PRTREORT STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,PRSAVE+4
         LA    13,PRSAVE
*
         MVC   0(133,1),=CL133' '    Clear output line
         MVC   1(80,1),EMPREC         Copy employee data
         CVD   3,WORKDBL              Convert pay to packed
         MVC   50(12,1),=X'402020206B2020206B202060'
         ED    50(12,1),WORKDBL+3     Edit pay amount
*
         L     13,PRSAVE+4
         LM    14,12,12(13)
         BR    14
*
PRSAVE   DC    18F'0'
WORKDBL  DS    D
*
* ============================================================
* INITWS – initialise working storage (GO/IN subroutine)
* ============================================================
INITWS   IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,IWSAVE+4
         LA    13,IWSAVE
*
         MVC   EMPREC,=CL80' '      Clear employee record
         MVC   OUTBUFF,=CL133' '    Clear output line
         MVI   PAYFLAG,X'00'        Clear flags
         XC    BASEPAY,BASEPAY      Zero base pay
         XC    NETPAY,NETPAY        Zero net pay
*
         L     13,IWSAVE+4
         LM    14,12,12(13)
         BR    14
*
IWSAVE   DC    18F'0'
*
* ============================================================
* VALIDATE – validate employee record (GO/IN subroutine)
* ============================================================
VALIDATE IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,VLSAVE+4
         LA    13,VLSAVE
*
         CLC   EMPREC(8),=CL8' '   Check if employee ID blank
         BE    VALERR               Error if blank
*
         CLC   EMPREC+8(4),=F'0'   Check hours > 0
         BNH   VALERR               Error if zero or negative
*
         MVI   PAYFLAG,X'02'        Mark record valid
         B     VALOK
*
VALERR   MVI   PAYFLAG,X'FF'        Mark record invalid
*
VALOK    DS    0H
         L     13,VLSAVE+4
         LM    14,12,12(13)
         BR    14
*
VLSAVE   DC    18F'0'
*
         END   PAYROLL
