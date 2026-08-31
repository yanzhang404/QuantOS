# Strategy SDK

Defines the `initialize`, `on_bar`, `on_fill`, and `finalize` lifecycle shared by
research runtimes. A strategy receives a read-only symbol/interval context and
events, and may only return `SignalEvent`; exchange and portfolio APIs are not
available.

Versioned external feature values arrive only inside the current read-only
`MarketEvent`. Strategies do not receive data-store, network, order, or account
handles.
