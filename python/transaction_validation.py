"""Backward-compatible shim.

All validation logic now lives in ``carddemo.validation.transaction_validation``.
This module re-exports every public name so that existing imports
(including ``test_transaction_validation.py``) continue to work.
"""

from carddemo.models.common import ValidationError, ValidationResult
from carddemo.models.transaction import DailyTransactionRecord
from carddemo.validation.transaction_validation import (
    TransactionInput,
    validate_batch_transaction,
    validate_online_transaction,
)

__all__ = [
    "DailyTransactionRecord",
    "TransactionInput",
    "ValidationError",
    "ValidationResult",
    "validate_batch_transaction",
    "validate_online_transaction",
]
