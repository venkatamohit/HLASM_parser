* External subroutine SUBA – calls SUBC (tests nested GO resolution)
SUBA     IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,SASAVE+4
         LA    13,SASAVE
*
         GO    SUBC
*
         L     13,SASAVE+4
         LM    14,12,12(13)
         BR    14
         OUT
*
SASAVE   DC    18F'0'
