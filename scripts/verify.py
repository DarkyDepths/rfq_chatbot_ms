"""Authoritative local/CI quality verification entrypoint."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_WHITELIST = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "SystemRoot",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TMP",
    "TEMP",
)


def _run_step(name: str, command: list[str], env: dict[str, str]) -> None:
    print(f"\n==> {name}")
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _build_verify_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in ENV_WHITELIST}
    env["PYTHONPATH"] = "."
    env["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite:///./.quality_gate.db")
    return env


def main() -> None:
    env = _build_verify_env()

    python = sys.executable

    _run_step("Lint (ruff)", [python, "-m", "ruff", "check", "src", "tests", "scripts"], env)
    _run_step("Tests (pytest)", [python, "-m", "pytest", "-q"], env)
    _run_step(
        "Startup sanity (app import/create)",
        [python, "-c", "from src.app import create_app; create_app(); print('startup-ok')"],
        env,
    )

    print("\nQuality verification passed.")


if __name__ == "__main__":
    main()
