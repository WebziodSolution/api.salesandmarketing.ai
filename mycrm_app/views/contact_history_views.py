import logging
import requests
from django.db import connection
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from rest_framework import status
from common_app.models import (CampaignsSmsSend, CampaignSmsReply, PollingSmsSend, SpSmsPolling, SmsConversations, SmsConversationsDetails, CampaignTransaction, CampaignSendSms, Clients)
from common_app.services import CommonServices
from common_app.utils import get_final_tenant_id, display_date_time, api_response, get_phone_numbers_first, get_client_id_by_tenant_id, get_tenant_id_by_client_id
from mycrm_app.serializers import (CallingHistoryDtoSerializer, ConversationsHistoryDtoSerializer)
from datetime import datetime
import math

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_send_emails(request, emailId):
    final_tenant_id = get_final_tenant_id(request=request)

    email_history_dtos = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT es.CEQ_SUBJECT, es.CEQ_SEND_ON_DATE 
                FROM CAMPAIGN_EMAIL_SENT se
                JOIN CAMPAIGN_EMAIL_QUEUED es ON se.CES_SEND_ID = es.CEQ_ID
                WHERE se.CES_CLIENT_ID = %s AND se.CES_EMAIL_ID = %s
                ORDER BY se.CES_ID DESC
                FETCH FIRST 5 ROWS ONLY
            """, [final_tenant_id, emailId])
            rows = cursor.fetchall()
            
            for row in rows:
                subject = row[0]
                send_on_date = row[1]
                
                # Java: EmailHistoryDto.setSubject("Email sent with subject is : "+campaignsEmailSend.getSubject())
                # Java: CommonFunction.displayDateTime formats as MM/dd/yyyy HH:mm:ss
                formatted_date = ""
                if send_on_date:
                    if isinstance(send_on_date, datetime):
                        formatted_date = send_on_date.strftime('%m/%d/%Y %H:%M:%S')
                    else:
                        # Fallback for unexpected types
                        formatted_date = str(send_on_date)

                email_history_dtos.append({
                    "subject": f"Email sent with subject is : {subject}",
                    "sendOnDate": formatted_date
                })
    except Exception as e:
        logger.error(f"[ memberId : {final_tenant_id} ] GetSendEmails Error : {e}")

    return api_response(status.HTTP_200_OK, "Email History Fetched Successfully.", {"emailHistory": email_history_dtos})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_outgoing_sms(request, emailId):
    final_tenant_id = get_final_tenant_id(request=request)

    outgoing_sms_history_dtos = []
    try:
        campaign_send_sms_list = CampaignSendSms.objects.filter(
            memberId=get_client_id_by_tenant_id(final_tenant_id), emailId=emailId
        ).order_by('-id')[:5]

        for se in campaign_send_sms_list:
            sms_name = ""
            if se.cssdId:
                try:
                    es = CampaignsSmsSend.objects.get(id=se.cssdId)
                    sms_name = es.smsName
                except CampaignsSmsSend.DoesNotExist:
                    pass
            
            sms_send_date = display_date_time(se.smsSendDate) if se.smsSendDate else None
            outgoing_sms_history_dtos.append({
                "smsName": f"SMS sent with title is : {sms_name}",
                "smsSendDate": sms_send_date
            })
    except Exception as e:
        logger.error(f"[ memberId : {final_tenant_id} ] GetOutgoingSMS Error : {e}")

    return api_response(status.HTTP_200_OK, "SMS History Fetched Successfully.", {"outgoingSmsHistory": outgoing_sms_history_dtos})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_incoming_sms(request, emailId):
    final_tenant_id = get_final_tenant_id(request=request)

    campaign_sms_reply_list = CampaignSmsReply.objects.filter(
        crMemberId=get_client_id_by_tenant_id(final_tenant_id), crEmailId=emailId
    ).order_by('-crId')[:5]

    incoming_sms_history_dtos = []
    for cr in campaign_sms_reply_list:
        incoming_sms_history_dtos.append({
            "crReply": cr.crReply,
            "crDate": display_date_time(cr.crDate)
        })

    return api_response(status.HTTP_200_OK, "SMS History Fetched Successfully.", {"incomingSmsHistory": incoming_sms_history_dtos})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_polling(request, emailId):
    final_tenant_id = get_final_tenant_id(request=request)

    polling_sms_send_list = PollingSmsSend.objects.filter(
        memberId=get_client_id_by_tenant_id(final_tenant_id), emailId=emailId
    ).order_by('-id')[:5]

    sms_polling_history_dtos = []
    for ps in polling_sms_send_list:
        sms_send_date = display_date_time(ps.smsSendDate) if ps.smsSendDate else None
        v_heading = None
        if ps.iSmspollingId:
            try:
                sp_sms_polling = SpSmsPolling.objects.get(iId=ps.iSmspollingId)
                v_heading = sp_sms_polling.vHeading
            except SpSmsPolling.DoesNotExist:
                pass
        
        sms_polling_history_dtos.append({
            "vHeading": v_heading,
            "smsSendDate": sms_send_date
        })

    return api_response(status.HTTP_200_OK, "SMS History Fetched Successfully.", {"smsPollingHistory": sms_polling_history_dtos})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def get_calling(request):
    final_tenant_id = get_final_tenant_id(request=request)

    serializer = CallingHistoryDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(status.HTTP_400_BAD_REQUEST, "Invalid data.", serializer.errors)
    
    data = serializer.validated_data
    sub_tenant_id = data.get('subTenantId')
    email_id = data.get('emailId')
    
    calling_history_dtos = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT cp.CP_DATE, cc.cc_duration 
                FROM CALLING_PARENT cp
                JOIN CALLING_CHILD cc ON cp.CP_ID = cc.CC_CP_ID
                WHERE cp.CP_CLIENT_ID = %s AND cc.CC_CLIENT_ID = %s
                ORDER BY cp.CP_ID DESC
                FETCH FIRST 5 ROWS ONLY
            """, [get_client_id_by_tenant_id(final_tenant_id), email_id])
            rows = cursor.fetchall()
        
        for row in rows:
            calling_history_dtos.append({
                "emailId": email_id,
                "firstName": data.get('firstName'),
                "LastName": data.get('LastName'),
                "subTenantId": sub_tenant_id,
                "cpDate": display_date_time(row[0]) if row[0] else None,
                "ccDuration": float(row[1]) if row[1] is not None else 0.0
            })
    except Exception as e:
        logger.error(f"GetCalling Error: {e}")

    return api_response(status.HTTP_200_OK, "Calling History Fetched Successfully.", {"callingHistory": calling_history_dtos})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def get_conversations(request):
    final_tenant_id = get_final_tenant_id(request=request)
    
    serializer = ConversationsHistoryDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(status.HTTP_400_BAD_REQUEST, "Invalid data.", serializer.errors)
    
    data = serializer.validated_data
    
    # Porting SMSInboxServicesImpl.getConversationsHistory
    # 1. cronConversationsRead
    cvs_id = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT sc.SC_ID 
                FROM SMS_CONVERSATIONS sc
                JOIN SMS_CONVERSATION_DETAILS scd ON sc.SC_ID = scd.SCD_SD_ID
                WHERE sc.SC_CLIENT_ID = %s AND sc.SC_CONTACT_NUMBER = %s AND scd.SCD_CLIENT_NUMBER = %s
                ORDER BY sc.SC_ID DESC
                FETCH FIRST 1 ROWS ONLY
            """, [get_client_id_by_tenant_id(final_tenant_id), data.get('memPhone'), data.get('contactPhoneNumber')])
            row = cursor.fetchone()
            if row:
                cvs_id = row[0]
    except Exception as e:
        logger.error(f"GetConversationsHistory Error 1: {e}")

    if cvs_id and cvs_id > 0:
        cron_conversations_read(cvs_id, data)

    final_con_history_dtos = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT SCD_SD_ID FROM SMS_CONVERSATION_DETAILS WHERE SCD_CLIENT_ID = %s GROUP BY SCD_SD_ID", [data.get('contactEmailId')])
            cvsd_cvs_id_list = [row[0] for row in cursor.fetchall()]

            if cvsd_cvs_id_list:
                # 3. findConversationsHistory
                in_clause = ', '.join(['%s'] * len(cvsd_cvs_id_list))
                query = f"""
                    SELECT scd.SCD_MESSAGE, scd.SCD_DATE, scd.SCD_SENDER, scd.SCD_CLIENT_ID, scd.SCD_ID, scd.SCD_SD_ID 
                    FROM SMS_CONVERSATIONS sc, SMS_CONVERSATION_DETAILS scd 
                    WHERE sc.SC_ID=scd.SCD_SD_ID AND sc.SC_CLIENT_ID=%s 
                    AND sc.SC_CONTACT_NUMBER=%s AND (scd.SCD_CLIENT_ID=%s OR scd.SCD_CLIENT_NUMBER=%s) 
                    AND sc.SC_ID IN ({in_clause}) 
                    ORDER BY scd.SCD_DATE, scd.SCD_ID
                """
                params = [get_client_id_by_tenant_id(final_tenant_id), data.get('memPhone'), data.get('contactPhoneNumber'), data.get('memPhone')] + cvsd_cvs_id_list
                cursor.execute(query, params)
                conversations_history = cursor.fetchall()
                
                rc = 1
                t_cvs_id = 0
                ci = 0
                olddetid = 0

                for conHist in conversations_history:
                    currdetid = int(conHist[4]) # cvsd_id
                    if ci == 0:
                        t_cvs_id = int(conHist[5]) # cvsd_cvs_id
                        if int(conHist[3]) != 0: # cvsd_client_id
                            ci = 1
                    
                    if olddetid != currdetid:
                        olddetid = currdetid
                    else:
                        if ci != 0:
                            conDto = {
                                "cvsdMessage": conHist[0],
                                "cvsdDate": display_date_time(conHist[1]) if conHist[1] else None,
                                "cvsdSender": conHist[2],
                                "cvsdClientId": int(conHist[3]),
                                "cvsdId": int(conHist[4]),
                                "cvsdCvsId": int(conHist[5]),
                                "contactEmailId": data.get('contactEmailId'),
                                "contactFirstName": data.get('contactFirstName'),
                                "contactLastName": data.get('contactLastName'),
                                "contactPhoneNumber": data.get('contactPhoneNumber'),
                                "contactCountryCallCode": data.get('contactCountryCallCode'),
                                "memPhone": data.get('memPhone'),
                                "memCountryCallCode": data.get('memCountryCallCode'),
                                "memFirstName": data.get('memFirstName'),
                                "memLastName": data.get('memLastName')
                            }
                            final_con_history_dtos.append(conDto)
                    
                    ci = 1
                    if t_cvs_id != int(conHist[5]):
                        ci = 0
                    rc += 1
    except Exception as e:
        logger.error(f"GetConversationsHistory Error 2: {e}")

    return api_response(status.HTTP_200_OK, "Conversations History Fetched Successfully.", {"conversationsHistory": final_con_history_dtos})

def cron_conversations_read(cvs_id, data):
    if cvs_id <= 0:
        return
    
    try:
        sms_conversations = SmsConversations.objects.get(cvsId=cvs_id)
        # Replicating logic
        tenant_id = get_tenant_id_by_client_id(sms_conversations.cvsMemberId)

        client = Clients.objects.get(cliTenantId=tenant_id)
        cli_sms_account_sid = client.cliSmsAccountSid
        chat_phone_number = get_phone_numbers_first(client.cliTenantId, "CHAT")
        
        if cli_sms_account_sid:
            telnyx_base_url = settings.TELNYX_BASE_URL
            telnyx_api_key = settings.TELNYX_API_KEY
            
            # Telnyx API Call: listConversation
            url = f"{telnyx_base_url}detail_records?filter[direction]=inbound&filter[profile_id]={cli_sms_account_sid}&filter[record_type]=messaging&filter[date_range]=today"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {telnyx_api_key}"
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                resp_data = response.json().get('data', [])
                for record in resp_data:
                    if chat_phone_number.phPhoneNumber == record.get('cld') and data.get('contactPhoneNumber') == record.get('cli'):
                        sid = record.get('id')
                        
                        # check if already exists
                        temp_cvsd_id = 0
                        try:
                            # getCvsdId(record.getSid(), cvsId)
                            cvsd_obj = SmsConversationsDetails.objects.filter(cvsdSid=sid, cvsdCvsId=cvs_id).first()
                            if cvsd_obj:
                                temp_cvsd_id = cvsd_obj.cvsdId
                        except Exception as e:
                            logger.error(f"CronConversationsRead Error 1: {e}")
                        
                        if temp_cvsd_id == 0:
                            sms_details = SmsConversationsDetails.objects.filter(cvsdCvsId=cvs_id, cvsdSender='m').order_by('cvsdId').first()
                            
                            # getMessageText
                            msg_url = f"{telnyx_base_url}messages/{sid}"
                            msg_resp = requests.get(msg_url, headers=headers)
                            msg_text = ""
                            if msg_resp.status_code == 200:
                                msg_text = msg_resp.json().get('data', {}).get('text', '')
                            
                            number_of_sms = 1
                            if msg_text and len(msg_text) > 160:
                                number_of_sms = math.ceil(len(msg_text) / 160)
                            
                            # Date formatting
                            date_created_str = record.get('created_at') # Assuming ISO format like 2023-10-27T10:00:00Z
                            try:
                                dt = datetime.fromisoformat(date_created_str.replace('Z', '+00:00'))
                            except:
                                dt = datetime.now()
                                
                            new_details = SmsConversationsDetails(
                                cvsdCvsId=cvs_id,
                                cvsdMessage=msg_text,
                                cvsdClientId=sms_details.cvsdClientId if sms_details else None,
                                cvsdClientNumber=sms_details.cvsdClientNumber if sms_details else None,
                                cvsdParticipantSid="",
                                cvsdSid=sid,
                                cvsdSender="c",
                                cvsdDate=dt
                            )
                            new_details.save()
                            
                            # Transaction logic
                            country_setting = CommonServices.country_setting_by_tenant_id(client.cliTenantId)
                            if number_of_sms > 0 and country_setting:
                                # getSmsConversationsTranId
                                # ctType = "sms conversations"
                                tran_exists = CampaignTransaction.objects.filter(
                                    ct_client_id=sms_conversations.cvsMemberId,
                                    tranCampaignId=cvs_id,
                                    tranType="sms conversations"
                                ).exists()
                                
                                if not tran_exists:
                                    trans_rate = country_setting.cnty_sms_conversations_per_price
                                    tt = number_of_sms * trans_rate
                                    CampaignTransaction.objects.create(
                                        ct_client_id=sms_conversations.cvsMemberId,
                                        tranCampaignId=cvs_id,
                                        tranType="sms conversations",
                                        tranTotalAmount=tt,
                                        tranStatus="uninvoiced"
                                    )
    except Exception as e:
        logger.error(f"CronConversationsRead Error: {e}")
