* ============================================================
* EXTPROG3 – external program called from an inline IN subroutine
* ============================================================
EXTPROG3 IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,EP3SAVE+4
         LA    13,EP3SAVE
*
         MVI   EP3FLAG,X'01'      Signal completion
*
         L     13,EP3SAVE+4
         LM    14,12,12(13)
         BR    14
*
EP3SAVE  DC    18F'0'
EP3FLAG  DS    X
*
         END   EXTPROG3
