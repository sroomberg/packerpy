"""Utility functions for packerpy."""

from __future__ import annotations


def parse_list(raw: list | str, delimiter: str = ",") -> list[str]:
    """Parse a value into a list of strings.

    Args:
        raw: A list (returned as-is) or a delimited string to split.
        delimiter: The delimiter to split on. Defaults to ",".

    Returns:
        A list of strings.

    Raises:
        ValueError: If raw is neither a list nor a string.
    """
    if isinstance(raw, list):
        return raw
    elif isinstance(raw, str):
        return raw.split(delimiter)
    else:
        raise ValueError(f"Invalid type {type(raw)}. Only list or str allowed.")
