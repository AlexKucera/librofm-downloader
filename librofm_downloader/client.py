"""Deprecated re-export shim — import from ``librofm_downloader.session`` instead."""

import warnings

from .session import (
    API_SEMAPHORE_CAPACITY,
    AuthError,
    LibroFmSession,
    M4BUnavailableError,
)

warnings.warn(
    "Import from 'librofm_downloader.session' instead of 'librofm_downloader.client'. "
    "This shim will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

# Backward-compatible alias
LibroFmClient = LibroFmSession

# Re-export DEFAULT_HEADERS for code that reads LibroFmClient.DEFAULT_HEADERS
DEFAULT_HEADERS = LibroFmSession.DEFAULT_HEADERS

__all__ = [
    "LibroFmSession",
    "LibroFmClient",
    "AuthError",
    "M4BUnavailableError",
    "API_SEMAPHORE_CAPACITY",
    "DEFAULT_HEADERS",
]
