"""Custom exceptions used across the Vortex framework."""
from __future__ import annotations


class VortexError(Exception):
    """Base exception for all framework-specific errors."""


class ConfigurationError(VortexError):
    """Raised when configuration loading or validation fails."""


class ProviderError(VortexError):
    """Raised when model providers report an issue."""


class MemoryError(VortexError):
    """Raised when the memory subsystem cannot complete an operation."""


class PluginError(VortexError):
    """Raised for plugin loading or execution issues."""


class SecurityError(VortexError):
    """Raised when security policies are violated."""


__all__ = [
    "VortexError",
    "ConfigurationError",
    "ProviderError",
    "MemoryError",
    "PluginError",
    "SecurityError",
]
