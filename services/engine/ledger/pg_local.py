"""Portable PostgreSQL 17 for local development and tests: no Docker and no system install.

The binaries are the zonky "embedded-postgres-binaries" builds on Maven Central (official
PostgreSQL sources, packaged per platform). They are cached outside the repo in
``~/.cache/fiona`` (override with FIONA_CACHE_DIR). One shared server runs on a fixed port
(FIONA_PG_PORT, default 54329) and accepts only localhost connections with trust auth.

Set DATABASE_URL to use any other PostgreSQL 17 instead; this module is then never used.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PG_VERSION = "17.11.0"
MAVEN = "https://repo1.maven.org/maven2/io/zonky/test/postgres"
# SHA-256 of the jar, pinned after the first verified download. Platforms without a pin are
# checked against Maven Central's published SHA-1 instead.
PINNED_SHA256 = {
    "windows-amd64": "98040fae18dd9633ff95932125b0cecf0a45a1a9312e216e2a33ad03a31d4251",
    "linux-amd64": "0dd7b72b6f335b8ecfb355fa24c5781e8a93edd09880bb77eb52ebbf29b3e96d",
}
PLATFORMS = {
    ("windows", "amd64"): "windows-amd64",
    ("windows", "x86_64"): "windows-amd64",
    ("linux", "x86_64"): "linux-amd64",
    ("linux", "amd64"): "linux-amd64",
    ("linux", "aarch64"): "linux-arm64v8",
    ("darwin", "arm64"): "darwin-arm64v8",
    ("darwin", "x86_64"): "darwin-amd64",
}
SUPERUSER = "postgres"


def port() -> int:
    return int(os.environ.get("FIONA_PG_PORT", "54329"))


def cache_dir() -> Path:
    return Path(os.environ.get("FIONA_CACHE_DIR", Path.home() / ".cache" / "fiona"))


def install_dir() -> Path:
    return cache_dir() / f"postgres-{PG_VERSION}"


def data_dir() -> Path:
    return cache_dir() / "pgdata-17"


def log_file() -> Path:
    return cache_dir() / "postgres.log"


def _exe(name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    return str(install_dir() / "bin" / f"{name}{suffix}")


def _platform_id() -> str:
    key = (platform.system().lower(), platform.machine().lower())
    if key not in PLATFORMS:
        raise RuntimeError(f"No portable PostgreSQL build for {key}; set DATABASE_URL instead")
    return PLATFORMS[key]


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 (fixed https URL)
        return response.read()


def install() -> Path:
    """Download, verify and unpack the binaries once. Returns the install directory."""
    target = install_dir()
    if (target / "bin").is_dir():
        return target
    plat = _platform_id()
    artifact = f"embedded-postgres-binaries-{plat}"
    jar_url = f"{MAVEN}/{artifact}/{PG_VERSION}/{artifact}-{PG_VERSION}.jar"
    jar = _download(jar_url)
    if plat in PINNED_SHA256:
        actual = hashlib.sha256(jar).hexdigest()
        if actual != PINNED_SHA256[plat]:
            raise RuntimeError(f"Checksum mismatch for {jar_url}: {actual}")
    else:
        expected = _download(jar_url + ".sha1").decode().split()[0]
        if hashlib.sha1(jar).hexdigest() != expected:  # noqa: S324 (Maven publishes SHA-1)
            raise RuntimeError(f"Checksum mismatch for {jar_url}")
    with zipfile.ZipFile(io.BytesIO(jar)) as archive:
        txz_name = next(n for n in archive.namelist() if n.endswith(".txz"))
        txz = archive.read(txz_name)
    staging = target.with_name(target.name + ".partial")
    staging.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(txz), mode="r:xz") as tar:
        tar.extractall(staging, filter="data")
    staging.rename(target)
    return target


def is_running() -> bool:
    if not (data_dir() / "PG_VERSION").exists():
        return False
    result = subprocess.run(
        [_exe("pg_ctl"), "status", "-D", str(data_dir())], capture_output=True, check=False
    )
    return result.returncode == 0


def start() -> None:
    """Install if needed, initialise the cluster once, and start the shared server."""
    install()
    if not (data_dir() / "PG_VERSION").exists():
        data_dir().parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                _exe("initdb"),
                "-D",
                str(data_dir()),
                "-U",
                SUPERUSER,
                "-A",
                "trust",
                "-E",
                "UTF8",
                "--locale=C",
                "--no-instructions",
            ],
            check=True,
            capture_output=True,
        )
    if is_running():
        return
    options = f"-p {port()} -c listen_addresses=localhost -c synchronous_commit=off"
    flags = 0
    if os.name == "nt":  # keep the server alive after this process and its console exit
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.run(
        [
            _exe("pg_ctl"),
            "start",
            "-D",
            str(data_dir()),
            "-l",
            str(log_file()),
            "-o",
            options,
            "-w",
            "-t",
            "60",
        ],
        check=True,
        capture_output=True,
        creationflags=flags,
    )


def stop() -> None:
    if is_running():
        subprocess.run(
            [_exe("pg_ctl"), "stop", "-D", str(data_dir()), "-m", "fast", "-w"],
            check=True,
            capture_output=True,
        )


def dsn(dbname: str) -> str:
    return f"postgresql://{SUPERUSER}@localhost:{port()}/{dbname}?connect_timeout=10"
