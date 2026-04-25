"""Smoke: concurrent sessions + rate-limit headers via the HTTP API.

Validates Issue #33 wiring:
  * many parallel /reset + /step calls succeed against the async session manager
  * /step responses expose RateLimit-* headers from slowapi
  * exceeding the per-IP burst eventually returns HTTP 429

Run with:
  python scripts/smoke_concurrency_ratelimit.py --base http://127.0.0.1:7874
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import urllib.error
import urllib.request


def _request(
    method: str, url: str, *, body: dict | None = None, headers: dict | None = None
) -> tuple[int, dict[str, str], Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else None
            return resp.status, dict(resp.headers), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp is not None else ""
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw
        return exc.code, dict(exc.headers or {}), payload


async def _spawn_session(base: str, idx: int) -> str:
    loop = asyncio.get_event_loop()
    status, _, payload = await loop.run_in_executor(
        None,
        lambda: _request(
            "POST",
            f"{base}/reset",
            body={"task_name": "single-service-alert", "seed": 100 + idx},
        ),
    )
    assert status == 200, f"reset {idx} returned {status}: {payload}"
    return payload["session_id"]


async def concurrency_smoke(base: str, n: int) -> None:
    sids = await asyncio.gather(*[_spawn_session(base, i) for i in range(n)])
    assert len(set(sids)) == n, "expected unique session_ids per concurrent reset"
    print(f"[concurrency] spawned {n} sessions, all unique: OK")

    async def _step(sid: str) -> int:
        loop = asyncio.get_event_loop()
        status, _, _ = await loop.run_in_executor(
            None,
            lambda: _request(
                "POST",
                f"{base}/step",
                body={"command": "check_metrics service=api metric=latency"},
                headers={"X-Session-Id": sid},
            ),
        )
        return status

    statuses = await asyncio.gather(*[_step(sid) for sid in sids])
    bad = [s for s in statuses if s != 200]
    assert not bad, f"unexpected step statuses under concurrency: {bad}"
    print(f"[concurrency] {n} concurrent /step calls all 200: OK")


def ratelimit_smoke(base: str) -> None:
    status, headers, _ = _request(
        "POST",
        f"{base}/reset",
        body={"task_name": "single-service-alert", "seed": 7},
    )
    assert status == 200
    sid = _request(
        "POST", f"{base}/reset", body={"task_name": "single-service-alert", "seed": 8}
    )[2]["session_id"]

    rl_keys = [
        k
        for k in headers
        if k.lower().startswith("ratelimit") or k.lower().startswith("x-ratelimit")
    ]
    print(f"[ratelimit] /reset response RateLimit-* headers: {rl_keys}")
    assert rl_keys, "expected slowapi to emit RateLimit-* headers on /reset"

    saw_429 = False
    retry_after: str | None = None
    for i in range(120):
        status, hdr, body = _request(
            "POST",
            f"{base}/step",
            body={"command": "check_metrics service=api metric=latency"},
            headers={"X-Session-Id": sid},
        )
        if status == 429:
            saw_429 = True
            retry_after = hdr.get("Retry-After") or hdr.get("retry-after")
            print(f"[ratelimit] hit 429 after {i + 1} bursts: OK")
            print(f"[ratelimit] retry-after header: {retry_after}")
            break
    assert saw_429, "expected /step burst to eventually return HTTP 429"
    assert retry_after is not None, "expected 429 response to include Retry-After"


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:7874")
    p.add_argument("-n", "--concurrent", type=int, default=8)
    args = p.parse_args()

    await concurrency_smoke(args.base, args.concurrent)
    ratelimit_smoke(args.base)

    print("\n[PASS] concurrency + rate-limit smoke succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
