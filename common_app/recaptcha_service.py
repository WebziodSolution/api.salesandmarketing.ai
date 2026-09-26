import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class ReCaptchaResponse:
    def __init__(self, success: bool, message: str = ""):
        self.success = success
        self.message = message
        
    def isSuccess(self):
        return self.success

class ReCaptchaService:
    @staticmethod
    def verify(client_response: str) -> ReCaptchaResponse:
        """
        Verifies the reCAPTCHA token against Google's API.
        """
        secret_key = getattr(settings, 'GOOGLE_RECAPTCHA_KEY_SECRET', None)
        threshold = getattr(settings, 'GOOGLE_RECAPTCHA_KEY_THRESHOLD', 0.5)

        if not secret_key:
            logger.warning("Google reCAPTCHA secret key is not configured. Failing open or closed depending on requirements? Defaulting to True for now to avoid breaking without config.")
            return ReCaptchaResponse(True, "Not configured")

        verify_url = "https://www.google.com/recaptcha/api/siteverify"
        payload = {
            "secret": secret_key,
            "response": client_response
        }

        try:
            response = requests.post(verify_url, data=payload)
            response.raise_for_status()
            result = response.json()
            
            success = result.get("success", False)
            score = result.get("score", 0.0)
            
            if success and score >= threshold:
                return ReCaptchaResponse(True, "Success")
            else:
                logger.warning(f"reCAPTCHA validation failed. Result: {result}")
                return ReCaptchaResponse(False, "You are a robot")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error communicating with reCAPTCHA service: {e}")
            return ReCaptchaResponse(False, "Service unavailable")

reCaptchaService = ReCaptchaService()
