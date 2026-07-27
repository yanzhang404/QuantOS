"""Domain-specific failures for the market-data module."""


class MarketDataError(Exception):
    """Base class for expected market-data failures."""


class ConfigurationError(MarketDataError):
    """Raised when a requested symbol, interval, or time range is unsupported."""


class DownloadError(MarketDataError):
    """Raised when an exchange response cannot be downloaded or normalized."""


class ValidationError(MarketDataError):
    """Raised when normalized market data violates the Kline contract."""


class DatasetError(MarketDataError):
    """Raised when a versioned dataset cannot be published or verified."""
