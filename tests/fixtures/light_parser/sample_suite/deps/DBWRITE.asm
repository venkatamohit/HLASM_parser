* ================================================================
* DBWRITE  –  Pay Detail Database Write Subroutine
* ================================================================
*
* Called by: PROCESS  (L R15,=V(DBWRITE))
* Calls:     (none – leaf subroutine)
*
* Function:
*   Writes one pay-detail row to the PAYDETL VSAM KSDS.
*   The key is  EMPLID (8) || PAYPER (6) = 14 bytes.
*   If a record with the same key already exists, it is
*   replaced (PUT with OPTCD=UPD).  A new record is added
*   if none exists (PUT with OPTCD=ADR).
*
*   Fields written:
*     EMPLID   CL8   Employee identifier
*     PAYPER   CL6   Pay period YYYYMM
*     EMGROSS  PL8   Gross pay
*     EMTAX    PL8   Total tax
*     EMFED    PL8   Federal tax
*     EMSTATE  PL8   State tax
*     EMHINS   PL8   Health insurance deduction
*     EMRET    PL8   Retirement deduction
*     EMDED    PL8   Total deductions
*     EMNPAY   PL8   Net pay
*     EMPLTYP  CL1   Employment type
*     Filler   CL109 Reserved for future use
*
* Exit:
*   R15 = 0   write successful
*   R15 = 4   duplicate key; record updated (not an error)
*   R15 = 8   I/O error
*   R15 = 12  file not open
* ================================================================
*
DBWRITE  IN
         STM   R14,R12,12(R13)
         BALR  R12,0
         USING *,R12
         ST    R13,DBWSAVE+4
         LA    R13,DBWSAVE
*
* ---- Verify file is open ------------------------------------
         TM    PAYDETL+48,X'10'   Check open flag in ACB
         BZ    DBWNOTOP           File not open – error
*
* ---- Build the output record --------------------------------
         MVC   DBWREC,=CL200' '   Clear the output buffer
         MVC   DBWREC+0(8),EMPLID     Employee ID
         MVC   DBWREC+8(6),PAYPER     Pay period
         MVC   DBWREC+14(8),EMGROSS   Gross pay (packed)
         MVC   DBWREC+22(8),EMTAX     Total tax
         MVC   DBWREC+30(8),EMFED     Federal tax
         MVC   DBWREC+38(8),EMSTATE   State tax
         MVC   DBWREC+46(8),EMHINS    Health insurance
         MVC   DBWREC+54(8),EMRET     Retirement
         MVC   DBWREC+62(8),EMDED     Total deductions
         MVC   DBWREC+70(8),EMNPAY    Net pay
         MVC   DBWREC+78(1),EMPLTYP   Employment type
*
* ---- Attempt to locate existing record (update or add) ------
         PUT   RPL=DBWAPL          First try an update
         LTR   R15,R15
         BZ    DBWOK              Updated – done
         C     R15,=F'8'          Logic-level error?
         BNE   DBWIOERR           No – physical I/O error
*
* ---- Record did not exist – add it --------------------------
         PUT   RPL=DBWRPL          Add the new record
         LTR   R15,R15
         BNZ   DBWIOERR
         B     DBWOK
*
* ---- I/O error ---------------------------------------------
DBWIOERR DS    0H
         MVC   DBWERR,=CL40'VSAM I/O error writing PAYDETL    '
         LA    R15,8
         B     DBWEXIT
*
* ---- File not open -----------------------------------------
DBWNOTOP DS    0H
         MVC   DBWERR,=CL40'PAYDETL file is not open           '
         LA    R15,12
         B     DBWEXIT
*
* ---- Success -----------------------------------------------
DBWOK    DS    0H
         XR    R15,R15
*
* ---- Exit --------------------------------------------------
DBWEXIT  DS    0H
         L     R13,DBWSAVE+4
         LM    R14,R12,12(R13)
         BR    R14
         OUT
*
* ---- Local working storage ---------------------------------
DBWSAVE  DC    18F'0'
DBWERR   DC    CL40' '
DBWREC   DC    CL200' '           Pay-detail record buffer
*
* ---- VSAM RPLs (update and add) ----------------------------
DBWAPL   RPL   ACB=PAYDETL,AREA=DBWREC,AREALEN=200,                   X
               OPTCD=(KEY,DIR,SYN,UPD)
DBWRPL   RPL   ACB=PAYDETL,AREA=DBWREC,AREALEN=200,                   X
               OPTCD=(KEY,DIR,SYN,ADR)
*
PAYDETL  ACB   DDNAME=PAYDETL,MACRF=(KEY,DIR),STRNO=1
*
         LTORG
