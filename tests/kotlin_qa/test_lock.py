"""Tests for the run lock: one kotlin-qa run at a time in a work tree."""

import os
import subprocess
from pathlib import Path

import pytest

from kotlin_qa.config import QA_DIR_NAME, load_config
from kotlin_qa.lock import LockHeldError, lock_path, run_lock


def test_the_lock_lives_in_the_git_directory(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = lock_path(load_config(tmp_path))
    assert path == tmp_path / ".git" / "kotlin-qa" / "run.lock"


def test_outside_git_there_is_no_lock(tmp_path: Path) -> None:
    assert lock_path(load_config(tmp_path)) is None


def test_a_lock_switched_off_in_the_configuration(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / QA_DIR_NAME).mkdir()
    (tmp_path / QA_DIR_NAME / "kotlin-qa.toml").write_text("lock = false\n", "utf-8")
    assert lock_path(load_config(tmp_path)) is None


def test_a_second_run_is_refused_while_the_first_holds_the_lock(tmp_path: Path) -> None:
    path = tmp_path / "run" / "qa.lock"
    with run_lock(path):
        assert path.read_text(encoding="utf-8") == f"pid={os.getpid()}\n"
        with pytest.raises(LockHeldError, match=f"pid={os.getpid()}"), run_lock(path):
            pass
    with run_lock(path):
        pass


def test_no_path_is_no_lock() -> None:
    with run_lock(None):
        pass
