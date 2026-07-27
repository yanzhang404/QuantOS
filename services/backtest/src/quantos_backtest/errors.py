"""Expected backtest-domain failures."""


class BacktestError(Exception):
    """Base class for backtest failures that should be shown to users."""


class BacktestConfigurationError(BacktestError):
    """Raised when a backtest configuration is unsafe or inconsistent."""


class PortfolioError(BacktestError):
    """Raised when a simulated fill violates portfolio invariants."""
