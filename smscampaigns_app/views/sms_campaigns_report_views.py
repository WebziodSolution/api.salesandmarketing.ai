import logging
from django.db.models import Q
from django.core.paginator import Paginator
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.models import (CampaignsSmsSend, CampaignSendSms, Userlist, CampaignSmsReply, SmsLinks, SmsLinkTrace)
from common_app.utils import (api_response, get_final_tenant_id, display_date, display_date_time, get_client_id_by_tenant_id)
from common_app.decrypt_string import DecryptString
import requests
from collections import Counter

logger = logging.getLogger(__name__)

# Helper to capitalize first letter
def uc_first(string):
    if not string:
        return ""
    return string[0].upper() + string[1:]

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_report_list_page(request):
    """
    Get a paginated list of SMS campaign reports.
    """
    member_id = get_final_tenant_id(request=request)
    id_param = request.GET.get('id')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    res_body = {}
    try:
        query = Q(memberId=get_client_id_by_tenant_id(member_id), smsId=id_param)
        if search_key:
            query &= Q(smsName__icontains=search_key)
        
        campaigns_list = CampaignsSmsSend.objects.filter(query).order_by('-id')
        paginator = Paginator(campaigns_list, size)
        current_page = paginator.get_page(page + 1)

        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['totalSmsCampaigns'] = campaigns_list.count()

        lst = []
        for campaign in current_page:
            # Replicating Java DTO construction
            dto = {
                'encId': DecryptString.set_enc_dec_user(str(campaign.id), "", "Y"),
                'smsId': campaign.smsId,
                'sendDate': display_date_time(campaign.sendDate) if campaign.sendDate else None,
                'smsName': campaign.smsName,
            }
            phone_number = CampaignSendSms.objects.filter(smsId=campaign.id, memberId=get_client_id_by_tenant_id(member_id)).values_list('fromContact', flat=True).first()
            dto['phoneNumber'] = phone_number if phone_number else ""
            lst.append(dto)
        res_body['smsCampaignsReportList'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportListPage Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_report_dashboard(request):
    """
    Get a dashboard report for an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')
    sms_id = request.GET.get('smsId')

    res_body = {}
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        # Java logic: findByIdAndSmsIdAndMemberId (returns smsName)
        campaign_send = CampaignsSmsSend.objects.filter(id=cssd_id, smsId=sms_id, memberId=get_client_id_by_tenant_id(member_id)).first()
        sms_name = campaign_send.smsName if campaign_send else ""

        # Java logic: findTotalSent
        total_sent = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y').count()
        
        # Java logic: findTotalSentDelivered
        total_delivered = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y', smsStatus='delivered').count()
        
        # Java logic: findTotalTextSentDelivered
        total_text_delivered = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y', smsStatus='delivered', cssdType='sms').count()
        
        # Java logic: findTotalMmsSentDelivered
        total_mms_delivered = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y', smsStatus='delivered', cssdType='mms').count()
        
        # Java logic: findTotalNotSent (failed or NULL)
        total_not_sent = CampaignSendSms.objects.filter(
            Q(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y') &
            (Q(smsStatus='failed') | Q(smsStatus__isnull=True))
        ).count()
        
        # Java logic: findTotalMember (group by emailId)
        total_recipients = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y').values('emailId').distinct().count()

        # Java logic: totalSentUndelivered = totalSent - totalSentDelivered - totalNotSent
        total_sent_undelivered = total_sent - total_delivered - total_not_sent
        
        total_sent_percent = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
        total_undelivered_percent = (total_sent_undelivered / total_sent * 100) if total_sent > 0 else 0.0
        total_not_sent_percent = (total_not_sent / total_sent * 100) if total_sent > 0 else 0.0

        res_body['smsName'] = sms_name
        res_body['recipients'] = total_recipients
        res_body['successFulDeliveriesData'] = {
            "totalCount": total_delivered,
            "smsCount": total_text_delivered,
            "mmsCount": total_mms_delivered,
            "percentage": total_sent_percent
        }
        res_body['unDeliveredData'] = {
            "count": max(0, total_sent_undelivered),
            "percentage": max(0, total_undelivered_percent)
        }
        res_body['notSentData'] = {
            "count": total_not_sent,
            "percentage": total_not_sent_percent
        }

    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportDashboard Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Dashboard Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_sms_reports_deliveries_data(request):
    """
    Get SMS delivery reports for an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    res_body = {}
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        query = Q(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), cssdType='sms', smsStatus='delivered')
        if search_key:
            email_ids = Userlist.objects.filter(
                Q(memberId=get_client_id_by_tenant_id(member_id)) &
                (Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=search_key) | Q(phoneNumber__icontains=search_key))
            ).values_list('emailId', flat=True)
            query &= Q(emailId__in=email_ids)

        deliveries_list = CampaignSendSms.objects.filter(query).order_by('-id')
        paginator = Paginator(deliveries_list, size)
        current_page = paginator.get_page(page + 1)

        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['totalSmsDeliveries'] = deliveries_list.count()

        lst = []
        for data in current_page:
            temp = {
                "contact": data.toContact,
                "date": display_date(data.smsSendDate) if data.smsSendDate else "",
                "errorMessage": data.errorMessage or ""
            }
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=data.emailId)
                temp["firstName"] = uc_first(user.firstName)
                temp["lastName"] = uc_first(user.lastName)
            except Userlist.DoesNotExist:
                temp["firstName"] = ""
                temp["lastName"] = ""
            lst.append(temp)

        res_body['smsDeliveriesData'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsSmsReportsDeliveriesData Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Deliveries SMS Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_mms_reports_deliveries_data(request):
    """
    Get MMS delivery reports for an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    res_body = {}
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        query = Q(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), cssdType='mms', smsStatus='delivered')
        if search_key:
            email_ids = Userlist.objects.filter(
                Q(memberId=get_client_id_by_tenant_id(member_id)) &
                (Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(emailId__icontains=search_key) | Q(phoneNumber__icontains=search_key))
            ).values_list('emailId', flat=True)
            query &= Q(emailId__in=email_ids)

        deliveries_list = CampaignSendSms.objects.filter(query).order_by('-id')
        paginator = Paginator(deliveries_list, size)
        current_page = paginator.get_page(page + 1)

        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['totalMmsDeliveries'] = deliveries_list.count()

        lst = []
        for data in current_page:
            temp = {
                "contact": data.toContact,
                "date": display_date(data.smsSendDate) if data.smsSendDate else "",
                "errorMessage": data.errorMessage or ""
            }
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=data.emailId)
                temp["firstName"] = uc_first(user.firstName)
                temp["lastName"] = uc_first(user.lastName)
            except Userlist.DoesNotExist:
                temp["firstName"] = ""
                temp["lastName"] = ""
            lst.append(temp)

        res_body['mmsDeliveriesData'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsMmsReportsDeliveriesData Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Deliveries MMS Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_reports_undelivered_data(request):
    """
    Get undelivered SMS reports for an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    res_body = {}
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        # Java logic: getUndeliveredSmsData
        # smsStatus NOT IN ('failed','delivered') and smsStatus not like '' and smsStatus IS NOT NULL
        query = (
            Q(smsId=cssd_id, memberId=member_id, isSend='Y') & 
            ~Q(smsStatus='delivered') & 
            ~Q(smsStatus='failed') & 
            ~Q(smsStatus='') & 
            Q(smsStatus__isnull=False)
        )
        
        if search_key:
            email_ids = Userlist.objects.filter(
                Q(memberId=get_client_id_by_tenant_id(member_id)) &
                (Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(emailId__icontains=search_key) | Q(phoneNumber__icontains=search_key))
            ).values_list('emailId', flat=True)
            query &= Q(emailId__in=email_ids)

        undelivered_list = CampaignSendSms.objects.filter(query).order_by('-id')
        paginator = Paginator(undelivered_list, size)
        current_page = paginator.get_page(page + 1)

        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['totalUndeliveredSms'] = undelivered_list.count()

        lst = []
        for data in current_page:
            temp = {
                "contact": data.toContact,
                "date": display_date(data.smsSendDate) if data.smsSendDate else "",
                "errorMessage": data.errorMessage or "Not Send Due To SMS Gateway Error"
            }
            try:
                user = Userlist.objects.get(memberId=member_id, emailId=data.emailId)
                temp["firstName"] = uc_first(user.firstName)
                temp["lastName"] = uc_first(user.lastName)
            except Userlist.DoesNotExist:
                temp["firstName"] = ""
                temp["lastName"] = ""
            lst.append(temp)

        res_body['unDeliveredSmsData'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportsUndeliveredData Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Undelivered SMS Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_reports_not_sent_data(request):
    """
    Get not sent SMS reports for an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    res_body = {}
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        # Java logic: getNotSentSmsData
        # isSend='Y' and (smsStatus='failed' or smsStatus IS NULL)
        query = Q(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y') & (Q(smsStatus='failed') | Q(smsStatus__isnull=True))
        if search_key:
            email_ids = Userlist.objects.filter(
                Q(memberId=get_client_id_by_tenant_id(member_id)) &
                (Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(emailId__icontains=search_key) | Q(phoneNumber__icontains=search_key))
            ).values_list('emailId', flat=True)
            query &= Q(emailId__in=email_ids)

        not_sent_list = CampaignSendSms.objects.filter(query).order_by('-id')
        paginator = Paginator(not_sent_list, size)
        current_page = paginator.get_page(page + 1)

        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['totalNotSentSms'] = not_sent_list.count()

        lst = []
        for data in current_page:
            temp = {
                "contact": data.toContact,
                "date": display_date(data.smsSendDate) if data.smsSendDate else "",
                "errorMessage": data.errorMessage or "Not Send Due To SMS Gateway Error"
            }
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=data.emailId)
                temp["firstName"] = uc_first(user.firstName)
                temp["lastName"] = uc_first(user.lastName)
            except Userlist.DoesNotExist:
                temp["firstName"] = ""
                temp["lastName"] = ""
            lst.append(temp)

        res_body['notSentSmsData'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportsNotSentData Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Not Sent SMS Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_report_replies_data(request):
    """
    Get SMS campaign replies reports.
    """
    member_id = get_final_tenant_id(request=request)
    sms_id_param = request.GET.get('smsId') # Original SMS ID? Java uses smsId for reply lookup
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    res_body = {}
    try:
        query = Q(crSmsId=sms_id_param, crMemberId=get_client_id_by_tenant_id(member_id))
        if search_key:
            email_ids = Userlist.objects.filter(
                Q(memberId=get_client_id_by_tenant_id(member_id)) &
                (Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(emailId__icontains=search_key) | Q(phoneNumber__icontains=search_key))
            ).values_list('emailId', flat=True)
            query &= Q(crEmailId__in=email_ids)

        replies_list = CampaignSmsReply.objects.filter(query).order_by('-crId')
        paginator = Paginator(replies_list, size)
        current_page = paginator.get_page(page + 1)

        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['totalRepliesSms'] = replies_list.count()

        lst = []
        for data in current_page:
            temp = {
                "contact": data.crReplyNo,
                "date": display_date(data.crDate) if data.crDate else "",
                "details": data.crReply
            }
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=data.crEmailId)
                temp["firstName"] = uc_first(user.firstName)
                temp["lastName"] = uc_first(user.lastName)
            except Userlist.DoesNotExist:
                temp["firstName"] = ""
                temp["lastName"] = ""
            lst.append(temp)

        res_body['repliesSms'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportRepliesData Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Replies SMS Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_reports_unsubscribed_data(request):
    """
    Get reports for unsubscribed SMS recipients in an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')
    sms_id = request.GET.get('smsId')

    res_body = {}
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        sent_list = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y')
        
        lst = []
        for sent in sent_list:
            user = Userlist.objects.filter(emailId=sent.emailId, memberId=get_client_id_by_tenant_id(member_id), smsStatus='Unsubscribed', smsSid=sms_id).first()
            if user:
                temp = {
                    "firstName": uc_first(user.firstName),
                    "lastName": uc_first(user.lastName),
                    "date": display_date(user.optDate) if user.optDate else "",
                    "contact": sent.toContact
                }
                lst.append(temp)

        res_body['unsubscribedData'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportsUnsubscribedData Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Unsubscribed SMS Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_reports_links_data(request):
    """
    Get reports for links in an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')

    res_body = dict()
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        links = SmsLinks.objects.filter(smsId=cssd_id)
        
        lst = []
        for link in links:
            temp = {
                "linkName": link.smsLink,
                "mainLink": link.smsOrgLink,
                "linkCount": link.linkCount,
                "encLinkId": DecryptString.set_enc_dec_user(str(link.id), "", "Y")
            }
            lst.append(temp)

        res_body['linksData'] = lst
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportsLinksData Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Undelivered SMS Report Fetched Successfully", res_body) # Java message says undelivered? following Java.

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_reports_links_data_details(request):
    """
    Get detailed information about a specific link in an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    enc_link_id = request.GET.get('encLinkId')

    res_body = {}
    try:
        link_id = int(DecryptString.set_enc_dec_user(enc_link_id, "display", "Y"))
        link_data = SmsLinks.objects.get(id=link_id)
        
        res_body['linkName'] = link_data.smsLink
        res_body['mainLink'] = link_data.smsOrgLink
        
        traces = SmsLinkTrace.objects.filter(smsLinkId=link_id)
        
        macintosh = 0
        windows = 0
        ipad = 0
        iphone = 0
        android = 0
        android_tab = 0
        mobile_other = 0
        pc_other = 0
        
        regions = []
        
        for trace in traces:
            # Strip slashes is simplified here
            content = (trace.linkArray or "").replace("\\", "")
            pairs = content.split("~~")
            user_agent = ""
            remote_addr = ""
            
            for pair in pairs:
                if "=>" in pair:
                    k, v = pair.split("=>", 1)
                    if k == "HTTP_USER_AGENT":
                        user_agent = v
                    elif k == "REMOTE_ADDR":
                        remote_addr = v
            
            if user_agent:
                if "Macintosh" in user_agent:
                    macintosh += 1
                elif "Windows" in user_agent:
                    windows += 1
                elif "iPad" in user_agent:
                    ipad += 1
                elif "iPhone" in user_agent:
                    iphone += 1
                elif "tablet" in user_agent:
                    android_tab += 1
                elif "Android" in user_agent:
                    android += 1
                elif "AppleWebKit" in user_agent:
                    mobile_other += 1
                else:
                    pc_other += 1

            if remote_addr:
                try:
                    # In real scenario, might need to cache this
                    resp = requests.get(f"http://ip-api.com/json/{remote_addr}", timeout=2)
                    if resp.status_code == 200:
                        data = resp.json()
                        regions.append(f"{data.get('city')}, {data.get('regionName')}, {data.get('country')}")
                except Exception:
                    pass
        
        res_body.update({
            "desktopTotal": macintosh + windows + pc_other,
            "mobileTotal": android + iphone + mobile_other,
            "tabletTotal": ipad + android_tab,
            "macintosh": macintosh,
            "windows": windows,
            "iPad": ipad,
            "iPhone": iphone,
            "android": android,
            "androidTab": android_tab,
            "mobileOther": mobile_other,
            "pcOther": pc_other,
        })
        
        res_body['regionData'] = dict(Counter(regions))

    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportsLinksDataDetails Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Undelivered SMS Report Fetched Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_campaigns_report_data_for_pdf(request):
    """
    Get data for generating a PDF report for an SMS campaign.
    """
    member_id = get_final_tenant_id(request=request)
    cs_id_enc = request.GET.get('csId')
    sms_id_param = request.GET.get('smsId')

    res_body = {}
    try:
        cssd_id = int(DecryptString.set_enc_dec_user(cs_id_enc, "display", "Y"))
        
        campaign_send = CampaignsSmsSend.objects.filter(id=cssd_id, smsId=sms_id_param, memberId=get_client_id_by_tenant_id(member_id)).first()
        res_body['smsName'] = campaign_send.smsName if campaign_send else ""

        # SMS Deliveries
        sms_del = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), cssdType='sms', smsStatus='delivered')
        lst = []
        for d in sms_del:
            temp = {"contact": d.toContact, "date": display_date(d.smsSendDate) if d.smsSendDate else "", "errorMessage": d.errorMessage or ""}
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=d.emailId)
                temp.update({"firstName": uc_first(user.firstName), "lastName": uc_first(user.lastName)})
            except Userlist.DoesNotExist:
                temp.update({"firstName": "", "lastName": ""})
            lst.append(temp)
        res_body['smsDeliveriesData'] = lst

        # MMS Deliveries
        mms_del = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), cssdType='mms', smsStatus='delivered')
        lst = []
        for d in mms_del:
            temp = {"contact": d.toContact, "date": display_date(d.smsSendDate) if d.smsSendDate else "", "errorMessage": d.errorMessage or ""}
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=d.emailId)
                temp.update({"firstName": uc_first(user.firstName), "lastName": uc_first(user.lastName)})
            except Userlist.DoesNotExist:
                temp.update({"firstName": "", "lastName": ""})
            lst.append(temp)
        res_body['mmsDeliveriesData'] = lst

        # Undelivered (Align with Java logic)
        undel = CampaignSendSms.objects.filter(
            Q(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y') &
            ~Q(smsStatus='delivered') & 
            ~Q(smsStatus='failed') & 
            ~Q(smsStatus='') & 
            Q(smsStatus__isnull=False)
        )
        lst = []
        for d in undel:
            temp = {"contact": d.toContact, "date": display_date(d.smsSendDate) if d.smsSendDate else "", "errorMessage": d.errorMessage or ""}
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=d.emailId)
                temp.update({"firstName": uc_first(user.firstName), "lastName": uc_first(user.lastName)})
            except Userlist.DoesNotExist:
                temp.update({"firstName": "", "lastName": ""})
            lst.append(temp)
        res_body['unDeliveredSmsData'] = lst

        # Not Sent (Align with Java logic)
        notsent = CampaignSendSms.objects.filter(
            Q(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y') &
            (Q(smsStatus='failed') | Q(smsStatus__isnull=True))
        )
        lst = []
        for d in notsent:
            temp = {"contact": d.toContact, "date": display_date(d.smsSendDate) if d.smsSendDate else "", "errorMessage": d.errorMessage or ""}
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=d.emailId)
                temp.update({"firstName": uc_first(user.firstName), "lastName": uc_first(user.lastName)})
            except Userlist.DoesNotExist:
                temp.update({"firstName": "", "lastName": ""})
            lst.append(temp)
        res_body['notSentSmsData'] = lst

        # Replies
        replies = CampaignSmsReply.objects.filter(crSmsId=sms_id_param, crMemberId=get_client_id_by_tenant_id(member_id))
        lst = []
        for d in replies:
            temp = {"contact": d.crReplyNo, "date": display_date(d.crDate) if d.crDate else "", "details": d.crReply}
            try:
                user = Userlist.objects.get(memberId=get_client_id_by_tenant_id(member_id), emailId=d.crEmailId)
                temp.update({"firstName": uc_first(user.firstName), "lastName": uc_first(user.lastName)})
            except Userlist.DoesNotExist:
                temp.update({"firstName": "", "lastName": ""})
            lst.append(temp)
        res_body['repliesSms'] = lst

        # Unsubscribed
        sent_list = CampaignSendSms.objects.filter(smsId=cssd_id, memberId=get_client_id_by_tenant_id(member_id), isSend='Y')
        lst = []
        for s in sent_list:
            u = Userlist.objects.filter(emailId=s.emailId, memberId=get_client_id_by_tenant_id(member_id), smsStatus='Unsubscribed', smsSid=sms_id_param).first()
            if u:
                lst.append({"firstName": uc_first(u.firstName), "lastName": uc_first(u.lastName), "date": display_date(u.optDate) if u.optDate else "", "contact": s.toContact})
        res_body['unsubscribedData'] = lst

        # Links
        links = SmsLinks.objects.filter(smsId=cssd_id)
        lst = []
        for l in links:
            lst.append({"linkName": l.smsLink, "mainLink": l.smsOrgLink, "linkCount": l.linkCount})
        res_body['linksData'] = lst

    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSmsCampaignsReportDataForPdf Error: {e}")
        return api_response(500, "Error", res_body)

    return api_response(200, "SMS Campaigns Report Fetched Successfully", res_body)
