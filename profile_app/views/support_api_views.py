import hashlib
from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response, get_final_tenant_id, get_tenants, get_client_id_by_tenant_id
from profile_app.models import SupportApiModule, SupportApiPermission, WhiteListingUrls
from django.utils import timezone
from auth_app.models import TenantDetails
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

def to_ms_timestamp(dt):
    if dt:
        # datetime.timestamp() returns seconds, we need milliseconds
        return int(dt.timestamp() * 1000)
    return None

@api_view(['GET', 'POST'])
def getSupportApiModuleList(request):
    try:
        modules = SupportApiModule.objects.all()
        module_list = []
        for m in modules:
            module_list.append({
                "mdId": m.mdId,
                "mdName": m.mdName
            })
        
        resBody = {
            "supportApiModuleList": module_list
        }
        return api_response(200, "Fetch Support Api Module List Successfully.", resBody)
    except Exception as e:
        logging.error(f"GetSupportApiModuleList Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getSupportApiSetting(request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        # Permissions
        permissions = SupportApiPermission.objects.filter(perMemberId=get_client_id_by_tenant_id(final_tenant_id))
        permission_list = []
        for p in permissions:
            permission_list.append({
                "perId": p.perId,
                "perMdId": p.perMdId,
                "perMemberId": p.perMemberId,
            })
            
        # Tenant auth settings
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": final_tenant_id
                }
            }
        )
        
        resBody = {
            "supportApiPermissionList": permission_list,
            "allowApiAccess": tenant.td_enable_api,
            "supportApiAuth": {
                "secretKey": tenant.td_auth_key,
                "authToken": tenant.td_auth_token
            }
        }
        return api_response(200, "Fetch Support Api Setting Successfully.", resBody)
    except Exception as e:
        logging.error(f"GetSupportApiSetting Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
def saveAllowApiAccess(request: Request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        enable_api = request.data.get('enableApi', 'N')
        
        tenant_details = TenantDetails.objects.get(tenant__ten_id=final_tenant_id)
        tenant_details.td_enable_api = enable_api
        
        if not tenant_details.td_auth_key or tenant_details.td_auth_key == "":
            current_ts = datetime.now()
            auth_key_raw = f"{final_tenant_id}S@M{current_ts}"
            tenant_details.td_auth_key = hashlib.md5(auth_key_raw.encode('utf-8')).hexdigest()
            
            auth_token_raw = f"{tenant_details.tenant.ten_email}S@M{current_ts}"
            tenant_details.td_auth_token = hashlib.md5(auth_token_raw.encode('utf-8')).hexdigest()
            
        tenant_details.save()
        
        res_body = {
            "secretKey": tenant_details.td_auth_key,
            "authToken": tenant_details.td_auth_token,
            "error": ""
        }
        return api_response(200, "Save Allow Api Access Successfully", res_body)
    except Exception as e:
        logger.error(f"SaveAllowApiAccess Error : {e}")
        return api_response(500, "Error Processing Request", {"error": "Invalid Data"})


@api_view(['POST'])
def saveAllowApiTo(request: Request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        allow_api_to = request.data.get('allowApiTo', [])
        
        try:
            SupportApiPermission.objects.filter(perMemberId=get_client_id_by_tenant_id(final_tenant_id)).delete()
        except Exception:
            pass
            
        for md_id in allow_api_to:
            SupportApiPermission.objects.create(
                perMemberId=get_client_id_by_tenant_id(final_tenant_id),
                perMdId=md_id,
            )
            
        return api_response(200, "Save Allow Api Access To Successfully", {"error": ""})
    except Exception as e:
        logger.error(f"SaveAllowApiTo Error : {e}")
        return api_response(500, "Error Processing Request", {"error": "Invalid Data"})


@api_view(['GET'])
def generateAuthKey(request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        if not final_tenant_id:
            return api_response(400, "Tenant ID is not get", {})

        tenant_details = TenantDetails.objects.get(tenant__ten_id=final_tenant_id)
        current_ts = datetime.now()
        
        auth_key_raw = f"{final_tenant_id}S@M{current_ts}"
        auth_key = hashlib.md5(auth_key_raw.encode('utf-8')).hexdigest()
        
        auth_token_raw = f"{tenant_details.tenant.ten_email}S@M{current_ts}"
        auth_token = hashlib.md5(auth_token_raw.encode('utf-8')).hexdigest()
        tenant_details.td_auth_key = auth_key
        tenant_details.td_auth_token = auth_token
        tenant_details.td_enable_api = "Y"
        tenant_details.save()

        res_body = {
            "secretKey": auth_key,
            "authToken": auth_token
        }
        
        return api_response(200, "Successfully", res_body)
    except Exception as e:
        logger.error(f"GenerateAuthKey Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['DELETE'])
def deleteWhiteListingUrls(request: Request):
    try:
        # Match Java's deleteWhiteListingUrls(DeleteWhiteListingUrlsDto deleteWhiteListingUrlsDto)
        ids = request.data.get("id",[])
        
        if ids is not None and len(ids) > 0:
            for url_id in ids:
                # Match Java's whiteListingUrlsRepository.findById(id).isPresent() 
                # and whiteListingUrlsRepository.deleteById(id)
                WhiteListingUrls.objects.filter(id=url_id).delete()
                
        resBody = {}
        return api_response(200, "Whitelisting Urls Deleted Successfully.", resBody)
    except Exception as e:
        logger.error(f"DeleteWhiteListingUrls Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getWhiteListingUrlsList(request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        urls = WhiteListingUrls.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id))
        url_list = []
        for u in urls:
            url_list.append({
                "id": u.id,
                "tenantId": get_client_id_by_tenant_id(u.memberId),
                "url": u.url,
                "createdDate": to_ms_timestamp(u.createdDate)
            })
            
        resBody = {
            "whiteListingUrls": url_list
        }
        return api_response(200, "Fetch Whitelisting Urls Successfully.", resBody)
    except Exception as e:
        logging.error(f"GetWhiteListingUrlsList Error : {e}")
        return api_response(500, "Error Processing Request", {})


@api_view(['POST'])
def saveWhiteListingUrls(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        # Extract data from request body
        urls_data = request.data

        # Validation: check if list is null or empty
        if not urls_data:
            return api_response(400, "Invalid Data", {"error": "Invalid Data"})

        for dto in urls_data:
            dto_id = dto["id"] or 0
            url_value = dto["url"] or ''

            # Logic: If ID is 0, create new; otherwise, fetch existing
            if dto_id == 0:
                white_listing_url = WhiteListingUrls()
            else:
                try:
                    white_listing_url = WhiteListingUrls.objects.get(id=dto_id)
                except WhiteListingUrls.DoesNotExist:
                    # Optional: handle cases where an ID is provided but doesn't exist
                    continue

                    # Update fields
            white_listing_url.url = url_value
            white_listing_url.memberId = get_client_id_by_tenant_id(tenant_id)
            white_listing_url.createdDate = timezone.now()

            # Save to database
            white_listing_url.save()

        return api_response(200, "Whitelisting Urls Processed Successfully", {})

    except Exception as e:
        logger.error(f"[ TenantId : {tenant_id} ] SaveWhiteListingUrls Error : {e}")
        return api_response(500, "Error Processing Request", {"error": "Invalid Data"})

