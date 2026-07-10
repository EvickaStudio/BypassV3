import base64
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode

import requests

# Default reCAPTCHA JS release is resolved lazily from api.js / enterprise.js
# when a site key is used without an explicit anchor URL.
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"
)


def _encode_origin(origin: str) -> str:
    """Base64-encode scheme://host:port (Google's `co` form)."""
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid origin: {origin!r}")
    port = (
        parsed.port
        if parsed.port is not None
        else (443 if parsed.scheme == "https" else 80)
    )
    normalized = f"{parsed.scheme}://{parsed.hostname}:{port}"
    return base64.b64encode(normalized.encode("utf-8")).decode("ascii")


def resolve_script_version(
    site_key: str, *, enterprise: bool = False, session=None, timeout: int = 30
) -> str:
    """Fetch the current reCAPTCHA JS release (`v`) for a site key.

    The version is embedded in `api.js` / `enterprise.js` as
    `recaptcha/releases/<version>/...`. It changes over time; resolve it fresh."""
    js_name = "enterprise.js" if enterprise else "api.js"
    url = f"https://www.google.com/recaptcha/{js_name}?render={site_key}"
    s = session or requests
    ua = (
        session.headers.get("User-Agent", _DEFAULT_UA)
        if session is not None
        else _DEFAULT_UA
    )
    resp = s.get(url, timeout=timeout, headers={"User-Agent": ua})
    resp.raise_for_status()
    if m := re.search(r"recaptcha/releases/([A-Za-z0-9_-]+)", resp.text):
        return m[1]
    raise RuntimeError(
        f"could not resolve reCAPTCHA script version from {url}; "
        "pass an explicit anchor URL or v= instead"
    )


def anchor_url_for_site_key(
    site_key: str,
    origin: str,
    *,
    enterprise: bool = False,
    v: str | None = None,
    hl: str = "en",
    size: str = "invisible",
    session=None,
    timeout: int = 30,
) -> str:
    """Build a reCAPTCHA anchor URL from just a site key + origin.

    Resolves the current JS release (`v`) from api.js/enterprise.js when not
    given. Everything else the bypass needs (recaptcha-token, k) comes from the
    anchor response itself."""
    if v is None:
        v = resolve_script_version(
            site_key, enterprise=enterprise, session=session, timeout=timeout
        )
    family = "enterprise" if enterprise else "api2"
    params = {
        "ar": "1",
        "k": site_key,
        "co": _encode_origin(origin),
        "hl": hl,
        "v": v,
        "size": size,
    }
    return f"https://www.google.com/recaptcha/{family}/anchor?{urlencode(params)}"


# Minimal protobuf writer for /api2/reload.
def _encode_varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _encode_field(field: int, wire: int, payload: bytes) -> bytes:
    tag = _encode_varint((field << 3) | wire)
    if wire == 2:
        return tag + _encode_varint(len(payload)) + payload
    if wire == 0:
        return tag + payload
    raise ValueError(f"unsupported wire type {wire}")


def _encode_string_field(field: int, text: str) -> bytes:
    return _encode_field(field, 2, text.encode("utf-8"))


def _encode_int_field(field: int, value: int) -> bytes:
    return _encode_field(field, 0, _encode_varint(value))


def encode_reload_body(
    *,
    v: str,
    c: str,
    k: str,
    action: str | None,
    fingerprint: dict | None,
    reason: str = "q",
) -> bytes:
    """Build the protobuf reload body, optionally with captured fingerprint fields."""
    body = bytearray()
    body += _encode_string_field(1, v)
    body += _encode_string_field(2, c)
    body += _encode_string_field(6, reason)
    if action:
        body += _encode_string_field(8, action)
    body += _encode_string_field(14, k)
    if fingerprint:
        for f in (5, 7, 16, 20, 22, 25):
            if val := fingerprint.get(str(f)) or fingerprint.get(f):
                body += _encode_string_field(f, val)
        for f in (28, 29):
            val = fingerprint.get(str(f)) or fingerprint.get(f)
            if val is not None:
                body += _encode_int_field(f, int(val))
    return bytes(body)


def parse_reload_response(text: str) -> str | None:
    """Extract the rresp token from JSON, with Google's XSSI guard stripped."""
    text = text.lstrip().removeprefix(")]}'").lstrip()
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\["rresp","(.*?)"', text)
        return m[1] if m else None
    if isinstance(arr, list) and len(arr) >= 2 and arr[0] == "rresp":
        token = arr[1]
        return token if isinstance(token, str) else None
    return None


def reload_url_from_anchor(anchor_url: str, k_value: str) -> str:
    parsed = urlparse(anchor_url)
    family = "enterprise" if "/enterprise/" in parsed.path else "api2"
    host = parsed.hostname or "www.google.com"
    if host not in {"www.google.com", "www.recaptcha.net"} and not host.endswith(
        ".google.com"
    ):
        raise ValueError(f"unsupported reCAPTCHA host: {host}")
    return f"https://{host}/recaptcha/{family}/reload?k={k_value}"


class ReCaptchaV3Bypass:
    """Fetch a reCAPTCHA v3 reload token, retrying with a fresh anchor token."""

    def __init__(
        self,
        target_url: str,
        *,
        action: str | None = None,
        fingerprint_path: str | None = None,
        max_retries: int = 3,
        user_agent: str = _DEFAULT_UA,
    ) -> None:
        self.target_url = target_url
        self.action = action
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.fingerprint = self._load_fingerprint(fingerprint_path)

    @classmethod
    def from_site_key(
        cls,
        site_key: str,
        origin: str,
        *,
        action: str | None = None,
        enterprise: bool = False,
        v: str | None = None,
        hl: str = "en",
        size: str = "invisible",
        fingerprint_path: str | None = None,
        max_retries: int = 3,
        user_agent: str = _DEFAULT_UA,
    ) -> "ReCaptchaV3Bypass":
        """Construct a bypass from just a site key + origin.

        Builds the anchor URL by resolving the current JS release from
        api.js/enterprise.js. Use this when you don't have a captured anchor URL
        from the browser's network tab."""
        session = requests.Session()
        session.headers.update({"User-Agent": user_agent})
        anchor = anchor_url_for_site_key(
            site_key,
            origin,
            enterprise=enterprise,
            v=v,
            hl=hl,
            size=size,
            session=session,
        )
        instance = cls(
            anchor,
            action=action,
            fingerprint_path=fingerprint_path,
            max_retries=max_retries,
            user_agent=user_agent,
        )
        instance.session = session
        return instance

    @staticmethod
    def _load_fingerprint(path: str | None) -> dict | None:
        if not path or not (p := Path(path)).exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return {k: v for k, v in data.items() if not k.startswith("_")}

    def extract_values(
        self, response: requests.Response
    ) -> tuple[str | None, str | None, str | None, str | None, str]:
        params = parse_qs(urlparse(self.target_url).query)
        token = re.search(
            r'type="hidden" id="recaptcha-token" value="([^"]+)"', response.text
        )

        def one(name, default=None):
            return params.get(name, [default])[0]

        return (
            token[1] if token else None,
            one("k"),
            one("co"),
            one("v"),
            one("hl", "en"),
        )

    def get_response(self) -> requests.Response | None:
        try:
            return self.session.get(self.target_url, timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"Failed to send GET request: {e}")
            return None

    def _do_reload(
        self, recaptcha_token, k_value, co_value, v_value, hl_value
    ) -> str | None:
        post_url = reload_url_from_anchor(self.target_url, k_value)

        # Protobuf embeds action in the token; form mode is only the no-action fallback.
        if self.action or self.fingerprint:
            kwargs = {
                "data": encode_reload_body(
                    v=v_value,
                    c=recaptcha_token,
                    k=k_value,
                    action=self.action,
                    fingerprint=self.fingerprint,
                ),
                "headers": {
                    "Content-Type": "application/x-protobuffer",
                    "Accept": "*/*",
                    "Origin": "https://www.google.com",
                    "Referer": "https://www.google.com/",
                },
            }
        else:
            kwargs = {
                "data": {
                    "v": v_value,
                    "reason": "q",
                    "c": recaptcha_token,
                    "k": k_value,
                    "co": co_value,
                    "hl": hl_value,
                    "size": "invisible",
                    "chr": "%5B89%2C64%2C27%5D",
                    "vh": "13599012192",
                }
            }
        try:
            resp = self.session.post(post_url, timeout=30, **kwargs)
        except requests.exceptions.RequestException as e:
            print(f"Failed to send POST request: {e}")
            return None
        return parse_reload_response(resp.text)

    def bypass(self) -> str | None:
        for attempt in range(1, self.max_retries + 1):
            initial_response = self.get_response()
            if initial_response is None:
                continue

            values = self.extract_values(initial_response)
            recaptcha_token, k_value, co_value, v_value, hl_value = values
            if None in (recaptcha_token, k_value, co_value, v_value):
                print(f"Attempt {attempt}: failed to extract values.")
                continue

            if token := self._do_reload(
                recaptcha_token, k_value, co_value, v_value, hl_value
            ):
                return token

            print(f"Attempt {attempt}: no token, retrying...")

        print(f"All {self.max_retries} attempts failed.")
        return None
