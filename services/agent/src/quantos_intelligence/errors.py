"""Daily intelligence errors."""


class IntelligenceError(Exception):
    """Base error for validated daily intelligence workflows."""


class IntelligenceValidationError(IntelligenceError):
    """Raised when an intelligence input violates the versioned contract."""
