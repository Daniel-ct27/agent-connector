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

# --- Local HTTP servers (Stage 6) ----------------------------------------
DEFAULT_HTTP_HOST = "127.0.0.1"

# Distinct from the gRPC demo ports so both stacks can run together.
SEVERITY_HTTP_PORT = 8001
RUNBOOK_HTTP_PORT = 8002
LOG_ANALYSIS_HTTP_PORT = 8003

# Same ceiling as gRPC for fair unary request-size comparison.
MAX_HTTP_REQUEST_BYTES = MAX_GRPC_REQUEST_BYTES

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

# --- Stage 7 benchmarks --------------------------------------------------
BENCHMARK_PAYLOAD_SIZES = (100, 1_000, 5_000)
BENCHMARK_CONCURRENCY_LEVELS = (1, 5, 10)
BENCHMARK_WARMUP_TRIALS = 3
BENCHMARK_TIMED_TRIALS = 30
BENCHMARK_FIXTURE_SEED = 7
DEFAULT_BENCHMARK_RESULTS_DIR = "benchmarks/results"
DEMO_PANEL_PORT = 8090
