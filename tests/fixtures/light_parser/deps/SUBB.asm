* External subroutine SUBB – leaf (no further GO calls)
SUBB     IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,SBSAVE+4
         LA    13,SBSAVE
*
         MVI   0(13),X'00'
*
         L     13,SBSAVE+4
         LM    14,12,12(13)
         BR    14
         OUT
*
SBSAVE   DC    18F'0'
