"""Data-access abstraction replacing VSAM KSDS + AIX keyed access."""

from carddemo.dataaccess.repository import (
    AccountRepository,
    CardRepository,
    CardXrefRepository,
    CustomerRepository,
    DisclosureGroupRepository,
    TranCatBalRepository,
    TransactionRepository,
)
from carddemo.dataaccess.in_memory import (
    InMemoryAccountRepository,
    InMemoryCardRepository,
    InMemoryCardXrefRepository,
    InMemoryCustomerRepository,
    InMemoryDisclosureGroupRepository,
    InMemoryTranCatBalRepository,
    InMemoryTransactionRepository,
)

__all__ = [
    "AccountRepository",
    "CardRepository",
    "CardXrefRepository",
    "CustomerRepository",
    "DisclosureGroupRepository",
    "InMemoryAccountRepository",
    "InMemoryCardRepository",
    "InMemoryCardXrefRepository",
    "InMemoryCustomerRepository",
    "InMemoryDisclosureGroupRepository",
    "InMemoryTranCatBalRepository",
    "InMemoryTransactionRepository",
    "TranCatBalRepository",
    "TransactionRepository",
]
