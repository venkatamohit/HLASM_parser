* ================================================================
* ERRORS  –  Centralised Error Handling Subroutine
* ================================================================
*
* Called by: MAINPROG  (L R15,=V(ERRORS)  via ERRHANDLE)
*            VALIDATE  (L R15,=V(ERRORS))
*            PROCESS   (GOIF  ERRORS)
* Calls:     (none – leaf subroutine)
*
* Function:
*   Provides a single point of error handling for the payroll
*   system.  It:
*     1. Formats an error detail line from ERRMSG / EMPLID
*     2. Writes the line to ERRFILE (SYSOUT class R)
*     3. Bumps the run error counter ERRCTR
*     4. If ERRCTR exceeds ERRLIMIT, sets ABEND flag
*     5. Optionally issues an operator WTOR if CONSOLE flag set
*
* Entry:
*   ERRFLAG  set to X'FF' by caller
*   ERRMSG   contains 40-byte description  (caller-set)
*   EMPLID   contains the current employee ID
*
* Exit:
*   ERRFLAG  unchanged (caller must reset if processing continues)
*   ERRCTR   incremented
*   PRTLINE  written to ERRFILE
* ================================================================
*
ERRORS   IN
         STM   R14,R12,12(R13)
         BALR  R12,0
         USING *,R12
         ST    R13,ERRSAVE+4
         LA    R13,ERRSAVE
*
* ---- Increment error counter ---------------------------------
         L     R2,ERRCTR           Load current count
         LA    R2,1(R2)            Add 1
         ST    R2,ERRCTR           Store updated count
*
* ---- Build error print line ----------------------------------
         MVC   ERPRLIN,=CL133' '  Clear output line
         MVI   ERPRLIN,C'0'       Double-space control char
         MVC   ERPRLIN+1(8),=CL8'** ERROR'
         MVC   ERPRLIN+10(8),EMPLID    Employee ID
         MVC   ERPRLIN+20(40),ERRMSG   Error message text
*
* ---- Format current date/time into error line ---------------
         TIME  BIN
         CVD   R0,ERTIMWD          Convert time to packed
         UNPK  ERTIME(6),ERTIMWD+5(3)  Extract HH MM SS
         OI    ERTIME+5,X'F0'
         MVC   ERPRLIN+62(6),ERTIME
*
* ---- Write the error line -----------------------------------
         PUT   ERRFILE,ERPRLIN
*
* ---- Check whether we have hit the error limit --------------
         C     R2,ERRLIMIT         Exceeded limit?
         BL    ERROK               No – carry on
*
* ---- Too many errors – set abend flag -----------------------
         MVI   RETCODE,X'16'       Set severe return code
         MVC   ERPRLIN+1(20),=CL20'** ABEND LIMIT HIT **'
         PUT   ERRFILE,ERPRLIN
*
ERROK    DS    0H
* ---- Clear ERRMSG so caller does not re-use stale text ------
         MVC   ERRMSG,=CL40' '
*
* ---- Exit ---------------------------------------------------
         L     R13,ERRSAVE+4
         LM    R14,R12,12(R13)
         XR    R15,R15
         BR    R14
         OUT
*
* ---- Local working storage ----------------------------------
ERRSAVE  DC    18F'0'
ERPRLIN  DC    CL133' '           Error print line buffer
ERTIMWD  DC    D'0'               Time work doubleword
ERTIME   DC    CL6' '             Formatted time HHMMSS
ERCNT    DC    F'0'               Local counter copy
*
* ---- Shared error-handling fields ---------------------------
ERRCTR   DC    F'0'               Count of errors this run
ERRLIMIT DC    F'99'              Maximum errors before abend
ERRMSG   DC    CL40' '            Error description from caller
*
* ---- Error output file DCB ----------------------------------
ERRFILE  DCB   DDNAME=ERRFILE,MACRF=PM,DSORG=PS,                      X
               LRECL=133,BLKSIZE=1330,RECFM=FBA
*
         LTORG
