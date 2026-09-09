.PHONY: verify-fast verify-docs

verify-fast:
	uv run python -m faultwitness_dev verify-fast

verify-docs:
	uv run python -m faultwitness_dev verify-docs
