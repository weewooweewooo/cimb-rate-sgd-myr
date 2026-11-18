"""Rate providers (CIMB, Wise)."""
from __future__ import annotations


class ProviderError(Exception):
    """A provider could not be reached or returned data we cannot use."""
