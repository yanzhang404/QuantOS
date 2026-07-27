# Strategy SDK

Defines the `initialize`, `on_bar`, `on_fill`, and `finalize` lifecycle shared by
research runtimes. A strategy receives a read-only symbol/interval context and
events, and may only return `SignalEvent`; exchange and portfolio APIs are not
available.
