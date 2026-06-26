"""Copybook record models (dataclass equivalents of COBOL copybooks)."""

from carddemo.models.account import AccountRecord
from carddemo.models.card_xref import CardXrefRecord
from carddemo.models.customer import CustomerRecord
from carddemo.models.daily_transaction import DailyTransactionRecord
from carddemo.models.transaction import TransactionRecord

__all__ = [
    "AccountRecord",
    "CardXrefRecord",
    "CustomerRecord",
    "DailyTransactionRecord",
    "TransactionRecord",
]
