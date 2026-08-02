# Compose

The root Compose file runs the canonical stateful research API and a separate
one-shot daily-intelligence refresh job. The API never starts that job or makes
implicit network calls.

Run one safe manual refresh with:

```bash
docker compose --profile research-admin run --rm intelligence-refresh
```

Before the first Linux-host run, create the three
`var/quantos/intelligence*` bind-mount directories and make them writable by
container UID `10001`. The systemd unit assumes the repository is installed at
`/opt/QuantOS`; adjust `WorkingDirectory` if needed, copy both files from
`deployments/systemd/` to `/etc/systemd/system/`, then enable the timer. It runs
once after the UTC close, catches up missed runs, and relies on the command's
non-blocking file lock to reject overlap.
