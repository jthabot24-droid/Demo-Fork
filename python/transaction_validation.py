"""Backward-compatibility shim.

The transaction validation logic has moved to
``carddemo.transaction_validation``.  This module re-exports every public name
so that existing ``from transaction_validation import ...`` statements continue
to work.
"""

from carddemo.transaction_validation import (  # noqa: F401
    AccountRecord,
    CardXrefRecord,
    DailyTransactionRecord,
    TransactionInput,
    ValidationError,
    ValidationResult,
    validate_batch_transaction,
    validate_online_transaction,
)
