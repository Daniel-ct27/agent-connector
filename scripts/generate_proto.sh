#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

mkdir -p src/agent_connector/generated
touch src/agent_connector/generated/__init__.py

python -m grpc_tools.protoc \
  -Iagent_connector/generated=proto \
  --python_out=src \
  --pyi_out=src \
  --grpc_python_out=src \
  proto/incident.proto
