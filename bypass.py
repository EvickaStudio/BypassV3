import re

import requests


class ReCaptchaV3Bypass:
    """
    Bypass the reCAPTCHA v3 challenge.
    Only works for some reCAPTCHA v3 challenges.
    """

    def __init__(self, target_url) -> None:
        self.target_url = target_url
        self.session = requests.Session()

    def extract_values(self, response) -> tuple[str, str, str, str]:
        """
        Extracts necessary values from the response.
        """
        try:
            recaptcha_token = self._extract_value(
                r"type=\"hidden\" id=\"recaptcha-token\" value=\"(.*?)\"", response.text
            )
            k_value = self._extract_value(r"&k=(.*?)&co", self.target_url)
            co_value = self._extract_value(r"&co=(.*?)&hl", self.target_url)
            v_value = self._extract_value(r"&v=(.*?)&size", self.target_url)
        except AttributeError:
            print("Failed to extract values. Check your regex patterns.")
            return None, None, None, None

        return recaptcha_token, k_value, co_value, v_value

    def _extract_value(self, pattern, text) -> str:
        """
        Extracts a value from the text using the provided regex pattern.
        """
        return re.search(pattern, text).group(1)

    def get_response(self) -> requests.Response:
        """
        Sends a GET request to the target URL.
        """
        try:
            return self.session.get(self.target_url)
        except requests.exceptions.RequestException as e:
            print(f"Failed to send GET request: {e}")
            return None

    def post_response(
        self, recaptcha_token, k_value, co_value, v_value
    ) -> requests.Response:
        """
        Sends a POST request to the reCAPTCHA API.
        """
        post_url = "https://www.google.com/recaptcha/api2/reload?k=" + k_value
        post_data = self._generate_post_data(
            recaptcha_token, k_value, co_value, v_value
        )
        try:
            return self.session.post(post_url, data=post_data)
        except requests.exceptions.RequestException as e:
            print(f"Failed to send POST request: {e}")
            return None

    def _generate_post_data(self, recaptcha_token, k_value, co_value, v_value) -> dict:
        """
        Generates the data to be sent in the POST request.
        """
        return {
            "v": v_value,
            "reason": "q",
            "c": recaptcha_token,
            "k": k_value,
            "co": co_value,
            "hl": "en",
            "size": "invisible",
            "chr": "%5B89%2C64%2C27%5D",
            "vh": "13599012192",
        }

    def extract_gtk(self, response) -> str:
        """
        Extracts the GTK value from the response.
        """
        try:
            return self._extract_value(r'\["rresp","(.*?)"', response.text)
        except AttributeError:
            print("Failed to extract GTK. Check your regex pattern.")
            return None

    def bypass(self) -> str:
        """
        Performs the bypass of the reCAPTCHA.
        """
        initial_response = self.get_response()
        if initial_response is None:
            return None

        recaptcha_token, k_value, co_value, v_value = self.extract_values(
            initial_response
        )
        if None in (recaptcha_token, k_value, co_value, v_value):
            return None

        post_response = self.post_response(recaptcha_token, k_value, co_value, v_value)
        if post_response is None:
            return None

        return self.extract_gtk(post_response)
