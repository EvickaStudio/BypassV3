# BypassV3 - reCAPTCHA v3 Integration Test Toolkit

![BypassV3](assets/card.png)

Browserless Python client for testing **reCAPTCHA v3** and **score-based reCAPTCHA Enterprise** integrations. Generate tokens for integration and end-to-end tests without launching a full browser, or evaluate how your server-side verification handles minimally constructed token requests.

Supports invisible, score-based flows only—it does **not** solve image, audio, checkbox, or other interactive CAPTCHA challenges.

> [!IMPORTANT]
> Use this toolkit only on applications you own, operate, or are explicitly authorized to test, or against public demo environments intended for testing. Using this repository does not grant permission to test third-party sites. See [SECURITY.md](SECURITY.md) for full scope and reporting guidelines.

## Quick Start

Requires **Python 3.12+**. The only direct runtime dependency is `requests`.

```bash
uv sync
```

### Solve from a site key and origin

When testing your own app, pass the **site key** and **origin** (`scheme://host`). BypassV3 resolves the current JS release (`v`) from `api.js` / `enterprise.js` and encodes `origin` into Google's `.`-padded base64 `co` parameter automatically:

```python
from bypass import ReCaptchaV3Bypass

# Standard reCAPTCHA v3
token = ReCaptchaV3Bypass.from_site_key(
    "YOUR_SITE_KEY",
    origin="https://app.example.test",
    action="login",
).bypass()

# reCAPTCHA Enterprise
token = ReCaptchaV3Bypass.from_site_key(
    "YOUR_ENTERPRISE_SITE_KEY",
    origin="https://app.example.test",
    action="login",
    enterprise=True,
).bypass()
```

### Solve from a captured anchor URL

You can also pass an `/api2/anchor` or `/enterprise/anchor` URL copied from browser DevTools (the reload endpoint is selected automatically from the URL):

```python
from bypass import ReCaptchaV3Bypass

anchor = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=..."

# Recommended: embed the expected action via protobuf reload
token = ReCaptchaV3Bypass(anchor, action="login").bypass()

# Optional: omit action (falls back to form-encoded reload)
token = ReCaptchaV3Bypass(anchor).bypass()

# Optional: replay captured fingerprint fields for local comparison
token = ReCaptchaV3Bypass(anchor, action="login", fingerprint_path="fingerprint.json").bypass()
```

### Synthetic fingerprints (`bypass_synthetic.py`)

`ReCaptchaV3SyntheticBypass` generates fresh synthetic fingerprint fields for each
reload without a captured fingerprint file. It is experimental and does not
guarantee a higher score.

```python
from bypass_synthetic import ReCaptchaV3SyntheticBypass

token = ReCaptchaV3SyntheticBypass.from_site_key(
    "YOUR_SITE_KEY",
    origin="https://app.example.test",
    action="login",
).bypass()
```

Add `enterprise=True` for Enterprise, or use
`ReCaptchaV3SyntheticBypass(anchor, action="login").bypass()` with a captured anchor URL.

## How It Works

reCAPTCHA v3 (`/api2/reload`) and Enterprise (`/enterprise/reload`) accept a binary **protobuf** request (`Content-Type: application/x-protobuffer`). No browser execution is needed for the token exchange itself:

1. **Fetch anchor (`GET .../anchor`)** — Extracts the `recaptcha-token` (`c`), site key (`k`), encoded origin (`co`), script version (`v`), and language (`hl`). Note that Google expects `.` instead of `=` for base64 padding in `co`; literal `=`/`%3D` causes the anchor endpoint to return an unsupported-browser page without a token.
2. **Request token (`POST .../reload?k=...`)** — Sends a minimal protobuf payload containing `v` (1), `c` (2), `reason` (6), `action` (8), and `k` (14). Google returns `["rresp","<token>",null,<ttl>,...]` prefixed with the XSSI guard `)]}'`.
3. **Verify** — Submit `<token>` to your application's backend verifier. Because `action` is bound into the token at generation time, pass the `action=` your verifier expects (if omitted, the client falls back to form-encoded mode with no action bound).

## Scores & Snapshot

Scores vary per request and depend primarily on factors outside the client: IP reputation, request rate, site-key configuration, action matching, and Google's risk model. By default, BypassV3 sends no browser automation stack or device fingerprint.

Sample from **November 11, 2026** (10 runs per site and adapter; snapshot only, not a fixed benchmark):

| Site | Adapter | Runs | Success | Average | Median | Min | Max |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Appspot | `base` | 10 | 10/10 | 0.90 | 0.90 | 0.90 | 0.90 |
| Appspot | `synthetic` | 10 | 10/10 | 0.90 | 0.90 | 0.90 | 0.90 |
| NextCaptcha | `base` | 10 | 10/10 | 0.90 | 0.90 | 0.90 | 0.90 |
| NextCaptcha | `synthetic` | 10 | 10/10 | 0.90 | 0.90 | 0.90 | 0.90 |
| Own Enterprise | `base` | 10 | 10/10 | 0.90 | 0.90 | 0.90 | 0.90 |
| Own Enterprise | `synthetic` | 10 | 10/10 | 0.90 | 0.90 | 0.90 | 0.90 |

* `base` sends the minimal 5-field protobuf body; `synthetic` adds experimental synthetic fingerprint fields for comparison.
* **Why 2captcha demos are disabled:** As of November 11, 2026, both the 2captcha v3 and Enterprise demo endpoints act like mock backends (accepting fabricated tokens and invalid site keys), so they are disabled in `test.py` and excluded here.

## Testing

```bash
uv run python test.py
```

Runs 10 iterations per adapter (`base` and `synthetic`) against the live **Appspot** and **NextCaptcha** demo verifiers, prints summary statistics, and writes per-run logs to `results/` (`.jsonl` and `.csv`).

To test different actions, set `RANDOMIZE_ACTIONS = True` in `test.py`.

## Captured Fingerprints & Protocol Tools

For controlled local research, you can replay fields from a real `reload` request captured in your own test environment:

1. **Capture the `POST .../reload` body** in DevTools Network tab into `tests/fixtures/reload_req.bin`:
   * **From a HAR file:** save a HAR with content into `tests/har/`, then run `uv run python tools/extract_har.py`.
   * **From a base64 payload:** save the copied base64 string to `copied_b64.txt` and decode it:
     ```bash
     python -c "import base64,sys; open('tests/fixtures/reload_req.bin','wb').write(base64.b64decode(open(sys.argv[1]).read().strip()))" copied_b64.txt
     ```
2. **Extract reusable fields:**
   ```bash
   uv run python tools/extract_fingerprint.py tests/fixtures/reload_req.bin fingerprint.json
   ```
3. **Pass `fingerprint_path="fingerprint.json"`** to `ReCaptchaV3Bypass` or `ReCaptchaV3Bypass.from_site_key(...)`.

### Reload protobuf fields

| Field | Type | Contents | Source |
| :---: | :--- | :--- | :--- |
| `5` | string | Integer hash/seed | `webworker.js` |
| `7` | string | Prior reload token (`05AD5oO3...`) | Previous reload response |
| `16` | string | Opaque canvas/audio blob | `webworker.js` |
| `20` | string | Base64 JSON (perf timing + host list) | `webworker.js` |
| `22` | string | Base64 binary (JS environment probes) | `webworker.js` |
| `25` | string | Base64 JSON (mouse/touch events) | `webworker.js` |
| `28` | int | `anchor-ms` parameter | Anchor URL |
| `29` | int | `execute-ms` parameter | Anchor URL |

*(Fields `7`, `16`, and `22` are opaque device-bound research artifacts, not portable score boosters.)*

### Utilities in `tools/`

Only `decode_body.py` needs the optional dependency: install it with `uv sync --extra tools`.

* `proto_decode.py` — Schema-less protobuf wire-format decoder
* `decode_body.py` — Decode captured reload request/response bodies
* `extract_har.py` — Extract raw bodies from `tests/har/*.har`
* `extract_fingerprint.py` — Export fields `5, 7, 16, 20, 22, 25, 28, 29` to JSON
* `generate_fingerprint.py` — Experimental synthetic fingerprint generator

## Disclaimer & License

Provided "as is" for authorized testing and educational research only, without warranty of any kind. Misuse or unauthorized testing is strictly prohibited, and the authors assume no liability for its use.

Licensed under the Apache License 2.0 — see [LICENSE](LICENSE).
