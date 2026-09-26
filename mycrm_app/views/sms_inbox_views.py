import logging
import math
import re
import traceback
from datetime import datetime
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from django.db import models
from django.db.models import Q, Subquery
from common_app.models import (Userlist, Country, SmsConversations, SmsConversationsDetails, CampaignSmsReply, NumberCallForwarding, CampaignsSms, CampaignSmsDetails, Language, Udf, CampaignTransaction, PhoneNumbers, Clients)
from auth_app.models import TenantDetails
from common_app.utils import (api_response, get_final_tenant_id, display_date_time, display_date, convert_event_timezone_to_user, get_tenants, get_phone_numbers_first, get_client_id_by_tenant_id, add_one_month)
from common_app.telnyx_utils import (send_sms_telnyx, telnyx_sub_account, delete_telnyx_number, check_assign_to_number, telnyx_call_forwarding, change_telnyx_number, )
from common_app.services import CommonServices
from smscampaigns_app.views.sms_campaigns_views import _perform_close_campaign_logic

logger = logging.getLogger(__name__)

def _clean_phone(phone):
    """Remove non-digit characters except leading +."""
    return re.sub(r'[^\d]', '', phone)


def _last_chars(s, n):
    """Return last n characters of string."""
    return s[-n:] if len(s) >= n else s


def _get_tenant_phone(tenant):
    """Return formatted E.164 member phone using country code."""
    tenant_phone = ''
    try:
        if tenant.ten_phone:
            phone = tenant.ten_phone
            country = Country.objects.get(country_id=int(tenant.ten_country))
            phone_clean = _clean_phone(phone)
            phone_clean = _last_chars(phone_clean, country.phone_max_length or 10)
            tenant_phone = (country.cnt_code or '+1') + phone_clean
    except Exception:
        pass
    return tenant_phone


def _personalize_sms(template_data, userlist, group_id):
    """Port of Java's personalization logic for SMS campaigns."""
    if not template_data:
        return ""

    replacements = {
        "##First Name##": userlist.firstName or "",
        "##Last Name##": userlist.lastName or "",
        "##Full Name##": userlist.fullName or "",
        "##Contact No##": userlist.phoneNumber or "",
        "##Phone##": userlist.phone or "",
        "##Gender##": userlist.gender or "",
        "##Country##": userlist.country or "",
        "##State##": userlist.stateProvRegion or "",
        "##Street Address1##": userlist.streetAddress1 or "",
        "##Street Address2##": userlist.streetAddress2 or "",
        "##City##": userlist.city or "",
        "##Zip Code##": userlist.zipPostalCode or "",
    }

    # Special handling for Email (Decryption)
    if userlist.email:
        replacements["##Email##"] = userlist.email
    else:
        replacements["##Email##"] = ""

    # Special handling for Birthday (Formatting)
    if userlist.birthday:
        try:
            birthday_str = userlist.birthday
            replacements["##Date Of Birth##"] = display_date(birthday_str)
        except Exception:
            replacements["##Date Of Birth##"] = ""
    else:
        replacements["##Date Of Birth##"] = ""

    if userlist.usDefaultLanguage:
        try:
            lang = Language.objects.filter(lg_name=userlist.usDefaultLanguage).first()
            if lang:
                replacements["##Language##"] = lang.lg_long_name or ""
            else:
                replacements["##Language##"] = ""
        except Exception:
            replacements["##Language##"] = ""
    else:
        replacements["##Language##"] = ""

    # Apply standard replacements
    for key, value in replacements.items():
        template_data = template_data.replace(key, str(value or ""))

    # Handle UDFs
    try:
        if group_id:
            # Assuming groupList can contain multiple IDs, but Java uses the first one or parses it.
            group_id = int(group_id)
            udf_list_data = Udf.objects.filter(groupId=group_id)

            udf_values = {
                1: (userlist.udf1 or "").replace("'", "\\'"),
                2: (userlist.udf2 or "").replace("'", "\\'"),
                3: (userlist.udf3 or "").replace("'", "\\'"),
                4: (userlist.udf4 or "").replace("'", "\\'"),
                5: (userlist.udf5 or "").replace("'", "\\'"),
                6: (userlist.udf6 or "").replace("'", "\\'"),
                7: (userlist.udf7 or "").replace("'", "\\'"),
                8: (userlist.udf8 or "").replace("'", "\\'"),
                9: (userlist.udf9 or "").replace("'", "\\'"),
                10: (userlist.udf10 or "").replace("'", "\\'"),
            }

            for udf in udf_list_data:
                # Java uses list index, assuming udfLabel matches the udf1-10 index
                label_idx = udf.udfLabel
                val = udf_values.get(label_idx, "")
                template_data = template_data.replace(f"##{udf.udf}##", val)
    except Exception:
        pass

    return re.sub(r" +", " ", template_data).strip()


# ─────────────────────────────────────────────
# GET /smsInbox/getAllReplyCount
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_all_reply_count(request):
    """GET /smsInbox/getAllReplyCount"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        campaign_reply_count = CampaignSmsReply.objects.filter(
            Q(crRead__isnull=True) | Q(crRead='N'),
            crMemberId=get_client_id_by_tenant_id(tenant_id),
            crSmsId__in=CampaignsSms.objects.values_list('smsId', flat=True)
        ).count()

        # Use Subquery to avoid N+1 query
        conversation_subquery = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id),
            cvsClosed='N'
        ).values_list('cvsId', flat=True)

        conversations_count = SmsConversationsDetails.objects.filter(
            cvsdCvsId__in=Subquery(conversation_subquery),
            cvsdRead__in=[None, 'N'],
            cvsdSender='c',
        ).count()

        res_body['totalSmsCampaignCount'] = campaign_reply_count
        res_body['totalConversationsCount'] = conversations_count
        res_body['totalSmsInboxCount'] = conversations_count + campaign_reply_count
    except Exception as e:
        logger.error(f"GetAllReplyCount Error: {e}")
    return api_response(200, 'SMS Count Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/getSMSCampaignPhoneNumberList
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaign_phone_number_list(request):
    """GET /smsInbox/getSMSCampaignPhoneNumberList"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        replied_phones = CampaignSmsReply.objects.filter(
            crMemberId=get_client_id_by_tenant_id(tenant_id),
            crSmsId__in=CampaignsSms.objects.values_list('smsId', flat=True)
        ).values('crReplyNo').annotate(
            crEmailId=models.Max('crEmailId'),
            crDate=models.Max('crDate')
        ).order_by('-crDate')

        phone_number_list = []
        for r in replied_phones:
            phone = r['crReplyNo']
            email_id = r['crEmailId']

            cnt_code = '+1'
            first_name = ''
            last_name = ''
            try:
                # Fix attribute access: firstName, lastName instead of first_name, last_name
                contact = Userlist.objects.get(emailId=email_id, memberId=get_client_id_by_tenant_id(tenant_id))
                first_name = contact.firstName or ''
                last_name = contact.lastName or ''
                if contact.country:
                    # Fix: use cnt_name instead of country_name
                    c = Country.objects.filter(cnt_name=contact.country).first()
                    if c:
                        cnt_code = c.cnt_code or '+1'
            except Exception:
                pass

            # Update: count ONLY unread replies to match Java
            sms_reply_count = CampaignSmsReply.objects.filter(
                Q(crRead__isnull=True) | Q(crRead='N'),
                crReplyNo=phone,
                crMemberId=get_client_id_by_tenant_id(tenant_id),
                crSmsId__in=CampaignsSms.objects.values_list('smsId', flat=True)
            ).count()

            phone_number_list.append({
                'emailId': email_id,
                'firstName': first_name,
                'lastName': last_name,
                'cntCode': cnt_code,
                'phoneNumber': phone,
                'smsCampaignCount': sms_reply_count,
            })

        res_body['phoneNumberList'] = phone_number_list
    except Exception as e:
        logger.error(f"GetSMSCampaignPhoneNumberList Error: {e}")
    return api_response(200, 'SMS Campaign Number Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/getSMSCampaignList/<phoneNumber>
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaign_list(request, phoneNumber):
    """GET /smsInbox/getSMSCampaignList/{phoneNumber}"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        # Match Java: group by cr_sms_id and order by cr_date desc
        # Java uses MAX for cr_email_id
        replies = CampaignSmsReply.objects.filter(
            crReplyNo=phoneNumber, crMemberId=get_client_id_by_tenant_id(tenant_id)
        ).values('crSmsId').annotate(
            max_crEmailId=models.Max('crEmailId'),
            max_crDate=models.Max('crDate')
        ).order_by('-max_crDate')

        sms_campaign_list = []
        for r in replies:
            sms_id = r['crSmsId']
            email_id = r['max_crEmailId']
            
            campaign = CampaignsSms.objects.filter(smsId=sms_id).first()
            if campaign and campaign.smsName:
                sms_campaign_list.append({
                    'crEmailId': email_id,
                    'crSmsId': sms_id,
                    'crReplyNo': phoneNumber,
                    'smsName': campaign.smsName,
                    'smsCampaignStatus': campaign.smsOpenClose or '',
                })

        res_body['smsCampaignList'] = sms_campaign_list
    except Exception as e:
        logger.error(f"GetSMSCampaignList Error: {e}")
    return api_response(200, 'SMS Campaign Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/getSMSCampaignDetailList/<phoneNumber>/<crEmailId>/<crSmsId>
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaign_detail_list(request, phoneNumber, crEmailId, crSmsId):
    """GET /smsInbox/getSMSCampaignDetailList/{phoneNumber}/{crEmailId}/{crSmsId}"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        sms_reply_count = CampaignSmsReply.objects.filter(
            Q(crRead__isnull=True) | Q(crRead='N'),
            crReplyNo=phoneNumber, crMemberId=get_client_id_by_tenant_id(tenant_id)
        ).count()
        res_body['smsCampaignCount'] = sms_reply_count

        # Mark replies as read (Match Java: update BEFORE returning detail list)
        CampaignSmsReply.objects.filter(crEmailId=crEmailId, crSmsId=crSmsId).update(crRead='Y')

        # Campaign reply list for specific email + sms
        replies = CampaignSmsReply.objects.filter(
            crEmailId=crEmailId, crSmsId=crSmsId
        ).order_by('crDate')
        campaign_sms_reply_list = []
        for r in replies:
            campaign_sms_reply_list.append({
                'crReply': r.crReply or '',
                'crDate': display_date_time(r.crDate) if r.crDate else '',
            })
        res_body['campaignSmsReplyList'] = campaign_sms_reply_list

        # Match Java: Add smsCampaignDetailList with personalization
        campaign_sms = CampaignsSms.objects.filter(smsId=crSmsId).first()
        send_date_str = ""
        group_id = 0
        if campaign_sms:
            send_date_str = display_date_time(campaign_sms.sendDate) if campaign_sms.sendDate else ""
            group_id = campaign_sms.groupList
        
        userlist = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), emailId=crEmailId).first()
        
        sms_details = CampaignSmsDetails.objects.filter(smsId=crSmsId).order_by('sdDisplayOrder')
        sms_campaign_detail_list = []
        for sd in sms_details:
            detail_text = sd.sdDetail or ''
            if sd.sdType == 'text' and userlist:
                detail_text = _personalize_sms(detail_text, userlist, group_id)
            
            sms_campaign_detail_list.append({
                'sdId': sd.sdId,
                'smsId': sd.smsId,
                'sdDetail': detail_text,
                'sdType': sd.sdType or '',
                'sdDisplayOrder': sd.sdDisplayOrder,
                'sendDate': send_date_str,
            })
        res_body['smsCampaignDetailList'] = sms_campaign_detail_list

        # Re-compute total counts (Match Java: check for both NULL and N)
        campaign_reply_count = CampaignSmsReply.objects.filter(
            Q(crRead__isnull=True) | Q(crRead='N'),
            crMemberId=get_client_id_by_tenant_id(tenant_id)
        ).count()

        conversation_subquery = SmsConversations.objects.filter(cvsMemberId=get_client_id_by_tenant_id(tenant_id)).values_list('cvsId', flat=True)
        conversations_count = SmsConversationsDetails.objects.filter(
            cvsdCvsId__in=Subquery(conversation_subquery),
            cvsdRead__in=[None, 'N'], cvsdSender='c',
        ).count()
        res_body['totalSmsCampaignCount'] = campaign_reply_count
        res_body['totalConversationsCount'] = conversations_count
        res_body['totalSmsInboxCount'] = conversations_count + campaign_reply_count
    except Exception as e:
        logger.error(f"GetSMSCampaignDetailList Error: {e}")
    return api_response(200, 'SMS Campaign Details Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/getConversationsList
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_conversations_list(request):
    """GET /smsInbox/getConversationsList"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        conversations_list = []
        seen_client_ids = set()

        # Get open conversations for this member
        open_convs = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id), cvsClosed='N'
        ).order_by('-cvsDate')

        for conv in open_convs:
            # Get the latest detail message for this conversation
            latest = SmsConversationsDetails.objects.filter(
                cvsdCvsId=conv.cvsId
            ).order_by('-cvsdDate').first()

            if not latest:
                continue

            client_id = latest.cvsdClientId
            if client_id in seen_client_ids:
                continue
            seen_client_ids.add(client_id)

            first_name = ''
            last_name = ''
            try:
                contact = Userlist.objects.get(emailId=client_id, memberId=get_client_id_by_tenant_id(tenant_id))
                first_name = contact.firstName or ''
                last_name = contact.lastName or ''
            except Exception:
                pass

            unread_count = SmsConversationsDetails.objects.filter(
                cvsdCvsId=conv.cvsId, cvsdRead__in=[None, 'N'], cvsdSender='c'
            ).count()

            # Match Java: readClob behavior strips newlines
            msg = latest.cvsdMessage or ''
            msg_clean = msg.replace('\r\n', '').replace('\n', '').replace('\r', '')

            conversations_list.append({
                'cvsdClientId': client_id,
                'cvsdMessage': msg_clean,
                'cvsdClientNumber': latest.cvsdClientNumber or '',
                'cvsMemberNumber': conv.cvsMemberNumber or '',
                'cvsdDate': display_date_time(latest.cvsdDate) if latest.cvsdDate else '',
                'cvsdCvsId': conv.cvsId,
                'firstName': first_name,
                'lastName': last_name,
                'conversationsCount': unread_count,
            })

        res_body['conversationsList'] = conversations_list
    except Exception as e:
        logger.error(f"GetConversationsList Error: {e}")
    return api_response(200, 'Message Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/getConversationsClosedList
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_conversations_closed_list(request):
    """GET /smsInbox/getConversationsClosedList"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        conversations_list = []
        seen_client_ids = set()

        closed_convs = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id), cvsClosed='Y'
        ).order_by('-cvsClosedDate')

        for conv in closed_convs:
            latest = SmsConversationsDetails.objects.filter(
                cvsdCvsId=conv.cvsId
            ).order_by('-cvsdDate').first()

            if not latest:
                continue

            client_id = latest.cvsdClientId
            if client_id in seen_client_ids:
                continue
            seen_client_ids.add(client_id)

            first_name = ''
            last_name = ''
            try:
                contact = Userlist.objects.get(emailId=client_id, memberId=get_client_id_by_tenant_id(tenant_id))
                first_name = contact.firstName or ''
                last_name = contact.lastName or ''
            except Exception:
                pass

            # Match Java: readClob behavior strips newlines
            msg = latest.cvsdMessage or ''
            msg_clean = msg.replace('\r\n', '').replace('\n', '').replace('\r', '')

            conversations_list.append({
                'cvsdClientId': client_id,
                'cvsdMessage': msg_clean,
                'cvsdClientNumber': latest.cvsdClientNumber or '',
                'cvsMemberNumber': conv.cvsMemberNumber or '',
                'cvsdDate': display_date_time(latest.cvsdDate) if latest.cvsdDate else '',
                'cvsdCvsId': conv.cvsId,
                'firstName': first_name,
                'lastName': last_name,
            })

        res_body['conversationsList'] = conversations_list
    except Exception as e:
        logger.error(f"GetConversationsClosedList Error: {e}")
    return api_response(200, 'Conversations Closed List Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/getConversationsContactList/<searchName>
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_conversations_contact_list(request, searchName):
    """GET /smsInbox/getConversationsContactList/{searchName}"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        tenant_phone = _get_tenant_phone(tenant)

        # Match Java: Exclude contacts who already have an open conversation
        open_conv_ids = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id), cvsClosed='N'
        ).values_list('cvsId', flat=True)
        
        open_client_ids = SmsConversationsDetails.objects.filter(
            cvsdCvsId__in=Subquery(open_conv_ids)
        ).values_list('cvsdClientId', flat=True).distinct()

        contacts_query = Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(tenant_id)
        ).exclude(
            Q(phoneNumber__isnull=True) | Q(phoneNumber='') | Q(emailId__in=open_client_ids)
        )

        if searchName and searchName != 'all':
            contacts_query = contacts_query.filter(
                Q(firstName__icontains=searchName) | 
                Q(lastName__icontains=searchName) |
                Q(phoneNumber__icontains=searchName)
            )

        # Match Java: Group by fields and get min emailId
        # We use values().annotate() to emulate GROUP BY behavior
        contacts = contacts_query.values(
            'firstName', 'lastName', 'phoneNumber', 'country'
        ).annotate(
            minEmailId=models.Min('emailId')
        )

        contact_list = []
        for c in contacts:
            cnt_code = ''
            max_len = 10
            
            try:
                if c['country']:
                    country_obj = Country.objects.filter(cnt_name=c['country']).first()
                    if country_obj:
                        cnt_code = country_obj.cnt_code or ''
                        max_len = country_obj.phone_max_length or 10
            except Exception:
                pass

            raw_phone = _clean_phone(c['phoneNumber'])
            client_phone = _last_chars(raw_phone, max_len)
            if cnt_code:
                client_phone = cnt_code + client_phone

            full_name = f"{c['firstName'] or ''} {c['lastName'] or ''}"
            contact_list.append({
                'value': full_name,
                'label': f"{full_name} ({client_phone})",
                'memberNumber': tenant_phone,
                'clientNumber': client_phone,
                'emailId': str(c['minEmailId']),
                'clientEmail': None,
            })

        res_body['contactList'] = contact_list
    except Exception as e:
        logger.error(f"GetConversationsContactList Error: {e}")
    return api_response(200, 'Message Contact List Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# POST /smsInbox/currentConversationsDetailList
# ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def current_conversations_detail_list(request):
    """POST /smsInbox/currentConversationsDetailList"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        data = request.data
        cvsd_client_id = data.get('cvsdClientId')
        cvs_member_number = data.get('cvsMemberNumber', '')
        cvsd_client_number = data.get('cvsdClientNumber', '')
        check_conversations_rows = int(data.get('checkConversationsRows', 0))
        time_zone = data.get('timeZone', 'UTC')

        # Get all conversation IDs for this client
        cvsd_cvs_id_list = SmsConversationsDetails.objects.filter(
            cvsdClientId=cvsd_client_id
        ).values_list('cvsdCvsId', flat=True).distinct()

        # Filter for active conversations only
        active_cvs_ids = SmsConversations.objects.filter(
            cvsId__in=cvsd_cvs_id_list,
            cvsMemberId=get_client_id_by_tenant_id(tenant_id),
            cvsMemberNumber=cvs_member_number,
            cvsClosed='N'
        ).values_list('cvsId', flat=True)

        # Get all message history
        history = SmsConversationsDetails.objects.filter(
            cvsdCvsId__in=active_cvs_ids
        ).filter(
            Q(cvsdClientNumber=cvsd_client_number) | Q(cvsdClientNumber=cvs_member_number)
        ).order_by('cvsdDate', 'cvsdId')

        current_check_rows = history.count()
        final_history = []

        if current_check_rows > 0 and current_check_rows > check_conversations_rows:
            rc = 1
            m = 0
            for h in history:
                # Determine chat color
                if h.cvsdClientId == 0 or h.cvsdSender == 'm':
                    chat_color = 'myChat'
                else:
                    chat_color = 'clientChat'

                if rc == 1 and h.cvsdClientId != 0:
                    m = 1

                if rc != 1 or m == 1:
                    raw_date = display_date_time(h.cvsdDate) if h.cvsdDate else ''
                    converted_date = convert_event_timezone_to_user(raw_date, 'UTC', time_zone)

                    final_history.append({
                        'cvsdClientId': cvsd_client_id,
                        'cvsMemberNumber': cvs_member_number,
                        'cvsdClientNumber': cvsd_client_number,
                        'checkConversationsRows': current_check_rows,
                        'chatColor': chat_color,
                        'cvsdMessage': h.cvsdMessage or '',
                        'cvsdDate': converted_date,
                        'timeZone': time_zone,
                    })
                m = 0
                rc += 1

        # Mark all as read
        SmsConversationsDetails.objects.filter(cvsdCvsId__in=active_cvs_ids).update(cvsdRead='Y')

        res_body['conversationsDetailList'] = final_history
        res_body['checkConversationsRows'] = current_check_rows

        # Get latest message
        latest_msg_obj = SmsConversationsDetails.objects.filter(
            cvsdClientId__gt=0,
            cvsdCvsId__in=active_cvs_ids,
            cvsdClientNumber=cvsd_client_number
        ).order_by('-cvsdDate').first()
        
        latest_msg = latest_msg_obj.cvsdMessage if latest_msg_obj else ""
        if latest_msg:
             latest_msg = latest_msg.replace('\r\n', '').replace('\n', '').replace('\r', '')
        res_body['getLatestMessage'] = latest_msg

        # Counts
        campaign_reply_count = CampaignSmsReply.objects.filter(
            Q(crRead__isnull=True) | Q(crRead='N'),
            crMemberId=get_client_id_by_tenant_id(tenant_id)
        ).count()

        # Use Subquery to avoid N+1 query (single query with subquery instead of 2 separate queries)
        conversation_subquery_counts = SmsConversations.objects.filter(cvsMemberId=get_client_id_by_tenant_id(tenant_id)).values_list('cvsId', flat=True)
        conversations_count = SmsConversationsDetails.objects.filter(
            cvsdCvsId__in=Subquery(conversation_subquery_counts),
            cvsdRead__in=[None, 'N'], cvsdSender='c',
        ).count()
        res_body['totalSmsCampaignCount'] = campaign_reply_count
        res_body['totalConversationsCount'] = conversations_count
        res_body['totalSmsInboxCount'] = conversations_count + campaign_reply_count

    except Exception as e:
        logger.error(f"CurrentConversationsDetailList Error: {e}")
    return api_response(200, 'Message Fetched Successfully', res_body)


# ─────────────────────────────────────────────
# POST /smsInbox/sendConversations
# ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_conversations(request):
    """POST /smsInbox/sendConversations"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        data = request.data
        cvs_email_id = data.get('cvsEmailId')
        send_message = data.get('sendMessage', '')
        sub_tenant_id = int(data.get('subTenantId', 0))

        if not send_message or cvs_email_id is None:
            return api_response(500, 'Message Can Not Be Send.', res_body)

        logged_user_id = sub_tenant_id if sub_tenant_id > 0 else tenant_id
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": logged_user_id
                }
            }
        )
        chat_phone_number = get_phone_numbers_first(tenant.ten_id, "CHAT")
        if not chat_phone_number:
            chat_phone_number = get_phone_numbers_first(tenant.ten_id, "DEFAULTCHAT")
        if not chat_phone_number:
            return api_response(500, 'Message Can Not Be Send.', res_body)
        
        tenant_name = ""
        first_name = tenant.ten_first_name if tenant.ten_first_name else ""
        if first_name:
            tenant_name = first_name.capitalize()
        last_name = tenant.ten_last_name if tenant.ten_last_name else ""
        if last_name:
            tenant_name = (tenant_name + " " + last_name.capitalize()).strip()

        tenant_phone = _get_tenant_phone(tenant)
        ph_chat_phone_number = chat_phone_number.phPhoneNumber or ''

        # Calculate SMS count (Match Java Line 754-757)
        number_of_sms = math.ceil(len(send_message) / 160) if len(send_message) > 160 else 1

        # Get contact(s) (Match Java Line 825: findMultipleRecords)
        contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), emailId=cvs_email_id)
        if not contacts.exists():
            return api_response(500, 'Message Can Not Be Send.', res_body)

        # We'll use the first contact for numbering/naming as Java loops but overwrites cvsdClientNo
        cvsd_client_no = ""
        client_name = ""
        user_data_list = []

        for userlist in contacts:
            c_phone = userlist.phoneNumber
            c_name = ""
            c_no = ""
            if c_phone:
                country_client = Country.objects.filter(cnt_name=userlist.country).first()
                cnt_code = country_client.cnt_code if country_client else "+1"
                max_len = country_client.phone_max_length if country_client else 10
                c_no = cnt_code + _last_chars(_clean_phone(c_phone), max_len)
                
                # Client naming (Match Java Line 854-860)
                if userlist.firstName:
                    c_name = userlist.firstName.capitalize()
                if userlist.lastName:
                    c_name = (c_name + " " + userlist.lastName.capitalize()).strip()
            
            # For transaction/lookup we use the last valid one from the loop (matches Java j++ logic)
            if c_no:
                cvsd_client_no = c_no
                client_name = c_name
                user_data_list.append({'id': userlist.emailId, 'phone': c_no})

        if not cvsd_client_no:
            return api_response(500, 'Message Can Not Be Send.', res_body)

        cvs_title = f"{tenant_name} to {client_name}"

        temp_cvs_id = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id),
            cvsMemberNumber=tenant_phone,
            cvsClosed='N',
            cvsId__in=SmsConversationsDetails.objects.filter(
                cvsdClientNumber=cvsd_client_no,
                cvsdSender='m'
            ).values('cvsdCvsId')
        ).order_by('-cvsId').values_list('cvsId', flat=True).first()

        cvs_id = temp_cvs_id or 0
        cvsd_sid = ""

        if cvs_id == 0:
            # Create new conversation (Match Java Line 881-890)
            new_conv = SmsConversations(
                cvsMemberId=get_client_id_by_tenant_id(tenant_id),
                cvsMemberNumber=tenant_phone,
                cvsTwilioNumber=ph_chat_phone_number,
                cvsTitle=cvs_title,
                cvsClosed='N',
                cvsDate=timezone.now(),
            )
            new_conv.save()
            cvs_id = new_conv.cvsId

            # Multiple recipients if applicable (Match Java Line 894-916)
            for u in user_data_list:
                detail = SmsConversationsDetails(
                    cvsdCvsId=cvs_id,
                    cvsdMessage=send_message,
                    cvsdClientId=u['id'],
                    cvsdClientNumber=u['phone'],
                    cvsdSender='m',
                    cvsdDate=timezone.now(),
                )
                detail.save()

                # Send via Telnyx
                conversations_status_url = getattr(settings, 'CONVERSATIONS_STATUS_URL', '')
                msg = send_sms_telnyx(u['phone'], ph_chat_phone_number, 'text', send_message, 'first', None, conversations_status_url)
                cvsd_sid = msg.get('msgId', '')

                if cvsd_sid:
                    detail.cvsdSid = cvsd_sid
                    detail.cvsdDate = timezone.now()
                    detail.save()
        else:
            # Append to existing (Match Java Line 919-934)
            detail = SmsConversationsDetails(
                cvsdCvsId=cvs_id,
                cvsdMessage=send_message,
                cvsdClientId=cvs_email_id,
                cvsdClientNumber=cvsd_client_no,
                cvsdSender='m',
                cvsdDate=timezone.now(),
            )
            detail.save()

            # Send via Telnyx
            conversations_status_url = getattr(settings, 'CONVERSATIONS_STATUS_URL', '')
            msg = send_sms_telnyx(cvsd_client_no, ph_chat_phone_number, 'text', send_message, 'first', None, conversations_status_url)
            cvsd_sid = msg.get('msgId', '')

            if cvsd_sid:
                detail.cvsdSid = cvsd_sid
                detail.cvsdDate = timezone.now()
                detail.save()

        # Handle Campaign Transaction (Match Java Line 935-957)
        if tenant.ten_id:
            try:
                country_setting = CommonServices.country_setting_by_tenant_id(tenant.ten_id)
                if country_setting and number_of_sms > 0:
                    # Java uses findByConversations
                    trans = CampaignTransaction.objects.filter(
                        tran_campaign_id=cvs_id,
                        tran_type='sms conversations'
                    ).first()

                    conv_rate = country_setting.cnty_sms_conversations_per_price or 0
                    if trans:
                        trans.tran_total_amount = float(trans.tran_total_amount or 0) + (number_of_sms * float(trans.tran_member_rate or 0))
                        trans.tran_count_total_sms = (trans.tran_count_total_sms or 0) + number_of_sms
                        trans.save()
                    else:
                        CommonServices.saveCampaignTransaction(
                            cvs_id,
                            f"SMS Chat : {cvs_title}",
                            1,
                            "sms conversations",
                            None,
                            "uninvoiced",
                            None,
                            get_client_id_by_tenant_id(tenant_id),
                            "0",
                            number_of_sms * conv_rate,
                            conv_rate,
                            number_of_sms,
                            None,
                            None,
                            0
                        )
            except Exception as ex:
                traceback.print_exc()
                logger.error(f"SendConversations Transaction Error: {ex}")

        if not cvsd_sid:
            return api_response(500, 'Message Can Not Be Send.', res_body)

        return api_response(200, 'Message Send Successfully.', res_body)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"SendConversations Error: {e}")
        return api_response(500, 'Message Can Not Be Send.', res_body)


# ─────────────────────────────────────────────
# POST /smsInbox/closedConversations
# ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def closed_conversations(request):
    """POST /smsInbox/closedConversations"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        data = request.data
        cvsd_client_no = data.get('cvsdClientNo', '')
        member_phone = data.get('memberPhone', '')

        if not cvsd_client_no or not member_phone:
            return api_response(500, 'Conversations Not Exists.', res_body)

        convs = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id),
            cvsMemberNumber=member_phone,
        ).filter(
            Q(cvsTwilioNumber=cvsd_client_no) |
            Q(cvsId__in=SmsConversationsDetails.objects.filter(
                cvsdClientNumber=cvsd_client_no
            ).values('cvsdCvsId'))
        )

        if not convs.exists():
            return api_response(500, 'Conversations Not Exists.', res_body)

        for conv in convs:
            conv.cvsClosed = 'Y'
            conv.cvsClosedDate = timezone.now()
            conv.save()

        return api_response(200, 'Conversations Is Closed.', res_body)
    except Exception as e:
        logger.error(f"ClosedConversations Error: {e}")
        return api_response(500, 'Conversations Not Exists.', res_body)


# ─────────────────────────────────────────────
# POST /smsInbox/buyNumber
# ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def buy_number(request):
    """POST /smsInbox/buyNumber"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        data = request.data
        sub_tenant_id = int(data.get('subTenantId', 0))
        full_name = data.get('fullName', '')
        sub_full_name = data.get('subFullName', '')
        ph_chat_phone_number = data.get('phChatPhoneNumber', '')
        check_forwarding = data.get('checkForwardingYesNo', 'no')
        call_forwarding_country_code = data.get('callForwardingCountryCode', '')
        call_forwarding_number = data.get('callForwardingNumber', '')

        logged_user_id = sub_tenant_id if sub_tenant_id > 0 else tenant_id
        if sub_tenant_id > 0:
            display_name = f"{sub_full_name} {sub_tenant_id}"
        else:
            display_name = full_name

        client = Clients.objects.get(cliTenantId=tenant_id)

        sms_reply_url = getattr(settings, 'SMS_REPLY_URL', '')
        env_sys = getattr(settings, 'ENVSYS', 'QA')
        telnyx_base_url = getattr(settings, 'TELNYX_BASE_URL', '')
        telnyx_api_key = getattr(settings, 'TELNYX_API_KEY', '')
        telnyx_outbound_voice_profile_id = getattr(settings, 'TELNYX_OUTBOUND_VOICE_PROFILE_ID', '')
        site_url_backend = getattr(settings, 'SITE_URL_BACKEND', '')

        cli_sip_friendly_name = f"{env_sys.upper()} {display_name} {tenant_id}"
        out_result = telnyx_sub_account(
            sms_reply_url=sms_reply_url,
            cli_sip_friendly_name=cli_sip_friendly_name,
            ph_phone_number=ph_chat_phone_number,
            cli_sms_account_sid=client.cliSmsAccountSid or '',
            telnyx_base_url=telnyx_base_url,
            telnyx_api_key=telnyx_api_key,
            cli_sip_connection_id=client.cliSipConnectionId or '',
            site_url_backend=site_url_backend,
            telnyx_outbound_voice_profile_id=telnyx_outbound_voice_profile_id,
        )

        if out_result.get('error', ''):
            return api_response(500, out_result['error'], res_body)

        # Call forwarding
        if check_forwarding == 'yes' and call_forwarding_number:
            forward_number = call_forwarding_country_code + call_forwarding_number
            s_id = telnyx_call_forwarding(out_result.get('phSid', ''), forward_number, True, telnyx_base_url, telnyx_api_key)
            if s_id:
                NumberCallForwarding(
                    cfnTwilioNumber=ph_chat_phone_number,
                    cfnTwilioPhoneSid=out_result.get('phSid', ''),
                    cfnForwardingCountryCode=call_forwarding_country_code,
                    cfnForwardingNumber=call_forwarding_number,
                    cfnMemberId=get_client_id_by_tenant_id(tenant_id),
                    cfnDateTime=timezone.now(),
                ).save()

        # Update member
        client.cliSipFriendlyName = out_result.get('cliSipFriendlyName', '')
        client.cliSmsAccountSid = out_result.get('cliSmsAccountSid', '')
        client.save()
        renew_date_str = add_one_month() + " " + timezone.now().strftime('%H:%M:%S')
        renew_date_str = datetime.strptime(renew_date_str, '%Y-%m-%d %H:%M:%S')
        renew_date_str = timezone.make_aware(renew_date_str)
        PhoneNumbers.objects.create(
            phClientId=get_client_id_by_tenant_id(tenant_id),
            phPhoneNumber=out_result.get('phPhoneNumber', ''),
            phSid=out_result.get('phSid', ''),
            phHowUsed="CHAT",
            phDatePurchased=timezone.now(),
            phDateRenew=renew_date_str,
            phPhoneNumberClosed = 'N'
        )

        # Handle Campaign Transaction (to match Java)
        if logged_user_id:
            try:
                country_setting = CommonServices.country_setting_by_tenant_id(logged_user_id)
                if country_setting:
                    price = country_setting.cnty_sms_number_per_price or 0.0
                    CommonServices.saveCampaignTransaction(
                        None,
                        f"SMS Chat number purchased : {out_result.get('phPhoneNumber')}",
                        1,
                        "sms conversations number",
                        None,
                        "uninvoiced",
                        None,
                        get_client_id_by_tenant_id(tenant_id),
                        "0",
                        price,
                        price,
                        0,
                        None,
                        None,
                        0
                    )
            except Exception as ex:
                logger.error(f"BuyNumber CampaignTransaction Error: {ex}")

        return api_response(200, 'You Are Good To Go For Calling And SMS Chat', res_body)
    except Exception as e:
        logger.error(f"BuyNumber Error: {e}")
        return api_response(500, 'An error occurred while buying the number.', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/checkInboxForConversation/<clientNumber>
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def check_inbox_for_conversation(request, clientNumber):
    """GET /smsInbox/checkInboxForConversation/{clientNumber}"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        exists = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id),
            cvsId__in=SmsConversationsDetails.objects.filter(
                cvsdClientNumber=clientNumber
            ).values('cvsdCvsId')
        ).exists()
        res_body['status'] = exists
    except Exception as e:
        logger.error(f"CheckInboxForConversation Error: {e}")
        res_body['status'] = False
    return api_response(200, 'Fetch Data Successfully.', res_body)


# ─────────────────────────────────────────────
# DELETE /smsInbox/deleteSmsConversationsNumber/<tenantId>
# ─────────────────────────────────────────────
@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def delete_sms_conversations_number(request, tenantId):
    """DELETE /smsInbox/deleteSmsConversationsNumber/{tenantId}"""
    res_body = {'error': ''}
    try:
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenantId)
        phone_number = get_phone_numbers_first(tenant_details.tenant.ten_id, "CAMPAIGN")
        chat_phone_number = get_phone_numbers_first(tenant_details.tenant.ten_id, "CHAT")
        chat_ph_sid = chat_phone_number.phSid or ''

        if chat_ph_sid:
            telnyx_base_url = getattr(settings, 'TELNYX_BASE_URL', '')
            telnyx_api_key = getattr(settings, 'TELNYX_API_KEY', '')

            flag = delete_telnyx_number(chat_ph_sid, telnyx_base_url, telnyx_api_key)
            if flag == 1:
                # Delete call forwarding records
                NumberCallForwarding.objects.filter(cfnTwilioPhoneSid=chat_ph_sid, cfnMemberId=get_client_id_by_tenant_id(tenantId)).delete()

                # Close conversations for this number
                SmsConversations.objects.filter(
                    cvsTwilioNumber=chat_phone_number.phPhoneNumber
                ).update(cvsClosed='Y', cvsClosedDate=timezone.now())

                chat_phone_number.ph_phone_number_closed = 'Y'
                chat_phone_number.save()
            else:
                res_body['error'] = 'Oops !! There Is Some Problem While Sub Account Delete.'

        res_body['phPhoneNumber'] = phone_number.phPhoneNumber or ''
        res_body['phChatPhoneNumber'] = chat_phone_number.phPhoneNumber or ''

        if res_body['error'] == '':
            return api_response(200, 'Delete Phone Number Successfully.', res_body)
        return api_response(500, res_body['error'], res_body)
    except Exception as e:
        logger.error(f"DeleteSmsConversationsNumber Error: {e}")
        return api_response(500, 'An error occurred while deleting the number.', res_body)

# ─────────────────────────────────────────────
# POST /smsInbox/changeSmsConversationsNumber
# ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def change_sms_conversations_number(request):
    """POST /smsInbox/changeSmsConversationsNumber"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        data = request.data
        ph_chat_phone_number = data.get('phChatPhoneNumber', '')
        check_forwarding = data.get('checkForwardingYesNo', 'no')
        call_forwarding_country_code = data.get('callForwardingCountryCode', '')
        call_forwarding_number = data.get('callForwardingNumber', '')

        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
        chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
        default_chat_phone_number = get_phone_numbers_first(tenant_id, "DEFAULTCHAT")
        client = Clients.objects.get(cliTenantId=tenant_id)

        # Keep initial numbers for result/flags
        res_body['phPhoneNumber'] = phone_number.phPhoneNumber or ''
        res_body['phChatPhoneNumber'] = chat_phone_number.phPhoneNumber or ''

        chat_ph_sid = chat_phone_number.phSid

        flag = 0
        if phone_number.phPhoneNumber == chat_phone_number.phPhoneNumber:
            flag = 1

        flag_default = 0
        try:
            if chat_phone_number.phPhoneNumber == default_chat_phone_number.phPhoneNumber:
                flag_default = 1
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsConversationsNumber Error 1: {e}")

        telnyx_base_url = getattr(settings, 'TELNYX_BASE_URL', '')
        telnyx_api_key = getattr(settings, 'TELNYX_API_KEY', '')

        cli_sip_friendly_name = client.cliSipFriendlyName or ''
        out_result = change_telnyx_number(
            cli_sip_friendly_name=cli_sip_friendly_name,
            ph_phone_number=ph_chat_phone_number,
            cli_sms_account_sid=client.cliSmsAccountSid or '',
            ph_sid=chat_phone_number.phSid or '',
            telnyx_base_url=telnyx_base_url,
            telnyx_api_key=telnyx_api_key,
            cli_sip_connection_id=client.cliSipConnectionId or '',
        )

        # Call forwarding
        try:
            if check_forwarding == 'yes' and call_forwarding_number:
                forward_number = call_forwarding_country_code + call_forwarding_number
                s_id = telnyx_call_forwarding(out_result.get('phSid', ''), forward_number, True, telnyx_base_url, telnyx_api_key)
                if s_id:
                    NumberCallForwarding(
                        cfnTwilioNumber=ph_chat_phone_number,
                        cfnTwilioPhoneSid=out_result.get('phSid', ''),
                        cfnForwardingCountryCode=call_forwarding_country_code,
                        cfnForwardingNumber=call_forwarding_number,
                        cfnMemberId=get_client_id_by_tenant_id(tenant_id),
                        cfnDateTime=timezone.now(),
                    ).save()
        except Exception:
            pass

        # Close old conversations
        try:
            if chat_phone_number.phPhoneNumber:
                SmsConversations.objects.filter(
                    cvsTwilioNumber=chat_phone_number.phPhoneNumber
                ).exclude(cvsClosed='Y').update(cvsClosed='Y', cvsClosedDate=timezone.now())
        except Exception as ee:
            logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsConversationsNumber Error 2: {ee}")

        # Sms Campaign Close Start
        try:
            if chat_ph_sid:
                sms_id_list = list(CampaignsSms.objects.filter(
                    pnId=chat_phone_number.pnId
                ).values_list('smsId', flat=True))
                if sms_id_list:
                    _perform_close_campaign_logic(tenant_id, sms_id_list, "")
                PhoneNumbers.objects.filter(pnId=chat_phone_number.pnId).update(phPhoneNumberClosed='Y')
        except Exception as ee:
            logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsConversationsNumber Error 3: {ee}")
        # Sms Campaign Close End

        if not out_result.get('error', ''):
            try:
                client.cliSipFriendlyName = out_result.get('cliSipFriendlyName', '')
                client.cliSmsAccountSid = out_result.get('cliSmsAccountSid', '')
                client.save()
                renew_date_str = add_one_month() + " " + timezone.now().strftime('%H:%M:%S')
                renew_date_str = datetime.strptime(renew_date_str, '%Y-%m-%d %H:%M:%S')
                renew_date_str = timezone.make_aware(renew_date_str)
                if flag == 1:
                    ph_how_used = "CAMPAIGN"
                elif flag_default == 1:
                    ph_how_used = "DEFAULTCHAT"
                else:
                    ph_how_used = "CHAT"
                PhoneNumbers.objects.create(
                    phClientId=get_client_id_by_tenant_id(tenant_id),
                    phPhoneNumber=out_result.get('phPhoneNumber', ''),
                    phSid=out_result.get('phSid', ''),
                    phHowUsed=ph_how_used,
                    phDatePurchased=timezone.now(),
                    phDateRenew=renew_date_str,
                    phPhoneNumberClosed='N'
                )
                res_body['phPhoneNumber'] = phone_number.phPhoneNumber or ''
                res_body['phChatPhoneNumber'] = chat_phone_number.phPhoneNumber or ''
            except Exception as e:
                logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsConversationsNumber Error 4: {e}")

            # Handle Campaign Transaction (to match Java)
            if tenant_id:
                try:
                    country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
                    if country_setting:
                        price = country_setting.cnty_sms_number_per_price or 0.0
                        CommonServices.saveCampaignTransaction(
                            None,
                            f"New SMS Chat number purchased : {out_result.get('phPhoneNumber')}",
                            1,
                            "sms conversations number",
                            None,
                            "uninvoiced",
                            None,
                            get_client_id_by_tenant_id(tenant_id),
                            "0",
                            price,
                            price,
                            0,
                            None,
                            None,
                            0
                        )
                except Exception as ex:
                    logger.error(f"ChangeSmsConversationsNumber CampaignTransaction Error: {ex}")

            res_body['status'] = 'ok'
            res_body['msg'] = 'Your New SMS/MMS Number Ready To Use'
            return api_response(200, 'Your New SMS/MMS Number Ready To Use', res_body)
        else:
            res_body['status'] = 'error'
            res_body['msg'] = out_result.get('error')
            return api_response(500, out_result.get('error'), res_body)

    except Exception as e:
        logger.error(f"ChangeSmsConversationsNumber Error: {e}")
        return api_response(500, 'An error occurred.', res_body)


# ─────────────────────────────────────────────
# POST /smsInbox/setConversationNumber
# ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def set_conversation_number(request):
    """POST /smsInbox/setConversationNumber"""
    res_body = dict()
    try:
        data = request.data
        ph_chat_phone_number = data.get('conversationsTwilioNumber', '')
        ph_chat_sid = data.get('conversationsSubAccountPhoneSId', '')
        default_yn = data.get('defaultYN', 'N')

        chat_phone_number = PhoneNumbers.objects.get(phPhoneNumber=ph_chat_phone_number, phSid=ph_chat_sid)
        chat_phone_number.phHowUsed = "CHAT"
        if default_yn == 'Y':
            chat_phone_number.phHowUsed = "DEFAULTCHAT"
        chat_phone_number.save()
        res_body['msg'] = 'success'
        return api_response(200, 'Conversation Number Set Successfully', res_body)
    except Exception as e:
        logger.error(f"SetConversationNumber Error: {e}")
        return api_response(500, 'An error occurred.', res_body)


# ─────────────────────────────────────────────
# POST /smsInbox/campaignCloseConversation
# ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def campaign_close_conversation(request):
    """POST /smsInbox/campaignCloseConversation"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        data = request.data
        tenant_phone = data.get('tenantPhone', '')

        convs = SmsConversations.objects.filter(
            cvsMemberId=get_client_id_by_tenant_id(tenant_id),
            cvsMemberNumber=tenant_phone,
        )

        if not convs.exists():
            res_body['isClosed'] = False
            return api_response(200, 'All Conversation Successfully', res_body)

        for conv in convs:
            conv.cvsClosed = 'Y'
            conv.cvsClosedDate = timezone.now()
            conv.save()

        res_body['isClosed'] = True
        return api_response(200, 'All Conversation Successfully', res_body)
    except Exception as e:
        logger.error(f"CampaignCloseConversation Error: {e}")
        res_body['isClosed'] = False
        return api_response(500, 'An error occurred.', res_body)


# ─────────────────────────────────────────────
# POST /smsInbox/smsStatusUrl  (hidden - webhook)
# ─────────────────────────────────────────────
@api_view(['POST'])
def sms_status_url(request: Request):
    """POST /smsInbox/smsStatusUrl (hidden webhook)"""
    logger.info(f"smsStatusUrl Response: {request.body}")
    return api_response(200, 'success')


# ─────────────────────────────────────────────
# GET /smsInbox/checkDefaultConversationsNumber
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def check_default_conversations_number(request):
    """GET /smsInbox/checkDefaultConversationsNumber"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    res_body['defaultConversationsTwilioNumber'] = ''
    res_body['defaultConversationsSubAccountPhoneSId'] = ''
    res_body['numberCallForwarding'] = None
    res_body['smsId'] = 0
    try:
        phone_number = get_phone_numbers_first(tenant_id, "DEFAULTCHAT")
        ph_phone_number = phone_number.phPhoneNumber if phone_number else ''
        ph_sid = phone_number.phSid if phone_number else ''

        # Call forwarding info
        cfn = NumberCallForwarding.objects.filter(
            cfnTwilioPhoneSid=ph_sid, cfnMemberId=get_client_id_by_tenant_id(tenant_id)
        ).first()
        if cfn:
            res_body['numberCallForwarding'] = {
                'cfnId': cfn.cfnId,
                'cfnTwilioNumber': cfn.cfnTwilioNumber or '',
                'cfnTwilioPhoneSid': cfn.cfnTwilioPhoneSid or '',
                'cfnForwardingCountryCode': cfn.cfnForwardingCountryCode or '',
                'cfnForwardingNumber': cfn.cfnForwardingNumber or '',
            }

        if ph_phone_number:
            res_body['defaultConversationsTwilioNumber'] = ph_phone_number
            res_body['defaultConversationsSubAccountPhoneSId'] = ph_sid
    except Exception as e:
        logger.error(f"CheckDefaultConversationsNumber Error: {e}")
    return api_response(200, 'Check Default Conversations Number', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/checkConversationsNumberStatus  (hidden)
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def check_conversations_number_status(request):
    """GET /smsInbox/checkConversationsNumberStatus (hidden)"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        flag = request.query_params.get('flag', 'conversations')
        client = Clients.objects.get(cliTenantId=tenant_id)

        telnyx_base_url = getattr(settings, 'TELNYX_BASE_URL', '')
        telnyx_api_key = getattr(settings, 'TELNYX_API_KEY', '')

        if flag == 'conversations':
            phone_number = get_phone_numbers_first(tenant_id, "CHAT")
            ph_sid = phone_number.phSid if phone_number else ''
        else:
            phone_number = get_phone_numbers_first(tenant_id, "DEFAULTCHAT")
            ph_sid = phone_number.phSid if phone_number else ''

        number_assign = check_assign_to_number(
            cli_sms_account_sid=client.cliSmsAccountSid or '',
            ph_sid=ph_sid,
            telnyx_base_url=telnyx_base_url,
            telnyx_api_key=telnyx_api_key,
            cli_sip_connection_id=client.cliSipConnectionId or '',
        )
        number_status = 'Provisioned' if number_assign == 'Yes' else 'Unprovisioned'
        res_body['numberStatus'] = number_status
    except Exception as e:
        logger.error(f"CheckConversationsNumberStatus Error: {e}")
        res_body['numberStatus'] = 'Unprovisioned'
    return api_response(200, 'Successfully', res_body)


# ─────────────────────────────────────────────
# GET /smsInbox/getConversationsNumber
# ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_conversations_number(request):
    """GET /smsInbox/getConversationsNumber"""
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    res_body['numberCallForwarding'] = None
    try:
        chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
        phone_sid = chat_phone_number.phSid if chat_phone_number else ''
        res_body['cfnTwilioPhoneSid'] = phone_sid

        cfn = NumberCallForwarding.objects.filter(
            cfnTwilioPhoneSid=phone_sid, cfnMemberId=get_client_id_by_tenant_id(tenant_id)
        ).first()
        if cfn:
            res_body['numberCallForwarding'] = {
                'cfnId': cfn.cfnId,
                'cfnTwilioNumber': cfn.cfnTwilioNumber or '',
                'cfnTwilioPhoneSid': cfn.cfnTwilioPhoneSid or '',
                'cfnForwardingCountryCode': cfn.cfnForwardingCountryCode or '',
                'cfnForwardingNumber': cfn.cfnForwardingNumber or '',
            }
    except Exception as e:
        logger.error(f"GetConversationsNumber Error: {e}")
    return api_response(200, 'Successfully', res_body)
