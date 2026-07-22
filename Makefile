.PHONY: verify-fast eval-changed audit-g00 eval-g00 eval-g00-close

verify-fast:
	uv run python -m faultwitness_dev verify-fast

eval-changed:
	uv run python -m faultwitness_dev eval-changed

audit-g00:
	uv run python -m faultwitness_dev audit-g00
	pnpm run check:mermaid

eval-g00:
	uv run python -m faultwitness_dev eval-g00

eval-g00-close:
	uv run python -m faultwitness_dev eval-g00-close
