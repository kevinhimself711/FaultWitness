"""One-time G02 governance-cost classifier.

This proof intentionally stays outside pytest and ``verify-fast``. It reads the frozen
``gate/G01-v1..gate/G02-v1`` history, applies one mutually exclusive rule order, and fails if the
frozen reference counts or reviewed timelines drift.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HISTORY_RANGE = "gate/G01-v1..gate/G02-v1^{}"
EXPECTED_COUNTS = {
    "semantic": 57,
    "evidence-only": 38,
    "lifecycle/binding": 54,
    "policy/docs": 22,
    "other": 3,
}
SEMANTIC_ROOTS = ("src/", "tests/", "deploy/", "config/", "migrations/")
SEMANTIC_FILES = {"package.json", "pnpm-lock.yaml", "pyproject.toml", "uv.lock"}

ACCESS_START = "1a48cda4c3cbc986ddbf44119a5b1b79003a1a72"
ACCESS_END = "fbd03c464904b0969fdff9a8c89170435b80ef81"
I0034_START = "696d5887117d5689a0eb2b144fdcd26854373cec"
I0034_FIX = "1f366dc8bbe0e71611367b87ed72fb4e70db69cd"
I0034_END = "8a57964339f3bbd7bda538b239e6147406c487cb"
C012_FIX = "86a459c0bec1bcf3e583fd1280fbca2667479d2e"
C012_CLOSE = "ceb82e389164be2be085e80761ee7fc59edb517c"
AB_START = C012_CLOSE
AB_END = "e419e073695015441d90f92bc4469f49310f9893"


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def _commit_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    output = _git(
        "log",
        "--reverse",
        "--format=%H%x09%cI%x09%s",
        HISTORY_RANGE,
    )
    for line in output.splitlines():
        sha, committed_at, subject = line.split("\t", 2)
        paths = _git("diff-tree", "--no-commit-id", "--name-only", "-r", sha).splitlines()
        rows.append(
            {
                "sha": sha,
                "committed_at": committed_at,
                "subject": subject,
                "paths": paths,
            }
        )
    return rows


def _is_semantic_path(path: str) -> bool:
    return path in SEMANTIC_FILES or path.startswith(SEMANTIC_ROOTS)


def _classify(subject: str, paths: list[str]) -> str:
    """Apply the frozen, mutually exclusive P0 rule order."""
    if subject.startswith(("chore(iteration):", "chore(work-item):", "chore(eval):")):
        return "lifecycle/binding"
    if subject.startswith(("docs(eval):", "test(g02):")):
        return "evidence-only"
    if subject.startswith(('Revert "', 'Reapply "')):
        return "other"
    if any(_is_semantic_path(path) for path in paths):
        return "semantic"
    return "policy/docs"


def _numstat(commit: str) -> list[tuple[int, int, str]]:
    rows: list[tuple[int, int, str]] = []
    for line in _git("show", "--numstat", "--format=", commit).splitlines():
        added, deleted, path = line.split("\t", 2)
        rows.append(
            (
                int(added) if added.isdigit() else 0,
                int(deleted) if deleted.isdigit() else 0,
                path,
            )
        )
    return rows


def _commit_range(start: str, end: str) -> list[str]:
    return _git("rev-list", "--reverse", f"{start}^..{end}").splitlines()


def _range_stats(commits: list[str]) -> dict[str, int]:
    stats = [row for commit in commits for row in _numstat(commit)]
    return {
        "commits": len(commits),
        "file_touches": len(stats),
        "added_lines": sum(row[0] for row in stats),
        "deleted_lines": sum(row[1] for row in stats),
    }


def _commit_time(sha: str) -> datetime:
    return datetime.fromisoformat(_git("show", "-s", "--format=%cI", sha).strip())


def _assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise SystemExit(f"{label} drifted: expected {expected!r}, observed {actual!r}")


def build_report() -> dict[str, Any]:
    commits = _commit_rows()
    for row in commits:
        row["category"] = _classify(str(row["subject"]), list(row["paths"]))
    counts = dict(Counter(str(row["category"]) for row in commits))
    _assert_equal(len(commits), 174, "G02 commit count")
    _assert_equal(counts, EXPECTED_COUNTS, "mutually exclusive classification")

    implementation_or_test = [
        row
        for row in commits
        if any(path.startswith(("src/", "tests/")) for path in row["paths"])
    ]
    non_implementation = [row for row in commits if row not in implementation_or_test]
    total_touches = sum(len(row["paths"]) for row in commits)
    non_implementation_touches = sum(len(row["paths"]) for row in non_implementation)
    _assert_equal(len(implementation_or_test), 55, "src/tests commit observation")
    _assert_equal((non_implementation_touches, total_touches), (1111, 1616), "file touches")

    discrepancy = [
        {"sha": row["sha"], "subject": row["subject"], "paths": row["paths"]}
        for row in commits
        if row["category"] == "semantic" and row not in implementation_or_test
    ]
    _assert_equal([row["sha"][:7] for row in discrepancy], ["a66a6d1", "81ae5ec"], "55/57")

    status_prefixes = (
        "chore(iteration):",
        "chore(work-item):",
        "chore(eval):",
        "docs(eval):",
        "docs(g02):",
        "docs(governance):",
        "fix(governance):",
        "refactor(governance):",
        'Revert "chore(iteration):',
        'Reapply "chore(iteration):',
    )
    governance_status_intent = [
        row
        for row in commits
        if str(row["subject"]).startswith(status_prefixes)
        and row["sha"] != "149365d877cf0119aacd21f2f5b14001ed814070"
    ]
    _assert_equal(len(governance_status_intent), 93, "governance/status intent commits")

    access_commits = _commit_range(ACCESS_START, ACCESS_END)
    access = _range_stats(access_commits)
    runtime_rows = [
        row
        for commit in access_commits
        for row in _numstat(commit)
        if row[2] == "deploy/g02/gate_probe.py"
    ]
    access["runtime_added_lines"] = sum(row[0] for row in runtime_rows)
    access["runtime_deleted_lines"] = sum(row[1] for row in runtime_rows)
    _assert_equal(
        access,
        {
            "commits": 7,
            "file_touches": 59,
            "added_lines": 1593,
            "deleted_lines": 132,
            "runtime_added_lines": 12,
            "runtime_deleted_lines": 7,
        },
        "access-58 timeline",
    )

    i0034_commits = _commit_range(I0034_START, I0034_END)
    i0034 = _range_stats(i0034_commits)
    i0034["fix_file_touches"] = len(_numstat(I0034_FIX))
    _assert_equal(i0034["commits"], 5, "I-0034 commits")
    _assert_equal(i0034["file_touches"], 49, "I-0034 touches")
    _assert_equal(i0034["fix_file_touches"], 4, "I-0034 semantic fix touches")

    seam = json.loads(
        _git("show", f"{C012_CLOSE}:docs/evals/EVAL-G02-045/artifacts/trace-replay-seam.json")
    )
    seam_seconds = (
        datetime.fromisoformat(seam["ended_at"]) - datetime.fromisoformat(seam["started_at"])
    ).total_seconds()
    fix_to_close_seconds = (_commit_time(C012_CLOSE) - _commit_time(C012_FIX)).total_seconds()
    close_stats = _range_stats([C012_CLOSE])
    lessons = _git(
        "show",
        "gate/G02-v1:docs/engineering/GOVERNANCE_REFACTOR_LESSONS_LOG.md",
    )
    final_plan = _git("show", "gate/G02-v1:docs/evals/EVAL-G02-046/PLAN.md")
    final_report = _git("show", "gate/G02-v1:docs/evals/EVAL-G02-046/REPORT.md")
    c012 = {
        "real_seam_seconds": seam_seconds,
        "fix_to_lifecycle_close_seconds": fix_to_close_seconds,
        "close_commit_file_touches": close_stats["file_touches"],
        "close_commit_added_lines": close_stats["added_lines"],
        "one_time_adapter_observation_recorded": (
            "9.9 KB" in lessons and "真实运行只需 16 秒" in lessons
        ),
        "adapter_did_no_deploy_or_access_work": (
            "without redeployment" in final_plan
            and "No access cell executes again" in final_plan
            and "inherited with `execution_count: 0`" in final_report
        ),
    }
    _assert_equal(round(seam_seconds), 27, "C-G02-012 seam duration")
    _assert_equal(round(fix_to_close_seconds), 21935, "C-G02-012 orchestration gap")
    _assert_equal(
        (close_stats["file_touches"], close_stats["added_lines"]),
        (16, 362),
        "C-G02-012 close payload",
    )
    _assert_equal(
        (
            c012["one_time_adapter_observation_recorded"],
            c012["adapter_did_no_deploy_or_access_work"],
        ),
        (True, True),
        "C-G02-012 adapter observation",
    )

    ab_commits = _git("rev-list", "--reverse", f"{AB_START}..{AB_END}").splitlines()
    ab_numstat: list[tuple[int, int, str]] = []
    for line in _git("diff", "--numstat", AB_START, AB_END).splitlines():
        added, deleted, path = line.split("\t", 2)
        ab_numstat.append((int(added), int(deleted), path))
    ab = {
        "commits": len(ab_commits),
        "subjects": [_git("show", "-s", "--format=%s", sha).strip() for sha in ab_commits],
        "paths": sorted(row[2] for row in ab_numstat),
        "added_lines": sum(row[0] for row in ab_numstat),
        "deleted_lines": sum(row[1] for row in ab_numstat),
    }
    _assert_equal(
        (ab["commits"], ab["paths"], ab["added_lines"], ab["deleted_lines"]),
        (
            5,
            ["src/faultwitness_dev/g02_lab.py", "tests/g02/test_g02_lab.py"],
            540,
            5,
        ),
        "natural A/B",
    )

    return {
        "proof": "P0-g02-history-cost",
        "history_range": HISTORY_RANGE,
        "classification_rule_order": [
            "lifecycle/binding by chore(iteration|work-item|eval) subject",
            "evidence-only by docs(eval) or test(g02) subject",
            "other by revert/reapply subject",
            "semantic by src/tests/deploy/config/migrations or lockfile path",
            "policy/docs fallback",
        ],
        "classification_counts": counts,
        "commit_count": len(commits),
        "governance_status_intent_commits": len(governance_status_intent),
        "src_or_tests_touched_commits": len(implementation_or_test),
        "semantic_55_to_57_resolution": discrepancy,
        "non_implementation_file_touches": non_implementation_touches,
        "total_file_touches": total_touches,
        "access_58": access | {"shas": access_commits},
        "i0034": i0034 | {"shas": i0034_commits},
        "c_g02_012": c012,
        "natural_ab": ab | {"shas": ab_commits},
        "commits": [
            {
                "sha": row["sha"],
                "subject": row["subject"],
                "category": row["category"],
            }
            for row in commits
        ],
        "status": "pass",
    }


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--output", type=Path)
    args = argument_parser.parse_args()
    rendered = json.dumps(build_report(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
