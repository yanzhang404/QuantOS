"""Market Radar errors."""


class RadarError(Exception):
    """Base error for Market Radar workflows."""


class RadarValidationError(RadarError):
    """Raised when radar input violates the versioned contract."""
