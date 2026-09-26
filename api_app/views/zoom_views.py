import logging
import requests
import json
import uuid
from datetime import datetime
from django.conf import settings
from django.shortcuts import redirect
from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response, get_final_tenant_id
from common_app.services import commonServices, MailRequestDTO
from common_app.models import Zoom, ZoomDetails, Userlist, Clients
from auth_app.models import Tenants
import base64

logger = logging.getLogger(__name__)

def format_date_per_rule_9(date_val):
    if not date_val:
        return None
    if isinstance(date_val, str):
        try:
            date_val = datetime.strptime(date_val, "%Y-%m-%d %H:%M:%S")
        except:
            return date_val
    # Rule 9: MM-dd-yyyy MM-dd-yyyy HH:mm:ss.
    return date_val.strftime("%m-%d-%Y %m-%d-%Y %H:%M:%S.")

def uc_words(s):
    if not s:
        return s
    return ' '.join([word.capitalize() for word in s.split()])

@api_view(['GET'])
def zoomLogin(request):
    url = f"https://zoom.us/oauth/authorize?response_type=code&client_id={settings.ZOOM_CLIENT_ID}&redirect_uri={settings.ZOOM_REDIRECT_URL}"
    return redirect(url)

@api_view(['GET'])
def zoomOauth(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    code = request.query_params.get("code")
    
    res_body = {"error": ""}
    try:
        request_url = "https://zoom.us/oauth/token"
        auth_header = base64.b64encode(f"{settings.ZOOM_CLIENT_ID}:{settings.ZOOM_CLIENT_SECRET}".encode()).decode()
        
        headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.ZOOM_REDIRECT_URL
        }
        
        response = requests.post(request_url, headers=headers, data=data)
        token_data = response.json()
        
        if response.status_code == 200:
            client = Clients.objects.get(cliTenantId=tenant_id)
            client.cliZoomToken = json.dumps(token_data)
            client.save()
            return api_response(200, "Zoom Connected Successfully.", res_body)
        else:
            res_body["error"] = token_data.get("reason", "Zoom Failed To Authenticate.")
            return api_response(500, res_body["error"], res_body)
            
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] ZoomOauth Error : {e}")
        return api_response(500, "Zoom Failed To Authenticate.", res_body)

@api_view(['GET'])
def zoomLogout(request):
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        client.cliZoomToken = None
        client.save()
        return api_response(200, "Zoom Disconnected Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] ZoomLogout Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

@api_view(['GET'])
def getZoomAuthentication(request):
    tenant_id = get_final_tenant_id(request=request)
    client = Clients.objects.get(cliTenantId=tenant_id)
    
    res_body = {"zoom": False}
    if client.cliZoomToken:
        if client.cliZoomToken.strip():
            res_body["zoom"] = True
            
    return api_response(200, "Fetch Zoom Authentication Successfully.", res_body)

@api_view(['POST'])
def addZoomMeeting(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    data = request.data
    email_ids = data.get("emailIds", [])
    sub_tenant_id = data.get("subTenantId", 0)
    
    res_body = {"error": "", "joinUrl": ""}
    
    try:
        if len(email_ids) > 0:
            tenant = Tenants.objects.get(ten_id=tenant_id)
            client = Clients.objects.get(cliTenantId=tenant_id)
            zoom_token_data = json.loads(client.cliZoomToken)
            access_token = zoom_token_data.get("access_token")
            
            rnd_number = str(uuid.uuid4())
            password = rnd_number[-10:]
            
            request_url = "https://api.zoom.us/v2/users/me/meetings"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "topic": settings.SITE_NAME,
                "type": 1,
                "start_time": datetime.now(),
                "password": password
            }
            
            response = requests.post(request_url, headers=headers, json=payload)
            meeting_data = response.json()
            
            if response.status_code in [200, 201]:
                join_url = meeting_data.get("join_url")
                
                zoom = Zoom()
                zoom.zmType = meeting_data.get("type")
                zoom.zmStartTime = datetime.now()
                zoom.zmJoinUrl = join_url
                zoom.zmPassword = meeting_data.get("password")
                zoom.zmMemberId = tenant_id
                zoom.zmDate = datetime.now()
                zoom.subMemberId = sub_tenant_id
                zoom.save()
                
                res_body["joinUrl"] = join_url
                
                # Email logic
                if sub_tenant_id == 0:
                    fname = tenant.ten_first_name
                    lname = tenant.ten_last_name
                    invt_name = f"{uc_words(fname)} {uc_words(lname)}"
                else:
                    sub_tenant = Tenants.objects.get(ten_id=tenant_id)
                    fname = sub_tenant.ten_first_name
                    lname = sub_tenant.ten_last_name
                    invt_name = f"{uc_words(fname)} {uc_words(lname)}"
                
                for email_id in email_ids:
                    zoom_details = ZoomDetails()
                    zoom_details.zmdZmId = zoom.zmId
                    zoom_details.zmdClientId = email_id
                    zoom_details.save()
                    
                    try:
                        contact = Userlist.objects.get(memberId=tenant_id, emailId=email_id)
                        email = contact.email
                        if email:
                            email = email.lower().strip()
                            
                            model = {
                                "SITEURL": settings.IMAGE_SITE_URL,
                                "invtName": invt_name,
                                "joinUrl": join_url,
                                "toAdminSupportEmail": settings.TO_ADMIN_SUPPORT_EMAIL,
                                "siteUrlWWW": settings.SITE_URL_WWW,
                                "siteName": settings.SITE_NAME,
                                "siteUrlWWWDisplay": settings.SITE_URL_WWW_DISPLAY,
                                "companyName": settings.COMPANY_NAME,
                                "mainCompanyName": settings.MAIN_COMPANY_NAME,
                                "siteUrlAddress": settings.SITE_URL_ADDRESS,
                                "siteUrlAddressBr": settings.SITE_URL_ADDRESS_BR,
                                "companyNumber": settings.COMPANY_NUMBER,
                                "siteNameSmallCom": settings.SITE_NAME_SMALL_COM,
                                "siteNameBigCom": settings.SITE_NAME_BIG_COM
                            }
                            
                            mail_dto = MailRequestDTO(to=email, subject="Zoom Meeting Invitation", template_name="zoom-template.ftl")
                            commonServices.sendEmail(mail_dto, model)
                    except Userlist.DoesNotExist:
                        continue
                
                return api_response(200, "Add Zoom Meeting Successfully.", res_body)
            else:
                if response.status_code == 401:
                    res_body["error"] = "401"
                    client = Clients.objects.get(cliTenantId=tenant_id)
                    client.cliZoomToken = None
                    client.save()
                else:
                    res_body["error"] = "Zoom Failed To Authenticate."
                return api_response(500, res_body["error"], res_body)
                
        else:
            res_body["error"] = "Please Set Email To Client Contact."
            return api_response(500, res_body["error"], res_body)
            
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] AddZoomMeeting Error : {e}")
        res_body["error"] = "Zoom Failed To Authenticate."
        return api_response(500, res_body["error"], res_body)
