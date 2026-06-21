from __future__ import annotations

import subprocess
from pathlib import Path


PRIVATE_TRACKED_PATTERNS = [
    "personal-finance/imports/processed/*.pdf",
    "personal-finance/imports/to_import/*",
    "personal-finance/imports/failed/*",
    "personal-finance/data/*.duckdb",
    "personal-finance/backups/*",
    "personal-finance/rules/merchant_rules.yml",
]


def tracked_files_for(pattern: str) -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "ls-files", "--", pattern],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        path
        for path in result.stdout.splitlines()
        if not path.endswith("/.gitkeep")
    ]


def test_private_finance_artifacts_are_not_tracked():
    tracked = []
    for pattern in PRIVATE_TRACKED_PATTERNS:
        tracked.extend(tracked_files_for(pattern))

    assert tracked == []


def test_desktop_package_does_not_bundle_runtime_yaml_rules():
    project_root = Path(__file__).resolve().parents[1]
    spec_text = (project_root / "packaging" / "personal_finance_app.spec").read_text()

    assert '.yml"' not in spec_text
