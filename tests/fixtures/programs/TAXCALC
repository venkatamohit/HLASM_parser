* ============================================================
* TAXCALC – Tax-calculation module
*
* Entry point:  TAXCALC  IN
*
* Inline subroutine (GO/IN style):
*   APPLYRT   – apply the appropriate tax rate
*
* External dependency (GO → separate file):
*   DEDUCTNS  – deductions module (DEDUCTNS.asm)
*
* Called from: PAYROLL (main driver), RPTWRITE (report writer)
* ============================================================
TAXCALC  IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,TCSAVE+4
         LA    13,TCSAVE
*
* Determine which tax band applies
         L     2,BASEPAY        Load gross pay
         C     2,=F'50000'      Compare with low threshold
         BH    TAXHI            Branch if high earner
*
* Low-band: apply standard rate inline then call rate routine
         MVC   TAXRATE,=F'20'   20% standard rate
         B     TAXAPPLY
*
TAXHI    DS    0H
         MVC   TAXRATE,=F'40'   40% higher rate
*
TAXAPPLY DS    0H
* Apply rate using inline GO/IN subroutine
         GO    APPLYRT
*
* Now apply any statutory deductions from external module
         GO    DEDUCTNS
*
* Store final net pay
         L     3,BASEPAY
         S     3,TAXAMT
         S     3,DEDAMT
         ST    3,NETPAY
*
         L     13,TCSAVE+4
         LM    14,12,12(13)
         BR    14
*
* ── Data areas ───────────────────────────────────────────────
TCSAVE   DC    18F'0'
TAXRATE  DS    F
TAXAMT   DS    F
DEDAMT   DS    F
*
* ============================================================
* APPLYRT – apply tax rate to base pay (GO/IN subroutine)
* ============================================================
APPLYRT  IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,ARSAVE+4
         LA    13,ARSAVE
*
         L     2,BASEPAY        Load gross pay
         M     2,TAXRATE        Multiply by rate
         D     2,=F'100'        Divide by 100 (get percentage)
         ST    3,TAXAMT         Store tax amount
*
         L     13,ARSAVE+4
         LM    14,12,12(13)
         BR    14
*
ARSAVE   DC    18F'0'
*
         END   TAXCALC
