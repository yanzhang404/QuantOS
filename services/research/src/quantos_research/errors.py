"""Expected research workflow failures."""


class ResearchError(Exception):
    """Base class for failures that should be shown to CLI users."""


class ResearchConfigurationError(ResearchError):
    """Raised when an experiment design is invalid."""
