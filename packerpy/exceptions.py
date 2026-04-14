"""Custom exceptions for packerpy."""

from __future__ import annotations


def raise_(ex: Exception) -> None:
    """Raise an exception from a lambda or expression context."""
    raise ex


class PackerBuildError(Exception):
    """Raised when a Packer build fails or produces an invalid configuration."""

    def __init__(self, message: str | None = None, _type: type | None = None) -> None:
        error_message = f"- {_type.__name__}: {message}" if _type else f"- {message}"
        super().__init__("PackerBuildError " + error_message)


class PackerClientError(Exception):
    """Raised when the Packer CLI encounters an error."""
