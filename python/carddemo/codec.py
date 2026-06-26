"""COBOL fixed-width field codec utilities.

Handles zoned-decimal (overpunch) sign encoding used in ASCII representations
of COBOL ``PIC S9(n)Vnn`` fields, as well as generic fixed-width string and
unsigned numeric helpers.
"""

from __future__ import annotations

from decimal import Decimal

# ASCII overpunch sign encoding (last digit encodes the sign).
_POS_OVERPUNCH = {
    "0": "{", "1": "A", "2": "B", "3": "C", "4": "D",
    "5": "E", "6": "F", "7": "G", "8": "H", "9": "I",
}
_NEG_OVERPUNCH = {
    "0": "}", "1": "J", "2": "K", "3": "L", "4": "M",
    "5": "N", "6": "O", "7": "P", "8": "Q", "9": "R",
}

_OVERPUNCH_TO_DIGIT: dict[str, tuple[str, bool]] = {}
for _d, _c in _POS_OVERPUNCH.items():
    _OVERPUNCH_TO_DIGIT[_c] = (_d, False)
for _d, _c in _NEG_OVERPUNCH.items():
    _OVERPUNCH_TO_DIGIT[_c] = (_d, True)


def decode_signed_numeric(raw: str, decimal_places: int) -> Decimal:
    """Decode a COBOL zoned-decimal (overpunch) string to ``Decimal``.

    Parameters
    ----------
    raw:
        The fixed-width field value, e.g. ``"00000001940{"`` for
        ``PIC S9(10)V99``.
    decimal_places:
        Number of implied decimal digits (the ``nn`` in ``Vnn``).

    Returns
    -------
    Decimal with the correct sign and scale.
    """
    if not raw:
        return Decimal(0)

    last_char = raw[-1]
    if last_char in _OVERPUNCH_TO_DIGIT:
        digit, is_negative = _OVERPUNCH_TO_DIGIT[last_char]
        digits = raw[:-1] + digit
    else:
        digits = raw
        is_negative = False

    if decimal_places > 0:
        integer_part = digits[:-decimal_places]
        decimal_part = digits[-decimal_places:]
        numeric_str = f"{integer_part}.{decimal_part}"
    else:
        numeric_str = digits

    value = Decimal(numeric_str)
    if is_negative:
        value = -value
    return value


def encode_signed_numeric(
    value: Decimal, total_digits: int, decimal_places: int
) -> str:
    """Encode a ``Decimal`` to a COBOL zoned-decimal (overpunch) string.

    Parameters
    ----------
    value:
        The numeric value to encode.
    total_digits:
        Total number of digit positions (integer + decimal).
    decimal_places:
        Number of implied decimal digits.

    Returns
    -------
    Fixed-width string with overpunch sign on the last character.
    """
    is_negative = value < 0
    abs_val = abs(value)

    if decimal_places > 0:
        shifted = int(abs_val * (10 ** decimal_places))
    else:
        shifted = int(abs_val)

    digits = str(shifted).zfill(total_digits)
    if len(digits) > total_digits:
        digits = digits[-total_digits:]

    last_digit = digits[-1]
    overpunch_map = _NEG_OVERPUNCH if is_negative else _POS_OVERPUNCH
    encoded = digits[:-1] + overpunch_map[last_digit]
    return encoded


def decode_unsigned_numeric(raw: str) -> int:
    """Decode a ``PIC 9(n)`` field to ``int``."""
    stripped = raw.strip()
    if not stripped or not stripped.isdigit():
        return 0
    return int(stripped)


def encode_unsigned_numeric(value: int, width: int) -> str:
    """Encode an ``int`` to a ``PIC 9(n)`` field."""
    return str(value).zfill(width)[:width]


def decode_alphanumeric(raw: str) -> str:
    """Decode a ``PIC X(n)`` field — strip trailing spaces."""
    return raw.rstrip()


def encode_alphanumeric(value: str, width: int) -> str:
    """Encode a string to a ``PIC X(n)`` field — right-pad with spaces."""
    return value.ljust(width)[:width]
