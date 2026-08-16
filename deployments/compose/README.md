# Compose

Local dependency and application composition belongs here as services enter the
roadmap. The root `compose.yaml` runs nothing by default and exposes only opt-in
profiles.

The optional `us-radar` profile runs the read-only US equity heat worker as a
long-lived container. Copy `.env.example` to the ignored `.env`, add Alpaca
market-data credentials, entitled equity/option feed names, and an optional
webhook, then run:

```bash
docker compose --profile us-radar up --build -d us-market-radar
```

No credential is copied into the image. Reports are written beneath local
`data/us-market-radar/`, which is ignored by Git.
