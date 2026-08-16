"""Worker entry point. Install services/market-data before invoking directly."""

from quantos_market_data.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
