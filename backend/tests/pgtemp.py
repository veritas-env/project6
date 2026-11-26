"""Throwaway PostgreSQL cluster for local tests when no APP_TEST_DATABASE_URL is given.

Looks for PostgreSQL binaries in $PG_BIN, then on PATH, then in Laragon's folder.
The cluster listens on 127.0.0.1 only, on a free port, in a temp directory, and is
deleted afterwards. Trust auth is used because nothing else can reach it."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

CANDIDATES = [
    os.environ.get("PG_BIN", ""),
    str(Path(shutil.which("pg_ctl") or "").parent) if shutil.which("pg_ctl") else "",
    r"C:\laragon\bin\postgresql\pgsql-16\bin",
]


def find_bin() -> Path:
    for c in CANDIDATES:
        if c and (Path(c) / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")).exists():
            return Path(c)
    raise RuntimeError("PostgreSQL binaries not found; set PG_BIN or APP_TEST_DATABASE_URL")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TempPostgres:
    def __init__(self) -> None:
        self.bin = find_bin()
        self.dir = Path(tempfile.mkdtemp(prefix="pgtest-"))
        self.data = self.dir / "data"
        self.port = _free_port()
        # psycopg's pure-Python mode loads libpq from PATH.
        os.environ["PATH"] = str(self.bin) + os.pathsep + os.environ.get("PATH", "")

    def _run(self, *args: str, timeout: int = 120) -> None:
        # Output goes to DEVNULL, not a pipe: on Windows the server started by pg_ctl
        # inherits pipe handles and the parent would wait for EOF forever.
        subprocess.run([str(self.bin / args[0]), *args[1:]], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=timeout)

    def start(self) -> str:
        self._run("initdb", "-D", str(self.data), "-U", "postgres", "--auth=trust", "-E", "UTF8", "--locale=C")
        self._run("pg_ctl", "-D", str(self.data), "-l", str(self.dir / "log.txt"), "-w",
                  "-o", f"-p {self.port} -h 127.0.0.1 -c fsync=off -c full_page_writes=off", "start")
        self._run("createdb", "-h", "127.0.0.1", "-p", str(self.port), "-U", "postgres", "app_test")
        return f"postgresql+psycopg://postgres@127.0.0.1:{self.port}/app_test"

    def stop(self) -> None:
        try:
            self._run("pg_ctl", "-D", str(self.data), "-m", "immediate", "-w", "stop")
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)
