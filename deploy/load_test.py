"""Load / performance test for a deployed EDI-Converter.

Answers the question the deployment sizing depends on: how many claims per
second does one container handle, and where does latency go under concurrency?
Parsing is CPU-bound and synchronous, so throughput is governed by the CPU limit
set in docker-compose — this measures the real number rather than guessing it.

Standard library only (threads + urllib), so it runs anywhere Python does.

    python load_test.py http://localhost:8088 --concurrency 8 --requests 400
    python load_test.py https://edi.example.com --endpoint /edi/fhir --duration 30

On Windows/Git Bash, prefix with MSYS_NO_PATHCONV=1 or the shell rewrites the
leading slash of --endpoint into a Windows path before Python ever sees it.

Exits 1 if the error rate exceeds --max-error-rate (default 1%), so it can gate
a release in CI.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from smoke_test import SAMPLE_837P, multipart, request


class Recorder:
    """Thread-safe collection of per-request outcomes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.latencies: list[float] = []
        self.statuses: Counter[str] = Counter()

    def record(self, seconds: float, status: str) -> None:
        with self._lock:
            self.latencies.append(seconds)
            self.statuses[status] += 1


def one_request(url: str, body: bytes, ctype: str, rec: Recorder, insecure: bool) -> None:
    started = time.perf_counter()
    try:
        status, _, _ = request(url, method="POST", data=body,
                               headers={"Content-Type": ctype}, timeout=120,
                               insecure=insecure)
        rec.record(time.perf_counter() - started, str(status))
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        rec.record(time.perf_counter() - started, f"error:{type(exc).__name__}")


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile — no interpolation, no numpy."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(pct / 100 * len(ordered) + 0.5) - 1))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--api-path", default="/api")
    parser.add_argument("--endpoint", default="/edi/validate",
                        help="endpoint under test (default: /edi/validate — the heaviest common path)")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--requests", type=int, default=200, help="total requests (ignored with --duration)")
    parser.add_argument("--duration", type=int, default=0, help="run for N seconds instead of a fixed count")
    parser.add_argument("--max-error-rate", type=float, default=1.0, help="percent, above which this exits 1")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}{args.api_path.rstrip('/')}{args.endpoint}"
    body, ctype = multipart("file", "claim.edi", SAMPLE_837P.encode())
    rec = Recorder()

    print(f"\nTarget      {url}")
    print(f"Payload     {len(SAMPLE_837P)} bytes (837P, 23 segments)")
    print(f"Concurrency {args.concurrency}")
    print("Warming up…")
    one_request(url, body, ctype, Recorder(), args.insecure)   # discard: JIT/connection/import warmup

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        if args.duration:
            print(f"Running for {args.duration}s…\n")
            deadline = started + args.duration
            pending: list = []
            while time.perf_counter() < deadline:
                if len(pending) < args.concurrency * 2:
                    pending.append(pool.submit(one_request, url, body, ctype, rec, args.insecure))
                pending = [f for f in pending if not f.done()]
            for future in pending:
                future.result()
        else:
            print(f"Sending {args.requests} requests…\n")
            futures = [pool.submit(one_request, url, body, ctype, rec, args.insecure)
                       for _ in range(args.requests)]
            for future in futures:
                future.result()
    elapsed = time.perf_counter() - started

    total = sum(rec.statuses.values())
    ok = rec.statuses.get("200", 0)
    failed = total - ok
    error_rate = (failed / total * 100) if total else 100.0
    ms = [s * 1000 for s in rec.latencies]

    print(f"Requests     {total} in {elapsed:.1f}s")
    print(f"Throughput   {total / elapsed:.1f} req/s")
    print(f"Success      {ok}/{total} ({100 - error_rate:.1f}%)")
    if failed:
        for status, count in sorted(rec.statuses.items()):
            if status != "200":
                print(f"  {status}: {count}")
    print(f"\nLatency (ms)")
    print(f"  min        {min(ms):.0f}")
    print(f"  mean       {statistics.fmean(ms):.0f}")
    print(f"  p50        {percentile(ms, 50):.0f}")
    print(f"  p90        {percentile(ms, 90):.0f}")
    print(f"  p95        {percentile(ms, 95):.0f}")
    print(f"  p99        {percentile(ms, 99):.0f}")
    print(f"  max        {max(ms):.0f}")

    if error_rate > args.max_error_rate:
        print(f"\nFAIL error rate {error_rate:.2f}% exceeds the {args.max_error_rate}% budget")
        return 1
    print(f"\nPASS error rate {error_rate:.2f}% within the {args.max_error_rate}% budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
