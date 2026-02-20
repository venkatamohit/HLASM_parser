* External subroutine SUBC – leaf (called by SUBA, tests depth-2 resolution)
SUBC     IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,SCSAVE+4
         LA    13,SCSAVE
*
         MVC   0(4,13),=F'0'
*
         L     13,SCSAVE+4
         LM    14,12,12(13)
         BR    14
         OUT
*
SCSAVE   DC    18F'0'
