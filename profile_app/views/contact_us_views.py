from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.conf import settings
from common_app.utils import api_response
from common_app.recaptcha_service import reCaptchaService
from common_app.services import commonServices, MailRequestDTO
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def sendContactUs(request):
    try:
        data = request.data
        user_name = data.get('userName')
        email = data.get('email')
        services = data.get('services')
        message = data.get('message')
        recaptcha_token = data.get('reCaptchaToken')

        # DTO Validation
        if not user_name:
            return api_response(400, "Please enter your name.", "")
        if not email:
            return api_response(400, "Please enter email.", "")
        if not services:
            return api_response(400, "Please select service.", "")
        if not message:
            return api_response(400, "Please enter message.", "")
        if not recaptcha_token:
            return api_response(400, "Please select reCaptcha.", "")

        # Verify token
        re_captcha_response = reCaptchaService.verify(recaptcha_token)
        if not re_captcha_response.isSuccess():
            return api_response(204, "You are a robot", "")

        company_name = getattr(settings, 'COMPANY_NAME', 'SAM')

        mail_request_dto = MailRequestDTO()
        mail_request_dto.template_name = "contactus-template.ftl"
        mail_request_dto.subject = f"{company_name} Contact Us :: {services}"

        model_data = {
            "userName": user_name,
            "email": email,
            "services": services,
            "message": message,
            "siteName": getattr(settings, 'SITE_NAME', ''),
            "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', ''),
            "siteUrlWWW": getattr(settings, 'SITE_URL_WWW', ''),
            "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', ''),
            "companyName": company_name,
            "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', ''),
            "siteUrlAddress": getattr(settings, 'SITE_URL_ADDRESS', ''),
            "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', ''),
            "companyNumber": getattr(settings, 'COMPANY_NUMBER', ''),
            "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', ''),
            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', '')
        }

        # Send to admin 1
        to_email_admin_1 = getattr(settings, 'TO_EMAIL_ADMIN_MEMBER_1', '')
        mail_request_dto.to = to_email_admin_1
        response = commonServices.sendEmail(mail_request_dto, model_data)

        # Send to admin 2
        to_email_admin_2 = getattr(settings, 'TO_EMAIL_ADMIN_MEMBER_2', '')
        mail_request_dto.to = to_email_admin_2
        commonServices.sendEmail(mail_request_dto, model_data)

        if response.status:
            return api_response(200, "Your message has been sent.", "")
        else:
            return api_response(204, "Something went wrong.", "")

    except Exception as e:
        logger.error(f"Error in sendContactUs: {str(e)}")
        return api_response(500, "Internal Server Error", "")
