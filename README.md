# Bypass invisible ReCaptcha v3

Just a simple ReCaptcha v3 bypass that returns the `X-RECAPTCHA-TOKEN` token from an captcha.

## Requirements

- Python 3.6
- requests
- re (regex)

## Disclaimer

This program is intended for educational and testing purposes only.
Any misuse or illegal activity using this code is strictly prohibited.
The authors assume no liability for any damage or legal consequences caused by the use of this software.

**Additional Disclaimer**:
This software is provided “as is,” without warranty of any kind.
The authors are not responsible for any direct, indirect, incidental, or consequential damages arising from its use or the inability to use it.
Use at your own risk.

## Usage

```python
from bypass import ReCaptchaV3Bypass


# Initialize the ReCaptchaV3Bypass class with the anchor URL
# The anchor URL can be found when inspecting the network requests in the browser
url = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=..."

bypass = ReCaptchaV3Bypass(url)


# Now call the bypass method with the bypass object and get the v3 token
gtk = bypass.bypass()


# Or you can just call it like this
gtk = ReCaptchaV3Bypass(url).bypass()
```

## License

This project is licensed under the AGPLv3 License - see the [LICENSE](LICENSE) file for details.
