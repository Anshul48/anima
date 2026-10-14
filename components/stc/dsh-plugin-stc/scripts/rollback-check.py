#!/usr/bin/env python3
"""Rollback mechanics check: previous-home-untouched + external store.

A. Install current bundle into H1 (fresh home), boot green.
B. Install into H2 (trial home), boot green, wipe H2.
C. Restart H1 (rollback = restart previous home), boot green.
D. External-store marker survives the H2 wipe.
E. Observe `plugin remove` behavior (recorded, not depended on).

Usage: STC_ROOT must point at the STC checkout (default: this repo).
"""

from __future__ import annotations

import contextlib
import http.cookiejar
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

STC = Path(os.environ.get("STC_ROOT", Path(__file__).resolve().parents[2]))
DSH = Path("/tmp/dsh-upstream")
FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("pass " if cond else "FAIL ") + name + (f" :: {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def base_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = "/tmp/toolchain/node22/bin:" + env.get("PATH", "")
    env["COREPACK_HOME"] = "/tmp/toolchain/corepack-home"
    env["XDG_DATA_HOME"] = "/tmp/stc-xdg/data"
    env["XDG_CACHE_HOME"] = "/tmp/stc-xdg/cache"
    env["STC_ROOT"] = str(STC)
    env["no_proxy"] = "*"
    env["NO_PROXY"] = "*"
    for k in (
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "ftp_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "FTP_PROXY",
    ):
        env.pop(k, None)
    return env


def run(argv: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


def port_free(port: int = 3080) -> bool:
    with socket.socket() as s:
        s.settimeout(2)
        try:
            s.connect(("127.0.0.1", port))
        except OSError:
            return True
        return False


def boot_green(home: Path, env: dict[str, str], tag: str) -> bool:
    env = dict(env)
    env["DSH_HOME"] = str(home)
    log_path = Path(f"/tmp/stc-rollback-{tag}.log")
    with log_path.open("w") as log_file:
        srv = subprocess.Popen(
            ["pnpm", "dsh", "web", "--no-open"],
            cwd=DSH,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            token_url = None
            for _ in range(60):
                time.sleep(2)
                txt = log_path.read_text()
                m = re.search(r"http://127\.0\.0\.1:\d+/\?token=[a-zA-Z0-9_\-]+", txt)
                if m:
                    token_url = m.group(0)
                    break
                if srv.poll() is not None:
                    break
            if token_url is None:
                return False
            if "did not activate" in txt or "startup failed" in txt:
                return False
            time.sleep(2)
            jar = http.cookiejar.CookieJar()
            nop = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar)
            )
            with nop.open(token_url, timeout=20) as r:
                return r.status == 200 and b"stc" in r.read()
        finally:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(srv.pid, signal.SIGTERM)
            try:
                srv.wait(timeout=20)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(srv.pid, signal.SIGKILL)
                srv.wait(timeout=20)
            for _ in range(30):
                if port_free():
                    break
                time.sleep(1)


def main() -> int:
    env = base_env()
    h1 = Path("/tmp/stc-rb-h1")
    h2 = Path("/tmp/stc-rb-h2")
    store = Path("/tmp/stc-rb-store")
    for p in (h1, h2, store):
        shutil.rmtree(p, ignore_errors=True)
    store.mkdir(parents=True)
    (store / "RUN-MARKER.txt").write_text("external run store survives home wipe\n")

    for home, tag in ((h1, "h1"), (h2, "h2")):
        home.mkdir(parents=True)
        env_h = dict(env)
        env_h["DSH_HOME"] = str(home)
        r = run(
            ["pnpm", "dsh", "plugin", "--profile", "web", "add", f"file:{STC}/dsh-plugin-stc"],
            env_h,
            DSH,
        )
        check(f"{tag}-install", r.returncode == 0, (r.stderr or r.stdout)[-400:])
        if r.returncode != 0:
            print("RESULT: FAIL", FAILS)
            return 1

    check("h1-boot-green", boot_green(h1, env, "h1a"))
    check("h2-boot-green", boot_green(h2, env, "h2"))
    shutil.rmtree(h2, ignore_errors=True)
    check("store-survives-wipe", (store / "RUN-MARKER.txt").exists())
    check("h1-restart-green-rollback", boot_green(h1, env, "h1b"))

    env_h = dict(env)
    env_h["DSH_HOME"] = str(h1)
    r = run(
        ["pnpm", "dsh", "plugin", "--profile", "web", "remove", "@stc/dsh-plugin-stc"],
        env_h,
        DSH,
    )
    print(f"remove-observed: rc={r.returncode} out={(r.stdout or r.stderr)[-300:]}")
    print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
