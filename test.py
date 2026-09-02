"""
Live smoke test against reCAPTCHA v3 demo sites.

Run:
    uv run python test.py
    RUNS=100 uv run python test.py          # longer sample
    RUNS=100 SAVE=results.csv uv run python test.py

Raw per-run data is always appended to test_results.jsonl so long samples
can be re-analyzed without re-running.
"""

import csv
import json
import os
import random
from collections import Counter
from datetime import UTC, datetime
from statistics import mean, median, stdev
from urllib.parse import parse_qs, urlparse

import requests

from bypass import ReCaptchaV3Bypass as ReCaptchaV3BypassBase
from bypass_synthetic import ReCaptchaV3SyntheticBypass

# --- 2captcha demo ---
ANCHOR_2CAPTCHA = (
    "https://www.google.com/recaptcha/api2/anchor?ar=1"
    "&k=6Lcyqq8oAAAAAJE7eVJ3aZp_hnJcI6LgGdYD8lge"
    "&co=aHR0cHM6Ly8yY2FwdGNoYS5jb206NDQz"
    "&hl=de&v=MerVUtRoajKEbP7pLiGXkL28&size=invisible"
    "&anchor-ms=20000&execute-ms=30000&cb=wm7bpt4pmfo9"
)
VERIFY_2CAPTCHA = "https://2captcha.com/api/v1/captcha-demo/recaptcha/verify"


# --- 2captcha enterprise demo ---
ANCHOR_2CAPTCHA_ENTERPRISE = (
    "https://www.google.com/recaptcha/enterprise/anchor?ar=1"
    "&k=6Lel38UnAAAAAMRwKj9qLH2Ws4Tf2uTDQCyfgR6b"
    "&co=aHR0cHM6Ly8yY2FwdGNoYS5jb206NDQz"
    "&hl=en&v=TnA7HacJFoBWt9hnlunBlYfK&size=invisible"
    "&anchor-ms=20000&execute-ms=30000&cb=lr7k554m491h"
)
VERIFY_2CAPTCHA_ENTERPRISE = (
    "https://2captcha.com/api/v1/captcha-demo/recaptcha-enterprise/verify"
)


ADAPTERS = (
    ("base", ReCaptchaV3BypassBase),
    ("synthetic", ReCaptchaV3SyntheticBypass),
)
RUNS = int(os.environ.get("RUNS", "10"))
RESULTS_DIR = "results"
RUN_ID = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
JSONL_PATH = os.path.join(RESULTS_DIR, f"{RUN_ID}_results.jsonl")
CSV_PATH = os.path.join(RESULTS_DIR, f"{RUN_ID}_runs.csv")
RANDOMIZE_ACTIONS = False
RANDOM_ACTIONS = (
    "login",
    "submit",
    "checkout",
    "contact",
    "newsletter",
    "search",
    "demo_action",
    "examples/v3scores",
)

SITES = (
    {
        "name": "2captcha",
        "anchor": ANCHOR_2CAPTCHA,
        "action": "demo_action",
        "verify_type": "2captcha",
        "verify_url": VERIFY_2CAPTCHA,
    },
    {
        "name": "2captcha-enterprise",
        "anchor": ANCHOR_2CAPTCHA_ENTERPRISE,
        "action": "demo_action",
        "verify_type": "2captcha-enterprise",
        "verify_url": VERIFY_2CAPTCHA_ENTERPRISE,
    },
)


def site_key_from(anchor_url: str) -> str:
    return parse_qs(urlparse(anchor_url).query)["k"][0]


def verify_token(site: dict[str, str], token: str) -> dict:
    if site["verify_type"] == "2captcha":
        resp = requests.post(
            site["verify_url"],
            data={"siteKey": site_key_from(site["anchor"]), "answer": token},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "score": data.get("score"),
            "success": bool(data.get("success")),
        }

    if site["verify_type"] == "2captcha-enterprise":
        resp = requests.post(
            site["verify_url"],
            json={"siteKey": site_key_from(site["anchor"]), "token": token},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "score": data.get("riskAnalysis", {}).get("score"),
            "success": bool(
                data.get("success") and data.get("tokenProperties", {}).get("valid")
            ),
        }

    raise ValueError(f"unsupported verify type: {site['verify_type']}")


def run_once(
    site: dict[str, str],
    adapter_name: str,
    adapter_class: type[ReCaptchaV3BypassBase],
    run_number: int,
    action: str,
) -> dict:
    print(f"=== {site['name']} ({adapter_name}) run {run_number}/{RUNS} ===")
    print(f"action: {action}")
    token = adapter_class(
        site["anchor"],
        action=action,
    ).bypass()
    if not token:
        print("token: <missing>")
        return {
            "action": action,
            "score": None,
            "success": False,
            "error": "missing token",
        }
    print(f"token: {token[:60]}...")

    try:
        data = verify_token(site, token)
    except (requests.RequestException, ValueError) as exc:
        print(f"verify error: {exc}")
        return {
            "action": action,
            "score": None,
            "success": False,
            "error": str(exc),
        }

    print(f"score: {data.get('score')}  success: {data.get('success')}")
    return {
        "action": action,
        "score": data.get("score"),
        "success": bool(data.get("success")),
        "error": None,
    }


def fmt_number(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}".rstrip("0").rstrip(".")


def score_distribution(scores: list[float]) -> str:
    if not scores:
        return "-"
    counts = Counter(round(score, 2) for score in scores)
    return ", ".join(
        f"{fmt_number(score)} x {count}" for score, count in sorted(counts.items())
    )


def summarize_results(results: dict[tuple[str, str], list[dict]]) -> None:
    rows = []
    for (site_name, adapter_name), runs in results.items():
        scores = [float(run["score"]) for run in runs if run["score"] is not None]
        errors = sum(1 for run in runs if run["error"])
        successes = sum(1 for run in runs if run["success"])
        success_rate = successes / len(runs) * 100 if runs else 0
        actions = len({run["action"] for run in runs})
        rows.append(
            [
                site_name,
                adapter_name,
                str(len(runs)),
                str(actions),
                str(len(scores)),
                str(successes),
                f"{success_rate:.0f}%",
                str(errors),
                fmt_number(mean(scores) if scores else None),
                fmt_number(median(scores) if scores else None),
                fmt_number(min(scores) if scores else None),
                fmt_number(max(scores) if scores else None),
                fmt_number(stdev(scores) if len(scores) > 1 else 0 if scores else None),
                score_distribution(scores),
            ]
        )

    headers = [
        "site",
        "adapter",
        "runs",
        "actions",
        "scored",
        "success",
        "success %",
        "errors",
        "avg",
        "median",
        "min",
        "max",
        "stdev",
        "distribution",
    ]
    widths = [
        max(len(str(row[i])) for row in [headers, *rows]) for i in range(len(headers))
    ]

    print("\n=== Comparison ===")
    print(
        "| "
        + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))
        + " |"
    )
    print("| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |")
    for row in rows:
        print(
            "| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(row))) + " |"
        )


def compare_adapters(results: dict[tuple[str, str], list[dict]]) -> None:
    """Paired base-vs-synthetic comparison per site (same IP, same session)."""
    for site_name in sorted({key[0] for key in results}):
        base = [
            float(r["score"])
            for r in results.get((site_name, "base"), [])
            if r["score"] is not None
        ]
        syn = [
            float(r["score"])
            for r in results.get((site_name, "synthetic"), [])
            if r["score"] is not None
        ]
        if not base or not syn:
            continue
        n = min(len(base), len(syn))
        diffs = [b - s for b, s in zip(base[:n], syn[:n])]
        delta = mean(diffs)
        se = stdev(diffs) / (n**0.5) if n > 1 and stdev(diffs) > 0 else 0.0
        t = delta / se if se else float("inf") if delta else 0.0
        verdict = (
            "base higher (significant)"
            if abs(t) > 2 and delta > 0
            else "synthetic higher (significant)"
            if abs(t) > 2
            else "no significant difference"
        )
        print(
            f"\n{site_name}: n={n}  base-synthetic delta={delta:+.3f} "
            f"(t≈{t:+.2f})  -> {verdict}"
        )


def save_results(results: dict[tuple[str, str], list[dict]]) -> None:
    """Write raw per-run data to results/<run_id>_results.jsonl and _runs.csv."""
    record = {
        "run_id": RUN_ID,
        "timestamp": datetime.now(UTC).isoformat(),
        "runs_per_cell": RUNS,
        "cells": {
            f"{site}|{adapter}": runs for (site, adapter), runs in results.items()
        },
    }
    with open(JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["site", "adapter", "run", "action", "score", "success", "error"]
        )
        for (site_name, adapter_name), runs in results.items():
            for i, run in enumerate(runs, start=1):
                writer.writerow(
                    [
                        site_name,
                        adapter_name,
                        i,
                        run["action"],
                        run["score"],
                        run["success"],
                        run["error"],
                    ]
                )
    print(f"per-run data saved to {JSONL_PATH} and {CSV_PATH}")


def main() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {}
    for site in SITES:
        if RANDOMIZE_ACTIONS:
            actions = [random.choice(RANDOM_ACTIONS) for _ in range(RUNS)]
        else:
            actions = [site["action"]] * RUNS
        for adapter_name, adapter_class in ADAPTERS:
            key = (site["name"], adapter_name)
            results[key] = []
            for run_number, action in enumerate(actions, start=1):
                try:
                    results[key].append(
                        run_once(
                            site,
                            adapter_name,
                            adapter_class,
                            run_number,
                            action,
                        )
                    )
                except (requests.exceptions.RequestException, ValueError) as e:
                    print(f"verification error: {e}")
                    results[key].append(
                        {
                            "action": "<error>",
                            "score": None,
                            "success": False,
                            "error": str(e),
                        }
                    )
                print()
    summarize_results(results)
    compare_adapters(results)
    save_results(results)
    print("\nDone.")


if __name__ == "__main__":
    main()
