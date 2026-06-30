"""CSUSR01Y -- SEC-USER-DATA (RECLN 80).

COBOL layout::

    01 SEC-USER-DATA.
      05 SEC-USR-ID                 PIC X(08).
      05 SEC-USR-FNAME              PIC X(20).
      05 SEC-USR-LNAME              PIC X(20).
      05 SEC-USR-PWD                PIC X(08).
      05 SEC-USR-TYPE               PIC X(01).
      05 SEC-USR-FILLER             PIC X(23).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SecUserData:
    """CSUSR01Y -- User security record (80 bytes)."""

    RECORD_LENGTH: int = 80

    sec_usr_id: str = ""        # PIC X(08)
    sec_usr_fname: str = ""     # PIC X(20)
    sec_usr_lname: str = ""     # PIC X(20)
    sec_usr_pwd: str = ""       # PIC X(08)
    sec_usr_type: str = ""      # PIC X(01)
    # FILLER PIC X(23) -- not stored

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "sec_usr_id": 8,
            "sec_usr_fname": 20,
            "sec_usr_lname": 20,
            "sec_usr_pwd": 8,
            "sec_usr_type": 1,
        }
