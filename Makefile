.PHONY: install proto test

install:
	python -m pip install -e ".[dev]"

proto:
	python -m grpc_tools.protoc -Iagent_connector/generated=proto --python_out=src --pyi_out=src --grpc_python_out=src proto/incident.proto

test:
	python -m pytest -q
