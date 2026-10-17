"""Tests for the pinned tools: where they are found, and how one is installed."""

import hashlib
import io
import tarfile

import pytest

from kotlin_qa.toolchain import (
    PINNED,
    ChecksumError,
    ToolMissingError,
    cache_dir,
    install,
    platform_key,
    resolve,
)


def archive(name: str, content: bytes = b"#!/bin/sh\n") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_every_pinned_tool_has_a_checksum_for_each_supported_platform() -> None:
    assert {"ktlint", "actionlint", "gitleaks", "shellcheck", "zizmor"} <= set(PINNED)
    for tool in PINNED.values():
        assert tool.version
        for key in ("linux-x86_64", "linux-aarch64"):
            asset = tool.assets[key]
            assert len(asset.sha256) == 64
            assert tool.version in asset.url or tool.name == "ktlint"
            assert asset.url.startswith("https://github.com/")


def test_the_platform_key_names_the_os_and_machine() -> None:
    assert platform_key("Linux", "x86_64") == "linux-x86_64"
    assert platform_key("Linux", "arm64") == "linux-aarch64"
    assert platform_key("Linux", "aarch64") == "linux-aarch64"


def test_the_cache_is_where_kotlin_qa_home_says_else_the_user_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KOTLIN_QA_HOME", str(tmp_path / "home"))
    assert cache_dir() == tmp_path / "home"
    monkeypatch.delenv("KOTLIN_QA_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cache_dir() == tmp_path / ".cache" / "kotlin-qa"


def test_the_environment_variable_wins_over_the_cache_and_the_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KOTLIN_QA_HOME", str(tmp_path))
    monkeypatch.setenv("SHELLCHECK", "/chosen/shellcheck")
    assert resolve("shellcheck") == "/chosen/shellcheck"


def test_an_installed_copy_wins_over_the_path(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SHELLCHECK", raising=False)
    monkeypatch.setenv("KOTLIN_QA_HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/nowhere")
    installed = tmp_path / "shellcheck" / PINNED["shellcheck"].version / "shellcheck"
    installed.parent.mkdir(parents=True)
    installed.write_text("x", "utf-8")
    assert resolve("shellcheck") == str(installed)


def test_the_path_is_the_last_resort(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SHELLCHECK", raising=False)
    monkeypatch.setenv("KOTLIN_QA_HOME", str(tmp_path / "empty"))
    found = tmp_path / "bin" / "shellcheck"
    found.parent.mkdir()
    found.write_text("x", "utf-8")
    found.chmod(0o755)
    monkeypatch.setenv("PATH", str(found.parent))
    assert resolve("shellcheck") == str(found)


def test_a_missing_tool_names_the_variable_and_the_command_that_installs_it(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("GITLEAKS", raising=False)
    monkeypatch.setenv("KOTLIN_QA_HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/nowhere")
    with pytest.raises(ToolMissingError) as raised:
        resolve("gitleaks")
    assert "kotlin-qa install-tools" in str(raised.value)
    assert "GITLEAKS" in str(raised.value)


def test_install_verifies_the_checksum_extracts_the_binary_and_marks_it_executable(
    monkeypatch, tmp_path
) -> None:
    data = archive("gitleaks")
    tool = PINNED["gitleaks"]
    monkeypatch.setattr(tool.assets["linux-x86_64"], "sha256", hashlib.sha256(data).hexdigest())
    path = install("gitleaks", tmp_path, "linux-x86_64", fetch=lambda url: data)
    assert path == tmp_path / "gitleaks" / tool.version / "gitleaks"
    assert path.read_bytes() == b"#!/bin/sh\n"
    assert path.stat().st_mode & 0o111


def test_a_download_with_the_wrong_checksum_installs_nothing(tmp_path) -> None:
    with pytest.raises(ChecksumError, match="gitleaks"):
        install("gitleaks", tmp_path, "linux-x86_64", fetch=lambda url: archive("gitleaks"))
    assert not (tmp_path / "gitleaks").exists()


def test_installing_twice_downloads_once(monkeypatch, tmp_path) -> None:
    data = archive("zizmor")
    monkeypatch.setattr(
        PINNED["zizmor"].assets["linux-x86_64"], "sha256", hashlib.sha256(data).hexdigest()
    )
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return data

    install("zizmor", tmp_path, "linux-x86_64", fetch=fetch)
    install("zizmor", tmp_path, "linux-x86_64", fetch=fetch)
    assert len(calls) == 1


def test_ktlint_is_a_single_file_not_an_archive(monkeypatch, tmp_path) -> None:
    script = b"#!/bin/sh\necho ktlint\n"
    monkeypatch.setattr(
        PINNED["ktlint"].assets["linux-x86_64"], "sha256", hashlib.sha256(script).hexdigest()
    )
    path = install("ktlint", tmp_path, "linux-x86_64", fetch=lambda url: script)
    assert path.read_bytes() == script
    assert path.stat().st_mode & 0o111
