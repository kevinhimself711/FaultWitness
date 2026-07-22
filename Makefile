.PHONY: verify-fast eval-changed

verify-fast:
	uv run python -m faultwitness_dev verify-fast

eval-changed:
	uv run python -m faultwitness_dev eval-changed
