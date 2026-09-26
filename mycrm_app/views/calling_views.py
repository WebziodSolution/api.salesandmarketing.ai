from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from datetime import datetime
import logging
import json
from django.http import HttpResponse
from common_app.models import (Country, Userlist, CallingParent, CallingChild, CallingIncoming, Clients)
from common_app.utils import (api_response, get_final_tenant_id, clean_me_number, last_characters, get_tenants, get_phone_numbers_first, get_client_id_by_tenant_id, get_tenant_id_by_client_id)
from common_app.telnyx_utils import get_token
from common_app.services import commonServices, MailRequestDTO
import dateutil.parser

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_calling(request):
    """
    Python port of CallingController.sendCalling
    """
    try:
        tenant_id = get_final_tenant_id(request=request)
        calling_dto = request.data
        
        # In Java, memberId can be extracted from JWT or provided as attribute
        # Here we use request.user.member_id from IsAuthenticated
        
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        phone_number = get_phone_numbers_first(tenant.ten_id, "CAMPAIGN")
        client = Clients.objects.get(cliTenantId=tenant_id)

        country = Country.objects.get(country_id=int(tenant.ten_country))
        ten_phone = ""
        
        sub_tenant_id = int(calling_dto.get("subMemberId", 0))
        if sub_tenant_id == 0:
            if tenant.ten_phone:
                ten_phone = tenant.ten_phone
                ten_phone = clean_me_number(ten_phone)
                ten_phone = last_characters(ten_phone, country.phone_max_length)
                ten_phone = str(calling_dto.get("memCallCode", "")) + ten_phone
        else:
            sub_tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": sub_tenant_id
                    }
                }
            )
            if sub_tenant.ten_phone:
                ten_phone = sub_tenant.ten_phone
                ten_phone = clean_me_number(ten_phone)
                ten_phone = last_characters(ten_phone, country.phone_max_length)
                ten_phone = str(calling_dto.get("memCallCode", "")) + ten_phone
                
        ph_phone_number = phone_number.phPhoneNumber
        
        # Get phone number and userlist
        email_id = calling_dto.get("emailId")
        # In Java: contactRepository.getPhoneNo(memberId, callingDto.getEmailId())
        # and contactRepository.findByEmailId(memberId, callingDto.getEmailId())
        userlist = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), emailId=email_id).first()
        
        cc_client_phone_no = ""
        if userlist:
            phone_number = userlist.phone # Simplified, check if this is correct
            country_client = Country.objects.filter(cnt_name=userlist.country).first()
            if phone_number:
                cc_client_phone_no = clean_me_number(phone_number)
                if country_client:
                    cc_client_phone_no = last_characters(cc_client_phone_no, country_client.phone_max_length)
                else:
                    cc_client_phone_no = last_characters(cc_client_phone_no, 10)
                cc_client_phone_no = str(calling_dto.get("clientCallCode", "")) + cc_client_phone_no
                
        # Save CallingParent
        calling_parent = CallingParent(
            cp_twilio_no=ph_phone_number,
            cp_member_id=get_client_id_by_tenant_id(tenant_id),
            cp_member_phone_no=ten_phone,
            cp_date=datetime.now()
        )
        calling_parent.save()
        cp_id = calling_parent.cp_id
        
        # Get Telnyx Token
        telnyx_api_key = getattr(settings, 'TELNYX_API_KEY', '')
        telnyx_base_url = getattr(settings, 'TELNYX_BASE_URL', '')
        res_body = get_token(cp_id, telnyx_api_key, client.cliSipConnectionId, telnyx_base_url)
        res_body["cpId"] = cp_id
        
        if res_body.get("callingToken"):
            calling_parent.cp_token = str(res_body.get("callingToken"))
            calling_parent.save()
            
            # Save CallingChild
            calling_child = CallingChild(
                cc_cp_id=cp_id,
                cc_client_id=email_id,
                cc_client_phone_no=cc_client_phone_no,
                cc_start_time=datetime.now()
            )
            calling_child.save()
            
            return api_response(200, "Calling Successfully.", res_body)
        else:
            res_body["error"] = "Calling Not Working."
            res_body["callingToken"] = ""
            return api_response(500, "Error", res_body)
            
    except Exception as e:
        logger.error(f"send_calling error: {e}")
        return api_response(500, "Error", {"error": str(e)})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def calling_reply(request):
    """
    Python port of CallingController.callingReply
    """
    try:
        response_text = request.body.decode('utf-8')
        j_object = json.loads(response_text)
        json_data = j_object.get("data", {})
        payload = json_data.get("payload", {})
        
        site_name = getattr(settings, 'SITE_NAME', '')
        
        # Send debug email
        try:
            model = {
                "data": response_text,
                "siteName": site_name,
                "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', ''),
                "siteUrlWWW": getattr(settings, 'SITE_URL_WWW', ''),
                "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', ''),
                "companyName": getattr(settings, 'COMPANY_NAME', ''),
                "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', ''),
                "siteUrlAddress": getattr(settings, 'SITE_URL_ADDRESS', ''),
                "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', ''),
                "companyNumber": getattr(settings, 'COMPANY_NUMBER', ''),
                "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', ''),
                "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', '')
            }
            mail_request = MailRequestDTO(
                to="rajan@kaiasoft.com",
                template_name="preview-email-template.ftl",
                subject=f"Calling Reply at {site_name}"
            )
            commonServices.sendEmail(mail_request, model)
        except Exception:
            pass
            
        calling_incoming = None
        tenant_id = 0
        
        if "direction" in payload:
            if payload.get("direction") == "incoming":
                connection_id = payload.get("connection_id")
                client = Clients.objects.get(cliSipConnectionId=connection_id)
                if client:
                    tenant_id = client.cliTenantId
                    
                    calling_incoming = CallingIncoming(
                        cin_session_id=payload.get("call_session_id"),
                        cin_from=payload.get("from"),
                        cin_to=payload.get("to"),
                        cin_member_id=get_client_id_by_tenant_id(tenant_id),
                        cin_call_stop="N",
                        cin_date=datetime.now()
                    )
                    calling_incoming.save()
        else:
            try:
                calling_incoming = CallingIncoming.objects.filter(cin_session_id=payload.get("call_session_id")).first()
            except Exception:
                pass
                
        event_type = json_data.get("event_type")
        sip_hangup_cause = payload.get("sip_hangup_cause")
        
        if event_type == "call.hangup" and (sip_hangup_cause == "200" or sip_hangup_cause == "unspecified"):
            # Calculate duration
            start_time_str = payload.get("start_time")
            end_time_str = payload.get("end_time")
            
            cc_start_time = None
            cc_end_time = None
            duration_seconds = 0
            
            if start_time_str and end_time_str:
                cc_start_time = dateutil.parser.isoparse(start_time_str)
                cc_end_time = dateutil.parser.isoparse(end_time_str)
                duration_seconds = (cc_end_time - cc_start_time).total_seconds()
                
            calling_parent = None
            country_setting = {}
            
            if calling_incoming is None:
                try:
                    calling_parent = CallingParent.objects.filter(
                        cp_twilio_no=payload.get("from"),
                    ).order_by('-cp_id').first()
                    
                    if calling_parent:
                        calling_parent.cp_call_stop = "Y"
                        calling_parent.save()
                        tenant_id = get_tenant_id_by_client_id(calling_parent.cp_member_id)
                except Exception as e:
                    logger.error(f"CallingReply Error 1: {e}")
            else:
                tenant_id = get_tenant_id_by_client_id(calling_incoming.cin_member_id)
                
            try:
                country_setting = commonServices.country_setting_by_tenant_id(tenant_id)
            except Exception:
                pass
                
            client_name = ""
            duration = duration_seconds
            cc_duration = int((duration + 59) // 60) # ceil(duration/60)
            c_duration = int(duration // 60)
            final_duration = c_duration + ((duration - (c_duration * 60)) / 100.0)
            
            call_per_min_price = country_setting.get("cnty_call_per_min_price") if country_setting else 0
            amt = float(call_per_min_price or 0) * cc_duration
                
            cp_id = 0
            
            if calling_incoming is None and calling_parent:
                calling_child = CallingChild.objects.filter(cc_cp_id=calling_parent.cp_id).order_by('-cc_id').first()
                if calling_child:
                    calling_child.cc_duration = final_duration
                    calling_child.cc_sid = json_data.get("id")
                    calling_child.cc_start_time = cc_start_time
                    calling_child.cc_end_time = cc_end_time
                    calling_child.save()
                    
                    userlist = Userlist.objects.filter(memberId=calling_parent.cp_member_id, emailId=calling_child.cc_client_id).first()
                    if userlist:
                        if userlist.firstName:
                            client_name = userlist.firstName
                        if userlist.lastName:
                            client_name += " " + userlist.lastName
                            
                cp_id = calling_parent.cp_id
                client_name = f"Calling To {client_name}"
            elif calling_incoming:
                client_name = f"Calling From {calling_incoming.cin_from}"
                cp_id = None
                tenant_id = get_tenant_id_by_client_id(calling_incoming.cin_member_id)
                calling_incoming.cin_duration = final_duration
                calling_incoming.cin_start_time = cc_start_time
                calling_incoming.cin_end_time = cc_end_time
                calling_incoming.cin_call_stop = "Y"
                calling_incoming.save()
                
            if amt > 0:
                try:
                    from common_app.services import CommonServices
                    CommonServices.saveCampaignTransaction(
                        cp_id, client_name, 1, "calling",
                        None, "uninvoiced", None,
                        get_client_id_by_tenant_id(tenant_id), "0", amt, getattr(country_setting, 'cnty_call_per_min_price', 0),
                        0, None, None, 0
                    )
                except Exception as e:
                    logger.error(f"CallingReply Error 4: {e}")
                    
    except Exception as e:
        logger.error(f"CallingReply Error: {e}")
        
    return HttpResponse("")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def calling_stop(request):
    """
    Python port of CallingController.callingStop
    """
    try:
        cp_id = request.query_params.get("cpId")
        if cp_id:
            calling_parent = CallingParent.objects.filter(cp_id=int(cp_id)).first()
            if calling_parent and calling_parent.cp_call_stop == "Y":
                return api_response(200, "Successfully.", "")
    except Exception as e:
        logger.error(f"CallingStop Error: {e}")
        
    return api_response(500, "Error", "")
