* ================================================================
* DBREAD  –  Employee Master Database Read Subroutine
* ================================================================
*
* Called by: VALIDATE  (GO DBREAD)
* Calls:     (none – leaf subroutine)
*
* Function:
*   Reads one row from the EMPMAST VSAM KSDS using the key
*   supplied in MSTKEY.  On success the master record fields
*   MSTNAME, MSTDEPT, MSTGRD, MSTSAL, MSTHIRDT, MSTTERMDT
*   are populated.  On failure R15 is set non-zero and DBERR
*   contains a descriptive message.
*
* Entry:
*   MSTKEY  (CL8) contains the employee ID to look up.
*
* Exit:
*   R15 = 0   record found and returned in MSTREC
*   R15 = 4   record not found (MSTKEY not in master)
*   R15 = 8   I/O error reading the VSAM file
*   R15 = 12  file not open
* ================================================================
*
DBREAD   IN
         STM   R14,R12,12(R13)
         BALR  R12,0
         USING *,R12
         ST    R13,DBRSAVE+4
         LA    R13,DBRSAVE
*
* ---- Verify file is open -------------------------------------
         TM    MSTFILE+48,X'10'   Check VSAM ACB open flag
         BZ    DBRNOTOP           File not open
*
* ---- Issue VSAM GET (keyed direct) --------------------------
         GET   RPL=DBRPL          Retrieve by key
         LTR   R15,R15
         BNZ   DBRNFND            Check for not-found vs I/O error
*
* ---- Record found – copy to caller's layout -----------------
         MVC   MSTNAME, MSTREC+8(30)    Name field
         MVC   MSTDEPT, MSTREC+38(4)    Department
         MVC   MSTGRD,  MSTREC+42(2)    Grade
         MVC   MSTTYP,  MSTREC+44(1)    Employment type
         ZAP   MSTSAL,  MSTREC+45       Annual salary
         MVC   MSTHIRDT,MSTREC+53(8)    Hire date
         MVC   MSTTRMDT,MSTREC+61(8)    Termination date (or spaces)
         MVI   DBRSTATS,C'F'      Status = Found
         XR    R15,R15            Return 0 = success
         B     DBREXIT
*
* ---- Record not found ----------------------------------------
DBRNFND  DS    0H
         C     R15,=F'8'          Is it a logical error (not found)?
         BNE   DBIOERR            No – real I/O error
         MVI   DBRSTATS,C'N'      Status = Not found
         MVC   DBERR,=CL40'Employee record not in master file '
         LA    R15,4              Return code 4 = not found
         B     DBREXIT
*
* ---- I/O error ----------------------------------------------
DBIOERR  DS    0H
         MVI   DBRSTATS,C'E'      Status = Error
         MVC   DBERR,=CL40'VSAM I/O error reading master file '
         LA    R15,8
         B     DBREXIT
*
* ---- File not open ------------------------------------------
DBRNOTOP DS    0H
         MVI   DBRSTATS,C'C'      Status = Closed
         MVC   DBERR,=CL40'EMPMAST file is not open           '
         LA    R15,12
*
* ---- Exit ---------------------------------------------------
DBREXIT  DS    0H
         L     R13,DBRSAVE+4
         LM    R14,R12,12(R13)    Restore registers; R15 already set
         BR    R14
         OUT
*
* ---- Local working storage ----------------------------------
DBRSAVE  DC    18F'0'
DBRSTATS DC    C' '               Last-operation status character
DBERR    DC    CL40' '            Error description
*
* ---- VSAM RPL (Request Parameter List) ----------------------
DBRPL    RPL   ACB=MSTFILE,       VSAM ACB                            X
               AREA=MSTREC,       Record buffer                       X
               AREALEN=200,       Buffer length                       X
               ARG=MSTKEY,        Key for keyed retrieval             X
               KEYLEN=8,          Key length                          X
               OPTCD=(KEY,DIR,SYN,NUP)  Options
*
* ---- Master record input buffer and field offsets -----------
MSTREC   DS    CL200              Raw 200-byte master record
MSTNAME  DS    CL30               Employee full name
MSTDEPT  DS    CL4                Department
MSTGRD   DS    CL2                Pay grade
MSTTYP   DS    CL1                Employment type
MSTSAL   DS    PL8                Annual salary
MSTHIRDT DS    CL8                Hire date  YYYYMMDD
MSTTRMDT DS    CL8                Termination date YYYYMMDD
*
* ---- VSAM ACB (Access Method Control Block) -----------------
MSTFILE  ACB   DDNAME=EMPMAST,MACRF=(KEY,DIR,SEQ),STRNO=1
*
         LTORG
