"""One-time G02 immutability and remote-ruleset proof for governance v2."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
G02_RELEASE = "4622470a6afebc77e71519ee905d461fb0e86635"
RULESET_ID = "19545995"
PROTECTED_PATHS = (
    ":(glob)docs/evals/EVAL-G02-*/**",
    "docs/gates/G02",
    "docs/claims/CLAIMS.yaml",
    "config/g02",
    "deploy/g02/isolation-policy.yaml",
    "deploy/g02/packages",
    "tests/fixtures/g02",
)


def _run(*arguments: str) -> str:
    return subprocess.run(
        list(arguments),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def _private_p6_summary() -> dict[str, Any]:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("APPDATA is required to read private P6 evidence")
    path = (
        Path(appdata)
        / "FaultWitness/evidence/platform/governance-v2-k3s/proof-summary.json"
    )
    if not path.is_file():
        raise SystemExit(f"P6 summary is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_report() -> dict[str, Any]:
    release = _run("git", "rev-parse", "gate/G02-v1^{}").strip()
    if release != G02_RELEASE:
        raise SystemExit(f"gate/G02-v1 moved: expected {G02_RELEASE}, observed {release}")

    protected_diff = _run(
        "git",
        "diff",
        "--name-only",
        "gate/G02-v1^{}",
        "--",
        *PROTECTED_PATHS,
    ).splitlines()
    if protected_diff:
        raise SystemExit("frozen G02 assets changed: " + ", ".join(protected_diff))

    ruleset = json.loads(
        _run(
            "gh",
            "api",
            f"repos/kevinhimself711/FaultWitness/rulesets/{RULESET_ID}",
        )
    )
    rule_types = [rule["type"] for rule in ruleset["rules"]]
    if (
        ruleset.get("name") != "main-governance"
        or ruleset.get("enforcement") != "active"
        or ruleset.get("conditions", {}).get("ref_name", {}).get("include")
        != ["~DEFAULT_BRANCH"]
        or rule_types != ["deletion", "non_fast_forward"]
    ):
        raise SystemExit("remote GitHub ruleset does not match the minimal frozen policy")

    p6 = _private_p6_summary()
    zero_usage = {
        key: p6.get(key)
        for key in ("authorization_requests", "model_calls", "model_tokens", "model_cost")
    }
    if p6.get("status") != "pass" or zero_usage != {
        "authorization_requests": 0,
        "model_calls": 0,
        "model_tokens": 0,
        "model_cost": 0,
    }:
        raise SystemExit("P6 did not preserve zero authorization/model usage")

    if (ROOT / ".github/rulesets/main.json").exists():
        raise SystemExit("a second local ruleset authority is still active")

    return {
        "proof": "P7-g02-invariance-and-ruleset",
        "status": "pass",
        "g02_release": release,
        "protected_paths": list(PROTECTED_PATHS),
        "protected_diff": protected_diff,
        "invariants_preserved": [
            "G02 REPORT, PLAN, VALIDATIONS, CLAIMS and all EVAL-G02 evidence",
            "baseline N, bootstrap B, quality/performance thresholds and oracle semantics",
            "locked-test and Ground-Truth isolation inputs",
            "identity, object-prefix, egress and observability permissions",
            "frozen deployment package and image/config digests",
        ],
        "ruleset": {
            "id": ruleset["id"],
            "name": ruleset["name"],
            "enforcement": ruleset["enforcement"],
            "target": ruleset["target"],
            "include": ruleset["conditions"]["ref_name"]["include"],
            "rules": rule_types,
        },
        "local_ruleset_mirror": "absent",
        "usage": zero_usage,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
