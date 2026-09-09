.PHONY: verify-fast

verify-fast:
	uv run python -m faultwitness_dev verify-fast
