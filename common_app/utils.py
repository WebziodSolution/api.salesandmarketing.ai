import json
from auth_app.models import Tenants, TenantDetails
from common_app.models import Userlist, Groups, CountrySetting, CampaignTransaction, Plans, TenantPlanDetails, Clients, PhoneNumbers
from rest_framework.response import Response
from datetime import datetime, date, timedelta
from django.utils import timezone
import base64
import re
from django.db.models import Count, Q, Sum
import logging
import requests
from urllib.parse import urljoin
from dateutil.relativedelta import relativedelta
import os
import random
import string
from zoneinfo import ZoneInfo
import datetime as py_datetime
import traceback
from django.conf import settings
import calendar
import math
from types import SimpleNamespace
from django.forms.models import model_to_dict

logger = logging.getLogger(__name__)

def extract_member_id_from_token(token):
    if not token:
        return 0
    try:
        parts = token.split('.')
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
            return int(json.loads(payload_json).get('memberId', 0))
    except Exception:
        pass
    return 0

def api_response(error_code, message, data=None, sendErrorAs200=False):
    if data is None:
        data = ""
    return Response({
        "status": error_code,
        "message": message,
        "result": data
    }, status=error_code if error_code >= 400 and not sendErrorAs200 else 200)

def get_final_tenant_id(tenant=None, tenant_id=None, request=None):
    """
    Returns the parent member ID if it exists, otherwise the member ID itself. 
    Mirrors CommonFunction.getFinalMemberId from Java.
    """
    if request and not tenant and not tenant_id:
        # Helper to extract from request user if authenticated
        if hasattr(request, 'user') and hasattr(request.user, 'ten_id'):
            tenant_id = request.user.ten_id

    if tenant is None and tenant_id is not None:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        if not tenant:
            return 0
            
    if tenant is None:
        return 0

    t_id = getattr(tenant, 'ten_id', 0)
    try:
        ten_parent_id = getattr(tenant, 'ten_parent_id')
        if ten_parent_id is not None and ten_parent_id > 0:
            t_id = ten_parent_id
    except Exception:
        pass
    return t_id

def remove_decimal(value):
    if not value or "." not in str(value):
        return value
    
    val_str = str(value)
    splits = val_str.split(".")
    if len(splits) > 1 and splits[1] == "00":
        return splits[0]
    return val_str

def set_file_permissions(file_path, decoded_bytes):
    with open(file_path, "wb") as f:
        f.write(decoded_bytes)
    
    # POSIX permissions are only applicable on Unix-like systems.
    # On Windows, we just ensure the file is written.
    if os.name != 'nt':
        try:
            os.chmod(file_path, 0o644)
        except Exception:
            pass

def save_campaign_transaction(tran_campaign_id, tran_campaign_name, tran_total_member, tran_type, tran_invoiced_id, tran_invoiced_status, tran_invoiced_date, member_id, tran_bill_type, tran_total_amount, tran_member_rate, tran_count_total_sms=None, tran_poll_form_no=None, tran_poll_to_no=None, sub_member_id=0):
    camp_tran = CampaignTransaction()
    camp_tran.tran_campaign_id = tran_campaign_id
    camp_tran.tran_campaign_name = tran_campaign_name
    camp_tran.tran_campaign_date = timezone.now()
    camp_tran.tran_total_member = tran_total_member
    camp_tran.tran_type = tran_type
    camp_tran.tran_invoiced_id = tran_invoiced_id
    camp_tran.tran_invoiced_status = tran_invoiced_status
    camp_tran.tran_invoiced_date = tran_invoiced_date
    camp_tran.ct_client_id = member_id
    camp_tran.tran_bill_type = tran_bill_type
    camp_tran.tran_total_amount = tran_total_amount
    camp_tran.tran_member_rate = tran_member_rate
    camp_tran.tran_count_total_sms = tran_count_total_sms
    camp_tran.tran_poll_form_no = tran_poll_form_no
    camp_tran.tran_poll_to_no = tran_poll_to_no
    camp_tran.save()

def total_uninvoiced_amt(tenant_id):
    amt = 0
    previous_uninvoiced_price = 0
    trans_types = ["sms", "sms number", "sms polling", "sms polling number", "language translation"]
    
    campaign_transactions = CampaignTransaction.objects.filter(
        ct_client_id=get_client_id_by_tenant_id(tenant_id),
        tran_invoiced_status='uninvoiced', 
        tran_bill_type=0
    )
    
    for ct in campaign_transactions:
        tran_type = (ct.tran_type or "").lower()
        if tran_type == "previous uninvoiced":
            previous_uninvoiced_price += (ct.tran_total_amount or 0)
        
        if tran_type in trans_types:
            amt += (ct.tran_total_amount or 0)
        else:
            amt += ((ct.tran_total_member or 0) * (ct.tran_member_rate or 0))
            
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        country_id = getattr(tenant, 'ten_country', "100")
        plan_id = getattr(tenant, 'td_plan_id', 1)
        
        try:
            country_setting = CountrySetting.objects.get(cnty_id=int(country_id), cnty_plan_id=plan_id)
        except CountrySetting.DoesNotExist:
            country_setting = CountrySetting.objects.filter(cnty_id=100, cnty_plan_id=2).first()
            
        cur_contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id)).count()
        
        plan = Plans.objects.get(plan_id=plan_id)
        if plan.plan_name.lower() == "pay as you grow":
            assert country_setting is not None
            amt = previous_uninvoiced_price + (cur_contacts * (country_setting.ctny_contact_per_price or 0))
    except Exception:
        pass
        
    return amt

def clean_me_number(val):
    if not val:
        return ""
    return re.sub(r"[^A-Za-z0-9']", "", str(val))

def country_code_number(client_number, country_code):
    """
    Python port of CommonFunction.countryCodeNumber
    Ensures phone number has a + prefix and a country code.
    """
    if not client_number:
        return ""
    
    if str(client_number).startswith("+"):
        client_number = clean_me_number(client_number)
        return "+" + client_number
    else:
        client_number = clean_me_number(client_number)
        if not country_code:
            country_code = "1" # Default to USA
        return "+" + str(country_code).replace("+", "") + client_number

def display_date(date_obj):
    if not date_obj:
        return ""
    if isinstance(date_obj, datetime):
        return date_obj.strftime('%m/%d/%Y')
    if isinstance(date_obj, str):
        return date_obj
    try:
        return datetime.fromtimestamp(date_obj).strftime('%m/%d/%Y')
    except Exception:
        return str(date_obj)

def is_weekend(date_val):
    if not date_val:
        return False
    if isinstance(date_val, datetime):
        return date_val.weekday() >= 5
    if isinstance(date_val, str):
        for fmt in ('%Y-%m-%d %H:%M:%S', '%m-%d-%Y %H:%M:%S'):
            try:
                date_val = datetime.strptime(date_val, fmt)
                return date_val.weekday() >= 5
            except ValueError:
                pass
    return False

def date_time_stamp_to_display_date(timestamp_str):
    try:
        if not timestamp_str:
            return ""
        dt = datetime.fromtimestamp(int(timestamp_str) / 1000.0)
        return dt.strftime('%m-%d-%Y %H:%M:%S')
    except:
        return timestamp_str

def nl2br(string_data):
    if not string_data:
        return ""
    return string_data.replace("\n", "<br />")

def strip_slashes(s):
    if not s:
        return ""
    return s.replace("\\", "")


def remove_whitespace(data):
    # Port of Java removeWhitespace logic: data.replaceAll("/(?<=>)\s+(?=<)/", "")
    # Note: Delimiters '/' are omitted as they are likely from a different regex engine notation.
    return re.sub(r'(?<=>)\s+(?=<)', '', data)

def cron_send_campaign_content_remove(content):
    if not content:
        return ""
    
    data = remove_whitespace(content)
    
    # Map of replacements from Java cronSendCampaignContentRemove
    replacements = [
        ("display: none;", "display: none !important;max-width: 0px !important;max-height: 0px !important;overflow:hidden !important;"),
        ("display:none;", "display: none !important;max-width: 0px !important;max-height: 0px !important;overflow:hidden !important;"),
        ("Drop Content Blocks Here", ""),
        ('<div class="mojoMcContainerEmptyMessage" style="display: none;"></div>', ""),
        ("Drop an image here", ""),
        ("<br>or", ""),
        ('<td><div class="imagePlaceholder"><img class="mojoImageItemIcon" src="images/icons/empty_image-72.png"><div data-dojo-attach-point="uploadText"><span></span></div><div><input data-dojo-attach-point="browseBtn" class="button-small p3" value="browse" type="button"></div></div></td>', "")
    ]
    
    for old, new in replacements:
        data = data.replace(old, new)
        
    return data

def get_browser_name(agent):
    if not agent:
        return "Others"
    if "Firefox" in agent:
        return "Firefox"
    elif "MSIE" in agent or "EIE" in agent or "Edg" in agent:
        return "IE"
    elif "iPhone" in agent:
        return "iPhone"
    elif "iPad" in agent:
        return "iPad"
    elif "Android" in agent:
        if "Mobile" in agent:
            return "Android Phone"
        return "Android Tab"
    elif "Chrome" in agent:
        return "Chrome"
    elif "Safari" in agent:
        return "Safari"
    elif "AIR" in agent:
        return "Air"
    elif "Fluid" in agent:
        return "Fluid"
    else:
        return "Others"

def get_ran_str(length=16):
    """
    Python port of CommonFunction.getRanStr
    Generates a random alphanumeric string of the specified length.
    """
    characters = string.digits + string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(characters) for _ in range(length))


def clean_me(val):
    """
    Python port of CommonFunction.cleanMe
    Removes characters not in [A-Za-z0-9/@.:%,_'-].
    """
    if not val:
        return ""
    val = re.sub(r"[^A-Za-z0-9/@.:%,_'\-]", " ", str(val))
    return val


def last_characters(input_str, no):
    """
    Python port of CommonFunction.lastCharaters
    Returns the last `no` characters of input_str.
    """
    if not input_str:
        return ""
    if len(input_str) > no:
        return input_str[-no:]
    return input_str


def sms_campaign_price_list_per(total_sms, text_im, country_setting):
    """
    Python port of CommonFunction.smsCampaignPriceListPer
    """
    pc = 0.0
    if total_sms > 0 and country_setting:
        if text_im == "image":
            pc = getattr(country_setting, 'cnty_mms_per_price', 0) or 0
        else:
            pc = getattr(country_setting, 'cnty_sms_per_price', 0) or 0
    return pc


def add_one_month():
    """
    Python port of CommonFunction.addOneMonth
    Returns ISO date string for 1 month from today.
    """
    return (date.today() + relativedelta(months=1)).isoformat()


def convert_event_timezone_to_user(date_str, from_tz, to_tz):
    try:
        if not from_tz or from_tz == to_tz or not to_tz:
            return date_str
        
        # Mapping for deprecated or inconsistent names
        tz_map = {"Asia/Calcutta": "Asia/Kolkata", "Calcutta": "Asia/Kolkata", "Kolkata": "Asia/Kolkata"}
        f_tz = str(tz_map.get(from_tz, from_tz))
        t_tz = tz_map.get(to_tz, to_tz)

        fmt = "%m/%d/%Y %H:%M:%S"
        # Relax format if necessary (Java uses MM/dd/yyyy)
        try:
            dt = datetime.strptime(date_str, fmt)
        except ValueError:
            fmt = "%m-%d-%Y %H:%M:%S"
            dt = datetime.strptime(date_str, fmt)
            
        dt_localized = dt.replace(tzinfo=ZoneInfo(f_tz))
        dt_converted = dt_localized.astimezone(ZoneInfo(str(t_tz)))
        
        return dt_converted.strftime(fmt)
    except Exception:
        return date_str


def db_date(date_str):
    try:
        # Java: MM/dd/yyyy -> yyyy-MM-dd
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str


def db_date_time(date_str):
    try:
        # Java: handles yyyy-MM-dd HH:mm:ss or MM/dd/yyyy HH:mm:ss
        if "-" in date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
        
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, py_datetime.timezone.utc)
        return dt
    except Exception:
        return date_str


def db_date_time2(date_str):
    try:
        # Java: MM/dd/yyyy hh:mm aa -> yyyy-MM-dd HH:mm:ss
        dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return date_str


def display_db_date_time_to_time(date_str):
    try:
        # Java: yyyy-MM-dd HH:mm:ss -> HH:mm:ss
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%H:%M:%S")
    except Exception:
        return ""


def date_time_zone_to_time(date_str):
    try:
        # Java: EEE MMM d HH:mm:ss z yyyy -> HH:mm:ss
        # Python's %z is a bit different, but we can try to parse the default Java Date.toString()
        # "Tue Mar 10 21:43:30 IST 2026"
        # Since 'IST' might not be parsed by %Z easily, we might need to strip it if it fails
        date_str = re.sub(r'\s[A-Z]{3,4}\s', ' ', date_str)
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
        return dt.strftime("%H:%M:%S")
    except Exception:
        return ""


def slot_list(minutes, first_time, second_time):
    try:
        fmt = "%H:%M:%S"
        date_obj1 = datetime.strptime(first_time, fmt)
        date_obj2 = datetime.strptime(second_time, fmt)
        
        slots = []
        current = date_obj1
        last_slot = first_time
        
        while current < date_obj2:
            slots.append(current.strftime(fmt))
            last_slot = current.strftime(fmt)
            current += timedelta(minutes=minutes)
            
        if second_time == "24:00:00":
            if current.strftime(fmt) != "00:00:00":
                if last_slot in slots:
                    slots.remove(last_slot)
        else:
            if current.strftime(fmt) != second_time:
                if last_slot in slots:
                    slots.remove(last_slot)
        return slots
    except Exception:
        return []


def remaining_time(minutes, first_time, second_time):
    try:
        fmt = "%H:%M:%S"
        
        # Handle 24:00:00 by treating it as tomorrow 00:00:00
        def parse_time(t_str):
            if t_str == "24:00:00":
                return datetime.strptime("00:00:00", fmt) + timedelta(days=1)
            return datetime.strptime(t_str, fmt)

        date_obj1 = parse_time(first_time)
        date_obj2 = parse_time(second_time)
        
        if date_obj2 <= date_obj1:
            date_obj2 += timedelta(days=1)

        current = date_obj1
        last_slot_str = first_time
        while current < date_obj2:
            last_slot_str = current.strftime(fmt)
            current += timedelta(minutes=minutes)
        
        t1 = parse_time(last_slot_str)
        t2 = parse_time("24:00:00")
        
        difference = (t2 - t1).total_seconds() / 60
        
        if difference > minutes:
            add_minutes = difference - minutes
        else:
            add_minutes = minutes - difference
            
        new_time = (datetime.strptime("00:00:00", fmt) + timedelta(minutes=add_minutes)).strftime(fmt)
        return new_time
    except Exception:
        return "00:00:00"


def remove_book_slot(minutes, slot_list_data, start_time, end_time):
    try:
        fmt = "%H:%M:%S"
        
        # Java logic: tries to remove slot if it matches exactly, or find interval
        if start_time in slot_list_data:
            slot_list_data.remove(start_time)
        else:
            count = len(slot_list_data)
            for i in range(count - 1):
                t1 = datetime.strptime(slot_list_data[i], fmt)
                t2 = datetime.strptime(slot_list_data[i+1], fmt)
                x = datetime.strptime(start_time, fmt)
                if t1 < x < t2:
                    slot_list_data.remove(slot_list_data[i])
                    break
        
        t_start = datetime.strptime(start_time, fmt)
        t_end = datetime.strptime(end_time, fmt)
        
        free_slots = []
        for slot in slot_list_data:
            t_slot = datetime.strptime(slot, fmt)
            if t_start < t_slot < t_end:
                continue
            else:
                free_slots.append(slot)
        return free_slots
    except Exception:
        return slot_list_data


def db_date_to_display_date_time(date_str):
    try:
        # Java: yyyy-MM-dd HH:mm:ss -> hh:mma - EEEE, dd MMMM yyyy
        dt = parse_date_time(date_str)
        if not dt:
             return date_str
        return dt.strftime("%I:%M%p - %A, %d %B %Y").replace("AM", "am").replace("PM", "pm")
    except Exception:
        traceback.print_exc()
        return ""


def db_date_to_display_date(date_str):
    try:
        date_str = re.sub(r'\s[A-Z]{3,4}\s', ' ', date_str)
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
        return dt.strftime("%B, %d %Y")
    except Exception:
        return ""


def db_date_to_display_time(date_str):
    try:
        date_str = re.sub(r'\s[A-Z]{3,4}\s', ' ', date_str)
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
        return dt.strftime("%I:%M%p").lstrip('0').replace("AM", "am").replace("PM", "pm")
    except Exception:
        return ""


def day_name(date_str):
    try:
        # Java: MM/dd/yyyy -> EEEE
        dt = parse_date_time(date_str)
        if not dt:
            # Fallback for just date if parse_date_time (which expects time) fails
            if "-" in date_str:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            else:
                dt = datetime.strptime(date_str[:10], "%m/%d/%Y")
        return dt.strftime("%A")
    except Exception:
        return ""


def check_big_first_time(first_time, second_time):
    try:
        fmt = "%H:%M:%S"
        return datetime.strptime(first_time, fmt) > datetime.strptime(second_time, fmt)
    except Exception:
        return False


def current_time(time_zone):
    try:
        # Mapping for deprecated or inconsistent names
        tz_map = {"Asia/Calcutta": "Asia/Kolkata", "Calcutta": "Asia/Kolkata", "Kolkata": "Asia/Kolkata"}
        tz_name = tz_map.get(time_zone, time_zone)
        
        now_utc = datetime.now(ZoneInfo('UTC'))
        now_tz = now_utc.astimezone(ZoneInfo(str(tz_name)))
        return now_tz.strftime("%H:%M:%S")
    except Exception:
        return ""


def convert_event_timezone_to_user_db(date_str, from_tz, to_tz):
    try:
        if not from_tz or from_tz == to_tz or not to_tz:
            return date_str
        
        # Mapping for deprecated or inconsistent names
        tz_map = {"Asia/Calcutta": "Asia/Kolkata", "Calcutta": "Asia/Kolkata", "Kolkata": "Asia/Kolkata"}
        f_tz = str(tz_map.get(from_tz, from_tz))
        t_tz = tz_map.get(to_tz, to_tz)

        dt = None
        # Try multiple formats common in the application
        for pattern in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m-%d-%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(date_str, pattern)
                break
            except ValueError:
                continue
        
        if not dt:
            raise ValueError(f"Time data '{date_str}' does not match any supported format")
        
        # Handle already aware or naive
        dt_localized = dt.replace(tzinfo=ZoneInfo(f_tz))
        dt_converted = dt_localized.astimezone(ZoneInfo(str(t_tz)))
        
        return dt_converted.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        logger.error(f"convert_event_timezone_to_user_db Error (from={from_tz}, to={to_tz}): {e}")
        return date_str
def parse_date_time(date_str):
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        return date_str
    
    date_str = str(date_str).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m-%d-%Y %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y"
    ]
    
    dt = None
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue
            
    if dt:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, py_datetime.timezone.utc)
        return dt
    return None

def check_duplicate_records(group_id, client_id):
    duplicate_records = "N"

    # 1. Logic for getEmailIdByGroupId
    has_duplicate_emails = (
        Userlist.objects.filter(
            groupId=group_id,
            memberId=client_id,
            status='Subscribed',
            badEmail__in=['N', 'B', 'D']
        )
        .filter(Q(optId__isnull=True) | Q(optId=0))
        .exclude(Q(email__isnull=True) | Q(email=''))
        .values('email')
        .annotate(email_count=Count('memberId'))
        .filter(email_count__gt=1)
        .exists()  # We only need to know IF they exist, no need to pull the list
    )
    
    if has_duplicate_emails:
        duplicate_records = "Y"
    else:
        # 2. Logic for getPhoneNumberByGroupId
        has_duplicate_phones = (
            Userlist.objects.filter(
                groupId=group_id,
                memberId=client_id,
                badPhoneNumber='N'
            )
            .filter(Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))
            .filter(Q(optId__isnull=True) | Q(optId=0))
            .exclude(Q(phoneNumber__isnull=True) | Q(phoneNumber=''))
            .values('phoneNumber')
            .annotate(ulPhone_count=Count('memberId'))
            .filter(ulPhone_count__gt=1)
            .exists()
        )
        if has_duplicate_phones:
            duplicate_records = "Y"

    # 3. Update the Group record
    Groups.objects.filter(grpId=group_id).update(grpDuplicateRecordsYn=duplicate_records)

def check_type_email(group_id, client_id):
    type_email = "unverified"
    # Ported from CommonServicesImpl.checkTypeEmail
    count = Userlist.objects.filter(memberId=client_id, groupId=group_id).exclude(Q(email__isnull=True) | Q(email='')).count()
    if count > 0:
        count_email = Userlist.objects.filter(groupId=group_id, memberId=client_id, typeEmail='email').count()
        if count_email == 0:
            count_unverified = Userlist.objects.filter(groupId=group_id, memberId=client_id, typeEmail='unverified').count()
            if count_unverified == 0:
                type_email = "done"
            else:
                type_email = "unverified"
        else:
            type_email = "email"
    Groups.objects.filter(grpId=group_id).update(grpTypeEmail=type_email)

def check_total_member(group_id, client_id):
    count = Userlist.objects.filter(
        Q(memberId=client_id),
        Q(groupId=group_id),
        Q(status='Subscribed'),
        Q(badEmail__in=['N', 'B', 'D']),
        Q(optId=0) | Q(optId__isnull=True)
    ).count()
    Groups.objects.filter(grpId=group_id).update(grpTotalMember=count)

def country_setting_by_country_id_and_plan_id(country_id, plan_id):
    # Oracle uses 'FETCH FIRST 1 ROWS ONLY' instead of 'LIMIT 1'
    # Use :1, :2 placeholders for Oracle native style, 
    # though Django's raw() often translates %s for you.
    query = """
        SELECT cs.* 
        FROM COUNTRY_SETTING cs
        INNER JOIN PLANS pl ON cs.CNTY_PLAN_ID = pl.PLAN_ID
        WHERE cs.CNTY_ID = %s 
          AND pl.PLAN_ID = %s 
          AND pl.PLAN_ACTIVE = 'Y' 
        FETCH FIRST 1 ROWS ONLY
    """
    
    try:
        # Execute for the specific country_id
        results = list(CountrySetting.objects.raw(query, [country_id, plan_id]))
        if results:
            return results[0]
        
        # Fallback to country_id 100
        results_fallback = list(CountrySetting.objects.raw(query, [100, plan_id]))
        return results_fallback[0] if results_fallback else None
        
    except Exception as e:
        logger.error(f"Oracle Query Error: {e}")
        return None

def minutes_convert(minutes):
    """
    Python port of CommonFunction.minutesConvert
    Converts minutes to a human-readable string (e.g., "1 hour 30 mins").
    """
    if minutes <= 0:
        return "0 min"
    if minutes < 60:
        return f"{int(minutes)} mins"

    hours = int(minutes // 60)
    rem_minutes = int(minutes % 60)

    res = f"{hours} hour" if hours == 1 else f"{hours} hours"
    if rem_minutes > 0:
        res += f" {rem_minutes} mins"
    return res


def trim_file_extension(filename):
    """
    Removes the extension from a filename.
    """
    return os.path.splitext(filename)[0]


def remove_utf8_bom(file_path):
    """
    Removes the UTF-8 BOM from a file if present.
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        if content.startswith(b'\xef\xbb\xbf'):
            with open(file_path, 'wb') as f:
                f.write(content[3:])
    except Exception:
        pass


def header_filter(header):
    """
    Python port of CommonFunction.headerFilter
    Removes special characters and spaces from header and converts to lowercase.
    """
    if not header:
        return ""
    # Java: header.toLowerCase().trim().replaceAll("[-+.^:,_]", "").replaceAll(" ", "")
    h = header.lower().strip()
    h = re.sub(r"[-+.^:,_]", "", h)
    h = h.replace(" ", "")
    return h


def header_double_quotes(header):
    """
    Python port of CommonFunction.headerDoubleQuotes
    Removes leading/trailing double quotes.
    """
    if not header:
        return ""
    return header.strip('"')


def uc_first(s):
    """
    Upper case the first letter of the string.
    """
    if not s:
        return ""
    return s[0].upper() + s[1:]

def display_date_time(timestamp):
    if not timestamp:
        return ""
    if isinstance(timestamp, datetime):
        return timestamp.strftime('%m/%d/%Y %H:%M:%S')
    if isinstance(timestamp, str):
        try:
            # Handle ISO format from Google API
            return datetime.strptime(timestamp[:19], '%Y-%m-%dT%H:%M:%S').strftime('%m/%d/%Y %H:%M:%S')
        except:
            return timestamp
    try:
        return datetime.fromtimestamp(timestamp).strftime('%m/%d/%Y %H:%M:%S')
    except Exception:
        return str(timestamp)


def add_slashes(text):
    if not text:
        return ""
    
    res = ""
    for char in str(text):
        if char == '"':
            res += "\\\""
        elif char == "'":
            res += "\\\'"
        elif char == "\\":
            res += "\\\\"
        elif char == "\n":
            res += "\\n"
        elif char == "{":
            res += "\\{"
        elif char == "}":
            res += "\\}"
        else:
            res += char
    return res
def get_image_content(url):
    """
    Fetches file content from a URL, but first checks if the URL points to the local EAS drive.
    If it does, it reads the file directly from the filesystem to avoid DNS/network issues.
    """
    try:
        # Check if settings required for local mapping are present
        if not hasattr(settings, 'IMAGE_SITE_URL') or not hasattr(settings, 'EAS_DRIVE_NAME') or not hasattr(settings, 'EAS_DRIVE_PATH'):
            response = requests.get(url)
            response.raise_for_status()
            return response.content
            
        eas_url_prefix = f"{settings.IMAGE_SITE_URL}{settings.EAS_DRIVE_NAME}/"
        
        if url.startswith(eas_url_prefix):
            # Extract the relative path after "easdrive/"
            relative_path = url[len(eas_url_prefix):]
            # Construct the local path
            local_path = os.path.join(settings.EAS_DRIVE_PATH, relative_path)
            # normalize for the OS (handles both / and \ accurately)
            local_path = os.path.normpath(local_path)
            
            if os.path.exists(local_path):
                try:
                    with open(local_path, 'rb') as f:
                        return f.read()
                except Exception as file_err:
                    logger.warning(f"Failed to read local file {local_path}: {str(file_err)}. Falling back to URL.")
            else:
                logger.warning(f"Local file does not exist at {local_path}. URL prefix matched but filesystem path did not. Falling back to URL.")
        
        # Fallback to HTTP request
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"Error fetching content from {url}: {str(e)}")
        try:
            return requests.get(url).content
        except:
            raise e

def get_split_date(date_str):
    """
    Returns a dict with day (weekday index 1-7), week (of month), month (1-12), year.
    Mirrors CommonFunction.getSplitDate in Java.
    """
    if not date_str:
        return {}
    try:
        if " " in date_str:
            date_str = date_str.split(" ")[0]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = dt.isoweekday()  # 1=Monday, 7=Sunday
        month = dt.month
        year = dt.year
        # Week of month calculation
        first_day = dt.replace(day=1)
        dom = dt.day
        adjusted_dom = dom + first_day.weekday()
        week = (adjusted_dom - 1) // 7 + 1
        
        return {
            "day": weekday,
            "week": week,
            "month": month,
            "year": year
        }
    except Exception:
        return {}

def get_weekday_date(year, month, weekday, week):
    """
    Returns the date string (yyyy-MM-dd) of the Nth occurrence of a weekday in a month.
    weekday: 1=Monday, 7=Sunday
    week: 1=First, 2=Second, etc.
    Mirrors CommonFunction.getDateTime in Java.
    """
    month_calendar = calendar.monthcalendar(year, month)
    # weekday is 1-7 (Mon-Sun), calendar.monthcalendar weekday is 0-6 (Mon-Sun)
    py_weekday = weekday - 1
    
    occurrences = []
    for week_list in month_calendar:
        day = week_list[py_weekday]
        if day != 0:
            occurrences.append(day)
            
    if week <= len(occurrences):
        return f"{year}-{month:02d}-{occurrences[week-1]:02d}"
    return f"{year}-{month:02d}-{occurrences[-1]:02d}"

def get_last_weekday_date(year, month, weekday):
    """
    Returns the date string (yyyy-MM-dd) of the last occurrence of a weekday in a month.
    Mirrors CommonFunction.getLastWeek in Java.
    """
    month_calendar = calendar.monthcalendar(year, month)
    py_weekday = weekday - 1
    
    last_day = 0
    for week_list in reversed(month_calendar):
        day = week_list[py_weekday]
        if day != 0:
            last_day = day
            break
            
    return f"{year}-{month:02d}-{last_day:02d}"

def get_user_db_timezone():
    return getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')

def date_object_to_db_date(date_obj):
    if not date_obj:
        return ""
    if isinstance(date_obj, datetime):
        return date_obj.strftime('%Y-%m-%d')
    return str(date_obj)

def date_object_to_display_date(date_obj):
    if not date_obj:
        return ""
    if isinstance(date_obj, datetime):
        return date_obj.strftime('%m/%d/%Y %H:%M:%S')
    return str(date_obj)

def convert_time_zone_to_db_date(date_str):
    """
    Python port of CommonFunction.convertTimeZoneToDbDate
    Handles ISO 8601 strings like 2026-04-15T12:00:00.0000000Z
    Returns yyyy-MM-dd HH:mm:ss
    """
    if not date_str:
        return ""
    try:
        # Outlook often returns ISO format
        dt_str = date_str.replace('Z', '')
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str[:19])
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        return date_str
    except Exception:
        return date_str

def change_timezone_name(tz_name):
    """
    Python port of CommonFunction.changeTimeZoneName
    Maps common timezone names to standardized ones.
    """
    if not tz_name:
        return "UTC"
    
    tz_map = {
        "India Standard Time": "Asia/Kolkata",
        "Pacific Standard Time": "America/Los_Angeles",
        "Pacific Daylight Time": "America/Los_Angeles",
        "Eastern Standard Time": "America/New_York",
        "Eastern Daylight Time": "America/New_York",
        "Central Standard Time": "America/Chicago",
        "Central Daylight Time": "America/Chicago",
        "Mountain Standard Time": "America/Denver",
        "Mountain Daylight Time": "America/Denver"
    }
    return tz_map.get(tz_name, tz_name)

def extract_image_urls_from_html(tree, base_url):
    image_urls = []
    for img in tree.xpath('//img'):
        image_url = img.get('src')
        if not image_url:
            continue

        ext = image_url.split('.')[-1].lower() if '.' in image_url else ""
        if (image_url.startswith('http://') or image_url.startswith('https://')) and 'data:' not in image_url and ext != 'svg':
            image_urls.append(image_url)
        elif 'data:' in image_url:
            pass
        elif ext != 'svg':
            try:
                full_url = urljoin(base_url, image_url.lstrip('\'".'))
                image_urls.append(full_url)
            except Exception:
                pass
    return image_urls

def extract_image_urls_from_style_tags(tree, base_url):
    image_urls = []
    for style in tree.xpath('//style'):
        css_text = style.text or ""
        lines = css_text.splitlines()
        for line in lines:
            if 'background' in line and 'url(' in line:
                try:
                    match = re.search(r'url\((.*?)\)', line)
                    if match:
                        image_url = match.group(1).strip(' \'"')
                        if not image_url:
                            continue
                        ext = image_url.split('.')[-1].lower() if '.' in image_url else ""
                        if (image_url.startswith('http://') or image_url.startswith('https://')) and 'data:' not in image_url and ext != 'svg':
                            image_urls.append(image_url)
                        elif 'data:' in image_url:
                            pass
                        elif ext != 'svg' and ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                            full_url = urljoin(base_url, image_url.lstrip('\'".'))
                            image_urls.append(full_url)
                except Exception:
                    pass
    return image_urls

def extract_image_urls_from_css_files(tree, base_url):
    image_urls = []
    for link in tree.xpath('//link[@rel="stylesheet"]'):
        css_url = link.get('href')
        if not css_url:
            continue
        if not (css_url.startswith('http://') or css_url.startswith('https://')):
            css_url = urljoin(base_url, css_url)

        try:
            resp = requests.get(css_url, timeout=5)
            if resp.status_code == 200:
                css_content = resp.text
                lines = css_content.splitlines()
                for line in lines:
                    if 'background' in line and 'url(' in line:
                        match = re.search(r'url\((.*?)\)', line)
                        if match:
                            image_url = match.group(1).strip(' \'"')
                            if not image_url:
                                continue
                            ext = image_url.split('.')[-1].lower() if '.' in image_url else ""
                            if (image_url.startswith('http://') or image_url.startswith('https://')) and 'data:' not in image_url and ext != 'svg':
                                image_urls.append(image_url)
                            elif 'data:' in image_url:
                                pass
                            elif ext != 'svg' and ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                                full_url = urljoin(base_url, image_url.lstrip('\'".'))
                                image_urls.append(full_url)
        except Exception:
            pass
    return image_urls

def extract_background_image_urls(style_attribute, base_url):
    image_urls = []

    regex = r"(?i)background(?:-image)?\s*:\s*url\(['\"]?(.*?)['\"]?\)"
    matches = re.finditer(regex, style_attribute)

    for match in matches:
        image_url = match.group(1)

        if "." in image_url:
            extension = image_url.split(".")[-1].lower()
        else:
            extension = ""

        if image_url == "":
            pass

        elif (
            ("http://" in image_url or "https://" in image_url)
            and "data:" not in image_url
            and extension != "svg"
        ):
            image_urls.append(image_url)

        elif "data:" in image_url:
            pass

        elif (
            extension != "svg"
            and extension in ["jpg", "jpeg", "png", "gif", "webp"]
        ):
            cleaned_url = re.sub(r"^['\".]*", "", image_url)
            image_urls.append(urljoin(base_url, cleaned_url))

    return image_urls

def extract_image_urls_from_style_attr(tree, base_url):
    image_urls = []
    for element in tree.xpath('//*[@style]'):
        style_attr = element.get('style')
        if style_attr:
            image_urls.extend(extract_background_image_urls(style_attr, base_url))
    return image_urls


def extract_classes_and_ids_from_html(html_content):
    classes = set()
    ids = set()
    for match in re.finditer(r'class="([^"]*)"', html_content):
        for cls in match.group(1).split():
            classes.add("." + cls)
    for match in re.finditer(r'id="([^"]*)"', html_content):
        ids.add("#" + match.group(1))
    return list(classes | ids)

def extract_colors_form_css_text(css_text, selector):
    color_set = set()
    escaped_selector = re.escape(selector)
    pattern = re.compile(escaped_selector + r'\s*{([^}]*)}')
    for match in pattern.finditer(css_text):
        properties_text = match.group(1).strip()
        color_set.update(extract_properties(properties_text))
    return list(color_set)

def extract_properties(properties_text):
    color_list = []
    pattern = re.compile(r'([\w-]+)\s*:\s*([^;]+)')
    for match in pattern.finditer(properties_text):
        prop_name = match.group(1).strip()
        prop_val = match.group(2).strip()
        if prop_name == "background-color" or prop_name == "color":
            if "var(" not in prop_val and "color" not in prop_val:
                color_list.append(prop_val.replace(" !important", "").replace("!important", ""))
    return color_list

def extract_colors_from_html(html_content):
    color_list = set()
    selectors = extract_classes_and_ids_from_html(html_content)
    for selector in selectors:
        color_list.update(extract_colors_form_css_text(html_content, selector))
    return color_list

def extract_colors_from_css_file(tree, html_content, base_url):
    colors = set()
    link_elements = tree.xpath('//link[@rel="stylesheet"]')
    selectors = extract_classes_and_ids_from_html(html_content)
    for link in link_elements:
        try:
            css_url = link.get('href')
            if not css_url: continue
            if not (css_url.startswith('http') or css_url.startswith('https')):
                css_url = urljoin(base_url, css_url)

            resp = requests.get(css_url, timeout=5)
            if resp.status_code == 200:
                css_content = resp.text
                for selector in selectors:
                    colors.update(extract_colors_form_css_text(css_content, selector))
        except Exception:
            pass
    return colors


def upgrade_plan(total_contact_uploaded, cnty_id, tenant_id, current_plan_id, sub_member_id=0):
    try:
        plan = Plans.objects.filter(plan_id=current_plan_id, plan_active='Y').first()
        if not plan:
            return

        plan_name = plan.plan_name.lower() if plan.plan_name else ""
        if (current_plan_id not in [1, 2] and
                plan_name not in ["free", "pay as you go", "pay as you grow"]):

            current_plan = country_setting_by_country_id_and_plan_id(cnty_id, current_plan_id)
            if not current_plan:
                return

            try:
                agg = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenant_id), tran_type="additional contacts", tran_invoiced_status='uninvoiced').aggregate(
                    Sum('tran_total_member'))
                additional_contact = int(agg['tran_total_member__sum'] or 0)
            except Exception as ee:
                logger.error(f"[ memberId : {tenant_id} ] UpgradePlan Error : {ee}")
                additional_contact = 0

            current_plan_contacts = (current_plan.cnty_contacts_included or 0) + additional_contact

            query = """
                SELECT cs.* 
                FROM COUNTRY_SETTING cs
                INNER JOIN PLANS pl 
                    ON cs.CNTY_PLAN_ID = pl.PLAN_ID
                WHERE pl.PLAN_VISIBILITY = 'Public'
                  AND cs.CNTY_ID = %s
                  AND cs.CNTY_PLAN_ID NOT IN (%s)
                  AND cs.CNTY_CONTACTS_INCLUDED > %s
                ORDER BY cs.CNTY_CONTACTS_INCLUDED ASC
                FETCH FIRST 1 ROWS ONLY
            """
            next_plan = list(CountrySetting.objects.raw(query, [cnty_id, current_plan_id, current_plan.cnty_contacts_included]))[0]

            pen_count = 1
            plan_id_update = current_plan_id

            if next_plan and total_contact_uploaded > (next_plan.cnty_contacts_included or 0):
                plan_id_update = next_plan.cnty_plan_id

                pending_contact = total_contact_uploaded - (next_plan.cnty_contacts_included or 0)
                add_contacts_next = next_plan.cnty_additional_contacts or 1
                if pending_contact > (next_plan.cnty_contacts_included or 0):
                    pen_count = int(math.ceil(float(pending_contact) / add_contacts_next))

                for j in range(pen_count):
                    ct = CampaignTransaction(
                        tran_campaign_name="Add additional contacts",
                        tran_total_member=add_contacts_next,
                        tran_type="additional contacts",
                        tran_invoiced_status="uninvoiced",
                        ct_client_id=get_client_id_by_tenant_id(tenant_id),
                        tran_bill_type="0",
                        tran_member_rate=next_plan.cnty_additional_contacts_price or 0.0,
                        tran_total_amount=next_plan.cnty_additional_contacts_price or 0.0
                    )
                    ct.save()

                    pl = TenantPlanDetails(
                        tpd_plan_id=plan_id_update,
                        tpd_client_id=get_client_id_by_tenant_id(tenant_id),
                        tpd_added_date=datetime.now(),
                        tpd_additional_contacts=add_contacts_next
                    )
                    pl.save()
            else:
                if total_contact_uploaded > current_plan_contacts:
                    pending_contact = total_contact_uploaded - current_plan_contacts
                    add_contacts_curr = current_plan.cnty_additional_contacts or 1
                    if pending_contact > add_contacts_curr:
                        pen_count = int(math.ceil(float(pending_contact) / add_contacts_curr))

                    for j in range(pen_count):
                        ct = CampaignTransaction(
                            tran_campaign_name="Add additional contacts",
                            tran_total_member=add_contacts_curr,
                            tran_type="additional contacts",
                            tran_invoiced_status="uninvoiced",
                            ct_client_id=get_client_id_by_tenant_id(tenant_id),
                            tran_bill_type="0",
                            tran_member_rate=current_plan.cnty_additional_contacts_price or 0.0,
                            tran_total_amount=current_plan.cnty_additional_contacts_price or 0.0
                        )
                        ct.save()

                        pl = TenantPlanDetails(
                            tpd_plan_id=plan_id_update,
                            tpd_client_id=get_client_id_by_tenant_id(tenant_id),
                            tpd_added_date=datetime.now(),
                            tpd_additional_contacts=add_contacts_curr
                        )
                        pl.save()
                else:
                    plan_id_update = 0

            if plan_id_update > 0:
                TenantDetails.objects.filter(tenant__ten_id=tenant_id).update(td_plan_id=plan_id_update)

    except Exception as e:
        logger.error(f"Error in upgrade_plan: {e}")

def number_format(total_amount: float, number: int) -> str:
    return f"{total_amount:.{number}f}"

def uc_words(s):
    if not s:
        return s
    return ' '.join([word.capitalize() for word in s.split()])

def br2nl(text):
    if not text:
        return ""
    return text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

def add_month(date_obj: datetime, plus_month: int) -> datetime:
    return date_obj + relativedelta(months=plus_month)

def convert_date(date_str: str) -> datetime:
    formatter = "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(date_str, formatter)

def get_tenants(
    detail_filters=None,
    select_fields=None,
    where_conditions=None,
    exclude_conditions=None,
    return_type="first"
):
    detail_filters = detail_filters or {}
    where_conditions = where_conditions or {}
    select_fields = select_fields or {}
    exclude_conditions = exclude_conditions or {}

    queryset = Tenants.objects.select_related("details")

    filters = Q()

    # detail_filters
    for field, value in detail_filters.get("tenant", {}).items():
        filters &= Q(**{field: value})

    for field, value in detail_filters.get("tenant_details", {}).items():
        filters &= Q(**{f"details__{field}": value})

    # where_conditions
    for field, value in where_conditions.get("tenant", {}).items():
        if field == "or":
            or_filter = Q()
            for or_field, or_value in value.items():
                or_filter |= Q(**{or_field: or_value})
            filters &= or_filter
        else:
            filters &= Q(**{field: value})

    for field, value in where_conditions.get("tenant_details", {}).items():
        if field == "or":
            or_filter = Q()
            for or_field, or_value in value.items():
                or_filter |= Q(**{f"details__{or_field}": or_value})
            filters &= or_filter
        else:
            filters &= Q(**{f"details__{field}": value})

    queryset = queryset.filter(filters)

    exclude_filters = Q()
    for field, value in exclude_conditions.get("tenant", {}).items():
        exclude_filters |= Q(**{field: value})

    for field, value in exclude_conditions.get("tenant_details", {}).items():
        exclude_filters |= Q(**{f"details__{field}": value})

    if exclude_filters:
        queryset = queryset.exclude(exclude_filters)

    tenant_fields = select_fields.get("tenant", [])
    detail_fields = select_fields.get("tenant_details", [])

    results = []

    for tenant in queryset:

        row = {}

        # If select_fields not provided, return all tenant fields
        if not tenant_fields:
            tenant_fields = [
                field.name
                for field in tenant._meta.fields
            ]

        for field in tenant_fields:
            row[field] = getattr(tenant, field)

        if hasattr(tenant, "details"):

            # If select_fields not provided, return all detail fields
            if not detail_fields:
                detail_fields = [
                    field.name
                    for field in tenant.details._meta.fields
                ]

            for field in detail_fields:
                row[field] = getattr(tenant.details, field)

        results.append(row)

    if return_type == "first":
        return SimpleNamespace(**results[0]) if results else None

    return [SimpleNamespace(**row) for row in results]

def get_tenant_common_object(tenant_obj, tenant_details_obj):
    tenant = model_to_dict(tenant_obj)
    tenant_details = model_to_dict(tenant_details_obj)

    return SimpleNamespace(**{**tenant, **tenant_details})

def get_client_id_by_tenant_id(tenant_id):
    client = Clients.objects.filter(cliTenantId=tenant_id).first()
    if client:
        return client.cliId
    return 0

def get_tenant_id_by_client_id(client_id):
    client = Clients.objects.filter(cliId=client_id).first()
    if client:
        return client.cliTenantId
    return 0

def get_client_timezone(tenant_id):
    try:
        client = Clients.objects.filter(cliTenantId=tenant_id).first()
        if client:
            return client.cliTimeZone or "UTC"
        else:
            return "UTC"
    except Clients.DoesNotExist:
        return "UTC"

def get_phone_numbers_first(tenant_id, ph_how_used):
    phone_numbers = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id), phHowUsed=ph_how_used, phPhoneNumberClosed='N').order_by("pnId").first()
    if phone_numbers is not None:
        return phone_numbers
    else:
        return None