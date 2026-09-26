from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from django.db.models import Q
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone
import pytz
import logging
import traceback
import json
import requests
import re
from common_app.models import (Calendar, CalendarDetails, TimeZoneList, CalendarNotification, CalendarNotificationReminder, CalendarSetup, Clients, CalendarReminderSmsDetails)
from common_app.services import CommonServices, MailRequestDTO
from api_app.views import google_calendar_views, outlook_calendar_views
from zoneinfo import ZoneInfo
import calendar as py_cal
from common_app.utils import get_final_tenant_id, api_response, convert_event_timezone_to_user, display_date_time, get_user_db_timezone, date_object_to_display_date, convert_time_zone_to_db_date, change_timezone_name, get_client_id_by_tenant_id, db_date_to_display_date_time, get_tenants, get_split_date, get_weekday_date, get_last_weekday_date, get_client_timezone
from mycrm_app.serializers import TimeZoneListSerializer, SaveTenantSmsNotificationDtoSerializer, DeleteEventDtoSerializer, CalendarDtoSerializer, SaveTenantTimeZoneDtoSerializer, SaveTenantWebConferenceDtoSerializer, SaveTenantEmailNotificationDtoSerializer

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _tenant_notification(cal_id, email_notification):
    try:
        # Delete existing notifications for this event
        CalendarNotification.objects.filter(calnCalId=cal_id).delete()
    except Exception:
        pass

    try:
        if email_notification:
            minutes_list = str(email_notification).split(",")
            for minutes in minutes_list:
                if minutes.strip():
                    notif = CalendarNotification(
                        calnCalId=cal_id,
                        calnMinutes=int(minutes.strip()),
                        calnCreatedDateTime=timezone.now()
                    )
                    notif.save()
    except Exception as e:
        logger.error(f"Error in _tenant_notification: {e}")

def _tenant_notification_reminder(calendar):
    try:
        if calendar.calReminderType:
            try:
                CalendarNotificationReminder.objects.filter(calnCalId=calendar.calId).delete()
            except Exception:
                pass

            reminder_types = str(calendar.calReminderType).split(",")
            for rtype in reminder_types:
                rtype = rtype.strip()
                if rtype:
                    reminder = CalendarNotificationReminder(
                        calnCalId=calendar.calId,
                        calnReminderType=rtype,
                        calnCreatedDateTime=timezone.now(),
                        calnSendDateTime=calendar.calStartDateTime
                    )
                    reminder.save()
    except Exception as e:
        logger.error(f"Error in _tenant_notification_reminder: {e}")


def _day_name_to_int(name):
    days = {"monday":1, "tuesday":2, "wednesday":3, "thursday":4, "friday":5, "saturday":6, "sunday":7}
    return days.get(name.lower(), 1)

def _convert_date_time_to_db(date_str):
    """
    Normalizes MM/dd/yyyy HH:mm:ss or yyyy-MM-dd HH:mm:ss to yyyy-MM-dd HH:mm:ss.
    Mirrors CommonFunction.dbDateTime in Java.
    """
    try:
        if not date_str:
            return None
        if "-" in date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"DEBUG: _convert_date_time_to_db error for {date_str}: {e}")
        return date_str

def _convert_event_time_zone_to_user_db(date_str, from_tz, to_tz):
    """
    Converts a date string between timezones.
    Expects date_str in yyyy-MM-dd HH:mm:ss format.
    Mirrors CommonFunction.convertEventTimeZoneToUserDB in Java.
    """
    try:
        if not date_str:
            return None
        if not from_tz or from_tz == to_tz or not to_tz:
            return date_str
        
        # Mapping for common inconsistent names
        tz_map = {"Asia/Calcutta": "Asia/Kolkata", "Calcutta": "Asia/Kolkata", "Kolkata": "Asia/Kolkata"}
        f_tz = tz_map.get(from_tz, from_tz)
        t_tz = tz_map.get(to_tz, to_tz)

        # Java uses LocalDateTime.parse(date, "yyyy-MM-dd HH:mm:ss")
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        
        # Shift instant between zones
        dt_localized = dt.replace(tzinfo=ZoneInfo(str(f_tz)))
        dt_converted = dt_localized.astimezone(ZoneInfo(str(t_tz)))
        
        return dt_converted.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"DEBUG: _convert_event_time_zone_to_user_db error for {date_str}: {e}")
        logger.error(f"Error in _convert_event_time_zone_to_user_db: {e}")
        return date_str

def _convert_event_time_zone_to_user_db_aware(date_str, from_tz, to_tz):
    """
    Robustly parses date strings (handling both timestamp and date-only formats)
    and converts them to aware datetime objects in the target timezone.
    """
    try:
        if not date_str:
            return None
        
        # Mapping for common inconsistent names
        tz_map = {"Asia/Calcutta": "Asia/Kolkata", "Calcutta": "Asia/Kolkata", "Kolkata": "Asia/Kolkata"}
        f_tz = tz_map.get(from_tz, from_tz)
        t_tz = tz_map.get(to_tz, to_tz)

        dt = None
        # Try multiple formats common in the application
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(date_str, pattern)
                break
            except ValueError:
                continue
        
        if not dt:
            raise ValueError(f"Time data '{date_str}' does not match any supported format")

        dt_localized = dt.replace(tzinfo=ZoneInfo(f_tz or "UTC"))
        dt_converted = dt_localized.astimezone(ZoneInfo(t_tz or "UTC"))
        
        return dt_converted
    except Exception as e:
        logger.error(f"Error in _convert_event_time_zone_to_user_db_aware: {e}")
        return None

def _convert_date(date_str):
    """
    Parses yyyy-MM-dd HH:mm:ss string into a datetime object.
    Mirrors CommonFunction.convertDate in Java.
    """
    try:
        if not date_str:
            return None
        # This function strictly expects yyyy-MM-dd HH:mm:ss due to normalization steps
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, dt_timezone.utc)
        return dt
    except Exception as e:
        print(f"DEBUG: _convert_date error for {date_str}: {e}")
        return None

def _clone_calendar_event(source):
    content = {field.name: getattr(source, field.name) for field in Calendar._meta.fields if field.name != 'calId'}
    return Calendar(**content)

def _repeat_every_type_year_fun(tenant_id, cal_id, email_notification, flag):
    """
    Creates occurrences for yearly recurrence.
    """
    try:
        parent = Calendar.objects.get(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id))
        start_date_aware = parent.calRepeatDate or parent.calStartDateTime
        start_date = start_date_aware.astimezone(pytz.UTC).replace(tzinfo=None)
        
        end_date_aware = parent.calRepeatEndDate
        end_date = end_date_aware.astimezone(pytz.UTC).replace(tzinfo=None)
        
        event_end = parent.calEndDateTime
        
        split_date = {}
        if parent.calRepeatSelectedOption in [2, 3]:
            split_date = get_split_date(start_date.strftime("%Y-%m-%d"))
            
        current_start = start_date
        day_no = current_start.day
        current_start = current_start.replace(year=current_start.year + 1)
        
        while current_start <= end_date:
            if parent.calRepeatSelectedOption == 1:
                # Handle leap year/day overflow
                target_year = current_start.year
                target_month = current_start.month
                last_day = py_cal.monthrange(target_year, target_month)[1]
                current_start = current_start.replace(day=min(day_no, last_day))
                target_date_str = current_start.strftime("%Y-%m-%d")
            elif parent.calRepeatSelectedOption == 2:
                target_date_str = get_weekday_date(current_start.year, split_date.get("month"), split_date.get("day"), split_date.get("week"))
            elif parent.calRepeatSelectedOption == 3:
                target_date_str = get_last_weekday_date(current_start.year, split_date.get("month"), split_date.get("day"))
            else:
                target_date_str = current_start.strftime("%Y-%m-%d")

            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            if target_date <= end_date.date():
                new_cal = _clone_calendar_event(parent)
                new_cal.calId = None
                new_cal.calParentId = parent.calId
                start_time = parent.calStartDateTime.time()
                new_cal.calStartDateTime = timezone.make_aware(datetime.combine(target_date, start_time))
                
                if event_end:
                    # Align with Java: Combine target date with original end time
                    new_cal.calEndDateTime = timezone.make_aware(datetime.combine(target_date, event_end.time()))
                
                new_cal.save()
                if flag == "event":
                    _tenant_notification(new_cal.calId, email_notification)
                else:
                    _tenant_notification_reminder(new_cal)
            
            current_start = current_start.replace(year=current_start.year + 1)
            
    except Exception as e:
        logger.error(f"Error in _repeat_every_type_year_fun: {e}")

def _repeat_every_type_month_fun(tenant_id, cal_id, email_notification, flag):
    """
    Creates occurrences for monthly recurrence.
    """
    try:
        parent = Calendar.objects.get(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id))
        repeat_every = parent.calRepeatEvery or 1
        start_date_aware = parent.calRepeatDate or parent.calStartDateTime
        start_date = start_date_aware.astimezone(pytz.UTC).replace(tzinfo=None)
        
        end_date_aware = parent.calRepeatEndDate
        end_date = end_date_aware.astimezone(pytz.UTC).replace(tzinfo=None)
        
        event_end = parent.calEndDateTime
        
        split_date = {}
        if parent.calRepeatSelectedOption in [2, 3]:
            split_date = get_split_date(start_date.strftime("%Y-%m-%d"))
            
        current_start = start_date
        # Increment month manually to match repeat_every
        def add_months(sourcedate, months):
            month = sourcedate.month - 1 + months
            year = sourcedate.year + month // 12
            month = month % 12 + 1
            day = min(sourcedate.day, py_cal.monthrange(year, month)[1])
            return datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)

        current_start = add_months(current_start, repeat_every)
        
        while current_start <= end_date:
            if parent.calRepeatSelectedOption == 1:
                target_date_str = current_start.strftime("%Y-%m-%d")
            elif parent.calRepeatSelectedOption == 2:
                target_date_str = get_weekday_date(current_start.year, current_start.month, split_date.get("day"), split_date.get("week"))
            elif parent.calRepeatSelectedOption == 3:
                target_date_str = get_last_weekday_date(current_start.year, current_start.month, split_date.get("day"))
            else:
                target_date_str = current_start.strftime("%Y-%m-%d")

            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            if target_date <= end_date.date():
                new_cal = _clone_calendar_event(parent)
                new_cal.calId = None
                new_cal.calParentId = parent.calId
                start_time = parent.calStartDateTime.time()
                new_cal.calStartDateTime = timezone.make_aware(datetime.combine(target_date, start_time))
                
                if event_end:
                    # Align with Java: Combine target date with original end time
                    new_cal.calEndDateTime = timezone.make_aware(datetime.combine(target_date, event_end.time()))
                
                new_cal.save()
                if flag == "event":
                    _tenant_notification(new_cal.calId, email_notification)
                else:
                    _tenant_notification_reminder(new_cal)
            
            current_start = add_months(current_start, repeat_every)
            
    except Exception as e:
        logger.error(f"Error in _repeat_every_type_month_fun: {e}")

def _repeat_every_type_day_fun(tenant_id, cal_id, email_notification, flag):
    """
    Creates occurrences for daily recurrence.
    """
    try:
        parent = Calendar.objects.get(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id))
        repeat_every = parent.calRepeatEvery or 1
        start_date = parent.calRepeatDate or parent.calStartDateTime
        end_date = parent.calRepeatEndDate
        event_end = parent.calEndDateTime
        
        current_date = start_date + timedelta(days=repeat_every)
        while current_date <= end_date:
            new_cal = _clone_calendar_event(parent)
            new_cal.calId = None
            new_cal.calParentId = parent.calId
            new_cal.calStartDateTime = current_date
            
            if event_end:
                # Align with Java: Combine current date with original end time
                new_cal.calEndDateTime = timezone.make_aware(datetime.combine(current_date.date(), event_end.time()))
                
            new_cal.save()
            if flag == "event":
                _tenant_notification(new_cal.calId, email_notification)
            else:
                _tenant_notification_reminder(new_cal)
                
            current_date += timedelta(days=repeat_every)
            
    except Exception as e:
        logger.error(f"Error in _repeat_every_type_day_fun: {e}")

def _repeat_every_type_week_fun(tenant_id, cal_id, email_notification, flag):
    """
    Creates occurrences for weekly recurrence.
    Fixed to correctly include days in the first week and maintain chronological order.
    """
    try:
        parent = Calendar.objects.get(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id))
        repeat_every = parent.calRepeatEvery or 1
        week_day_name_list = [d.strip() for d in (parent.calRepeatDayName or "").split(",") if d.strip()]
        
        # Convert weekday names to indices for easy matching (1=Mon, 7=Sun)
        target_weekdays = [_day_name_to_int(name) for name in week_day_name_list]
        
        start_date_time = (parent.calRepeatDate or parent.calStartDateTime)
        end_date_time = parent.calRepeatEndDate
        
        if not start_date_time or not end_date_time:
            return

        # Use naive dates for calculation to match common calendar logic
        # We process week by week
        current_week_base = start_date_time.date()
        
        # Determine the start of the week (Sunday) for the beginning of the recurrence
        days_to_sunday = current_week_base.isoweekday() % 7
        week_start = current_week_base - timedelta(days=days_to_sunday)
        
        # Loop while the week start hasn't exceeded the end date
        while week_start <= end_date_time.date():
            for offset in range(7):
                target_date = week_start + timedelta(days=offset)
                if target_date.isoweekday() in target_weekdays:
                    if target_date < start_date_time.date():
                        continue
                        
                    if target_date == start_date_time.date():
                        continue
                        
                    if target_date > end_date_time.date():
                        continue
                    
                    new_cal = _clone_calendar_event(parent)
                    new_cal.calId = None
                    new_cal.calParentId = parent.calId
                    
                    # Combine target date with original time parts
                    if parent.calStartDateTime:
                        new_cal.calStartDateTime = timezone.make_aware(
                            datetime.combine(target_date, parent.calStartDateTime.time()),
                            parent.calStartDateTime.tzinfo
                        )
                    
                    if parent.calEndDateTime:
                        new_cal.calEndDateTime = timezone.make_aware(
                            datetime.combine(target_date, parent.calEndDateTime.time()),
                            parent.calEndDateTime.tzinfo
                        )
                    
                    new_cal.save()
                    
                    if flag == "event":
                        _tenant_notification(new_cal.calId, email_notification)
                    else:
                        _tenant_notification_reminder(new_cal)
            
            # Move to the next block of weeks
            week_start += timedelta(weeks=repeat_every)
            
    except Exception as e:
        logger.error(f"Error in _repeat_every_type_week_fun: {e}")


def _add_edit_event_google_and_outlook(tenant_id, calendar_list, clad_type_list, attendees_list, event_timezone):
    """
    Syncs a list of calendar events to Google and Outlook.
    Handles creation, updates, and deletion of syncs based on clad_type_list.
    Mirrors transition logic in Java lines 645-731 and 1018-1064.
    """
    for cal in calendar_list:
        # Convert DB time (usually UTC) to the event's local timezone for external sync
        # This addresses the shift issue where UTC digits were sent with a local timezone name
        target_tz_str = cal.calTimeZone or event_timezone
        start_dt = cal.calStartDateTime
        end_dt = cal.calEndDateTime
        
        if target_tz_str:
            try:
                tz_obj = pytz.timezone(target_tz_str)
                if start_dt:
                    if not timezone.is_aware(start_dt):
                        start_dt = timezone.make_aware(start_dt, pytz.UTC)
                    start_dt = start_dt.astimezone(tz_obj)
                if end_dt:
                    if not timezone.is_aware(end_dt):
                        end_dt = timezone.make_aware(end_dt, pytz.UTC)
                    end_dt = end_dt.astimezone(tz_obj)
            except Exception as e:
                logger.error(f"Timezone conversion error in sync helper: {e}")
        
        logger.info(f"Syncing event {cal.calId} to {clad_type_list}. Start(Local): {start_dt}, TZ: {target_tz_str}")

        data = {
            "calTitle": cal.calTitle,
            "calDescription": cal.calDescription,
            "calStartDateTime": start_dt.strftime("%Y-%m-%d %H:%M:%S") if start_dt else "",
            "calEndDateTime": end_dt.strftime("%Y-%m-%d %H:%M:%S") if end_dt else "",
            "calAllDay": cal.calAllDay,
            "calTimeZone": target_tz_str,
            "calAttendees": attendees_list
        }
        
        # Current syncs for this specific event
        cal_details = CalendarDetails.objects.filter(caldCalId=cal.calId)
        synced_types = {d.caldType: d for d in cal_details}
        
        # Working copy of target sync types
        active_sync_types = list(clad_type_list)
        
        # 1. Update existing syncs or Delete removed syncs (Java lines 647-697)
        for ct, detail in synced_types.items():
            if ct in active_sync_types:
                # Update existing sync
                inner_data = data.copy()
                inner_data["caldSycId"] = detail.caldSycId
                
                res = {}
                try:
                    if ct == "google":
                        res = google_calendar_views.save_event_internal(tenant_id, inner_data)
                    elif ct == "outlook":
                        res = outlook_calendar_views.save_event_internal(tenant_id, inner_data)
                    
                    if res.get("caldSycId"):
                        detail.caldSycId = res["caldSycId"]
                        detail.save()
                except Exception as e:
                    logger.error(f"Error updating external sync for {ct}: {e}")
                
                # Remove from active_sync_types so it's not created as new
                active_sync_types.remove(ct)
            else:
                # Cleanup: type no longer requested for this event (Java lines 673-695)
                try:
                    if ct == "google" and detail.caldSycId:
                        google_calendar_views.delete_event_internal(tenant_id, detail.caldSycId)
                    elif ct == "outlook" and detail.caldSycId:
                        outlook_calendar_views.delete_event_internal(tenant_id, detail.caldSycId)
                except Exception as e:
                    logger.error(f"Error deleting external sync for {ct}: {e}")
                
                detail.delete()
        
        # 2. Add new syncs (Java lines 700-731)
        for ct in active_sync_types:
            inner_data = data.copy()
            res = {}
            try:
                if ct == "google":
                    res = google_calendar_views.save_event_internal(tenant_id, inner_data)
                elif ct == "outlook":
                    res = outlook_calendar_views.save_event_internal(tenant_id, inner_data)
                
                if res.get("caldSycId"):
                    CalendarDetails.objects.create(
                        caldCalId=cal.calId,
                        caldType=ct,
                        caldSycId=res["caldSycId"]
                    )
            except Exception as e:
                traceback.print_exc()
                logger.error(f"Error creating external sync for {ct}: {e}")
                logger.error(f"Error in _add_edit_event_google_and_outlook: {e}")

# --- API Endpoints ---

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_time_zone_list(request):
    time_zones = TimeZoneList.objects.all().order_by('tmzId')
    serializer = TimeZoneListSerializer(time_zones, many=True)
    return api_response(200, "Fetch Time Zone Successfully.", {"timeZoneList":serializer.data})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_calendar_authentication(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        calendar_setups = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id))
        google_calendar = False
        outlook_calendar = False
        google_calendar_email = ""
        outlook_calendar_email = ""
        for calendar_setup in calendar_setups:
            if calendar_setup.csCalendarType == "GOOGLE":
                if calendar_setup.csAccessToken and calendar_setup.csAccessToken.strip():
                    google_calendar = True
                if calendar_setup.csEmail and calendar_setup.csEmail.strip():
                    google_calendar_email = calendar_setup.csEmail

            if calendar_setup.csCalendarType == "MICROSOFT":
                if calendar_setup.csAccessToken and calendar_setup.csAccessToken.strip():
                    outlook_calendar = True
                if calendar_setup.csEmail and calendar_setup.csEmail.strip():
                    outlook_calendar_email = calendar_setup.csEmail

        data = {
            "googleCalendar": google_calendar,
            "outlookCalendar": outlook_calendar,
            "googleCalendarEmail": google_calendar_email,
            "outlookCalendarEmail": outlook_calendar_email
        }
        return api_response(200, "Fetch Calendar Authentication Successfully.", data)
    except CalendarSetup.DoesNotExist:
        return api_response(404, "Tenant not found.")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_client_time_zone(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = SaveTenantTimeZoneDtoSerializer(data=request.data)
    if serializer.is_valid():
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
            client.cliTimeZone = serializer.validated_data['timeZone']
            client.save()
            return api_response(200, "Save Time Zone Successfully.")
        except Clients.DoesNotExist:
            return api_response(404, "Client not found.")
    return api_response(400, "Invalid data.", serializer.errors)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_web_conference(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = SaveTenantWebConferenceDtoSerializer(data=request.data)
    if serializer.is_valid():
        try:
            CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id)).update(csWebConferenceUrl=serializer.validated_data['webConference'])
            return api_response(200, "Save Web Conference Successfully.")
        except CalendarSetup.DoesNotExist:
            return api_response(404, "Tenant not found.")
    return api_response(400, "Invalid data.", serializer.errors)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_email_notification(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = SaveTenantEmailNotificationDtoSerializer(data=request.data)
    if serializer.is_valid():
        try:
            CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id)).update(csEmailNotification=serializer.validated_data['emailNotification'])
            return api_response(200, "Save Email Notification Successfully.")
        except CalendarSetup.DoesNotExist:
            return api_response(404, "Tenant not found.")
    return api_response(400, "Invalid data.", serializer.errors)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_sms_notification(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = SaveTenantSmsNotificationDtoSerializer(data=request.data)
    if serializer.is_valid():
        try:
            CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id)).update(csSmsNotification=serializer.validated_data['smsNotification'])
            return api_response(200, "Save SMS Notification Successfully.")
        except CalendarSetup.DoesNotExist:
            return api_response(404, "Tenant not found.")
    return api_response(400, "Invalid data.", serializer.errors)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_event_list(request):
    tenant_id = get_final_tenant_id(request=request)
    start_date_str = request.query_params.get('start')
    end_date_str = request.query_params.get('end')
    tenant_time_zone = request.query_params.get('timeZone', 'UTC')
    
    if not start_date_str or not end_date_str:
        return api_response(400, "startDate and endDate are required.")

    try:
        user_tz = pytz.timezone(tenant_time_zone)
        # Parse start and end dates and make them aware using the provided timezone
        start_dt = datetime.strptime(start_date_str, "%m/%d/%Y").replace(hour=0, minute=0, second=0)
        end_dt = datetime.strptime(end_date_str, "%m/%d/%Y").replace(hour=23, minute=59, second=59)
        
        start_dt = timezone.make_aware(start_dt, user_tz)
        end_dt = timezone.make_aware(end_dt, user_tz)

        events = Calendar.objects.filter(
            calMemberId=get_client_id_by_tenant_id(tenant_id),
            calStartDateTime__lte=end_dt,
            calEndDateTime__gte=start_dt
        ).order_by('calStartDateTime')

        company_name_normalized = settings.COMPANY_NAME.lower().replace(" ", "")
        db_tz = getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')

        calendar_dto_list = []
        for event in events:
            display_tz = tenant_time_zone
            if event.calType and event.calType.lower() == company_name_normalized:
                display_tz = event.calTimeZone or tenant_time_zone
            dto = {
                "id": event.calId,
                "title": event.calTitle,
                "description": event.calDescription,
                "allDay": event.calAllDay.lower() == 'true',
                "calMemberId": event.calMemberId,
                "calTimeZone": display_tz,
                "calAttendees": event.calAttendees,
                "slotMember": None,
                "calAetId": event.calAetId,
                "slotTimeMinus": 0,
                "contactList": (event.calNumbers or "").split(",") if event.calNumbers else [],
                "calType": event.calType,
                "currentDateYN": None,
                "memTimeZone": None,
                "calEventReminder": event.calEventReminder,
                "calReminderSubject": event.calReminderSubject,
                "calReminderType": event.calReminderType,
                "calMyPageId": event.calMyPageId,
                "calSmsSstId": event.calSmsSstId,
                "calParentId": event.calParentId,
                "calRepeatEvery": event.calRepeatEvery,
                "calRepeatType": event.calRepeatType,
                "calRepeatEveryType": event.calRepeatEveryType,
                "calRepeatDayName": event.calRepeatDayName,
                "calRepeatEndDate": None,
                "calRepeatDate": None,
                "calRepeatSelectedOption": event.calRepeatSelectedOption,
                "editAll": None
            }


            if event.calStartDateTime:
                start_str = convert_event_timezone_to_user(display_date_time(event.calStartDateTime), db_tz, tenant_time_zone)
                display_start_str = convert_event_timezone_to_user(display_date_time(event.calStartDateTime), db_tz, display_tz)
                if dto["allDay"]:
                    if start_str and " " in start_str:
                        start_str = start_str.split(" ")[0] + " 00:00:00"
                    if display_start_str and " " in display_start_str:
                        display_start_str = display_start_str.split(" ")[0] + " 00:00:00"
                dto["start"] = start_str
                dto["displayStart"] = display_start_str
            
            if event.calEndDateTime:
                end_str = convert_event_timezone_to_user(display_date_time(event.calEndDateTime), db_tz, tenant_time_zone)
                display_end_str = convert_event_timezone_to_user(display_date_time(event.calEndDateTime), db_tz, display_tz)
                if dto["allDay"]:
                    if end_str and " " in end_str:
                        end_str = end_str.split(" ")[0] + " 00:00:00"
                    if display_end_str and " " in display_end_str:
                        display_end_str = display_end_str.split(" ")[0] + " 00:00:00"
                dto["end"] = end_str
                dto["displayEnd"] = display_end_str

            if event.calScheduleDateTime:
                dto["calScheduleDateTime"] = convert_event_timezone_to_user(display_date_time(event.calScheduleDateTime), db_tz, display_tz)

            if event.calRepeatEndDate:
                dto["calRepeatEndDate"] = convert_event_timezone_to_user(display_date_time(event.calRepeatEndDate), db_tz, display_tz)
            
            if event.calRepeatDate:
                dto["calRepeatDate"] = convert_event_timezone_to_user(display_date_time(event.calRepeatDate), db_tz, display_tz)
            calendar_dto_list.append(dto)

        return api_response(200, "Fetch Event Successfully.", {"eventList": calendar_dto_list})
    except Exception as e:
        logger.error(f"get_event_list error: {e}")
        return api_response(500, f"Internal server error: {str(e)}")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_event(request, calId):
    tenant_id = get_final_tenant_id(request=request)
    cal_id = calId
    tenant_time_zone = request.query_params.get('timezone', 'UTC')

    if not cal_id:
        return api_response(400, "calId is required.")

    try:
        event = Calendar.objects.get(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id))
        company_name_normalized = settings.COMPANY_NAME.lower().replace(" ", "")
        display_tz = tenant_time_zone
        if event.calType and event.calType.lower() == company_name_normalized:
            display_tz = event.calTimeZone or tenant_time_zone

        db_tz = getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')

        dto = {
            "id": event.calId,
            "title": event.calTitle,
            "description": event.calDescription,
            "allDay": event.calAllDay.lower() == 'true',
            "calMemberId": event.calMemberId,
            "calTimeZone": display_tz,
            "calAttendees": event.calAttendees,
            "calAetId": event.calAetId,
            "calType": event.calType,
            "calEventReminder": event.calEventReminder,
            "calReminderSubject": event.calReminderSubject,
            "calReminderType": event.calReminderType,
            "calMyPageId": event.calMyPageId,
            "calSmsSstId": event.calSmsSstId,
            "calParentId": event.calParentId,
            "calRepeatEvery": event.calRepeatEvery,
            "calRepeatType": event.calRepeatType,
            "calRepeatEveryType": event.calRepeatEveryType,
            "calRepeatDayName": event.calRepeatDayName,
            "calRepeatSelectedOption": event.calRepeatSelectedOption,
            "contactList": (event.calNumbers or "").split(",") if event.calNumbers else []
        }

        if event.calStartDateTime:
            start_str = convert_event_timezone_to_user(display_date_time(event.calStartDateTime), db_tz, tenant_time_zone)
            display_start_str = convert_event_timezone_to_user(display_date_time(event.calStartDateTime), db_tz, display_tz)
            if dto["allDay"]:
                if start_str and " " in start_str:
                    start_str = start_str.split(" ")[0] + " 00:00:00"
                if display_start_str and " " in display_start_str:
                    display_start_str = display_start_str.split(" ")[0] + " 00:00:00"
            dto["start"] = start_str
            dto["displayStart"] = display_start_str
        
        if event.calEndDateTime:
            end_str = convert_event_timezone_to_user(display_date_time(event.calEndDateTime), db_tz, tenant_time_zone)
            display_end_str = convert_event_timezone_to_user(display_date_time(event.calEndDateTime), db_tz, display_tz)
            if dto["allDay"]:
                if end_str and " " in end_str:
                    end_str = end_str.split(" ")[0] + " 00:00:00"
                if display_end_str and " " in display_end_str:
                    display_end_str = display_end_str.split(" ")[0] + " 00:00:00"
            dto["end"] = end_str
            dto["displayEnd"] = display_end_str

        if event.calScheduleDateTime:
            dto["calScheduleDateTime"] = convert_event_timezone_to_user(display_date_time(event.calScheduleDateTime), db_tz, display_tz)

        if event.calRepeatEndDate:
            dto["calRepeatEndDate"] = convert_event_timezone_to_user(display_date_time(event.calRepeatEndDate), db_tz, display_tz)
        
        if event.calRepeatDate:
            dto["calRepeatDate"] = convert_event_timezone_to_user(display_date_time(event.calRepeatDate), db_tz, display_tz)

        return api_response(200, "Fetch Event Successfully.", dto)
    except Calendar.DoesNotExist:
        return api_response(404, "Event not found.")
    except Exception as e:
        logger.error(f"get_event error: {e}")
        return api_response(500, f"Internal server error: {str(e)}")

def download_google(google_calendar_data, tenant_id, current_date, google_flag):
    google_time_zone = ""
    google_cal_id_list = []
    # 1. Download Google Calendar to Local Data
    if google_calendar_data:
        if google_calendar_data.csAccessToken:
            google_access_token = google_calendar_views.refresh_google_token(google_calendar_data)
            if google_access_token:
                google_calendar_data.csAccessToken = google_access_token
                google_calendar_data.save()
                google_time_zone = google_calendar_views.get_user_calendar_timezone(google_access_token)

                # Check sync time
                if google_calendar_data.csRefreshTime:
                    last_updated_json = _get_google_last_updated_time(google_access_token)
                    if last_updated_json and last_updated_json.get("updated") == google_calendar_data.csRefreshTime:
                        google_flag = 1

                if google_flag == 0:
                    # Passing [] as the second arg because Java passes an empty list to download method
                    google_cal_id_list = _download_google_calendar_to_local_data(tenant_id, google_access_token, current_date)
    return google_time_zone, google_cal_id_list, google_flag

def download_outlook(outlook_calendar_data, tenant_id, current_date, outlook_flag) :
    # 2. Download Outlook Calendar to Local Data
    outlook_time_zone = ""
    outlook_cal_id_list = []
    if outlook_calendar_data:
        if outlook_calendar_data.csAccessToken:
            outlook_access_token = outlook_calendar_views.refresh_outlook_token(outlook_calendar_data)
            if outlook_access_token:
                outlook_time_zone = outlook_calendar_views.get_user_calendar_timezone(outlook_access_token)
                if outlook_flag == 0:
                    outlook_cal_id_list = _download_outlook_calendar_to_local_data(tenant_id, outlook_access_token, current_date)
    return outlook_time_zone, outlook_cal_id_list, outlook_flag

def upload_google(google_calendar_data, tenant_id, current_date, google_flag, google_time_zone, google_cal_id_list) :
    # 3. Upload Local Data to Google Calendar
    if google_calendar_data:
        if google_flag == 0:
            _upload_local_data_to_google_calendar(tenant_id, google_time_zone, google_cal_id_list, current_date)
        else:
            # findTypeCalendarList logic: already synced records
            member_cal_ids = Calendar.objects.filter(calMemberId=get_client_id_by_tenant_id(tenant_id)).exclude(
                calEventReminder='reminder').values_list('calId', flat=True)
            synced_ids = CalendarDetails.objects.filter(
                caldType="google",
                caldSycId__isnull=False,
                caldCalId__in=member_cal_ids
            ).values_list('caldCalId', flat=True)
            _upload_local_data_to_google_calendar(tenant_id, google_time_zone, synced_ids, current_date)

        # Save sync time
        last_updated_json = _get_google_last_updated_time(google_calendar_data.csAccessToken)
        if last_updated_json and "updated" in last_updated_json:
            google_calendar_data.csRefreshTime = last_updated_json["updated"]
            google_calendar_data.save()

def upload_outlook(outlook_calendar_data, outlook_flag, outlook_time_zone, outlook_cal_id_list, tenant_id, current_date) :
    # 4. Upload Local Data to Outlook Calendar
    if outlook_calendar_data:
        if outlook_flag == 0:
            _upload_local_data_to_outlook_calendar(tenant_id, outlook_time_zone, outlook_cal_id_list, current_date)
        else:
            member_cal_ids = Calendar.objects.filter(calMemberId=get_client_id_by_tenant_id(tenant_id)).exclude(
                calEventReminder='reminder').values_list('calId', flat=True)
            synced_ids = CalendarDetails.objects.filter(
                caldType="outlook",
                caldSycId__isnull=False,
                caldCalId__in=member_cal_ids
            ).values_list('caldCalId', flat=True)
            _upload_local_data_to_outlook_calendar(tenant_id, outlook_time_zone, synced_ids, current_date)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sync(request):
    tenant_id = get_final_tenant_id(request=request)
    time_zone = request.query_params.get("timeZone")
    try:
        google_calendar_data = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
        outlook_calendar_data = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
        tenant_time_zone = get_client_timezone(tenant_id) or time_zone
        now_tenant = timezone.now().astimezone(pytz.timezone(tenant_time_zone or "UTC"))
        current_date = now_tenant.strftime("%Y-%m-%d")
        default_calendar = "google"
        if google_calendar_data and google_calendar_data.csDefaultCalendar == "Y":
            default_calendar = "google"
        if outlook_calendar_data and outlook_calendar_data.csDefaultCalendar == "Y":
            default_calendar = "microsoft"
        google_flag = 0
        outlook_flag = 0

        if default_calendar == "google":
            google_time_zone, google_cal_id_list, google_flag = download_google(google_calendar_data, tenant_id, current_date, google_flag)
            outlook_time_zone, outlook_cal_id_list, outlook_flag = download_outlook(outlook_calendar_data, tenant_id, current_date, outlook_flag)
            upload_google(google_calendar_data, tenant_id, current_date, google_flag, google_time_zone, google_cal_id_list)
            upload_outlook(outlook_calendar_data, outlook_flag, outlook_time_zone, outlook_cal_id_list, tenant_id, current_date)
        else:
            outlook_time_zone, outlook_cal_id_list, outlook_flag = download_outlook(outlook_calendar_data, tenant_id, current_date, outlook_flag)
            google_time_zone, google_cal_id_list, google_flag = download_google(google_calendar_data, tenant_id, current_date, google_flag)
            upload_outlook(outlook_calendar_data, outlook_flag, outlook_time_zone, outlook_cal_id_list, tenant_id, current_date)
            upload_google(google_calendar_data, tenant_id, current_date, google_flag, google_time_zone, google_cal_id_list)
        return api_response(200, "Sync Event Successfully.")
    except Clients.DoesNotExist:
        return api_response(404, "Client not found.")
    except Exception as e:
        logger.error(f"get_sync error: {e}")
        logger.error(traceback.format_exc())
        return api_response(500, f"Internal server error: {str(e)}")

def _get_google_last_updated_time(access_token):
    request_url = f"{settings.GOOGLE_CALENDAR_API_URI}events?maxResults=1&singleEvents=true"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(request_url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching Google last updated time: {e}")
    return {}

def _download_google_calendar_to_local_data(tenant_id, access_token, current_date):
    db_tz = get_user_db_timezone()
    pageToken = None
    cal_id_list = []

    while True:
        request_url = f"{settings.GOOGLE_CALENDAR_API_URI}events?maxResults=100&singleEvents=true"
        if pageToken is not None:
            request_url += "&pageToken=" + str(pageToken)
        request_url += "&timeMin=" + current_date + "T00:00:00Z"

        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            response = requests.get(request_url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Google Calendar API error: {response.status_code} {response.text}")
                break
                
            events_json = response.json()
            
            # Java Extracts root timezone: response.getString("timeZone")
            user_calendar_time_zone = events_json.get("timeZone", "")
            
            items = events_json.get("items", [])
            for item in items:
                if "summary" not in item:
                    continue
                    
                sync_id = item.get("id")
                title = item.get("summary", "")
                description = item.get("description", "")
                
                # Attendee parsing (Java lines 477-487)
                cal_attendees_list = []
                if "attendees" in item:
                    for attendee in item["attendees"]:
                        email = attendee.get("email")
                        if email and email not in cal_attendees_list:
                            cal_attendees_list.append(email)
                
                # Attendee JSON string for database
                attnd_str = ""
                if cal_attendees_list:
                    attnd_str = json.dumps({"attendees": cal_attendees_list})
                
                # Timezone and Date parsing
                start_raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
                end_raw = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
                
                if not start_raw: 
                    continue
                
                all_day = "true" if "date" in item.get("start", {}) else "false"
                item_time_zone = item.get("start", {}).get("timeZone", "")
                
                # Convert ISO to DB format yyyy-MM-dd HH:mm:ss
                start_db = convert_time_zone_to_db_date(start_raw)
                end_db = convert_time_zone_to_db_date(end_raw)
                
                # Shift from event timezone to user/DB timezone
                # Java uses root user_calendar_time_zone (line 497)
                conv_from_tz = user_calendar_time_zone or item_time_zone or "UTC"
                
                start_for_db = _convert_event_time_zone_to_user_db_aware(start_db[:19], conv_from_tz, db_tz)
                end_for_db = _convert_event_time_zone_to_user_db_aware(end_db[:19], conv_from_tz, db_tz)
                
                if not start_for_db or not end_for_db:
                    continue
                
                # Check existence in CalendarDetails
                detail = CalendarDetails.objects.filter(caldSycId=sync_id, caldType="google").first()
                
                if not detail:
                    # Check if exists in Calendar by Title + Start + End (Java line 552)
                    # Removed calTimeZone from filter to match Java findData
                    cal = Calendar.objects.filter(
                        calMemberId=get_client_id_by_tenant_id(tenant_id),
                        calTitle=title,
                        calStartDateTime=start_for_db,
                        calEndDateTime=end_for_db
                    ).first()
                    
                    if not cal:
                        # Create new Calendar record (Java lines 562-621)
                        cal = Calendar.objects.create(
                            calMemberId=get_client_id_by_tenant_id(tenant_id),
                            calTitle=title,
                            calDescription=description,
                            calStartDateTime=start_for_db,
                            calEndDateTime=end_for_db,
                            calTimeZone=item_time_zone,
                            calAllDay=all_day,
                            calType="google",
                            calCreatedDateTime=timezone.now(),
                            calUpdatedDateTime=timezone.now(),
                            calNotification='Y', # Default to 'Y' for new download
                            calEventReminder="event",
                            calReminderSubject="",
                            calReminderType="",
                            calMyPageId=0,
                            calSmsSstId=0,
                            calScheduleDateTime=timezone.now(),
                            calAttendees=attnd_str
                        )
                    else:
                        # Update existing Calendar found via Title/Start/End (Java lines 566-568)
                        cal.calTitle = title
                        cal.calDescription = description
                        cal.calAllDay = all_day
                        cal.calAttendees = attnd_str
                        cal.calStartDateTime = start_for_db
                        cal.calEndDateTime = end_for_db
                        cal.calTimeZone = item_time_zone
                        cal.calUpdatedDateTime = timezone.now()
                        cal.calEventReminder = "event"
                        cal.calReminderSubject = ""
                        cal.calReminderType = ""
                        cal.calMyPageId = 0
                        cal.calSmsSstId = 0
                        cal.calScheduleDateTime = timezone.now()
                        cal.save()
                    
                    # Save to CalendarDetails
                    CalendarDetails.objects.create(
                        caldCalId=cal.calId,
                        caldType="google",
                        caldSycId=sync_id
                    )
                    cal_id_list.append(cal.calId)
                else:
                    # Update existing record linked via CalendarDetails (Java lines 631-657)
                    cal = Calendar.objects.filter(calId=detail.caldCalId, calMemberId=get_client_id_by_tenant_id(tenant_id)).first()
                    if cal:
                        cal.calTitle = title
                        cal.calDescription = description
                        cal.calAllDay = all_day
                        cal.calStartDateTime = start_for_db
                        cal.calEndDateTime = end_for_db
                        # cal.calTimeZone = item_time_zone # Java comments this out (line 642)
                        cal.calUpdatedDateTime = timezone.now()
                        cal.calEventReminder = "event"
                        cal.calReminderSubject = ""
                        cal.calReminderType = ""
                        cal.calMyPageId = 0
                        cal.calSmsSstId = 0
                        cal.calScheduleDateTime = timezone.now()
                        cal.save()
                        cal_id_list.append(cal.calId)

            if "nextPageToken" in events_json:
                pageToken = events_json.get("nextPageToken")
            else:
                pageToken = None
        except Exception as e:
            logger.error(f"Error downloading Google calendar: {e}")
            logger.error(traceback.format_exc())
            break
            
        if not pageToken:
            break
            
    return cal_id_list


def _upload_local_data_to_google_calendar(tenant_id, time_zone, cal_id_list, current_date):
    db_tz = get_user_db_timezone()
    
    synced_ids = CalendarDetails.objects.filter(caldType="google").values_list('caldCalId', flat=True)
    if not cal_id_list:
        calendar_list = Calendar.objects.filter(calMemberId=get_client_id_by_tenant_id(tenant_id)).exclude(calId__in=synced_ids)
    else:    
        # calendar_list = Calendar.objects.filter(calMemberId=member_id, calId__in=cal_id_list).exclude(calId__in=synced_ids)
        calendar_list = Calendar.objects.filter(
            calMemberId=get_client_id_by_tenant_id(tenant_id),
            calStartDateTime__date__gte=current_date,  # TRUNC and TO_DATE equivalent
        ).exclude(  
            calId__in=cal_id_list                     # NOT IN equivalent
        ).exclude(
            calEventReminder='reminder'               # != 'reminder' equivalent
        )
    for cdar in calendar_list:
        # Skip events with missing dates to avoid API errors (Fix for Outlook 400)
        if not cdar.calStartDateTime or not cdar.calEndDateTime:
            logger.warning(f"Skipping upload for local event {cdar.calId}: Missing start or end date.")
            continue
            
        # Prepare DTO for save_event_internal
        # Java logic: shift date from DB (UTC) to User TZ
        start_display = convert_event_timezone_to_user(
            date_object_to_display_date(cdar.calStartDateTime),
            db_tz, 
            cdar.calTimeZone or time_zone
        )
        end_display = convert_event_timezone_to_user(
            date_object_to_display_date(cdar.calEndDateTime),
            db_tz, 
            cdar.calTimeZone or time_zone
        )

        event_data = {
            "title": cdar.calTitle,
            "description": cdar.calDescription,
            "start": start_display,
            "end": end_display,
            "allDay": cdar.calAllDay.lower() == "true",
            "calTimeZone": cdar.calTimeZone or time_zone,
            "calAttendees": cdar.calAttendees or ""
        }
        try:
            res = google_calendar_views.save_event_internal(tenant_id, event_data)
            if res.get("caldSycId"):
                CalendarDetails.objects.create(
                    caldCalId=cdar.calId,
                    caldType="google",
                    caldSycId=res["caldSycId"]
                )
        except Exception as e:
            logger.error(f"Error uploading local event {cdar.calId} to Google: {e}")

def _download_outlook_calendar_to_local_data(tenant_id, access_token, current_date):
    db_tz = get_user_db_timezone()
    
    next_link = None
    top = 100
    skip = 0
    cal_id_list = []
    
    try:
        while True:
            if not next_link:
                request_url = f"{settings.OUTLOOK_CALENDAR_API_URI}events?$select=transactionId,subject,bodyPreview,start,end,isAllDay&$count=true&$top={top}"
            else:
                request_url = f"{settings.OUTLOOK_CALENDAR_API_URI}events?$select=transactionId,subject,bodyPreview,start,end,isAllDay&$count=true&$top={top}&$skip={skip}"
            
            # Java adds filter for current date
            request_url += f"&$filter=Start/DateTime ge '{current_date[:10]}T00:00:00Z'"
            
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(request_url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Outlook Calendar API error: {response.status_code} {response.text}")
                break
                
            response_json = response.json()
            next_link = response_json.get("@odata.nextLink")
            skip += top
            
            json_array = response_json.get("value", [])
            for res in json_array:
                sync_id = res.get("id")
                title = res.get("subject", "")
                description = res.get("bodyPreview", "")
                
                # Attendee extraction (Java lines 380-389)
                cal_attendees = []
                if description:
                    regex_email = r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,6}\b'
                    matches = re.findall(regex_email, description, re.IGNORECASE)
                    for m in matches:
                        email = m.lower()
                        if email not in cal_attendees:
                            cal_attendees.append(email)
                
                # Attendee string formation (Java lines 453-465)
                attnd_str = ""
                if cal_attendees:
                    attnd_str = json.dumps({"attendees": cal_attendees})
                
                all_day = "true" if res.get("isAllDay") else "false"
                
                # TZ and Date parsing
                start_obj = res.get("start", {})
                end_obj = res.get("end", {})
                
                time_zone = start_obj.get("timeZone", "UTC")
                start_raw = start_obj.get("dateTime")
                end_raw = end_obj.get("dateTime")
                
                if not start_raw: 
                    continue
                
                # Java: substring(0, 19) to strip decimals
                start_db = convert_time_zone_to_db_date(start_raw[:19])
                end_db = convert_time_zone_to_db_date(end_raw[:19])
                
                # Shift from event timezone to user/DB timezone
                start_for_db = _convert_event_time_zone_to_user_db_aware(start_db, time_zone, db_tz)
                end_for_db = _convert_event_time_zone_to_user_db_aware(end_db, time_zone, db_tz)
                
                if not start_for_db or not end_for_db:
                    continue
                
                # Check existence in CalendarDetails
                detail = CalendarDetails.objects.filter(caldSycId=sync_id, caldType="outlook").first()
                if detail:
                    # Update existing record linked via CalendarDetails (Java lines 510-541)
                    cal = Calendar.objects.filter(calId=detail.caldCalId, calMemberId=get_client_id_by_tenant_id(tenant_id)).first()
                    if cal:
                        cal.calTitle = title if title is not None else ""
                        cal.calDescription = description
                        cal.calAllDay = all_day
                        cal.calStartDateTime = start_for_db
                        cal.calEndDateTime = end_for_db
                        cal.calUpdatedDateTime = timezone.now()
                        cal.calEventReminder = "event"
                        cal.calReminderSubject = ""
                        cal.calReminderType = ""
                        cal.calMyPageId = 0
                        cal.calSmsSstId = 0
                        cal.calScheduleDateTime = timezone.now()
                        cal.save()
                        cal_id_list.append(cal.calId)
                else:
                    # Check if exists in Calendar by Title + Start + End (Java line 429)
                    cal = Calendar.objects.filter(
                        calMemberId=get_client_id_by_tenant_id(tenant_id),
                        calTitle=title,
                        calStartDateTime=start_for_db,
                        calEndDateTime=end_for_db
                    ).first()
                    
                    if not cal:
                        # Create new Calendar record (Java lines 440-499)
                        cal = Calendar.objects.create(
                            calMemberId=get_client_id_by_tenant_id(tenant_id),
                            calTitle=title if title is not None else "",
                            calDescription=description,
                            calAllDay=all_day,
                            calStartDateTime=start_for_db,
                            calEndDateTime=end_for_db,
                            calTimeZone=time_zone,
                            calCreatedDateTime=timezone.now(),
                            calUpdatedDateTime=timezone.now(),
                            calNotification="Y",
                            calType="outlook",
                            calEventReminder="event",
                            calReminderSubject="",
                            calReminderType="",
                            calMyPageId=0,
                            calSmsSstId=0,
                            calScheduleDateTime=timezone.now(),
                            calAttendees=attnd_str
                        )
                    else:
                        cal.calTitle = title if title is not None else ""
                        cal.calDescription = description
                        cal.calAllDay = all_day
                        cal.calAttendees = attnd_str
                        cal.calStartDateTime = start_for_db
                        cal.calEndDateTime = end_for_db
                        cal.calTimeZone = time_zone
                        cal.calUpdatedDateTime = timezone.now()
                        cal.calEventReminder = "event"
                        cal.calReminderSubject = ""
                        cal.calReminderType = ""
                        cal.calMyPageId = 0
                        cal.calSmsSstId = 0
                        cal.calScheduleDateTime = timezone.now()
                        cal.save()
                            
                    # Save to CalendarDetails
                    CalendarDetails.objects.create(
                        caldCalId=cal.calId,
                        caldType="outlook",
                        caldSycId=sync_id
                    )
                    cal_id_list.append(cal.calId)
            
            if not next_link:
                break
    except Exception as e:
        logger.error(f"Error downloading Outlook calendar: {e}")
        logger.error(traceback.format_exc())
    return cal_id_list


def _upload_local_data_to_outlook_calendar(tenant_id, time_zone, cal_id_list, current_date):
    db_tz = get_user_db_timezone()
    if not cal_id_list:
        calendar_list = Calendar.objects.filter(calMemberId=get_client_id_by_tenant_id(tenant_id))
    else:
        calendar_list = Calendar.objects.filter(
            calMemberId=get_client_id_by_tenant_id(tenant_id),
            calStartDateTime__date__gte=current_date
        ).exclude(
            calId__in=cal_id_list
        ).exclude(
            calEventReminder='reminder'
        )       
    for cdar in calendar_list:
        flagCalendarDetails = 0
        caldId = 0
        try:
            calendarDetailsList = CalendarDetails.objects.filter(caldCalId=cdar.calId, caldType="outlook")
            if calendarDetailsList.exists():
                calendarDetails = calendarDetailsList[0]
                caldId = calendarDetails.caldId
                if calendarDetails.caldSycId and len(calendarDetails.caldSycId) > 0:
                    flagCalendarDetails = 1
                    calendarDetails.delete()
                    try:
                        # Error 1 alignment (Java lines 578-581)
                        count = CalendarDetails.objects.filter(caldCalId=cdar.calId).count()
                        if count == 0:
                            cdar.delete()
                    except Exception as e:
                        logger.error(f"[ memberId : {tenant_id} ] UploadLocalDataToOutlookCalendar Error 1 : {e}")
        except Exception as e:
            logger.error(f"[ memberId : {tenant_id} ] UploadLocalDataToOutlookCalendar Error 2 : {e}")

        if flagCalendarDetails == 0:
            # Skip events with missing dates to avoid API errors (Fix for Outlook 400)
            if not cdar.calStartDateTime or not cdar.calEndDateTime:
                logger.warning(f"Skipping upload for local event {cdar.calId}: Missing start or end date.")
                continue
            event_data = dict()
            event_data["calTitle"] = cdar.calTitle
            event_data["calDescription"] = cdar.calDescription
            event_data["calAttendees"] = []
            
            try:
                # Error 3 alignment (Java lines 597-613)
                if cdar.calAttendees:
                    data = json.loads(cdar.calAttendees)
                    if "attendees" in data:
                        event_data["calAttendees"] = [str(a) for a in data["attendees"]]
            except Exception as e:
                logger.error(f"[ memberId : {tenant_id} ] UploadLocalDataToOutlookCalendar Error 3 : {e}")

            cal_target_tz = cdar.calTimeZone if cdar.calTimeZone else time_zone
            
            try:
                if cdar.calStartDateTime:
                    start_str = date_object_to_display_date(cdar.calStartDateTime)
                    target_tz = change_timezone_name(cal_target_tz if cal_target_tz else db_tz)
                    event_data["start"] = convert_event_timezone_to_user(start_str, db_tz, target_tz)
                
                if cdar.calEndDateTime:
                    end_str = date_object_to_display_date(cdar.calEndDateTime)
                    target_tz = change_timezone_name(cal_target_tz if cal_target_tz else db_tz)
                    event_data["end"] = convert_event_timezone_to_user(end_str, db_tz, target_tz)
                    
            except Exception as e:
                logger.error(f"[ memberId : {tenant_id} ] UploadLocalDataToOutlookCalendar Error 4 : {e}")

            event_data["allDay"] = cdar.calAllDay.lower() == "true"
            event_data["calTimeZone"] = cal_target_tz
            try:
                res = outlook_calendar_views.save_event_internal(tenant_id, event_data)
                if res and res.get("error") == "":
                    sync_id = res.get("caldSycId")
                    if sync_id:
                        CalendarDetails.objects.create(
                            caldId=caldId if caldId > 0 else None, # PK preservation attempts
                            caldCalId=cdar.calId,
                            caldType="outlook",
                            caldSycId=sync_id
                        )
            except Exception as e:
                logger.error(f"[ memberId : {tenant_id} ] UploadLocalDataToOutlookCalendar Error 5 : {e}")

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def delete_event(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = DeleteEventDtoSerializer(data=request.data)
    if serializer.is_valid():
        try:
            cal_id = serializer.validated_data['calId']
            delete_all = serializer.validated_data.get('deleteAll', 'N')
            
            # 1. Fetch event first for details and series resolution
            event = Calendar.objects.filter(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id)).first()
            if not event:
                return api_response(404, "Event not found.")

            cal_parent_id = event.calParentId or 0
            ids_to_delete = [cal_id]

            # 2. Comprehensive ID Collection
            if delete_all == 'Y':
                if cal_parent_id > 0:
                    # Mirror Java's findIdsAndParentId repo query
                    target_indices = [cal_id, cal_parent_id]
                    ids_to_delete = list(Calendar.objects.filter(
                        Q(calId__in=target_indices) | Q(calParentId__in=target_indices),
                        calMemberId=get_client_id_by_tenant_id(tenant_id)
                    ).values_list('calId', flat=True))
                else:
                    # Mirror Java's findIds repo query
                    ids_to_delete = list(Calendar.objects.filter(
                        Q(calId=cal_id) | Q(calParentId=cal_id),
                        calMemberId=get_client_id_by_tenant_id(tenant_id)
                    ).values_list('calId', flat=True))

            # 3. External Sync & CalendarDetails Cleanup
            google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
            outlook_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
            sync_details = CalendarDetails.objects.filter(caldCalId__in=ids_to_delete)
            
            for detail in sync_details:
                if detail.caldType == "google" and google_calendar_setup and google_calendar_setup.csAccessToken:
                    google_calendar_views.delete_event_internal(tenant_id, detail.caldSycId)
                elif detail.caldType == "outlook" and outlook_calendar_setup and outlook_calendar_setup.csAccessToken:
                    outlook_calendar_views.delete_event_internal(tenant_id, detail.caldSycId)
            
            sync_details.delete()

            # 4. Notification & Reminder Cleanup
            CalendarNotification.objects.filter(calnCalId__in=ids_to_delete).delete()
            CalendarNotificationReminder.objects.filter(calnCalId__in=ids_to_delete).delete()

            # 5. Automated Cancellation Emails
            try:
                # Formatted dates for the email template
                # Shift UTC date from DB to event's local timezone for email display (Mirroring Java line 393)
                start_dt = event.calStartDateTime
                if start_dt and event.calTimeZone:
                    try:
                        tz_obj = pytz.timezone(event.calTimeZone)
                        if not timezone.is_aware(start_dt):
                            start_dt = timezone.make_aware(start_dt, pytz.UTC)
                        start_dt = start_dt.astimezone(tz_obj)
                    except Exception as e:
                        logger.error(f"Error shifting date for deletion email: {e}")

                start_date_str = start_dt.strftime("%Y-%m-%d %H:%M:%S") if start_dt else ""
                
                # In delete-event template we use meetingDateTime and inviteeTimezone
                meeting_date_time = db_date_to_display_date_time(start_date_str)
                invitee_timezone = event.calTimeZone or "UTC"

                tenant = get_tenants(
                    where_conditions={
                        "tenant": {
                            "ten_id": tenant_id
                        }
                    }
                )
                client = Clients.objects.get(cliTenantId=tenant_id)

                # customerLogo logic (Java lines 394-402)
                first_name = tenant.ten_first_name or ""
                last_name = tenant.ten_last_name or ""
                image_url = client.cliProfileImageUrl

                if not image_url:
                    initials = ""
                    if first_name: initials += first_name[0].upper()
                    if last_name: initials += last_name[0].upper()
                    customer_logo = f'<div style="align-items: center; background: #4285f4; border-radius: 50%; color: #fff; display: flex; font-size: 22px; height: 60px; justify-content: center; text-align: center; width: 60px; font-family: \'Poppins\', sans-serif !important;"><span style="margin: auto;">{initials}</span></div>'
                else:
                    # Ensure image_url is absolute for emails
                    image_src = image_url if image_url.startswith('http') else f"{settings.IMAGE_SITE_URL.rstrip('/')}/{image_url.lstrip('/')}"
                    customer_logo = f'<img tabindex="0" src="{image_src}" style="margin:0;padding:0;outline:none;text-decoration:none;max-width:120px" border="0" />'

                # webConference logic (Java lines 427-431)
                web_conf = google_calendar_setup.csWebConferenceUrl if google_calendar_setup else ""
                if not web_conf:
                    web_conf = outlook_calendar_setup.csWebConferenceUrl if outlook_calendar_setup else ""
                if web_conf:
                    # Simple regex to find links and wrap in <a> tags, then nl2br
                    regex_url = r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'\".,<>?«»“”‘’]))'
                    web_conf = re.sub(regex_url, r"<a href='\1' target='blank'>\1</a>", web_conf)
                    web_conf = web_conf.replace("\n", "<br />")

                email_model = {
                    "meetingDateTime": meeting_date_time,
                    "inviteeTimezone": invitee_timezone,
                    "customerLogo": customer_logo,
                    "webConference": web_conf,
                    # Fallback site metadata
                    "siteName": getattr(settings, 'SITE_NAME', 'SalesAndMarketing'),
                    "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', 'www.salesandmarketing.ai'),
                    "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', 'SalesAndMarketing'),
                    "companyName": getattr(settings, 'COMPANY_NAME', 'SAM'),
                    "eventTitle": event.calTitle,
                    "memberName": f"{first_name} {last_name}".strip(),
                    "memberEmail": tenant.ten_email
                }

                # Prepare recipient list
                recipients = set()
                if tenant.ten_email: recipients.add(tenant.ten_email)
                if google_calendar_setup and google_calendar_setup.csEmail: recipients.add(google_calendar_setup.csEmail)
                if outlook_calendar_setup and outlook_calendar_setup.csEmail: recipients.add(outlook_calendar_setup.csEmail)

                # Extract attendees
                cal_attendees = event.calAttendees
                if cal_attendees:
                    try:
                        attendee_data = json.loads(cal_attendees)
                        parsed_attendees = []
                        if isinstance(attendee_data, list):
                            parsed_attendees = attendee_data
                        elif isinstance(attendee_data, dict) and 'attendees' in attendee_data:
                            parsed_attendees = attendee_data['attendees']
                        
                        for a in parsed_attendees:
                            if isinstance(a, dict) and 'email' in a:
                                recipients.add(a['email'])
                            elif isinstance(a, str) and '@' in a:
                                recipients.add(a.strip())
                    except (json.JSONDecodeError, TypeError):
                        # Fallback to CSV parsing
                        for email in cal_attendees.split(','):
                            email = email.strip()
                            if email and '@' in email:
                                recipients.add(email)

                # Dispatch emails
                for recipient_email in recipients:
                    mail_dto = MailRequestDTO(
                        to=recipient_email,
                        subject=f"Canceled Event: {event.calTitle}",
                        template_name="calendar-delete-event-template.html"
                    )
                    CommonServices.sendEmail(mail_dto, email_model)

            except Exception as e:
                logger.error(f"Error dispatching cancellation emails: {str(e)}")

            # 6. Final Database Deletion
            Calendar.objects.filter(calId__in=ids_to_delete).delete()

            return api_response(200, "Event deleted successfully")
        except Exception as e:
            logger.error(f"delete_event error: {e}")
            return api_response(500, f"Internal server error: {str(e)}")
    return api_response(400, "Invalid data.", serializer.errors)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_event(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = CalendarDtoSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
            outlook_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").first()
            calendar_dto = serializer.validated_data
            
            # Java lines 488-493: Get user timezone from Google Calendar
            time_zone = None
            if google_calendar_setup and google_calendar_setup.csAccessToken and google_calendar_setup.csAccessToken.strip():
                try:
                    access_token = google_calendar_views.refresh_google_token(google_calendar_setup)
                    if access_token:
                        # Mimicking googleCalendarService.getUserTimezone
                        time_zone = google_calendar_views.get_user_calendar_timezone(access_token)
                except Exception:
                    pass
            
            # Java lines 495-499: Set DTO timezone if empty
            if not calendar_dto.get('calTimeZone'):
                if time_zone:
                    calendar_dto['calTimeZone'] = time_zone
            
            # Java lines 501-516: Active clad type list
            clad_type_list = []
            clad_type_list_new = []
            if google_calendar_setup and google_calendar_setup.csAccessToken and google_calendar_setup.csAccessToken.strip():
                clad_type_list.append("google")
                clad_type_list_new.append("google")
            if outlook_calendar_setup and outlook_calendar_setup.csAccessToken and outlook_calendar_setup.csAccessToken.strip():
                clad_type_list.append("outlook")
                clad_type_list_new.append("outlook")

            # Java lines 518-528: Parse attendees
            cal_attendees_list = []
            cal_att = calendar_dto.get('calAttendees')
            if cal_att and cal_att.strip():
                try:
                    data = json.loads(cal_att)
                    if "attendees" in data:
                        for att in data["attendees"]:
                            cal_attendees_list.append(str(att))
                except Exception:
                    # Fallback for simple comma separated if not JSON
                    if "," in cal_att:
                        cal_attendees_list = [a.strip() for a in cal_att.split(",") if a.strip()]
                    else:
                        cal_attendees_list = [cal_att.strip()]

            # Java lines 530-552: Initialize external DTOs
            google_calendar_dto = dict()
            if "google" in clad_type_list:
                google_calendar_dto = {
                    "calTitle": calendar_dto.get('title'),
                    "calDescription": calendar_dto.get('description'),
                    "calStartDateTime": calendar_dto.get('start'),
                    "calEndDateTime": calendar_dto.get('end'),
                    "calAllDay": str(calendar_dto.get('allDay', False)).lower(),
                    "calTimeZone": calendar_dto.get('calTimeZone'),
                    "calAttendees": cal_attendees_list
                }
            
            outlook_calendar_dto = dict()
            if "outlook" in clad_type_list:
                outlook_calendar_dto = {
                    "calTitle": calendar_dto.get('title'),
                    "calDescription": calendar_dto.get('description'),
                    "calStartDateTime": calendar_dto.get('start'),
                    "calEndDateTime": calendar_dto.get('end'),
                    "calAllDay": str(calendar_dto.get('allDay', False)).lower(),
                    "calTimeZone": calendar_dto.get('calTimeZone'),
                    "calAttendees": cal_attendees_list
                }

            # Java lines 554-569: DTO date normalization
            try:
                if calendar_dto.get('start'):
                    calendar_dto['start'] = _convert_date_time_to_db(calendar_dto['start'])
                if calendar_dto.get('end'):
                    calendar_dto['end'] = _convert_date_time_to_db(calendar_dto['end'])
                if calendar_dto.get('calRepeatEndDate'):
                    calendar_dto['calRepeatEndDate'] = _convert_date_time_to_db(calendar_dto['calRepeatEndDate'])
                if calendar_dto.get('calRepeatDate'):
                    calendar_dto['calRepeatDate'] = _convert_date_time_to_db(calendar_dto['calRepeatDate'])
            except Exception as e:
                logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 1: {e}")

            # Java line 572: Set Database Timezone
            db_tz = getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')
            time_zone = db_tz # In Java this is serverDatabaseTimeZone

            # Java lines 574-606: Populate Calendar Model
            cal_id_dto = calendar_dto.get('id', 0)
            calendar = Calendar()
            if cal_id_dto > 0:
                calendar = Calendar.objects.get(calId=cal_id_dto, calMemberId=get_client_id_by_tenant_id(tenant_id))
            
            calendar.calTitle = calendar_dto.get('title')
            calendar.calDescription = calendar_dto.get('description')
            calendar.calMemberId = get_client_id_by_tenant_id(tenant_id)
            calendar.calAllDay = str(calendar_dto.get('allDay', False)).lower()
            calendar.calTimeZone = calendar_dto.get('calTimeZone')
            calendar.calAttendees = calendar_dto.get('calAttendees')
            
            numbers = ""
            for number in calendar_dto.get('contactList', []):
                if not numbers:
                    numbers = number
                else:
                    numbers += "," + number
            calendar.calNumbers = numbers
            calendar.calType = settings.COMPANY_NAME.lower().replace(" ", "")
            
            calendar.calEventReminder = "event"
            calendar.calReminderSubject = ""
            calendar.calReminderType = ""
            calendar.calMyPageId = 0
            calendar.calSmsSstId = 0
            calendar.calScheduleDateTime = timezone.now()
            
            calendar.calParentId = calendar_dto.get('calParentId', 0)
            calendar.calRepeatEvery = calendar_dto.get('calRepeatEvery', 0)
            calendar.calRepeatType = calendar_dto.get('calRepeatType')
            calendar.calRepeatEveryType = calendar_dto.get('calRepeatEveryType')
            calendar.calRepeatDayName = calendar_dto.get('calRepeatDayName')
            calendar.calRepeatSelectedOption = calendar_dto.get('calRepeatSelectedOption', 0)

            # Java lines 608-623: Model date conversion
            try:
                if calendar_dto.get('start'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['start'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calStartDateTime = _convert_date(converted)
                if calendar_dto.get('end'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['end'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calEndDateTime = _convert_date(converted)
                if calendar_dto.get('calRepeatEndDate'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['calRepeatEndDate'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calRepeatEndDate = _convert_date(converted)
                if calendar_dto.get('calRepeatDate'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['calRepeatDate'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calRepeatDate = _convert_date(converted)
            except Exception as e:
                logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 2: {e}")

            # Java lines 625-631: Creation timing
            if cal_id_dto == 0:
                calendar.calCreatedDateTime = timezone.now()
                calendar.calNotification = "N"
            else:
                tmp_calendar = Calendar.objects.get(calId=cal_id_dto, calMemberId=get_client_id_by_tenant_id(tenant_id))
                calendar.calCreatedDateTime = tmp_calendar.calCreatedDateTime

            calendar.calUpdatedDateTime = timezone.now()
            calendar.save()
            cal_id = calendar.calId
            
            # Java lines 636-639: Get Email Notification
            email_notification = ""
            try:
                if google_calendar_setup and google_calendar_setup.csEmailNotification:
                    email_notification = google_calendar_setup.csEmailNotification
                elif outlook_calendar_setup and outlook_calendar_setup.csEmailNotification:
                    email_notification = outlook_calendar_setup.csEmailNotification
            except Exception: pass
            
            # Java lines 641-643: Tenant notification
            _tenant_notification(cal_id, email_notification)

            # Java lines 645-731: External sync (detailed)
            cal_details_list = CalendarDetails.objects.filter(caldCalId=cal_id)
            if cal_details_list.exists():
                for list_item in list(cal_details_list):
                    if list_item.caldType in clad_type_list:
                        if list_item.caldType == "google" and list_item.caldSycId and len(list_item.caldSycId) > 0:
                            try:
                                google_calendar_dto["caldSycId"] = list_item.caldSycId
                                google_calendar_views.save_event_internal(tenant_id, google_calendar_dto)
                            except Exception as e:
                                logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 4: {e}")
                        
                        if list_item.caldType == "outlook" and list_item.caldSycId and len(list_item.caldSycId) > 0:
                            try:
                                outlook_calendar_dto["caldSycId"] = list_item.caldSycId
                                outlook_calendar_views.save_event_internal(tenant_id, outlook_calendar_dto)
                            except Exception as e:
                                logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 5: {e}")
                        
                        clad_type_list.remove(list_item.caldType)
                    else:
                        try:
                            if list_item.caldType == "google" and list_item.caldSycId and len(list_item.caldSycId) > 0:
                                google_calendar_views.delete_event_internal(tenant_id, list_item.caldSycId)
                            if list_item.caldType == "outlook" and list_item.caldSycId and len(list_item.caldSycId) > 0:
                                outlook_calendar_views.delete_event_internal(tenant_id, list_item.caldSycId)
                            list_item.delete()
                        except Exception as e:
                            logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 8: {e}")

            if clad_type_list:
                for ct in clad_type_list:
                    cd = CalendarDetails()
                    if ct == "google":
                        try:
                            google_calendar_dto["caldSycId"] = ""
                            inner_res = google_calendar_views.save_event_internal(tenant_id, google_calendar_dto)
                            if inner_res and not inner_res.get("error"):
                                cd.caldSycId = inner_res.get("caldSycId", "")
                        except Exception as e:
                            logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 9: {e}")
                    
                    if ct == "outlook":
                        try:
                            outlook_calendar_dto["caldSycId"] = ""
                            inner_res = outlook_calendar_views.save_event_internal(tenant_id, outlook_calendar_dto)
                            if inner_res and not inner_res.get("error"):
                                cd.caldSycId = inner_res.get("caldSycId", "")
                        except Exception as e:
                            logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 10: {e}")
                    
                    cd.caldCalId = cal_id
                    cd.caldType = ct
                    cd.save()

            # Java lines 733-804: Repeat functionality
            if calendar_dto.get('calRepeatType') != "donotrepeat":
                if cal_id_dto == 0:
                    repeat_every_type = calendar_dto.get('calRepeatEveryType')
                    if repeat_every_type == "year":
                        _repeat_every_type_year_fun(tenant_id, cal_id, email_notification, "event")
                    if repeat_every_type == "month":
                        _repeat_every_type_month_fun(tenant_id, cal_id, email_notification, "event")
                    if repeat_every_type == "day":
                        _repeat_every_type_day_fun(tenant_id, cal_id, email_notification, "event")
                    if repeat_every_type == "week":
                        _repeat_every_type_week_fun(tenant_id, cal_id, email_notification, "event")
                    
                    cal_list = list(Calendar.objects.filter(calMemberId=get_client_id_by_tenant_id(tenant_id), calParentId=cal_id))
                    # Java line 751: Batch update external calendars
                    _add_edit_event_google_and_outlook(tenant_id, cal_list, clad_type_list_new, cal_attendees_list, calendar.calTimeZone)
                else:
                    if calendar_dto.get('editAll') == "Y":
                        # Java lines 754-802: Update existing series
                        main_record = Calendar.objects.get(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id))
                        if calendar.calParentId > 0:
                            cal_list = list(Calendar.objects.filter(Q(calId=calendar.calId) | Q(calId=calendar.calParentId) | Q(calParentId=calendar.calParentId), calMemberId=get_client_id_by_tenant_id(tenant_id)))
                        else:
                            cal_list = list(Calendar.objects.filter(Q(calId=calendar.calId) | Q(calParentId=calendar.calId), calMemberId=get_client_id_by_tenant_id(tenant_id)))
                        
                        for cal_item in cal_list:
                            cal_item.calTitle = main_record.calTitle
                            cal_item.calDescription = main_record.calDescription
                            cal_item.calAllDay = main_record.calAllDay
                            cal_item.calTimeZone = main_record.calTimeZone
                            cal_item.calAttendees = main_record.calAttendees
                            cal_item.calNumbers = main_record.calNumbers
                            cal_item.calRepeatEvery = main_record.calRepeatEvery
                            cal_item.calRepeatType = main_record.calRepeatType
                            cal_item.calRepeatEveryType = main_record.calRepeatEveryType
                            cal_item.calRepeatDayName = main_record.calRepeatDayName
                            cal_item.calRepeatSelectedOption = main_record.calRepeatSelectedOption
                            cal_item.calUpdatedDateTime = main_record.calUpdatedDateTime
                            
                            # Preserve individual start/end dates but update time portions (Java lines 777-783)
                            if cal_item.calStartDateTime and main_record.calStartDateTime:
                                cal_item.calStartDateTime = cal_item.calStartDateTime.replace(
                                    hour=main_record.calStartDateTime.hour, 
                                    minute=main_record.calStartDateTime.minute,
                                    second=main_record.calStartDateTime.second
                                )
                            if cal_item.calEndDateTime and main_record.calEndDateTime:
                                cal_item.calEndDateTime = cal_item.calEndDateTime.replace(
                                    hour=main_record.calEndDateTime.hour, 
                                    minute=main_record.calEndDateTime.minute,
                                    second=main_record.calEndDateTime.second
                                )
                            
                            cal_item.save()
                            _tenant_notification(cal_item.calId, email_notification)
                        
                        # Refresh list and batch update external calendars
                        if calendar.calParentId > 0:
                            cal_list = list(Calendar.objects.filter(Q(calId=calendar.calId) | Q(calId=calendar.calParentId) | Q(calParentId=calendar.calParentId), calMemberId=get_client_id_by_tenant_id(tenant_id)))
                        else:
                            cal_list = list(Calendar.objects.filter(Q(calId=calendar.calId) | Q(calParentId=calendar.calId), calMemberId=get_client_id_by_tenant_id(tenant_id)))
                        _add_edit_event_google_and_outlook(tenant_id, cal_list, clad_type_list_new, cal_attendees_list, calendar.calTimeZone)

            return api_response(200, "Save Event Successfully" if cal_id_dto == 0 else "Update Event Successfully", {"calId": cal_id})
        except CalendarSetup.DoesNotExist:
            return api_response(404, "Tenant not found.")
        except Exception as e:
            logger.error(f"[ memberId : {tenant_id} ] SaveEvent Error 11: {e}")
            logger.error(traceback.format_exc())
            return api_response(500, f"Internal server error: {str(e)}")
    return api_response(400, "Invalid data.", serializer.errors)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_reminder(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = CalendarDtoSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").first()
            calendar_dto = serializer.validated_data
            
            # Java lines 1355-1360: Get user timezone
            time_zone = None
            if google_calendar_setup and google_calendar_setup.csAccessToken and google_calendar_setup.csAccessToken.strip():
                try:
                    access_token = google_calendar_views.refresh_google_token(google_calendar_setup)
                    if access_token:
                        time_zone = google_calendar_views.get_user_calendar_timezone(access_token)
                except Exception:
                    pass
            
            # Java lines 1362-1366: Set DTO timezone if empty
            if not calendar_dto.get('calTimeZone'):
                if time_zone:
                    calendar_dto['calTimeZone'] = time_zone
            
            # Java lines 1368-1386: DTO date normalization
            try:
                if calendar_dto.get('start'):
                    calendar_dto['start'] = _convert_date_time_to_db(calendar_dto['start'])
                if calendar_dto.get('end'):
                    calendar_dto['end'] = _convert_date_time_to_db(calendar_dto['end'])
                if calendar_dto.get('calScheduleDateTime'):
                    calendar_dto['calScheduleDateTime'] = _convert_date_time_to_db(calendar_dto['calScheduleDateTime'])
                if calendar_dto.get('calRepeatEndDate'):
                    calendar_dto['calRepeatEndDate'] = _convert_date_time_to_db(calendar_dto['calRepeatEndDate'])
                if calendar_dto.get('calRepeatDate'):
                    calendar_dto['calRepeatDate'] = _convert_date_time_to_db(calendar_dto['calRepeatDate'])
            except Exception as e:
                logger.error(f"[ memberId : {tenant_id} ] SaveReminder Error 1: {e}")

            # Java line 1389: Set Database Timezone
            db_tz = getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')
            time_zone = db_tz # In Java this is serverDatabaseTimeZone

            # Java lines 1391-1422: Populate Calendar Model
            cal_id_dto = calendar_dto.get('id', 0)
            calendar = Calendar()
            if cal_id_dto > 0:
                calendar = Calendar.objects.get(calId=cal_id_dto, calMemberId=get_client_id_by_tenant_id(tenant_id))
            
            calendar.calTitle = calendar_dto.get('calReminderSubject')
            calendar.calDescription = calendar_dto.get('description')
            calendar.calMemberId = get_client_id_by_tenant_id(tenant_id)
            calendar.calAllDay = 'false'
            calendar.calTimeZone = calendar_dto.get('calTimeZone')
            calendar.calAttendees = calendar_dto.get('calAttendees')
            
            calendar.calNumbers = ",".join(calendar_dto.get('contactList', []))
            calendar.calType = settings.COMPANY_NAME.lower().replace(" ", "")
            
            calendar.calEventReminder = "reminder"
            calendar.calReminderSubject = calendar_dto.get('calReminderSubject')
            calendar.calReminderType = calendar_dto.get('calReminderType')
            calendar.calMyPageId = calendar_dto.get('calMyPageId', 0)
            calendar.calSmsSstId = calendar_dto.get('calSmsSstId', 0)
            
            calendar.calParentId = calendar_dto.get('calParentId', 0)
            calendar.calRepeatEvery = calendar_dto.get('calRepeatEvery', 0)
            calendar.calRepeatType = calendar_dto.get('calRepeatType')
            calendar.calRepeatEveryType = calendar_dto.get('calRepeatEveryType')
            calendar.calRepeatDayName = calendar_dto.get('calRepeatDayName')
            calendar.calRepeatSelectedOption = calendar_dto.get('calRepeatSelectedOption', 0)

            # Java lines 1424-1442: Model date conversion
            try:
                if calendar_dto.get('start'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['start'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calStartDateTime = _convert_date(converted)
                if calendar_dto.get('end'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['end'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calEndDateTime = _convert_date(converted)
                if calendar_dto.get('calScheduleDateTime'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['calScheduleDateTime'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calScheduleDateTime = _convert_date(converted)
                if calendar_dto.get('calRepeatEndDate'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['calRepeatEndDate'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calRepeatEndDate = _convert_date(converted)
                if calendar_dto.get('calRepeatDate'):
                    converted = _convert_event_time_zone_to_user_db(calendar_dto['calRepeatDate'], calendar_dto['calTimeZone'], time_zone)
                    calendar.calRepeatDate = _convert_date(converted)
            except Exception as e:
                logger.error(f"[ memberId : {tenant_id} ] SaveReminder Error 2: {e}")

            # Java lines 1444-1450: Creation timing
            if cal_id_dto == 0:
                calendar.calCreatedDateTime = timezone.now()
                calendar.calNotification = "N"
            else:
                tmp_calendar = Calendar.objects.get(calId=cal_id_dto, calMemberId=get_client_id_by_tenant_id(tenant_id))
                calendar.calCreatedDateTime = tmp_calendar.calCreatedDateTime

            calendar.calUpdatedDateTime = timezone.now()
            calendar.save()
            cal_id = calendar.calId
            
            # Java lines 1455-1457: Reminder notification
            _tenant_notification_reminder(calendar)

            # Java lines 1459-1515: Repeat Functionality
            if calendar.calRepeatType != "donotrepeat":
                if cal_id_dto == 0:
                    repeat_every_type = calendar.calRepeatEveryType
                    if repeat_every_type == "year":
                        _repeat_every_type_year_fun(tenant_id, cal_id, "", "reminder")
                    elif repeat_every_type == "month":
                        _repeat_every_type_month_fun(tenant_id, cal_id, "", "reminder")
                    elif repeat_every_type == "day":
                        _repeat_every_type_day_fun(tenant_id, cal_id, "", "reminder")
                    elif repeat_every_type == "week":
                        _repeat_every_type_week_fun(tenant_id, cal_id, "", "reminder")
                else:
                    if calendar_dto.get('editAll') == "Y":
                        # Java lines 1476-1482: Fetch original records
                        main_record = Calendar.objects.get(calId=cal_id, calMemberId=get_client_id_by_tenant_id(tenant_id))
                        if calendar.calParentId > 0:
                            cal_list = list(Calendar.objects.filter(Q(calId=calendar.calId) | Q(calId=calendar.calParentId) | Q(calParentId=calendar.calParentId), calMemberId=get_client_id_by_tenant_id(tenant_id)))
                        else:
                            cal_list = list(Calendar.objects.filter(Q(calId=calendar.calId) | Q(calParentId=calendar.calId), calMemberId=get_client_id_by_tenant_id(tenant_id)))
                        
                        for cal_item in cal_list:
                            # Java lines 1485-1496: Update fields from main_record
                            cal_item.calTitle = main_record.calTitle
                            cal_item.calDescription = main_record.calDescription
                            cal_item.calAllDay = main_record.calAllDay
                            cal_item.calTimeZone = main_record.calTimeZone
                            cal_item.calAttendees = main_record.calAttendees
                            cal_item.calNumbers = main_record.calNumbers
                            cal_item.calRepeatEvery = main_record.calRepeatEvery
                            cal_item.calRepeatType = main_record.calRepeatType
                            cal_item.calRepeatEveryType = main_record.calRepeatEveryType
                            cal_item.calRepeatDayName = main_record.calRepeatDayName
                            cal_item.calRepeatSelectedOption = main_record.calRepeatSelectedOption
                            cal_item.calUpdatedDateTime = main_record.calUpdatedDateTime
                            
                            # Reminder specific fields
                            cal_item.calReminderSubject = main_record.calReminderSubject
                            cal_item.calReminderType = main_record.calReminderType
                            cal_item.calMyPageId = main_record.calMyPageId
                            cal_item.calSmsSstId = main_record.calSmsSstId

                            # Java lines 1498-1504: update time portion
                            if cal_item.calStartDateTime and main_record.calStartDateTime:
                                cal_item.calStartDateTime = cal_item.calStartDateTime.replace(
                                    hour=main_record.calStartDateTime.hour, 
                                    minute=main_record.calStartDateTime.minute,
                                    second=main_record.calStartDateTime.second
                                )
                            if cal_item.calEndDateTime and main_record.calEndDateTime:
                                cal_item.calEndDateTime = cal_item.calEndDateTime.replace(
                                    hour=main_record.calEndDateTime.hour, 
                                    minute=main_record.calEndDateTime.minute,
                                    second=main_record.calEndDateTime.second
                                )
                            
                            cal_item.save()
                            # Java line 1509: Reminder notification
                            _tenant_notification_reminder(cal_item)

            message = "Add Reminder Successfully" if cal_id_dto == 0 else "Update Reminder Successfully"
            return api_response(200, message, {"calId": cal_id})
        except CalendarSetup.DoesNotExist:
            return api_response(404, "Tenant not found.")
        except Exception as e:
            logger.error(f"[ memberId : {tenant_id} ] SaveReminder Error 4: {e}")
            logger.error(traceback.format_exc())
            return api_response(500, f"Internal server error: {str(e)}")
    return api_response(400, "Invalid data.", serializer.errors)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def sms_status_url_send_sms_calendar_reminder(request):
    try:
        response_dict = request.data
        if response_dict:
            data_obj = response_dict.get("data", {})
            payload = data_obj.get("payload", {})
            sms_sid = payload.get("id", "")
            to_list = payload.get("to", [])
            if to_list:
                final_json_object = to_list[0]
                status = final_json_object.get("status", "")

                find_data = CalendarReminderSmsDetails.objects.filter(crsdSid=sms_sid).first()
                if find_data:
                    find_data.crsdStatus = status
                    find_data.save()
    except Exception as e:
        logger.error(f"SmsStatusUrlSendSmsCalendarReminder Error : {e}")

    return api_response(200, "Sms Status.", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_default_calendar(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id)).update(csDefaultCalendar='N')
        if request.data['defaultCalendar'] == "google":
            CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="GOOGLE").update(csDefaultCalendar='Y')
        else:
            CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType="MICROSOFT").update(csDefaultCalendar='Y')
        return api_response(200, "Save Default Calendar Successfully.")
    except CalendarSetup.DoesNotExist:
        return api_response(404, "Tenant not found.")