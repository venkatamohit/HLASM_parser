* External subroutine SUBD – leaf called via L (Link) instruction
SUBD     IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,SDSAVE+4
         LA    13,SDSAVE
*
         MVC   0(8,13),=CL8'LINK-OK '
*
         L     13,SDSAVE+4
         LM    14,12,12(13)
         BR    14
         OUT
*
SDSAVE   DC    18F'0'
