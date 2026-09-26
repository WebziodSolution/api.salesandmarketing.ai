import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from automation_app.models import Automation
from common_app.models import PhoneNumbers
from common_app.utils import api_response, get_final_tenant_id, get_phone_numbers_first, get_client_id_by_tenant_id

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getBuyAllNumberList(request):
    res_body = {}
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        phone_number = get_phone_numbers_first(final_tenant_id, "CAMPAIGN")
        chat_phone_number = get_phone_numbers_first(final_tenant_id, "CHAT")
        number_list = []
        
        # 1. From SpSmsPolling
        sp_numbers = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(final_tenant_id), phHowUsed='SMSPOLLING', phPhoneNumberClosed='N')

        for sp in sp_numbers:
            number_list.append({
                "numberSid": sp.phSid,
                "number": sp.phPhoneNumber
            })
            
        if phone_number and phone_number.phPhoneNumber and phone_number.phSid:
            number_list.append({
                "numberSid": phone_number.phSid,
                "number": phone_number.phPhoneNumber
            })
            
        if chat_phone_number and chat_phone_number.phPhoneNumber and chat_phone_number.phSid:
            number_list.append({
                "numberSid": chat_phone_number.phSid,
                "number": chat_phone_number.phPhoneNumber
            })

        phone_numbers = PhoneNumbers.objects.filter(
            phClientId=get_client_id_by_tenant_id(final_tenant_id),
            phPhoneNumberClosed='N'
        ).exclude(phPhoneNumber='').exclude(phSid__isnull=True).exclude(phSid='')
        
        for ph in phone_numbers:
            number_list.append({
                "numberSid": ph.phSid,
                "number": ph.phPhoneNumber
            })
            
        # 4. Filter and distinct
        seen_numbers = set()
        distinct_number_list = []
        for entry in number_list:
            num = entry.get("number")
            if num and num not in seen_numbers:
                count = Automation.objects.filter(
                    autSmsFromNumber=num
                ).exclude(autAutomationCampaignStatus='close').count()
                
                if count == 0:
                    seen_numbers.add(num)
                    distinct_number_list.append(entry)
                    
        res_body['numberList'] = distinct_number_list
        return api_response(status.HTTP_200_OK, "Buy All Number List Fetched Successfully", res_body)
        
    except Exception as e:
        logger.error(f"[ memberId : {final_tenant_id} ] GetBuyAllNumberList Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)
