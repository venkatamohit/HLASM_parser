* ============================================================
* EXTPROG2 – leaf-level external subroutine
* ============================================================
EXTPROG2 IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,EP2SAVE+4
         LA    13,EP2SAVE
*
         MVI   EP2FLAG,X'01'      Signal completion
*
         L     13,EP2SAVE+4
         LM    14,12,12(13)
         BR    14
*
EP2SAVE  DC    18F'0'
EP2FLAG  DS    X
*
         END   EXTPROG2
