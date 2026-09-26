import logging
from rest_framework.decorators import api_view, permission_classes
from common_app.utils import api_response, get_client_id_by_tenant_id
from profile_app.models import WarmupLog
from common_app.models import Domains, DomainEmails
from common_app import dns_functions, domain_check_service
from common_app.services import commonServices, MailRequestDTO
from common_app.utils import get_final_tenant_id
from common_app.custom_permissions import WhitelistPermission
from django.utils import timezone
from django.conf import settings

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getDomainList(request):
    try:        
        tenant_id = get_final_tenant_id(request=request)
        domains = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant_id))
        domain_list = []
        for d in domains:
            domain_list.append({
                "id": d.domId,
                "uid": d.domClientId,
                "domain": d.domDomain,
                "dmarc": d.domDmarc,
                "spf": d.domSpf,
                "dkim": d.domDkim,
                "bimi": d.domBimi,
                "status": d.domStatus,
                "domainReputation": d.domDomainReputation
            })
        resBody = {
            "domain": domain_list
        }
        return api_response(200, "Domain fetched successfully.", resBody)
    except Exception as e:
        logging.error(f"GetDomainList Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveDomain(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        data = request.data
        domain_name = data.get('domain', '')

        dns_check = domain_check_service.checkDns(domain_name)
        
        ff = 0
        f = 0
        site_name_small_com = getattr(settings, 'SITE_NAME_SMALL_COM', 'salesandmarketing.ai')
        
        if domain_name == site_name_small_com:
            ff = 1
        else:
            if dns_check.get("spf") == "Y" and dns_check.get("dkim") == "Y":
                f = 1
                
        if ff == 1 or f == 1:
            reputation = "Healthy"
            
            status = 0
            if ff == 1:
                status = 1
            else:
                if dns_check.get("spf") == "Y" and dns_check.get("dkim") == "Y" and dns_check.get("dmarc") == "Y":
                    status = 1
            
            domain_obj = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant_id), domDomain=domain_name).first()
            
            if not domain_obj:
                domain_obj = Domains()
                domain_obj.domCreateDate = timezone.now()
                domain_obj.domDomainCapacity = 1000
                domain_obj.domDomainCapacityUsed = 0
            
            domain_obj.domClientId = get_client_id_by_tenant_id(tenant_id)
            domain_obj.domDomain = domain_name
            domain_obj.domSpf = dns_check.get("spf")
            domain_obj.domDkim = dns_check.get("dkim")
            domain_obj.domDmarc = dns_check.get("dmarc")
            domain_obj.domBimi = dns_check.get("bimi")
            domain_obj.domEsp = dns_check.get("esp")
            domain_obj.domDsp = dns_check.get("dsp")
            domain_obj.domDomainReputation = reputation
            domain_obj.domStatus = status
            
            domain_obj.save()
            
            resBody = {
                "id": domain_obj.domId,
                "uid": domain_obj.domClientId,
                "domain": domain_obj.domDomain,
                "domainCapacity": domain_obj.domDomainCapacity,
                "domainCapacityUsed": domain_obj.domDomainCapacityUsed,
                "dmarc": domain_obj.domDmarc,
                "spf": domain_obj.domSpf,
                "dkim": domain_obj.domDkim,
                "bimi": domain_obj.domBimi,
                "status": domain_obj.domStatus,
                "vDate": domain_obj.domCreateDate.strftime("%m-%d-%Y %H:%M:%S") if domain_obj.domCreateDate else None,
                "esp": domain_obj.domEsp,
                "dsp": domain_obj.domDsp,
                "domainReputation": domain_obj.domDomainReputation
            }
            
            return api_response(200, "Great, your domain has been verified and is ready to use.\n\nWe recommend you verify at least one email address with this domain name also.", resBody)
        else:
            return api_response(204, "Sorry, we were not able to verify your domain DNS with DKIM and SPF values provides by us.\n\nPlease update your domain DNS with DKIM and SPF values provided and try again.", {})

    except Exception as e:
        logging.error(f"SaveDomain Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteDomain(request, domainId):
    try:
        try:
            domain_obj = Domains.objects.filter(domId=domainId).first()
            domain_email_obj = DomainEmails.objects.filter(did=domainId).first()          
            if domain_obj:  
                domain_obj.delete()
            if domain_email_obj:
                domain_email_obj.delete()
        except Domains.DoesNotExist:
            return api_response(404, "Domain Not Found", {})
        resBody = {}
        return api_response(200, "Domain deleted successfully.", resBody)
    except Exception as e:
        logging.error(f"DeleteDomain Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def buyWarmupService(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        data = request.data
        warm_email = data.get('warmEmail', '')
        warm_domain = data.get('warmDomain', '')
        sub_tenant_id = data.get('subTenantId', 0)
        
        resBody = {"error": ""}
        
        country_setting = commonServices.country_setting_by_tenant_id(tenant_id)
        warmup_price = country_setting.cnty_warmup_price if country_setting else 0.0
        
        count_warm_id = WarmupLog.objects.filter(warmEmail=warm_email, memberId=get_client_id_by_tenant_id(tenant_id)).count()
        
        if count_warm_id == 0:
            warmup_log = WarmupLog()
            warmup_log.warmDomain = warm_domain
            warmup_log.warmEmail = warm_email
            warmup_log.warmStartDate = timezone.now()
            
            # Add one month logic
            end_date = timezone.now()
            month = end_date.month % 12 + 1
            year = end_date.year + (end_date.month // 12)
            warmup_log.warmEndDate = end_date.replace(year=year, month=month)
            
            warmup_log.memberId = get_client_id_by_tenant_id(tenant_id)
            warmup_log.warmPrice = warmup_price
            warmup_log.save()
            
            commonServices.saveCampaignTransaction(
                None,
                f"Add email : {warm_email}",
                1,
                "domain warmup",
                None,
                "uninvoiced",
                None,
                get_client_id_by_tenant_id(tenant_id),
                "0",
                warmup_price,
                warmup_price,
                0,
                None,
                None,
                sub_tenant_id
            )
            
            # send email logic
            model_data = {
                "SITEURL": getattr(settings, 'IMAGE_SITE_URL', ''),
                "msgBody": f"<p>We have got new domain warmup registration.</p><p>Tenant Id : {tenant_id}</p><p>Domain : {warm_email.split('@')[-1] if '@' in warm_email else ''}</p><p>Email : {warm_email}</p>",
                "siteName": getattr(settings, 'SITE_NAME', ''),
                "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', ''),
                "companyName": getattr(settings, 'COMPANY_NAME', ''),
                "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', '')
            }
            
            mail_dto = MailRequestDTO()
            mail_dto.to = getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', '')
            mail_dto.template_name = "email-warmup-template.ftl"
            mail_dto.subject = "Domain Warmup Registration"
            
            commonServices.sendEmail(mail_dto, model_data)
            
            # secondary email
            mail_dto.to = "ritesh@kaiasoft.com"
            commonServices.sendEmail(mail_dto, model_data)
            
            return api_response(200, "Buy Warmup Service Successfully", resBody)
        else:
            resBody["error"] = "error1"
            return api_response(500, "Domain Warmup Service Already Exists", resBody,sendErrorAs200=True)
            
    except Exception as e:
        logging.error(f"BuyWarmupService Error : {e}")
        return api_response(500, "Error Processing Request", {},sendErrorAs200=True)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getDNSProvider(request):
    try:
        domain = request.GET.get('domainName', '')
        resBody = dict()
        resBody["error"] = ""
        resBody["dnsProvider"] = dns_functions.DNSFunction.getDNSProvider(domain)
        return api_response(200, "DNS Provider fetched successfully.", resBody)
    except Exception as e:
        logging.error(f"GetDNSProvider Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkDMARC(request):
    try:
        domain = request.GET.get('domainName', '')
        resBody = dict()
        resBody["error"] = ""
        resBody["checkDMARC"] = dns_functions.DNSFunction.checkDMARC(domain)
        return api_response(200, "Check DMARC successfully.", resBody)
    except Exception as e:
        logging.error(f"CheckDMARC Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkSPF(request):
    try:
        domain = request.GET.get('domainName', '')
        resBody = dict()
        resBody["error"] = ""
        resBody["checkSPF"] = dns_functions.DNSFunction.checkSPF(domain)
        return api_response(200, "Check SPF successfully.", resBody)
    except Exception as e:
        logging.error(f"CheckSPF Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getESP(request):
    try:
        domain = request.GET.get('domainName', '')
        resBody = dict()
        resBody["error"] = ""
        resBody["esp"] = dns_functions.DNSFunction.getESP(domain)
        return api_response(200, "ESP fetched successfully.", resBody)
    except Exception as e:
        logging.error(f"GetESP Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getBIMI(request):
    try:
        domain = request.GET.get('domainName', '')
        resBody = dict()
        resBody["error"] = ""
        resBody["bimi"] = dns_functions.DNSFunction.getBIMI(domain)
        return api_response(200, "BIMI fetched successfully.", resBody)
    except Exception as e:
        logging.error(f"GetBIMI Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def domainChecker(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        domain = request.GET.get('domainName', '')
        
        resBody = {
            "error": "",
            "spf": False,
            "dkim": False,
            "dmarc": False
        }

        public_domain_list = [
            "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.co.in", 
            "zoho.com", "mail.com", "aol.com", "salesandmarketing.ai", getattr(settings, 'SITE_NAME_SMALL_COM', '')
        ]

        dns_check = domain_check_service.checkDns(domain)
        status = 0

        if domain in public_domain_list:
            status = 1
        else:
            if dns_check.get("spf") == "Y" and dns_check.get("dkim") == "Y" and dns_check.get("dmarc") == "Y":
                status = 1

        if dns_check.get("spf") == "Y" or status == 1:
            resBody["spf"] = True
        else:
            resBody["error"] = "error1"

        if dns_check.get("dkim") == "Y" or status == 1:
            resBody["dkim"] = True
        else:
            resBody["error"] = "error1"

        if dns_check.get("dmarc") == "Y" or status == 1:
            resBody["dmarc"] = True
        else:
            resBody["error"] = "error1"

        if status == 0:
            Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant_id), domDomain=domain).update(domStatus=status)

        if resBody.get("error") == "":
            return api_response(200, "Successful", resBody)
        elif resBody.get("error") == "error1":
            return api_response(204, "Successful", resBody)
        else:
            return api_response(500, "Something went wrong.", resBody)
            
    except Exception as e:
        logging.error(f"DomainChecker Error : {e}")
        return api_response(500, "Error Processing Request", {})
