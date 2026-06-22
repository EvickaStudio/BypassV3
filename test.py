"""
Live smoke test against the 2captcha reCAPTCHA v3 demo.
"""

from urllib.parse import parse_qs, urlparse

import requests

from bypass import ReCaptchaV3Bypass


ANCHOR_URL = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=6Lcyqq8oAAAAAJE7eVJ3aZp_hnJcI6LgGdYD8lge&co=aHR0cHM6Ly8yY2FwdGNoYS5jb206NDQz&hl=de&v=MerVUtRoajKEbP7pLiGXkL28&size=invisible&anchor-ms=20000&execute-ms=30000&cb=wm7bpt4pmfo9"
VERIFY_URL = "https://2captcha.com/api/v1/captcha-demo/recaptcha/verify"


def site_key_from(anchor_url: str) -> str:
    return parse_qs(urlparse(anchor_url).query)["k"][0]


def main() -> None:
    token = ReCaptchaV3Bypass(ANCHOR_URL).bypass()
    if not token:
        raise RuntimeError("Bypass returned no token")

    print(token)

    response = requests.post(
        VERIFY_URL,
        data={"siteKey": site_key_from(ANCHOR_URL), "answer": token},
        timeout=30,
    )
    response.raise_for_status()

    print(response.text)

    if not response.json().get("success"):
        raise RuntimeError("2captcha demo verification failed")


if __name__ == "__main__":
    main()
