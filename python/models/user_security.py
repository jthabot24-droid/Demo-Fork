"""CSUSR01Y -- SEC-USER-DATA (80 bytes)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserSecurityRecord:
    """Python mirror of the COBOL SEC-USER-DATA copybook (CSUSR01Y)."""

    sec_usr_id: str = ""        # PIC X(08)
    sec_usr_fname: str = ""     # PIC X(20)
    sec_usr_lname: str = ""     # PIC X(20)
    sec_usr_pwd: str = ""       # PIC X(08)
    sec_usr_type: str = ""      # PIC X(01)

    RECORD_LENGTH: int = 80
