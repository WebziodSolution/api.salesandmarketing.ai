from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from rest_framework import status
from common_app.utils import api_response
from django.conf import settings
from auth_app.models import TenantDetails
import pyotp
import logging
from urllib.parse import unquote, quote

logger = logging.getLogger(__name__)


def get_app_name():
    server_type = getattr(settings, 'SERVER_TYPE', 'local')
    site_name = getattr(settings, 'SITE_NAME_BIG_COM', 'SalesAndMarketing.ai')
    if server_type == "pj":
        return site_name
    elif server_type == "qj":
        return f"Qa{site_name}"
    else:
        return f"Local{site_name}"

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def generate(request):
    username = request.GET.get('username')
    res_body = {
        "secret": "",
        "qrUrl": "",
        "error": ""
    }
    try:
        secret = pyotp.random_base32()
        app_name = get_app_name()
        totp = pyotp.totp.TOTP(secret)
        
        decoded_username = unquote(str(username))
        qr_url = totp.provisioning_uri(name=decoded_username, issuer_name=app_name)
        final_url = "https://api.qrserver.com/v1/create-qr-code/?data="+quote(qr_url)+"&size=200x200"
        res_body["secret"] = secret
        res_body["qrUrl"] = final_url
        return api_response(status.HTTP_200_OK, "Successfully", res_body)
    except Exception as e:
        logger.error(f"GoogleAuthenticatorGenerate Error : {str(e)}")
        res_body["error"] = "error"
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def verify(request):
    data = request.data
    secret = data.get('secret')
    code = data.get('code')
    tenant_id = data.get('memberId')
    td_login_preference = data.get('loginPreference')
    
    try:
        totp = pyotp.TOTP(secret)
        is_valid = totp.verify(code, valid_window=2)

        if is_valid:
            if tenant_id != 0:
                tenant_details = TenantDetails.objects.filter(tenant__ten_id=tenant_id).first()
                if tenant_details:
                    if td_login_preference == "googleAuthenticator":
                        tenant_details.td_google_authenticator_secret = secret
                    elif td_login_preference == "microsoftAuthenticator":
                        tenant_details.td_microsoft_authenticator_secret = secret
                    tenant_details.save()
            return api_response(status.HTTP_200_OK, "OTP Is Valid", {})
        else:
            return api_response(status.HTTP_401_UNAUTHORIZED, "Invalid OTP", {})
    except Exception as e:
        logger.exception(f"Verify error: {str(e)}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error", {})
