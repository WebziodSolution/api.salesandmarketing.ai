from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication
from auth_app.models import Tenants
from common_app.utils import get_tenants

class MemberJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            # Extract the user_id from the token using the claim defined in settings
            user_id = validated_token.get('tenId')
            if user_id is None:
                raise exceptions.AuthenticationFailed('Token contained no recognizable user identification')

            # Look up the member directly from your custom table
            tenant = Tenants.objects.get(ten_id=user_id)
            return tenant
        except Tenants.DoesNotExist:
            raise exceptions.AuthenticationFailed('No member found with this ID', code='user_not_found')


class SupportApiAuthentication(BaseAuthentication):
    """
    Extracted from Java's JwtRequestFilter.java
    Allows authentication using secretKey and authToken headers.
    """
    def authenticate(self, request):
        secret_key = request.headers.get('secretKey')
        auth_token = request.headers.get('authToken')
        
        if not secret_key or not auth_token:
            return None
            
        try:
            # Match Java's getByAuthKeyByAndAuthToken(secretKey, authToken)
            tenant = get_tenants(
                where_conditions={
                    "tenant_details": {
                        "td_auth_key": secret_key,
                        "td_auth_token": auth_token,
                        "td_enable_api": 'Y'
                    }
                }
            )
            
            # Java also checks suspended status (memberStatus == 3)
            if tenant.ten_status == 3:
                raise exceptions.AuthenticationFailed('Your Account Is Suspended. Please Contact Administrator')
                
            return tenant or None
        except Tenants.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid SecretKey or AuthToken')
