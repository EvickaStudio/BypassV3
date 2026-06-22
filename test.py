"""
Live smoke test against two reCAPTCHA v3 demo sites.

Run:
    uv run python test.py
"""

from urllib.parse import parse_qs, urlparse

import requests

from bypass import ReCaptchaV3Bypass


# --- 2captcha demo ---
ANCHOR_2CAPTCHA = (
    "https://www.google.com/recaptcha/api2/anchor?ar=1"
    "&k=6Lcyqq8oAAAAAJE7eVJ3aZp_hnJcI6LgGdYD8lge"
    "&co=aHR0cHM6Ly8yY2FwdGNoYS5jb206NDQz"
    "&hl=de&v=MerVUtRoajKEbP7pLiGXkL28&size=invisible"
    "&anchor-ms=20000&execute-ms=30000&cb=wm7bpt4pmfo9"
)
VERIFY_2CAPTCHA = "https://2captcha.com/api/v1/captcha-demo/recaptcha/verify"


# --- recaptcha-demo.appspot.com demo ---
ANCHOR_APPSPOT = (
    "https://www.google.com/recaptcha/api2/anchor?ar=1"
    "&k=6LdKlZEpAAAAAAOQjzC2v_d36tWxCl6dWsozdSy9"
    "&co=aHR0cHM6Ly9yZWNhcHRjaGEtZGVtby5hcHBzcG90LmNvbTo0NDM."
    "&hl=de&v=MerVUtRoajKEbP7pLiGXkL28&size=invisible"
    "&anchor-ms=20000&execute-ms=30000&cb=86qxp6yq6kmo"
)
VERIFY_APPSPOT = "https://recaptcha-demo.appspot.com/recaptcha-v3-verify.php"


def site_key_from(anchor_url: str) -> str:
    return parse_qs(urlparse(anchor_url).query)["k"][0]


def test_2captcha() -> None:
    print("=== 2captcha demo ===")
    token = ReCaptchaV3Bypass(ANCHOR_2CAPTCHA, action="demo_action").bypass()
    if not token:
        raise RuntimeError("Bypass returned no token")
    print(f"token: {token[:60]}...")

    resp = requests.post(
        VERIFY_2CAPTCHA,
        data={"siteKey": site_key_from(ANCHOR_2CAPTCHA), "answer": token},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"score: {data.get('score')}  success: {data.get('success')}")
    print(f"full: {resp.text}")
    if not data.get("success"):
        raise RuntimeError("2captcha demo verification failed")


def test_appspot() -> None:
    print("\n=== recaptcha-demo.appspot.com ===")
    token = ReCaptchaV3Bypass(ANCHOR_APPSPOT, action="examples/v3scores").bypass()
    if not token:
        raise RuntimeError("Bypass returned no token")
    print(f"token: {token[:60]}...")

    resp = requests.get(
        VERIFY_APPSPOT,
        params={"action": "examples/v3scores", "token": token},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"score: {data.get('score')}  success: {data.get('success')}")
    print(f"full: {resp.text}")
    if data.get("score") is None:
        raise RuntimeError("appspot demo returned no score")


def main() -> None:
    test_2captcha()
    test_appspot()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
