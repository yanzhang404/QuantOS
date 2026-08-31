# Compose

The root Compose file runs the canonical stateful research API plus separate
one-shot daily-intelligence and Market Radar refresh jobs. The API never starts
those jobs or makes implicit network calls.

Run one safe manual refresh with:

```bash
docker compose --profile research-admin run --rm intelligence-refresh
```

Run one safe A-share Market Radar refresh with:

```bash
docker compose --profile research-admin run --rm radar-refresh
```

Before the first Linux-host run, create the `var/quantos/intelligence*` and
`var/quantos/radar*` bind-mount directories and make them writable by
container UID `10001`. The systemd unit assumes the repository is installed at
`/opt/QuantOS`; adjust `WorkingDirectory` if needed, copy the desired unit pairs
from `deployments/systemd/` to `/etc/systemd/system/`, then enable their timers.
Each command uses a non-blocking file lock to reject overlap.
The radar timer covers the two weekday A-share sessions in UTC and deliberately
does not catch up missed intraday runs. It does not yet encode exchange holidays.
