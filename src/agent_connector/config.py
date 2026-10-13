"""Project-wide tunable settings.

Keep operational limits and defaults here so callers do not hunt through
individual modules. Algorithm-internal weights can stay private to their
agents unless they need to be shared or tuned from one place.
"""

# --- Incident validation -------------------------------------------------
MAX_LOG_ENTRIES = 5_000

# --- Local gRPC servers --------------------------------------------------
DEFAULT_GRPC_HOST = "127.0.0.1"
GRPC_SHUTDOWN_GRACE_SECONDS = 5.0

# Slightly under gRPC's common 4 MiB default message ceiling.
MAX_GRPC_REQUEST_BYTES = 3_932_160
