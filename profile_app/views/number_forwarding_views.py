import logging
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.utils import timezone
from common_app.telnyx_utils import telnyx_call_forwarding
from common_app.utils import api_response, get_final_tenant_id
from common_app.models import NumberCallForwarding

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getNumberForwardingList(request):
    resBody = {}
    try:
        final_member_id = get_final_tenant_id(request=request)

        # findPageNumberForwardingList logic
        forwardings = NumberCallForwarding.objects.filter(cfnMemberId=final_member_id).order_by('-cfnId')
        
        dto_list = []
        for cf in forwardings:
            dto_list.append({
                "cfnId": cf.cfnId,
                "cfnTwilioNumber": cf.cfnTwilioNumber,
                "cfnForwardingCountryCode": cf.cfnForwardingCountryCode,
                "cfnForwardingNumber": cf.cfnForwardingNumber,
                "cfnTwilioPhoneSid": cf.cfnTwilioPhoneSid
            })
            
        resBody["numberForwarding"] = dto_list
        return api_response(200, "Fetch Number Forwarding Successfully.", resBody)
    except Exception as e:
        logger.error(f"[ memberId : {request.user.id if hasattr(request, 'user') else None} ] GetNumberForwardingList Error : {e}")
        return api_response(500, "Oops!! There is some issue", resBody)


@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteNumberForwarding(request):
    resBody = {"error": ""}
    cfn_id = request.GET.get('cfnId')
    try:
        final_member_id = get_final_tenant_id(request=request)

        try:
            cf = NumberCallForwarding.objects.get(cfnId=cfn_id, cfnMemberId=final_member_id)
            
            forwarding_number = f"{cf.cfnForwardingCountryCode or ''}{cf.cfnForwardingNumber or ''}"
            
            s_id = telnyx_call_forwarding(cf.cfnTwilioPhoneSid, forwarding_number, False)
            
            if s_id:
                cf.delete()
                
            if resBody.get("error") == "":
                return api_response(200, "Delete Number Forwarding Successfully.", resBody)
        except NumberCallForwarding.DoesNotExist:
            resBody["error"] = "Record not found"
            
    except Exception as e:
        logger.error(f"[ memberId : {request.user.id if hasattr(request, 'user') else None} ] DeleteNumberForwarding Error : {e}")
        return api_response(500, "Oops!! There is some issue", resBody)
        
    return api_response(500, str(resBody.get("error", "Error")), resBody)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveNumberForwarding(request):
    resBody = {"error": ""}
    try:
        final_member_id = get_final_tenant_id(request=request)

        data = request.data
        cfn_id = data.get('cfnId')
        twilio_number = data.get('cfnTwilioNumber')
        forwarding_country_code = data.get('cfnForwardingCountryCode')
        forwarding_number = data.get('cfnForwardingNumber')
        twilio_phone_sid = data.get('cfnTwilioPhoneSid')
        sub_member_id = data.get('subMemberId')

        full_forwarding_number = f"{forwarding_country_code}{forwarding_number}"

        s_id = telnyx_call_forwarding(twilio_phone_sid, full_forwarding_number, True)

        if s_id:
            # commonServices.saveNumberCallForwarding implementation
            if cfn_id and int(cfn_id) > 0:
                try:
                    cf = NumberCallForwarding.objects.get(cfnId=cfn_id)
                    cf.cfnTwilioNumber = twilio_number
                    cf.cfnForwardingCountryCode = forwarding_country_code
                    cf.cfnForwardingNumber = forwarding_number
                    cf.cfnMemberId = final_member_id
                    cf.cfnTwilioPhoneSid = twilio_phone_sid
                    cf.save()
                except NumberCallForwarding.DoesNotExist:
                    resBody["error"] = "Record not found"
            else:
                cf = NumberCallForwarding(
                    cfnTwilioNumber=twilio_number,
                    cfnForwardingCountryCode=forwarding_country_code,
                    cfnForwardingNumber=forwarding_number,
                    cfnMemberId=final_member_id,
                    cfnDateTime=timezone.now(),
                    subMemberId=sub_member_id if sub_member_id else 0,
                    cfnTwilioPhoneSid=twilio_phone_sid
                )
                cf.save()

        if resBody.get("error") == "":
            return api_response(200, "Change Number Successfully.", resBody)
        else:
            return api_response(500, str(resBody.get("error")), resBody)
            
    except Exception as e:
        logger.error(f"[ memberId : {request.user.id if hasattr(request, 'user') else None} ] SaveNumberForwarding Error : {e}")
        return api_response(500, "Oops!! There is some issue", resBody)

