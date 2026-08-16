# Docker

Images use pinned base versions and non-root runtime users.

`market-radar.Dockerfile` packages the read-only US equity/options radar. API
credentials and webhooks are runtime environment variables and are never copied
into the image. The root Compose `us-radar` profile is its supported local
composition path.
