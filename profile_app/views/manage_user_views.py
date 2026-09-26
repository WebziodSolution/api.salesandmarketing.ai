from rest_framework.decorators import api_view, permission_classes
from common_app.telnyx_utils import delete_telnyx_number
from common_app.utils import api_response, get_final_tenant_id, get_tenants, clean_me_number, get_phone_numbers_first, get_client_id_by_tenant_id
from django.conf import settings
from profile_app.models import SubaccountType, PageActionName, SubaccountPageDetails
from auth_app.models import Tenants, TenantDetails
from profile_app.serializers import SubaccountTypeDtoSerializer
from common_app.models import NumberCallForwarding, Clients, PhoneNumbers, SpSmsPolling, SubaccountPage, SubaccountPagePermission
from common_app.decrypt_string import DecryptString
from django.utils import timezone
from common_app.custom_permissions import WhitelistPermission
import logging
from common_app.services import CommonServices, MailRequestDTO

@api_view(['GET', 'POST'])
@permission_classes([WhitelistPermission])
def getUserTypeById(request, styId=None):
    try:
        try:
            sub_type = SubaccountType.objects.get(styId=styId)
        except SubaccountType.DoesNotExist:
             return api_response(404, "User Type Not Found", {})
        
        serializer = SubaccountTypeDtoSerializer(sub_type)
        return api_response(200, "User Type Fetched Successfully.", serializer.data)
    except Exception as e:
        logging.error(f"GetUserTypeById Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getUserType(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        sub_types = SubaccountType.objects.filter(styMemberId=get_client_id_by_tenant_id(tenant_id))
        serializer = SubaccountTypeDtoSerializer(sub_types, many=True)
        resBody = {
            "subaccountType": serializer.data
        }
        return api_response(200, "Fetch Data Successfully", resBody)
    except Exception as e:
        logging.error(f"GetUserType Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSubUser(request):
    resBody = dict()
    try:
        data = request.data
        if not isinstance(data, list) or len(data) == 0:
             return api_response(400, "Expected a list of users.", resBody)
        
        old_tenant_id = data[0].get('memberId', 0)
        parent_tenant_id = data[0].get('parentMemberId', 0)
        parent_tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": parent_tenant_id
                }
            }
        )
        saved_tenants = []
        for req in data:
            req_tenant_id = req.get('memberId', 0)
            tenant = Tenants.objects.filter(ten_id=req_tenant_id).first()

            if req_tenant_id != 0 and tenant:
                if tenant and tenant.ten_id != req_tenant_id:
                     return api_response(304, "Sub Account Already In Used.", resBody)

                tenant.ten_first_name = req.get("firstName")
                tenant.ten_last_name = req.get("lastName")
                tenant.ten_email = req.get("email")
                tenant.ten_parent_id = req.get("parentMemberId")
                tenant.save()
                saved_tenants.append(tenant.ten_id)
            else:
                if not tenant:
                    new_tenant = Tenants.objects.create(
                        ten_first_name=req.get("firstName"),
                        ten_last_name=req.get("lastName"),
                        ten_email=req.get("email"),
                        ten_parent_id=req.get("parentMemberId"),
                        ten_city=parent_tenant.ten_city if parent_tenant else None,
                        ten_state=parent_tenant.ten_state if parent_tenant else None,
                        ten_country=parent_tenant.ten_country if parent_tenant else None,
                        ten_default_language=parent_tenant.ten_default_language if parent_tenant else None,
                        ten_date_registered=timezone.now(),
                        ten_status=1,
                    )
                    TenantDetails.objects.create(
                        tenant=new_tenant,
                        td_sec_ans_1=None,
                        td_sec_ans_2=None,
                        td_sec_ans_3=None,
                        td_sec_qus_1=0,
                        td_sec_qus_2=0,
                        td_sec_qus_3=0,
                        td_opt_in="Y",
                        td_sub_account_type_id=req.get("subaccountTypeId", 0),
                        td_bill_date=parent_tenant.td_bill_date if parent_tenant else None,
                        td_plan_id=parent_tenant.td_plan_id if parent_tenant else None
                    )
                    parent_client = Clients.objects.filter(cliTenantId=parent_tenant_id).first()
                    if parent_client is not None:
                        new_client = parent_client
                        new_client.cliId = None
                        new_client.cliTenantId = new_tenant.ten_id
                        new_client.save()
                    saved_tenants.append(new_tenant.ten_id)
                else:
                    return api_response(304, "Sub Account Already In Used.", resBody)
                    
        # Invitation logic
        if data[0].get('btnType') == "sendInvitation" and saved_tenants:
            tenant_id = saved_tenants[0]
            tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
            tenant_details.td_suba_reg_link_expire = timezone.now()
            tenant_details.save()

            tenant = Tenants.objects.get(ten_id=tenant_id)
            tenant_id_str = str(tenant.ten_id)
            enc_tenant_id = DecryptString.set_enc_dec_user(tenant_id_str, "", "Y")
            first_name = tenant.ten_first_name
            email = tenant.ten_email
            
            link = f"{settings.SITE_URL}subaccountactivesetup?v={enc_tenant_id}"
            
            model = {
                "SITEURL": settings.SITE_URL,
                "siteName": settings.SITE_NAME,
                "firstName": first_name,
                "link": link,
                "toAdminSupportEmail": settings.TO_ADMIN_SUPPORT_EMAIL,
                "siteUrlWWW": settings.SITE_URL_WWW,
                "siteUrlWWWDisplay": settings.SITE_URL_WWW_DISPLAY,
                "companyName": settings.COMPANY_NAME,
                "mainCompanyName": settings.MAIN_COMPANY_NAME,
                "siteUrlAddress": settings.SITE_URL_ADDRESS,
                "siteUrlAddressBr": settings.SITE_URL_ADDRESS_BR,
                "companyNumber": settings.COMPANY_NUMBER,
                "siteNameSmallCom": settings.SITE_NAME_SMALL_COM,
                "siteNameBigCom": settings.SITE_NAME_BIG_COM,
            }
            
            mail_request = MailRequestDTO(
                to=email,
                subject="Request To Set Your Sub User Account Password",
                template_name="subaccount-active-link-template.ftl"
            )
            
            try:
                CommonServices.sendEmail(mail_request, model)
            except Exception as ee:
                logging.error(f"SaveSubUser Invitation Error : {ee}")
        
        if old_tenant_id == 0:
            return api_response(200, "Add Sub Account Successfully.", resBody)
        else:
            return api_response(200, "Update Sub Account Successfully.", resBody)
            
    except Exception as e:
        logging.error(f"SaveSubUser Error : {e}", exc_info=True)
        return api_response(500, "Error Processing Request", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAllUser(request):
    resBody = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        sub_tenants = Tenants.objects.filter(ten_parent_id=tenant_id)
        
        users_data = []
        for sub_tenant in sub_tenants:
            sty_name = ""
            tenant_detail = TenantDetails.objects.filter(tenant__ten_id=sub_tenant.ten_id).first()
            if tenant_detail and tenant_detail.td_sub_account_type_id:
                try:
                    sty_name = SubaccountType.objects.get(styId=tenant_detail.td_sub_account_type_id).styName
                except:
                    pass
            users_data.append({
                "memberId": sub_tenant.ten_id,
                "firstName": sub_tenant.ten_first_name,
                "lastName": sub_tenant.ten_last_name,
                "email": sub_tenant.ten_email,
                "phone": sub_tenant.ten_phone,
                "parentMemberId": sub_tenant.ten_parent_id,
                "subaccountTypeId": tenant_detail.td_sub_account_type_id if tenant_detail else None,
                "subaccountTypeName": sty_name,
                "status": "Active" if sub_tenant.ten_status == 0 else "Pending",  # Java maps 0 -> Active, else Pending
                "secAns1": None,
                "secAns2": None,
                "secAns3": None,
                "secQus1": None,
                "secQus2": None,
                "secQus3": None,
                "city": None,
                "state": None,
                "country": None,
                "memberDefaultLanguage": None,
                "dateRegistered": None,
                "optin": None,
                "billDate": None
            })
            
        resBody["subaccount"] = users_data
        return api_response(200, "Fetch Data Successfully", resBody)
    except Exception as e:
        logging.error(f"GetAllUser Error : {e}")
        return api_response(500, "Error Processing Request", resBody)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSubUser(request, tenant_id):
    resBody = dict()
    try:

        # 1. PhoneNumbers cleanup
        try:
            phone_number_list = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id), phPhoneNumberClosed='N')
            for pn in phone_number_list:
                PhoneNumbers.objects.filter(pnId=pn.pnId).update(phPhoneNumberClosed='Y')
                # delete telnyx number
                if pn.phSid:
                    delete_telnyx_number(
                        ph_sid=pn.phSid,
                        telnyx_base_url=getattr(settings, 'TELNYX_BASE_URL', ''),
                        telnyx_api_key=getattr(settings, 'TELNYX_API_KEY', '')
                    )
                    # delete call forwarding
                    CommonServices.delete_number_call_forwarding(pn.phSid, tenant_id)
        except Exception as e:
            logging.error(f"DeleteSubUser PhoneNumbers cleanup Error: {e}")

        # 2. SpSmsPolling cleanup
        try:
            sp_polling_list = SpSmsPolling.objects.filter(iUserId=tenant_id)
            for sp in sp_polling_list:
                phone_number = PhoneNumbers.objects.get(pnId=sp.pnId)
                if phone_number.phSid:
                    delete_telnyx_number(
                        ph_sid=phone_number.phSid,
                        telnyx_base_url=getattr(settings, 'TELNYX_BASE_URL', ''),
                        telnyx_api_key=getattr(settings, 'TELNYX_API_KEY', '')
                    )
                    CommonServices.delete_number_call_forwarding(phone_number.phSid, tenant_id)
        except Exception as e:
            logging.error(f"DeleteSubUser SpSmsPolling cleanup Error: {e}")

        try:
            TenantDetails.objects.get(tenant__ten_id=tenant_id).delete()
            Tenants.objects.get(ten_id=tenant_id).delete()
        except Tenants.DoesNotExist:
            return api_response(500, "Error Processing Request", resBody)

        return api_response(200, "Sub Account Delete Successfully.", resBody)
    except Exception as e:
        logging.error(f"DeleteSubUser Error : {e}")
        return api_response(500, "Error Processing Request", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSubUserTypeEdit(request, sty_id):
    try:
        res_body = dict()
        sty_id = int(sty_id)
        if sty_id > 0:
            try:
                subaccount_type = SubaccountType.objects.get(styId=sty_id)
                res_body["subaccountType"] = {
                    "styId": subaccount_type.styId,
                    "styMemberId": subaccount_type.styMemberId,
                    "styName": subaccount_type.styName,
                    "pages": [] 
                }
            except SubaccountType.DoesNotExist:
                pass
        else:
            res_body["subaccountType"] = {
                "styId": 0,
                "styMemberId": get_final_tenant_id(request=request),
                "styName": "",
                "pages": []
            }

        page_action_names = PageActionName.objects.all()
        ac_name_list = []
        for pan in page_action_names:
            ac_name_list.append({
                "acName": pan.acName,
                "acCode": getattr(pan, 'acCode', pan.acName.upper() if pan.acName else "")
            })
        res_body["acName"] = ac_name_list

        subaccount_pages = SubaccountPage.objects.all().order_by('sp_name', 'sp_id')
        pages_list = []
        for page in subaccount_pages:
            details = SubaccountPageDetails.objects.filter(pgdPgId=page.sp_id).order_by('pgdId')
            page_actions = []
            checked_actions = []
            for detail in details:
                page_actions.append(detail.pgdActionName)
                if sty_id > 0:
                    try:
                        SubaccountPagePermission.objects.get(
                            spp_sub_id=sty_id, spp_action_name=detail.pgdActionName, spp_pg_id=page.sp_id
                        )
                        checked_actions.append(detail.pgdActionName)
                    except SubaccountPagePermission.DoesNotExist:
                        pass

            pages_list.append({
                "pgId": page.sp_id,
                "pgName": page.sp_name,
                "pgModuleName": page.sp_module_name,
                "pgdActionName": page_actions,
                "pgdCheckedActionName": checked_actions
            })
            
        res_body["pages"] = pages_list
        return api_response(200, "Sub User Type Fetched Successfully.", res_body)
    except Exception as e:
        logging.error(f"GetSubUserTypeEdit Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getPageActionName(request):
    try:
        page_action_names = PageActionName.objects.all()
        ac_name_list = []
        for pan in page_action_names:
            ac_name_list.append({
                "acId": pan.acId,
                "acName": pan.acName,
                "acCode": getattr(pan, 'acCode', pan.acName.upper() if pan.acName else "")
            })
        resBody = {
            "acName": ac_name_list
        }
        return api_response(200, "Fetch Data Successfully", resBody)
    except Exception as e:
        logging.error(f"GetPageActionName Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSubaccountPage(request):
    try:
        pages = SubaccountPage.objects.all().order_by('sp_name', 'sp_id')
        pages_list = []
        for p in pages:
            pages_list.append({
                "pgId": p.sp_id,
                "pgName": p.sp_name,
                "pgModuleName": p.sp_module_name,
                "pgMenuName": p.sp_menu_name
            })
        resBody = {
            "pages": pages_list
        }
        return api_response(200, "Fetch Data Successfully", resBody)
    except Exception as e:
        logging.error(f"GetSubaccountPage Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSubaccountPageDetails(request, pgId):
    try:
        details = SubaccountPageDetails.objects.filter(pgdPgId=pgId).order_by('pgdId')
        details_list = []
        for d in details:
            details_list.append({
                "pgdId": d.pgdId,
                "pgdPgId": d.pgdPgId,
                "pgdActionName": d.pgdActionName
            })
        resBody = {
            "pgdActionName": details_list
        }
        return api_response(200, "Fetch Data Successfully", resBody)
    except Exception as e:
        logging.error(f"GetSubaccountPageDetails Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSubUserType(request, styId):
    resBody = {}
    try:
        try:
            sub_type = SubaccountType.objects.get(styId=styId)
            sub_type.delete()
            SubaccountPagePermission.objects.filter(spp_id=styId).delete()
            return api_response(200, "Sub Account Type Delete Successfully.", resBody)
        except SubaccountType.DoesNotExist:
            return api_response(500, "Error Processing Request", resBody)
    except Exception as e:
        logging.error(f"DeleteSubUserType Error : {e}")
        return api_response(500, "Error Processing Request", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSubUserType(request):
    resBody = dict()
    try:
        data = request.data
        sty_id = data.get('styId', 0)
        sty_name = data.get('styName', '')
        sty_member_id = data.get('styMemberId') or get_final_tenant_id(request=request)
        sty_member_id = get_client_id_by_tenant_id(sty_member_id)
        pages_permissions = data.get('pages', [])

        if sty_id == 0:
            type_exists = SubaccountType.objects.filter(styMemberId=sty_member_id, styName=sty_name).exists()
        else:
            type_exists = SubaccountType.objects.filter(styMemberId=sty_member_id, styName=sty_name).exclude(styId=sty_id).exists()
            
        if not type_exists:
            if sty_id == 0:
                sub_type = SubaccountType(
                    styName=sty_name, 
                    styMemberId=sty_member_id,
                    styCreatedDate=timezone.now()
                )
            else:
                try:
                    sub_type = SubaccountType.objects.get(styId=sty_id)
                except SubaccountType.DoesNotExist:
                    return api_response(500, "Error Processing Request", resBody)
                sub_type.styName = sty_name
                
            sub_type.save()
            new_sty_id = sub_type.styId
            
            if sty_id > 0:
                SubaccountPagePermission.objects.filter(spp_sub_id=new_sty_id).delete()
                
            permissions_to_create = []
            for p in pages_permissions:
                permissions_to_create.append(SubaccountPagePermission(
                    spp_pg_id=p.get('perPgId'),
                    spp_action_name=p.get('perActionName'),
                    spp_sub_id=new_sty_id,
                    spp_client_id=sty_member_id
                ))
            
            if permissions_to_create:
                SubaccountPagePermission.objects.bulk_create(permissions_to_create)
                
            msg = "Add Sub Account Type Successfully." if sty_id == 0 else "Update Sub Account Type Successfully."
            return api_response(200, msg, resBody)
        else:
            return api_response(304, "Sub Account Type Already In Used.", resBody)
    except Exception as e:
        logging.error(f"SaveSubUserType Error : {e}")
        return api_response(500, "Error Processing Request", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSubUserPhoneList(request):
    resBody = {}
    try:
        tenant_id = get_final_tenant_id(request=request)
        main_client = Clients.objects.get(cliTenantId=tenant_id)
        sub_tenants = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_parent_id": tenant_id
                }
            },
            return_type="all"
        )

        users_list = []
        for sub_tenant in sub_tenants:
            chat_phone_number = get_phone_numbers_first(sub_tenant.ten_id, "CHAT")
            # Replicating Java getMemName logic with decryption
            first_name = sub_tenant.ten_first_name
            last_name = sub_tenant.ten_last_name
            ten_name = f"{first_name} {last_name}".strip()

            # Replicating Java findSubUserPhoneList logic
            phone_numbers = PhoneNumbers.objects.filter(
                phClientId=get_client_id_by_tenant_id(tenant_id),
                phPhoneNumberClosed='N'
            )

            str_number_list = []
            number_call_forwarding = None

            for pn in phone_numbers:
                # Exclude main account's phone SID if it matches
                cli_sms_account_sid = getattr(main_client, 'cliSmsAccountSid', None)
                if cli_sms_account_sid != pn.phSid:
                    str_number_list.append(clean_me_number(pn.phPhoneNumber))

                # Fetch Call Forwarding (Inner loop logic from Java)
                try:
                    cf = NumberCallForwarding.objects.filter(
                        cfnTwilioPhoneSid=pn.phSid,
                        cfnMemberId=tenant_id
                    ).order_by('-cfnId').first()

                    if cf:
                        number_call_forwarding = {
                            "cfnId": cf.cfnId,
                            "cfnTwilioNumber": cf.cfnTwilioNumber,
                            "cfnTwilioPhoneSid": cf.cfnTwilioPhoneSid,
                            "cfnForwardingCountryCode": cf.cfnForwardingCountryCode,
                            "cfnForwardingNumber": cf.cfnForwardingNumber,
                            "cfnMemberId": cf.cfnMemberId,
                            "cfnDateTime": cf.cfnDateTime.strftime("%Y-%m-%dT%H:%M:%S") if cf.cfnDateTime else None
                        }
                except Exception:
                    pass

            users_list.append({
                "memberId": sub_tenant.ten_id,
                "memName": ten_name,
                "twilioNumber": ", ".join(str_number_list),
                "conversationsTwilioNumber": chat_phone_number.phPhoneNumber if chat_phone_number else None,
                "btnDelete": "N",
                "numberCallForwarding": number_call_forwarding
            })

        resBody["subUserList"] = users_list
        return api_response(200, "Fetch Sub Account Successfully.", resBody)
    except Exception as e:
        logging.error(f"getSubUserPhoneList Error : {e}")
        return api_response(500, "Error Processing Request", {})
