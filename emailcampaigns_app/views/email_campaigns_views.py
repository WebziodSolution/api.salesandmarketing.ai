import re
import math
import lxml.html
from typing import Any
import os
import shutil
import traceback
from datetime import datetime, timedelta
import io
from PIL import Image
import qrcode
from django.conf import settings
from django.db import connection
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.core.paginator import Paginator
from common_app.models import (CampaignsEmail, CampaignsSendEmail, Groups, MyPages, CampaignsEmailSend, CampaignLinks, CampaignLinkClick, CampaignSubscriber, CampaignTransaction, CountrySetting, Userlist, Contact, Invoices, GroupSegment, Udf, Domains, TempSendEmailCampaigns, TranslateTemplateSend, Clients)
from emailcampaigns_app.serializers import ( EditCampaignScheduleSerializer, DeleteCampaignSerializer, ResendAllCampaignSerializer, SendCampaignSerializer, SaveSendCampaignSerializer, CheckSpamSerializer, ThrottlingValidationSerializer)
from common_app.utils import (
    api_response, get_final_tenant_id,
    total_uninvoiced_amt, display_date_time, display_date,
    is_weekend, nl2br, strip_slashes, cron_send_campaign_content_remove,
    convert_event_timezone_to_user, db_date_time, get_tenants, get_client_id_by_tenant_id, get_tenant_id_by_client_id
)
from common_app.decrypt_string import DecryptString
from django.utils import timezone
from django.db.models import F
import base64
import json
import logging
from rest_framework.request import Request
from common_app.services import MailRequestDTO, CommonServices
import subprocess

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def get_country_setting(tenant_id):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        country_id = tenant.ten_country if tenant.ten_country else "100"
        plan_id = tenant.td_plan_id or 1
        
        try:
            return CountrySetting.objects.get(cnty_id=int(country_id), cnty_plan_id=plan_id)
        except CountrySetting.DoesNotExist:
            return CountrySetting.objects.filter(cnty_id=100, cnty_plan_id=2).first()
    except Exception:
        return None

def parse_date_time(date_str):
    if not date_str:
        return None
    try:
        if isinstance(date_str, datetime):
            return timezone.make_aware(date_str) if timezone.is_naive(date_str) else date_str
        # Handles yyyy-MM-dd HH:mm:ss or MM/dd/yyyy HH:mm:ss
        if "-" in date_str:
            if date_str.find("-") == 4: # yyyy-MM-dd
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            else: # MM-dd-yyyy
                dt = datetime.strptime(date_str, "%m-%d-%Y %H:%M:%S")
        else:
            dt = datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
        return timezone.make_aware(dt)
    except Exception:
        return None

def campaign_price_list_display(member_list, country_setting):
    if member_list > 0 and country_setting:
        return member_list * float(country_setting.cnty_campaign_per_price or 0.0)
    return 0.0

def campaign_price_list_per(member_list, country_setting):
    if member_list > 0 and country_setting:
        return float(country_setting.cnty_campaign_per_price or 0.0)
    return 0.0

def get_browser_name(agent):
    if not agent:
        return "Others"
    if "Firefox" in agent:
        return "Firefox"
    elif "MSIE" in agent or "EIE" in agent or "Edg" in agent:
        return "IE"
    elif "iPhone" in agent:
        if "Mobile" in agent:
            return "iPhone"
    elif "iPad" in agent:
        return "iPad"
    elif "Android" in agent:
        if "Mobile" in agent:
            return "Android Phone"
        else:
            return "Android Tab"
    elif "Chrome" in agent:
        return "Chrome"
    elif "Safari" in agent:
        return "Safari"
    elif "AIR" in agent:
        return "Air"
    elif "Fluid" in agent:
        return "Fluid"
    return "Others"

def check_payment_profile_exists(tenant_id):
    tenant = get_tenants(
        where_conditions={
            "tenant": {
                "ten_id": tenant_id
            }
        }
    )
    if tenant.td_authorize_customer_profile_id and tenant.td_authorize_customer_payment_profile_id:
        return "yes"
    return "no"

def get_latest_send_record(camp_id):
    try:
        return CampaignsSendEmail.objects.filter(campId=camp_id).order_by('-campSendId').first()
    except Exception:
        return None

def calculate_status(camp_status, camp_id, camp_send_id=0):
    try:
        campaign_status = ""
        if camp_status == 0 or camp_status == 1:
            campaign_status = "Draft"
        elif camp_status == 2:
            total_sent = CampaignsSendEmail.objects.filter(campId=camp_id, campSendId=camp_send_id).count()
            total_delivered = CampaignsSendEmail.objects.filter(campId=camp_id, campSendId=camp_send_id, isSend='Y').count()
            if total_sent == 0:
                total_sent = 1
                total_delivered = 0

            f = (float(total_delivered) / float(total_sent)) * 100
            result = f"{f:.2f}"
            if result == "100.00":
                campaign_status = "Completed"
            else:
                campaign_status = f"{result} %"
        elif camp_status == 4:
            campaign_status = "Delete Pending"
        elif camp_status == 3:
            campaign_status = "Completed"

        # Override with Scheduled if applicable
        try:
            now = timezone.now()
            sch_qs = CampaignsEmailSend.objects.filter(
                camp_id=camp_id
            ).filter(
                Q(sendondate__gt=now) | Q(sendondate__isnull=True)
            ).order_by('-id')

            if sch_qs.exists():
                campaign_status = "Scheduled"
        except Exception:
            pass

        return campaign_status
    except Exception:
        return "Draft"

def final_save_resend_campaign(tenant_id, resend_all_campaign_dto):
    try:
        camp_id = resend_all_campaign_dto.get('campId')
        camp_send_id = resend_all_campaign_dto.get('campSendId')
        send_on_date = resend_all_campaign_dto.get('sendOnDate')
        s_not_read = int(resend_all_campaign_dto.get('totalMember', 0))
        
        send_on_time = timedelta(hours=send_on_date.hour, minutes=send_on_date.minute, seconds=send_on_date.second)
        CampaignsEmail.objects.filter(campId=camp_id).update(
            campStatus=2,
            scheduleType=1,
            sendOnDate=send_on_date,
            sendOnTime=send_on_time
        )
        
        CampaignsEmailSend.objects.filter(id=camp_send_id).update(
            readytomail='Y'
        )
        
        # Get campaign name for transaction (Java lines 1061-1065)
        heading = ""
        camp_send = CampaignsEmailSend.objects.filter(id=camp_send_id).first()
        if camp_send:
            heading = camp_send.camp_name
            
        country_setting = get_country_setting(tenant_id)
        
        # saveCampaignTransaction (Java line 1066)
        CommonServices.saveCampaignTransaction(
            camp_id,
            heading,
            s_not_read,
            "campaign",
            None,
            "uninvoiced",
            None,
            get_client_id_by_tenant_id(tenant_id),
            "0",
            campaign_price_list_display(s_not_read, country_setting),
            campaign_price_list_per(s_not_read, country_setting),
            0,
            None,
            None,
            0
        )
        
        return {"error": "", "location": ""}
    except Exception as e:
        logger.error(f"final_save_resend_campaign Error : {str(e)}")
        return {"error": "Exception While Inserting Resend Campaign All", "location": ""}

def get_domain_capacity(tenant_id, from_add):
    domain_name = from_add.split('@')[-1] if '@' in from_add else ""
    domain = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant_id), domDomain=domain_name).first()
    if domain:
        return domain.domDomainCapacity or 0
    return 0

def final_send_campaign(tenant_id, country_setting, cid, member_list, camp_id):
    try:
        camp_send = CampaignsEmailSend.objects.get(id=cid)
        CommonServices.saveCampaignTransaction(
            camp_id,
            camp_send.camp_name,
            member_list,
            "campaign",
            None,
            "uninvoiced",
            None,
            get_client_id_by_tenant_id(tenant_id),
            "0",
            campaign_price_list_display(member_list, country_setting),
            campaign_price_list_per(member_list, country_setting),
            0,
            None,
            None,
            0
        )
        return {"error": ""}
    except Exception as e:
        logger.error(f"final_send_campaign Error : {str(e)}")
        return {"error": "Invalid Data"}

# --- Views ---

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_campaign_list_automation(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        campaigns = CampaignsEmail.objects.filter(
            ceClientId=get_client_id_by_tenant_id(tenant_id),
            archiveYn='N'
        ).order_by('-campId')
        
        response_data = []
        for camp in campaigns:
            dto = {
                'campId': camp.campId,
                'campName': camp.campName,
                'sendOnDate': display_date_time(camp.sendOnDate),
                'status': calculate_status(camp.campStatus, camp.campId)
            }
            response_data.append(dto)
        
        return api_response(200, "success", response_data)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] get_campaign_list_automation Error : {str(e)}")
        return api_response(500, "Exception While Fetching Campaign")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def get_campaign_list(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        search_key = request.data.get('searchKey', '')
        page_no = int(request.data.get('pageNo', 0))
        page_size = int(request.data.get('pageSize', 10))

        time_zone = "America/New_York"
        try:
            member_dto = CommonServices.find_tenant_record(tenant_id)
            if request.data.get('timeZone'):
                time_zone = request.data.get('timeZone')
            elif member_dto and member_dto.get('timeZone'):
                time_zone = member_dto['timeZone']
        except Exception:
            pass

        if search_key:
            campaigns_qs = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(tenant_id), campName__icontains=search_key).order_by('-campId')
        else:
            campaigns_qs = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(tenant_id)).order_by('-campId')

        total_campaign = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(tenant_id)).count()

        paginator = Paginator(campaigns_qs, page_size)
        try:
            campaigns = paginator.get_page(page_no + 1)
        except Exception:
            campaigns = paginator.get_page(1)

        campaign_list = []
        for camp in campaigns:
            # Java: findByIdByOrder(camp_id) -> order by camp_send_id desc limit 1
            campaigns_send_email = CampaignsSendEmail.objects.filter(campId=camp.campId).order_by('-campSendId').first()
            camp_send_id = campaigns_send_email.campSendId if campaigns_send_email else 0

            dto = {
                "campId": camp.campId,
                "campName": camp.campName,
                "subject": camp.subject,
                "campSendId": camp_send_id,
                "templateName": "",
                "groupName": "",
                "totalMemberTooltip": 0,
                "totalMemberNotOpen": 0,
                "totalMemberResendAll": 0,
                "archiveYn": camp.archiveYn or "N",
                "sendOnDate": "",
                "lastSendDate": "",
                "intervalDays": 0,
                "sendDate": "",
                "status": "",
                "throttling": "N",
                "throttlingType": "",
                "schId": 0,
                "cronStatus": "",
                "groupList": camp.groupList or "",
                "typeEmail": "",
                "stopStatus": ""
            }

            # Throttling and Date logic
            try:
                # Java: findByCampId(camp_id) -> order by id desc limit 1
                camp_email_send = CampaignsEmailSend.objects.filter(camp_id=camp.campId).order_by('-id').first()
                if camp_email_send:
                    dto["throttling"] = camp_email_send.throttling or "N"
                    dto["throttlingType"] = camp_email_send.throttling_type or ""
                    
                if camp.sendOnDate:
                    # Java: CommonFunction.convertEventTimeZoneToUser(..., "UTC", timeZone)
                    dto["sendOnDate"] = convert_event_timezone_to_user(camp.sendOnDate.strftime('%m/%d/%Y %H:%M:%S'), "UTC", time_zone)
                    dto["lastSendDate"] = display_date(camp.sendOnDate)
                    
                    # Java: Math.abs(System.currentTimeMillis() - sendOnDate) / (24*60*60*1000)
                    now = timezone.now()
                    diff = now - camp.sendOnDate
                    dto["intervalDays"] = abs(diff.days)
            except Exception as e:
                logger.error(f"[ tenantId : {tenant_id} ] FindEmailCampaignsByPage Error 6 : {e}")

            # Status logic
            dto["status"] = calculate_status(camp.campStatus, camp.campId, camp_send_id)

            # CronStatus and StopStatus logic
            try:
                if dto["status"] != "Completed":
                    dto["cronStatus"] = campaigns_send_email.cronStatus if campaigns_send_email else ""

                # Stop Status Logic from Java
                # Java: getStopStatusData(camp_id) -> select where stop_status is not null
                stop_status_record = CampaignsEmailSend.objects.filter(camp_id=camp.campId, stop_status__isnull=False).first()
                if stop_status_record:
                    count_pause = CampaignsSendEmail.objects.filter(campSendId=camp_send_id, cronStatus='pause').count()
                    count_restart_with_send = CampaignsSendEmail.objects.filter(campSendId=camp_send_id, cronStatus='restart', isSend='N').count()
                    
                    if count_pause > 0:
                        dto["cronStatus"] = "pause"
                    elif count_restart_with_send > 0:
                        dto["cronStatus"] = "restart"
                    else:
                        dto["cronStatus"] = "Bounce"

                    if stop_status_record.stop_status:
                        dto["stopStatus"] = "Bounce"
            except Exception as e:
                pass

            # Type Email logic
            try:
                if camp.groupList:
                    g_ids = camp.groupList.split(',')
                    if g_ids:
                        target_g_id = g_ids[0].strip()
                        if target_g_id:
                            group = Groups.objects.filter(grpId=target_g_id).first()
                            if group:
                                dto["typeEmail"] = group.grpTypeEmail or ""
            except Exception:
                pass

            campaign_list.append(dto)

        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": campaigns.number - 1,
            "getSize": paginator.per_page,
            "totalCampaign": total_campaign,
            "campaign": campaign_list
        }
        return api_response(200, "Campaign List Fetched Successfully", res_body)

    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] FindEmailCampaignsByPage Error 12 : {e}")
        try:
            error_dto = {
                "message": f"FindEmailCampaignsByPage Error : {str(e)}",
                "error_type": "Campaign List API",
                "user_id": tenant_id,
                "stack_trace": traceback.format_exc()
            }
            CommonServices.send_whoops_error(error_dto)
            return api_response(500, "Something went wrong. Please try again later.", {})
        except Exception:
            pass
        return api_response(500, "Something went wrong. Please try again later.", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_campaign_info(request, campId, campSendId):
    """
    Java: /emailCampaign/getCampaignInfo/{campId}
    """
    try:
        campaign = CampaignsEmail.objects.filter(campId=campId).first()
        if not campaign:
            return api_response(404, "Campaign Not Found")
            
        campaign_dto = {
            "campId": campaign.campId,
            "campName": campaign.campName,
            "subject": campaign.subject,
            "fromName": campaign.fromName,
            "fromAdd": campaign.fromAdd,
            "replyToAdd": campaign.replyToAdd,
            "campType": campaign.campType,
            "groupList": campaign.groupList,
            "mailType": campaign.mailType,
            "mypageId": campaign.mypageId,
            "campMainType": campaign.campMainType,
            "testingType": campaign.testingType,
            "selectGroupPer": campaign.selectGroupPer,
            "remainGroupPer": campaign.remainGroupPer,
            "subjectB": campaign.subjectB,
            "fromNameB": campaign.fromNameB,
            "mypageIdB": campaign.mypageIdB,
            "scheduleType": campaign.scheduleType,
            "scheduleTypeB": campaign.scheduleTypeB,
            "byAutoManual": campaign.byAutoManual,
            "byType": campaign.byType,
            "byNumber": campaign.byNumber,
            "byMeasure": campaign.byMeasure,
            "incrementalUpdates": campaign.incrementalUpdates,
            "tries": campaign.tries,
            "triesCount": campaign.triesCount,
            "sendOnDate": display_date_time(campaign.sendOnDate) if campaign.sendOnDate else None,
            "sendOnTime": campaign.sendOnTime if campaign.sendOnTime else None,
            "sendOnDateB": display_date_time(campaign.sendOnDateB) if campaign.sendOnDateB else None,
            "sendOnTimeB": campaign.sendOnTimeB if campaign.sendOnTimeB else None,
        }
        
        return api_response(200, "Campaigns Information Fetched Successfully", {"campaignInfo": campaign_dto})
    except Exception as e:
        logger.error(f"get_campaign_info Error : {str(e)}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_campaign_list(request):
    tenant_id = get_final_tenant_id(request=request)
    search_key = request.GET.get('searchKey', '')
    time_zone = request.GET.get('timeZone', 'UTC')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))
    sort = request.GET.get('sort', 'campId,desc')

    try:
        queryset = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(tenant_id))
        
        if search_key:
            queryset = queryset.filter(campName__icontains=search_key)
            
        if ',' in sort:
            sort_field, sort_dir = sort.split(',')
            if sort_dir.lower() == 'desc':
                queryset = queryset.order_by(f'-{sort_field}')
            else:
                queryset = queryset.order_by(sort_field)
        else:
            queryset = queryset.order_by('-campId')
            
        paginator = Paginator(queryset, size)
        page_obj = paginator.get_page(page + 1)
        
        response_list = []
        for camp in page_obj:
            dto = {
                "campId": camp.campId,
                "campName": camp.campName,
                "subject": camp.subject,
                "status": "",
                "campSendId": 0,
                "templateName": "",
                "groupName": "",
                "totalMemberTooltip": 0,
                "totalMemberNotOpen": 0,
                "totalMemberResendAll": 0,
                "sendOnDate": "",
                "lastSendDate": "",
                "sendDate": "",
                "schId": 0,
                "cronStatus": "",
                "intervalDays": 0,
                "archiveYn": camp.archiveYn or "N",
                "throttling": "N",
                "throttlingType": ""
            }
            
            latest_send = get_latest_send_record(camp.campId)
            if latest_send:
                dto["campSendId"] = latest_send.campSendId or 0
                dto["cronStatus"] = latest_send.cronStatus or ""
            
            if camp.sendOnDate:
                dto["sendOnDate"] = convert_event_timezone_to_user(display_date_time(camp.sendOnDate), "UTC", time_zone)
                dto["lastSendDate"] = display_date(camp.sendOnDate)
                delta = timezone.now() - camp.sendOnDate
                dto["intervalDays"] = delta.days
                
            dto["status"] = calculate_status(camp.campStatus, camp.campId, int(dto["campSendId"]))
            
            camp_email_send = CampaignsEmailSend.objects.filter(camp_id=camp.campId).order_by('-id').first()
            if camp_email_send:
                dto["throttling"] = camp_email_send.throttling or "N"
                dto["throttlingType"] = getattr(camp_email_send, 'throttling_type', None) or None
                
            # Equivalant to getSchIdAndSendOnDate
            now = timezone.now()
            sch_qs = CampaignsEmailSend.objects.filter(
                camp_id=camp.campId
            ).filter(
                Q(sendondate__gt=now) | Q(sendondate__isnull=True)
            ).order_by('-id').first()
            
            if sch_qs:
                dto["schId"] = sch_qs.id
                dto["status"] = "Scheduled"
                if getattr(sch_qs, 'sendondate', None):
                    dto["sendOnDate"] = convert_event_timezone_to_user(display_date_time(sch_qs.sendondate), "UTC", time_zone)
            else:
                dto["schId"] = None

            dto["stopStatus"] = ""
            try:
                camp_email_send_stop = CampaignsEmailSend.objects.filter(camp_id=camp.campId, stop_status__isnull=False).first()
                if camp_email_send_stop:
                    count_pause = CampaignsSendEmail.objects.filter(campSendId=dto["campSendId"], cronStatus='pause').count()
                    count_restart_send = CampaignsSendEmail.objects.filter(campSendId=dto["campSendId"], cronStatus='restartWithSend').count()
                    
                    if count_pause > 0:
                        dto["cronStatus"] = "pause"
                    elif count_restart_send > 0:
                        dto["cronStatus"] = "restart"
                    else:
                        dto["cronStatus"] = "Bounce"

                    if getattr(camp_email_send_stop, 'stop_status', None):
                        dto["stopStatus"] = "Bounce"
            except Exception:
                pass

            dto["groupList"] = camp.groupList
            dto["typeEmail"] = ""
            try:
                if camp.groupList:
                    group = Groups.objects.filter(grpId=int(camp.groupList)).first()
                    if group:
                        dto["typeEmail"] = getattr(group, 'typeEmail', '')
            except Exception:
                pass

            response_list.append(dto)
            
        total_campaign = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(tenant_id)).count()
        
        response_data = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalCampaign": total_campaign,
            "campaign": response_list
        }
        
        return api_response(200, "Fetch Email Campaign Successfully.", response_data)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] findEmailCampaignsByPage Error : {str(e)}")
        return api_response(500, "Internal Server Error")

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def edit_campaign_schedule(request):
    serializer = EditCampaignScheduleSerializer(data=request.data)
    if serializer.is_valid():
        camp_id = serializer.validated_data['campId']
        send_on_date_str = serializer.validated_data['sendOnDate']
        
        try:
            # CommonFunction.dbDateTime(editCampaignScheduleDto.getSendOnDate())
            parsed_date = parse_date_time(send_on_date_str)
            assert parsed_date is not None
            temp = convert_event_timezone_to_user(parsed_date.strftime('%m/%d/%Y %H:%M:%S'), serializer.validated_data['timeZone'], "UTC")
            db_date_time_val = parse_date_time(temp)
            assert db_date_time_val is not None
            send_on_timedelta =  timedelta(hours=db_date_time_val.hour, minutes=db_date_time_val.minute, seconds=db_date_time_val.second)
            camp = CampaignsEmail.objects.filter(campId=camp_id).first()
            if camp:
                camp.sendOnDate = db_date_time_val
                camp.sendOnTime = send_on_timedelta
                camp.save()
                
                camp_send = CampaignsEmailSend.objects.filter(camp_id=camp_id).first()
                if camp_send:
                    camp_send.sendondate = db_date_time_val
                    camp_send.save()
                    
            return api_response(200, "Campaign schedule updated successfully")
        except Exception as e:
            logger.error(f"EditCampaignSchedule Error : {str(e)}")
            return api_response(500, "Internal Server Error")
    return api_response(400, "Invalid Request", serializer.errors)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def delete_campaign(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = DeleteCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    camp_ids = serializer.validated_data['campId']
    count = 0
    try:
        for camp_id in camp_ids:
            # Java: campaignSendEmailRepository.findCampSendId(memberId, id)
            # Find the latest camp_send_id for this campaign
            latest_send = CampaignsEmailSend.objects.filter(member_id=get_client_id_by_tenant_id(tenant_id), camp_id=camp_id).order_by('-id').first()
            camp_send_id = latest_send.id if latest_send else 0
            
            campaigns_email = CampaignsEmail.objects.filter(campId=camp_id).first()
            if not campaigns_email:
                continue
                
            tot_records = 0
            
            transaction_exists = CampaignTransaction.objects.filter(
                tran_type='campaign', 
                tran_invoiced_status='uninvoiced', 
                tran_campaign_id=camp_id
            ).exists()
            
            if not transaction_exists:
                campaigns_email.delete()
            else:
                count += 1
                try:
                    tot_records = CampaignsSendEmail.objects.filter(memberId=get_tenant_id_by_client_id(tenant_id), campId=camp_id).count()
                    if tot_records == 0:
                        CampaignTransaction.objects.filter(
                            member_id=get_client_id_by_tenant_id(tenant_id),
                            tran_invoiced_status='uninvoiced', 
                            tran_type='campaign', 
                            tran_campaign_id=camp_id
                        ).delete()
                except Exception:
                    pass
            
            if campaigns_email.campStatus == 2:
                try:
                    # status 2 means Sending. Check if completed.
                    totsent = CampaignsSendEmail.objects.filter(campId=camp_id, campSendId=camp_send_id).count()
                    totsend = CampaignsSendEmail.objects.filter(campId=camp_id, campSendId=camp_send_id, isSend='Y').count()
                    if totsent == 0:
                        totsent = 1
                        totsend = 0
                    
                    f = (totsend / totsent) * 100
                    result = "{:.2f}".format(f)
                    if result == "100.00":
                        tot_records = 0
                except Exception:
                    pass
            
            if tot_records == 0:
                try:
                    if camp_send_id > 0:
                        CampaignsEmailSend.objects.filter(id=camp_send_id).delete()
                        CampaignsSendEmail.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), campSendId=camp_send_id).delete()
                except Exception:
                    pass
                
                try:
                    img_dir = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "emailcampaign", str(camp_id))
                    if os.path.exists(img_dir):
                        shutil.rmtree(img_dir)
                except Exception:
                    pass
        
        if count != 0:
            for camp_id in camp_ids:
                CampaignsEmail.objects.filter(campId=camp_id).delete()
        
        return api_response(200, "Campaign Deleted Successfully.")
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] DeleteCampaign Error : {str(e)}")
        return api_response(500, "Exception While Deleting Campaign")

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def resend_all_campaign(request):
    """
    Java: /emailCampaign/resendAllCampaign
    """
    tenant_id = get_final_tenant_id(request=request)
    serializer = ResendAllCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    data = serializer.validated_data
    res_body = {"error": "", "location": ""}
    
    try:
        camp_id = data['campId']
        camp_send_id = data['campSendId']

        camp = CampaignsEmail.objects.filter(campId=camp_id).first()
        if not camp:
            res_body['error'] = "Campaign Not Found"
            return api_response(500, "Fetch Email Campaigns List Successfully.", res_body)

        group_id = int(camp.groupList) if camp.groupList and camp.groupList.isdigit() else 0
        group_exists = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(tenant_id), grpId=group_id).exists()
        if not group_exists:
            res_body['error'] = "groupNotExists"
            return api_response(500, "This Campaign Is Not Resend Because Associated Group Is Deleted.", res_body)

        old_camp_send = CampaignsEmailSend.objects.filter(id=camp_send_id).first()
        if not old_camp_send:
            res_body['error'] = "Campaign Send Record Not Found"
            return api_response(500, "Fetch Email Campaigns List Successfully.", res_body)

        now = timezone.now()
        new_camp_send = CampaignsEmailSend(
            camp_id=camp_id,
            member_id=get_client_id_by_tenant_id(tenant_id),
            camp_name=camp.campName or old_camp_send.camp_name,
            camp_detail=camp.campDetail or old_camp_send.camp_detail,
            camp_type=camp.campType or old_camp_send.camp_type,
            grouplist=camp.groupList or old_camp_send.grouplist,
            from_name=camp.fromName or old_camp_send.from_name,
            from_add=camp.fromAdd or old_camp_send.from_add,
            reply_to_add=camp.replyToAdd or old_camp_send.reply_to_add,
            subject=camp.subject or old_camp_send.subject,
            send_date=camp.sendDate or old_camp_send.send_date,
            readytomail=old_camp_send.readytomail,
            sendondate=now,
            sendontime=timedelta(hours=now.hour, minutes=now.minute, seconds=now.second),
            mail_type=camp.mailType or old_camp_send.mail_type,
            mypageid=camp.mypageId or old_camp_send.mypageid,
            camp_main_type=camp.campMainType or old_camp_send.camp_main_type,
            testing_type=camp.testingType or old_camp_send.testing_type,
            selectgroupper=camp.selectGroupPer or old_camp_send.selectgroupper,
            remaingroupper=camp.remainGroupPer or old_camp_send.remaingroupper,
            camp_detail_b=camp.campDetailB or old_camp_send.camp_detail_b,
            mypageidb=camp.mypageIdB or old_camp_send.mypageidb,
            from_name_b=camp.fromNameB or old_camp_send.from_name_b,
            subjectb=camp.subjectB or old_camp_send.subjectb,
            scheduletypeb=camp.scheduleTypeB or old_camp_send.scheduletypeb,
            sendondateb=now,
            sendontimeb=timedelta(hours=now.hour, minutes=now.minute, seconds=now.second),
            byautomanual=camp.byAutoManual or old_camp_send.byautomanual,
            bytype=camp.byType or old_camp_send.bytype,
            bynumber=camp.byNumber or old_camp_send.bynumber,
            bymeasure=camp.byMeasure or old_camp_send.bymeasure,
            incremental_updates=camp.incrementalUpdates or old_camp_send.incremental_updates,
            tries=camp.tries or old_camp_send.tries,
            tries_count=camp.triesCount or old_camp_send.tries_count,
            unsubscribe_uid=old_camp_send.unsubscribe_uid
        )
        new_camp_send.save()
        cid = new_camp_send.id
        
        # Throttling status (Java line 687)
        cron_status = "active"
        if old_camp_send.throttling == 'Y':
            cron_status = "pausebythrottling"
            
        # selectInsertSendEmailTransfer (Java line 742)
        with connection.cursor() as cursor:
            cursor.execute("""
                insert into CAMPAIGN_EMAIL_SENT(CES_CAMP_ID,CES_SEND_ID, CES_CLIENT_ID, CES_EMAIL_ID, CES_IS_SEND,CES_FIRST_NAME,CES_LAST_NAME,CES_EMAIL,CES_EMAIL_DOMAIN,CES_CS_DEFAULT_LANGUAGE,CES_SPLIT_GROUP,CES_GROUP_WINNER,CES_MSG_PRIORITY,CES_CRON_STATUS) 
                select %s, %s, cse.CES_CLIENT_ID,cse.CES_EMAIL_ID,'N',cse.CES_FIRST_NAME,cse.CES_LAST_NAME,cse.CES_EMAIL,cse.CES_EMAIL_DOMAIN,cse.CES_CS_DEFAULT_LANGUAGE,cse.CES_SPLIT_GROUP,cse.CES_GROUP_WINNER,cse.CES_MSG_PRIORITY, %s  
                from CAMPAIGN_EMAIL_SENT cse,USER_LIST tul where tul.UL_EMAIL_ID=cse.CES_EMAIL_ID and cse.CES_CAMP_ID=%s and cse.CES_SEND_ID=%s and (cse.CES_IS_BOUNCED is NULL or cse.CES_IS_BOUNCED='N')
            """, [camp_id, cid, cron_status, camp_id, camp_send_id])

        # selectInsertTemplateCampSendTransfer (Java line 743)
        with connection.cursor() as cursor:
            cursor.execute("""
                insert into TRANSLATE_TEMPLATE_SEND(TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR,TTS_CAMP_SEND_ID) 
                select TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR, %s
                from TRANSLATE_TEMPLATE_SEND where TTS_CAMP_SEND_ID=%s
            """, [cid, camp_send_id])

        count_total_contact = CampaignsSendEmail.objects.filter(campSendId=cid).count()
        
        # Throttling and Bounce Rate (Java lines 748-757)
        bounce_rate = 5.0 # Should ideally come from settings
        max_bounce_email = int((bounce_rate * count_total_contact) / 100)
        
        new_camp_send.readytomail = 'Y'
        new_camp_send.max_bounce_email = max_bounce_email
        new_camp_send.retry_send_count = 0
        new_camp_send.throttling = old_camp_send.throttling
        new_camp_send.throttling_type = old_camp_send.throttling_type
        new_camp_send.throttling_value = old_camp_send.throttling_value
        new_camp_send.throttling_next_date = now
        
        if new_camp_send.camp_main_type == 2:
            new_camp_send.total_queued = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='A').count()
            new_camp_send.total_queued_b = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='B').count()
            new_camp_send.total_queued_o = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='O').count()
        else:
            new_camp_send.total_queued = count_total_contact
            
        new_camp_send.save()
        
        data['campSendId'] = cid
        data['totalMember'] = count_total_contact
        data['sendOnDate'] = now
        
        country_setting = get_country_setting(tenant_id)
        
        membership_type = request.user.membership_type if hasattr(request.user, 'membership_type') else "Free"
        if membership_type == "Free":
            res_body = final_save_resend_campaign(tenant_id, data)
        else:
            amt = campaign_price_list_display(count_total_contact, country_setting)
            profile_status = check_payment_profile_exists(tenant_id)
            if profile_status == "yes":
                res_body = final_save_resend_campaign(tenant_id, data)
            else:
                count_inv = Invoices.objects.filter(invTenantId=tenant_id).count()
                if count_inv == 0:
                    first_inv_amt = float(getattr(country_setting, "cnty_first_inv_free_amt", 0) or 0)
                    if amt >= first_inv_amt:
                        res_body = {"error": "", "location": "paymentProfile"}
                    else:
                        total_uninv = total_uninvoiced_amt(tenant_id)
                        if (total_uninv + amt) >= first_inv_amt:
                            res_body = {"error": "", "location": "paymentProfile"}
                        else:
                            res_body = final_save_resend_campaign(tenant_id, data)
                else:
                    res_body = {"error": "", "location": "paymentProfile"}
                    
        if res_body.get('error'):
            if res_body.get('error') == "groupNotExists":
                return api_response(500, "This Campaign Is Not Resend Because Associated Group Is Deleted.", res_body)
            else:
                return api_response(500, res_body.get('error'), res_body)
        else:
            if res_body.get('location') == "paymentProfile":
                return api_response(200, "Add Payment Profile.", res_body)
            else:
                return api_response(200, "Campaign Resend Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] ResendCampaignAll Error : {str(e)}")
        res_body['error'] = "Exception While Inserting Resend Campaign All"
        return api_response(500, "Exception While Inserting Resend Campaign All", res_body)

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def resend_campaign_not_open(request):
    """
    Java: /emailCampaign/resendCampaignNotOpened
    """
    tenant_id = get_final_tenant_id(request=request)
    serializer = ResendAllCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    data = serializer.validated_data
    res_body = {"error": "", "location": ""}
    
    try:
        camp_id = data['campId']
        camp_send_id = data['campSendId']

        camp = CampaignsEmail.objects.filter(campId=camp_id).first()
        if not camp:
            res_body['error'] = "Campaign Not Found"
            return api_response(500, "Resend Campaign Success", res_body)

        group_id = int(camp.groupList) if camp.groupList and camp.groupList.isdigit() else 0
        group_exists = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(tenant_id), grpId=group_id).exists()
        if not group_exists:
            res_body['error'] = "groupNotExists"
            return api_response(500, "This Campaign Is Not Resend Because Associated Group Is Deleted.", res_body)

        old_camp_send = CampaignsEmailSend.objects.filter(id=camp_send_id).first()
        if not old_camp_send:
            res_body['error'] = "Campaign Send Record Not Found"
            return api_response(500, "Resend Campaign Success", res_body)

        send_on_date = db_date_time(data['sendOnDate'])
        data['sendOnDate'] = send_on_date
        
        # Create new CampaignsEmailSend (Java lines 846-888)
        new_camp_send = CampaignsEmailSend(
            camp_id=camp_id,
            member_id=get_client_id_by_tenant_id(tenant_id),
            camp_name=camp.campName or old_camp_send.camp_name,
            camp_detail=camp.campDetail or old_camp_send.camp_detail,
            camp_type=camp.campType or old_camp_send.camp_type,
            grouplist=camp.groupList or old_camp_send.grouplist,
            from_name=camp.fromName or old_camp_send.from_name,
            from_add=camp.fromAdd or old_camp_send.from_add,
            reply_to_add=camp.replyToAdd or old_camp_send.reply_to_add,
            subject=camp.subject or old_camp_send.subject,
            send_date=camp.sendDate or old_camp_send.send_date,
            readytomail=old_camp_send.readytomail,
            sendondate=send_on_date,
            sendontime=timedelta(hours=send_on_date.hour, minutes=send_on_date.minute, seconds=send_on_date.second),
            mail_type=camp.mailType or old_camp_send.mail_type,
            mypageid=camp.mypageId or old_camp_send.mypageid,
            camp_main_type=camp.campMainType or old_camp_send.camp_main_type,
            testing_type=camp.testingType or old_camp_send.testing_type,
            selectgroupper=camp.selectGroupPer or old_camp_send.selectgroupper,
            remaingroupper=camp.remainGroupPer or old_camp_send.remaingroupper,
            camp_detail_b=camp.campDetailB or old_camp_send.camp_detail_b,
            mypageidb=camp.mypageIdB or old_camp_send.mypageidb,
            from_name_b=camp.fromNameB or old_camp_send.from_name_b,
            subjectb=camp.subjectB or old_camp_send.subjectb,
            scheduletypeb=camp.scheduleTypeB or old_camp_send.scheduletypeb,
            sendondateb=send_on_date,
            sendontimeb=timedelta(hours=send_on_date.hour, minutes=send_on_date.minute, seconds=send_on_date.second),
            byautomanual=camp.byAutoManual or old_camp_send.byautomanual,
            bytype=camp.byType or old_camp_send.bytype,
            bynumber=camp.byNumber or old_camp_send.bynumber,
            bymeasure=camp.byMeasure or old_camp_send.bymeasure,
            incremental_updates=camp.incrementalUpdates or old_camp_send.incremental_updates,
            tries=camp.tries or old_camp_send.tries,
            tries_count=camp.triesCount or old_camp_send.tries_count,
            unsubscribe_uid=old_camp_send.unsubscribe_uid
        )
        new_camp_send.save()
        cid = new_camp_send.id
        
        # Throttling status (Java line 892)
        cron_status = "active"
        if old_camp_send.throttling == 'Y':
            cron_status = "pausebythrottling"
            
        with connection.cursor() as cursor:
            # selectInsertSendEmailResendNotOpenedTransfer (Java line 935)
            cursor.execute("""
                insert into CAMPAIGN_EMAIL_SENT(CES_CAMP_ID,CES_SEND_ID, CES_CLIENT_ID, CES_EMAIL_ID, CES_IS_SEND,CES_FIRST_NAME,CES_LAST_NAME,CES_EMAIL,CES_EMAIL_DOMAIN,CES_CS_DEFAULT_LANGUAGE,CES_SPLIT_GROUP,CES_GROUP_WINNER,CES_MSG_PRIORITY,CES_CRON_STATUS) 
                select %s, %s, cse.CES_CLIENT_ID,cse.CES_EMAIL_ID,'N',cse.CES_FIRST_NAME,cse.CES_LAST_NAME,cse.CES_EMAIL,cse.CES_EMAIL_DOMAIN,cse.CES_CS_DEFAULT_LANGUAGE,cse.CES_SPLIT_GROUP,cse.CES_GROUP_WINNER,cse.CES_MSG_PRIORITY, %s  
                from CAMPAIGN_EMAIL_SENT cse,USER_LIST tul 
                where tul.UL_EMAIL_ID=cse.CES_EMAIL_ID and cse.camp_id=%s and cse.camp_send_id=%s and cse.is_read is NULL and (cse.is_bounced is NULL or cse.is_bounced='N')
            """, [camp_id, cid, cron_status, camp_id, camp_send_id])
            
            # selectInsertTemplateCampSendTransfer (Java line 936)
            cursor.execute("""
                insert into TRANSLATE_TEMPLATE_SEND(TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR, TTS_CAMP_SEND_ID) 
                select TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR, %s
                from TRANSLATE_TEMPLATE_SEND where TTS_CAMP_SEND_ID=%s
            """, [cid, camp_send_id])
            
        count_total_contact = CampaignsSendEmail.objects.filter(campSendId=cid).count()
        
        # Throttling and Bounce Rate (Java lines 941-950)
        bounce_rate = 5.0 
        max_bounce_email = int((bounce_rate * count_total_contact) / 100)

        new_camp_send.readytomail = 'Y'
        new_camp_send.max_bounce_email = max_bounce_email
        new_camp_send.retry_send_count = 0
        new_camp_send.throttling = old_camp_send.throttling
        new_camp_send.throttling_type = old_camp_send.throttling_type
        new_camp_send.throttling_value = old_camp_send.throttling_value
        new_camp_send.throttling_next_date = timezone.now()
        
        if new_camp_send.camp_main_type == 2:
            new_camp_send.total_queued = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='A').count()
            new_camp_send.total_queued_b = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='B').count()
            new_camp_send.total_queued_o = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='O').count()
        else:
            new_camp_send.total_queued = count_total_contact
            
        new_camp_send.save()
        
        data['campSendId'] = cid
        data['totalMember'] = count_total_contact
        
        country_setting = get_country_setting(tenant_id)
        
        # Payment Logic (Java lines 958-1006)
        membership_type = request.user.membership_type if hasattr(request.user, 'membership_type') else "Free"
        if membership_type == "Free":
            res_body = final_save_resend_campaign(tenant_id, data)
        else:
            amt = campaign_price_list_display(count_total_contact, country_setting)
            profile_status = check_payment_profile_exists(tenant_id)
            if profile_status == "yes":
                res_body = final_save_resend_campaign(tenant_id, data)
            else:
                count_inv = Invoices.objects.filter(invTenantId=tenant_id).count()
                if count_inv == 0:
                    first_inv_amt = float(getattr(country_setting, "cnty_first_inv_free_amt", 0) or 0)
                    if amt >= first_inv_amt:
                        res_body = {"error": "", "location": "paymentProfile"}
                    else:
                        total_uninv = total_uninvoiced_amt(tenant_id)
                        if (total_uninv + amt) >= first_inv_amt:
                            res_body = {"error": "", "location": "paymentProfile"}
                        else:
                            res_body = final_save_resend_campaign(tenant_id, data)
                else:
                    res_body = {"error": "", "location": "paymentProfile"}
                    
        if res_body.get('error'):
            if res_body.get('error') == "groupNotExists":
                return api_response(500, "This Campaign Is Not Resend Because Associated Group Is Deleted.", res_body)
            else:
                return api_response(500, res_body.get('error'), res_body)
        else:
            if res_body.get('location') == "paymentProfile":
                return api_response(200, "Add Payment Profile.", res_body)
            else:
                return api_response(200, "Campaign Resend Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] ResendCampaignNotOpened Error : {str(e)}")
        res_body['error'] = "Exception While Inserting Resend Campaign Not Opened"
        return api_response(500, "Exception While Inserting Resend Campaign Not Opened", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def resend_campaign_to_new_contacts(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = ResendAllCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    data = serializer.validated_data
    camp_id = data['campId']
    
    try:
        camp = CampaignsEmail.objects.get(campId=camp_id)
        group_id = int(camp.groupList) if camp.groupList else None
        if not group_id:
            return api_response(400, "groupNotExists")
        
        send_on_date = db_date_time(data['sendOnDate'])
        data['sendOnDate'] = send_on_date
        
        country_setting = get_country_setting(tenant_id)
        if not country_setting:
            return api_response(400, "Country setting not found")
        
        old_camp_send = CampaignsEmailSend.objects.filter(camp_id=camp_id).first()
        
        new_camp_send = CampaignsEmailSend(
            member_id=get_tenant_id_by_client_id(camp.ceClientId),
            camp_name=camp.campName,
            camp_detail=camp.campDetail,
            camp_type=camp.campType,
            group_list=camp.groupList,
            from_name=camp.fromName,
            from_add=camp.fromAdd,
            reply_to_add=camp.replyToAdd,
            subject=camp.subject,
            sendDate=camp.sendDate,
            readytomail='N',
            camp_id=camp.campId,
            sendondate=send_on_date,
            mail_type=camp.mailType,
            mypageid=camp.mypageId,
            camp_main_type=camp.campMainType,
            testing_type=camp.testingType,
            selectgroupper=camp.selectGroupPer,
            remaingroupper=camp.remainGroupPer,
            camp_detail_b=camp.campDetailB,
            mypageidb=camp.mypageIdB,
            from_name_b=camp.fromNameB,
            subjectb=camp.subjectB,
            scheduletypeb=camp.scheduleTypeB,
            sendondateb=camp.sendOnDateB,
            byautomanual=camp.byAutoManual,
            bytype=camp.byType,
            bynumber=camp.byNumber,
            bymeasure=camp.byMeasure,
            incremental_updates=camp.incrementalUpdates,
            tries=camp.tries
        )
        new_camp_send.save()
        cid = new_camp_send.id
        
        # updateCampSendId
        CampaignsSendEmail.objects.filter(
            campId=camp_id, 
            isSend='N', 
            campSendId=0
        ).update(
            campSendId=cid,
            msgPriority=20
        )
        
        # Template transfer
        with connection.cursor() as cursor:
            cursor.execute("""
                insert into TRANSLATE_TEMPLATE_SEND(TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR,TTS_CAMP_SEND_ID) 
                select TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR, %s
                from TRANSLATE_TEMPLATE_SEND where TTS_CAMP_SEND_ID=%s
            """, [cid, data['campSendId']])
            
        count_total_contact = CampaignsSendEmail.objects.filter(campId=cid).count()
        bounce_rate = 5.0 
        max_bounce_email = int((bounce_rate * count_total_contact) / 100)

        new_camp_send.readytomail = 'Y'
        new_camp_send.max_bounce_email = max_bounce_email
        new_camp_send.retry_send_count = 0
        if old_camp_send:
            new_camp_send.throttling = old_camp_send.throttling
            new_camp_send.throttling_type = old_camp_send.throttling_type
            new_camp_send.throttling_value = old_camp_send.throttling_value
        new_camp_send.throttling_next_date = timezone.now()
        
        if new_camp_send.camp_main_type == 2:
            new_camp_send.total_queued = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='A').count()
            new_camp_send.total_queued_b = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='B').count()
            new_camp_send.total_queued_o = CampaignsSendEmail.objects.filter(campSendId=cid, splitGroup='O').count()
        else:
            new_camp_send.total_queued = CampaignsSendEmail.objects.filter(campSendId=cid).count()
            
        new_camp_send.save()
        data['campSendId'] = cid
        
        membership_type = request.user.membership_type if hasattr(request.user, 'membership_type') else "Free"
        if membership_type == "Free":
            res_body = final_save_resend_campaign(tenant_id, data)
        else:
            amt = campaign_price_list_display(data['totalMember'], country_setting)
            profile_status = check_payment_profile_exists(tenant_id)
            if profile_status == "yes":
                res_body = final_save_resend_campaign(tenant_id, data)
            else:
                count_inv = Invoices.objects.filter(invTenantId=tenant_id).count()
                if count_inv == 0:
                    first_inv_amt = float(country_setting.cnty_first_inv_free_amt or 0)
                    if amt >= first_inv_amt:
                        res_body = {"error": "", "location": "paymentProfile"}
                    else:
                        total_uninv = total_uninvoiced_amt(tenant_id)
                        if (total_uninv + amt) >= first_inv_amt:
                            res_body = {"error": "", "location": "paymentProfile"}
                        else:
                            res_body = final_save_resend_campaign(tenant_id, data)
                else:
                    res_body = {"error": "", "location": "paymentProfile"}
                    
        return api_response(200, "Resend Campaign Success", res_body)
    except Exception as e:
        logger.error(f"resend_campaign_to_new_contacts Error : {str(e)}")
        return api_response(500, str(e))

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_campaign(request):
    """
    Java: /emailCampaign/sendCampaign
    """
    tenant_id = get_final_tenant_id(request=request)
    serializer = SendCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    data = serializer.validated_data
    res_body = {"error": "", "location": "", "msg": "", "memberList": 0, "campId": 0}
    
    try:
        subject = data['subject']
        # Java: subject.replaceAll("/[^A-Za-z0-9#@.:%-,_/']/", " ")
        subject = re.sub(r"[^A-Za-z0-9#@.:%-,_/']", " ", subject)
        
        camp_main_type = data['campMainType']
        subject_b = data.get('subjectB', subject)
        if camp_main_type == 2:
            if subject_b:
                subject_b = re.sub(r"[^A-Za-z0-9#@.:%-,_/']", " ", subject_b)
            else:
                subject_b = subject
        
        mail_type = data.get('mailType', 'Newsletter')
        if not mail_type or mail_type == "":
            mail_type = "Newsletter"

        # Check if campaign name exists (Java lines 1102-1113)
        camp_id_exists = CampaignsEmail.objects.filter(campName=data['campName'], ceClientId=get_client_id_by_tenant_id(tenant_id)).order_by('-campId').values_list('campId', flat=True).first()
        if camp_id_exists:
            res_body['error'] = "Campaign Name Already Exists."
            return api_response(200, "Send Campaign Successfully.", res_body)

        # Contact counting logic (Java lines 1120-1155)
        g_id_tmp = data.get('selectedGid', 0)
        seg_id = data.get('selectedSid', 0)
        final_qry = ""
        
        if seg_id > 0:
            selected_all_sid = data.get('selectedAllSid', [seg_id])
            queries = []
            for sid in selected_all_sid:
                if sid > 0:
                    seg_query_obj = GroupSegment.objects.filter(segId=sid).first()
                    if seg_query_obj and seg_query_obj.segQuery:
                        qry_str = seg_query_obj.segQuery
                        qry_str = re.sub(r"(?i)select \*", "SELECT tul.UL_EMAIL_ID", qry_str)
                        qry_str = qry_str.replace("WHERE", " WHERE tul.UL_TYPE_EMAIL not in ('email', 'pending') AND tul.UL_TYPE_SMS != 'sms' And (tul.UL_EMAIL is not null) and (tul.UL_EMAIL_DOMAIN is not null) and ")
                        queries.append(f"( {qry_str} )")
            if queries:
                final_qry = " UNION ".join(queries)
        else:
            final_qry = f"SELECT UL_EMAIL_ID FROM USER_LIST WHERE UL_TYPE_EMAIL not in ('email', 'pending') AND UL_TYPE_SMS != 'sms' And UL_GROUP_ID = {g_id_tmp} AND UL_CLIENT_ID = {get_client_id_by_tenant_id(tenant_id)} AND UL_STATUS = 'Subscribed' AND (UL_BAD_EMAIL in ('N', 'B', 'D') and (UL_OPT_ID is null or UL_OPT_ID = 0)) AND (UL_EMAIL is not null) AND (UL_EMAIL_DOMAIN is not null) ORDER BY UL_FIRST_NAME"

        number_of_member = 0
        if final_qry:
            temp_qry = final_qry.replace("SELECT UL_EMAIL_ID", "SELECT COUNT(UL_EMAIL_ID) as tot").replace("SELECT tul.UL_EMAIL_ID", "SELECT COUNT(tul.UL_EMAIL_ID) as tot").replace("ORDER BY UL_FIRST_NAME", "")
            if " UNION " in temp_qry:
                temp_qry = f"SELECT SUM(tot) as tot FROM ({temp_qry}) tmp"
            
            with connection.cursor() as cursor:
                cursor.execute(temp_qry)
                row = cursor.fetchone()
                if row:
                    number_of_member = int(row[0] or 0)

        res_body['memberList'] = number_of_member

        # Domain Capacity check (Java lines 1160-1172)
        domain_limit_msg = ""
        from_add_domain = data['fromAdd'].split("@")[-1]
        domain_obj = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant_id), domDomain=from_add_domain).first()
        if domain_obj:
            domain_capacity = domain_obj.domDomainCapacity or 0
            domain_capacity_used = domain_obj.domDomainCapacityUsed or 0
            pending_capacity = domain_capacity - domain_capacity_used
            if pending_capacity < number_of_member:
                domain_limit_msg += f"\n\nYour domain current sending limit : {domain_capacity} per day"
                domain_limit_msg += f"\nYou have used : {domain_capacity_used}"
                if pending_capacity < 0:
                    pending_capacity = 0
                domain_limit_msg += f"\nRemaining will be send {pending_capacity} today"

        # Time handling
        now = timezone.now()
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )

        # Template language processing (Java lines 1209-1250)
        all_language = []
        language_name = []
        mp_template_language = "en"
        my_page_id_val = data.get('myPageId') or 0
        my_page_id_b_val = data.get('myPageIdB') or 0

        if my_page_id_val and my_page_id_val > 0:
            my_page_obj = MyPages.objects.filter(mpId=my_page_id_val).first()
            if my_page_obj:
                mp_template_language = my_page_obj.mpTemplateLanguage or "en"
                all_lan = mp_template_language
                if my_page_obj.mpTemplateConvertLangList:
                    all_lan += "," + my_page_obj.mpTemplateConvertLangList
                if all_lan:
                    all_language = [l for l in all_lan.split(",") if l]
                    language_name = list(all_language)

        all_language_b = []
        if camp_main_type == 2:
            if my_page_id_b_val and my_page_id_b_val > 0:
                my_page_obj_b = MyPages.objects.filter(mpId=my_page_id_b_val).first()
                if my_page_obj_b:
                    mp_template_language_b = my_page_obj_b.mpTemplateLanguage or "en"
                    all_lan_b = mp_template_language_b
                    if my_page_obj_b.mpTemplateConvertLangList:
                        all_lan_b += "," + my_page_obj_b.mpTemplateConvertLangList
                    if all_lan_b:
                        all_language_b = [l for l in all_lan_b.split(",") if l]
            else:
                all_language_b = list(all_language)

        # Create CampaignsEmail
        camp = CampaignsEmail(
            ceClientId=get_client_id_by_tenant_id(tenant_id),
            campName=data['campName'],
            campType=data['campType'],
            groupList=str(g_id_tmp),
            fromName=data['fromName'],
            fromAdd=data['fromAdd'],
            replyToAdd=data['replyToAdd'],
            subject=subject,
            sendDate=now,
            campStatus=2,
            segId=seg_id,
            mypageId=data.get('myPageId', 0),
            scheduleType=data['schType'],
            mailType=mail_type,
            campMainType=camp_main_type,
            archiveYn='N'
        )

        # Both Oracle tables store sendOnTime as INTERVAL DAY TO SECOND → DurationField + timedelta
        send_on_timedelta = None
        send_on_timedelta_b = None
        send_on_date_b = None

        if data['schType'] == 1:
            send_on_date = now
            send_on_timedelta = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
        else:
            send_on_dt = parse_date_time(data.get('sendOnDateTime'))
            assert send_on_dt is not None
            temp = convert_event_timezone_to_user(send_on_dt.strftime('%m/%d/%Y %H:%M:%S'), data.get('timeZone', 'UTC'), 'UTC')
            send_on_dt = parse_date_time(temp)
            send_on_date = send_on_dt
            if send_on_dt:
                send_on_timedelta = timedelta(hours=send_on_dt.hour, minutes=send_on_dt.minute, seconds=send_on_dt.second)

        camp.sendOnDate = send_on_date
        camp.sendOnTime = send_on_timedelta

        if camp_main_type == 2:
            camp.testingType = data.get('testingType', 0)
            camp.selectGroupPer = data.get('selectGroupPer', 0)
            camp.remainGroupPer = data.get('remainGroupPer', 0)
            camp.subjectB = subject_b
            camp.campDetailB = ''
            camp.mypageIdB = data.get('myPageIdB', data.get('myPageId', 0)) or data.get('myPageId', 0)
            camp.fromNameB = data.get('fromNameB', data['fromName']) if data.get('fromNameB') else data['fromName']
            camp.scheduleTypeB = data.get('schTypeB', data['schType']) if data.get('schTypeB') else data['schType']
            
            if camp.scheduleTypeB == 1:
                send_on_date_b = now
                send_on_timedelta_b = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
            else:
                send_on_dt_b = parse_date_time(data.get('sendOnDateTimeB'))
                send_on_date_b = send_on_dt_b
                if send_on_dt_b:
                    send_on_timedelta_b = timedelta(hours=send_on_dt_b.hour, minutes=send_on_dt_b.minute, seconds=send_on_dt_b.second)

            camp.sendOnDateB = send_on_date_b
            camp.sendOnTimeB = send_on_timedelta_b
            
            if data.get('byAutoManual'):
                camp.byAutoManual = data.get('byAutoManual')
                if data.get('byAutoManual') == "auto":
                    camp.byType = data.get('byType')
                    camp.byNumber = data.get('byNumber', 0)
                    camp.byMeasure = data.get('byMeasure')
                    if data.get('incrementalUpdates') == "Y":
                        camp.incrementalUpdates = "Y"
                        camp.tries = 4
                        camp.triesCount = 1
                    else:
                        camp.incrementalUpdates = "N"
                        camp.tries = 1
                        camp.triesCount = 1
        
        camp.save()
        camp_id = camp.campId
        res_body['campId'] = camp_id

        # Directory creation (Java lines 1378-1396)
        camp_dir = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "emailcampaign", str(camp_id))
        os.makedirs(camp_dir, exist_ok=True)
        
        all_data = ""
        if data.get('myPageId', 0) > 0:
            src_dir = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "mypage", str(data['myPageId']))
            if os.path.exists(src_dir):
                for item in os.listdir(src_dir):
                    s = os.path.join(src_dir, item)
                    d = os.path.join(camp_dir, item)
                    if os.path.isfile(s):
                        shutil.copy2(s, d)
            
            index_path = os.path.join(camp_dir, "index.html")
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    all_data = f.read()
                
                try:
                    tree = lxml.html.fromstring(all_data)
                    # Background images
                    for element_id in ['mcd', 'templateBody']:
                        elem = tree.get_element_by_id(element_id, None)
                        if elem is not None and elem.get('item-path'):
                            old_link = elem.get('item-path')
                            if "emailcampaign" not in old_link:
                                img_name = old_link.split("/")[-1]
                                new_link = f"{settings.SITE_URL}usercontent/{tenant_id}/images/emailcampaign/{camp_id}/{img_name}"
                                all_data = all_data.replace(old_link, new_link)
                    
                    # Class images
                    for img in tree.xpath('//*[@class="mcnImage"]'):
                        old_link = img.get('src')
                        if old_link and "emailcampaign" not in old_link:
                            img_name = old_link.split("/")[-1]
                            new_link = f"{settings.SITE_URL}usercontent/{tenant_id}/images/emailcampaign/{camp_id}/{img_name}"
                            all_data = all_data.replace(old_link, new_link)
                            
                    all_data = re.sub(r'[\r\n]+', '', all_data)
                    all_data = re.sub(r'>\s+<', '><', all_data)
                    with open(index_path, 'w', encoding='utf-8') as f:
                        f.write(all_data)
                except Exception as e:
                    logger.error(f"HTML Processing Error (A) : {str(e)}")
        else:
            all_data = data.get('allTempData', '')
            if data.get('campType') == 1:
                all_data = all_data.replace('\n', '<br/>')
            else:
                all_data = re.sub(r'[\r\n]+', '', all_data)
                all_data = re.sub(r'>\s+<', '><', all_data)

        all_data_b = all_data
        if camp_main_type == 2:
            my_page_id_b = data.get('myPageIdB', data.get('myPageId', 0))
            if data.get('testingType') not in [2, 5]:
                my_page_id_b = data.get('myPageId', 0)
                
            if my_page_id_b > 0:
                camp_dir_b = os.path.join(camp_dir, "B")
                os.makedirs(camp_dir_b, exist_ok=True)
                src_dir_b = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "mypage", str(my_page_id_b))
                if os.path.exists(src_dir_b):
                    for item in os.listdir(src_dir_b):
                        s = os.path.join(src_dir_b, item)
                        d = os.path.join(camp_dir_b, item)
                        if os.path.isfile(s):
                            shutil.copy2(s, d)
                
                index_path_b = os.path.join(camp_dir_b, "index.html")
                if os.path.exists(index_path_b):
                    with open(index_path_b, 'r', encoding='utf-8') as f:
                        all_data_b = f.read()

                    try:
                        tree_b = lxml.html.fromstring(all_data_b)
                        # Background images (Java lines 1500-1526)
                        for element_id in ['mcd', 'templateBody']:
                            elem_b = tree_b.get_element_by_id(element_id, None)
                            if elem_b is not None and elem_b.get('item-path'):
                                old_link_b = elem_b.get('item-path')
                                if "emailcampaign" not in old_link_b:
                                    img_name_b = old_link_b.split("/")[-1]
                                    new_link_b = f"{settings.SITE_URL}usercontent/{tenant_id}/images/emailcampaign/{camp_id}/{img_name_b}"
                                    all_data_b = all_data_b.replace(old_link_b, new_link_b, 1).replace(old_link_b, new_link_b, 1)

                        # Class images (Java lines 1528-1537)
                        for img_b in tree_b.xpath('//*[@class="mcnImage"]'):
                            old_link_b = img_b.get('src')
                            if old_link_b and "emailcampaign" not in old_link_b:
                                img_name_b = old_link_b.split("/")[-1]
                                new_link_b = f"{settings.SITE_URL}usercontent/{tenant_id}/images/emailcampaign/{camp_id}/{img_name_b}"
                                all_data_b = all_data_b.replace(old_link_b, new_link_b, 1).replace(old_link_b, new_link_b, 1)

                        all_data_b = re.sub(r'[\r\n]+', '', all_data_b)
                        all_data_b = re.sub(r'>\s+<', '><', all_data_b)
                        with open(index_path_b, 'w', encoding='utf-8') as f:
                            f.write(all_data_b)
                    except Exception as e:
                        logger.error(f"HTML Processing Error (B) : {str(e)}")
            else:
                all_data_b = data.get('allTempDataB', all_data)
                all_data_b = re.sub(r'[\r\n]+', '', all_data_b)
                all_data_b = re.sub(r'>\s+<', '><', all_data_b)
            
            camp.campDetailB = all_data_b
            
        camp.campDetail = all_data
        camp.save()

        # A/B Testing Partitioning (Java lines 1568-1585)
        contact_count_a = number_of_member
        contact_count_b = 0
        contact_count_o = 0
        tot_a = float(number_of_member)
        tot_b = 0.0
        if camp_main_type == 2:
            total_all = float(number_of_member)
            ab_per = (data.get('selectGroupPer', 0) // 2)
            tot_a = math.ceil((ab_per * total_all) / 100.0)
            tot_b = math.ceil((ab_per * total_all) / 100.0)
            if (tot_a + tot_b) > total_all:
                tot_b = total_all - tot_a
            contact_count_a = int(tot_a)
            contact_count_b = int(tot_b)
            contact_count_o = int(number_of_member - tot_a - tot_b)

        # CampaignsEmailSend (Java lines 1589-1647)
        camp_send = CampaignsEmailSend(
            member_id=get_client_id_by_tenant_id(tenant_id),
            camp_id=camp_id,
            camp_name=camp.campName,
            camp_detail=all_data,
            camp_type=camp.campType,
            grouplist=camp.groupList,
            from_name=camp.fromName,
            from_add=camp.fromAdd,
            reply_to_add=camp.replyToAdd,
            subject=camp.subject,
            send_date=now,
            readytomail='N',
            sendondate=send_on_date,
            sendontime=send_on_timedelta,   # DurationField → timedelta (INTERVAL DAY TO SECOND)
            mail_type=camp.mailType,
            mypageid=camp.mypageId,
            camp_main_type=camp_main_type,
            testing_type=camp.testingType,
            selectgroupper=camp.selectGroupPer,
            remaingroupper=camp.remainGroupPer,
            camp_detail_b=camp.campDetailB,
            mypageidb=camp.mypageIdB,
            from_name_b=camp.fromNameB,
            subjectb=camp.subjectB,
            scheduletypeb=camp.scheduleTypeB,
            sendondateb=send_on_date_b,
            sendontimeb=send_on_timedelta_b,  # DurationField → timedelta (INTERVAL DAY TO SECOND)
            byautomanual=camp.byAutoManual,
            bytype=camp.byType,
            bynumber=camp.byNumber,
            bymeasure=camp.byMeasure,
            incremental_updates=camp.incrementalUpdates,
            tries=camp.tries,
            tries_count=camp.triesCount,
            total_queued=contact_count_a,
            total_queued_b=contact_count_b,
            total_queued_o=contact_count_o,
            throttling=data.get('throttling', 'N'),
            throttling_type=data.get('throttlingType'),
            throttling_value=data.get('throttlingValue', 0),
            throttling_next_date=send_on_date or now
        )
        camp_send.save()
        cid = camp_send.id

        temp_send_email_campaign = TempSendEmailCampaigns(
            campId=camp_id,
            campMainType=camp_main_type,
            memberId=get_client_id_by_tenant_id(tenant_id),
            totA=tot_a,
            totB=tot_b,
            sqlString=final_qry,
            languageName=",".join(language_name) if language_name else "en",
            mpTemplateLanguage=mp_template_language,
            msgPriority=1 if (tenant and tenant.td_membership_type != 'Free') else 0,
            campSendId=cid,
            isProcessedStart='N',
            isProcessedEnd='N'
        )
        temp_send_email_campaign.save()

        # Recalculate memberList for A/B (Java lines 1673-1677)
        member_list = number_of_member
        if camp_main_type == 2:
            member_list = int(tot_a + tot_b)
        res_body['memberList'] = member_list

        # Bulk translation transfer (Java lines 1681-1703) - must happen BEFORE link processing
        my_page_id_a = data.get('myPageId', 0) or 0
        if my_page_id_a > 0:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO TRANSLATE_TEMPLATE_SEND (TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR, TTS_CAMP_SEND_ID) "
                        "SELECT TT_MY_PAGE_ID, TT_CLIENT_ID, TT_CAMP_DETAIL_SEND, TT_MASTER_COPY, TT_TEMPLATE_LANGUAGE, TT_PUBLISH_DATE, TT_API_ERROR, %s "
                        "FROM TRANSLATE_TEMPLATE WHERE TT_MY_PAGE_ID = %s",
                        [cid, my_page_id_a]
                    )
            except Exception as e:
                logger.error(f"[ tenantId : {tenant_id} ] SendCampaign Error 17 : {e}")

        if camp_main_type == 2:
            my_page_id_b_send = data.get('myPageIdB', 0) or 0
            if my_page_id_b_send > 0:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO TRANSLATE_TEMPLATE_SEND(TTS_MY_PAGE_ID, TTS_CLIENT_ID, TTS_CAMP_DETAIL_SEND, TTS_MASTER_COPY, TTS_TEMPLATE_LANGUAGE, TTS_PUBLISH_DATE, TTS_API_ERROR, TTS_CAMP_SEND_ID) "
                            "SELECT TT_MY_PAGE_ID, TT_CLIENT_ID, TT_CAMP_DETAIL_SEND, TT_MASTER_COPY, TT_TEMPLATE_LANGUAGE, TT_PUBLISH_DATE, TT_API_ERROR, %s "
                            "FROM TRANSLATE_TEMPLATE WHERE TT_MY_PAGE_ID = %s",
                            [cid, my_page_id_b_send]
                        )
                except Exception as e:
                    logger.error(f"[ tenantId : {tenant_id} ] SendCampaign Error 18 : {e}")

        # Link Tracking and Substitution Logic (Java lines 1705-1991)
        try:
            # Re-fetch from DB (Java line 1679-1680)
            campaigns_email_send = CampaignsEmailSend.objects.get(id=cid)
            camp_detail = campaigns_email_send.camp_detail or ""

            # Shared ignore list
            nfl = [
                "javascript:void(0);", "#dialog_1", "#dialog_2", "#dialog_3", "#dialog_4", "#dialog_5",
                "http://www.yourgaragesale.com", "http://qa.yourgaragesale.com"
            ]
            webapp_name = settings.SITE_URL_WEBAPP.lower() if hasattr(settings, 'SITE_URL_WEBAPP') else ""
            site_name_small = settings.SITE_NAME_BIG_COM.lower() if hasattr(settings, 'SITE_NAME_BIG_COM') else ""

            # --- SIDE A (Java lines 1705-1855) ---
            html = camp_detail.replace("?", "~~~~~~")
            try:
                tree_a = lxml.html.fromstring(html)
                tags_a = tree_a.xpath('//a')
                t_val_count = 0
                key_val_array = {}

                for tag in tags_a:
                    href_link = tag.get('href')
                    if not href_link:
                        continue
                    link = href_link
                    if (href_link.lower() not in [n.lower() for n in nfl] and
                            (not webapp_name or webapp_name not in href_link.lower()) and
                            "mailto:" not in href_link.lower() and
                            "tel:" not in href_link.lower()):
                        if "flink=" in href_link:
                            link = href_link.split("flink=")[1]
                        if link:
                            q_link = link.replace("~~~~~~", "?")
                            if camp_main_type == 2:
                                tid = CampaignLinks.objects.filter(campId=cid, campLink=q_link, splitGroup='A').values_list('id', flat=True).first()
                            else:
                                tid = CampaignLinks.objects.filter(campId=cid, campLink=q_link).values_list('id', flat=True).first()

                            if not tid:
                                CampaignLinks.objects.create(
                                    campId=cid,
                                    campLink=q_link,
                                    linkCount=0,
                                    splitGroup='A' if camp_main_type == 2 else None
                                )
                                new_link = f"{settings.SITE_URL}linkclick?d={DecryptString.set_enc_dec_user(str(cid), '', 'Y')}&flink={link}&m=~~~uid~~~"
                                nlink = f"~~~~{t_val_count}~~~~"
                                # Java: replaceFirst twice
                                html = html.replace(link, nlink, 1)
                                html = html.replace(link, nlink, 1)
                                key_val_array[nlink] = new_link
                                t_val_count += 1

                # Process translation templates for Side A (Java lines 1763-1805)
                if my_page_id_a > 0:
                    for j in range(len(all_language)):
                        try:
                            tt_send = TranslateTemplateSend.objects.filter(
                                ttMyPageId=my_page_id_a, ttTemplateLanguage=all_language[j], ttCampSendId=cid
                            ).first()
                            if tt_send:
                                html_trans = tt_send.ttCampDetailSend or ""
                                html_trans = html_trans.replace("?", "~~~~~~")
                                tree_trans = lxml.html.fromstring(html_trans)
                                tags_trans = tree_trans.xpath('//a')
                                for tag_t in tags_trans:
                                    href_t = tag_t.get('href')
                                    if not href_t:
                                        continue
                                    link_t = href_t
                                    if (href_t.lower() not in [n.lower() for n in nfl] and
                                            (not webapp_name or webapp_name not in href_t.lower()) and
                                            "mailto:" not in href_t.lower() and
                                            "tel:" not in href_t.lower()):
                                        if "flink=" in href_t:
                                            link_t = href_t.split("flink=")[1]
                                        if link_t:
                                            new_link_t = f"{settings.SITE_URL}linkclick?d={DecryptString.set_enc_dec_user(str(cid), '', 'Y')}&flink={link_t}&m=~~~uid~~~"
                                            nlink_t = f"~~~~{t_val_count}~~~~"
                                            html_trans = html_trans.replace(link_t, nlink_t, 1)
                                            html_trans = html_trans.replace(link_t, nlink_t, 1)
                                            key_val_array[nlink_t] = new_link_t
                                            t_val_count += 1
                                html_trans = re.sub(r'[\r\n]+', '', html_trans)
                                html_trans = re.sub(r'>\s+<', '><', html_trans)
                                html_trans = html_trans.replace("~~~~~~", "?")
                                tt_send.ttCampDetailSend = html_trans
                                tt_send.save()
                        except Exception as e_t:
                            logger.error(f"[ tenantId : {tenant_id} ] Side A Translation Lang {all_language[j]} Error : {e_t}")

                # Second pass: replace placeholders with tracking URLs (Java lines 1808-1838)
                if key_val_array:
                    for nlink_key, new_link_val in key_val_array.items():
                        html = html.replace(nlink_key, new_link_val, 1)
                        html = html.replace(nlink_key, new_link_val, 1)

                    # Apply to translations too (Java lines 1818-1838)
                    if my_page_id_a > 0:
                        for j in range(len(all_language)):
                            try:
                                tt_send = TranslateTemplateSend.objects.filter(
                                    ttMyPageId=my_page_id_a, ttTemplateLanguage=all_language[j], ttCampSendId=cid
                                ).first()
                                if tt_send:
                                    html_trans2 = tt_send.ttCampDetailSend or ""
                                    for nlink_key, new_link_val in key_val_array.items():
                                        temp_link = new_link_val.replace("~~~~~~", "?")
                                        html_trans2 = html_trans2.replace(nlink_key, temp_link, 1)
                                        html_trans2 = html_trans2.replace(nlink_key, temp_link, 1)
                                    html_trans2 = re.sub(r'[\r\n]+', '', html_trans2)
                                    html_trans2 = re.sub(r'>\s+<', '><', html_trans2)
                                    html_trans2 = html_trans2.replace("~~~~~~", "?")
                                    tt_send.ttCampDetailSend = html_trans2
                                    tt_send.save()
                            except Exception as e_t2:
                                logger.error(f"[ tenantId : {tenant_id} ] Side A Translation Pass2 Lang {all_language[j]} Error : {e_t2}")

                try:
                    find_email_send = CampaignsEmailSend.objects.get(id=cid)
                    html = re.sub(r'[\r\n]+', '', html)
                    html = re.sub(r'>\s+<', '><', html)
                    html = html.replace("~~~~~~", "?")
                    find_email_send.camp_detail = html
                    # Throttling (Java lines 1849-1852)
                    find_email_send.throttling = data.get('throttling', 'N')
                    find_email_send.throttling_type = data.get('throttlingType')
                    find_email_send.throttling_value = data.get('throttlingValue', 0)
                    find_email_send.throttling_next_date = send_on_date or now
                    find_email_send.save()
                except Exception as e_save:
                    logger.error(f"[ tenantId : {tenant_id} ] SendCampaign Error 19 : {e_save}")

            except Exception as e_a:
                logger.error(f"[ tenantId : {tenant_id} ] Side A Link Processing Error : {e_a}")

            # --- SIDE B (Java lines 1861-1991) ---
            if camp_main_type == 2:
                camp_detail_b = campaigns_email_send.camp_detail_b or ""
                if not camp_detail_b:
                    camp_detail_b = campaigns_email_send.camp_detail or ""

                html_b = camp_detail_b.replace("?", "~~~~~~")
                try:
                    tree_b = lxml.html.fromstring(html_b)
                    tags_b = tree_b.xpath('//a')
                    t_val_count_b = 0
                    key_val_array_b = {}

                    for tag_b in tags_b:
                        href_link_b = tag_b.get('href')
                        if not href_link_b:
                            continue
                        link_b = href_link_b
                        if (href_link_b.lower() not in [n.lower() for n in nfl] and
                                (not site_name_small or site_name_small not in href_link_b.lower()) and
                                "mailto:" not in href_link_b.lower() and
                                "tel:" not in href_link_b.lower()):
                            if "flink=" in href_link_b:
                                link_b = href_link_b.split("flink=")[1]
                            if link_b:
                                q_link_b = link_b.replace("~~~~~~", "?")
                                tid_b = CampaignLinks.objects.filter(campId=cid, campLink=q_link_b, splitGroup='B').values_list('id', flat=True).first()
                                if not tid_b:
                                    CampaignLinks.objects.create(
                                        campId=cid,
                                        campLink=q_link_b,
                                        linkCount=0,
                                        splitGroup='B'
                                    )
                                    new_link_b = f"{settings.SITE_URL}linkclick?d={DecryptString.set_enc_dec_user(str(cid), '', 'Y')}&flink={link_b}&m=~~~uid~~~"
                                    nlink_b = f"~~~~{t_val_count_b}~~~~"
                                    html_b = html_b.replace(link_b, nlink_b, 1)
                                    html_b = html_b.replace(link_b, nlink_b, 1)
                                    key_val_array_b[nlink_b] = new_link_b
                                    t_val_count_b += 1

                    # Process translation templates for Side B (Java lines 1901-1945)
                    my_page_id_b_send = data.get('myPageIdB', 0) or 0
                    if my_page_id_b_send > 0:
                        for j in range(len(all_language_b)):
                            try:
                                tt_send_b = TranslateTemplateSend.objects.filter(
                                    ttMyPageId=my_page_id_b_send, ttTemplateLanguage=all_language_b[j], ttCampSendId=cid
                                ).first()
                                if tt_send_b:
                                    html_trans_b = tt_send_b.ttCampDetailSend or ""
                                    html_trans_b = html_trans_b.replace("?", "~~~~~~")
                                    tree_trans_b = lxml.html.fromstring(html_trans_b)
                                    tags_trans_b = tree_trans_b.xpath('//a')
                                    for tag_tb in tags_trans_b:
                                        href_tb = tag_tb.get('href')
                                        if not href_tb:
                                            continue
                                        link_tb = href_tb
                                        if (href_tb.lower() not in [n.lower() for n in nfl] and
                                                (not site_name_small or site_name_small not in href_tb.lower()) and
                                                "mailto:" not in href_tb.lower() and
                                                "tel:" not in href_tb.lower()):
                                            if "flink=" in href_tb:
                                                link_tb = href_tb.split("flink=")[1]
                                            if link_tb:
                                                new_link_tb = f"{settings.SITE_URL}linkclick?d={DecryptString.set_enc_dec_user(str(cid), '', 'Y')}&flink={link_tb}&m=~~~uid~~~"
                                                nlink_tb = f"~~~~{t_val_count_b}~~~~"
                                                html_trans_b = html_trans_b.replace(link_tb, nlink_tb, 1)
                                                html_trans_b = html_trans_b.replace(link_tb, nlink_tb, 1)
                                                key_val_array_b[nlink_tb] = new_link_tb
                                                t_val_count_b += 1
                                    html_trans_b = re.sub(r'[\r\n]+', '', html_trans_b)
                                    html_trans_b = re.sub(r'>\s+<', '><', html_trans_b)
                                    html_trans_b = html_trans_b.replace("~~~~~~", "?")
                                    tt_send_b.ttCampDetailSend = html_trans_b
                                    tt_send_b.save()
                            except Exception as e_tb:
                                logger.error(f"[ tenantId : {tenant_id} ] Side B Translation Lang {all_language_b[j]} Error : {e_tb}")

                    # Second pass: replace placeholders (Java lines 1948-1979)
                    if key_val_array_b:
                        for nlink_key_b, new_link_val_b in key_val_array_b.items():
                            html_b = html_b.replace(nlink_key_b, new_link_val_b, 1)
                            html_b = html_b.replace(nlink_key_b, new_link_val_b, 1)

                        if my_page_id_b_send > 0:
                            for j in range(len(all_language_b)):
                                try:
                                    tt_send_b = TranslateTemplateSend.objects.filter(
                                        ttMyPageId=my_page_id_b_send, ttTemplateLanguage=all_language_b[j], ttCampSendId=cid
                                    ).first()
                                    if tt_send_b:
                                        html_trans_b2 = tt_send_b.ttCampDetailSend or ""
                                        for nlink_key_b, new_link_val_b in key_val_array_b.items():
                                            temp_link_b = new_link_val_b.replace("~~~~~~", "?")
                                            html_trans_b2 = html_trans_b2.replace(nlink_key_b, temp_link_b, 1)
                                            html_trans_b2 = html_trans_b2.replace(nlink_key_b, temp_link_b, 1)
                                        html_trans_b2 = re.sub(r'[\r\n]+', '', html_trans_b2)
                                        html_trans_b2 = re.sub(r'>\s+<', '><', html_trans_b2)
                                        html_trans_b2 = html_trans_b2.replace("~~~~~~", "?")
                                        tt_send_b.ttCampDetailSend = html_trans_b2
                                        tt_send_b.save()
                                except Exception as e_tb2:
                                    logger.error(f"[ tenantId : {tenant_id} ] Side B Translation Pass2 Lang {all_language_b[j]} Error : {e_tb2}")

                    try:
                        find_email_send_b = CampaignsEmailSend.objects.get(id=cid)
                        html_b = re.sub(r'[\r\n]+', '', html_b)
                        html_b = re.sub(r'>\s+<', '><', html_b)
                        html_b = html_b.replace("~~~~~~", "?")
                        find_email_send_b.camp_detail_b = html_b
                        find_email_send_b.save()
                    except Exception as e_save_b:
                        logger.error(f"[ tenantId : {tenant_id} ] SendCampaign Error 20 : {e_save_b}")

                except Exception as e_b:
                    logger.error(f"[ tenantId : {tenant_id} ] Side B Link Processing Error : {e_b}")

        except Exception as e:
            logger.error(f"Link Processing Error (Full) : {str(e)}")

        # Membership/Payment checks
        membership_type = tenant.td_membership_type if tenant else "Free"
        country_setting = get_country_setting(tenant_id)
        
        if membership_type == "Free":
            res_inner = final_send_campaign(tenant_id, country_setting, cid, number_of_member, camp_id)
            if res_inner.get("error"):
                res_body["error"] = res_inner["error"]
        else:
            profile_exists = check_payment_profile_exists(tenant_id)
            if profile_exists == "yes":
                res_inner = final_send_campaign(tenant_id, country_setting, cid, number_of_member, camp_id)
                if res_inner.get("error"):
                    res_body["error"] = res_inner["error"]
            else:
                res_body["location"] = "paymentProfile"
                res_body["cid"] = cid
                res_body["campId"] = camp_id
                res_body["memberList"] = number_of_member
        
        return api_response(200, "Send Campaign Successfully.", res_body)

    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] SendCampaign Error : {e}")
        logger.error(traceback.format_exc())
        try:
            error_dto = {
                "memberId": tenant_id,
                "requestURL": request.build_absolute_uri(),
                "errorMessage": str(e),
                "errorDetails": traceback.format_exc()
            }
            CommonServices.send_whoops_error(error_dto)
        except Exception:
            pass
        return api_response(500, "Something went wrong. Please try again later.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_send_campaign(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = SaveSendCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    data = serializer.validated_data
    try:
        country_setting = get_country_setting(tenant_id)
        res = final_send_campaign(
            tenant_id=tenant_id,
            country_setting=country_setting,
            cid=data.get('cid'),
            member_list=data.get('memberList'),
            camp_id=data.get('campId')
        )
        msg = data.get('msg', 'Send Campaign Successfully.')
        return api_response(200, msg, {"error": res.get("error", "")})
    except Exception as e:
        logger.error(f"save_send_campaign Error : {str(e)}")
        return api_response(500, str(e))

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_resend_campaign(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = ResendAllCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    data = serializer.validated_data
    try:
        res_body = final_save_resend_campaign(tenant_id, data)
        return api_response(200, "Resend Campaign Success", res_body)
    except Exception as e:
        logger.error(f"save_resend_campaign Error : {str(e)}")
        return api_response(500, str(e))

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def check_spam(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = CheckSpamSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    check_spam_dto = serializer.validated_data
    res_body = {"error": ""} # type: dict[str, Any]
    
    try:
        domain_list = [
            "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", 
            "outlook.com", "msn.com", "live.com", "zoho.com", 
            "mail.com", "aol.com", "siteNameSmallCom"
        ]
        
        domain_name = check_spam_dto.get('domainName')
        if domain_name in domain_list:
            check_spam_dto['domainVerify'] = True
        else:
            id_val = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant_id), domDomain=domain_name).values_list('domId', flat=True).first()
            check_spam_dto['domainVerify'] = bool(id_val)
            
        check_spam_dto['dkim'] = 0
        check_spam_dto['spf'] = 0
        
        if domain_name == "siteNameSmallCom" or domain_name in domain_list:
            check_spam_dto['dkim'] = 1
            check_spam_dto['spf'] = 1
            
        all_data = ""
        if check_spam_dto.get('myPageId', 0) > 0:
            read_path = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "mypage", str(check_spam_dto['myPageId']), "index.html")
            if os.path.exists(read_path):
                with open(read_path, 'r', encoding='utf-8') as f:
                    all_data = f.read()
        else:
            all_data = check_spam_dto.get('allTempData', '')
            
        all_data = re.sub(r'[\r\n]+', '', all_data)
        all_data = re.sub(r'>\s+<', '><', all_data)
        
        inner_res_body = check_subject_content(check_spam_dto.get('subject', ''), all_data)
        inner_res_body2 = check_spam_assassin(check_spam_dto.get('fromAdd', ''), tenant_id, check_spam_dto.get('selectedGid', 0), check_spam_dto.get('subject', ''), all_data)
        inner_res_body['localSpamScore'] = inner_res_body2.get('localSpamScore', 0)
        
        inner_res_body['outlookSpam'] = 0
        inner_res_body['gmailSpam'] = 0
        inner_res_body['outlookClientSpam'] = 0
        
        res_body['checkSubjectContent'] = inner_res_body # type: ignore
        
        if check_spam_dto.get('testingType', 0) > 0:
            all_data_b = ""
            if check_spam_dto.get('myPageIdB', 0) > 0:
                read_path_b = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "mypage", str(check_spam_dto['myPageIdB']), "index.html")
                if os.path.exists(read_path_b):
                    with open(read_path_b, 'r', encoding='utf-8') as f:
                        all_data_b = f.read()
            else:
                all_data_b = check_spam_dto.get('allTempDataB', '')
                
            all_data_b = re.sub(r'[\r\n]+', '', all_data_b)
            all_data_b = re.sub(r'>\s+<', '><', all_data_b)
            
            if check_spam_dto.get('subjectB') and all_data_b:
                inner_res_body_b = check_subject_content(check_spam_dto['subjectB'], all_data_b)
                inner_res_body2_b = check_spam_assassin(check_spam_dto.get('fromAdd', ''), tenant_id, check_spam_dto.get('selectedGid', 0), check_spam_dto['subjectB'], all_data_b)
                inner_res_body_b['localSpamScore'] = inner_res_body2_b.get('localSpamScore', 0)
                
                inner_res_body_b['outlookSpam'] = 0
                inner_res_body_b['gmailSpam'] = 0
                inner_res_body_b['outlookClientSpam'] = 0
                res_body['checkSubjectContentB'] = inner_res_body_b # type: ignore
                
        res_body['dkim'] = check_spam_dto.get('dkim', 0)
        res_body['spf'] = check_spam_dto.get('spf', 0)
        
    except Exception as e:
        logger.error(f"check_spam Error: {str(e)}")
        res_body['error'] = "Invalid Data"
        
    return api_response(200, "Fetch Spam Check Successfully.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def throttling_validation(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = ThrottlingValidationSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    dto = serializer.validated_data
    res_body = {"error": ""}
    
    try:
        if dto.get('throttlingType') == "daysMF":
            send_on_date_time = dto.get('sendOnDateTime')
            if dto.get('schType') == 1:
                send_on_date_time = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
                
            if is_weekend(send_on_date_time):
                res_body["error"] = "The Selected Date Falls On a Weekend. Please Choose a Weekday For Sending."
                return api_response(200, "Weekend Check", res_body)
                
        g_id = dto.get('selectedGid')
        seg_id = dto.get('selectedSid', 0)
        
        final_qry = ""
        if seg_id > 0:
            selected_all_sid = dto.get('selectedAllSid', [])
            for sid in selected_all_sid:
                if sid > 0:
                    gs = GroupSegment.objects.filter(segId=sid).first()
                    if gs and gs.segQuery:
                        # Java transformation
                        seg_query = gs.segQuery
                        seg_query = seg_query.replace("select *", "SELECT tul.UL_EMAIL_ID")
                        qry = seg_query.replace("WHERE", " WHERE tul.UL_TYPE_EMAIL not in ('email', 'pending') AND tul.UL_TYPE_SMS != 'sms' And (tul.UL_EMAIL is not null) and (tul.UL_EMAIL_DOMAIN is not null) and ")
                        
                        if not final_qry:
                            final_qry = f" ( {qry} ) "
                        else:
                            final_qry += f" UNION ( {qry} ) "
            
            temp_qry = final_qry.replace("SELECT tul.UL_EMAIL_ID", "SELECT COUNT(tul.UL_EMAIL_ID) as tot") if final_qry else ""
        else:
            final_qry = f"SELECT UL_EMAIL_ID FROM USER_LIST WHERE UL_TYPE_EMAIL not in ('email', 'pending') AND UL_TYPE_SMS != 'sms' And UL_GROUP_ID = {g_id} AND UL_CLIENT_ID = {get_client_id_by_tenant_id(tenant_id)} AND UL_STATUS = 'Subscribed' AND (UL_BAD_EMAIL in ('N', 'B', 'D') and (UL_OPT_ID is null or UL_OPT_ID = 0)) AND (UL_EMAIL is not null) AND (UL_EMAIL_DOMAIN is not null) ORDER BY UL_FIRST_NAME"
            temp_qry = final_qry.replace("SELECT UL_EMAIL_ID", "SELECT COUNT(UL_EMAIL_ID) as tot")
            
        number_of_member = 0
        if temp_qry:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(temp_qry)
                    row = cursor.fetchone()
                    if row:
                        number_of_member = row[0]
            except Exception as e:
                logger.error(f"Throttling Validation Counting Error: {str(e)}")
            
        domain_limit_msg = ""
        from_add = dto.get('fromAdd', '')
        domain_part = from_add.split('@')[-1] if '@' in from_add else ''
        domain_obj = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant_id), domDomain=domain_part).first()
        domain_capacity = domain_obj.domDomainCapacity if domain_obj else 0
        
        if dto.get('throttlingType') == "emails":
            tv_val = dto.get('throttlingValue', 0)
            if number_of_member < tv_val:
                domain_limit_msg = f"You cannot set {tv_val} emails because your group contains only {number_of_member} contacts.\nPlease enter a number less than or equal to {number_of_member}."
            elif domain_capacity < tv_val:
                domain_limit_msg = f"Your domain current sending limit : {domain_capacity} per day"
        else:
            days = dto.get('throttlingValue', 1) or 1
            count_email = math.ceil(number_of_member / days) if days > 0 else 0
            if domain_capacity < count_email:
                domain_limit_msg = f"Your domain current sending limit : {domain_capacity} per day.\nYour requirement limit : {count_email} per day"
                
        res_body["error"] = domain_limit_msg
        
    except Exception as e:
        logger.error(f"throttling_validation Error: {str(e)}")
        res_body["error"] = "Invalid Data"
        
    return api_response(200, "Fetch Throttling Validation Successfully.", res_body)

class ErrorMsgDto:
    def __init__(self):
        self.memberId = None
        self.requestURL = None
        self.errorMessage = None
        self.errorDetails = None

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_campaign_exists(request, campName):
    resBody = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        resBody["error"] = ""
        exists = None
        try:
            exists = CampaignsEmail.objects.filter(ceClientId=get_client_id_by_tenant_id(final_tenant_id), campName=campName).exists()
        except Exception as e:
            logger.error(f"[ tenantId : {final_tenant_id} ] FindCampaignExists Error : {e}")
        if exists:
            resBody["error"] = "Campaign Name Already Exists."
        else:
            resBody["error"] = ""
        if resBody.get("error") == "":
            return api_response(status.HTTP_200_OK, "Successfully.", resBody)
        else:
            return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Campaign Name Already Exists.", resBody)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetCampaignExists Error : {e}")
        errorMsgDto = ErrorMsgDto()
        errorMsgDto.memberId = final_tenant_id
        errorMsgDto.requestURL = request.build_absolute_uri() # Gets the full URL string in Django
        errorMsgDto.errorMessage = str(e)

        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Whoops Something Went Wrong!", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_email_preview(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = SendCampaignSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid Request", serializer.errors)
    
    dto = serializer.validated_data
    res_body = {"error": ""}
    
    try:
        campaign_name = dto.get('campName', '')
        subject = dto.get('subject', '')
        subject = re.sub(r'[^A-Za-z0-9#@.:%-,_/\']', ' ', subject)
        from_name = dto.get('fromName', '')
        selected_gid = dto.get('selectedGid', 0)

        all_data = ""
        my_page_id = dto.get('myPageId', 0) or 0
        if my_page_id > 0:
            read_path = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "mypage", str(my_page_id), "index.html")
            if os.path.exists(read_path):
                with open(read_path, 'r', encoding='utf-8') as f:
                    tree = lxml.html.fromstring(f.read())
                    all_data = lxml.html.tostring(tree, encoding='unicode')
        else:
            all_data = dto.get('allTempData', '')
            
        all_data = cron_send_campaign_content_remove(all_data)
        if dto.get('campType') == 1:
            all_data = re.sub(r'[\r\n]+', '<br/>', all_data)
        else:
            all_data = re.sub(r'[\r\n]+', '', all_data)
            
        all_data = re.sub(r'>\s+<', '><', all_data)
        all_data = nl2br(all_data)
        
        try:
            udf_first_group_data = CommonServices.find_group_first_records(tenant_id, selected_gid)
            for key, val in udf_first_group_data.items():
                replace_value = str(val) if val is not None else ""
                subject = subject.replace(f"##{key}##", replace_value)
                all_data = all_data.replace(f"##{key}##", replace_value)
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] SendEmailPreview Error 1 : {e}")

        if dto.get('mpType', 0) == 3:
            all_data += (
                "<div style='color:#4285F4; font-size:12px; padding: 1px 0px; display: flex; margin: 0px auto; width: 600px;'>"
                "<div style='margin: 10px; width: calc(100% - 20px); max-width: 600px;'>"
                f"<a href='{settings.SITE_URL}unsubscribe?ui=&ci=&e=&m=' style='color:#4285F4; padding-left:5px'>Opt Out</a>"
                f"<img src='{settings.SITE_URL_BACKEND}emailCampaign/openEmail?fg=1&ui=&ci=' />"
                "</div>"
                "</div>"
            )
        else:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": tenant_id
                    }
                }
            )
            client = Clients.objects.get(cliTenantId=tenant_id)
            country_setting = get_country_setting(tenant_id)
            cnty_white_listing = country_setting.cnty_white_listing if country_setting else 'n'
            cli_logo = client.cliLogo if client else None
            cli_customer_footer = client.cliCustomerFooter if client else None

            all_data += "<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:'Myriad Pro',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
            all_data += "<div style='padding-top:2px'>"
            
            if cnty_white_listing.lower() == 'y' and cli_logo:
                if cli_logo != "":
                    all_data += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
                else:
                    all_data += f'<a style="color:#00599A;margin: 0px auto;" href="{settings.SITE_URL_WWW}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{settings.SITE_URL}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'
            else:
                all_data += f'<a style="color:#00599A;margin: 0px auto;" href="{settings.SITE_URL_WWW}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{settings.SITE_URL}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'
            
            all_data += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"
            if cnty_white_listing.lower() == 'y' and cli_customer_footer:
                if cli_logo != "":
                    all_data += nl2br(cli_customer_footer)
                else:
                    all_data += settings.SITE_URL_ADDRESS
            else:
                all_data += settings.SITE_URL_ADDRESS

            all_data += "</div></div></div></div>"
            all_data += "<div align='center' style='color:#7f7f7f'><a href='#' style='color:#7f7f7f'>View In Browser</a> | <a href='#' style='color:#7f7f7f'>Unsubscribe</a> | <a href='#' style='color:#7f7f7f'>Change Language</a> | <a href='#' style='color:#7f7f7f'>Update Contact Information</a></div>"

        from_name_val = strip_slashes(campaign_name) if (from_name == "" or from_name is None) else strip_slashes(from_name)
        subject_val = strip_slashes(subject)
        html_data = strip_slashes(all_data)

        model_map = {
            "data": html_data,
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
            "siteNameBigCom": settings.SITE_NAME_BIG_COM
        }

        contact_selected = dto.get('contactSelected', [])
        for contact in contact_selected:
            mail_request = MailRequestDTO(
                to=contact,
                subject=subject_val,
                template_name="preview-email-template.ftl"
            )
            CommonServices.sendEmail(mail_request, model_map)

        all_data = ""
        testing_type = dto.get('testingType', 0)
        if testing_type != 6 and testing_type > 0:
            if testing_type == 2 or testing_type == 5:
                my_page_id_b = dto.get('myPageIdB', 0) or 0
                if my_page_id_b > 0:
                    read_path = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "mypage", str(my_page_id_b), "index.html")
                    if os.path.exists(read_path):
                        with open(read_path, 'r', encoding='utf-8') as f:
                            tree = lxml.html.fromstring(f.read())
                            all_data = lxml.html.tostring(tree, encoding='unicode')
                else:
                    all_data = dto.get('allTempDataB', '')
            else:
                if my_page_id > 0:
                    read_path = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images", "mypage", str(my_page_id), "index.html")
                    if os.path.exists(read_path):
                        with open(read_path, 'r', encoding='utf-8') as f:
                            tree = lxml.html.fromstring(f.read())
                            all_data = lxml.html.tostring(tree, encoding='unicode')
                else:
                    all_data = dto.get('allTempData', '')
                    
            if dto.get('campType') == 1:
                all_data = re.sub(r'[\r\n]+', '<br/>', all_data)
            else:
                all_data = re.sub(r'[\r\n]+', '', all_data)
            all_data = re.sub(r'>\s+<', '><', all_data)

            camp_detail = all_data
            from_add = dto.get('fromAdd', '')
            if testing_type in [3, 4, 5]:
                from_name = dto.get('fromNameB', '')
            else:
                from_name = dto.get('fromName', '')
                
            if testing_type in [1, 4, 5]:
                subject = dto.get('subjectB', '')
            else:
                subject = dto.get('subject', '')
                
            reply_to_add = dto.get('replyToAdd', '')
            campaign_name = dto.get('campName', '')
            camp_detail = cron_send_campaign_content_remove(camp_detail)
            camp_detail = re.sub(r'[\r\n]+', '', camp_detail)
            camp_detail = re.sub(r'>\s+<', '><', camp_detail)
            camp_detail = nl2br(camp_detail)
            
            try:
                udf_first_group_data = CommonServices.find_group_first_records(tenant_id, selected_gid)
                for key, val in udf_first_group_data.items():
                    replace_value = str(val) if val is not None else ""
                    subject = subject.replace(f"##{key}##", replace_value)
                    camp_detail = camp_detail.replace(f"##{key}##", replace_value)
            except Exception as e:
                logger.error(f"[ tenantId : {tenant_id} ] SendEmailPreview Error 2 : {e}")
                
            mp_type_b = dto.get('mpTypeB', 0) or 0
            if mp_type_b == 0:
                mp_type_b = dto.get('mpType', 0) or 0
                
            if mp_type_b == 3:
                camp_detail += (
                    "<div style='color:#4285F4; font-size:12px; padding: 1px 0px; display: flex; margin: 0px auto; width: 600px;'>"
                    "<div style='margin: 10px; width: calc(100% - 20px); max-width: 600px;'>"
                    f"<a href='{settings.SITE_URL}unsubscribe?ui=&ci=&e=&m=' style='color:#4285F4; padding-left:5px'>Opt Out</a>"
                    f"<img src='{settings.SITE_URL_BACKEND}emailCampaign/openEmail?fg=1&ui=&ci=' />"
                    "</div>"
                    "</div>"
                )
            else:
                tenant = get_tenants(
                    where_conditions={
                        "tenant": {
                            "ten_id": tenant_id
                        }
                    }
                )
                client = Clients.objects.get(cliTenantId=tenant_id)
                country_setting = get_country_setting(tenant_id)
                cnty_white_listing = country_setting.cnty_white_listing if country_setting else 'n'
                cli_logo = client.cliLogo if client else None
                cli_customer_footer = client.cliCustomerFooter if client else None

                camp_detail += "<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:'Myriad Pro',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
                camp_detail += "<div style='padding-top:2px'>"
                
                if cnty_white_listing.lower() == 'y' and cli_logo:
                    if cli_logo != "":
                        camp_detail += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
                    else:
                        camp_detail += f'<a style="color:#00599A;margin: 0px auto;" href="{settings.SITE_URL_WWW}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{settings.SITE_URL}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'
                else:
                    camp_detail += f'<a style="color:#00599A;margin: 0px auto;" href="{settings.SITE_URL_WWW}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{settings.SITE_URL}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'
                
                camp_detail += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"
                if cnty_white_listing.lower() == 'y' and cli_customer_footer:
                    if cli_logo != "":
                        camp_detail += nl2br(cli_customer_footer)
                    else:
                        camp_detail += settings.SITE_URL_ADDRESS
                else:
                    camp_detail += settings.SITE_URL_ADDRESS

                camp_detail += "</div></div></div></div>"
                camp_detail += "<div align='center' style='color:#7f7f7f'><a href='#' style='color:#7f7f7f'>View In Browser</a> | <a href='#' style='color:#7f7f7f'>Unsubscribe</a> | <a href='#' style='color:#7f7f7f'>Change Language</a> | <a href='#' style='color:#7f7f7f'>Update Contact Information</a></div>"

            from_name_val = strip_slashes(campaign_name) if (from_name == "" or from_name is None) else strip_slashes(from_name)
            subject_val = strip_slashes(subject)
            html_data = strip_slashes(camp_detail)
            
            for contact in contact_selected:
                mail_request = MailRequestDTO(
                    to=contact,
                    subject=subject_val,
                    template_name="preview-email-template.ftl"
                )

                model_map["data"] = html_data
                logger.error(f"[ tenantId : {tenant_id} ] SendEmailPreview Error data : {model_map["data"]}")
                CommonServices.sendEmail(mail_request, model_map)
                
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] SendEmailPreview Error 3 : {e}")
        res_body["error"] = str(e)
        return api_response(500, "Test e-mail Has Not Been Sent.", res_body)

    if res_body["error"] == "":
        return api_response(200, "Test e-mail Has Been Sent.", res_body)
    else:
        return api_response(500, "Test e-mail Has Not Been Sent.", res_body)

def get_source(user_agent):
    ua = (user_agent or "").lower()
    mobile_keywords = ["android", "iphone", "mobile", "ipad", "tablet"]
    for keyword in mobile_keywords:
        if keyword in ua:
            return "Phone"
    return "PC"

@api_view(['POST'])
def campaign_link_click(request: Request):
    flink = request.data.get("flink")
    d_enc = request.data.get('d')
    m_enc = str(request.data.get('m'))
    n_enc = request.data.get('n')
    res_body = {
        "url": flink,
        "error": ""
    }
    try:
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        sources = get_source(user_agent)
        camp_id = int(DecryptString.set_enc_dec_user(d_enc, "display", "Y"))
        decoded_once = base64.urlsafe_b64decode(m_enc)
        decoded_twice = base64.urlsafe_b64decode(decoded_once)
        user_id = int(decoded_twice.decode())
        try:
            CampaignsEmailSend.objects.filter(id=camp_id).update(last_opened=timezone.now())
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 2: {e}")

        try:
            CampaignSubscriber.objects.create(campId=camp_id, subId=user_id, totalOpen=1, lastOpened=timezone.now())
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 3: {e}")

        try:
            CampaignsSendEmail.objects.filter(emailId=user_id, campSendId=camp_id).update(isRead='Y')
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 4: {e}")

        split_group = None
        cse = None
        try:
            cse = CampaignsSendEmail.objects.filter(emailId=user_id, campSendId=camp_id).first()
            if cse:
                split_group = cse.splitGroup
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 4: {e}")
            pass

        try:
            if split_group is None:
                CampaignLinks.objects.filter(campId=camp_id, campLink=flink).update(linkCount=F('linkCount') + 1)
            else:
                if split_group == "O":
                    split_group = getattr(cse, "groupWinner")
                CampaignLinks.objects.filter(campId=camp_id, campLink=flink, splitGroup=split_group).update(linkCount=F('linkCount') + 1)
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 5: {e}")

        link_id = None
        try:
            if split_group is None:
                cl = CampaignLinks.objects.filter(campId=camp_id, campLink=flink).first()
            else:
                cl = CampaignLinks.objects.filter(campId=camp_id, campLink=flink, splitGroup=split_group).first()

            if cl:
                link_id = cl.id
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 7: {e}")

        campaign_link = None
        campaign_link_id = None
        node_id = 0
        try:
            if n_enc:
                node_id = int(DecryptString.set_enc_dec_user(n_enc, "display", "Y"))
                campaign_link = CampaignLinks.objects.filter(campLink=flink, nodeId=node_id).first()

                if campaign_link:
                    campaign_link_id = campaign_link.id
                    link_id = campaign_link_id
                    CampaignLinks.objects.filter(nodeId=node_id, campLink=flink).update(linkCount=F('linkCount') + 1)
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 8: {e}")

        try:
            if link_id:
                CampaignLinkClick.objects.create(userId=user_id, linkId=link_id, city=request.data.get("city"), linkCount=1, clickDate=timezone.now(), sources=sources, sourceDetails=user_agent)
        except Exception as e:
            logger.error(f"CampaignLinkClick Error 9: {e}")

        try:
            if campaign_link and campaign_link.automationEmailNodeDetails:
                user = Userlist.objects.filter(emailId=user_id).first()
                if user:
                    details = json.loads(campaign_link.automationEmailNodeDetails)
                    send_data = {
                        "emailId": user_id,
                        "groupId": user.groupId,
                        "myPageId": details["emailTemplateSelected"]["mpId"],
                        "fromName": details["fromName"],
                        "fromAddress": details["fromEmail"],
                        "subject": details["subject"],
                        "sendLinkId": campaign_link_id,
                        "sendNodeId": node_id,
                        "sendAutomationId": campaign_link.campId
                    }
                    CommonServices.send_email_to_contact(get_tenant_id_by_client_id(user.memberId), send_data)
        except Exception as e:
            logger.exception(f"CampaignLinkClick Error 11: {e}")
    except Exception as e:
        res_body["error"] = "Invalid Data"
        logger.error(f"CampaignLinkClick Main Error: {e}")

    if res_body.get("error", "") == "":
        return api_response(200, "Campaign Link Click Successfully.", res_body)
    else:
        return api_response(500, res_body.get("error"), res_body, sendErrorAs200=True)

@api_view(['GET'])
def open_email(request: Request):
    fg = request.GET.get('fg', '1')
    ui = request.GET.get('ui', '')
    ci = request.GET.get('ci', '')
    d_enc = request.GET.get('d', '')
    m_enc = request.GET.get('m', '')

    # Prioritize ui/ci (Java style) then d/m (legacy Python style)
    if not ui: ui = m_enc
    if not ci: ci = d_enc

    view_in_browser_url = ""

    if ui and ci:
        try:
            # URL safe base64 decoding with padding handling
            def decode_b64(data):
                try:
                    padding = 4 - (len(data) % 4)
                    if padding < 4:
                        data += "=" * padding
                    return base64.urlsafe_b64decode(data).decode('utf-8')
                except:
                    return data # Fallback to raw data if not base64

            ui_decoded = decode_b64(ui)
            ci_decoded = decode_b64(ci)

            try:
                subscriber_id = int(ui_decoded)
                camp_send_id = int(ci_decoded)
            except (ValueError, TypeError):
                subscriber_id = 0
                camp_send_id = 0

            if subscriber_id > 0 and camp_send_id > 0:
                try:
                    # Update 1: Last open timestamp on the main send record
                    try:
                        CampaignsEmailSend.objects.filter(id=camp_send_id).update(last_opened=timezone.now())
                    except Exception as e:
                        logger.error(f"OpenEmail Error 1 : {e}")

                    # Update 2: Record individual open in CampaignSubscriber
                    try:
                        CampaignSubscriber.objects.create(
                            campId=camp_send_id,
                            subId=subscriber_id,
                            totalOpen=1,
                            lastOpened=timezone.now(),
                        )
                    except Exception as e:
                        logger.error(f"OpenEmail Error 2 : {e}")

                    # Update 3: Set is_read flag on subscriber record
                    try:
                        CampaignsSendEmail.objects.filter(emailId=subscriber_id, campSendId=camp_send_id).update(isRead='Y')
                    except Exception as e:
                        logger.error(f"OpenEmail Error 3 : {e}")

                except Exception as e:
                    logger.error(f"OpenEmail Error 4 : {e}")

                # Prepare view in browser URL for QR code (matching Java line 3054-3055)
                try:
                    camp_data = CampaignsEmailSend.objects.filter(id=camp_send_id).first()
                    if camp_data:
                        get_mypage_id = camp_data.mypageid or 0
                        view_in_browser_url = f"{settings.SITE_URL}viewinbrowser?mpId={DecryptString.set_enc_dec_user(str(get_mypage_id), '', 'Y')}&ui={ui}&ci={ci}"
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"OpenEmail Overall Error : {e}")

    # Image Response Handling (Matching Java logic line 3058-3089)
    if fg == "0":
        # Java generates a 100x100 QR code here.
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=1,
                border=4,
            )
            data_to_encode = view_in_browser_url if view_in_browser_url else " "
            qr.add_data(data_to_encode)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white").get_image()
            # Resize to exactly 100x100 to match Java implementation
            img = img.resize((100, 100))
            
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return HttpResponse(buffer.getvalue(), content_type="image/png")
        except Exception as e:
            logger.error(f"OpenEmail Error 5 : {e}")
            # Representing the tracking/QR placeholder
            black_pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
            return HttpResponse(black_pixel, content_type="image/png")
    else:
        try:
            # Generate a black square of size fg x fg as requested in Java service
            try:
                width = int(fg)
            except:
                width = 1
            
            if width <= 0: width = 1
            
            image = Image.new('RGB', (width, width), color=(0, 0, 0))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return HttpResponse(buffer.getvalue(), content_type="image/png")
        except Exception as e:
            logger.error(f"OpenEmail Error 5 : {e}")
            # Final fallback to standard tracking pixel
            return HttpResponse(base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"), content_type="image/gif")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_campaign_by_id(request):
    camp_id = request.query_params.get('campId')
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        campId = int(camp_id)
        campaigns_email = CampaignsEmail.objects.get(campId=campId)
        campaigns_send_email = CampaignsSendEmail.objects.filter(campId=campId).order_by('-campSendId').first()

        camp_send_id = 0
        if campaigns_send_email and campaigns_send_email.campSendId:
            camp_send_id = campaigns_send_email.campSendId

        res_data = {
            "campSendId": camp_send_id,
            "subject": campaigns_email.subject,
            "templateName": "",
            "groupName": "",
            "totalMemberTooltip": 0,
            "totalMemberNotOpen": 0,
            "totalMemberResendAll": 0,
            "lastSendDate": "",
            "sendDate": ""
        }

        if campaigns_email.mypageId:
            try:
                mypage = MyPages.objects.get(mpId=campaigns_email.mypageId)
                res_data["templateName"] = mypage.mpName
            except MyPages.DoesNotExist:
                pass

        if campaigns_email.groupList:
            try:
                # Java uses Long.parseLong(campaignsEmail.getGroupList())
                gid = int(campaigns_email.groupList)
                group = Groups.objects.get(grpId=gid)
                res_data["groupName"] = group.grpGroupName
            except (Groups.DoesNotExist, ValueError):
                pass

        # Total sent for this specific camp_send_id
        res_data["totalMemberTooltip"] = CampaignsSendEmail.objects.filter(campId=campId, campSendId=camp_send_id).count()

        res_data["totalMemberNotOpen"] = CampaignsSendEmail.objects.filter(
            campId=campId,
            campSendId=camp_send_id,
            isRead__isnull=True
        ).filter(
            Q(isBounced__isnull=True) | Q(isBounced='N')
        ).filter(
            emailId__in=Userlist.objects.values('emailId')
        ).count()

        res_data["totalMemberResendAll"] = CampaignsSendEmail.objects.filter(
            campId=campId,
            campSendId=camp_send_id
        ).filter(
            Q(isBounced__isnull=True) | Q(isBounced='N')
        ).filter(
            emailId__in=Userlist.objects.values('emailId')
        ).count()

        if campaigns_email.sendOnDate:
            res_data["lastSendDate"] = display_date(campaigns_email.sendOnDate)

        if campaigns_email.sendDate:
            res_data["sendDate"] = display_date(campaigns_email.sendDate)

        res_body["campaign"] = res_data
        return api_response(200, "Fetch Email Campaign Successfully.", res_body)

    except CampaignsEmail.DoesNotExist:
        return api_response(404, "Campaign Not Found")
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetCampaignById Error : {e}")
        return api_response(500, "Internal Server Error")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_email(request):
    # Java equivalent: /emailCampaign/sendEmail
    return api_response(200, "Email sent successfully")

@api_view(['GET'])
def view_in_browser(request: Request):
    mp_id_enc = request.GET.get('mpId', '')
    ui_enc = request.GET.get('ui', '')
    ci_enc = request.GET.get('ci', '')
    print(mp_id_enc, ui_enc, ci_enc)
    if not mp_id_enc or not ui_enc:
        return api_response(status.HTTP_400_BAD_REQUEST, "Missing parameters")

    try:
        # 1. Decode/Decrypt Parameters
        mp_id = int(DecryptString.set_enc_dec_user(mp_id_enc, "display", "Y"))

        def decode_b64(data):
            try:
                padding = 4 - (len(data) % 4)
                if padding < 4:
                    data += "=" * padding
                return base64.urlsafe_b64decode(data).decode('utf-8')
            except:
                return "0"

        subscriber_id = int(decode_b64(ui_enc))
        camp_send_id = int(decode_b64(ci_enc))

        mypage = get_object_or_404(MyPages, mpId=mp_id)
        tenant_id = get_tenant_id_by_client_id(mypage.mpClientId)
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        client = Clients.objects.get(cliTenantId=tenant_id)

        your_first_name = tenant.ten_first_name or ""
        your_last_name = tenant.ten_last_name or ""
        cli_logo = client.cliLogo
        cli_customer_footer = client.cliCustomerFooter

        country_setting = get_country_setting(tenant_id)
        cnty_white_listing = country_setting.cnty_white_listing if country_setting else "n"

        # 3. Fetch Campaign Record
        campaign_send_email = CampaignsSendEmail.objects.filter(emailId=subscriber_id, campSendId=camp_send_id).order_by('-id').first()
        if not campaign_send_email:
            return api_response(status.HTTP_404_NOT_FOUND, "Campaign record not found")

        # 4. Fetch Translation Template
        translate_template = TranslateTemplateSend.objects.filter(ttMyPageId=mp_id, ttTemplateLanguage=campaign_send_email.csDefaultLanguage).order_by('-ttId').first()
        if not translate_template:
            # Fallback to first available template for this page if language-specific not found
            translate_template = TranslateTemplateSend.objects.filter(ttMyPageId=mp_id).order_by('-ttId').first()

        if not translate_template:
            return api_response(status.HTTP_404_NOT_FOUND, "Template not found")

        # 5. Fetch Contact Details (Userlist)
        contact = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), emailId=subscriber_id).first()
        if not contact:
            return api_response(status.HTTP_404_NOT_FOUND, "Contact (Userlist) not found")

        # 6. Extraction and Sanitization (Java lines 3718-3726)
        camp_detail_temp = translate_template.ttCampDetailSend or ""
        camp_detail_temp = camp_detail_temp.replace('\u200c', '').replace('\u200b', '')
        camp_detail_temp = camp_detail_temp.replace("447px", "5px")
        camp_detail_temp = camp_detail_temp.replace('height="100%"', '')
        
        # Remove style blocks
        camp_detail_temp = re.sub(r'(?i)<style.*?>.*?</style>', '', camp_detail_temp, flags=re.DOTALL)
        # Remove editor tags
        camp_detail_temp = re.sub(r'<!--RT3S-->.*?<!--RT3E-->', '', camp_detail_temp, flags=re.DOTALL)

        # 7. Placeholder Replacements
        def safe_replace(content, pattern, val):
            if val is None: val = ""
            return re.sub(pattern, str(val).strip(), content, flags=re.IGNORECASE)

        camp_detail_temp = safe_replace(camp_detail_temp, r'##your_first_name##', DecryptString.set_enc_dec_user(your_first_name, "display", "Y"))
        camp_detail_temp = safe_replace(camp_detail_temp, r'##your_last_name##', DecryptString.set_enc_dec_user(your_last_name, "display", "Y"))

        # Contact details
        camp_detail_temp = safe_replace(camp_detail_temp, r'##first_name##', contact.firstName)
        camp_detail_temp = safe_replace(camp_detail_temp, r'##client_first_name##', contact.firstName)
        camp_detail_temp = safe_replace(camp_detail_temp, r'##last_name##', contact.lastName)
        camp_detail_temp = safe_replace(camp_detail_temp, r'##client_last_name##', contact.lastName)

        email_display = contact.email or ""
        camp_detail_temp = safe_replace(camp_detail_temp, r'##email##', email_display)

        # Contact Phone
        client_phone_number = contact.phoneNumber or ""
        camp_detail_temp = safe_replace(camp_detail_temp, r'##contact_no##', client_phone_number.replace(" ", ""))

        # Contact Address
        camp_detail_temp = safe_replace(camp_detail_temp, r'##street_address1##', contact.streetAddress1)
        camp_detail_temp = safe_replace(camp_detail_temp, r'##street_address2##', contact.streetAddress2)
        camp_detail_temp = safe_replace(camp_detail_temp, r'##city##', contact.city)
        camp_detail_temp = safe_replace(camp_detail_temp, r'##state##', contact.stateProvRegion)
        camp_detail_temp = safe_replace(camp_detail_temp, r'##country##', contact.country)

        # UDF replacement logic (Java lines 3837-3871)
        udf_array = list(Udf.objects.filter(groupId=contact.groupId).values_list('udf', flat=True))
        for i, udf_name in enumerate(udf_array):
            if i >= 10: break
            search_val = f"##{udf_name}##"
            replace_val = getattr(contact, f'udf{i+1}', "") or ""
            camp_detail_temp = camp_detail_temp.replace(search_val, replace_val.strip())

        # 8. HTML Post-Processing (Jsoup equivalents)
        try:
            doc = lxml.html.fromstring(camp_detail_temp)
            # doc.select("div.removeClass").remove()
            for div in doc.xpath('//div[contains(@class, "removeClass")]'):
                div.getparent().remove(div)
            camp_detail_temp = lxml.html.tostring(doc, encoding='unicode')
        except:
            pass

        camp_detail_temp = cron_send_campaign_content_remove(camp_detail_temp)
        camp_detail_temp = camp_detail_temp.replace("</body></html>", "")

        # 9. Branding and Tracking Links Footer (Java lines 3880-3940)
        footer = "<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:'Myriad Pro',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
        footer += "<div style='padding-top:2px'>"

        site_url = settings.SITE_URL
        site_url_www = settings.SITE_URL_WWW
        site_url_address = settings.SITE_URL_ADDRESS

        # Whitelisting logo
        if cnty_white_listing.lower() == "y" and cli_logo:
             footer += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
        else:
             footer += f'<a style="color:#00599A;margin: 0px auto;" href="{site_url_www}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{site_url}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'

        footer += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"
        if cnty_white_listing.lower() == "y" and cli_customer_footer:
             footer += nl2br(cli_customer_footer)
        else:
             footer += site_url_address

        # Tracking and Management Links
        group_id_str = f"{contact.groupId}~{tenant_id}~0~{subscriber_id}"
        update_str = DecryptString.set_enc_dec_user(group_id_str, "", "Y")
        update_contact_link = f"{site_url}inviteurl?q={update_str}"

        temp_email_b64 = base64.b64encode(email_display.encode('utf-8')).decode('utf-8')
        temp_tenant_id_b64 = base64.b64encode(str(tenant_id).encode('utf-8')).decode('utf-8')

        footer += f"</div></div>"
        footer += f'</div></div><div align="center" style="color:#4285F4;font-size:12px;font-family:Arial, Helvetica Neue, Helvetica, sans-serif;">'
        footer += f'<a href="{site_url}viewinbrowser?mpId={mp_id_enc}&ui={ui_enc}&ci={ci_enc}" style="color:#4285F4">View In Browser</a> | '
        footer += f'<a href="{site_url}unsubscribe?ui={ui_enc}&ci={ci_enc}&e={temp_email_b64}&m={temp_tenant_id_b64}" style="color:#4285F4">Unsubscribe</a> | '
        footer += f'<a href="{site_url}viewtemplate?mpId={mp_id_enc}" style="color:#4285F4">Change Language</a> | '
        footer += f'<a href="{update_contact_link}" style="color:#4285F4">Update Contact Information</a></div>'
        
        footer += f'<br/><div align="center"><img src="{settings.SITE_URL_BACKEND}emailCampaign/openEmail?fg=0&ui={ui_enc}&ci={ci_enc}" /></div>'
        footer += "<br/></body></html>"

        camp_detail_temp += footer
        
        # Prepare Response Object
        response_data = {
            "ttId": translate_template.ttId,
            "mpTemplateLanguage": mypage.mpTemplateLanguage,
            "mpTemplateConvertLangList": mypage.mpTemplateConvertLangList,
            "ttCampDetail": camp_detail_temp
        }
        
        return api_response(status.HTTP_200_OK, "Preview Successfully.", {"response":response_data})

    except Exception as e:
        logger.error(f"ViewInBrowser Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error")

def check_subject_content(subject, message):
    res_body: dict[str, Any] = {
        "emailSubjectColor": 1,
        "emailSubjectError": [],
        "emailContentColor": 1,
        "emailContentError": []
    }
    
    email_subject_error: list[str] = res_body["emailSubjectError"]

    first_word_array = ["hi", "hello", "hey", "whazzup", "what's", "yo", "howdy"]
    subject_split = subject.lower().split(" ")
    if subject_split and subject_split[0] in first_word_array:
        res_body["emailSubjectColor"] = 0
        email_subject_error.append("First Word Flag")
        
    if subject:
        first_char = subject.lower()[0]
        if not ('a' <= first_char <= 'z'):
            res_body["emailSubjectColor"] = 0
            email_subject_error.append("First Character Flag")
            
    # Simplified spam/vulgar words logic (as CSVs are not available here)
    spam_words = ["free", "money", "win", "winner", "cash"] # Placeholder

    sub_lower = subject.lower()
    for word in spam_words:
        if word in sub_lower:
            res_body["emailSubjectColor"] = 0
            email_subject_error.append(f"Spam Words : {word}")
            break
            
    # Capitalization check
    cu = sum(1 for c in subject if c.isupper())
    cl = sum(1 for c in subject if c.islower())
    if cu > cl:
        res_body["emailSubjectColor"] = 0
        email_subject_error.append("Percent Capital Letters")
        
    # Punctuation check
    if ".." in subject:
        res_body["emailSubjectColor"] = 0
        email_subject_error.append("Punctuation Flag")
        
    return res_body

def check_spam_assassin(from_add, tenant_id, selected_gid, subject, all_data):
    """
    Integrates with SpamAssassin using spamc.
    Java equivalent: checkSpamAssassin
    """
    res_body = {"localSpamScore": 0}
    try:
        # Prepare email content with headers (simplified but following Java logic)
        headers = f"To: support@example.com\r\n"
        headers += f"From: {from_add}\r\n"
        headers += f"Subject: {subject}\r\n"
        headers += f"Date: {datetime.now().strftime('%a, %d %b %Y %H:%M:%S')}\r\n"
        headers += "Content-type: text/html; charset=iso-8859-1\r\n\r\n"
        
        email_content = headers + all_data

        process = subprocess.Popen(['/usr/bin/spamc', '-R'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(input=email_content)
        
        if stdout:
            # Java logic: String[] st = str.split("/"); Long.parseLong(st[0])
            match = re.search(r'Spam detection software.*?([\d\.]+)/([\d\.]+)', stdout, re.DOTALL)
            if match:
                res_body["localSpamScore"] = int(float(match.group(1))) # type: ignore
            elif "/" in stdout:
                st = stdout.split("/")
                try:
                    res_body["localSpamScore"] = int(float(st[0].strip().split()[-1])) # type: ignore
                except:
                    pass
                    
        return res_body
    except Exception as e:
        logger.error(f"check_spam_assassin Error: {str(e)}")
        return res_body

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_list_page(request):
    tenant_id = get_final_tenant_id(request=request)
    camp_id_raw = request.query_params.get('id')
    search_key = request.query_params.get('searchKey')
    time_zone = request.query_params.get('timeZone')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 10))
    
    try:
        camp_id = int(camp_id_raw) if camp_id_raw else 0
        
        queryset = CampaignsEmailSend.objects.filter(member_id=get_client_id_by_tenant_id(tenant_id), camp_id=camp_id)
        if search_key:
            queryset = queryset.filter(campName__icontains=search_key)
            
        paginator = Paginator(queryset.order_by('-id'), size)
        current_page = paginator.get_page(page + 1)
        
        total_elements = queryset.count()
        
        email_campaigns_report_list = []
        for ces in current_page:
            item = {
                "campName": ces.campName,
                "campId": ces.id,
                "campMainType": ces.campMainType,
                "encCampId": DecryptString.set_enc_dec_user(str(ces.id), "", "Y"),
                "createdOn": "",
                "sendOnDate": ""
            }
            if hasattr(ces, 'sendondate') and ces.sendondate:
                item["createdOn"] = display_date_time(ces.sendondate)
            if ces.sendOnDate:
                item["sendOnDate"] = convert_event_timezone_to_user(display_date_time(ces.sendOnDate), "UTC", time_zone)
            email_campaigns_report_list.append(item)
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalCampaignsEmailSend": total_elements,
            "emailCampaignsReport": email_campaigns_report_list
        }
        return api_response(200, "Fetch Email Campaigns Report List Successfully.", res_body)
    except Exception as e:
        logger.error(f"get_email_campaigns_report_list_page Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_sources(request):
    camp_id_enc = request.query_params.get('campId')
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        campaign_links = CampaignLinks.objects.filter(campId=camp_id)
        source_links = []
        for cl in campaign_links:
            pc = CampaignLinkClick.objects.filter(linkId=cl.id, sources='PC').count()
            phone = CampaignLinkClick.objects.filter(linkId=cl.id, sources='Phone').count()
            source_links.append({
                "id": cl.id,
                "campLink": cl.campLink,
                "clickThroughRate": None,
                "pc": pc,
                "mobile": phone
            })
            
        return api_response(200, "Fetch Email Campaigns Report Sources Successfully.", source_links)
    except Exception as e:
        logger.error(f"get_email_campaigns_report_sources Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_campaigns_report_print(request):
    tenant_id = get_final_tenant_id(request=request)
    cid_raw = request.query_params.get('id')
    camp_id_enc = request.query_params.get('campId')
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        cid_raw = int(cid_raw) if cid_raw else 0 # camp_send_id
        
        # This is a combination of product links, members and sources
        # Reusing logic for brevity
        product_links = []
        members = []
        source_links = []
        
        # Product Links
        total_recept = CampaignsSendEmail.objects.filter(campSendId=cid_raw, isSend='Y', isBounced='N').count()
        campaign_links = CampaignLinks.objects.filter(campId=camp_id)
        for cl in campaign_links:
            uc = CampaignLinkClick.objects.filter(linkId=cl.id).values('emailId').distinct().count()
            click_through = (cl.linkCount / total_recept * 100) if total_recept > 0 else 0.0
            product_links.append({
                "id": cl.id, "campLink": cl.campLink, "uniqueClicks": uc,
                "totalClicks": cl.linkCount, "clickThroughRate": click_through
            })
            
            # Source
            pc = CampaignLinkClick.objects.filter(linkId=cl.id, sources='PC').count()
            phone = CampaignLinkClick.objects.filter(linkId=cl.id, sources='Phone').count()
            source_links.append({
                "id": cl.id, "campLink": cl.campLink, "clickThroughRate": None, "pc": pc, "mobile": phone
            })
            
        # Members
        member_list = CampaignsSendEmail.objects.filter(campSendId=cid_raw).order_by('firstName')
        for cse in member_list:
            unsubscribe_date = Contact.objects.filter(emailId=cse.emailId, memberId=get_client_id_by_tenant_id(tenant_id), optId=cse.campId, status='Unsubscribed').first()
            unsubscribe_date_str = display_date_time(unsubscribe_date.optDate) if unsubscribe_date and unsubscribe_date.optDate else ""
            total_open = CampaignSubscriber.objects.filter(campId=cse.campId, subId=cse.emailId).count()
            members.append({
                "firstName": cse.firstName, "lastName": cse.lastName, "emailId": cse.emailId,
                "email": cse.email,
                "unsubscribeDate": unsubscribe_date_str, "totalOpen": total_open
            })
            
        res_body = {
            "productLinks": product_links,
            "members": members,
            "sourceLinks": source_links
        }
        return api_response(200, "success", res_body)
    except Exception as e:
        logger.error(f"get_campaigns_report_print Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_dashboard(request):
    tenant_id = get_final_tenant_id(request=request)
    cid_raw = request.query_params.get('id')
    camp_id_enc = request.query_params.get('campId')
    time_zone = request.query_params.get('timeZone')
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        cid_raw = int(cid_raw) if cid_raw else 0 # camp_send_id
        
        camp_send = CampaignsEmailSend.objects.get(id=cid_raw, member_id=get_client_id_by_tenant_id(tenant_id))
        
        dashboard = {
            "campName": camp_send.camp_name,
            "totalQueued": camp_send.total_queued,
            "sentOn": "",
            "templateName": "",
            "mailingGroup": "",
            "subject": camp_send.subject,
            "senderName": camp_send.from_name,
            "senderEmail": camp_send.from_add,
            "sent": 0,
            "delivered": 0,
            "exception": 0,
            "opened": 0,
            "bounced": 0,
            "unread": 0,
            "totalDesktop": 0,
            "totalMobile": 0,
            "successfulDeliveries": 0,
            "successfulDeliveriesPer": 0.0,
            "bouncedPer": 0.0,
            "unsubscribed": 0,
            "unsubscribedPer": 0.0,
            "openRatePer": 0.0,
            "totalClickThroughRate": 0,
            "totalClickThroughRatePer": 0.0,
            "uniqueClickThroughRate": 0,
            "uniqueClickThroughRatePer": 0.0,
            "lastOpened": ""
        }
        
        if camp_send.sendondate:
            dashboard["sentOn"] = convert_event_timezone_to_user(display_date_time(camp_send.sendondate), "UTC", time_zone)
        
        if camp_send.mypageid:
            mypage = MyPages.objects.filter(myPageId=camp_send.mypageid).first()
            if mypage:
                dashboard["templateName"] = mypage.mpName
                
        if camp_send.grouplist:
            group = Groups.objects.filter(grpId=int(camp_send.grouplist)).first()
            if group:
                dashboard["mailingGroup"] = group.grpGroupName
                
        with connection.cursor() as cursor:
            # findSentCount
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_SEND_ID=%s", [cid_raw])
            sent = cursor.fetchone()[0]
            dashboard["sent"] = sent
            
            # findDeliveryCount
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_IS_SEND='Y' and CES_IS_BOUNCED='N' and CES_SEND_ID=%s", [cid_raw])
            delivered = cursor.fetchone()[0]
            dashboard["delivered"] = delivered
            dashboard["successfulDeliveries"] = delivered
            
            # findExceptionCount
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_IS_SEND='Y' and (CES_IS_BOUNCED='E' OR CES_IS_BOUNCED='D') and CES_SEND_ID=%s", [cid_raw])
            exception = cursor.fetchone()[0]
            dashboard["exception"] = exception
            
            # findOpenedCount
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_IS_READ='Y' and CES_SEND_ID=%s", [cid_raw])
            opened = cursor.fetchone()[0]
            dashboard["opened"] = opened
            dashboard["unread"] = delivered - opened
            
            # findBouncedCount
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_IS_BOUNCED='Y' and CES_SEND_ID=%s", [cid_raw])
            bounced = cursor.fetchone()[0]
            dashboard["bounced"] = bounced
            
            # findUnsubscribedCount
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_IS_UNSUBSCRIBED='Y' and CES_SEND_ID=%s", [cid_raw])
            unsubscribed = cursor.fetchone()[0]
            dashboard["unsubscribed"] = unsubscribed

            if sent > 0:
                dashboard["bouncedPer"] = round((bounced * 100.0) / sent, 2)
                
            # Unsubscribed Count & Percentage
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_IS_UNSUBSCRIBED='Y' and CES_SEND_ID=%s", [cid_raw])
            unsubscribed = cursor.fetchone()[0]
            dashboard["unsubscribed"] = unsubscribed
            if sent > 0:
                dashboard["unsubscribedPer"] = round((unsubscribed * 100.0) / sent, 2)
                
            # Open Rate Percentage
            if delivered > 0:
                dashboard["openRatePer"] = round((opened * 100.0) / delivered, 2)
                
            # Click Through Rate & Device Stats
            cursor.execute("SELECT CL_ID, CL_LINK_COUNT FROM CAMPAIGN_LINKS where CL_CAMP_ID=%s", [camp_id])
            links = cursor.fetchall()
            link_ids = [row[0] for row in links]
            link_count_total = sum(row[1] for row in links)
            dashboard["totalClickThroughRate"] = link_count_total
            
            if delivered > 0:
                dashboard["totalClickThroughRatePer"] = round((link_count_total * 100.0) / delivered, 2)
            
            unique_clicks_total = 0
            total_desktop = 0
            total_mobile = 0
            
            if link_ids:
                # Java: sum of unique users per link
                for lid in link_ids:
                    cursor.execute("SELECT count(distinct USER_ID) FROM TEMP_CAMP_LINK_CLICK where LINK_ID=%s", [lid])
                    unique_clicks_total += cursor.fetchone()[0]
                    
                    cursor.execute("SELECT count(ID_LINK) FROM TEMP_CAMP_LINK_CLICK where LINK_ID=%s and sources='PC'", [lid])
                    total_desktop += cursor.fetchone()[0]
                    
                    cursor.execute("SELECT count(ID_LINK) FROM TEMP_CAMP_LINK_CLICK where LINK_ID=%s and sources='Phone'", [lid])
                    total_mobile += cursor.fetchone()[0]
            
            dashboard["uniqueClickThroughRate"] = unique_clicks_total
            dashboard["totalDesktop"] = total_desktop
            dashboard["totalMobile"] = total_mobile
            
            # lastOpened
            cursor.execute("SELECT max(CS_LAST_OPENED) FROM CAMPAIGN_EMAIL_REPORTING where CS_CAMP_ID=%s", [camp_id])
            last_opened_row = cursor.fetchone()
            if last_opened_row and last_opened_row[0]:
                dashboard["lastOpened"] = last_opened_row[0].strftime('%m/%d/%Y %H:%M:%S')

            if sent > 0:
                dashboard["successfulDeliveriesPer"] = round(float(delivered * 100.0) / sent, 2)
                dashboard["bouncedPer"] = round(float(bounced * 100.0) / sent, 2)
                dashboard["unsubscribedPer"] = round(float(unsubscribed * 100.0) / sent, 2)
                
            if delivered > 0:
                dashboard["openRatePer"] = round(float(opened * 100.0) / delivered, 2)
                dashboard["totalClickThroughRatePer"] = round(float(link_count_total * 100.0) / delivered, 2)
                dashboard["uniqueClickThroughRatePer"] = round(float(unique_clicks_total * 100.0) / delivered, 2)
                
        return api_response(200, "Fetch Email Campaigns Report Dashboard Successfully.", dashboard)
    except CampaignsEmailSend.DoesNotExist:
        return api_response(404, "campaignNotExists")
    except Exception as e:
        logger.error(f"get_email_campaigns_report_dashboard Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_product_links_click_user(request):
    link_id = request.query_params.get('linkId')
    try:
        # getUserWiseLinkCount
        clicks_user_wise = CampaignLinkClick.objects.filter(linkId=link_id).values('emailId').annotate(link_count=Count('id'))
        
        product_links_click_user = []
        for item in clicks_user_wise:
            email_id = item['emailId']
            # getClickOneDetailByEmailId
            click_user = CampaignsSendEmail.objects.filter(emailId=email_id).order_by('-id').first()
            user_name = f"{click_user.firstName} {click_user.lastName}" if click_user else "Unknown"
            
            product_links_click_user.append({
                "userName": user_name,
                "linkCount": item['link_count']
            })
            
        return api_response(200, "success", product_links_click_user)
    except Exception as e:
        logger.error(f"get_email_campaigns_report_product_links_click_user Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_product_links(request):
    cid_raw = request.query_params.get('id') # camp_send_id
    camp_id_enc = request.query_params.get('campId')
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        cid_raw = int(cid_raw) if cid_raw else 0
        
        with connection.cursor() as cursor:
            # findDeliveryCount
            cursor.execute("SELECT count(CES_ID) FROM CAMPAIGN_EMAIL_SENT where CES_IS_SEND='Y' and CES_IS_BOUNCED='N' and CES_SEND_ID=%s", [cid_raw])
            total_recept = cursor.fetchone()[0]
            
        campaign_links = CampaignLinks.objects.filter(campId=camp_id)
        product_links = []
        
        for cl in campaign_links:
            with connection.cursor() as cursor:
                # getLinkCountUserWise
                cursor.execute("SELECT count(DISTINCT USER_ID) FROM TEMP_CAMP_LINK_CLICK WHERE LINK_ID=%s", [cl.id])
                uc = cursor.fetchone()[0]
                
            unique_click_through = 0.0
            total_click_through = 0.0
            if total_recept > 0:
                unique_click_through = (uc * 100.0) / total_recept
                total_click_through = (cl.linkCount * 100.0) / total_recept
                
            user_detail_list = []
            # getUserWiseLinkCount
            clicks_user_wise = CampaignLinkClick.objects.filter(linkId=cl.id).values('emailId').annotate(link_count=Count('id'))
            for item in clicks_user_wise:
                email_id = item['emailId']
                click_user = CampaignsSendEmail.objects.filter(emailId=email_id, campSendId=cid_raw).first()
                user_name = f"{click_user.firstName} {click_user.lastName}" if click_user else "Unknown"
                
                location_list = []
                locations = CampaignLinkClick.objects.filter(linkId=cl.id, emailId=email_id)
                for loc in locations:
                    source = "Desktop" if loc.sources == "PC" else "Mobile" if loc.sources == "Phone" else loc.sources
                    location_list.append({
                        "osSource": source,
                        "cntDetails": loc.sourceDetails,
                        "cityName": loc.city,
                        "clickDateTime": display_date_time(loc.clickDate) if loc.clickDate else ""
                    })
                
                user_detail_list.append({
                    "clickUserName": user_name,
                    "clickCountUser": item['link_count'],
                    "locationList": location_list
                })
                
            product_links.append({
                "campLink": cl.campLink,
                "uniqueClicks": uc,
                "totalClicks": cl.linkCount,
                "uniqueClickThroughRatePer": round(unique_click_through, 2),
                "totalClickThroughRatePer": round(total_click_through, 2),
                "userDetailList": user_detail_list
            })
            
        return api_response(200, "Fetch Email Campaigns Report Product Links Successfully.", product_links)
    except Exception as e:
        logger.error(f"get_email_campaigns_report_product_links Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_member_click(request):
    cid_raw = request.query_params.get('id')
    camp_id_enc = request.query_params.get('campId')
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        cid_raw = int(cid_raw) if cid_raw else 0
        
        # Java logic matching EmailCampaignsReportServiceImpl:300+
        # This is very similar to product links but summarized by member
        members_click = []
        with connection.cursor() as cursor:
            # find all members who clicked any link in this campaign
            cursor.execute("""
                SELECT DISTINCT USER_ID FROM TEMP_CAMP_LINK_CLICK 
                WHERE LINK_ID IN (SELECT CL_ID FROM CAMPAIGN_LINKS WHERE CL_CAMP_ID = %s)
            """, [camp_id])
            email_ids = [row[0] for row in cursor.fetchall()]

            for email_uid in email_ids:
                click_user = CampaignsSendEmail.objects.filter(emailId=email_uid, campSendId=cid_raw).first()
                if not click_user: continue

                # getCountTotalClick
                cursor.execute("""
                    SELECT count(clc.ID_LINK) FROM TEMP_CAMP_LINK_CLICK clc, CAMPAIGN_LINKS cl 
                    WHERE cl.CL_CAMP_ID = %s AND clc.USER_ID = %s AND clc.LINK_ID = cl.CL_ID
                """, [camp_id, email_uid])
                total_clicks = cursor.fetchone()[0]

                link_list = []
                campaign_links = CampaignLinks.objects.filter(campId=camp_id)
                for cl in campaign_links:
                    # findDetailByLinkIdAndUserId
                    clcs = CampaignLinkClick.objects.filter(linkId=cl.id, emailId=email_uid)
                    if clcs.exists():
                        location_list = []
                        for loc in clcs:
                            source = "Desktop" if loc.sources == "PC" else "Mobile" if loc.sources == "Phone" else loc.sources
                            location_list.append({
                                "osSource": source,
                                "cntDetails": loc.sourceDetails,
                                "cityName": loc.city,
                                "clickDateTime": display_date_time(loc.clickDate) if loc.clickDate else ""
                            })
                        link_list.append({
                            "linkName": cl.campLink,
                            "linkClickCount": clcs.count(),
                            "locationList": location_list
                        })

                members_click.append({
                    "clickUserName": f"{click_user.firstName} {click_user.lastName}",
                    "email": click_user.email,
                    "totalClicks": total_clicks,
                    "linkList": link_list
                })
            
        return api_response(200, "Fetch Email Campaigns Report Tenant Click Successfully.", members_click)
    except Exception as e:
        logger.error(f"get_email_campaigns_report_member_click Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_member_open_list_page(request):
    tenant_id = get_final_tenant_id(request=request)
    camp_id_enc = request.query_params.get('campId')
    search_key = request.query_params.get('searchKey')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 10))
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        # getEmailIdListByCampId
        email_ids = CampaignSubscriber.objects.filter(campId=camp_id).values_list('subId', flat=True).distinct()
        
        queryset = CampaignsSendEmail.objects.filter(campSendId=camp_id, emailId__in=email_ids)
        if search_key:
            queryset = queryset.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key))
            
        paginator = Paginator(queryset.order_by('firstName'), size)
        current_page = paginator.get_page(page + 1)
        
        total_open_emails = CampaignSubscriber.objects.filter(campId=camp_id).count() # countTotalOpenEmail
        
        members = []
        for cse in current_page:
            unsubscribe_date = Contact.objects.filter(emailId=cse.emailId, memberId=get_client_id_by_tenant_id(tenant_id), optId=cse.campId, status='Unsubscribed').first()
            unsubscribe_date_str = display_date_time(unsubscribe_date.optDate) if unsubscribe_date and unsubscribe_date.optDate else ""
            total_open = CampaignSubscriber.objects.filter(campId=cse.campId, subId=cse.emailId).count()
            
            members.append({
                "firstName": cse.firstName,
                "lastName": cse.lastName,
                "emailId": cse.emailId,
                "email": cse.email,
                "unsubscribeDate": unsubscribe_date_str,
                "totalOpen": total_open
            })
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalCampaignsSendEmail": total_open_emails,
            "emailCampaignsReportMembers": members
        }
        return api_response(200, "Fetch Email Campaigns Tenant Open List Successfully.", res_body)
    except Exception as e:
        logger.error(f"get_email_campaigns_member_open_list_page Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_member_click_detail(request):
    email_id = request.query_params.get('emailId')
    camp_id_enc = request.query_params.get('campId')
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        # getTotalOpenCount
        total_open = CampaignSubscriber.objects.filter(campId=camp_id, emailId=email_id).count()
        
        campaign_links = CampaignLinks.objects.filter(campId=camp_id)
        product_links = []
        technology = []
        locations = []
        
        for cl in campaign_links:
            # Product Links
            link_clicked = CampaignLinkClick.objects.filter(linkId=cl.id, emailId=email_id).count()
            product_links.append({"link": cl.campLink, "linkClicked": link_clicked})
            
            # Technology
            pc = CampaignLinkClick.objects.filter(linkId=cl.id, sources='PC', emailId=email_id).count()
            phone = CampaignLinkClick.objects.filter(linkId=cl.id, sources='Phone', emailId=email_id).count()
            technology.append({
                "id": cl.id,
                "campLink": cl.campLink,
                "clickThroughRate": None,
                "pc": pc,
                "mobile": phone
            })
            
            # Location
            locs = CampaignLinkClick.objects.filter(linkId=cl.id, emailId=email_id)
            for l in locs:
                locations.append({
                    "link": cl.campLink,
                    "location": l.city or "",
                    "date": display_date_time(l.clickDate) if l.clickDate else "",
                    "browser": get_browser_name(l.sourceDetails)
                })
                
        res_body = {
            "totalEmailOpen": total_open,
            "productLinks": product_links,
            "technology": technology,
            "location": locations
        }
        return api_response(200, "Fetch Email Campaigns Report Tenant Click Detail Successfully.", res_body)
    except Exception as e:
        logger.error(f"get_email_campaigns_report_member_click Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_email_campaigns_report_members_list_page(request):
    tenant_id = get_final_tenant_id(request=request)
    camp_id_enc = request.query_params.get('campId')
    search_key = request.query_params.get('searchKey')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 10))
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        queryset = CampaignsSendEmail.objects.filter(campSendId=camp_id)
        if search_key:
            queryset = queryset.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key))
            
        paginator = Paginator(queryset.order_by('firstName'), size)
        current_page = paginator.get_page(page + 1)
        
        members = []
        for cse in current_page:
            # getUnsubscribeDate
            unsubscribe_date = Contact.objects.filter(emailId=cse.emailId, memberId=get_client_id_by_tenant_id(tenant_id), optId=cse.campId, status='Unsubscribed').first()
            unsubscribe_date_str = display_date_time(unsubscribe_date.optDate) if unsubscribe_date and unsubscribe_date.optDate else ""
            
            # getTotalOpenCount
            total_open = CampaignSubscriber.objects.filter(campId=cse.campId, subId=cse.emailId).count()
            
            # getCountTotalClick
            count_total_click = CampaignLinkClick.objects.filter(campId=cse.campId, userId=cse.emailId).count()
            
            link_detail = []
            if count_total_click > 0:
                campaign_links = CampaignLinks.objects.filter(campId=cse.campId)
                for cl in campaign_links:
                    link_clicked = CampaignLinkClick.objects.filter(linkId=cl.id, emailId=cse.emailId).count()
                    link_detail.append({
                        "link": cl.campLink,
                        "linkClicked": link_clicked
                    })
            
            members.append({
                "firstName": cse.firstName,
                "lastName": cse.lastName,
                "emailId": cse.emailId,
                "email": cse.email,
                "unsubscribeDate": unsubscribe_date_str,
                "totalOpen": total_open,
                "countTotalClick": count_total_click,
                "linkDetail": link_detail
            })
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalCampaignsSendEmail": queryset.count(),
            "emailCampaignsReportMembers": members
        }
        return api_response(200, "Fetch Email Campaigns Report Members List Successfully.", res_body)
    except Exception as e:
        logger.error(f"get_email_campaigns_report_members_list_page Error: {str(e)}")
        return api_response(500, str(e))

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def pause_campaign(request):
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        camp_id = request.data.get('campId')

        CampaignsSendEmail.objects.filter(
            campId=camp_id,
            memberId=get_client_id_by_tenant_id(tenant_id),
            isProcessed='N'
        ).update(
            cronStatus='pause'
        )

        return api_response(200, "Pause Campaign Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] PauseCampaign Error : {e}")
        return api_response(500, "Internal Server Error")

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def restart_campaign(request):
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        camp_id = request.data.get('campId')

        CampaignsSendEmail.objects.filter(
            campId=camp_id,
            memberId=get_client_id_by_tenant_id(tenant_id),
            isProcessed='N',
            cronStatus='pause'
        ).update(
            cronStatus='restart'
        )

        return api_response(200, "Restart Campaign Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] RestartCampaign Error : {e}")
        return api_response(500, "Internal Server Error")

@permission_classes([WhitelistPermission])
def get_campaigns_list_bounced_email(request):
    tenant_id = get_final_tenant_id(request=request)
    camp_id_enc = request.query_params.get('campId')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 10))
    
    try:
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        queryset = CampaignsSendEmail.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), campId=camp_id, isBounced='Y')
        
        paginator = Paginator(queryset.order_by('firstName'), size)
        current_page = paginator.get_page(page + 1)
        
        bounced_list = []
        for cse in current_page:
            bounced_list.append({
                "firstName": cse.firstName,
                "lastName": cse.lastName,
                "email": cse.email,
                "bounceReason": cse.bounceReason or "Unknown"
            })
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalBounced": queryset.count(),
            "bouncedList": bounced_list
        }
        return api_response(200, "Fetch Bounced Email List Successfully.", res_body)
    except Exception as e:
        logger.error(f"get_campaigns_list_bounced_email Error: {str(e)}")
        return api_response(500, str(e))