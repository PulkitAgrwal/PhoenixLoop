#!/usr/bin/env python3
"""Probe the Gemini API for which models are available and which have quota.

Reads ``GOOGLE_API_KEY`` from the project ``.env`` file (or the environment),
calls ``models.list``, then optionally sends a minimal ``generateContent``
request to every model that supports it. Each model is classified as:

    OK            200 response, has quota
    EXHAUSTED     429 RESOURCE_EXHAUSTED (free tier zeroed or daily cap hit)
    UNSUPPORTED   Model does not support ``generateContent``
    ERROR         Any other failure (network, auth, 400-class)

Usage:
    python scripts/check_gemini_models.py                # list + probe
    python scripts/check_gemini_models.py --list-only    # list only, no probing
    python scripts/check_gemini_models.py --filter flash # probe only flash models
    python scripts/check_gemini_models.py --key AQ...    # override the key
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
PROBE_TIMEOUT = 15.0
LIST_TIMEOUT = 15.0
PROBE_WORKERS = 8


def load_api_key(explicit: str | None) -> str:
    """Resolve the API key from --key, env var, or project .env in that order."""
    if explicit:
        return explicit
    env_key = os.environ.get("GOOGLE_API_KEY")
    if env_key:
        return env_key

    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                return line.split("=", 1)[1].strip()

    sys.exit(
        "GOOGLE_API_KEY not found. Pass --key, export GOOGLE_API_KEY, or add "
        f"it to {env_file}."
    )


def list_models(api_key: str) -> list[dict]:
    """Call models.list and return the raw list of model dicts."""
    url = f"{API_BASE}/models?key={api_key}&pageSize=200"
    try:
        with urlopen(Request(url), timeout=LIST_TIMEOUT) as response:
            payload = json.load(response)
    except HTTPError as exc:
        sys.exit(f"models.list HTTP {exc.code}: {exc.read().decode()[:300]}")
    except URLError as exc:
        sys.exit(f"models.list network error: {exc.reason}")
    return payload.get("models", [])


def probe_model(api_key: str, model_name: str) -> tuple[str, str]:
    """Send a 1-token generateContent request. Returns (status, detail)."""
    short = model_name.replace("models/", "")
    url = f"{API_BASE}/models/{short}:generateContent?key={api_key}"
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": "hi"}]}],
            "generationConfig": {
                "maxOutputTokens": 1,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode()
    request = Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urlopen(request, timeout=PROBE_TIMEOUT):
            return ("OK", "")
    except HTTPError as exc:
        body_text = exc.read().decode()
        try:
            err = json.loads(body_text).get("error", {})
            status = err.get("status", "")
            message = err.get("message", "")[:80]
        except json.JSONDecodeError:
            status, message = "", body_text[:80]
        if exc.code == 429 or status == "RESOURCE_EXHAUSTED":
            return ("EXHAUSTED", message)
        return (f"ERROR {exc.code}", f"{status} {message}".strip())
    except URLError as exc:
        return ("ERROR net", str(exc.reason))


STATUS_ORDER = {"OK": 0, "EXHAUSTED": 1, "UNSUPPORTED": 2}


def format_table(rows: list[tuple[str, str, str, int, int]]) -> str:
    """Render the result rows as a fixed-width table."""
    header = ("MODEL", "STATUS", "DETAIL", "IN_TOK", "OUT_TOK")
    widths = [
        max(len(header[0]), max((len(r[0]) for r in rows), default=0)),
        max(len(header[1]), max((len(r[1]) for r in rows), default=0)),
        max(len(header[2]), 50),
        max(len(header[3]), 7),
        max(len(header[4]), 7),
    ]
    line = (
        f"{header[0]:<{widths[0]}}  "
        f"{header[1]:<{widths[1]}}  "
        f"{header[2]:<{widths[2]}}  "
        f"{header[3]:>{widths[3]}}  "
        f"{header[4]:>{widths[4]}}"
    )
    out = [line, "-" * len(line)]
    for name, status, detail, in_tok, out_tok in rows:
        out.append(
            f"{name:<{widths[0]}}  "
            f"{status:<{widths[1]}}  "
            f"{detail[:widths[2]]:<{widths[2]}}  "
            f"{in_tok:>{widths[3]}}  "
            f"{out_tok:>{widths[4]}}"
        )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", help="API key (overrides env / .env)")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="List models without sending a probe request",
    )
    parser.add_argument(
        "--filter",
        default="",
        help="Only include models whose name contains this substring",
    )
    args = parser.parse_args()

    api_key = load_api_key(args.key)
    models = list_models(api_key)
    if args.filter:
        models = [m for m in models if args.filter in m["name"]]

    rows: list[tuple[str, str, str, int, int]] = []
    probeable: list[dict] = []
    for model in models:
        name = model["name"].replace("models/", "")
        methods = model.get("supportedGenerationMethods", [])
        in_tok = int(model.get("inputTokenLimit", 0))
        out_tok = int(model.get("outputTokenLimit", 0))
        if "generateContent" not in methods or args.list_only:
            status = "LISTED" if args.list_only else "UNSUPPORTED"
            detail = ",".join(methods) if args.list_only else "no generateContent"
            rows.append((name, status, detail, in_tok, out_tok))
        else:
            probeable.append(model)

    if not args.list_only and probeable:
        print(
            f"Probing {len(probeable)} models with 1-token generateContent calls...",
            file=sys.stderr,
        )
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=PROBE_WORKERS
        ) as pool:
            futures = {
                pool.submit(probe_model, api_key, m["name"]): m for m in probeable
            }
            for future in concurrent.futures.as_completed(futures):
                model = futures[future]
                name = model["name"].replace("models/", "")
                status, detail = future.result()
                rows.append(
                    (
                        name,
                        status,
                        detail,
                        int(model.get("inputTokenLimit", 0)),
                        int(model.get("outputTokenLimit", 0)),
                    )
                )

    rows.sort(key=lambda r: (STATUS_ORDER.get(r[1], 9), r[0]))
    print(format_table(rows))

    if not args.list_only:
        counts: dict[str, int] = {}
        for _, status, *_ in rows:
            counts[status] = counts.get(status, 0) + 1
        print()
        print("Summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
