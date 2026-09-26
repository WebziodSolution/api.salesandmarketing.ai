import telnyx
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response
import logging
import requests

logger = logging.getLogger(__name__)

# Initialize Telnyx client from the Django settings
TELNYX_API_KEY = getattr(settings, 'TELNYX_API_KEY', '')
telnyx_client = telnyx.Telnyx(api_key=TELNYX_API_KEY)

@api_view(['POST'])
def searchForBuyNumber(request: Request):
    resBody = dict()
    data = request.data
    
    # Matching Java SearchNumberDto
    area_code = data.get('areaCode', 510)
    country_code = data.get('countryCode', 'US')
    
    if not country_code:
        country_code = 'US'
    if not area_code or area_code == 0:
        area_code = 510

    search_numbers = []
    
    try:
        # Using the official python telnyx library matching the `TelnyxSmsFunction.getTelnyxNumberList` Unirest call
        # the telnyx library automatically searches available numbers based on filters
        response = telnyx_client.available_phone_numbers.list(
            filter={"country_code": country_code, "national_destination_code": str(area_code), "limit": 28}
        )
        assert response is not None and response.data is not None
        for item in response.data:
            search_numbers.append({
                "areaCode": area_code,
                "countryCode": country_code,
                "phoneNumber": item.phone_number,
                "friendlyName": item.phone_number
            })
            
        resBody['searchNumber'] = search_numbers
        return api_response(200, "Fetch Number Successfully.", resBody)
    except Exception as e:
        logger.error(f"SearchNumber Error : {e}")
        return api_response(500, "Error Processing Request", resBody)


@api_view(['POST'])
def sendSms(request: Request):
    data = request.data
    # Matching Java SmsRequestDto
    phone_number = data.get('phoneNumber')
    message = data.get('message')
    
    telnyx_from_phone = getattr(settings, 'TELNYX_FROM_PHONE_NO', '')
    
    if not phone_number or not message:
        return api_response(400, "Validation Error: phoneNumber and message are required.", {})
    
    try:
        # Using Telnyx python library to send SMS mirroring `TelnyxSmsFunction.sendSms`
        telnyx_client.messages.create(
            from_=telnyx_from_phone,
            to=phone_number,
            text=message,
        )
        
        return api_response(200, "Send SMS Successfully.", "Send SMS Successfully.")
    except Exception as e:
        logger.error(f"SendSms Error : {e}")
        return api_response(500, "Error Sending SMS", {})



@api_view(['POST'])
def createSIP(request):
    resBody = dict()
    
    telnyx_outbound_voice_profile_id = getattr(settings, 'TELNYX_OUTBOUND_VOICE_PROFILE_ID', '')
    site_url_backend = getattr(settings, 'SITE_URL_BACKEND', 'https://qaapi.salesandmarketing.ai:8443/v1/')
    
    # Java mocked "localtest1" explicitly
    telnyx_username = "localtest1"
    telnyx_password = "localtest1"
    
    try:
        # Create SIP Credential Connection based upon `TelnyxSmsFunction.createSIP` request syntax
        # telnyx python lib has connection logic, but translating the raw Unirest API natively uses requests
        headers = {
            "Authorization": f"Bearer {TELNYX_API_KEY}",

            "Content-Type": "application/json"
        }
        
        payload = {
            "active": True,
            "user_name": telnyx_username,
            "password": telnyx_password,
            "connection_name": telnyx_username,
            "webhook_event_url": f"{site_url_backend}calling/callingReply",
            "sip_uri_calling_preference": "unrestricted",
            "inbound": {
                "dnis_number_format": "sip_username",
                "codecs": ["G722", "G711U", "G711A", "G729", "OPUS", "H.264", "VP8", "AMR-WB"],
                "isup_headers_enabled": True
            },
            "outbound": {
                "outbound_voice_profile_id": telnyx_outbound_voice_profile_id
            }
        }
        
        base_url = getattr(settings, 'TELNYX_BASE_URL', 'https://api.telnyx.com/v2/')
        endpoint = f"{base_url}credential_connections"
        
        response = requests.post(endpoint, json=payload, headers=headers)
        data = response.json()
        
        sip_id = ""
        if 'data' in data and 'id' in data['data']:
            sip_id = data['data']['id']
            
        resBody['sipId'] = sip_id
        return api_response(200, "Create SubAccount Successfully.", resBody)
        
    except Exception as e:
        logger.error(f"CreateSIP Error : {e}")
        return api_response(500, "Error creating SIP", resBody)
