"""The pinned tools kotlin-qa runs, and how each is found or installed.

A tool is resolved from, in order: its environment variable (KTLINT, SHELLCHECK, ...), the copy
`kotlin-qa install-tools` put in the cache, then PATH. Installing downloads the release asset
named here, refuses it unless its SHA-256 matches the pin, and unpacks it. The pins are the
point: a laptop and CI run the same build of every tool, and a new release reaches a project
only as a deliberate bump of this package.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_RELEASES = "https://github.com"
_EXECUTABLE = 0o755


class ToolMissingError(Exception):
    """A tool a lane needs is not installed; the message says how to supply it."""


class ChecksumError(Exception):
    """A downloaded asset does not match its pinned SHA-256, so nothing was installed."""


@dataclass
class Asset:
    """One downloadable file: where it is and the SHA-256 it must have."""

    url: str
    sha256: str


@dataclass
class Pinned:
    """A tool at one version, with an asset for each platform that has one."""

    name: str
    version: str
    assets: dict[str, Asset] = field(default_factory=dict)
    archive: bool = True

    @property
    def variable(self) -> str:
        """Return the environment variable that names this tool's binary."""
        return self.name.upper()


def _github(owner_repo: str, tag: str, asset: str) -> str:
    return f"{_RELEASES}/{owner_repo}/releases/download/{tag}/{asset}"


def _pins() -> dict[str, Pinned]:
    ktlint = Asset(
        _github("ktlint/ktlint", "1.8.0", "ktlint"),
        "a3fd620207d5c40da6ca789b95e7f823c54e854b7fade7f613e91096a3706d75",
    )
    return {
        "ktlint": Pinned(
            "ktlint", "1.8.0", {"linux-x86_64": ktlint, "linux-aarch64": ktlint}, archive=False
        ),
        "actionlint": Pinned(
            "actionlint",
            "1.7.12",
            {
                "linux-x86_64": Asset(
                    _github("rhysd/actionlint", "v1.7.12", "actionlint_1.7.12_linux_amd64.tar.gz"),
                    "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
                ),
                "linux-aarch64": Asset(
                    _github("rhysd/actionlint", "v1.7.12", "actionlint_1.7.12_linux_arm64.tar.gz"),
                    "325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6",
                ),
            },
        ),
        "gitleaks": Pinned(
            "gitleaks",
            "8.30.1",
            {
                "linux-x86_64": Asset(
                    _github("gitleaks/gitleaks", "v8.30.1", "gitleaks_8.30.1_linux_x64.tar.gz"),
                    "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
                ),
                "linux-aarch64": Asset(
                    _github("gitleaks/gitleaks", "v8.30.1", "gitleaks_8.30.1_linux_arm64.tar.gz"),
                    "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
                ),
            },
        ),
        "shellcheck": Pinned(
            "shellcheck",
            "0.11.0",
            {
                "linux-x86_64": Asset(
                    _github(
                        "koalaman/shellcheck", "v0.11.0", "shellcheck-v0.11.0.linux.x86_64.tar.gz"
                    ),
                    "b7af85e41cc99489dcc21d66c6d5f3685138f06d34651e6d34b42ec6d54fe6f6",
                ),
                "linux-aarch64": Asset(
                    _github(
                        "koalaman/shellcheck", "v0.11.0", "shellcheck-v0.11.0.linux.aarch64.tar.gz"
                    ),
                    "68a8133197a50beb8803f8d42f9908d1af1c5540d4bb05fdfca8c1fa47decefc",
                ),
            },
        ),
        "zizmor": Pinned(
            "zizmor",
            "1.31.1",
            {
                "linux-x86_64": Asset(
                    _github(
                        "zizmorcore/zizmor", "v1.31.1", "zizmor-x86_64-unknown-linux-gnu.tar.gz"
                    ),
                    "d185f726bdaf92df78273217dfdd24ebcd6b0ef48cf3ce776ff5762b6e138c99",
                ),
                "linux-aarch64": Asset(
                    _github(
                        "zizmorcore/zizmor", "v1.31.1", "zizmor-aarch64-unknown-linux-gnu.tar.gz"
                    ),
                    "37eebbd5762a44f262d94875431b14a6d2402991e90a685113ea97b8b41be833",
                ),
            },
        ),
    }


PINNED = _pins()


def platform_key(system: str | None = None, machine: str | None = None) -> str:
    """Return the key of the asset for this platform, such as linux-x86_64."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = {"arm64": "aarch64", "amd64": "x86_64"}.get(machine, machine)
    return f"{system}-{machine}"


def cache_dir() -> Path:
    """Return where installed tools live: KOTLIN_QA_HOME, else ~/.cache/kotlin-qa."""
    chosen = os.environ.get("KOTLIN_QA_HOME")
    return Path(chosen) if chosen else Path.home() / ".cache" / "kotlin-qa"


def installed_path(name: str, root: Path) -> Path:
    """Return where install puts a tool, whether or not it is there yet."""
    return root / name / PINNED[name].version / name


def resolve(name: str) -> str:
    """Return the tool's path: its environment variable, an installed copy, then PATH."""
    pinned = PINNED[name]
    chosen = os.environ.get(pinned.variable)
    if chosen:
        return chosen
    copy = installed_path(name, cache_dir())
    if copy.is_file():
        return str(copy)
    found = shutil.which(name)
    if found:
        return found
    msg = (
        f"{name} is not installed; run `kotlin-qa install-tools` for the pinned {pinned.version}, "
        f"put it on PATH, or set {pinned.variable} to its path"
    )
    raise ToolMissingError(msg)


def download(url: str) -> bytes:
    """Fetch a URL over HTTPS, following redirects, and return the body."""
    done = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https", url],
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        msg = f"cannot download {url}: {done.stderr.decode(errors='replace').strip()}"
        raise OSError(msg)
    return done.stdout


def _unpack(name: str, data: bytes) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        for member in tar.getmembers():
            if member.isfile() and Path(member.name).name == name:
                handle = tar.extractfile(member)
                if handle is not None:
                    return handle.read()
    msg = f"{name}: no file named {name} in the downloaded archive"
    raise OSError(msg)


def install(
    name: str,
    root: Path,
    key: str | None = None,
    fetch: Callable[[str], bytes] = download,
) -> Path:
    """Download, verify and unpack one pinned tool under root, and return its path."""
    pinned = PINNED[name]
    key = key or platform_key()
    if key not in pinned.assets:
        msg = f"{name} has no pinned build for {key}; put it on PATH or set {pinned.variable}"
        raise ToolMissingError(msg)
    target = installed_path(name, root)
    if target.is_file():
        return target
    asset = pinned.assets[key]
    data = fetch(asset.url)
    digest = hashlib.sha256(data).hexdigest()
    if digest != asset.sha256:
        msg = f"{name} {pinned.version}: downloaded {digest}, pinned {asset.sha256}; not installed"
        raise ChecksumError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_unpack(name, data) if pinned.archive else data)
    target.chmod(_EXECUTABLE)
    return target
