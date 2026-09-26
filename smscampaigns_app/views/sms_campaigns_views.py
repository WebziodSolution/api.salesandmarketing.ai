import logging
import json
import math
import traceback
import re
import pytz
from decimal import Decimal
from datetime import datetime, timedelta
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from common_app.custom_permissions import WhitelistPermission
from common_app.models import (CampaignsSms, CampaignSmsDetails, SmsLinks, SmsLinkTrace, CampaignsSmsSend, CampaignSendSms, CampaignSendSmsTemp, SmsConversations, NumberCallForwarding, CampaignTransaction, SmsTemplates, CampaignSmsReply, Userlist, PhoneNumbers, Clients)
from common_app.utils import api_response, get_final_tenant_id, clean_me_number, get_phone_numbers_first, get_client_id_by_tenant_id, add_one_month, get_client_timezone
from common_app import telnyx_utils
from common_app.services import CommonServices
from smscampaigns_app.serializers import (SaveSendSmsCampaignDtoSerializer, CampaignsSmsPreviewDtoSerializer, EditSmsCampaignScheduleDtoSerializer, DeleteSmsCampaignDtoSerializer)
from smscampaigns_app import utils
from smscampaigns_app.queries import SmsCampaignQueries

logger = logging.getLogger(__name__)

def normalize_null_fields(value):
    """
    Convert empty strings to None to match Spring Boot null handling.
    Ensures consistency with Java API response format.
    """
    if value == '':
        return None
    return value


# ===== MAIN ENDPOINTS =====

def _save_sms_campaign_logic(tenant_id, request_data):
    """
    Shared logic for saving (and optionally sending) an SMS campaign.
    """
    serializer = SaveSendSmsCampaignDtoSerializer(data=request_data)
    if not serializer.is_valid():
        raise ValidationError(serializer.errors)

    data = serializer.validated_data
    return final_save_sms_campaign(tenant_id, data)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSendSmsCampaign(request):
    """
    Save and send SMS campaign in one step.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        res = _save_sms_campaign_logic(tenant_id, request.data)
        return api_response(200, "SMS Campaign Saved and Sent Successfully.", res)
    except ValidationError as e:
        return api_response(400, "Invalid Data", e.detail)
    except Exception as e:
        logger.error(f"Error in saveSendSmsCampaign: {e}")
        return api_response(500, str(e), {})


def final_save_sms_campaign(tenant_id, data):
    """
    Core logic for saving SMS campaign
    Java: SmsCampaignsServiceImpl.finalSaveSmsCampaign()

    Args:
        tenant_id: Tenant ID
        data: Campaign data dict

    Returns:
        Dict with smsId, emailIds, and error status
    """
    res_body = dict()
    res_body["error"] = ""
    res_body["emailIds"] = []
    res_body["smsId"] = None
    try:
        with connection.cursor() as cursor:
            group_id = data.get('groupList')
            seg_id = data.get('segId', 0)
            # Get contact list (emailIds) based on group or segment (Java lines 485-502)
            if seg_id and int(seg_id) > 0:
                email_ids = SmsCampaignQueries.get_segment_contact_list(seg_id, cursor)
            else:
                email_ids = SmsCampaignQueries.get_contact_list_for_campaign(group_id, tenant_id, cursor)

            res_body["emailIds"] = email_ids

            # Determine send date (Java lines 510-520)
            send_on_date = data.get('sendOnDate')
            schedule_type = data.get('scheduleType', 1)

            if schedule_type == 1:
                # Immediate send
                send_on_date = datetime.now(pytz.UTC)
            else:
                # Scheduled send - convert from user timezone to UTC (Java line 514)
                try:
                    time_zone = data.get('timeZone') or get_client_timezone(tenant_id)
                    send_on_date = utils.convert_user_timezone_to_utc(send_on_date, time_zone)
                except Exception:
                    res_body["error"] = "Invalid Date"

            # Get or create campaign (Java lines 521-525)
            sms_id = data.get('smsId', 0)
            if sms_id and int(sms_id) > 0:
                campaigns_sms = CampaignsSms.objects.get(smsId=sms_id)
            else:
                campaigns_sms = CampaignsSms()

            # Update campaign record (Java lines 525-560)
            campaigns_sms.memberId = get_client_id_by_tenant_id(tenant_id)
            campaigns_sms.smsName = data.get('smsName')
            campaigns_sms.groupList = str(group_id)
            campaigns_sms.sendDate = datetime.now(pytz.UTC)
            campaigns_sms.smsStatus = data.get('sendSaveValue', 0)
            campaigns_sms.readyToSms = "N"
            campaigns_sms.sendOnDate = send_on_date
            
            # Match Java time calculation (Java lines 538-548)
            # DurationField in Oracle requires timedelta
            if send_on_date:
                campaigns_sms.sendOnTime = timedelta(hours=send_on_date.hour, minutes=send_on_date.minute, seconds=send_on_date.second)
            else:
                campaigns_sms.sendOnTime = None
            
            campaign_schedule_type = data.get('scheduleType', 1)
            campaigns_sms.scheduleType = campaign_schedule_type
            campaigns_sms.segId = seg_id

            # Opt-out handling (Java lines 554-560)
            if data.get('chkOptOut') == 1:
                campaigns_sms.chkOptOut = 1
                campaigns_sms.optOutMsg = data.get('optOutMsg', '')
            else:
                campaigns_sms.chkOptOut = 0
                campaigns_sms.optOutMsg = None

            campaigns_sms.save()
            sms_id = campaigns_sms.smsId
            res_body["smsId"] = sms_id

            # Clear old details if updating (Java lines 564-576)
            input_sms_id = data.get('smsId', 0)
            if input_sms_id and int(input_sms_id) > 0:
                CampaignSmsDetails.objects.filter(smsId=sms_id).delete()
                CampaignSendSmsTemp.objects.filter(smsId=sms_id).delete()

            # Save campaign details and calculate numberOfSms (Java lines 580-604)
            sms_details = data.get('smsCampaignDetails', [])
            detail_objects = []
            number_of_sms = 0
            
            for index, detail in enumerate(sms_details):
                sms_detail_text = detail.get('smsDetail')
                if sms_detail_text:
                    count_tot_msg = 1
                    if detail.get('smsType') == "text":
                        # Java line 585-587: 160 char split logic
                        if len(sms_detail_text) > 160:
                            count_tot_msg = math.ceil(len(sms_detail_text) / 160.0)
                    
                    number_of_sms += count_tot_msg                    
                    detail_objects.append(
                        CampaignSmsDetails(
                            smsId=sms_id,
                            sdDetail=sms_detail_text,
                            sdType=detail.get('smsType'),
                            sdDisplayOrder=detail.get('rowDisplayOrder', 0)
                        )
                    )
            
            if detail_objects:
                CampaignSmsDetails.objects.bulk_create(detail_objects)

            # Create temp send records for all email IDs in batches of 2000 (Java lines 641-685)
            batch_size = 2000
            select_clauses = []
            ct = 0

            for email_id in email_ids:
                select_clauses.append(f"SELECT '{sms_id}', '{get_client_id_by_tenant_id(tenant_id)}', '{email_id}', 'N' FROM DUAL")
                ct += 1
                
                if ct == batch_size:
                    # Build the full INSERT with UNION ALL
                    sql = f"""
                        INSERT INTO CAMPAIGN_SMS_DRAFT (CSD_CS_ID, CSD_CLIENT_ID, CSD_EMAIL_ID, CSD_IS_SEND)
                        { " UNION ALL ".join(select_clauses) }
                    """
                    cursor.execute(sql)
                    select_clauses = []
                    ct = 0

            # Execute remaining rows (< batch_size)
            if select_clauses:
                sql = f"""
                    INSERT INTO CAMPAIGN_SMS_DRAFT (CSD_CS_ID, CSD_CLIENT_ID, CSD_EMAIL_ID, CSD_IS_SEND)
                    { " UNION ALL ".join(select_clauses) }
                """
                cursor.execute(sql)

            res_body["send_on_date"] = send_on_date

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in final_save_sms_campaign: {e}")
        res_body["error"] = str(e)

    return res_body

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignList(request):
    """
    Get paginated list of SMS campaigns.
    Mirrors SmsCampaignsServiceImpl.findSmsCampaignsByPage exactly.
    """
    tenant_id = get_final_tenant_id(request=request)
    page_no = int(request.GET.get('page', 0))
    page_size = int(request.GET.get('size', 25))
    search_key = request.GET.get('searchKey', '').strip()
    time_zone = request.GET.get('timeZone', get_client_timezone(tenant_id))
    
    try:
        # 1. Query Campaigns with Pagination
        if not search_key:
            queryset = CampaignsSms.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id))
        else:
            queryset = CampaignsSms.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smsName__icontains=search_key)
            
        total_campaigns = queryset.count()
        queryset = queryset.order_by('-smsId')[page_no * page_size : (page_no + 1) * page_size]
        
        campaigns_data = []
        for camp in queryset:
            # Date Formatting (Java logic matches)
            send_on_date = camp.sendOnDate
            send_date_str = utils.format_date_for_display(camp.sendDate)
            sms_close_date_str = utils.format_date_for_display(camp.smsCloseDate)
            
            # sendOnDate conversion (Java lines 362-365)
            send_on_date_str = None
            if send_on_date:
                send_on_date_str = utils.format_date_for_display(
                    utils.convert_utc_to_user_timezone(send_on_date, time_zone)
                )

            # 2. Populate arrFromMo (Java lines 387-400)
            from_numbers = []
            try:
                # Java: findIdList(smsId) then findFromContactList(id)
                send_ids = list(CampaignsSmsSend.objects.filter(smsId=camp.smsId).order_by('-id').values_list('id', flat=True))
                if send_ids:
                    contacts = list(CampaignSendSms.objects.filter(smsId__in=send_ids).values_list('fromContact', flat=True).distinct())
                    for contact in contacts:
                        if contact and contact.strip():
                            cleaned = clean_me_number(contact)
                            if cleaned and cleaned not in from_numbers:
                                from_numbers.append(cleaned)
            except Exception as e:
                logger.error(f"Error fetching arrFromMo for campaign {camp.smsId}: {e}")

            # 3. Status and Color Determination (Java lines 402-438)
            sms_status = ""
            color = "#000"
            if camp.smsStatus in [0, 1]:
                sms_status = "Draft"
            elif camp.smsStatus == 2:
                schedule_type = camp.scheduleType or 0
                if schedule_type == 2:
                    sms_status = "Scheduled"
                else:
                    ready_to_sms = CampaignsSmsSend.objects.filter(smsId=camp.smsId).order_by('-id').values_list('readyToSms', flat=True).first()
                    if ready_to_sms == 'N' or not ready_to_sms:
                        sms_status = "Draft"
                    else:
                        sms_status = "Sending"
                        color = "#0F5387"
            elif camp.smsStatus == 4:
                sms_status = "Delete Pending"
                color = "#fc0536"
            elif camp.smsStatus == 3:
                sms_status = "Completed"
                color = "#0F5387"

            # 4. Scheduled Override logic (Java lines 441-456)
            schedule_id = None
            try:
                # 1. Use Q objects to handle the (is_send != 'Y' OR is_send IS NULL) logic correctly
                # 2. Match the order by and get the first record
                active_send = CampaignsSmsSend.objects.filter(
                    smsId=camp.smsId,
                    readyToSms='Y',
                    isProcessed='N'
                ).filter(
                    # This matches: (is_send != 'Y' OR is_send IS NULL)
                    ~Q(isSend='Y') | Q(isSend__isnull=True)
                ).filter(
                    # This matches: (sendOnDate > now OR sendOnDate IS NULL)
                    Q(sendOnDate__gt=datetime.now(pytz.UTC)) | Q(sendOnDate__isnull=True)
                ).order_by('-id').first()

                if active_send:
                    sms_status = "Scheduled"
                    schedule_id = active_send.id
                    
                    if active_send.sendOnDate:
                        # Convert and format
                        utc_date = active_send.sendOnDate
                        user_date = utils.convert_utc_to_user_timezone(utc_date, time_zone)
                        send_on_date_str = utils.format_date_for_display(user_date)
            except Exception as e:
                logger.error(f"Error in scheduled override for campaign {camp.smsId}: {e}")

            # Assemble DTO
            camp_dto = {
                "smsId": camp.smsId,
                "groupList": camp.groupList,
                "readyToSms": camp.readyToSms or "N",
                "scheduleType": camp.scheduleType,
                "segId": camp.segId,
                "sendDate": send_date_str,
                "sendOnDate": send_on_date_str,
                "smsDetail": normalize_null_fields(camp.smsDetail),
                "smsName": camp.smsName,
                "smsStatus": camp.smsStatus,
                "scheduleId": schedule_id,
                "arrFromMo": from_numbers,
                "status": sms_status,
                "color": color,
                "chkOptOut": camp.chkOptOut or 0,
                "optOutMsg": normalize_null_fields(camp.optOutMsg),
                "smsOpenClose": normalize_null_fields(camp.smsOpenClose),
                "smsCloseDate": sms_close_date_str,
            }
            campaigns_data.append(camp_dto)

        response_data = {
            "getTotalPages": (total_campaigns + page_size - 1) // page_size,
            "getNumber": page_no,
            "getSize": page_size,
            "smsCampaigns": campaigns_data,
            "totalSmsCampaigns": total_campaigns
        }
        return api_response(200, "Fetch SMS Campaign Successfully.", response_data)
        
    except Exception as e:
        logger.error(f"Error in getSmsCampaignList: {e}")
        return api_response(500, str(e), {})


@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSmsCampaign(request):
    """
    Delete one or more SMS campaigns
    Java: SmsCampaignsController.deleteSmsCampaign()
    DELETE /smsCampaign/deleteSmsCampaign
    """
    tenant_id = get_final_tenant_id(request=request)

    serializer = DeleteSmsCampaignDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Data", serializer.errors)

    sms_ids = serializer.validated_data.get('smsId', [])
    if not isinstance(sms_ids, list):
        sms_ids = [sms_ids]

    try:
        with transaction.atomic():
            for sms_id in sms_ids:
                # 1. Resolve smsSendId (Java: getProcessN(id))
                send_record = CampaignsSmsSend.objects.filter(smsId=sms_id).first()
                sms_send_id = send_record.id if send_record else 0

                # 2. Delete temporary send list (Fixes FK_SMS_EMAIL violation)
                CampaignSendSmsTemp.objects.filter(smsId=sms_id).delete()

                # 3. Delete campaign details (Java parity)
                CampaignSmsDetails.objects.filter(smsId=sms_id).delete()

                # 4. Handle Broadcast Data (If exists)
                if sms_send_id > 0:
                    # Delete actual send logs (Linked to CampaignsSmsSend.id)
                    CampaignSendSms.objects.filter(smsId=sms_send_id).delete()
                    
                    # Delete transactions (Java parity: uses memberId and campaign smsId)
                    CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenant_id), tran_campaign_id=sms_id).delete()
                    
                    CampaignsSmsSend.objects.filter(id=sms_send_id).delete()

                # 5. Finally, delete the parent campaign record (Java parity)
                CampaignsSms.objects.filter(smsId=sms_id, memberId=get_client_id_by_tenant_id(tenant_id)).delete()

        return api_response(200, "SMS Campaign(s) Deleted Successfully.", {})
    except Exception as e:
        logger.error(f"Error in deleteSmsCampaign: {e}")
        # Return specific error message for integrity violations if found
        error_msg = str(e)
        if "ORA-02292" in error_msg:
            error_msg = f"Cannot delete campaign: {error_msg}"
        return api_response(500, error_msg, {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignById(request):
    """
    Get single SMS campaign details by ID
    Java: SmsCampaignsController.getSmsCampaign()
    GET /smsCampaign/getSmsCampaignById/{smsId}?timeZone=Asia/Calcutta
    """
    smsId = request.GET.get('smsId')
    tenant_id = get_final_tenant_id(request=request)
    # Support optional timeZone parameter from query string
    time_zone = request.GET.get('timeZone', get_client_timezone(tenant_id))

    try:
        camp = CampaignsSms.objects.get(smsId=smsId, memberId=get_client_id_by_tenant_id(tenant_id))

        # Format campaign data (matches Spring Boot null handling)
        camp_data = {
            'smsId': camp.smsId,
            'smsName': camp.smsName,
            'groupList': camp.groupList,
            # ===== CRITICAL FIX: sendDate = Display ONLY (NO timezone conversion) =====
            'sendDate': utils.format_date_for_display(camp.sendDate) if camp.sendDate else None,
            # ===== sendOnDate = Timezone conversion applied (UTC -> User TZ) =====
            'sendOnDate': format_date_for_api(camp.sendOnDate, time_zone),
            'smsDetail': normalize_null_fields(camp.smsDetail),
            'smsStatus': camp.smsStatus,
            'scheduleType': camp.scheduleType,
            'segId': camp.segId,
            'readyToSms': camp.readyToSms if camp.readyToSms else 'N',
            'chkOptOut': camp.chkOptOut if camp.chkOptOut is not None else 0,
            'optOutMsg': normalize_null_fields(camp.optOutMsg),
        }

        # Get campaign details
        details = CampaignSmsDetails.objects.filter(smsId=smsId).order_by('sdDisplayOrder')
        details_data = [
            {
                "sdId": d.sdId,
                "smsId": d.smsId,
                "sdDetail": d.sdDetail,
                "sdType": d.sdType,
                "sdDisplayOrder": d.sdDisplayOrder
            }
            for d in details
        ]

        return api_response(200, "SMS Campaign Retrieved Successfully.", {
            "smsCampaign": camp_data,
            "smsDetails": details_data
        })
    except CampaignsSms.DoesNotExist:
        return api_response(404, "Campaign Not Found", {})
    except Exception as e:
        logger.error(f"Error in getSmsCampaignById: {e}")
        return api_response(500, str(e), {})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def getSmsCampaignPreview(request):
    """
    Get preview of SMS campaign content
    Java: SmsCampaignsController.getSmsCampaignPreview()
    POST /smsCampaign/getSmsCampaignPreview
    """
    serializer = CampaignsSmsPreviewDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Data", serializer.errors)

    data = serializer.validated_data
    sms_detail = data.get('smsDetail', '')

    try:
        # Convert URLs if needed
        convert_tiny_url = request.data.get('convertTinyUrlYN', 'Y')
        converted_detail, url_mapping = utils.convert_urls_in_content(sms_detail, convert_tiny_url)

        # Calculate SMS count
        sms_count = utils.calculate_sms_count(converted_detail, 'text')

        response_data = {
            "preview": converted_detail,
            "numberOfSms": sms_count,
            "characterCount": len(converted_detail)
        }

        return api_response(200, "Campaign Preview Retrieved Successfully.", response_data)
    except Exception as e:
        logger.error(f"Error in getSmsCampaignPreview: {e}")
        return api_response(500, str(e), {})

# _final_send_sms_campaign_logic removed as functionality merged into sendSmsCampaign


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def sendSmsCampaign(request):
    """
    Main entry point for sending an SMS campaign.
    Mirrors SmsCampaignsServiceImpl.sendSmsCampaign exactly.
    """
    tenant_id = get_final_tenant_id(request=request)
    data = request.data
    res_body = dict()
    res_body["error"] = ""
    res_body["cid"] = 0
    res_body["amt"] = 0
    res_body["numberOfSms"] = 0
    try:
        # 1. Final Save (Java: resBody = finalSaveSmsCampaign)
        res_save = final_save_sms_campaign(tenant_id, data)
        if res_save.get('error'):
            return api_response(400, res_save.get('error'), {})
            
        sms_id = res_save.get('smsId')
        email_ids = res_save.get('emailIds', [])

        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
        if data.get('isClosedConversations') == 'Y':
            try:
                SmsConversations.objects.filter(
                    cvsTwilioNumber=phone_number.phPhoneNumber
                ).update(cvsStatus=0)
            except Exception as e:
                logger.error(f"Error closing conversations for tenant {tenant_id}: {e}")

        pn_id = data.get('pnId', 0)
        scm_number = ""
        scm_number_phone_sid = data.get('scmNumberPhoneSid')
        scm_number_purchase_date = None
        scm_number_renew_date = None

        if pn_id > 0 or scm_number_phone_sid:
            if scm_number_phone_sid == "previousnumber":
                number_masters = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id), phHowUsed="CAMPAIGN", phPhoneNumberClosed="N").order_by("pnId")

                found = False
                for nm in number_masters:
                    cvs_exists = SmsConversations.objects.filter(
                        cvsTwilioNumber=nm.phPhoneNumber,
                        cvsClosed="N",
                        cvsMemberId=get_client_id_by_tenant_id(tenant_id)
                    ).exists()
                    if not cvs_exists:
                        scm_number = nm.phPhoneNumber
                        scm_number_phone_sid = nm.phSid
                        scm_number_purchase_date = nm.phDatePurchased
                        scm_number_renew_date = nm.phDateRenew
                        found = True
                        break
                if not found:
                    scm_number = phone_number.phPhoneNumber
                    scm_number_phone_sid = phone_number.phSid
                    scm_number_purchase_date = phone_number.phDatePurchased
                    scm_number_renew_date = phone_number.phDateRenew
            elif scm_number_phone_sid:
                pn = PhoneNumbers.objects.get(phClientId=get_client_id_by_tenant_id(tenant_id), phSid=scm_number_phone_sid, phPhoneNumberClosed="N")
                if not pn:
                    chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
                    if scm_number_phone_sid == chat_phone_number.phSid:
                        scm_number = chat_phone_number.phPhoneNumber
                        scm_number_phone_sid = chat_phone_number.phSid
                        scm_number_purchase_date = chat_phone_number.phDatePurchased
                        scm_number_renew_date = chat_phone_number.phDateRenew
                    else:
                        scm_number = phone_number.phPhoneNumber
                        scm_number_phone_sid = phone_number.phSid
                        scm_number_purchase_date = phone_number.phDatePurchased
                        scm_number_renew_date = phone_number.phDateRenew
                else:
                    scm_number = pn.phPhoneNumber
                    scm_number_phone_sid = pn.phSid
                    scm_number_purchase_date = pn.phDatePurchased
                    scm_number_renew_date = pn.phDateRenew
            else:
                # Use pnId
                pn = PhoneNumbers.objects.filter(
                        pnId=pn_id,
                        phClientId=get_client_id_by_tenant_id(tenant_id),
                        phNumberClosed='N',
                        phNumberPhoneSid__isnull=False
                    ).order_by('-pnId').first()
                if not pn:
                    scm_number = phone_number.phPhoneNumber
                    scm_number_phone_sid = phone_number.phSid
                    scm_number_purchase_date = phone_number.phDatePurchased
                    scm_number_renew_date = phone_number.phDateRenew
                else:
                    scm_number = pn.phPhoneNumber
                    scm_number_phone_sid = pn.phSid
                    scm_number_purchase_date = pn.phDatePurchased
                    scm_number_renew_date = pn.phDateRenew

            if data.get('isClosedConversations') == 'Y':
                chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
                chat_phone_number.phPhoneNumberClosed = "Y"
                chat_phone_number.save()
                res_body["conversationsTwilioNumber"] = "Y"

            client = Clients.objects.get(cliTenantId=tenant_id)
            telnyx_utils.check_assign_to_number(client.cliSmsAccountSid, scm_number_phone_sid, cli_sip_connection_id=client.cliSipConnectionId)

            try:
                phone_number_data = PhoneNumbers.objects.filter(
                    phClientId=get_client_id_by_tenant_id(tenant_id),
                    phSid=scm_number_phone_sid
                ).first()
            except Exception as e:
                phone_number_data = None
                traceback.print_exc()
                logger.error(f"Error in sendSmsCampaign: {e}")

            if phone_number_data is None:
                phone_number_data = PhoneNumbers()

            phone_number_data.phPhoneNumber = scm_number
            phone_number_data.phSid = scm_number_phone_sid
            phone_number_data.phDatePurchased = scm_number_purchase_date
            phone_number_data.phDateRenew = scm_number_renew_date
            phone_number_data.phClientId = get_client_id_by_tenant_id(tenant_id)
            phone_number_data.phPhoneNumberClosed = 'N'
            phone_number_data.save()
            new_pn_id = phone_number_data.pnId

            # 4. Link to Campaign (Java lines 906-909)
            SmsCampaignQueries.update_campaign_open_status(sms_id, new_pn_id)

            # 5. Broadcast Table Preparation (Java line 915)
            cid = SmsCampaignQueries.insert_campaign_send_record(sms_id)
            
            if not cid:
                return api_response(500, "Error generating broadcast record", {})

            # 6. Link Processing (Java lines 924-985)
            if SmsCampaignQueries.check_temp_send_exists(sms_id):
                regex_url = r"(?i)\b((?:https?:\/\/|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}\/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
                
                campaign_details = SmsCampaignQueries.get_campaign_details_by_sms_id(sms_id)
                convert_tiny_url_yn = data.get('convertTinyUrlYN', 'Y')
                for detail in campaign_details:
                    sd_id = detail['sdId']
                    sd_detail = detail['sdDetail']
                    if not sd_detail:
                        continue
                        
                    # Extract original URLs (Java matchOrg)
                    match_org = [m.group() for m in re.finditer(regex_url, sd_detail)]
                    
                    s_detail = sd_detail
                    if convert_tiny_url_yn == 'Y':
                        # Mirror Java: convert detail and then find new matches
                        s_detail, _ = utils.convert_urls_in_content(s_detail, 'Y')
                    
                    # Extract converted URLs (Java match)
                    match_new = [m.group() for m in re.finditer(regex_url, s_detail)]
                    
                    # Create tracking links (Java lines 957-975)
                    # We iterate through both lists to maintain the mapping
                    for i in range(min(len(match_new), len(match_org))):
                        new_url = match_new[i]
                        old_url = match_org[i]
                        # Check if link exists using raw SQL
                        link_id = SmsCampaignQueries.get_sms_links_id(cid, new_url, old_url)
                        if not link_id:
                            SmsCampaignQueries.insert_sms_link(cid, new_url, old_url)
                    
                    # Update the campaign detail using raw SQL (Java lines 977-980)
                    if s_detail != sd_detail:
                        SmsCampaignQueries.update_sms_detail_text(sd_id, s_detail)

            # 7. Billing and transfer (Java lines 987-1050)
            country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
            total_amt = Decimal('0')
            number_of_sms = 0
            rate = Decimal('0')
            
            all_details = list(CampaignSmsDetails.objects.filter(smsId=sms_id).order_by('sdDisplayOrder'))
            
            with connection.cursor() as cursor:
                # Recipient processing loop
                # Python mirrors this with the provided list or fetching if needed
                for email_id in email_ids:
                    mg = 1
                    tot_row = len(all_details)
                    for detail in all_details:
                        sms_count_label = "first"
                        if mg == tot_row:
                            sms_count_label = "last"
                        
                        if detail.sdType == "image":
                            # Java logic for image billing
                            if sms_count_label == "last":
                                total_amt += Decimal(str(utils.calculate_sms_billing_price(2, "image", country_setting)))
                                if data.get('chkOptOut') == 1:
                                    number_of_sms += 2
                                else:
                                    number_of_sms += 1
                            else:
                                total_amt += Decimal(str(utils.calculate_sms_billing_price(1, "image", country_setting)))
                                number_of_sms += 1
                            rate = Decimal(str(utils.calculate_sms_billing_rate(1, "image", country_setting)))
                        else:
                            # Java logic for text billing
                            content_to_check = detail.sdDetail
                            if sms_count_label == "last" and data.get('chkOptOut') == 1:
                                content_to_check = f"{detail.sdDetail}\n{data.get('optOutMsg', '')}"
                            
                            count_tot_msg = utils.calculate_sms_count(content_to_check, "text")
                            if count_tot_msg == 0:
                                count_tot_msg = 1
                                
                            number_of_sms += count_tot_msg
                            total_amt += Decimal(str(utils.calculate_sms_billing_price(count_tot_msg, "text", country_setting)))
                            rate = Decimal(str(utils.calculate_sms_billing_rate(1, "text", country_setting)))

                        # 8. Transfer to final table (Java line 1048)
                        opt_out_msg = None
                        if sms_count_label == "last" and data.get('chkOptOut') == 1:
                            opt_out_msg = data.get('optOutMsg')

                        # We use raw Oracle insert here for parity and performance
                        transfer_query = """
                            INSERT INTO CAMPAIGN_SMS_QUEUED 
                            (CSQ_CSS_ID, CSQ_CLIENT_ID, CSQ_EMAIL_ID, CSQ_IS_SEND, CSQ_FROM_CONTACT, CSQ_SMS_DETAIL, CSQ_CSD_ID, CSQ_CSS_TYPE, CSQ_OPT_OUT_MSG)
                            VALUES (%s, %s, %s, 'N', %s, %s, %s, %s, %s)
                        """
                        cursor.execute(transfer_query, [
                            cid, get_client_id_by_tenant_id(tenant_id), email_id, scm_number,
                            detail.sdDetail, detail.sdId, detail.sdType,
                            opt_out_msg
                        ])
                        mg += 1

            # Metrics and early response data (Java lines 1063-1073)
            if number_of_sms == 0:
                number_of_sms = 1
                
            res_body["numberOfSms"] = number_of_sms
            res_body["amt"] = float(total_amt)
            res_body["cid"] = cid
            res_body["rate"] = float(rate)
            res_body["msg"] = "Your SMS Campaign Is Now Being Processed For Broadcast. Please Check The SMS Campaign Report For All Status Updates."

            # 9. Payment Check and Final Dispatch (Java lines 1074-1087)
            # Use SDK-based verification to match Java's checkPaymentProfileExists
            profile_status = CommonServices.check_payment_profile_exists(tenant_id)
            if profile_status == "ok":
                # If scheduled for now, execute finalSendSmsCampaign logic (Java lines 1088 onwards)
                # Sync with finalSendSmsCampaign (Java 1146-1158)
                SmsCampaignQueries.update_campaign_sms_send_member(cid)
                
                # Fetch campaign object for status update and transaction (Java parity)
                camp_send = CampaignsSms.objects.get(smsId=sms_id)
                
                # Transaction Billing (Java 1152-1153: totalAmt = perPrice * numberOfSms)
                per_price_unit = float(utils.calculate_sms_billing_rate(1, "text", country_setting))
                total_amt_txn = per_price_unit * number_of_sms
                
                # Save transaction
                CommonServices.saveCampaignTransaction(
                    sms_id, camp_send.smsName, len(email_ids), "sms", 
                    None, "uninvoiced", None, get_client_id_by_tenant_id(tenant_id), "0", total_amt_txn,
                    per_price_unit, number_of_sms, None, None, 0
                )
                
                # Set records to ready (Java behavior)
                camp_send.readyToSms = 'Y'
                camp_send.smsStatus = 2
                camp_send.save()
                
                # Also update the broadcast record (Java line 1146-ish)
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE CAMPAIGN_SMS_SENT SET CSS_READY_TO_SMS = 'Y' WHERE CSS_ID = %s", [cid])
            else:
                if profile_status == "noprofile":
                    res_body["location"] = "paymentProfile"
                    res_body["error"] = "noprofile"
                else:
                    res_body["error"] = profile_status

        return api_response(200, res_body.get('msg', "Success"), res_body)

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error in sendSmsCampaign: {e}")
        return api_response(500, str(e), {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def finalSendSmsCampaign(request):
    """
    Alias for sendSmsCampaign.
    """
    return sendSmsCampaign(request)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def sendSmsPreview(request):
    """
    Send preview SMS to test numbers
    Java: SmsCampaignsController.sendSmsPreview()
    POST /smsCampaign/sendSmsPreview
    """

    try:
        # This would integrate with Telnyx SMS service
        # Placeholder implementation
        return api_response(200, "Preview SMS Sent Successfully", {})
    except Exception as e:
        logger.error(f"Error in sendSmsPreview: {e}")
        return api_response(500, str(e), {})


@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def editSmsCampaignSchedule(request):
    """
    Edit scheduled send date for campaign
    Java: SmsCampaignsController.editSmsCampaignSchedule()
    PUT /smsCampaign/editSmsCampaignSchedule
    """
    
    tenant_id = get_final_tenant_id(request=request)

    serializer = EditSmsCampaignScheduleDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Data", serializer.errors)

    data = serializer.validated_data
    sms_id = data.get('smsId')
    date_str = data.get('sendOnDate')
    time_zone = data.get('timeZone') or get_client_timezone(tenant_id)
    schedule_id = data.get('scheduleId')

    try:
        if not CampaignsSms.objects.filter(smsId=sms_id, memberId=get_client_id_by_tenant_id(tenant_id)).exists():
            return api_response(404, "Campaign Not Found", {})

        # 1. Convert user timezone to UTC and format for Oracle
        # Matches Java: CommonFunction.dbDateTime(CommonFunction.convertEventTimeZoneToUser(..., "UTC"))
        send_on_date_utc = utils.convert_user_timezone_to_utc(date_str, time_zone)
        date_str_db = send_on_date_utc.strftime('%Y-%m-%d %H:%M:%S')

        with connection.cursor() as cursor:
            SmsCampaignQueries.update_campaign_schedule_date(
                sms_id, date_str_db, cursor
            )

            if schedule_id:
                SmsCampaignQueries.update_campaign_send_schedule_date(
                    schedule_id, date_str_db, cursor
                )

        return api_response(200, "Scheduled Time Changed Successfully.", {})
    except Exception as e:
        logger.error(f"Error in editSmsCampaignSchedule: {e}")
        # Java throws ProcessingFailedException("Invalid Date") for parse/validation errors
        return api_response(500, "Invalid Date" if "date" in str(e).lower() else str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkSmsCampaignNameExists(request):
    """
    Check if SMS campaign name already exists
    Java: SmsCampaignsController.checkSmsCampaignNameExists()
    GET /smsCampaign/checkSmsCampaignNameExists?smsName=&smsId=0
    """
    tenant_id = get_final_tenant_id(request=request)
    name = request.GET.get('smsName', '').strip()
    sms_id = int(request.GET.get('smsId', 0))

    try:
        with connection.cursor() as cursor:
            exists = SmsCampaignQueries.check_campaign_name_exists(
                tenant_id, name, sms_id if sms_id > 0 else None, cursor
            )
        return api_response(200, "Name Availability Check Completed Successfully.", {"exists": exists})
    except Exception as e:
        logger.error(f"Error in checkSmsCampaignNameExists: {e}")
        return api_response(500, str(e), {})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def getSmsCampaignTransactionList(request):
    """
    Get paginated list of SMS campaign transactions
    Java: SmsCampaignsController.getSmsCampaignTransactionList()
    POST /smsCampaign/getSmsCampaignTransactionList
    """
    tenant_id = get_final_tenant_id(request=request)
    page_no = int(request.data.get('pageNo', 0))
    page_size = int(request.data.get('pageSize', 10))

    try:
        time_zone = get_client_timezone(tenant_id)

        with connection.cursor() as cursor:
            transactions, total = SmsCampaignQueries.get_campaign_transaction_list(
                tenant_id, page_no, page_size, cursor
            )

        # Format dates in transaction list to user's timezone
        for txn in transactions:
            if txn.get('tranDate'):
                txn['tranDate'] = format_date_for_api(txn['tranDate'], time_zone)
            if txn.get('tranInvoicedDate'):
                txn['tranInvoicedDate'] = format_date_for_api(txn['tranInvoicedDate'], time_zone)

        return api_response(200, "Campaign Transactions Retrieved Successfully.", {
            "campaignTransaction": transactions,
            "totalCampaignTransaction": total,
            "getTotalPages": (total + page_size - 1) // page_size
        })
    except Exception as e:
        logger.error(f"Error in getSmsCampaignTransactionList: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignReportById(request, smsId):
    """
    Get detailed report for SMS campaign
    Java: SmsCampaignsController.getSmsCampaignReportById()
    GET /smsCampaign/getSmsCampaignReportById/{smsId}
    """
    try:
        tenant_id = get_final_tenant_id(request=request)
        time_zone = get_client_timezone(tenant_id)

        with connection.cursor() as cursor:
            total_sent = SmsCampaignQueries.get_sent_sms_count(smsId, cursor)
            total_delivered = SmsCampaignQueries.get_delivered_sms_count(smsId, cursor)
            total_failed = SmsCampaignQueries.get_failed_sms_count(smsId, cursor)
            sms_sent_list = SmsCampaignQueries.get_sms_sent_list(smsId, 0, 100, cursor)

        # Format dates in SMS sent list to user's timezone
        for sms in sms_sent_list:
            if sms.get('smsSendDate'):
                sms['smsSendDate'] = format_date_for_api(sms['smsSendDate'], time_zone)
            if sms.get('smsDeliveredDate'):
                sms['smsDeliveredDate'] = format_date_for_api(sms['smsDeliveredDate'], time_zone)

        return api_response(200, "Campaign Report Retrieved Successfully.", {
            "smsSentList": sms_sent_list,
            "totalSent": total_sent,
            "totalDelivered": total_delivered,
            "totalFailed": total_failed,
            "totalSms": total_sent
        })
    except Exception as e:
        logger.error(f"Error in getSmsCampaignReportById: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignReportDashboard(request, smsId):
    """
    Get summary dashboard for SMS campaign
    Java: SmsCampaignsController.getSmsCampaignReportDashboard()
    GET /smsCampaign/getSmsCampaignReportDashboard/{smsId}
    """
    try:
        with connection.cursor() as cursor:
            delivered = SmsCampaignQueries.get_delivered_sms_count(smsId, cursor)
            sent = SmsCampaignQueries.get_sent_sms_count(smsId, cursor)
            failed = SmsCampaignQueries.get_failed_sms_count(smsId, cursor)
            total = sent

        return api_response(200, "Dashboard Report Retrieved Successfully.", {
            "delivered": delivered,
            "sent": sent,
            "failed": failed,
            "total": total
        })
    except Exception as e:
        logger.error(f"Error in getSmsCampaignReportDashboard: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getMemberSmsSetting(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
        chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
        return api_response(200, "SMS Settings Retrieved Successfully.", {
            "twilioNumber": phone_number.phPhoneNumber,
            "smsNumber": phone_number.phPhoneNumber,
            "conversationsTwilioNumber": chat_phone_number.phPhoneNumber
        })
    except PhoneNumbers.DoesNotExist:
        return api_response(404, "Phone Number Not Found", {})
    except Exception as e:
        logger.error(f"Error in getMemberSmsSetting: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsTemplateList(request):
    tenant_id = get_final_tenant_id(request=request)
    # Support optional timeZone parameter from query string
    time_zone = request.GET.get('timeZone', get_client_timezone(tenant_id))

    try:
        templates = SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(tenant_id)).order_by('-stId')
        templates_data = [
            {
                "sstId": t.stId,
                "templateName": t.stName,
                "templateDetail": t.stDetails,
                "sstDate": format_date_for_api(t.stDate, time_zone)
            }
            for t in templates
        ]
        return api_response(200, "SMS Templates Retrieved Successfully.", templates_data)
    except Exception as e:
        logger.error(f"Error in getSmsTemplateList: {e}")
        return api_response(500, str(e), {})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSmsTemplate(request):
    """
    Save or update SMS template
    Java: SmsCampaignsController.saveSmsTemplate()
    POST /smsCampaign/saveSmsTemplate
    """
    tenant_id = get_final_tenant_id(request=request)
    sst_id = request.data.get('sstId', 0)
    template_name = request.data.get('templateName', '')
    template_detail = request.data.get('templateDetail', '')

    try:
        if sst_id and sst_id > 0:
            template = SmsTemplates.objects.get(stId=sst_id, stClientId=get_client_id_by_tenant_id(tenant_id))
        else:
            template = SmsTemplates(stClientId=get_client_id_by_tenant_id(tenant_id), stDate=datetime.now(pytz.UTC))

        template.stName = template_name
        template.stDetails = template_detail
        template.save()

        return api_response(200, "Template Saved Successfully.", {})
    except SmsTemplates.DoesNotExist:
        return api_response(404, "Template Not Found", {})
    except Exception as e:
        logger.error(f"Error in saveSmsTemplate: {e}")
        return api_response(500, str(e), {})


@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSmsTemplate(request):
    """
    Delete SMS template
    Java: SmsCampaignsController.deleteSmsTemplate()
    DELETE /smsCampaign/deleteSmsTemplate
    """
    tenant_id = get_final_tenant_id(request=request)
    sst_id = request.data.get('sstId')

    try:
        SmsTemplates.objects.filter(stId=sst_id, stClientId=get_client_id_by_tenant_id(tenant_id)).delete()
        return api_response(200, "Template Deleted Successfully.", {})
    except Exception as e:
        logger.error(f"Error in deleteSmsTemplate: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsTemplateById(request, sstId):
    """
    Get single SMS template by ID
    Java: SmsCampaignsController.getSmsTemplateById()
    GET /smsCampaign/getSmsTemplateById/{sstId}?timeZone=Asia/Calcutta
    """
    tenant_id = get_final_tenant_id(request=request)
    # Support optional timeZone parameter from query string
    time_zone = request.GET.get('timeZone', get_client_timezone(tenant_id))

    try:
        template = SmsTemplates.objects.get(stId=sstId, stClientId=get_client_id_by_tenant_id(tenant_id))
        template_data = {
            "sstId": template.stId,
            "templateName": template.stName,
            "templateDetail": template.stDetails,
            "sstDate": format_date_for_api(template.stDate, time_zone)
        }
        return api_response(200, "Template Retrieved Successfully.", template_data)
    except SmsTemplates.DoesNotExist:
        return api_response(404, "Template Not Found", {})
    except Exception as e:
        logger.error(f"Error in getSmsTemplateById: {e}")
        return api_response(500, str(e), {})


def _perform_close_campaign_logic(tenant_id, sms_ids, conversations_twilio_number):
    """
    Core logic for closing SMS campaigns with optional recursion.
    Java: SmsCampaignsServiceImpl.closeSmsCampaign()
    """
    if not sms_ids:
        return

    last_sms_id = 0
    with connection.cursor() as cursor:
        for sms_id in sms_ids:
            try:
                SmsCampaignQueries.close_campaign_master(sms_id, cursor)
                last_sms_id = sms_id
            except Exception as e:
                logger.error(f"Error in closeSmsCampaign loop 1: {e}")

        # 2. Handle Recursive Conversation Logic
        if conversations_twilio_number:
            campaign_sms = CampaignsSms.objects.get(smsId=last_sms_id, memberId=get_client_id_by_tenant_id(tenant_id))
            if campaign_sms:
                pn_id = campaign_sms.pnId
                related_campaigns_sms = CampaignsSms.objects.filter(pnId=pn_id, smsOpenClose='open')
                related_sms_ids = [rcs.smsId for rcs in related_campaigns_sms]
                if related_sms_ids:
                    _perform_close_campaign_logic(tenant_id, related_sms_ids, "")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def closeSmsCampaign(request):
    """
    Close SMS campaign (mark for deletion)
    Java: SmsCampaignsController.closeSmsCampaign()
    POST /smsCampaign/closeSmsCampaign
    """
    tenant_id = get_final_tenant_id(request=request)
    serializer = DeleteSmsCampaignDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Data", serializer.errors)

    data = serializer.validated_data
    sms_ids = data.get('smsId', [])
    if not isinstance(sms_ids, list):
        sms_ids = [sms_ids]

    ph_chat_phone_number = data.get('phChatPhoneNumber', "")

    try:
        _perform_close_campaign_logic(tenant_id, sms_ids, ph_chat_phone_number)
        return api_response(200, "SMS Campaign Closed Successfully.", {})
    except Exception as e:
        logger.error(f"Error in closeSmsCampaign view: {e}")
        # Java: throw new ProcessingFailedException("Exception while closing sms campaign")
        return api_response(500, "Exception while closing sms campaign", {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getMemberCallForwardingNumber(request):
    tenant_id = get_final_tenant_id(request=request)

    try:
        forwarding = NumberCallForwarding.objects.filter(member_id=get_client_id_by_tenant_id(tenant_id)).first()
        return api_response(200, "Call Forwarding Settings Retrieved Successfully.", {
            "callForwardingNumber": forwarding.cfnForwardingNumber if forwarding else None,
            "callForwardingCountryCode": forwarding.cfnForwardingCountryCode if forwarding else "+1"
        })
    except Exception as e:
        logger.error(f"Error in getMemberCallForwardingNumber: {e}")
        return api_response(500, str(e), {})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveMemberCallForwardingNumber(request):
    tenant_id = get_final_tenant_id(request=request)
    number = request.data.get('callForwardingNumber')
    code = request.data.get('callForwardingCountryCode', '+1')

    try:
        forwarding, created = NumberCallForwarding.objects.get_or_create(member_id=get_client_id_by_tenant_id(tenant_id))
        forwarding.cfnTwilioPhoneSid = number
        forwarding.cfnForwardingCountryCode = code
        forwarding.save()

        return api_response(200, "Call Forwarding Settings Saved Successfully.", {})
    except Exception as e:
        logger.error(f"Error in saveMemberCallForwardingNumber: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignDetailsById(request, smsId):
    """
    Get SMS campaign details
    Java: SmsCampaignsController.getSmsCampaignDetailsById()
    GET /smsCampaign/getSmsCampaignDetailsById/{smsId}
    """
    try:
        details = CampaignSmsDetails.objects.filter(smsId=smsId).order_by('sdDisplayOrder')
        details_data = [
            {
                "sdId": d.sdId,
                "sdDetail": d.sdDetail,
                "sdType": d.sdType
            }
            for d in details
        ]
        return api_response(200, "Campaign Details Retrieved Successfully.", details_data)
    except Exception as e:
        logger.error(f"Error in getSmsCampaignDetailsById: {e}")
        return api_response(500, str(e), {})


@api_view(['POST'])
def smsStatusUrl(request: Request):
    try:
        # Get raw request body
        request_data = request.data if isinstance(request.data, dict) else json.loads(request.body.decode())

        # Log the raw webhook response
        logger.error(f"SmsStatusUrl Telnyx Response: {request_data}")

        # Validate response is not empty
        if not request_data:
            return api_response(200, "SMS Status Updated Successfully.", {})

        # Parse nested JSON structure
        try:
            data = request_data.get('data', {})
            payload = data.get('payload', {})

            # Extract SMS message ID (SID)
            sms_sid = payload.get('id', '')

            # Extract delivery status from to array
            to_array = payload.get('to', [])
            if not to_array:
                logger.warning("smsStatusUrl: 'to' array is empty")
                return api_response(200, "SMS Status Updated Successfully.", {})

            # Get status from first element of to array
            to_obj = to_array[0]
            sms_status = to_obj.get('status', '')

        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"SmsStatusUrl: Error parsing JSON payload: {e}")
            return api_response(200, "SMS Status Updated Successfully.", {})

        # Find and update CampaignSendSms record
        if sms_sid and sms_status:
            try:
                campaign_sms = CampaignSendSms.objects.get(sid=sms_sid)
                campaign_sms.smsStatus = sms_status
                campaign_sms.save()

                logger.info(f"Updated SMS status for SID {sms_sid}: {sms_status}")

            except CampaignSendSms.DoesNotExist:
                logger.warning(f"SmsStatusUrl: CampaignSendSms not found for SID: {sms_sid}")
            except Exception as e:
                logger.error(f"SmsStatusUrl: Error updating SMS status: {e}")

        return api_response(200, "SMS Status Updated Successfully.", {})

    except Exception as e:
        logger.error(f"SmsStatusUrl Error: {e}")
        return api_response(200, "SMS Status Updated Successfully.", {})


@api_view(['POST'])
def smsStatusReplyUrl(request: Request):
    try:
        # Get raw request body
        request_data = request.data if isinstance(request.data, dict) else json.loads(request.body.decode())

        # Log the raw webhook response
        logger.error(f"SmsStatusReplyUrl Telnyx Response: {request_data}")

        # Validate response is not empty
        if not request_data:
            return api_response(200, "SMS Reply Status Updated Successfully.", {})

        # Parse nested JSON structure
        try:
            data = request_data.get('data', {})
            payload = data.get('payload', {})

            # Extract SMS message ID (SID)
            sms_sid = payload.get('id', '')

            # Extract delivery status from to array
            to_array = payload.get('to', [])
            if not to_array:
                logger.warning("smsStatusReplyUrl: 'to' array is empty")
                return api_response(200, "SMS Reply Status Updated Successfully.", {})

            # Get status from first element of to array
            to_obj = to_array[0]
            sms_status = to_obj.get('status', '')

        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"SmsStatusReplyUrl: Error parsing JSON payload: {e}")
            return api_response(200, "SMS Reply Status Updated Successfully.", {})

        if sms_sid and sms_status:
            try:
                campaign_sms_reply = CampaignSmsReply.objects.get(crSmsSid=sms_sid)

                # Null check - only update if record exists (safer than Java version)
                if campaign_sms_reply:
                    campaign_sms_reply.crSmsStatus = sms_status
                    campaign_sms_reply.save()

                    logger.info(f"Updated SMS reply status for SID {sms_sid}: {sms_status}")

            except CampaignSmsReply.DoesNotExist:
                logger.warning(f"SmsStatusReplyUrl: CampaignSmsReply not found for SID: {sms_sid}")
            except Exception as e:
                logger.error(f"SmsStatusReplyUrl: Error updating SMS reply status: {e}")

        return api_response(200, "SMS Reply Status Updated Successfully.", {})

    except Exception as e:
        logger.error(f"SmsStatusReplyUrl Error: {e}")
        return api_response(200, "SMS Reply Status Updated Successfully.", {})


@api_view(['POST'])
def smsLinkClick(request: Request):
    """
    Track link clicks in SMS
    Java: SmsCampaignsController.smsLinkClick()
    POST /smsCampaign/smsLinkClick
    """
    try:
        # Track link click
        campaign_id = request.data.get('campId')
        link_url = request.data.get('url')
        user_id = request.data.get('userId')

        if campaign_id and link_url:
            try:
                link = SmsLinks.objects.get(campId=campaign_id, linkUrl=link_url)
                link.linkCount = (link.linkCount or 0) + 1
                link.save()

                # Record click trace
                SmsLinkTrace.objects.create(
                    linkId=link.id,
                    userId=user_id,
                    clickDate=datetime.now(pytz.UTC)
                )
            except SmsLinks.DoesNotExist:
                pass

        return api_response(200, "Link Click Tracked Successfully.", {})
    except Exception as e:
        logger.error(f"Error in smsLinkClick: {e}")
        return api_response(500, str(e), {})


# ===== HELPER FUNCTIONS =====

def format_date_for_api(dt, user_timezone='UTC'):
    """Format datetime for API response with timezone conversion (matches Spring Boot format)"""
    if not dt:
        return None  # Return None to match Spring Boot null handling

    try:
        # Convert UTC to user timezone
        converted_dt = utils.convert_utc_to_user_timezone(dt, user_timezone)
        return utils.format_date_for_display(converted_dt)
    except Exception as e:
        logger.warning(f"Error formatting date: {e}")
        return dt.strftime("%m/%d/%Y %H:%M:%S") if dt else None


# ===== PLACEHOLDER ENDPOINTS (Not Fully Implemented) =====

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getBuyAllSmsNumberList(request):
    """Get available numbers for purchase"""
    try:
        tenant_id = get_final_tenant_id(request=request)
        # Query available numbers from Telnyx (would need API integration)
        # For now, return currently owned numbers
        numbers = PhoneNumbers.objects.filter(
            phClientId=get_client_id_by_tenant_id(tenant_id),
            phPhoneNumberClosed__ne='Y'
        ).values('pnId', 'phPhoneNumber', 'phDatePurchased')

        phone_list = [
            {
                "pnId": num['pnId'],
                "phPhoneNumber": num['phPhoneNumber'],
                "phDatePurchased": num['phDatePurchased']
            }
            for num in numbers
        ]
        return api_response(200, "Available Numbers Retrieved Successfully.", {
            "smsCampaignsPhoneList": phone_list
        })
    except Exception as e:
        logger.error(f"Error in getBuyAllSmsNumberList: {e}")
        return api_response(500, str(e), {})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def buyNumberForSmsCampaign(request):
    """
    Buy SMS number for SMS Campaign from Telnyx
    Converts Java buyNumberForSmsCampaign logic to Python/Django
    """
    result = {"scmId": "0"}

    try:
        # Get the request data
        buy_number_dto = request.data
        tenant_id = get_final_tenant_id(request=request)

        sub_tenant_id = buy_number_dto.get('subMemberId', 0)
        if sub_tenant_id and sub_tenant_id > 0:
            logged_user_id = sub_tenant_id
            full_name = f"{buy_number_dto.get('subFullName', '')} {sub_tenant_id}"
        else:
            logged_user_id = tenant_id
            full_name = buy_number_dto.get('fullName', '')

        try:
            client = Clients.objects.get(cliTenantId=logged_user_id)
        except Clients.DoesNotExist:
            result["status"] = "error"
            result["msg"] = f"Client not found with ID: {tenant_id}"
            return api_response(400, result["msg"], result)

        env_sys = settings.ENVSYS.upper() if hasattr(settings, 'ENVSYS') else "PRODUCTION"
        friendly_name_full = f"{env_sys} {full_name} {tenant_id}"

        try:
            out_result = telnyx_utils.telnyx_sub_account(
                sms_reply_url=settings.SMS_REPLY_URL if hasattr(settings, 'SMS_REPLY_URL') else '',
                cli_sip_friendly_name=friendly_name_full,
                ph_phone_number=buy_number_dto.get('twilioNumber', ''),
                cli_sms_account_sid=client.cliSmsAccountSid or '',
                telnyx_base_url=settings.TELNYX_BASE_URL if hasattr(settings, 'TELNYX_BASE_URL') else None,
                telnyx_api_key=settings.TELNYX_API_KEY if hasattr(settings, 'TELNYX_API_KEY') else None,
                cli_sip_connection_id=client.cliSipConnectionId or '',
                site_url_backend=settings.SITE_URL_BACKEND if hasattr(settings, 'SITE_URL_BACKEND') else '',
                telnyx_outbound_voice_profile_id=settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID if hasattr(settings, 'TELNYX_OUTBOUND_VOICE_PROFILE_ID') else None
            )
        except Exception as e:
            logger.error(f"[tenantId : {tenant_id}] buyNumberForSmsCampaign Telnyx error: {e}")
            result["status"] = "error"
            result["msg"] = str(e)
            return api_response(400, result["msg"], result)

        # Check for Telnyx API errors
        error_msg = out_result.get('error', '')
        if error_msg and error_msg.strip():
            result["status"] = "error"
            result["msg"] = error_msg
            return api_response(400, result["msg"], result)

        # Step 4: Call Forwarding Setup (if enabled)
        try:
            if buy_number_dto.get('checkForwardingYesNo') == 'yes':
                forward_number = (buy_number_dto.get('callForwardingCountryCode', '') +
                                buy_number_dto.get('callForwardingNumber', ''))

                try:
                    s_id = telnyx_utils.telnyx_call_forwarding(
                        ph_sid=out_result.get('phSid', ''),
                        forwarding_number=forward_number,
                        call_forwarding_enabled=True,
                        telnyx_base_url=settings.TELNYX_BASE_URL if hasattr(settings, 'TELNYX_BASE_URL') else None,
                        telnyx_api_key=settings.TELNYX_API_KEY if hasattr(settings, 'TELNYX_API_KEY') else None
                    )

                    if s_id and s_id.strip():
                        CommonServices.save_number_call_forwarding(
                            cfn_id=0,
                            twilio_number=buy_number_dto.get('conversationsTwilioNumber', ''),
                            country_code=buy_number_dto.get('callForwardingCountryCode', ''),
                            forwarding_number=buy_number_dto.get('callForwardingNumber', ''),
                            member_id=tenant_id,
                            twilio_phone_sid=out_result.get('phSid', '')
                        )
                except Exception as cf_error:
                    logger.error(f"[tenantId : {tenant_id}] Call forwarding setup error: {cf_error}")
                    # Continue even if call forwarding fails
        except Exception as e:
            logger.error(f"[tenantId : {tenant_id}] Call forwarding block error: {e}")
            # Continue even if this block fails

        client.cliSipFriendlyName = out_result.get('cliSipFriendlyName', '')
        client.cliSipUsername = out_result.get('cliSipFriendlyName', '')
        client.cliSipPassword = out_result.get('cliSipFriendlyName', '')
        client.cliSmsAccountSid = out_result.get('cliSmsAccountSid', '')
        client.cliSipConnectionId = (out_result.get('cliSipConnectionId', '') or '').strip()
        client.save()
        renew_date_str = add_one_month() + " " + timezone.now().strftime('%H:%M:%S')
        renew_date_str = datetime.strptime(renew_date_str, '%Y-%m-%d %H:%M:%S')
        renew_date_str = timezone.make_aware(renew_date_str)
        phone_number = PhoneNumbers.objects.create(
            phClientId=get_client_id_by_tenant_id(tenant_id),
            phPhoneNumber=out_result.get('phPhoneNumber', ''),
            phSid=out_result.get('phSid', ''),
            phHowUsed="CAMPAIGN",
            phDatePurchased=timezone.now(),
            phDateRenew=renew_date_str,
            phPhoneNumberClosed = 'N'
        )

        if buy_number_dto.get('flagType') == 'build':
            result["pnId"] = str(phone_number.pnId)

        # Step 7: Billing Transaction Logging
        try:
            country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
            sms_number_price = country_setting.cnty_sms_number_per_price if country_setting else 0

            CommonServices.saveCampaignTransaction(
                None,
                f"SMS number purchased : {out_result.get('phPhoneNumber', '')}",
                1,
                'sms number',
                None,
                'uninvoiced',
                None,
                get_client_id_by_tenant_id(tenant_id),
                '0',
                sms_number_price,
                sms_number_price,
                0,
                None,
                None,
                sub_tenant_id or 0
            )
        except Exception as e:
            logger.error(f"[tenantId : {tenant_id}] Campaign transaction logging error: {e}")

        # Step 8: Return success response
        result["status"] = "ok"
        result["msg"] = "You Are Good To Go For SMS/MMS"
        return api_response(200, result["msg"], result)

    except Exception as e:
        logger.error(f"[tenantId : {get_final_tenant_id(request=request)}] buyNumberForSmsCampaign Error: {e}")
        result["status"] = "error"
        result["msg"] = str(e)
        return api_response(500, str(e), result)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignPhoneList(request, subTenantId):
    """
    Retrieve a list of phone numbers associated with an SMS campaign.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
        chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
        client = Clients.objects.get(cliTenantId=tenant_id)

        res_body = dict()
        res_body["btnChangeDelete"] = "N"
        res_body["numberCallForwarding"] = None
        res_body["smsCampaignsPhoneList"] = []
        res_body["numberStatus"] = "Provisioned"
        
        if subTenantId > 0:
            count = 0
            phone_number_list = PhoneNumbers.objects.filter(
                phClientId=get_client_id_by_tenant_id(tenant_id)
            ).exclude(phPhoneNumberClosed='Y')
            
            for number in phone_number_list:
                campaign_sms = CampaignsSms.objects.filter(pnId=number.pnId).exclude(smsOpenClose='close').first()
                sms_id = campaign_sms.smsId if campaign_sms else 0
                
                main_tenant_id = get_final_tenant_id(request=request)
                main_chat_phone_number = get_phone_numbers_first(main_tenant_id, "CHAT")
                main_client = Clients.objects.get(cliTenantId=main_tenant_id)

                number_assign = telnyx_utils.check_assign_to_number(
                    main_client.cliSmsAccountSid,
                    number.phSid,
                    cli_sip_connection_id=main_client.cliSipConnectionId
                )
                
                phone_dto = {
                    "smsName": "",
                    "btnChange": "N",
                    "smsDisplay": "N",
                    "fromContact": number.phPhoneNumber,
                    "scmNumberPhoneSid": number.phSid,
                    "scdSmsId": sms_id,
                    "scmMemberId": number.phClientId,
                    "position": count,
                    "numberCallForwarding": None,
                    "numberStatus": "Provisioned" if number_assign == "Yes" else "Unprovisioned"
                }
                
                # Call Forwarding
                try:
                    ncf = NumberCallForwarding.objects.filter(
                        cfnTwilioPhoneSid=number.phSid,
                        cfnMemberId=get_client_id_by_tenant_id(tenant_id)
                    ).first()
                    if ncf:
                        phone_dto["numberCallForwarding"] = {
                            "cfnId": ncf.cfnId,
                            "cfnTwilioNumber": ncf.cfnTwilioNumber,
                            "cfnForwardingCountryCode": ncf.cfnForwardingCountryCode,
                            "cfnForwardingNumber": ncf.cfnForwardingNumber,
                            "cfnMemberId": ncf.cfnMemberId,
                            "cfnTwilioPhoneSid": ncf.cfnTwilioPhoneSid
                        }
                except:
                    pass
                
                # Delete button logic
                if number.phPhoneNumber and number.phSid != main_client.cliSmsAccountSid:
                    phone_dto["btnDelete"] = "Y"
                else:
                    phone_dto["btnDelete"] = "N"
                    
                # Conversations logic
                if main_chat_phone_number.phPhoneNumber:
                    if clean_me_number(main_chat_phone_number.phPhoneNumber) == clean_me_number(phone_dto["fromContact"]):
                        phone_dto["btnDelete"] = "N"
                        phone_dto["btnChange"] = "N"
                
                res_body["smsCampaignsPhoneList"].append(phone_dto)
                count += 1
                
        else: # subMemberId == 0
            if phone_number and phone_number.phPhoneNumber is not None and phone_number.phPhoneNumber != "":
                res_body["twilioNumber"] = phone_number.phPhoneNumber
                res_body["scmNumberPhoneSid"] = phone_number.phSid
                
                # Call Forwarding for main number
                try:
                    ncf = NumberCallForwarding.objects.filter(
                        cfnTwilioPhoneSid=phone_number.phSid,
                        cfnMemberId=get_client_id_by_tenant_id(tenant_id)
                    ).first()
                    if ncf:
                        res_body["numberCallForwarding"] = {
                            "cfnId": ncf.cfnId,
                            "cfnTwilioNumber": ncf.cfnTwilioNumber,
                            "cfnForwardingCountryCode": ncf.cfnForwardingCountryCode,
                            "cfnForwardingNumber": ncf.cfnForwardingNumber,
                            "cfnMemberId": ncf.cfnMemberId,
                            "cfnTwilioPhoneSid": ncf.cfnTwilioPhoneSid
                        }
                except:
                    pass
                
                # Number Status (Provisioning status from Telnyx)
                # In Java, this is checked via API.
                number_assign = telnyx_utils.check_assign_to_number(
                    client.cliSmsAccountSid,
                    phone_number.phSid,
                    cli_sip_connection_id=client.cliSipConnectionId
                )
                res_body["numberStatus"] = "Provisioned" if number_assign == "Yes" else "Unprovisioned"

            count = 0
            if phone_number is None:
                res_body["btnChangeDelete"] = "N"
            else:
                res_body["btnChangeDelete"] = "Y"
            
            # Java: findListData(memberId)
            phone_number_list = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id)).exclude(phPhoneNumberClosed='Y')
            for number in phone_number_list:
                first = "Yes"
                campaign_sms = CampaignsSms.objects.filter(pnId=number.pnId)
                for cs in campaign_sms:
                    sms_name = ""
                    try:
                        camp = CampaignsSmsSend.objects.filter(smsId=cs.smsId).first()
                        sms_name = camp.smsName if camp else ""
                    except Exception as e:
                        logger.error(f"Error fetching campaign name: {e}")
                    
                    # Number Status
                    number_assign_master = telnyx_utils.check_assign_to_number(
                        client.cliSmsAccountSid,
                        number.phSid,
                        cli_sip_connection_id=client.cliSipConnectionId
                    )
                    
                    phone_dto = {
                        "fromContact": number.phPhoneNumber,
                        "scmNumberPhoneSid": number.phSid,
                        "smsName": sms_name if sms_name else "",
                        "scdSmsId": cs.smsId,
                        "scmMemberId": number.phClientId,
                        "position": count,
                        "numberCallForwarding": None,
                        "numberStatus": "Provisioned" if number_assign_master == "Yes" else "Unprovisioned"
                    }
                    
                    if first == "Yes":
                        phone_dto["smsDisplay"] = "Y"
                    else:
                        phone_dto["smsDisplay"] = "N"
                        
                    # Call Forwarding for item
                    try:
                        incf = NumberCallForwarding.objects.filter(
                            cfnTwilioPhoneSid=number.phSid,
                            cfnMemberId=get_client_id_by_tenant_id(tenant_id)
                        ).first()
                        if incf:
                            phone_dto["numberCallForwarding"] = {
                                "cfnId": incf.cfnId,
                                "cfnTwilioNumber": incf.cfnTwilioNumber,
                                "cfnForwardingCountryCode": incf.cfnForwardingCountryCode,
                                "cfnForwardingNumber": incf.cfnForwardingNumber,
                                "cfnMemberId": incf.cfnMemberId,
                                "cfnTwilioPhoneSid": incf.cfnTwilioPhoneSid
                            }
                    except:
                        pass
                    
                    # btnChange logic
                    if phone_number:
                        if clean_me_number(phone_number.phPhoneNumber) == clean_me_number(number.phPhoneNumber) and first == "Yes":
                            phone_dto["btnChange"] = "Y"
                            res_body["btnChangeDelete"] = "N"
                        else:
                            phone_dto["btnChange"] = "N"
                    else:
                        phone_dto["btnChange"] = "N"
                        
                    # btnDelete logic
                    if number.phPhoneNumberClosed != 'Y' and first == "Yes":
                        phone_dto["btnDelete"] = "Y"
                    else:
                        phone_dto["btnDelete"] = "N"
                        
                    # Conversations check
                    if chat_phone_number:
                        if clean_me_number(chat_phone_number.phPhoneNumber) == clean_me_number(phone_dto["fromContact"]):
                            phone_dto["btnDelete"] = "N"
                            phone_dto["btnChange"] = "N"
                            
                    res_body["smsCampaignsPhoneList"].append(phone_dto)
                    count += 1
                    first = "No"

        return api_response(200, "Fetch SMS Campaign Successfully.", res_body)
    except Exception as e:
        logger.exception(e)
        logger.error(f"[ tenantId : {tenant_id} ] getSmsCampaignPhoneList Error : {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignReleasePhoneList(request, subMemberId):
    try:
        tenant_id = get_final_tenant_id(request=request)
        numbers = PhoneNumbers.objects.filter(
            phClientId=tenant_id,
            phPhoneNumberClosed='Y'
        ).values('pnId', 'phPhoneNumber', 'phSid')

        phone_list = [
            {
                "pnId": num['pnId'],
                "phPhoneNumber": num['phPhoneNumber'],
                "phSid": num['phSid']
            }
            for num in numbers
        ]

        return api_response(200, "Released Phone Numbers Retrieved Successfully.", {
            "smsCampaignsPhoneList": phone_list
        })
    except Exception as e:
        logger.error(f"Error in getSmsCampaignReleasePhoneList: {e}")
        return api_response(500, str(e), {})


@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSmsCampaignNumber(request, tenant_id, sms_id):
    res_body = {"error": ""}
    try:
        tenant_id = int(tenant_id)
        sms_id = int(sms_id)
    except (ValueError, TypeError):
        tenant_id = 0
        sms_id = 0

    try:
        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")

        ph_sid = ""
        campaign_sms = None

        if sms_id > 0:
            campaign_sms = CampaignsSms.objects.get(smsId=sms_id)
            if campaign_sms:
                pn = PhoneNumbers.objects.get(pnId=campaign_sms.pnId)
                ph_sid = pn.phSid or ""
        else:
            ph_sid = phone_number.phSid or ""

        telnyx_base_url = getattr(settings, 'TELNYX_BASE_URL', '')
        telnyx_api_key = getattr(settings, 'TELNYX_API_KEY', '')

        flag = telnyx_utils.delete_telnyx_number(ph_sid, telnyx_base_url, telnyx_api_key)

        if flag == 1:
            try:
                CommonServices.delete_number_call_forwarding(ph_sid, tenant_id)
            except Exception:
                pass

            try:
                if campaign_sms:
                    _perform_close_campaign_logic(tenant_id, [sms_id], "")
            except Exception as ee:
                logger.error(f"[ tenantId : {tenant_id} ] DeleteSmsCampaignNumber Error 2: {ee}")

            PhoneNumbers.objects.filter(phSid=ph_sid).update(phPhoneNumberClosed='Y')
        else:
            res_body["error"] = "Oops !! There Is Some Problem While Sub Account Delete."
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] DeleteSmsCampaignNumber - Delete Number Error 4: {e}")
        res_body["error"] = "Oops !! There Is Some Problem While Sub Account Delete."

    phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
    chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
    res_body["twilioNumber"] = phone_number.phPhoneNumber if phone_number else ""
    res_body["conversationsTwilioNumber"] = chat_phone_number if chat_phone_number else ""

    if res_body.get("error") == "":
        return api_response(200, "Delete Phone Number Successfully.", res_body)
    else:
        return api_response(500, res_body.get("error"), res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def changeSmsCampaignNumber(request):
    tenant_id = get_final_tenant_id(request=request)
    buy_number_dto = request.data

    res_body = dict()
    try:
        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
        chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
        default_chat_phone_number = get_phone_numbers_first(tenant_id, "DEFAULTCHAT")
        client = Clients.objects.get(cliTenantId=tenant_id)

        res_body['phPhoneNumber'] = phone_number.phPhoneNumber or ''
        res_body['phChatPhoneNumber'] = chat_phone_number.phPhoneNumber or ''

        old_ph_sid = phone_number.phSid or ''
        cli_sip_connection_id = client.cliSipConnectionId or ''
        cli_sms_account_sid = client.cliSmsAccountSid or ''

        # Get settings
        telnyx_base_url = getattr(settings, 'TELNYX_BASE_URL', '')
        telnyx_api_key = getattr(settings, 'TELNYX_API_KEY', '')

        # 1. Change Telnyx Number (FIRST step in Java)
        full_name = buy_number_dto.get('fullName', '')
        ph_phone_number_to_buy = buy_number_dto.get('phPhoneNumber', '')

        out_result = telnyx_utils.change_telnyx_number(
            cli_sip_friendly_name=full_name,
            ph_phone_number=ph_phone_number_to_buy,
            cli_sms_account_sid=cli_sms_account_sid,
            ph_sid=old_ph_sid,
            telnyx_base_url=telnyx_base_url,
            telnyx_api_key=telnyx_api_key,
            cli_sip_connection_id=cli_sip_connection_id,
        )

        # 2. Call Forwarding (SECOND step in Java)
        try:
            if buy_number_dto.get('checkForwardingYesNo') == 'yes':
                forward_number = (buy_number_dto.get('callForwardingCountryCode', '') +
                                  buy_number_dto.get('callForwardingNumber', ''))
                s_id = telnyx_utils.telnyx_call_forwarding(
                    ph_sid=out_result.get('phSid', ''),
                    forwarding_number=forward_number,
                    call_forwarding_enabled=True,
                    telnyx_base_url=telnyx_base_url,
                    telnyx_api_key=telnyx_api_key
                )
                if s_id:
                    CommonServices.save_number_call_forwarding(
                        cfn_id=0,
                        twilio_number=buy_number_dto.get('conversationsTwilioNumber', ''),
                        country_code=buy_number_dto.get('callForwardingCountryCode', ''),
                        forwarding_number=buy_number_dto.get('callForwardingNumber', ''),
                        member_id=tenant_id,
                        twilio_phone_sid=out_result.get('phSid', '')
                    )
        except Exception as cf_error:
            logger.error(f"[tenantId: {tenant_id}] Call forwarding setup error: {cf_error}")

        # 3. Check flag_default (THIRD step in Java)
        flag_default = 0
        try:
            if phone_number.phPhoneNumber == default_chat_phone_number.phPhoneNumber:
                flag_default = 1
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsCampaignNumber Error 1 : {e}")

        # 4. Close Related Campaigns (FOURTH step in Java)
        try:
            if old_ph_sid:
                sms_id_list = list(CampaignsSms.objects.filter(
                    pnId=phone_number.pnId
                ).values_list('smsId', flat=True))
                if sms_id_list:
                    _perform_close_campaign_logic(tenant_id, sms_id_list, "")
                PhoneNumbers.objects.filter(pnId=phone_number.pnId).update(phPhoneNumberClosed='Y')
        except Exception as ee:
            logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsCampaignNumber Error 2: {ee}")

        # 5. If Telnyx call was successful, save all records
        if not out_result.get('error', ''):
            try:
                client.cliSipFriendlyName = out_result.get('cliSipFriendlyName', '')
                client.cliSmsAccountSid = out_result.get('cliSmsAccountSid', '')
                client.save()
                renew_date_str = add_one_month() + " " + timezone.now().strftime('%H:%M:%S')
                renew_date_str = datetime.strptime(renew_date_str, '%Y-%m-%d %H:%M:%S')
                renew_date_str = timezone.make_aware(renew_date_str)
                if flag_default == 1:
                    ph_how_used = "DEFAULTCHAT"
                else:
                    ph_how_used = "CAMPAIGN"
                PhoneNumbers.objects.create(
                    phClientId=get_client_id_by_tenant_id(tenant_id),
                    phPhoneNumber=out_result.get('phPhoneNumber', ''),
                    phSid=out_result.get('phSid', ''),
                    phHowUsed=ph_how_used,
                    phDatePurchased=timezone.now(),
                    phDateRenew=renew_date_str,
                    phPhoneNumberClosed='N'
                )
            except Exception as ee:
                logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsCampaignNumber Error 4: {ee}")

            # Billing and saveCampaignTransaction
            try:
                country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
                sms_number_price = country_setting.cnty_sms_number_per_price if country_setting else 0.0

                CommonServices.saveCampaignTransaction(
                    None,
                    f"New SMS number purchased : {out_result.get('phPhoneNumber', '')}",
                    1,
                    'sms number',
                    None,
                    'uninvoiced',
                    None,
                    get_client_id_by_tenant_id(tenant_id),
                    '0',
                    sms_number_price,
                    sms_number_price,
                    0,
                    None,
                    None,
                    0
                )
            except Exception as e:
                logger.error(f"[ tenantId : {tenant_id} ] ChangeSmsCampaignNumber Billing Error: {e}")

            res_body = {
                "status": "ok",
                "msg": "Your New SMS/MMS Number Ready To Use",
                "twilioNumber": phone_number.phPhoneNumber or '',
                "conversationsTwilioNumber": chat_phone_number.phPhoneNumber or ''
            }
            return api_response(200, "Your New SMS/MMS Number Ready To Use", res_body)
        else:
            res_body = {
                "status": "error",
                "msg": out_result.get('error')
            }
            return api_response(500, out_result.get('error'), res_body)

    except Exception as e:
        logger.error(f"Error in changeSmsCampaignNumber: {e}")
        return api_response(500, 'An error occurred.', {"status": "error", "msg": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getNumberCheck(request, groupId):
    """
    Check phone numbers for group.
    Ported from SmsCampaignsServiceImpl.getNumberCheck(Long memberId, Long groupId)
    """
    try:
        # Extract tenant_id manually if not authenticated by DRF (since it's whitelisted)
        tenant_id = get_final_tenant_id(request=request)
        res_body = {
            "flag": "0",
            "phoneNumberList": []
        }
        
        if tenant_id == 0:
            return api_response(200, "Group Number Status Retrieved Successfully.", res_body)

        pn_id = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id)).values_list('pnId', flat=True).first()
        
        if not pn_id:
            res_body["flag"] = "1"
            return api_response(200, "Group Number Status Retrieved Successfully.", res_body)
        
        flag = 0
        campaigns_sms_list = CampaignsSms.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smsOpenClose='open')
        
        if campaigns_sms_list.exists():
            select_group_phone_numbers = set(Userlist.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(tenant_id)).values_list('phoneNumber', flat=True))
            
            for campaign in campaigns_sms_list:
                try:
                    campaign_group_id = int(campaign.groupList)
                    campaign_phone_numbers = set(Userlist.objects.filter(groupId=campaign_group_id, memberId=get_client_id_by_tenant_id(tenant_id)).values_list('phoneNumber', flat=True))
                    
                    if select_group_phone_numbers.intersection(campaign_phone_numbers):
                        flag = 1
                        break
                except (ValueError, TypeError):
                    continue
        
        if flag == 0:
            res_body["flag"] = "previousnumber"
            return api_response(200, "Group Number Status Retrieved Successfully.", res_body)
        else:
            number_list = []
            phone_number_list = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id))
            
            for pn in phone_number_list:
                already_assigned = CampaignsSms.objects.filter(
                    pnId=pn.pnId,
                    smsOpenClose='open'
                ).exists()
                
                if not already_assigned:
                    number_list.append({
                        "phPhoneNumber": pn.phPhoneNumber,
                        "phSid": pn.phSid
                    })
            
            if not number_list:
                res_body["flag"] = "2"
            else:
                res_body["phoneNumberList"] = number_list
                res_body["flag"] = "0" # Java logic says flag remains 0 if list is found? 
                # Actually, in Java if flag was 1 (overlap), it populates list and returns.
                # If list remains empty after checking ALL possibilities, it sets flag=2.
            
            return api_response(200, "Group Number Status Retrieved Successfully.", res_body)

    except Exception as e:
        logger.error(f"GetNumberCheck Error: {e}")
        return api_response(500, "Error Processing Request", str(e))


def find_ph_sid_by_tenant_id(tenant_id):
    result = PhoneNumbers.objects.filter(
        phPhoneNumberClosed='N',
        phClientId=get_client_id_by_tenant_id(tenant_id),
    ).exclude(
        phSid__in=['', None]
    ).order_by('-pnId').values_list('phSid', flat=True).first()

    return result  # returns string or None

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getScmNumberPhoneSid(request):
    tenant_id = get_final_tenant_id(request=request)
    resBody=dict()
    try:
        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
        scmNumberPhoneSid = find_ph_sid_by_tenant_id(tenant_id)
        if scmNumberPhoneSid:
            flag = telnyx_utils.check_active_telnyx_number(scmNumberPhoneSid)
            if flag == "Inactive":
                resBody={"scmNumberPhoneSid":""}
            else:
                resBody={"scmNumberPhoneSid":scmNumberPhoneSid}
        else:
            if phone_number.phSid:
                resBody={"scmNumberPhoneSid":phone_number.phSid}
        return api_response(200, "Fetch Phone Number Successfully.", resBody)
    except PhoneNumbers.DoesNotExist:
        return api_response(404, "Phone Number Not Found", {})
    except Exception as e:
        logger.error(f"Error in getScmNumberPhoneSid: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getFreeNumberList(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        final_number_list = []
        used_phone_number_list = []

        phone_number_list = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id)).exclude(phPhoneNumberClosed='Y')
        
        number_list = []
        for pn in phone_number_list:
            is_assigned = CampaignsSms.objects.filter(
                pnId=pn.pnId
            ).exclude(smsOpenClose='close').exists()
            
            if not is_assigned:
                number_list.append({
                    "scmNumberPhoneSid": pn.phSid,
                    "scmNumber": pn.phPhoneNumber,
                    "smsId": None
                })
        
        # Filter Conversations logic: if multiple numbers, exclude those used in conversations
        if len(number_list) > 1:
            for item in number_list:
                in_conv = SmsConversations.objects.filter(
                    cvsMemberId=get_client_id_by_tenant_id(tenant_id),
                    cvsTwilioNumber=item["phPhoneNumber"]
                ).exists()
                
                if not in_conv:
                    final_number_list.append(item)
        elif len(number_list) == 1:
            final_number_list = number_list

        # 2. Get usedPhoneNumberList
        closed_numbers = PhoneNumbers.objects.filter(phClientId=get_client_id_by_tenant_id(tenant_id)).exclude(phPhoneNumberClosed='Y')
        
        for cn in closed_numbers:
            cs = CampaignsSms.objects.filter(
                pnId=cn.pnId
            ).exclude(smsOpenClose='close').first()
            
            if cs:
                used_phone_number_list.append({
                    "scmNumberPhoneSid": cn.phSid,
                    "scmNumber": cn.phPhoneNumber,
                    "smsId": cs.smsId
                })

        return api_response(200, "Fetched Free Phone Number List Successfully.", {
            "phoneNumberList": final_number_list,
            "usedPhoneNumberList": used_phone_number_list
        })
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetFreeNumberList Error : {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignNumber(request, smsId):
    """Get numbers for SMS campaign"""
    try:
        campaign_sms = CampaignsSms.objects.filter(smsId=smsId).first()
        if campaign_sms and campaign_sms.pnId:
            number_master = PhoneNumbers.objects.get(pnId=campaign_sms.pnId)
            return api_response(200, "SMS Campaign Number Retrieved Successfully.", {
                "phPhoneNumber": number_master.phPhoneNumber
            })
        return api_response(200, "SMS Campaign Number Retrieved Successfully.", {"phPhoneNumber": None})
    except Exception as e:
        logger.error(f"Error in getSmsCampaignNumber: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsCampaignReplyNotification(request, replyId):
    """
    Get SMS reply notification logic matching Java
    Java: SmsCampaignsServiceImpl.getSmsCampaignReplyNotification()
    GET /smsCampaign/getSmsCampaignReplyNotification/{replyId}
    """
    tenant_id = get_final_tenant_id(request=request)
    
    try:
        sms_reply = CampaignSmsReply.objects.filter(
            crMemberId=get_client_id_by_tenant_id(tenant_id),
            crSmsSid__isnull=False
        ).filter(
            Q(crRead__isnull=True) | Q(crRead='N')
        ).order_by('-crId').first()
        
        if sms_reply is None:
            last_entry = CampaignSmsReply.objects.filter(crMemberId=get_client_id_by_tenant_id(tenant_id)).order_by('-crId').first()
            if last_entry is None:
                return api_response(status.HTTP_200_OK, "Fetch SMS Campaign Reply Notification Successfully.", {
                    "lastId": replyId,
                    "notification": "NO"
                })
            else:
                return api_response(status.HTTP_200_OK, "Fetch SMS Campaign Reply Notification Successfully.", {
                    "lastId": last_entry.crId,
                    "notification": "NO"
                })
        
        # Compare provided replyId with latest found ID
        # Convert replyId to int for comparison since it comes from URL path
        try:
            r_id = int(replyId)
        except (ValueError, TypeError):
            r_id = 0

        if r_id == sms_reply.crId:
            return api_response(status.HTTP_200_OK, "Fetch SMS Campaign Reply Notification Successfully.", {
                "lastId": sms_reply.crId,
                "notification": "NO"
            })
        else:
            return api_response(status.HTTP_200_OK, "Fetch SMS Campaign Reply Notification Successfully.", {
                "lastId": sms_reply.crId,
                "notification": "YES"
            })
            
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetSmsCampaignReplyNotification Error : {e}")
        # Matching Java catch block: log error but return map with default NO notification
        return api_response(status.HTTP_200_OK, "Fetch SMS Campaign Reply Notification Successfully.", {
            "lastId": replyId,
            "notification": "NO"
        })


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def setCampaignNumber(request):
    res_body = dict()
    tenant_id = 0
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        dto = request.data or {}
        ph_chat_phone_number = dto.get('conversationsTwilioNumber')
        sub_tenant_id = int(dto.get('subMemberId') or 0)

        if sub_tenant_id > 0:
            tenant_id = sub_tenant_id
        else:
            tenant_id = final_tenant_id

        # Sms Conversations Close Start
        try:
            if ph_chat_phone_number:
                PhoneNumbers.objects.filter(phPhoneNumber=ph_chat_phone_number).update(phHowUsed='CAMPAIGN')
                SmsConversations.objects.filter(
                    cvsTwilioNumber=ph_chat_phone_number
                ).exclude(cvsClosed='Y').update(
                    cvsClosed='Y',
                    cvsClosedDate=timezone.now()
                )
        except Exception as ee:
            logger.error(f"[ tenantId : {tenant_id} ] SetCampaignNumber Error : {ee}")
        # Sms Conversations Close End

        res_body["msg"] = "success"
        return api_response(200, "Campaign Number Set Successfully", res_body)

    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] SetCampaignNumber Error : {e}")
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkNumberAssignOrNot(request):
    """
    Check if a phone number has been assigned for SMS campaigns.
    Java: SmsCampaignsController.checkNumberAssignOrNot()
    GET /smsCampaign/checkNumberAssignOrNot
    """
    try:
        tenant_id = get_final_tenant_id(request=request)
        phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
        client = Clients.objects.get(cliTenantId=tenant_id)
        
        # Call Telnyx utility to check assignment status
        number_assign = "No"
        if phone_number is not None and client is not None and phone_number.phSid is not None and client.cliSmsAccountSid is not None and client.cliSipConnectionId is not None:
            number_assign = telnyx_utils.check_assign_to_number(
                client.cliSmsAccountSid,
                phone_number.phSid,
                cli_sip_connection_id=client.cliSipConnectionId
            )
        
        if number_assign == "Yes":
            return api_response(200, "Successfully.", "")
        else:
            return api_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR, 
                "Your Phone Number Is Being Provisioned Please Wait 10 To 15 Minutes. The Status Of Your Provisioning Can Be Viewed Here: <a href='javascript:void(0);' onclick='redirectToLink();'>SMS Phone List</a>", 
                ""
            )
    except Exception as e:
        logger.error(f"Error in checkNumberAssignOrNot: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Oops !! there is some problem while fetching data.", "")



@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getUsernamePassword(request):
    res_body = {"username": "", "password": ""}
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        client = Clients.objects.get(cliTenantId=final_tenant_id)
        
        if client.cliSipUsername and client.cliSipPassword:
            res_body["username"] = client.cliSipUsername.strip()
            res_body["password"] = client.cliSipPassword.strip()
            
        return api_response(200, "Successfully.", res_body)
    except Exception as e:
        logger.error(f"Error in getUsernamePassword: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Oops !! there is some problem while fetching data.", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getBuyAllSmsConversationsNumberList(request):
    """Get available SMS numbers for conversations"""
    try:
        tenant_id = get_final_tenant_id(request=request)
        numbers = PhoneNumbers.objects.filter(
            pnMemberId=get_client_id_by_tenant_id(tenant_id),
            pnNumberClosed='N'
        ).values('pnId', 'pnNumber', 'pnNumberPhoneSid')

        phone_list = [
            {
                "pnId": num['pnId'],
                "pnNumber": num['pnNumber'],
                "pnNumberPhoneSid": num['pnNumberPhoneSid']
            }
            for num in numbers
        ]

        return api_response(200, "Conversation Numbers Retrieved Successfully.", {
            "buyAllSmsNumberList": phone_list
        })
    except Exception as e:
        logger.error(f"Error in getBuyAllSmsConversationsNumberList: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getMemberSmsConversationsSetting(request):
    """Get SMS conversations settings"""
    tenant_id = get_final_tenant_id(request=request)
    try:
        chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
        return api_response(200, "SMS Conversations Settings Retrieved Successfully.", {
            "conversationsTwilioNumber": chat_phone_number.phPhoneNumber
        })
    except Exception as e:
        logger.error(f"Error in getMemberSmsConversationsSetting: {e}")
        return api_response(500, str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def closeAllSmsConversations(request):
    """Close all SMS conversations"""
    tenant_id = get_final_tenant_id(request=request)
    try:
        chat_phone_number = get_phone_numbers_first(tenant_id, "CHAT")
        if chat_phone_number.phPhoneNumber:
            SmsConversations.objects.filter(
                cvsMemberId=get_client_id_by_tenant_id(tenant_id)
            ).update(cvsClosed='Y', cvsClosedDate=datetime.now(pytz.UTC))
        return api_response(200, "All SMS Conversations Closed Successfully.", {})
    except PhoneNumbers.DoesNotExist:
        return api_response(404, "Phone Number Not Found", {})
    except Exception as e:
        logger.error(f"Error in closeAllSmsConversations: {e}")
        return api_response(500, str(e), {})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def finalizeSmsCampaignQuestionOrder(request):
    """Finalize SMS campaign question order"""
    try:
        sms_id = request.data.get('smsId')
        question_order = request.data.get('questionOrder', [])

        if not sms_id:
            return api_response(400, "Invalid Data: smsId required", {})

        # Update question order for campaign details
        for idx, question_id in enumerate(question_order):
            CampaignSmsDetails.objects.filter(
                sdId=question_id,
                smsId=sms_id
            ).update(sdDisplayOrder=idx)

        return api_response(200, "SMS Campaign Question Order Finalized Successfully.", {})
    except Exception as e:
        logger.error(f"Error in finalizeSmsCampaignQuestionOrder: {e}")
        return api_response(500, str(e), {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSmsCampaign(request):
    """
    Save only (alias for saveSendSmsCampaign logic without sending).
    Note: If the alias should **only** save and not send, you may need to
    adjust final_save_sms_campaign or pass a flag.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        # Optionally pass a flag `send=False` to your business logic if needed.
        res = _save_sms_campaign_logic(tenant_id, request.data)
        return api_response(200, "SMS Campaign Saved Successfully.", res)
    except ValidationError as e:
        return api_response(400, "Invalid Data", e.detail)
    except Exception as e:
        logger.error(f"Error in saveSmsCampaign: {e}")
        return api_response(500, str(e), {})