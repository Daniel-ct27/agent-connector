"""Small local collection of troubleshooting procedures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunbookDefinition:
    runbook_id: str
    title: str
    keywords: tuple[str, ...]
    steps: tuple[tuple[int, str, str], ...]  # order, action, detail


RUNBOOKS: tuple[RunbookDefinition, ...] = (
    RunbookDefinition(
        runbook_id="rb-db-connection",
        title="Database connection failure",
        keywords=(
            "database",
            "connection",
            "timeout",
            "too many clients",
            "i/o timeout",
            "orders-db",
        ),
        steps=(
            (1, "Check database process health", "Verify the DB host is up and accepting TCP connections."),
            (2, "Inspect connection pool saturation", "Compare active vs max connections and kill idle sessions if needed."),
            (3, "Validate dependent service credentials", "Confirm checkout-service can authenticate to the database."),
            (4, "Roll forward or fail closed", "If the DB remains unavailable, shed checkout traffic at the gateway."),
        ),
    ),
    RunbookDefinition(
        runbook_id="rb-retry-storm",
        title="Retry storm / cascading load",
        keywords=(
            "retry",
            "retries exhausted",
            "rate limit",
            "too many requests",
            "timeout",
            "scheduling retry",
        ),
        steps=(
            (1, "Disable or dampen aggressive retries", "Lower retry counts and add jittered backoff on the caller."),
            (2, "Protect the overloaded dependency", "Enable rate limiting or a circuit breaker on card-gateway calls."),
            (3, "Drain queued work", "Clear or pause backlog that is replaying failed payment attempts."),
            (4, "Confirm recovery", "Watch error rates on payment-service and inventory-service before reopening traffic."),
        ),
    ),
    RunbookDefinition(
        runbook_id="rb-expired-cert",
        title="Expired TLS certificate",
        keywords=(
            "certificate",
            "expired",
            "tls",
            "x509",
            "mtls",
            "certificate verify failed",
        ),
        steps=(
            (1, "Identify the expired certificate", "Inspect cert CN and not_after on auth-service."),
            (2, "Issue and install a replacement cert", "Deploy a valid certificate to the affected service."),
            (3, "Reload TLS material", "Restart or hot-reload auth-service and dependent mTLS clients."),
            (4, "Verify handshakes", "Confirm /login and service-to-service calls succeed without x509 errors."),
        ),
    ),
)
