from rest_framework.decorators import api_view
from django.shortcuts import redirect
from django.conf import settings
from rest_framework.request import Request
from common_app.models import CalendarSetup
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
import requests
import json
import logging
from datetime import datetime, timezone
import urllib.parse

logger = logging.getLogger(__name__)

def refresh_google_token(google_calendar_data):
    refresh_token = google_calendar_data.csRefreshToken
    if not refresh_token:
        return None
    
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            res_json = response.json()
            access_token = res_json.get("access_token")
            google_calendar_data.csAccessToken = access_token
            google_calendar_data.save()
            return access_token
    except Exception as e:
        logger.error(f"Error refreshing Google token: {e}")
    
    return None

@api_view(['GET'])
def googleCalendarSignIn(request):
    redirect_uri = settings.GOOGLE_CALENDAR_REDIRECT_URI
    client_id = settings.GOOGLE_CLIENT_ID
    
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        "scope=https://www.googleapis.com/auth/calendar+https://www.googleapis.com/auth/calendar.events"
        "&access_type=offline"
        "&include_granted_scopes=true"
        "&response_type=code"
        "&redirect_uri=" + urllib.parse.quote(redirect_uri) +
        "&client_id=" + client_id +
        "&prompt=consent"
    )
    return redirect(auth_url)

@api_view(['GET'])
def oauth(request: Request):
    code = request.query_params.get('code')
    error = request.query_params.get('error', '')
    
    if error == 'access_denied':
        return api_response(500, "Proper permissions are not provided to Google Calendar", {})
    
    if not code:
        return api_response(500, "Failed To Authenticate.", {})
    
    tenant_id = get_final_tenant_id(request=request)
    
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI
    }
    
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            res_json = response.json()
            access_token = res_json.get("access_token")
            refresh_token = res_json.get("refresh_token")
            
            if refresh_token:
                outlook_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
                cs_default_calendar = 'N'
                if outlook_calendar_setup is None:
                    cs_default_calendar = 'Y'
                google_calendar_setup = CalendarSetup.objects.create(
                    csClientId=get_client_id_by_tenant_id(tenant_id),
                    csCalendarType="GOOGLE",
                    csAccessToken=access_token,
                    csRefreshToken=refresh_token if refresh_token else None,
                    csDefaultCalendar=cs_default_calendar
                )
                # Fetch Email
                getEmail_internal(google_calendar_setup)
                
                return api_response(200, "Authenticate Successfully.", {})
            else:
                return api_response(500, "Already Exists Your Gmail Account In Our Website.", {})
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        
    return api_response(500, "Failed To Authenticate.", {})

def getEmail_internal(google_calendar_data):
    access_token = refresh_google_token(google_calendar_data)
    if access_token:
        url = "https://www.googleapis.com/calendar/v3/calendars/primary"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                res_json = response.json()
                email = res_json.get("id")
                google_calendar_data.csEmail = email
                google_calendar_data.save()
                return email
        except Exception as e:
            logger.error(f"GetEmail error: {e}")
    return None

@api_view(['GET'])
def getEmail(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
    email = None
    if google_calendar_setup:
        email = getEmail_internal(google_calendar_setup)
    return api_response(200, "Fetch Email Successfully.", {"email": email})

@api_view(['GET'])
def getEvent(request: Request, eventId):
    tenant_id = get_final_tenant_id(request=request)
    google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
    access_token = None
    if google_calendar_setup:
        access_token = refresh_google_token(google_calendar_setup)
    if not access_token:
        return api_response(500, "Invalid Access Token", {"error": "error"})
    
    url = f"{settings.GOOGLE_CALENDAR_API_URI}events/{eventId}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            event_dto = {
                "caldSycId": res_json.get("id"),
                "calTitle": res_json.get("summary"),
                "calDescription": res_json.get("description", ""),
                "calStartDateTime": "",
                "calEndDateTime": "",
                "calAllDay": "false",
                "calTimeZone": ""
            }
            
            start = res_json.get("start", {})
            if "dateTime" in start:
                event_dto["calStartDateTime"] = start["dateTime"]
                event_dto["calAllDay"] = "false"
                if "timeZone" in start:
                    event_dto["calTimeZone"] = start["timeZone"]
            elif "date" in start:
                event_dto["calStartDateTime"] = start["date"]
                event_dto["calAllDay"] = "true"
                
            end = res_json.get("end", {})
            if "dateTime" in end:
                event_dto["calEndDateTime"] = end["dateTime"]
            elif "date" in end:
                event_dto["calEndDateTime"] = end["date"]
                
            return api_response(200, "Fetch Data Successfully.", {"event": event_dto, "error": ""})
    except Exception as e:
        logger.error(f"GetEvent error: {e}")
        
    return api_response(500, "Constants.ERROR_MSG", {"error": "error"})

def delete_event_internal(tenant_id, eventId):
    try:
        google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
        access_token = None
        if google_calendar_setup:
            access_token = refresh_google_token(google_calendar_setup)
        if not access_token:
            return {"error": "Invalid Token"}
        
        url = f"{settings.GOOGLE_CALENDAR_API_URI}events/{eventId}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.delete(url, headers=headers)
        if response.status_code in [200, 204]:
            return {"error": ""}
        else:
            return {"error": f"Google API Error: {response.status_code}"}
    except Exception as e:
        logger.error(f"DeleteEvent internal error: {e}")
        return {"error": str(e)}

@api_view(['DELETE'])
def deleteEvent(request: Request, eventId):
    tenant_id = get_final_tenant_id(request=request)
    res = delete_event_internal(tenant_id, eventId)
    if res["error"]:
        return api_response(500, res["error"], {})
    return api_response(200, "Event Deleted Successfully.", {})

@api_view(['GET'])
def getEventList(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
    
    access_token = None
    if google_calendar_setup:
        access_token = refresh_google_token(google_calendar_setup)
    if not access_token:
        return api_response(500, "Constants.ERROR_MSG", {"error": "error"})
    
    event_list = []
    # Java calls with timeMin=currentDateT00:00:00Z
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"{settings.GOOGLE_CALENDAR_API_URI}events?maxResults=100&singleEvents=true&timeMin={current_date}T00:00:00Z"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            items = res_json.get("items", [])
            for item in items:
                if "summary" in item:
                    event_dto = {
                        "caldSycId": item.get("id"),
                        "calTitle": item.get("summary"),
                        "calDescription": item.get("description", ""),
                        "calStartDateTime": "",
                        "calEndDateTime": "",
                        "calAllDay": "false",
                        "calTimeZone": ""
                    }
                    
                    start = item.get("start", {})
                    if "dateTime" in start:
                        # Java converts timezone to DB date (yyyy-MM-dd HH:mm:ss)
                        dt_str = start["dateTime"][:19].replace("T", " ")
                        event_dto["calStartDateTime"] = dt_str
                        event_dto["calAllDay"] = "false"
                        if "timeZone" in start:
                            event_dto["calTimeZone"] = start["timeZone"]
                    elif "date" in start:
                        event_dto["calStartDateTime"] = start["date"]
                        event_dto["calAllDay"] = "true"
                        
                    end = item.get("end", {})
                    if "dateTime" in end:
                        dt_str = end["dateTime"][:19].replace("T", " ")
                        event_dto["calEndDateTime"] = dt_str
                        if "timeZone" in end:
                            event_dto["calTimeZone"] = end["timeZone"]
                    elif "date" in end:
                        event_dto["calEndDateTime"] = end["date"]
                        
                    event_list.append(event_dto)
            
            return api_response(200, "Fetch Event Successfully.", {"eventList": event_list, "error": ""})
    except Exception as e:
        logger.error(f"GetEventList error: {e}")
        
    return api_response(500, "Constants.ERROR_MSG", {"error": "error"})

def get_user_calendar_timezone(access_token):
    url = f"{settings.GOOGLE_CALENDAR_API_URI.replace('/primary/', '')}/settings/timezone"
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
        calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
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
    access_token = None
    if calendar_setup:
        access_token = refresh_google_token(calendar_setup)
    if not access_token:
        return {"error": "Invalid Token", "caldSycId": ""}
    
    user_tz = get_user_calendar_timezone(access_token)
    if calTimeZone:
        user_tz = calTimeZone
        
    if calDescription:
        calDescription = calDescription.replace("\r\n", "<br>").replace("\n", "<br>")
        
    event_body = {
        "summary": calTitle,
        "description": calDescription,
    }
    
    if calAttendees:
        # 1. Handle JSON string case
        if isinstance(calAttendees, str) and calAttendees.strip().startswith('{'):
            try:
                attendee_data = json.loads(calAttendees)
                # Extract the list from the "attendees" key
                calAttendees = attendee_data.get('attendees', [])
            except json.JSONDecodeError:
                # Fallback to standard string split if JSON parsing fails
                calAttendees = [e.strip() for e in calAttendees.split(",") if e.strip()]
        
        # 2. Handle comma-separated string case
        elif isinstance(calAttendees, str):
            calAttendees = [e.strip() for e in calAttendees.split(",") if e.strip()]

        # 3. Build the event_body
        if calAttendees:
            event_body["sendUpdates"] = "all"
            event_body["attendees"] = [{"email": email} for email in calAttendees if "@" in email]
        
    if str(calAllDay).lower() == "false":
        try:
            if "/" in calStartDateTime:
                dt_start = datetime.strptime(calStartDateTime, "%m/%d/%Y %H:%M:%S")
                dt_end = datetime.strptime(calEndDateTime, "%m/%d/%Y %H:%M:%S")
            else:
                dt_start = datetime.strptime(calStartDateTime, "%Y-%m-%d %H:%M:%S")
                dt_end = datetime.strptime(calEndDateTime, "%Y-%m-%d %H:%M:%S")
            
            event_body["start"] = {"dateTime": dt_start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": user_tz}
            event_body["end"] = {"dateTime": dt_end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": user_tz}
        except Exception as e:
             logger.error(f"SaveEvent Date Parsing Error: {e}")
             return {"error": f"Date Parsing Error: {e}", "caldSycId": ""}
    else:
        try:
            if "/" in calStartDateTime:
                d_start = datetime.strptime(calStartDateTime.split(" ")[0], "%m/%d/%Y").strftime("%Y-%m-%d")
                d_end = datetime.strptime(calEndDateTime.split(" ")[0], "%m/%d/%Y").strftime("%Y-%m-%d")
            else:
                d_start = calStartDateTime.split(" ")[0]
                d_end = calEndDateTime.split(" ")[0]
                
            event_body["start"] = {"date": d_start}
            event_body["end"] = {"date": d_end}
        except Exception as e:
            logger.error(f"SaveEvent AllDay Date Parsing Error: {e}")
            return {"error": f"AllDay Date Parsing Error: {e}", "caldSycId": ""}

    url = f"{settings.GOOGLE_CALENDAR_API_URI}events"
    if caldSycId:
        url += f"/{caldSycId}"
        method = "PUT"
    else:
        method = "POST"
        
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        if method == "POST":
            response = requests.post(url, headers=headers, json=event_body)
        else:
            response = requests.put(url, headers=headers, json=event_body)
            
        if response.status_code in [200, 201]:
            res_json = response.json()
            return {"caldSycId": res_json.get("id"), "error": ""}
        else:
            logger.error(f"Google API Error: {response.status_code} - {response.text}")
            return {"error": f"Google API Error: {response.status_code}", "caldSycId": ""}
    except Exception as e:
        logger.error(f"SaveEvent connection error: {e}")
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
def revoke(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
    
    access_token = calendar_setup.csAccessToken if calendar_setup else None
    if calendar_setup and access_token:
        # Refresh to get latest token
        access_token = refresh_google_token(calendar_setup)
        calendar_setup.delete()
    
    if access_token:
        url = f"https://oauth2.googleapis.com/revoke?token={access_token}"
        try:
            requests.post(url, headers={"Content-Type": "application/x-www-form-urlencoded"})
        except Exception:
            pass
            
    return api_response(200, "Disconnected Successfully.", {"error": ""})

@api_view(['GET'])
def getUserTimezone(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()

    if calendar_setup:
        access_token = refresh_google_token(calendar_setup)
    else:
        access_token = None

    if not access_token:
        return api_response(500, "Constants.ERROR_MSG", {})
    
    tz = get_user_calendar_timezone(access_token)
    return api_response(200, "Fetch User Timezone Successfully.", {"timezone": tz})
