from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
import logging
import re
from common_app.models import SmsTemplates, Userlist, Language
from common_app.utils import api_response, get_final_tenant_id, display_date, get_client_id_by_tenant_id

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsTemplateDetails(request, sstId, emailId):
    member_id = get_final_tenant_id(request=request)
    try:
        template = get_object_or_404(SmsTemplates, stId=sstId, stClientId=get_client_id_by_tenant_id(member_id))
        userlist = get_object_or_404(Userlist, emailId=emailId, memberId=get_client_id_by_tenant_id(member_id))
        
        template_data = template.stDetails or ""
        
        placeholders = {
            "##First Name##": userlist.firstName,
            "##Last Name##": userlist.lastName,
            "##Full Name##": userlist.fullName,
            "##Email##": userlist.email,
            "##Contact No##": userlist.phoneNumber,
            "##Phone##": userlist.phone,
            "##Gender##": userlist.gender,
            "##Date Of Birth##": display_date(userlist.birthday) if userlist.birthday else "",
            "##Country##": userlist.country,
            "##State##": userlist.stateProvRegion,
            "##Street Address1##": userlist.streetAddress1,
            "##Street Address2##": userlist.streetAddress2,
            "##City##": userlist.city,
            "##Zip Code##": userlist.zipPostalCode,
        }
        
        for key, value in placeholders.items():
            template_data = template_data.replace(key, str(value) if value else "")
            
        # Language placeholder
        if userlist.usDefaultLanguage:
            try:
                lang = Language.objects.get(lg_name=userlist.usDefaultLanguage)
                template_data = template_data.replace("##Language##", lang.lg_long_name or "")
            except Language.DoesNotExist:
                template_data = template_data.replace("##Language##", "")
        else:
            template_data = template_data.replace("##Language##", "")
            
        template_data = re.sub(r" +", " ", template_data).strip()
        
        return api_response(200, "Fetch SMS Template Details Successfully.", {"sstDetails": template_data})
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsTemplateDetails Error : {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsTemplateSelect(request):
    member_id = get_final_tenant_id(request=request)
    try:
        templates = SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(member_id)).order_by('stName')
        data = []
        for temp in templates:
            data.append({
                "sstId": temp.stId,
                "sstName": temp.stName
            })
        return api_response(200, "Fetch SMS Template Successfully.", {"smsTemplateSelect": data})
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsTemplateSelect Error : {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsTemplateList(request):
    member_id = get_final_tenant_id(request=request)
    try:
        templates = SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(member_id)).order_by('-stDate')
        data = []
        for temp in templates:
            data.append({
                "sstId": temp.stId,
                "sstMemberId": temp.stClientId,
                "sstName": temp.stName,
                "sstDetails": temp.stDetails,
                "sstDate": temp.stDate.strftime('%m-%d-%Y %H:%M:%S') if temp.stDate else None
            })
        return api_response(200, "Fetch SMS Template Successfully.", {"smsTemplateList": data})
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsTemplateList Error : {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsTemplate(request, sstId):
    member_id = get_final_tenant_id(request=request)
    try:
        temp = get_object_or_404(SmsTemplates, stId=sstId, stClientId=get_client_id_by_tenant_id(member_id))
        data = {
            "sstId": temp.stId,
            "sstMemberId": temp.stClientId,
            "sstName": temp.stName,
            "sstDetails": temp.stDetails,
            "sstDate": temp.stDate.strftime('%m-%d-%Y %H:%M:%S') if temp.stDate else None
        }
        return api_response(200, "Fetch SMS Template Successfully.", {"smsTemplate": data})
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsTemplate Error : {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def deleteSmsTemplate(request, sstId):
    try:
        temp = get_object_or_404(SmsTemplates, stId=sstId)
        temp.delete()
        return api_response(200, "SMS Template Deleted Successfully.", {})
    except Exception as e:
        logger.error(f"DeleteSmsTemplate Error : {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def saveSmsTemplate(request):
    member_id = get_final_tenant_id(request=request)
    data = request.data
    sst_id = data.get('sstId', 0)
    
    try:
        if sst_id and int(sst_id) > 0:
            template = get_object_or_404(SmsTemplates, stId=sst_id, stClientId=get_client_id_by_tenant_id(member_id))
            msg = "SMS Template Edited Successfully"
        else:
            template = SmsTemplates()
            template.stClientId = get_client_id_by_tenant_id(member_id)
            template.stDate = timezone.now()
            msg = "SMS Template Added Successfully"
            
        template.stName = data.get('sstName')
        template.stDetails = data.get('sstDetails')
        template.save()
        
        return api_response(200, msg, {"error": "", "msg": msg})
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] SaveSmsTemplate Error : {e}")
        return api_response(500, "Invalid Data", {"error": "Invalid Data", "msg": ""})
