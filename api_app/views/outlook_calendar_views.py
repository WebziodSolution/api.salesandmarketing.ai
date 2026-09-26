from rest_framework.decorators import api_view
from django.shortcuts import redirect
from django.conf import settings
from rest_framework.request import Request
from common_app.models import CalendarSetup
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
import requests
import logging
from datetime import datetime, timezone, timedelta
import urllib.parse

logger = logging.getLogger(__name__)

def refresh_outlook_token(outlook_calendar_data):
    refresh_token = outlook_calendar_data.csRefreshToken
    if not refresh_token:
        return None
    
    url = f"{settings.OUTLOOK_CALENDAR_AUTHORIZE_API_URI}token"
    data = {
        "client_id": settings.OUTLOOK_CLIENT_ID,
        "client_secret": settings.OUTLOOK_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": settings.OUTLOOK_CLIENT_SCOPE
    }
    
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            res_json = response.json()
            access_token = res_json.get("access_token")
            outlook_calendar_data.csAccessToken = access_token
            if "refresh_token" in res_json:
                outlook_calendar_data.csRefreshToken = res_json.get("refresh_token")
            outlook_calendar_data.save()
            return access_token
    except Exception as e:
        logger.error(f"Error refreshing Outlook token: {e}")
    
    return None

@api_view(['GET'])
def outlookCalendarSignIn(request):
    redirect_uri = settings.OUTLOOK_CALENDAR_REDIRECT_URI
    client_id = settings.OUTLOOK_CLIENT_ID
    scope = settings.OUTLOOK_CLIENT_SCOPE
    
    auth_url = (
        f"{settings.OUTLOOK_CALENDAR_AUTHORIZE_API_URI}authorize?"
        f"client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&response_mode=query"
        f"&scope={urllib.parse.quote(scope)}"
        f"&state=12345"
    )
    return redirect(auth_url)

@api_view(['GET'])
def oauth(request: Request):
    code = request.query_params.get('code')
    error = request.query_params.get('error', '')
    
    if error == 'consent_required':
        return api_response(500, "Proper Permissions Are Not Provided To Outlook Calendar", {})
    
    if not code:
        return api_response(500, "Failed To Authenticate.", {})
    
    tenant_id = get_final_tenant_id(request=request)
    
    url = f"{settings.OUTLOOK_CALENDAR_AUTHORIZE_API_URI}token"
    data = {
        "client_id": settings.OUTLOOK_CLIENT_ID,
        "client_secret": settings.OUTLOOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.OUTLOOK_CALENDAR_REDIRECT_URI,
        "scope": settings.OUTLOOK_CLIENT_SCOPE
    }
    
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            res_json = response.json()
            access_token = res_json.get("access_token")
            refresh_token = res_json.get("refresh_token")

            google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
            cs_default_calendar = 'N'
            if google_calendar_setup is None:
                cs_default_calendar = 'Y'
            outlook_calendar_setup = CalendarSetup.objects.create(
                csClientId=get_client_id_by_tenant_id(tenant_id),
                csCalendarType = "MICROSOFT",
                csAccessToken = access_token,
                csRefreshToken = refresh_token if refresh_token else None,
                csDefaultCalendar = cs_default_calendar
            )
            # Fetch Email
            getEmail_internal(outlook_calendar_setup)
            
            return api_response(200, "Authenticate Successfully.", {})
    except Exception as e:
        logger.error(f"Outlook OAuth error: {e}")
        
    return api_response(500, "Failed To Authenticate.", {})

def getEmail_internal(outlook_calendar_data):
    access_token = refresh_outlook_token(outlook_calendar_data)
    if access_token:
        url = "https://graph.microsoft.com/v1.0/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                res_json = response.json()
                email = res_json.get("mail") or res_json.get("userPrincipalName")
                outlook_calendar_data.csEmail = email
                outlook_calendar_data.save()
                return email
        except Exception as e:
            logger.error(f"Outlook GetEmail error: {e}")
    return None

@api_view(['GET'])
def getEmail(request):
    tenant_id = get_final_tenant_id(request=request)
    calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
    if calendar_setup:
        email = getEmail_internal(calendar_setup)
    else:
        email = None
    return api_response(200, "Fetch Email Successfully.", {"email": email})

@api_view(['GET'])
def getEventList(request):
    tenant_id = get_final_tenant_id(request=request)
    calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
    if not calendar_setup:
        return api_response(500, "Constants.ERROR_MSG", {"error": "error"})
    access_token = refresh_outlook_token(calendar_setup)
    if not access_token:
        return api_response(500, "Constants.ERROR_MSG", {"error": "error"})
    
    # Java filter: Start/DateTime ge 'yyyy-MM-ddT00:00:00Z'
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"{settings.OUTLOOK_CALENDAR_API_URI}events?$select=transactionId,subject,bodyPreview,start,end,isAllDay&$count=true&$filter=Start/DateTime ge '{current_date}T00:00:00Z'"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            items = res_json.get("value", [])
            event_list = []
            for item in items:
                event_dto = {
                    "caldSycId": item.get("id"),
                    "calTitle": item.get("subject"),
                    "calDescription": item.get("bodyPreview"),
                    "calStartDateTime": "",
                    "calEndDateTime": "",
                    "calAllDay": "false",
                    "calTimeZone": ""
                }
                
                if item.get("isAllDay"):
                    event_dto["calAllDay"] = "true"
                
                start = item.get("start", {})
                if "dateTime" in start:
                    # Java converts to DB date format: yyyy-MM-dd HH:mm:ss
                    dt_str = start["dateTime"][:19].replace("T", " ")
                    event_dto["calStartDateTime"] = dt_str
                    event_dto["calTimeZone"] = start.get("timeZone", "")
                    
                end = item.get("end", {})
                if "dateTime" in end:
                    dt_str = end["dateTime"][:19].replace("T", " ")
                    event_dto["calEndDateTime"] = dt_str
                    
                event_list.append(event_dto)
            
            return api_response(200, "Fetch Event Successfully.", {"eventList": event_list, "error": ""})
    except Exception as e:
        logger.error(f"Outlook GetEventList error: {e}")
        
    return api_response(500, "Constants.ERROR_MSG", {"error": "error"})

def delete_event_internal(tenant_id, eventId):
    try:
        outlook_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
        if not outlook_calendar_setup:
            return {"error": "Tenant not found"}
        access_token = refresh_outlook_token(outlook_calendar_setup)
        if not access_token:
            return {"error": "Invalid Token"}
        
        url = f"{settings.OUTLOOK_CALENDAR_API_URI}events/{eventId}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.delete(url, headers=headers)
        if response.status_code in [200, 204]:
            return {"error": ""}
        else:
            return {"error": f"Outlook API Error: {response.status_code}"}
    except Exception as e:
        logger.error(f"Outlook delete_event_internal error: {e}")
        return {"error": str(e)}

@api_view(['DELETE'])
def deleteEvent(request, eventId):
    tenant_id = get_final_tenant_id(request=request)
    res = delete_event_internal(tenant_id, eventId)
    if res["error"]:
        return api_response(500, res["error"], {})
    return api_response(200, "Event Deleted Successfully.", {})

def get_user_calendar_timezone(access_token):
    url = "https://graph.microsoft.com/v1.0/me/mailboxsettings/timeZone"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("value", "UTC")
    except Exception:
        pass
    return "UTC"


def save_event_internal(tenant_id, data):
    try:
        calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
    except CalendarSetup.DoesNotExist:
        return {"error": "Tenant not found", "caldSycId": ""}
    caldSycId = data.get('caldSycId', data.get('ID', ''))
    calTitle = data.get('calTitle', data.get('title', ''))
    calDescription = data.get('calDescription', data.get('description', ''))
    calStartDateTime = data.get('calStartDateTime', data.get('start', ''))
    calEndDateTime = data.get('calEndDateTime', data.get('end', ''))
    calAllDay = data.get('calAllDay', data.get('allDay', 'false'))
    calTimeZone = data.get('calTimeZone', '')
    calAttendees = data.get('calAttendees', [])

    if not calStartDateTime or not calEndDateTime:
        return {"error": "Start and End dates are required", "caldSycId": ""}
    if calendar_setup:
        access_token = refresh_outlook_token(calendar_setup)
    else:
        access_token = None
    if not access_token:
        return {"error": "Invalid Token", "caldSycId": ""}
    
    user_tz = get_user_calendar_timezone(access_token)
    if calTimeZone and calTimeZone != "":
        user_tz = calTimeZone
        
    is_all_day_bool = str(calAllDay).lower() == "true"
    if is_all_day_bool:
        try:
            # Replicate Java's midnight normalization (Java lines 280-290)
            # Java: startDate = new SimpleDateFormat("MM/dd/yyyy HH:mm:ss").parse(startDateTime);
            # midnightFormat = new SimpleDateFormat("MM/dd/yyyy 00:00:00");
            start_date_obj = None
            end_date_obj = None
            for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    if not start_date_obj: 
                        start_date_obj = datetime.strptime(calStartDateTime, fmt)
                except ValueError:
                    pass
                try:
                    if not end_date_obj: 
                        end_date_obj = datetime.strptime(calEndDateTime, fmt)
                except ValueError:
                    pass
                if start_date_obj and end_date_obj:
                    break
            
            if start_date_obj:
                start_date_obj = start_date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
                calStartDateTime = start_date_obj.strftime("%m/%d/%Y 00:00:00")
                
                if end_date_obj:
                    end_date_obj = end_date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
                    if end_date_obj <= start_date_obj:
                        end_date_obj = start_date_obj + timedelta(days=1)
                    calEndDateTime = end_date_obj.strftime("%m/%d/%Y 00:00:00")
            
            logger.error(f"calEndDateTime : {calEndDateTime} | calStartDateTime : {calStartDateTime}")
        except Exception as e:
            logger.error(f"SaveOutlookCalendarEvent Date Parsing Error : {e}")
            
    # Java converts nl to br
    calDescription_html = calDescription.replace("\n", "<br />") if calDescription else ""
    
    event_body = {
        "subject": calTitle,
        "body": {
            "contentType": "HTML",
            "content": calDescription_html
        }
    }
    
    if calAttendees:
        if isinstance(calAttendees, str):
            calAttendees = [e.strip() for e in calAttendees.split(",") if e.strip()]
        event_body["attendees"] = [
            {
                "emailAddress": {"address": email, "name": email},
                "type": "required"
            } for email in calAttendees
        ]
        
    def format_dt(dt_str):
        """
        Replicates CommonFunction.convertDateTimeToTimeZone:
        Parses MM/dd/yyyy HH:mm:ss and formats as yyyy-MM-dd'T'HH:mm:ss
        """
        try:
            # Handle potential ISO format from prior processing
            if "T" in dt_str:
                dt_str = dt_str.replace("T", " ")
            
            dt = None
            # CommonFunction.java: new SimpleDateFormat("MM/dd/yyyy HH:mm:ss")
            if "/" in dt_str:
                dt = datetime.strptime(dt_str, "%m/%d/%Y %H:%M:%S")
            else:
                # Fallback for internal robustness
                for format_date in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(dt_str, format_date)
                        break
                    except ValueError:
                        continue
            
            if not dt:
                raise ValueError(f"Unable to parse date: {dt_str}")
            
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception as exp:
            logger.error(f"Error formatting Outlook date {dt_str}: {exp}")
            return dt_str.replace(" ", "T")

    event_body["start"] = {"dateTime": format_dt(calStartDateTime), "timeZone": user_tz}
    event_body["end"] = {"dateTime": format_dt(calEndDateTime), "timeZone": user_tz}
    event_body["isAllDay"] = is_all_day_bool

    url = settings.OUTLOOK_CALENDAR_API_URI + "events"
    method = "POST"
    if caldSycId:
        url += "/" + caldSycId
        method = "PATCH"
        
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=event_body)
        else:
            response = requests.patch(url, headers=headers, json=event_body)
            
        if response.status_code in [200, 201]:
            res_json = response.json()
            return {"caldSycId": res_json.get("id"), "error": ""}
        else:
            logger.error(f"Outlook API Error: {response.status_code} - {response.text}")
            return {"error": f"Outlook API Error: {response.status_code}", "caldSycId": ""}
    except Exception as e:
        logger.error(f"Outlook SaveEvent connection error: {e}")
        return {"error": str(e), "caldSycId": ""}

@api_view(['POST'])
def saveEvent(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    res = save_event_internal(tenant_id, request.data)
    if res["error"]:
        return api_response(500, res["error"], {"error": "error"})
    
    msg = "Update Event Successfully" if request.data.get('caldSycId') else "Add Event Successfully"
    return api_response(200, msg, res)


@api_view(['GET'])
def revoke(request):
    tenant_id = get_final_tenant_id(request=request)
    calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
    # In Java, it refreshes then clears
    if calendar_setup:
        refresh_outlook_token(calendar_setup)
        calendar_setup.delete()
            
    return api_response(200, "Disconnected Successfully.", {"error": ""})
