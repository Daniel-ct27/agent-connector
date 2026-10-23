"""Project-wide tunable settings.
"""

# --- Incident validation -------------------------------------------------
MAX_LOG_ENTRIES = 5_000

# --- Local gRPC servers --------------------------------------------------
DEFAULT_GRPC_HOST = "127.0.0.1"
GRPC_SHUTDOWN_GRACE_SECONDS = 5.0

# Standard local gRPC demo range starting at the common example port 50051.
SEVERITY_GRPC_PORT = 50051
RUNBOOK_GRPC_PORT = 50052
LOG_ANALYSIS_GRPC_PORT = 50053

# Slightly under gRPC's common 4 MiB default message ceiling.
MAX_GRPC_REQUEST_BYTES = 3_932_160

# --- Orchestrator deadlines (Stage 4) ------------------------------------
UNARY_DEADLINE_SECONDS = 2.0
STREAM_DEADLINE_SECONDS = 10.0

# Default append target for structured orchestrator JSONL logs.
DEFAULT_ORCHESTRATOR_JSONL_PATH = "logs/orchestrator.jsonl"

# --- Log Analysis analyzer selection (Stage 5) ----------------------------
DEFAULT_ANALYZER = "deterministic"
LLM_MODEL = "gpt-4o-mini"
LLM_TIMEOUT_SECONDS = 8.0
LLM_MAX_OUTPUT_TOKENS = 256
LLM_TEMPERATURE = 0.0
ANALYZER_ENV_VAR = "AGENT_CONNECTOR_ANALYZER"
LLM_MODEL_ENV_VAR = "AGENT_CONNECTOR_LLM_MODEL"
LLM_TIMEOUT_ENV_VAR = "AGENT_CONNECTOR_LLM_TIMEOUT_SECONDS"
OPENAI_API_KEY_ENV_VARS = ("AGENT_CONNECTOR_OPENAI_API_KEY", "OPENAI_API_KEY")
