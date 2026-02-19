* CHUNK : HLASM_ROOT
* TYPE  : CSECT
* SOURCE: tests/fixtures/sample.hlasm
* DEPS  : PROCESS1, PROCESS2
*──────────────────────────────────────────────────────────────────
CSECT, labeled blocks, BAL subroutine calls, data areas
CSECT
STM   14,12,12(13)     Save all registers
BALR  12,0             Establish base register
USING *,12
ST    13,SAVEAREA+4    Save caller's save area address
LA    13,SAVEAREA      Point to our save area
LA    1,INPUTPARM      Load parameter address
BAL   14,PROCESS1      Call processing routine 1
LA    1,INPUTPARM
BAL   14,PROCESS2      Call processing routine 2
L     13,SAVEAREA+4    Restore caller's save area
LM    14,12,12(13)     Restore all registers
BR    14               Return to caller
