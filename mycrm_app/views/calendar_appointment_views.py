from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
import json
import logging
import traceback
import os
import math
import time
from common_app.models import (Calendar, CalendarAppointmentAvailabilitySlots, CalendarAppointmentEventType, CalendarAppointmentSms, CalendarAppointmentSmsDetails, CalendarNotification, ShareAppointmentLink, ShareAppointmentLinkDetails, Country, CalendarSetup, Clients)
from django.utils import timezone
from common_app.utils import (api_response, get_final_tenant_id, slot_list, remove_book_slot, db_date_to_display_date_time, country_code_number, day_name, current_time, convert_event_timezone_to_user_db, convert_event_timezone_to_user, remaining_time, parse_date_time, nl2br, get_tenants, get_client_id_by_tenant_id, get_phone_numbers_first, get_client_timezone)
from common_app.decrypt_string import DecryptString
from common_app.telnyx_utils import send_sms_telnyx, check_assign_to_number
from mycrm_app.serializers import (CalendarAppointmentAvailabilitySlotsSerializer,)
from api_app.views.google_calendar_views import refresh_google_token, get_user_calendar_timezone
from common_app.services import CommonServices, MailRequestDTO
from django.core.mail import EmailMessage
from common_app.ics_utils import generate_ics_file

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_availability_slots_list(request, tenId):
    res_body = dict()
    res_body["error"] = ""
    try:
        # Decrypt tenId
        tenant_id_str = DecryptString.set_enc_dec_user(tenId, "display", "Y")
        if not (tenant_id_str and str(tenant_id_str).isdigit()) and tenId.endswith('/'):
            tenant_id_str = DecryptString.set_enc_dec_user(tenId.rstrip('/'), "display", "Y")

        if tenant_id_str and str(tenant_id_str).isdigit():
            tenant_id = int(tenant_id_str)
            slots = CalendarAppointmentAvailabilitySlots.objects.filter(aasMemberId=get_client_id_by_tenant_id(tenant_id))
            serializer = CalendarAppointmentAvailabilitySlotsSerializer(slots, many=True)
            res_body["availabilitySlotsList"] = serializer.data
        else:
            res_body["error"] = "Invalid ID"
    except Exception as e:
        logger.error(f"get_availability_slots_list error: {e}")
        res_body["error"] = "Invalid Data"

    if res_body.get("error"):
        return api_response(500, res_body["error"], res_body)
    return api_response(200, "Fetch Availability Slot Successfully.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_availability_slots(request):
    res_body = {"error": ""}
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        data = request.data
        if isinstance(data, list):
            if not data:
                return api_response(200, "Success", {"error": ""})

            # Java doesn't delete existing, it just saves/updates items in the list

            for item in data:
                aas_id = item.get("aasId", 0)
                if aas_id > 0:
                    try:
                        slot = CalendarAppointmentAvailabilitySlots.objects.get(aasId=aas_id, aasMemberId=get_client_id_by_tenant_id(final_tenant_id))
                    except CalendarAppointmentAvailabilitySlots.DoesNotExist:
                        slot = CalendarAppointmentAvailabilitySlots()
                else:
                    slot = CalendarAppointmentAvailabilitySlots()

                slot.aasDayName = item.get("aasDayName")
                
                # These will seamlessly accept the string (e.g. "10:00:00") and use the custom field
                slot.aasStartTime = item.get("aasStartTime")
                slot.aasEndTime = item.get("aasEndTime")
                
                slot.aasMemberId = get_client_id_by_tenant_id(final_tenant_id)
                slot.aasAvailableYN = item.get("aasAvailableYN", "Y")
                slot.aasCreatedDate = timezone.now()
                
                # This will no longer throw ORA-00932!
                slot.save()
            
            # Java: decides message based on first item's ID
            message = "Add Availability Slot Successfully" if data[0].get("aasId", 0) == 0 else "Update Availability Slot Successfully"
            return api_response(200, message, {"error": ""})
        else:
            res_body["error"] = "Invalid data format."
    except Exception as e:
        logger.error(f"save_availability_slots error: {e}")
        logger.error(traceback.format_exc())
        res_body["error"] = "Internal Server Error"
        
    if res_body.get("error"):
        return api_response(500, res_body["error"], res_body)
    return api_response(200, "success", res_body)

def get_free_slots_logic(slot_time_minus, slot_date_time, slot_tenant, time_zone, current_date_yn):
    slots = []
    try:
        user_slot_date_time = slot_date_time # Original from request
        if slot_date_time and len(slot_date_time) > 10:
            db_tz = getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')
            slot_date_time = convert_event_timezone_to_user(slot_date_time, time_zone, db_tz)

        tenant_id_str = DecryptString.set_enc_dec_user(slot_tenant, "display", "Y")
        if not (tenant_id_str and str(tenant_id_str).isdigit()) and slot_tenant and slot_tenant.endswith('/'):
            tenant_id_str = DecryptString.set_enc_dec_user(slot_tenant.rstrip('/'), "display", "Y")
        if tenant_id_str:
            tenant_id = int(tenant_id_str)
            # Use original user date to find day name
            orig_date_part = user_slot_date_time[:10] if user_slot_date_time else slot_date_time[:10]
            day = day_name(orig_date_part)
            
            availability = CalendarAppointmentAvailabilitySlots.objects.filter(
                aasMemberId=get_client_id_by_tenant_id(tenant_id),
                aasDayName=day, 
                aasAvailableYN='Y'
            ).first()
            
            start_time = "00:00:00"
            end_time = "24:00:00"
            aas_available_yn = "Y"

            if availability:
                start_time = str(availability.aasStartTime)
                end_time = str(availability.aasEndTime)
                aas_available_yn = availability.aasAvailableYN

                tenant_tz = get_client_timezone(tenant_id) if tenant_id else time_zone
                temp_start_dt = convert_event_timezone_to_user(f"{slot_date_time[:10]} {start_time}", tenant_tz, time_zone)
                temp_end_dt = convert_event_timezone_to_user(f"{slot_date_time[:10]} {end_time}", tenant_tz, time_zone)

                temp_start = temp_start_dt.split(" ")
                temp_end = temp_end_dt.split(" ")

                if temp_start[0] == temp_end[0]:
                    start_time = temp_start[1]
                    end_time = temp_end[1]
                else:
                    start_time = temp_start[1]
                    end_time = "24:00:00"
                    if temp_start[0] != slot_date_time[:10]:
                        start_time = remaining_time(slot_time_minus, start_time, end_time)
                        end_time = temp_end[1]

            if aas_available_yn == "Y":
                slots = slot_list(slot_time_minus, start_time, end_time)
                if current_date_yn == "Y":
                    curr_time = current_time(time_zone)
                    slots = [s for s in slots if s > curr_time]
                
                # Filter booked slots
                db_tz = getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')
                # Java findBookList: TRUNC(cal_start_date_time)=:slotDateTime
                # Calculate search range based on User's full day converted to UTC
                temp_slot_date_str = convert_event_timezone_to_user(f"{user_slot_date_time}", time_zone, db_tz)
                dt_for_date = parse_date_time(temp_slot_date_str)
                booked = Calendar.objects.filter(
                    calMemberId=get_client_id_by_tenant_id(tenant_id),
                    calStartDateTime__date=dt_for_date.date() if dt_for_date else None
                )
                
                cal_all_day = False
                for b in booked:
                    if b.calAllDay == 'true':
                        cal_all_day = True
                        break
                    
                    s_time_db = b.calStartDateTime.strftime("%Y-%m-%d %H:%M:%S")
                    e_time_db = b.calEndDateTime.strftime("%Y-%m-%d %H:%M:%S")
                    
                    s_time_user = convert_event_timezone_to_user_db(s_time_db, db_tz, time_zone)
                    e_time_user = convert_event_timezone_to_user_db(e_time_db, db_tz, time_zone)
                    
                    s_time_only = s_time_user.split(" ")[1] if " " in s_time_user else s_time_user
                    e_time_only = e_time_user.split(" ")[1] if " " in e_time_user else e_time_user
                    
                    slots = remove_book_slot(slot_time_minus, slots, s_time_only, e_time_only)
                
                if cal_all_day:
                    slots = []
    except Exception as e:
        logger.error(f"get_free_slots_logic error: {e}")
    return slots

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def free_slot_list(request):
    res_body = dict()
    res_body["error"] = ""
    try:
        data = request.data
        slot_time_minus = int(data.get("slotTimeMinus", 0))
        slot_date_time = data.get("slotDateTime")
        slot_tenant = data.get("slotMember")
        time_zone = data.get("timeZone")
        current_date_yn = data.get("currentDateYN", "N")
        
        slots = get_free_slots_logic(slot_time_minus, slot_date_time, slot_tenant, time_zone, current_date_yn)
        res_body["freeSlotList"] = slots
    except Exception as e:
        logger.error(f"free_slot_list error: {e}")
        res_body["error"] = "Invalid Data"
        
    if res_body.get("error"):
        return api_response(500, res_body["error"], res_body)
    return api_response(200, "Fetch Free Slot Successfully.", res_body)

# @api_view(['POST'])
# @permission_classes([WhitelistPermission])
def send_sms_calendar_appointment(tenant_id, tenant, contact_list, sms_message, cal_id):
    try:
        # 1. Telnyx Provisioning Check (Java line 955)
        phone_number = get_phone_numbers_first(tenant.ten_id, "CAMPAIGN")
        client = Clients.objects.get(cliTenantId=tenant_id)
        try:
            check_assign_to_number(
                client.cliSmsAccountSid,
                phone_number.phSid,
                getattr(settings, 'TELNYX_BASE_URL', None), 
                getattr(settings, 'TELNYX_API_KEY', None), 
                getattr(client, 'cliSipConnectionId', None)
            )
        except Exception as e:
            logger.error(f"check_assign_to_number error: {e}")

        total_member = len(contact_list)
        if total_member > 0:
            # 2. Get Country and CountrySetting (Java lines 964-968)
            country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
            country_code = "1"
            try:
                if tenant.ten_country:
                    country = Country.objects.filter(country_id=int(tenant.ten_country)).first()
                    if country:
                        country_code = country.cnt_code
            except Exception:
                pass
            
            # 3. SMS Count Calculation (Java lines 981-982)
            number_of_sms = 1
            if len(sms_message) > 160:
                number_of_sms = math.ceil(len(sms_message) / 160)
            
            trans_rate = country_setting.cnty_sms_per_price if country_setting else 0
            
            # 4. Save Main SMS Record
            calendar_appointment_sms = CalendarAppointmentSms(
                casDateTime=timezone.now(),
                casMemberId=get_client_id_by_tenant_id(tenant_id),
                casMessage=sms_message,
                casFromNumber=phone_number.phPhoneNumber,
                casTotalMember=total_member,
                casCalId=cal_id
            )
            calendar_appointment_sms.save()
            cas_id = calendar_appointment_sms.casId
            
            # 5. Send Individual SMS and Record Details (Java lines 984-1002)
            for recipient_number in contact_list:
                formatted_number = country_code_number(recipient_number, country_code)
                
                msg_response = send_sms_telnyx(
                    mobile_no=formatted_number,
                    telnyx_number=phone_number.phPhoneNumber,
                    sms_type="text",
                    sms_details=sms_message,
                    sms_count="first",
                    opt_out_msg=None,
                    sms_status_url=settings.SMS_STATUS_URL_SEND_SMS_CALENDAR_APPOINTMENT
                )
                
                details = CalendarAppointmentSmsDetails(
                    casdToNumber=formatted_number,
                    casdCasId=cas_id,
                    casdSid=msg_response.get("msgId", ""),
                    casdStatus=msg_response.get("msgStatus", ""),
                    casdErrorCode=msg_response.get("msgError", ""),
                    casdErrorMessage=msg_response.get("msgErrorCode", "")
                )
                details.save()
            
            # 6. Save Campaign Transaction (Java line 1005)
            # Alignment with Java positions (via services.py mapping):
            # Pos 10 (tran_per_charge) -> Tenant Rate
            # Pos 11 (tran_total_amount) -> Total Amount (qty * rate)
            # Pos 12 (campaign_id) -> Total SMS Count
            total_amount = total_member * trans_rate * number_of_sms 
            
            CommonServices.saveCampaignTransaction(
                cas_id,                      # 1: tranCampaignId
                sms_message,                 # 2: tranCampaignName
                total_member,                # 3: tranTotalMember
                "sms calendar appointment",  # 4: tranType
                None,                        # 5: tranInvoicedId
                "uninvoiced",                # 6: tranInvoicedStatus
                None,                        # 7: tranInvoicedDate
                get_client_id_by_tenant_id(tenant_id),                   # 8: memberId
                "0",                         # 9: tranBillType
                total_amount,                # 10: tranTotalAmount
                trans_rate,                  # 11: tranMemberRate
                number_of_sms,               # 12: tranCountTotalSms
                None,                        # 13: tranPollFormNo
                None,                        # 14: tranPollToNo
                0                # 15: subMemberId
            )
    except Exception as e:
        logger.error(f"send_sms_calendar_appointment error: {e}")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_appointment(request):
    res_body = {"error": ""}
    try:
        data = request.data
        slot_tenant = data.get("slotMember")
        tenant_id_str = DecryptString.set_enc_dec_user(slot_tenant, "display", "Y")
        if not (tenant_id_str and str(tenant_id_str).isdigit()) and slot_tenant and slot_tenant.endswith('/'):
            tenant_id_str = DecryptString.set_enc_dec_user(slot_tenant.rstrip('/'), "display", "Y")
        
        if not (tenant_id_str and str(tenant_id_str).isdigit()):
            res_body["error"] = "Invalid Tenant"
            return api_response(500, res_body["error"], res_body)

        tenant_id = int(tenant_id_str)
        google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType='GOOGLE').first()
        outlook_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant_id), csCalendarType='MICROSOFT').first()
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        client = Clients.objects.get(cliTenantId=tenant_id)

        # Timezone Logic
        google_tz = None
        if google_calendar_setup:
            access_token = refresh_google_token(google_calendar_setup)
            google_tz = get_user_calendar_timezone(access_token) if access_token else None
        
        cal_tz = data.get("calTimeZone", "")
        if not cal_tz and google_tz:
            cal_tz = google_tz
        
        # Database Timezone
        db_tz = getattr(settings, 'SERVER_DATABASE_TIMEZONE', 'UTC')
        slot_time_minus = int(data.get("slotTimeMinus", 0))

        # Check for multiple slots
        slots_list = data.get("slots", [])
        if not slots_list or not isinstance(slots_list, list):
            slots_list = [{
                "start": data.get("start"),
                "end": data.get("end"),
                "currentDateYN": data.get("currentDateYN", "N")
            }]

        booked_count = 0
        conflict_count = 0
        created_cal_ids = []

        for slot_item in slots_list:
            start_raw = slot_item.get("start")
            end_raw = slot_item.get("end")
            current_date_yn = slot_item.get("currentDateYN", "N")

            start_dt_obj = parse_date_time(start_raw)
            if not start_dt_obj:
                conflict_count += 1
                continue
            start_display = start_dt_obj.strftime("%m/%d/%Y %H:%M:%S")

            slot_list_data = get_free_slots_logic(
                slot_time_minus, 
                start_display, 
                slot_tenant,
                cal_tz, 
                current_date_yn
            )
            check_slot_time_validation = start_dt_obj.strftime("%H:%M:%S")

            if check_slot_time_validation in slot_list_data:
                cal_start_db = convert_event_timezone_to_user_db(start_raw, cal_tz, db_tz)
                cal_end_db = convert_event_timezone_to_user_db(end_raw, cal_tz, db_tz)
                
                web_conf = ""
                cs_web_conference_url = None
                if google_calendar_setup:
                    cs_web_conference_url = google_calendar_setup.csWebConferenceUrl
                elif outlook_calendar_setup:
                    cs_web_conference_url = outlook_calendar_setup.csWebConferenceUrl
                if cs_web_conference_url:
                    web_conf = f"\n\n{cs_web_conference_url}"
                
                calendar_obj = Calendar(
                    calTitle=f"Meeting with {data.get('title')}",
                    calDescription=(data.get("description", "") + web_conf),
                    calStartDateTime=parse_date_time(cal_start_db),
                    calEndDateTime=parse_date_time(cal_end_db),
                    calMemberId=get_client_id_by_tenant_id(tenant_id),
                    calTimeZone=cal_tz,
                    calAttendees=data.get("calAttendees"),
                    calAetId=data.get("calAetId", 0),
                    calNotification='N',
                    calNumbers=",".join(data.get("contactList", [])),
                    calType=settings.COMPANY_NAME.lower().replace(" ", ""),
                    calCreatedDateTime=timezone.now(),
                    calUpdatedDateTime=timezone.now(),
                    calAllDay='false',
                    calEventReminder='event',
                    calScheduleDateTime=timezone.now()
                )
                calendar_obj.save()
                created_cal_ids.append(calendar_obj.calId)
                booked_count += 1

                # Email Notifications
                email_notification = ""
                if google_calendar_setup and google_calendar_setup.csEmailNotification:
                    email_notification = google_calendar_setup.csEmailNotification
                elif outlook_calendar_setup and outlook_calendar_setup.csEmailNotification:
                    email_notification = outlook_calendar_setup.csEmailNotification
                if email_notification:
                    for mins in email_notification.split(","):
                        if mins.strip():
                            CalendarNotification.objects.create(
                                calnCalId=calendar_obj.calId,
                                calnMinutes=int(mins.strip()),
                                calnCreatedDateTime=timezone.now()
                            )

                # Generate ICS and send Emails
                cal_att_raw = data.get("calAttendees", "")
                first_name_dec = ""
                last_name_dec = ""
                if cal_att_raw:
                    try:
                        att_json = json.loads(cal_att_raw)
                        attendee_emails = [e.lower() for e in att_json.get("attendees", [])]
                    except:
                        attendee_emails = [e.strip().lower() for e in cal_att_raw.split(",") if e.strip()]
                    
                    if attendee_emails:
                        invitee_email = attendee_emails[-1]
                        guests_list = attendee_emails[:-1]
                        
                        # ICS Description
                        ics_desc = nl2br(data.get("description", "") + web_conf)
                        ics_desc += f"<br /><br />Guest Email(s) :<br />{invitee_email}"
                        if guests_list:
                            ics_desc += "<br />" + "<br />".join(guests_list)
                        
                        contact_list = data.get("contactList", [])
                        if contact_list:
                            ics_desc += "<br /><br />Mobile Number(s) :<br />" + "<br />".join(contact_list)
                        
                        mem_email_dec = tenant.ten_email
                        first_name_dec = tenant.ten_first_name
                        last_name_dec = tenant.ten_last_name
                        
                        ics_event = {
                            "startDate": start_raw,
                            "endDate": end_raw,
                            "summary": calendar_obj.calTitle,
                            "description": ics_desc,
                            "replyToAdd": mem_email_dec,
                            "memberName": f"{first_name_dec} {last_name_dec}".strip(),
                            "attendees": attendee_emails,
                            "timeZone": cal_tz
                        }
                        
                        ics_path = os.path.join(settings.ICS_DOWNLOAD_DIR, f"{tenant_id}")
                        if not os.path.exists(ics_path):
                            os.makedirs(ics_path)
                        timestamp_ms = int(time.time() * 1000)
                        ics_file_name = f"CalendarInvite_{timestamp_ms}.ics"
                        ics_file = os.path.join(ics_path, ics_file_name)
                        
                        if generate_ics_file(ics_event, ics_file, settings.SITE_NAME_BIG_COM):
                            # Logo logic
                            if client.cliTenantId:
                                image_src = client.cliProfileImageUrl if client.cliProfileImageUrl.startswith('http') else f"{settings.IMAGE_SITE_URL.rstrip('/')}/{client.cliProfileImageUrl.lstrip('/')}"
                                customer_logo = f'<img tabindex="0" src="{image_src}" style="margin:0;padding:0;outline:none;text-decoration:none;max-width:120px" border="0" />'
                            else:
                                initials = ""
                                if first_name_dec: initials += first_name_dec[0].upper()
                                if last_name_dec: initials += last_name_dec[0].upper()
                                customer_logo = f'<div style="align-items: center; background: #4285f4; border-radius: 50%; color: #fff; display: flex; font-size: 22px; height: 60px; justify-content: center; text-align: center; width: 60px; font-family: \'Poppins\', sans-serif !important;"><span style="margin: auto;">{initials}</span></div>'

                            model = {
                                "SITEURL": settings.IMAGE_SITE_URL,
                                "memberName": f"{first_name_dec} {last_name_dec}".strip(),
                                "inviteeName": data.get("title"),
                                "inviteeEmail": invitee_email.lower(),
                                "guestsList": "<br />".join(guests_list).lower(),
                                "comment": nl2br(data.get("description", "")),
                                "siteName": settings.SITE_NAME,
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
                                "meetingDateTime": db_date_to_display_date_time(start_raw),
                                "inviteeTimezone": cal_tz,
                                "yourDateTime": db_date_to_display_date_time(convert_event_timezone_to_user_db(start_raw, cal_tz, get_client_timezone(tenant_id) or cal_tz)),
                                "yourTimezone": get_client_timezone(tenant_id) or cal_tz,
                                "customerLogo": customer_logo,
                                "webConference": nl2br(cs_web_conference_url) if cs_web_conference_url else ""
                            }
                            
                            # Fetch Event Type Title
                            try:
                                event_type = CalendarAppointmentEventType.objects.get(aetId=calendar_obj.calAetId)
                                model["eventType"] = event_type.aetTitle
                            except:
                                model["eventType"] = ""

                            # Send to Tenant
                            mail_req = MailRequestDTO(to=mem_email_dec.lower(), subject="New Event Meeting", template_name="calendar-appointment-member-event-template.html")
                            CommonServices.sendEmail(mail_req, model)
                            
                            # Java: Send to Google/Outlook emails if different
                            google_email_dec = google_calendar_setup.csEmail.lower() if google_calendar_setup else None
                            outlook_email_dec = outlook_calendar_setup.csEmail.lower() if outlook_calendar_setup else None
                            
                            if google_email_dec and google_email_dec != mem_email_dec.lower():
                                mail_req_google = MailRequestDTO(to=google_email_dec, subject="New Event Meeting", template_name="calendar-appointment-member-event-template.html")
                                CommonServices.sendEmail(mail_req_google, model)
                                
                            if outlook_email_dec and outlook_email_dec != mem_email_dec.lower():
                                mail_req_outlook = MailRequestDTO(to=outlook_email_dec, subject="New Event Meeting", template_name="calendar-appointment-member-event-template.html")
                                CommonServices.sendEmail(mail_req_outlook, model)

                            # Send to Invitee
                            mail_req_inv = MailRequestDTO(to=invitee_email, subject="New Event Meeting", template_name="calendar-appointment-invitee-event-template.html", file_name="CalendarInvite.ics", file_path=ics_file)
                            CommonServices.sendEmail(mail_req_inv, model)
                            
                            # Send to Guests
                            for guest in guests_list:
                                mail_req_guest = MailRequestDTO(to=guest, subject="New Event Meeting", template_name="calendar-appointment-client-event-template.html", file_name="CalendarInvite.ics", file_path=ics_file)
                                CommonServices.sendEmail(mail_req_guest, model)

                # SMS Notification
                contact_list = data.get("contactList", [])
                if contact_list:
                    sms_msg = f"Your meeting with {first_name_dec} {last_name_dec} has been scheduled for {db_date_to_display_date_time(start_raw)} {cal_tz}"
                    send_sms_calendar_appointment(tenant_id, tenant, contact_list, sms_msg, calendar_obj.calId)
            else:
                conflict_count += 1

        if booked_count > 0:
            res_body["error"] = ""
            res_body["bookedCount"] = booked_count
            res_body["conflictCount"] = conflict_count
            res_body["calIds"] = created_cal_ids
            return api_response(200, "Appointments Scheduled Successfully.", res_body)
        elif conflict_count > 0:
            res_body["error"] = "1"
            return api_response(200, "Slot already booked or invalid", {"error": "1"})
        else:
            res_body["error"] = "No valid slots provided"
            return api_response(500, "No valid slots provided", res_body)

    except Exception as e:
        logger.error(f"save_appointment error: {e}")
        res_body["error"] = "Invalid Data"
        return api_response(500, res_body["error"], res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_email_appointment_link(request):
    res_body = {"error": ""}
    try:
        data = request.data
        contact_list = data.get("contactList", [])
        message = data.get("message")
        
        for contact in contact_list:
            client_email = contact.get("clientEmail")
            if client_email:
                email = EmailMessage(
                    subject="Appointment Link",
                    body=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[client_email]
                )
                email.send(fail_silently=True)
    except Exception as e:
        logger.error(f"send_email_appointment_link error: {e}")
        res_body["error"] = "Invalid Data"
    if res_body.get("error"):
        return api_response(500, res_body["error"], res_body)
    return api_response(200, "Send Email Successfully.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_sms_appointment_link(request):
    res_body = {"error": ""}
    try:
        tenant_id = get_final_tenant_id(request=request)
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        data = request.data
        
        contact_list = data.get("contactList", [])
        message = data.get("message")
        phone_number = get_phone_numbers_first(tenant.ten_id, "CAMPAIGN")
        client = Clients.objects.get(cliTenantId=tenant_id)
        try:
            check_assign_to_number(
                client.cliSmsAccountSid,
                phone_number.phSid,
                getattr(settings, 'TELNYX_BASE_URL', None),
                getattr(settings, 'TELNYX_API_KEY', None),
                getattr(client, 'cliSipConnectionId', None)
            )
        except Exception as e:
            logger.error(f"check_assign_to_number error: {e}")

        total_member = len(contact_list)
        if total_member > 0:
            country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
            country_code = "1"
            try:
                if tenant.ten_country:
                    country = Country.objects.filter(country_id=int(tenant.ten_country)).first()
                    if country:
                        country_code = country.cnt_code
            except Exception:
                pass

            number_of_sms = 1
            if len(message) > 160:
                number_of_sms = math.ceil(len(message) / 160)

            trans_rate = country_setting.cnty_sms_per_price if country_setting else 0

            sal = ShareAppointmentLink(
                salDateTime=timezone.now(),
                salMemberId=get_client_id_by_tenant_id(tenant_id),
                salMessage=message,
                salFromNumber=phone_number.phPhoneNumber,
                salTotalMember=total_member
            )
            sal.save()
            sal_id = sal.salId
            
            for contact in contact_list:
                to_number = contact.get("clientNumber")
                if to_number:
                    formatted_number = country_code_number(to_number, country_code)
                    response = send_sms_telnyx(
                        mobile_no=formatted_number,
                        telnyx_number=phone_number.phPhoneNumber,
                        sms_type="text",
                        sms_details=message,
                        sms_count="first",
                        opt_out_msg=None,
                        sms_status_url=f"{settings.SITE_URL_BACKEND}calendarAppointment/smsStatusUrlSendAppointmentLink"
                    )
                    
                    sald = ShareAppointmentLinkDetails(
                        saldSalId=sal_id,
                        saldToNumber=formatted_number,
                        saldSid=response.get("msgId", ""),
                        saldStatus=response.get("msgStatus", ""),
                        saldErrorCode=response.get("msgError", ""),
                        saldErrorMessage=response.get("msgErrorCode", "")
                    )
                    sald.save()

            number_of_sms = number_of_sms * total_member
            if number_of_sms > 0:
                total_amount = number_of_sms * trans_rate
                CommonServices.saveCampaignTransaction(
                    sal_id,                      # 1: tranCampaignId
                    message,                     # 2: tranCampaignName
                    total_member,                # 3: tranTotalMember
                    "share appointment link",    # 4: tranType
                    None,                        # 5: tranInvoicedId
                    "uninvoiced",                # 6: tranInvoicedStatus
                    None,                        # 7: tranInvoicedDate
                    get_client_id_by_tenant_id(tenant_id),                   # 8: memberId
                    "0",                         # 9: tranBillType
                    total_amount,                # 10: tranTotalAmount
                    trans_rate,                  # 11: tranMemberRate
                    number_of_sms,               # 12: tranCountTotalSms
                    None,                        # 13: tranPollFormNo
                    None,                        # 14: tranPollToNo
                    0                # 15: subMemberId
                )
        else:
            res_body["error"] = "Invalid data"
    except Exception as e:
        logger.error(f"send_sms_appointment_link error: {e}")
        res_body["error"] = "Invalid Data"
    if res_body.get("error"):
        return api_response(500, res_body["error"], res_body)
    return api_response(200, "Send SMS Successfully.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def sms_status_url_send_appointment_link(request):
    try:
        data = request.data
        payload = data.get("data", {}).get("payload", {})
        sms_sid = payload.get("id")
        to_data = payload.get("to", [{}])[0]
        status = to_data.get("status")
        
        details = ShareAppointmentLinkDetails.objects.filter(saldSid=sms_sid).first()
        if details:
            details.saldStatus = status
            details.save()
    except Exception as e:
        logger.error(f"sms_status_url_send_appointment_link error: {e}")
    return api_response(200, "ok")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def sms_status_url_send_sms_calendar_appointment(request):
    try:
        data = request.data
        payload = data.get("data", {}).get("payload", {})
        sms_sid = payload.get("id")
        to_data = payload.get("to", [{}])[0]
        status = to_data.get("status")
        
        details = CalendarAppointmentSmsDetails.objects.filter(casdSid=sms_sid).first()
        if details:
            details.casdStatus = status
            details.save()
    except Exception as e:
        logger.error(f"sms_status_url_send_sms_calendar_appointment error: {e}")
    return api_response(200, "ok")