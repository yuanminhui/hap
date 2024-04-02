"""
A module for error classes in the program.

Classes:
    BaseError: Base error class.
    DatabaseError: Exception raised for errors related to database operations.
    UnsupportedError: Exception raised for unsupported operations.
    InternalError: Exception raised for internal errors.
    DataError: Exception raised for errors related to data.
    DataInvalidError: Exception raised when data is invalid.
    DataIncompleteError: Exception raised when data is incomplete.
"""


class BaseError(Exception):
    """Base error class."""

    pass


class DatabaseError(BaseError):
    """Exception raised for errors related to database operations."""

    pass


class UnsupportedError(BaseError):
    """Exception raised for unsupported operations."""

    pass


class InternalError(BaseError):
    """Exception raised for internal errors."""

    pass


class DataError(BaseError):
    """Exception raised for errors related to data."""

    pass


class DataInvalidError(DataError):
    """Exception raised when data is invalid."""

    pass


class DataIncompleteError(DataError):
    """Exception raised when data is incomplete."""

    pass
