"""
reCAPTCHA v3 bypass with SYNTHETIC fingerprints, grounded in the webworker.js
deobfuscation (see experiment/DEOBFUSCATION_WRITEUP.md).

WARNING: README.md documents that synthetic fingerprints LOWER the score —
Google detects fake motion data. This file exists to make that claim testable,
not to contradict it. Run test.py to compare against baseline.

Improvements over tools/generate_fingerprint.py + bypass.py, each tied to a
finding in the writeup:

- Field 5: positive decimal string (real capture was 1677000260, not negative).
- Field 20: base64 JSON matching reload_req.bin shape (timing triples + perf + hosts).
- Field 25: count buckets [[[5006,n],[64607,1],[35837,1]]] — not a fake path trail.
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


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _gen_field_5(rng: random.Random) -> str:
    # Real capture field 5 was positive "1677000260", not negative.
    base = int(time.time()) ^ rng.getrandbits(20)
    return str(base | 1_000_000_000)


def _origin_host(url: str) -> str:
    q = parse_qs(urlparse(url).query)
    co = q.get("co", [None])[0]
    if not co:
        return "2captcha.com"
    try:
        pad = "=" * (-len(co) % 4)
        origin = base64.urlsafe_b64decode(co + pad).decode("utf-8", "replace")
        return urlparse(origin).hostname or "2captcha.com"
    except Exception:
        return "2captcha.com"


def _gen_field_20(rng: random.Random, host: str) -> str:
    # Real capture shape (reload_req.bin, base64-decoded after head fix):
    # [[[3,1297],[1,187,1373],[2,81,1666]],null,
    #  [null,null,null,[7,3.42...,15],[225,0.11...,6],0,0,0],
    #  hosts,[1,441]]
    buckets = [
        [3, rng.randint(800, 2500)],
        [1, rng.randint(100, 400), rng.randint(800, 2500)],
        [2, rng.randint(40, 150), rng.randint(1000, 2500)],
    ]
    inner = [
        rng.choice([6, 7, 8, 15]),
        round(rng.uniform(3.0, 8.0), 16),
        rng.uniform(0.0008, 0.0025),
        15,
    ]
    inner2 = [
        rng.randint(200, 250),
        round(rng.uniform(0.04, 0.15), 16),
        rng.uniform(0.0005, 0.002),
        rng.choice([1, 4, 5, 6]),
    ]
    hosts = [
        host,
        "static.cloudflareinsights.com",
        "www.google.com",
        "www.gstatic.com",
    ]
    if rng.random() < 0.5:
        hosts.insert(2, "cdn.respond.io")
    data = [
        buckets,
        None,
        [None, None, None, inner, inner2, 0, 0, 0],
        hosts,
        [1, rng.randint(400, 500)],
    ]
    return _b64(json.dumps(data, separators=(",", ":")))


def _gen_field_25(rng: random.Random) -> str:
    # Real capture: [[[5006,119],[64607,1],[35837,1]]] — count buckets only.
    data = [[[5006, rng.randint(40, 160)], [64607, 1], [35837, 1]]]
    return _b64(json.dumps(data, separators=(",", ":")))


def generate_synthetic_fingerprint(
    seed: int | None = None, *, host: str = "2captcha.com"
) -> dict:
    rng = random.Random(seed)
    return {
        "5": _gen_field_5(rng),
        "20": _gen_field_20(rng, host),
        "25": _gen_field_25(rng),
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
    host: str = "2captcha.com",
    reason: str = "q",
) -> bytes:
    """Protobuf reload body with a fresh synthetic fingerprint per call."""
    fp = generate_synthetic_fingerprint(host=host)
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
        self._host = _origin_host(target_url)

    def _do_reload(self, recaptcha_token, k_value, co_value, v_value, hl_value):
        time.sleep(random.uniform(0.35, 1.4))
        post_url = reload_url_from_anchor(self.target_url, k_value)
        data = encode_synthetic_reload_body(
            v=v_value,
            c=recaptcha_token,
            k=k_value,
            action=self.action,
            anchor_ms=self._anchor_ms,
            execute_ms=self._execute_ms,
            host=self._host,
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
    host = _origin_host(url)
    fp = generate_synthetic_fingerprint(host=host)
    print(f"host: {host}")
    print(f"field 5:  {fp['5']}")
    print(f"field 20: {fp['20'][:60]}...")
    print(f"field 25: {fp['25']}")
    tok = ReCaptchaV3SyntheticBypass(url, action=action).bypass()
    print(f"token: {tok}")
