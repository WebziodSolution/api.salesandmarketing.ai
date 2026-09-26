"""
SMS Campaigns Utility Functions
Mirrors Java CommonFunction utilities for SMS campaigns
"""
import re
import logging
from datetime import datetime
import pytz
import requests
from decimal import Decimal
from common_app.models import (CountrySetting, SmsLinks, CampaignTransaction, CampaignsSmsSend)
from auth_app.models import TenantDetails
from django.conf import settings

logger = logging.getLogger(__name__)

# Configuration - set these to your actual service endpoints
TINYURL_API_ENDPOINT = "https://tinyurl.com/api/create.php"
BITLY_ACCESS_TOKEN = ""  # Set your Bitly token if using Bitly
SMS_STATUS_WEBHOOK_URL = ""  # Telnyx webhook URL
ENVIRONMENT = "PROD"  # PROD, DEV, TEST


def convert_user_timezone_to_utc(date_string, user_timezone_str):
    """
    Convert date string in user's timezone to UTC datetime
    Java: CommonFunction.convertEventTimeZoneToUser()

    Args:
        date_string: Date string format e.g. "YYYY-MM-DD HH:MM:SS" or "MM/DD/YYYY HH:MM:SS"
        user_timezone_str: Timezone string e.g. "US/Eastern"

    Returns:
        datetime object in UTC timezone
    """
    try:
        if not date_string or not user_timezone_str:
            return datetime.now(pytz.UTC)

        # Try to parse the date string with multiple formats
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(date_string, fmt)
                break
            except ValueError:
                continue
        
        if dt is None:
            # Fallback to current time if all formats fail
            logger.error(f"Failed to parse date string: {date_string}")
            return datetime.now(pytz.UTC)

        # Set the timezone to user's timezone
        user_tz = pytz.timezone(user_timezone_str)
        dt = user_tz.localize(dt)

        # Convert to UTC
        return dt.astimezone(pytz.UTC)
    except Exception as e:
        logger.error(f"Error converting timezone: {e}")
        return datetime.now(pytz.UTC)


def convert_utc_to_user_timezone(dt, user_timezone_str):
    """
    Convert UTC datetime to user's timezone for display
    Java: CommonFunction.displayDateTime()

    Args:
        dt: datetime object (should be UTC)
        user_timezone_str: User's timezone string

    Returns:
        datetime object in user's timezone
    """
    try:
        if not dt or not user_timezone_str:
            return dt

        # Ensure dt is UTC aware
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)

        # Convert to user timezone
        user_tz = pytz.timezone(user_timezone_str)
        return dt.astimezone(user_tz)
    except Exception as e:
        logger.error(f"Error converting to user timezone: {e}")
        return dt


def format_date_for_display(dt, date_format="%m/%d/%Y %H:%M:%S"):
    """
    Format datetime for display in API response (matches Spring Boot format)

    Args:
        dt: datetime object
        date_format: Format string (default: MM/DD/YYYY HH:MM:SS)

    Returns:
        Formatted date string
    """
    if not dt:
        return None  # Return None instead of empty string to match Spring Boot
    return dt.strftime(date_format)


def add_months(dt, months=1):
    """
    Add months to a datetime object
    Java: CommonFunction.addOneMonth()

    Args:
        dt: datetime object
        months: Number of months to add (default 1)

    Returns:
        datetime object with months added
    """
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return dt.replace(year=year, month=month)


def clean_phone_number(phone_no):
    """
    Remove formatting from phone number
    Java: CommonFunction.cleanMeNumber()

    Args:
        phone_no: Phone number with potential formatting

    Returns:
        Cleaned phone number (digits and + only)
    """
    if not phone_no:
        return ""
    # Remove all non-digit characters except +
    return re.sub(r'[^\d+]', '', phone_no)


def extract_urls_from_text(text):
    """
    Extract URLs from text using regex

    Args:
        text: Text content to search

    Returns:
        List of URLs found
    """
    if not text:
        return []

    # URL regex pattern from Java implementation
    url_pattern = r"(?i)\b((?:https?:\/\/|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}\/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()[]{};:'\".,<>?«»""']))"

    try:
        urls = re.findall(url_pattern, text)
        # Extract first group from regex results
        return [url[0] for url in urls if url]
    except Exception as e:
        logger.error(f"Error extracting URLs: {e}")
        return []


def convert_url_to_tiny_url(long_url):
    """
    Convert long URL to tiny URL using TinyURL API

    Args:
        long_url: Long URL to shorten

    Returns:
        Shortened URL or original URL if conversion fails
    """
    if not long_url:
        return ""

    try:
        # Use TinyURL API
        params = {'url': long_url}
        response = requests.get(TINYURL_API_ENDPOINT, params=params, timeout=5)

        if response.status_code == 200:
            tiny_url = response.text.strip()
            return tiny_url
        else:
            logger.warning(f"Failed to create tiny URL for {long_url}")
            return long_url
    except Exception as e:
        logger.error(f"Error converting URL: {e}")
        return long_url


def convert_urls_in_content(content, convert_tiny_url_yn='Y'):
    """
    Find and convert all URLs in content to tiny URLs

    Args:
        content: Text content containing URLs
        convert_tiny_url_yn: 'Y' or 'N' to enable/disable conversion

    Returns:
        Content with converted URLs and mapping dict
    """
    if convert_tiny_url_yn != 'Y' or not content:
        return content, {}

    try:
        urls = extract_urls_from_text(content)
        url_mapping = {}
        converted_content = content

        for url in urls:
            if url:
                tiny_url = convert_url_to_tiny_url(url)
                if tiny_url and tiny_url != url:
                    url_mapping[url] = tiny_url
                    converted_content = converted_content.replace(url, tiny_url)

        return converted_content, url_mapping
    except Exception as e:
        logger.error(f"Error converting URLs in content: {e}")
        return content, {}


def calculate_sms_count(content, content_type='text'):
    """
    Calculate number of SMS messages needed for content
    Java: Based on SMS character limit (160 chars for GSM, 70 for Unicode)

    Args:
        content: SMS message content
        content_type: 'text' or other type

    Returns:
        Number of SMS messages needed
    """
    if not content:
        return 0

    if content_type == 'text':
        # GSM 7-bit encoding: 160 chars per SMS, 153 chars for multipart
        # Formula: (len + 159) // 160
        content_len = len(content)
        return (content_len + 159) // 160
    else:
        # For other types (image, etc), count as 1
        return 1


def get_country_setting(tenant_id):
    """
    Get country settings for tenant (pricing, etc.)

    Args:
        tenant_id: Tenant ID

    Returns:
        CountrySetting object or default
    """
    try:
        setting = CountrySetting.objects.filter(cntyMemberId=tenant_id).first()

        if not setting:
            # Fall back to default (ID 100)
            setting = CountrySetting.objects.filter(cntyId=100).first()

        return setting
    except Exception as e:
        logger.error(f"Error getting country setting: {e}")
        return None


def calculate_sms_billing(email_ids_count, campaign_details, country_setting):
    """
    Calculate total SMS cost for campaign

    Args:
        email_ids_count: Number of recipients
        campaign_details: List of campaign detail objects
        country_setting: CountrySetting object

    Returns:
        Tuple: (total_sms_count, rate, total_amount)
    """
    try:
        total_sms_count = 0
        rate = Decimal('0.01')  # Default rate

        # Get rate from country setting
        if country_setting:
            rate = Decimal(str(country_setting.cnty_sms_per_price or 0.01))

        # Calculate total SMS count from all details
        for detail in campaign_details:
            if detail.sdType == 'text':
                sms_count = calculate_sms_count(detail.sdDetail, 'text')
            else:
                sms_count = 1
            total_sms_count += sms_count

        # Add opt-out message if enabled (will be added separately in code)
        # This is handled in the main logic, not here

        # Calculate total amount
        total_amount = Decimal(email_ids_count) * Decimal(total_sms_count) * rate

        return total_sms_count, rate, total_amount
    except Exception as e:
        logger.error(f"Error calculating SMS billing: {e}")
        return 0, Decimal('0.01'), Decimal('0')
def calculate_sms_billing_price(total_sms, content_type, country_setting):
    """
    Python port of CommonFunction.smsCampaignPriceListDisplay
    """
    if total_sms <= 0 or not country_setting:
        return 0.0
    
    if content_type == 'image':
        rate = float(country_setting.cnty_mms_per_price or 0.0)
    else:
        rate = float(country_setting.cnty_sms_per_price or 0.0)
        
    return float(total_sms) * rate


def calculate_sms_billing_rate(total_sms, content_type, country_setting):
    """
    Python port of CommonFunction.smsCampaignPriceListPer
    """
    if total_sms <= 0 or not country_setting:
        return 0.0
        
    if content_type == 'image':
        return float(country_setting.cnty_mms_per_price or 0.0)
    else:
        return float(country_setting.cnty_sms_per_price or 0.0)


def determine_campaign_status(campaign):
    """
    Determine campaign status and color for display
    Java: Complex logic from getSmsCampaignList()

    Args:
        campaign: CampaignsSms object

    Returns:
        Dict with 'status' and 'color'
    """
    status = "Draft"
    color = "#000"

    try:
        if campaign.smsStatus in [0, 1]:
            status = "Draft"
        elif campaign.smsStatus == 2:
            if campaign.scheduleType == 2:
                status = "Scheduled"
            else:
                # Check CampaignsSmsSend for readyToSms status
                send_record = CampaignsSmsSend.objects.filter(smsId=campaign.smsId).first()
                if send_record and send_record.readyToSms == 'Y':
                    status = "Sending"
                    color = "#0F5387"
                else:
                    status = "Draft"
        elif campaign.smsStatus == 4:
            status = "Delete Pending"
            color = "#fc0536"
        elif campaign.smsStatus == 3:
            status = "Completed"
            color = "#0F5387"
    except Exception as e:
        logger.error(f"Error determining campaign status: {e}")

    return {"status": status, "color": color}


def save_campaign_transaction(tran_campaign_id, tran_campaign_name, tran_total_member,
                               tran_type, tran_invoiced_id, tran_invoiced_status,
                               tran_invoiced_date, tenant_id, tran_bill_type,
                               tran_total_amount, tran_member_rate, tran_count_total_sms,
                               sub_tenant_id=0):
    """
    Save campaign transaction record for billing

    Args:
        tran_campaign_id: Campaign ID
        tran_campaign_name: Campaign name
        tran_total_member: Number of recipients
        tran_type: Transaction type (e.g., 'sms')
        tran_invoiced_id: Invoice ID (if any)
        tran_invoiced_status: Invoice status ('invoiced', 'uninvoiced')
        tran_invoiced_date: Invoice date
        tenant_id: Tenant ID
        tran_bill_type: Bill type ('0', '1', etc.)
        tran_total_amount: Total amount
        tran_member_rate: Per-unit rate
        tran_count_total_sms: Total SMS count
        sub_tenant_id: Sub-tenant ID (default 0)

    Returns:
        CampaignTransaction object or None
    """
    try:
        transaction = CampaignTransaction.objects.create(
            tran_campaign_id=tran_campaign_id,
            tran_campaign_name=tran_campaign_name,
            tran_total_member=tran_total_member,
            tran_type=tran_type,
            tran_invoiced_id=tran_invoiced_id,
            tran_invoiced_status=tran_invoiced_status,
            tran_invoiced_date=tran_invoiced_date,
            member_id=tenant_id,
            tran_bill_type=tran_bill_type,
            tran_total_amount=tran_total_amount,
            tran_member_rate=tran_member_rate,
            tran_count_total_sms=tran_count_total_sms,
            sub_member_id=sub_tenant_id,
            tran_campaign_date=datetime.now(pytz.UTC)
        )
        return transaction
    except Exception as e:
        logger.error(f"Error saving campaign transaction: {e}")
        return None


def store_sms_link(campaign_id, original_url, tiny_url):
    """
    Store URL mapping for link tracking

    Args:
        campaign_id: SMS campaign ID
        original_url: Original long URL
        tiny_url: Shortened URL

    Returns:
        SmsLinks object or None
    """
    try:
        link = SmsLinks.objects.create(
            campId=campaign_id,
            campLink=original_url,
            linkUrl=tiny_url,
            linkCount=0
        )
        return link
    except Exception as e:
        logger.error(f"Error storing SMS link: {e}")
        return None


def get_sms_count_from_details(campaign_details, include_opt_out=False):
    """
    Calculate total SMS count from campaign details

    Args:
        campaign_details: List of CampaignSmsDetails objects
        include_opt_out: Whether to include opt-out message count

    Returns:
        Total SMS count
    """
    total_count = 0

    for detail in campaign_details:
        if detail.sdType == 'text':
            count = calculate_sms_count(detail.sdDetail, 'text')
        else:
            count = 1
        total_count += count

    # Add 1 for opt-out message if needed
    if include_opt_out:
        total_count += 1

    return total_count


def get_telnyx_webhooks_config():
    """
    Get Telnyx webhook configuration URLs from settings

    Returns:
        Dict with webhook URLs
    """
    return {
        'sms_status_url': getattr(settings, 'TELNYX_SMS_STATUS_URL', SMS_STATUS_WEBHOOK_URL),
        'sms_reply_url': getattr(settings, 'TELNYX_SMS_REPLY_URL', ''),
        'environment': getattr(settings, 'ENVIRONMENT', ENVIRONMENT),
        'backend_url': getattr(settings, 'SITE_URL_BACKEND', ''),
    }


def format_phone_number(phone_no, country_code="+1"):
    """
    Format phone number with country code

    Args:
        phone_no: Phone number
        country_code: Country code (default +1 for US)

    Returns:
        Formatted phone number
    """
    if not phone_no:
        return ""

    cleaned = clean_phone_number(phone_no)

    # If already has country code, return as is
    if cleaned.startswith('+'):
        return cleaned

    # Add country code
    return country_code + cleaned

def format_sms_count_for_display(sms_count):
    """
    Format SMS count for API response

    Args:
        sms_count: Number of SMS messages

    Returns:
        Formatted string
    """
    return f"{sms_count} SMS" if sms_count != 1 else "1 SMS"


def validate_sms_campaign_data(campaign_data):
    """
    Validate SMS campaign data before saving

    Args:
        campaign_data: Campaign data dict

    Returns:
        Tuple: (is_valid, error_message)
    """
    errors = []

    if not campaign_data.get('smsName'):
        errors.append("Campaign name is required")

    if not campaign_data.get('groupList'):
        errors.append("Group is required")

    if campaign_data.get('scheduleType') == 2 and not campaign_data.get('sendOnDate'):
        errors.append("Send date is required for scheduled campaigns")

    if campaign_data.get('chkOptOut') == 1 and not campaign_data.get('optOutMsg'):
        errors.append("Opt-out message is required when opt-out is enabled")

    is_valid = len(errors) == 0
    error_message = "; ".join(errors) if errors else ""

    return is_valid, error_message
