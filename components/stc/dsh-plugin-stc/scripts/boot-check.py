"""One-shot DSH boot check with STC overlay (foreground supervisor)."""

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

STC = "/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/stc"
DSH = "/tmp/dsh-upstream"
HOME = "/tmp/stc-boot-fresh"
FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("pass " if cond else "FAIL ") + name + (f" :: {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    env = dict(os.environ)
    env["PATH"] = "/tmp/toolchain/node22/bin:" + env.get("PATH", "")
    env["COREPACK_HOME"] = "/tmp/toolchain/corepack-home"
    env["XDG_DATA_HOME"] = "/tmp/stc-xdg/data"
    env["XDG_CACHE_HOME"] = "/tmp/stc-xdg/cache"
    env["DSH_HOME"] = HOME
    env["STC_ROOT"] = STC
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
    shutil.rmtree(HOME, ignore_errors=True)
    log_path = Path("/tmp/stc-boot.log")
    log_file = log_path.open("w")
    srv = subprocess.Popen(
        ["pnpm", "dsh", "web", "--patch", f"{STC}/dsh-plugin-stc/cordis.dev.yml", "--no-open"],
        cwd=DSH,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    try:
        token_url = None
        for _ in range(100):
            time.sleep(2)
            with log_path.open() as f:
                txt = f.read()
            m = re.search(r"http://127\.0\.0\.1:\d+/\?token=[a-zA-Z0-9_\-]+", txt)
            if m:
                token_url = m.group(0)
                break
            if srv.poll() is not None:
                break
        check("server-up", token_url is not None, txt[-500:] if not token_url else "")
        if not token_url:
            return 1
        check("bundle-composed", "stc-bundle" in txt and "composed" in txt)
        check("no-activate-failures", "did not activate" not in txt and "startup failed" not in txt)
        time.sleep(3)
        import http.cookiejar

        nop = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )
        with nop.open(token_url, timeout=20) as r:
            page = r.read()
            check("token-200", r.status == 200, str(r.status))
        check("page-has-stc", b"stc" in page, f"{len(page)} bytes")
        try:
            fresh = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            fresh.open("http://127.0.0.1:3080/", timeout=10)
            check("untokened-401", False, "root allowed without token")
        except urllib.error.HTTPError as e:
            check("untokened-401", e.code == 401, f"code={e.code}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=20)
        except subprocess.TimeoutExpired:
            srv.kill()
        log_file.close()
    print("RESULT:", "FAIL " + str(FAILS) if FAILS else "PASS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
