* ============================================================
* EXTPROG1 – external subroutine in its own file
* Called via:  GO EXTPROG1  from the main program
* ============================================================
EXTPROG1 IN
         STM   14,12,12(13)
         BALR  12,0
         USING *,12
         ST    13,EP1SAVE+4
         LA    13,EP1SAVE
*
* Do some work
         MVC   EXTBUFF,=CL80'EXTPROG1 WAS HERE'
*
* Call a nested external program
         GO    EXTPROG2
*
         L     13,EP1SAVE+4
         LM    14,12,12(13)
         BR    14
*
EP1SAVE  DC    18F'0'
EXTBUFF  DS    CL80
*
         END   EXTPROG1
