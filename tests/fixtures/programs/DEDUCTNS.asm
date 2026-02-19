* ============================================================
* DEDUCTNS – Statutory deductions module
*
* Entry point:  DEDUCTNS  IN
*
* Inline subroutines (GO/IN style):
*   HLTHDED   – calculate health-insurance deduction
*   RETIRE    – calculate retirement-plan deduction
*
* No external GO dependencies (leaf-level module)
*
* Called from: PAYROLL (main driver), TAXCALC (tax module)
* ============================================================
DEDUCTNS IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,DDSAVE+4
         LA    13,DDSAVE
*
* Initialise total deductions
         XC    DEDAMT,DEDAMT        Zero deduction accumulator
*
* Calculate health-insurance deduction
         GO    HLTHDED
*
* Calculate retirement deduction
         GO    RETIRE
*
* Total deductions already accumulated in DEDAMT
         L     13,DDSAVE+4
         LM    14,12,12(13)
         BR    14
*
* ── Data areas ───────────────────────────────────────────────
DDSAVE   DC    18F'0'
DEDAMT   DS    F                Total deductions accumulator
HLTAMT   DS    F                Health deduction amount
RETAMT   DS    F                Retirement deduction amount
*
* ============================================================
* HLTHDED – health-insurance deduction (GO/IN subroutine)
* ============================================================
HLTHDED  IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,HHSAVE+4
         LA    13,HHSAVE
*
* Health deduction: 3% of base pay (standard plan)
         TM    PAYFLAG,X'02'    Check valid record flag
         BNO   HHLTEXIT         Skip if record not valid
*
         L     2,BASEPAY        Load gross pay
         M     2,=F'3'          Multiply by 3
         D     2,=F'100'        Divide by 100
         ST    3,HLTAMT         Store health amount
         A     3,DEDAMT         Add to total deductions
         ST    3,DEDAMT         Store updated total
*
HHLTEXIT DS    0H
         L     13,HHSAVE+4
         LM    14,12,12(13)
         BR    14
*
HHSAVE   DC    18F'0'
*
* ============================================================
* RETIRE – retirement-plan deduction (GO/IN subroutine)
* ============================================================
RETIRE   IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,RTSAVE+4
         LA    13,RTSAVE
*
* Retirement deduction: 5% of base pay
         TM    PAYFLAG,X'02'    Check valid record flag
         BNO   RTEXIT           Skip if not valid
*
         L     2,BASEPAY        Load gross pay
         M     2,=F'5'          Multiply by 5
         D     2,=F'100'        Divide by 100
         ST    3,RETAMT         Store retirement amount
         A     3,DEDAMT         Add to total deductions
         ST    3,DEDAMT         Store updated total
*
RTEXIT   DS    0H
         L     13,RTSAVE+4
         LM    14,12,12(13)
         BR    14
*
RTSAVE   DC    18F'0'
*
         END   DEDUCTNS
