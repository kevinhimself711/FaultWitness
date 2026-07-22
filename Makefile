.PHONY: verify-fast eval-changed

verify-fast:
	uv run python tools/bootstrap_check.py verify-fast

eval-changed:
	uv run python tools/bootstrap_check.py eval-changed
