import logging
import traceback
from rest_framework.decorators import api_view, permission_classes
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
from common_app.models import Domains, DomainEmails
from django.utils import timezone
from django.conf import settings
from auth_app.models import Tenants
from common_app.decrypt_string import DecryptString
from common_app.services import commonServices, MailRequestDTO
from common_app.custom_permissions import WhitelistPermission

def clean_uid(uid):
    if uid is None:
        return '0'
    return str(uid)

@api_view(['GET', 'POST'])
@permission_classes([WhitelistPermission])
def getDomainEmailById(request, deId=None):
    try:
        domain_email = DomainEmails.objects.filter(de_id=deId).first()
        if not domain_email:
            return api_response(200, "Domain Email Fetched Successfully.", None)
            
        resBody = {
            "deId": domain_email.de_id,
            "uid": clean_uid(domain_email.de_client_id),
            "did": domain_email.de_did,
            "email": domain_email.de_email,
            "date": domain_email.de_create_date.strftime("%Y-%m-%dT%H:%M:%S.000+00:00") if domain_email.de_create_date else None
        }
        return api_response(200, "Domain Email Fetched Successfully.", resBody)
    except Exception as e:
        logging.error(f"GetDomainEmailById Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getDomainEmailList(request, flag):
    try:
        final_member_id = get_final_tenant_id(request=request)
        email_list = []
        if flag == 0:
            emails = DomainEmails.objects.filter(de_client_id=get_client_id_by_tenant_id(final_member_id))
            for e in emails:
                email_list.append({
                    "deId": e.de_id,
                    "uid": clean_uid(e.de_client_id),
                    "did": e.de_did,
                    "email": e.de_email,
                    "date": e.de_create_date.strftime("%Y-%m-%dT%H:%M:%S.000+00:00") if e.de_create_date else None
                })
        else:
            domains = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(final_member_id), domStatus=1).values_list('domId', flat=True)
            emails = DomainEmails.objects.filter(de_did__in=domains)
            for e in emails:
                email_list.append({
                    "deId": e.de_id,
                    "uid": clean_uid(e.de_client_id),
                    "did": e.de_did,
                    "email": e.de_email,
                    "date": e.de_create_date.strftime("%Y-%m-%dT%H:%M:%S.000+00:00") if e.de_create_date else None
                })
        
        resBody = {"domainEmail": email_list}
        return api_response(200, "Domain Email Fetched Successfully.", resBody)
    except Exception as e:
        traceback.print_exc()
        logging.error(f"GetDomainEmailList Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveDomainEmail(request):
    try:
        data = request.data

        raw_email = data.get('email', '')
        uid = DecryptString.set_enc_dec_user(data.get("uid"), "display", "Y")
        decrypted_email = DecryptString.set_enc_dec_user(raw_email, "display", "Y")
        domain_email_exists = DomainEmails.objects.filter(de_client_id=get_client_id_by_tenant_id(uid), de_email=decrypted_email).exists()
        
        resBody = {}
        
        if not domain_email_exists:
            domain_name = decrypted_email.split('@')[1] if '@' in decrypted_email else ''
            
            domain_obj = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(uid), domDomain=domain_name).first()
            if not domain_obj:
                domain_obj = Domains()
                domain_obj.domCreateDate = timezone.now()
                domain_obj.domClientId = get_client_id_by_tenant_id(uid)
                domain_obj.domDomain = domain_name
                domain_obj.domStatus = 0
                domain_obj.save()
            
            domain_id = domain_obj.domId
            
            new_domain_email = DomainEmails()
            new_domain_email.de_client_id = get_client_id_by_tenant_id(uid)
            new_domain_email.de_did = domain_id
            new_domain_email.de_email = decrypted_email
            new_domain_email.de_create_date = timezone.now()
            new_domain_email.save()
            
            site_name_big_com = getattr(settings, 'SITE_NAME_BIG_COM', 'SalesAndMarketing.ai')
            return api_response(200, f"Your Email Address Has Been Verified With {site_name_big_com}. Thank You!!.", resBody)
        else:
            return api_response(304, "Email Already Verified.", resBody)

    except Exception as e:
        logging.error(f"SaveDomainEmail Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def checkDomainEmailExist(request):
    try:
        data = request.data
        email = data.get('email', '')
        
        final_tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=final_tenant_id)

        domain_email_exists = DomainEmails.objects.filter(de_client_id=get_client_id_by_tenant_id(final_tenant_id), de_email=email).exists()
        resBody = {}
        
        if domain_email_exists:
            return api_response(200, f"{email} Has Been Verified.", resBody)
        else:                    
            mail_dto = MailRequestDTO()
            mail_dto.template_name = "activate-email-template.ftl"
            mail_dto.subject = "Activate Email"
            mail_dto.to = email
            
            domain_name = email.split('@')[1] if '@' in email else ''
            enc_member_id = DecryptString.set_enc_dec_user(str(final_tenant_id), "", "Y")
            enc_email = DecryptString.set_enc_dec_user(email, "", "Y")
            verbtn = f"{getattr(settings, 'SITE_URL', '')}emailverification?v={enc_member_id}&d={enc_email}"
            
            model_data = {
                "domain": domain_name,
                "firstName": tenant.ten_first_name if tenant else "",
                "lastName": tenant.ten_last_name if tenant else "",
                "v": email,
                "verbtn": verbtn,
                "SITEURL": getattr(settings, 'SITE_URL', ''),
                "siteName": getattr(settings, 'SITE_NAME', ''),
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
            

            response = commonServices.sendEmail(mail_dto, model_data)
            
            if response.status:
                return api_response(200, "We have sent you an email to acknowledge this security setting.\n\nFollow the instructions in the verification email and than refresh this page.\n\nYou may need to wait 24 hours for DNS to propagate before you can continue.  When you see your domain name on this page you are ready to proceed.", resBody)
            else:
                return api_response(204, "Error occurred processing your request.", "")
                
    except Exception as e:
        logging.error(f"CheckDomainEmailExist Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteDomainEmail(request, domainEmailId):
    resBody = {}
    try:
        domain_email = DomainEmails.objects.filter(de_id=domainEmailId).first()
        if domain_email:
            domain_email.delete()
            return api_response(200, "Domain Email Deleted Successfully.", resBody)
        else:
            return api_response(500, "Error Processing Request", resBody)
    except Exception as e:
        logging.error(f"DeleteDomainEmail Error : {e}")
        return api_response(500, "Error Processing Request", resBody)

