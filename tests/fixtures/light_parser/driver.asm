* ============================================================
* LIGHT PARSER TEST DRIVER
* Main flow GO calls are on lines 5-12 (used as start/end in tests)
* ============================================================
MAINPROG CSECT
         BALR  12,0
         USING *,12
         GO    SUBA
         GO    SUBB
         GOIF  INLSUB
         MVC   RESULT,=CL20' '
         BR    14
*
RESULT   DS    CL20
*
* ============================================================
* INLSUB – inline subroutine defined in the driver itself
* ============================================================
INLSUB   IN
         MVI   RESULT,C'Y'
         BR    14
         OUT
*
         END   MAINPROG
