# Infrastructure

Phase 0 provides Docker Compose and CI foundations without provisioning unused
services. The opt-in `us-radar` profile runs the read-only market-radar worker;
no service starts by default. PostgreSQL, Redis, object storage, telemetry, and
dashboards will be added only with the milestone that consumes them. Kubernetes
is out of scope.
