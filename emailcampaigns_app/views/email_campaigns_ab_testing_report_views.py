import logging
import base64
import math
import json
from emailcampaigns_app.views.email_campaigns_report_views import with_oracle_db
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from common_app.models import (CampaignsEmailSend, CampaignLinks, CampaignLinkClick, CampaignSubscriber, Groups, MyPages, CampaignsSendEmail, SmtpServer, Contact, CampaignsEmail)
from django.db import connection
from common_app.utils import api_response, get_final_tenant_id, display_date_time, convert_event_timezone_to_user, \
    get_client_id_by_tenant_id, get_tenant_id_by_client_id, get_browser_name
from common_app.decrypt_string import DecryptString
from django.core.paginator import Paginator
from common_app.services import CommonServices

logger = logging.getLogger(__name__)

def get_dashboard_data(camp_id_param, split_group, campaigns_email_send, time_zone, winner=""):
    dash = {}
    q_filter = Q(campId=camp_id_param) | Q(campSendId=camp_id_param)
    sent = CampaignsSendEmail.objects.filter(q_filter, splitGroup=split_group).count()
    deliveries = CampaignsSendEmail.objects.filter(q_filter, splitGroup=split_group, isSend='Y', isBounced='N').count()
    exception = CampaignsSendEmail.objects.filter(q_filter, splitGroup=split_group, isSend='Y', isBounced__in=['E', 'D']).count()
    opened = CampaignsSendEmail.objects.filter(q_filter, splitGroup=split_group, isRead='Y').count()
    bounced = CampaignsSendEmail.objects.filter(q_filter, splitGroup=split_group, isBounced='Y').count()
    
    # Mirroring findUnsubscribedCountBySplitGroup logic
    unsubscribed = CampaignsSendEmail.objects.filter(q_filter, splitGroup=split_group, isUnsubscribed='Y').count()
    
    unread = deliveries - opened
    successful_deliveries = deliveries
    
    successful_deliveries_per = 0
    if sent > 0:
        successful_deliveries_per = (successful_deliveries / sent) * 100
    
    bounced_per = 0
    if sent > 0:
        bounced_per = (bounced * 100) / sent
        
    unsubscribed_per = 0
    if sent > 0:
        unsubscribed_per = (unsubscribed * 100) / sent
    
    open_rate_per = 0
    if deliveries > 0:
        open_rate_per = (opened * 100) / deliveries
    
    link_count_total = 0
    ui = 0
    total_desktop = 0
    total_mobile = 0
    
    campaign_links = CampaignLinks.objects.filter(campId=camp_id_param, splitGroup=split_group)
    for cl in campaign_links:
        link_count_total += (cl.linkCount or 0)
        total_desktop += CampaignLinkClick.objects.filter(linkId=cl.id, sources='PC').count()
        total_mobile += CampaignLinkClick.objects.filter(linkId=cl.id, sources='Phone').count()
        ui += CampaignLinkClick.objects.filter(linkId=cl.id).values('userId').distinct().count()

    total_click_through_rate_per = 0
    if deliveries > 0:
        total_click_through_rate_per = (link_count_total * 100) / deliveries
    
    unique_click_through_rate_per = 0
    if successful_deliveries > 0:
        unique_click_through_rate_per = (ui * 100) / successful_deliveries

    eff_split_group = split_group
    if split_group == 'O' and winner:
        eff_split_group = winner

    template_name = ""
    try:
        mypage_id = campaigns_email_send.mypageid if eff_split_group == 'A' else getattr(campaigns_email_send, 'mypageidb', campaigns_email_send.mypageid)
        if not mypage_id and eff_split_group != 'A':
             mypage_id = campaigns_email_send.mypageid
        if mypage_id:
            template_name = MyPages.objects.get(mpId=mypage_id).mpName
    except MyPages.DoesNotExist:
        pass

    sent_on = ""
    date_val = campaigns_email_send.sendondate if eff_split_group == 'A' else campaigns_email_send.sendondateb
    if date_val:
        sent_on = convert_event_timezone_to_user(display_date_time(date_val), "UTC", time_zone)

    group_name = ""
    if campaigns_email_send.grouplist:
        try:
            group_ids = campaigns_email_send.grouplist.split(',')
            group = Groups.objects.filter(grpId__in=group_ids).first()
            if group:
                group_name = group.grpGroupName
        except:
            pass

    if split_group == 'O':
        total_queued = getattr(campaigns_email_send, 'total_queued_o', 0)
    elif split_group == 'B':
        total_queued = getattr(campaigns_email_send, 'total_queued_b', 0)
    else:
        total_queued = getattr(campaigns_email_send, 'total_queued', 0)

    dash.update({
        "totalQueued": total_queued,
        "sentOn": sent_on,
        "mailingGroup": group_name,
        "subject": campaigns_email_send.subject if eff_split_group == 'A' or (eff_split_group == 'B' and campaigns_email_send.testing_type in [2, 3, 6]) else campaigns_email_send.subjectb,
        "senderName": campaigns_email_send.from_name if eff_split_group == 'A' else campaigns_email_send.from_name_b,
        "senderEmail": campaigns_email_send.from_add,
        "sent": sent,
        "delivered": deliveries,
        "exception": exception,
        "opened": opened,
        "bounced": bounced,
        "unread": unread,
        "totalDesktop": total_desktop,
        "totalMobile": total_mobile,
        "successfulDeliveries": successful_deliveries,
        "successfulDeliveriesPer": successful_deliveries_per,
        "bouncedPer": bounced_per,
        "unsubscribed": unsubscribed,
        "unsubscribedPer": unsubscribed_per,
        "openRatePer": open_rate_per,
        "totalClickThroughRate": link_count_total,
        "totalClickThroughRatePer": total_click_through_rate_per,
        "uniqueClickThroughRate": ui,
        "uniqueClickThroughRatePer": unique_click_through_rate_per,
        "templateName": template_name
    })
    return dash

def print_product_link(dec_camp_id, split_group):
    total_recept = CampaignsSendEmail.objects.filter(campId=dec_camp_id, splitGroup=split_group, isSend='Y').count()
    links = CampaignLinks.objects.filter(campId=dec_camp_id, splitGroup=split_group)
    
    res_list = []
    for l in links:
        uc = CampaignLinkClick.objects.filter(linkId=l.id).values('userId').distinct().count()
        click_through = 0
        if total_recept > 0:
            click_through = (l.linkCount / total_recept) * 100
        
        res_list.append({
            "id": l.id,
            "campLink": l.campLink,
            "uniqueClicks": uc,
            "totalClicks": l.linkCount,
            "clickThroughRate": click_through
        })
    return res_list

def print_members(dec_camp_id, split_group, final_member_id):
    queryset = CampaignsSendEmail.objects.filter(campSendId=dec_camp_id, splitGroup=split_group)
    members = []
    for m in queryset:
        total_open = CampaignSubscriber.objects.filter(campId=dec_camp_id, subId=m.emailId).count()
        
        unsubscribe_date_str = ""
        try:
            contact = Contact.objects.filter(emailId=m.emailId, memberId=get_client_id_by_tenant_id(final_member_id), status='Unsubscribed', optId=dec_camp_id).first()
            if contact and contact.optDate:
                unsubscribe_date_str = display_date_time(contact.optDate)
        except Exception as e:
            logger.error(f"Error getting unsubscribe date for member {m.emailId}: {e}")

        members.append({
            "firstName": m.firstName,
            "lastName": m.lastName,
            "emailId": m.emailId,
            "email": m.email,
            "unsubscribeDate": unsubscribe_date_str,
            "totalOpen": total_open
        })
    return members

def print_sources(dec_camp_id, split_group):
    links = CampaignLinks.objects.filter(campId=dec_camp_id, splitGroup=split_group)
    res = []
    for l in links:
        pc = CampaignLinkClick.objects.filter(linkId=l.id, sources='PC').count()
        phone = CampaignLinkClick.objects.filter(linkId=l.id, sources='Phone').count()
        res.append({
            "id": l.id,
            "campLink": l.campLink,
            "clickThroughRate": None,
            "pc": pc,
            "mobile": phone
        })
    return res

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportDashboardAB(request):
    camp_id_param = request.GET.get('campId')
    time_zone = request.GET.get('timeZone', 'UTC')

    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        campaigns_email_send = get_object_or_404(CampaignsEmailSend, id=dec_camp_id)
        
        res_body = dict()
        res_body['campName'] = campaigns_email_send.camp_name
        result_tie = campaigns_email_send.result_tie
        res_body['resultTie'] = result_tie if result_tie else None
        res_body['isCompletedAB'] = campaigns_email_send.is_completed_ab
        res_body['byAutoManual'] = campaigns_email_send.byautomanual
        res_body['lastOpened'] = display_date_time(campaigns_email_send.last_opened)

        res_body['winner'] = ""
        win_filter = Q(campSendId=dec_camp_id) | Q(campId=dec_camp_id)
        win_obj = CampaignsSendEmail.objects.filter(win_filter, splitGroup='O').exclude(groupWinner__isnull=True).exclude(groupWinner='').first()
        if win_obj:
            res_body['winner'] = win_obj.groupWinner

        res_body['dashboard'] = get_dashboard_data(dec_camp_id, 'A', campaigns_email_send, time_zone, res_body['winner'])
        res_body['dashboardB'] = get_dashboard_data(dec_camp_id, 'B', campaigns_email_send, time_zone, res_body['winner'])
        res_body['dashboardO'] = get_dashboard_data(dec_camp_id, 'O', campaigns_email_send, time_zone, res_body['winner'])

        return api_response(200, "Email Campaigns Dashboard Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getEmailCampaignsReportDashboardAB error: {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportProductLinksAB(request):
    camp_id_param = request.GET.get('campId')

    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        
        def report_product_links(split_group):
            total_recept = CampaignsSendEmail.objects.filter(campId=dec_camp_id, splitGroup=split_group, isSend='Y').count()
            links = CampaignLinks.objects.filter(campId=dec_camp_id, splitGroup=split_group)
            
            res_list = []
            for l in links:
                uc = CampaignLinkClick.objects.filter(linkId=l.id).values('userId').distinct().count()
                click_through = 0
                if total_recept > 0:
                    click_through = (l.linkCount / total_recept) * 100

                user_details = []
                user_wise = CampaignLinkClick.objects.filter(linkId=l.id).values('userId').annotate(totalClicked=Count('id'))
                for uw in user_wise:
                    user_id = uw['userId']

                    click_user_detail = CampaignsSendEmail.objects.filter(emailId=user_id).first()
                    first_name = ""
                    last_name = ""
                    if click_user_detail:
                        first_name = click_user_detail.firstName or ""
                        last_name = click_user_detail.lastName or ""
                    location_list = []
                    # Equivalent of findDetailByLinkIdAndUserId()
                    click_details = CampaignLinkClick.objects.filter(linkId=l.id, userId=user_id)
                    for click in click_details:
                        click_date = ""
                        if click.clickDate:
                            try:
                                click_date = display_date_time(click.clickDate)
                            except Exception:
                                click_date = ""

                        technology = ""
                        if click.sources == "PC":
                            technology = "Desktop"
                        elif click.sources == "Phone":
                            technology = "Mobile"

                        location_list.append({
                            "location": click.city,
                            "clickDate": click_date,
                            "browser": get_browser_name(click.sourceDetails),
                            "technology": technology
                        })

                    user_details.append({
                        "userId": user_id,
                        "userName": f"{first_name} {last_name}".strip(),
                        "totalClicked": uw['totalClicked'],
                        "locationList": location_list
                    })

                res_list.append({
                    "id": l.id,
                    "campLink": l.campLink,
                    "uniqueClicks": uc,
                    "totalClicks": l.linkCount,
                    "clickThroughRate": click_through,
                    "userDetailList": user_details
                })
            return res_list

        res_body = {
            "productLinks": report_product_links('A'),
            "productLinksB": report_product_links('B'),
            "productLinksO": report_product_links('O')
        }
        return api_response(200, "Email Campaigns Product Links Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getEmailCampaignsReportProductLinksAB error: {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportMembersListPageAB(request):
    camp_id_param = request.GET.get('campId')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        queryset = CampaignsSendEmail.objects.filter(campSendId=dec_camp_id, splitGroup='A')
        if search_key:
            queryset = queryset.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=search_key))
        
        sort_param = request.GET.get('sort')
        order_by_field = 'emailId'
        if sort_param:
            parts = sort_param.split(',')
            if len(parts) >= 2 and parts[1].lower() == 'desc':
                order_by_field = '-' + parts[0]
            else:
                order_by_field = parts[0]
            
        paginator = Paginator(queryset.order_by(order_by_field), size)
        page_obj = paginator.get_page(page + 1)
        
        members = []
        for m in page_obj:
            total_open = CampaignSubscriber.objects.filter(campId=dec_camp_id, subId=m.emailId).count()
            count_total_click = CampaignLinkClick.objects.filter(linkId__in=CampaignLinks.objects.filter(campId=dec_camp_id).values('id'), userId=m.emailId).count()
            
            link_detail = []
            if count_total_click > 0:
                links = CampaignLinks.objects.filter(campId=dec_camp_id, splitGroup='A')
                for l in links:
                    lc = CampaignLinkClick.objects.filter(linkId=l.id, userId=m.emailId).count()
                    link_detail.append({"link": l.campLink, "linkClicked": lc})

            members.append({
                "countTotalClick": count_total_click,
                "email": m.email,
                "emailId": m.emailId,
                "firstName": m.firstName,
                "lastName": m.lastName,
                "linkDetail": link_detail,
                "links": None,
                "phoneNumber": None,
                "smsStatus": None,
                "totalOpen": total_open,
                "unsubscribeDate": ""
            })
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalCampaignsSendEmail": paginator.count,
            "members": members
        }
        return api_response(200, "Email Campaigns Tenant List Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getEmailCampaignsReportMembersListPageAB error: {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportMembersBListPageAB(request):
    camp_id_param = request.GET.get('campId')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        queryset = CampaignsSendEmail.objects.filter(campSendId=dec_camp_id, splitGroup='B')
        if search_key:
            queryset = queryset.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=search_key))
        
        sort_param = request.GET.get('sort')
        order_by_field = 'emailId'
        if sort_param:
            parts = sort_param.split(',')
            if len(parts) >= 2 and parts[1].lower() == 'desc':
                order_by_field = '-' + parts[0]
            else:
                order_by_field = parts[0]
                
        paginator = Paginator(queryset.order_by(order_by_field), size)
        page_obj = paginator.get_page(page + 1)
        
        members = []
        for m in page_obj:
            total_open = CampaignSubscriber.objects.filter(campId=dec_camp_id, subId=m.emailId).count()
            count_total_click = CampaignLinkClick.objects.filter(linkId__in=CampaignLinks.objects.filter(campId=dec_camp_id).values('id'), userId=m.emailId).count()
            
            link_detail = []
            if count_total_click > 0:
                links = CampaignLinks.objects.filter(campId=dec_camp_id, splitGroup='B')
                for l in links:
                    lc = CampaignLinkClick.objects.filter(linkId=l.id, userId=m.emailId).count()
                    link_detail.append({"link": l.campLink, "linkClicked": lc})

            members.append({
                "countTotalClick": count_total_click,
                "email": m.email,
                "emailId": m.emailId,
                "firstName": m.firstName,
                "lastName": m.lastName,
                "linkDetail": link_detail,
                "links": None,
                "phoneNumber": None,
                "smsStatus": None,
                "totalOpen": total_open,
                "unsubscribeDate": ""
            })
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalCampaignsSendEmail": paginator.count,
            "membersB": members
        }
        return api_response(200, "Email Campaigns Tenant List B Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getEmailCampaignsReportMembersBListPageAB error: {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportMembersOListPageAB(request):
    camp_id_param = request.GET.get('campId')
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))

    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        queryset = CampaignsSendEmail.objects.filter(campSendId=dec_camp_id, splitGroup='O')
        if search_key:
            queryset = queryset.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=search_key))
        
        sort_param = request.GET.get('sort')
        order_by_field = 'emailId'
        if sort_param:
            parts = sort_param.split(',')
            if len(parts) >= 2 and parts[1].lower() == 'desc':
                order_by_field = '-' + parts[0]
            else:
                order_by_field = parts[0]
                
        paginator = Paginator(queryset.order_by(order_by_field), size)
        page_obj = paginator.get_page(page + 1)
        
        members = []
        for m in page_obj:
            total_open = CampaignSubscriber.objects.filter(campId=dec_camp_id, subId=m.emailId).count()
            count_total_click = CampaignLinkClick.objects.filter(linkId__in=CampaignLinks.objects.filter(campId=dec_camp_id).values('id'), userId=m.emailId).count()
            
            link_detail = []
            if count_total_click > 0:
                links = CampaignLinks.objects.filter(campId=dec_camp_id, splitGroup='O')
                for l in links:
                    lc = CampaignLinkClick.objects.filter(linkId=l.id, userId=m.emailId).count()
                    link_detail.append({"link": l.campLink, "linkClicked": lc})

            members.append({
                "countTotalClick": count_total_click,
                "email": m.email,
                "emailId": m.emailId,
                "firstName": m.firstName,
                "lastName": m.lastName,
                "linkDetail": link_detail,
                "links": None,
                "phoneNumber": None,
                "smsStatus": None,
                "totalOpen": total_open,
                "unsubscribeDate": ""
            })
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page,
            "getSize": size,
            "totalCampaignsSendEmail": paginator.count,
            "membersO": members
        }
        return api_response(200, "Email Campaigns Tenant List O Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getEmailCampaignsReportMembersOListPageAB error: {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportSourcesAB(request):
    camp_id_param = request.GET.get('campId')

    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        
        def report_sources(split_group):
            links = CampaignLinks.objects.filter(campId=dec_camp_id, splitGroup=split_group)
            res = []
            for l in links:
                pc = CampaignLinkClick.objects.filter(linkId=l.id, sources='PC').count()
                phone = CampaignLinkClick.objects.filter(linkId=l.id, sources='Phone').count()
                res.append({
                    "id": l.id,
                    "campLink": l.campLink,
                    "pc": pc,
                    "mobile": phone
                })
            return res

        res_body = {
            "sourceLinks": report_sources('A'),
            "sourceLinksB": report_sources('B'),
            "sourceLinksO": report_sources('O')
        }
        return api_response(200, "Email Campaigns Product Sources Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getEmailCampaignsReportSourcesAB error: {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getCampaignsReportPrintAB(request):
    camp_id_param = request.GET.get('campId')
    final_member_id = get_final_tenant_id(request=request)
    
    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        
        res_body = {
            "productLinks": print_product_link(dec_camp_id, 'A'),
            "productLinksB": print_product_link(dec_camp_id, 'B'),
            "productLinksWinner": print_product_link(dec_camp_id, 'O'),
            
            "members": print_members(dec_camp_id, 'A', final_member_id),
            "membersB": print_members(dec_camp_id, 'B', final_member_id),
            "membersWinner": print_members(dec_camp_id, 'O', final_member_id),
            
            "sourceLinks": print_sources(dec_camp_id, 'A'),
            "sourceLinksB": print_sources(dec_camp_id, 'B'),
            "sourceLinksWinner": print_sources(dec_camp_id, 'O')
        }
        
        return api_response(200, "Email Campaigns Report Print Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getCampaignsReportPrintAB error: {e}")
        return api_response(500, "Internal Server Error", {})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def setChooseWinner(request):
    data = request.data
    camp_id_enc = data.get('campId')
    winner = data.get('winner')

    final_member_id = get_final_tenant_id(request=request)
    
    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        # 1. SMTP Distribution Setup (Dedicated IPs)
        dedicated_server_name = {}
        smtp_member_list = SmtpServer.objects.filter(isDedicatedIp='Y', memberId__gt=0).values_list('memberId', flat=True).distinct()
        for mem_id in smtp_member_list:
            dedicated_servers = SmtpServer.objects.filter(memberId=mem_id)
            server_names = []
            for ds in dedicated_servers:
                if ds.isActive == 1:
                    server_names.append(ds.serverName)
            if server_names:
                dedicated_server_name[mem_id] = ",".join(server_names)

        # 2. Shared SMTP Server Distribution Setup
        shared_servers = SmtpServer.objects.filter(isActive=1, isDedicatedIp='N')
        server_domain_str = ""
        server_name_map = {}
        server_domain_set = set()
        domain_in_server = {}
        domain_server_in_count = {}

        for server in shared_servers:
            d_names = server.serverDomain.split(",") if server.serverDomain else []
            for d in d_names:
                d = d.strip()
                if d:
                    server_domain_str += f"{d},"
                    server_name_map[server.serverName] = server.serverDomain
                    server_domain_set.add(d)
                    if d not in domain_in_server:
                        domain_in_server[d] = []
                    domain_in_server[d].append(server.serverName)
                    domain_server_in_count[d] = domain_server_in_count.get(d, 0) + 1

        if "others" in server_domain_set:
            server_domain_set.remove("others")

        # 3. Update Campaign Status
        campaigns_email_send = CampaignsEmailSend.objects.filter(id=dec_camp_id).first()
        if not campaigns_email_send:
            return api_response(404, "Email Campaigns Send Record Not Found", {})

        CampaignsEmail.objects.filter(campId=campaigns_email_send.camp_id).update(resultTie=None)
        CampaignsEmailSend.objects.filter(id=dec_camp_id).update(result_tie=None)

        # 4. Handle Winner
        opp_split_group = 'B' if winner == 'A' else 'A'

        with connection.cursor() as cursor:
            cursor.execute("""
                            INSERT INTO CAMPAIGN_LINKS(
                                CL_ID, CL_LINK, CL_LINK_COUNT, CL_SPLIT_GROUP, CL_AUTOMATION_EMAIL_NODE_DETAILS, CL_NODE_ID
                            )
                            SELECT CL_ID, CL_LINK, 0, 'O', CL_AUTOMATION_EMAIL_NODE_DETAILS, CL_NODE_ID
                            FROM CAMPAIGN_LINKS
                            WHERE CL_ID = :dec_camp_id
                              AND CL_SPLIT_GROUP = :split_group
                        """, {
                'dec_camp_id': dec_camp_id,
                'split_group': winner
            })
            

            # selectInsertSendEmailTransfer equivalent logic
            cursor.execute("""
                INSERT INTO CAMPAIGN_EMAIL_SENT(
                    CES_CAMP_ID, CES_SEND_ID, CES_CLIENT_ID, CES_EMAIL_ID, CES_IS_SEND, CES_IS_PROCESSED,
                    CES_FIRST_NAME, CES_LAST_NAME, CES_EMAIL, CES_EMAIL_DOMAIN, CES_CS_DEFAULT_LANGUAGE,
                    CES_SPLIT_GROUP, CES_MSG_PRIORITY
                )
                SELECT CES_CAMP_ID, :CES_SEND_ID, CES_CLIENT_ID, CES_EMAIL_ID, 'N', 'N',
                       CES_FIRST_NAME, CES_LAST_NAME, CES_EMAIL, CES_EMAIL_DOMAIN, CES_CS_DEFAULT_LANGUAGE,
                       'O', CES_MSG_PRIORITY
                FROM CAMPAIGN_EMAIL_SENT
                WHERE CES_SEND_ID = :dec_camp_id 
                  AND CES_SPLIT_GROUP = :CES_SPLIT_GROUP
                  AND (CES_IS_BOUNCED = 'N' OR CES_IS_BOUNCED IS NULL)
            """, {
                'CES_SEND_ID': dec_camp_id,
                'dec_camp_id': dec_camp_id,
                'CES_SPLIT_GROUP': opp_split_group
            })

            cursor.execute("""
                UPDATE CAMPAIGN_EMAIL_SENT 
                SET CES_GROUP_WINNER = :winner
                WHERE CES_SEND_ID = :dec_camp_id AND CES_SPLIT_GROUP = 'O'
            """, {
                'winner': winner,
                'dec_camp_id': dec_camp_id
            })

        # 5. Record Transaction
        # In java it's dec_camp_id used as camp_id/camp_send_id
        member_list_count = CampaignsSendEmail.objects.filter(
            groupWinner=winner, campSendId=dec_camp_id, splitGroup='O'
        ).count()

        country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(campaigns_email_send.member_id))
        
        price_display = 0.0
        price_per = 0.0
        if member_list_count > 0 and country_setting:
            price_per = getattr(country_setting, 'cnty_campaign_per_price', 0) or 0
            price_display = member_list_count * price_per

        CommonServices.saveCampaignTransaction(
            campaigns_email_send.camp_id,
            f"{campaigns_email_send.camp_name}-send winner campaign",
            member_list_count,
            "campaign",
            None,
            "uninvoiced",
            None,
            campaigns_email_send.member_id,
            "0",
            price_display,
            price_per,
            0,
            None,
            None,
            0
        )

        msg = f"{winner} Campaign Is Send To Remain Contacts."

        # 6. Final Updates and SMTP Assignment
        total_queued_o = CampaignsSendEmail.objects.filter(campSendId=dec_camp_id, splitGroup='O').count()
        CampaignsEmailSend.objects.filter(id=dec_camp_id).update(
            total_queued_o=total_queued_o, result_tie=None, readytomail='Y'
        )

        # SMTP Distribution Logic
        d_val_list = list(server_domain_set) or [""]
        mem_id_list = list(smtp_member_list) or [0]

        # Domain "others"
        d_value_total = CampaignsSendEmail.objects.filter(
            campSendId=dec_camp_id, splitGroup='O'
        ).exclude(emailDomain__in=server_domain_set).count()
        
        if d_value_total > 0:
            others_servers = domain_in_server.get("others", [])
            if others_servers:
                d_value_limit = math.ceil(d_value_total / len(others_servers))
                st_point = 0
                for ds_value in others_servers:
                    with connection.cursor() as cursor:
                        d_placeholders = ",".join([f":d{i}" for i in range(len(d_val_list))])
                        m_placeholders = ",".join([f":m{get_client_id_by_tenant_id(i)}" for i in range(len(mem_id_list))])
                        params = {
                            'ds_value': ds_value,
                            'camp_id': dec_camp_id,
                            'st_point': st_point,
                            'd_value_limit': d_value_limit
                        }
                        params.update({f"d{i}": v for i, v in enumerate(d_val_list)})
                        params.update({f"m{get_client_id_by_tenant_id(i)}": v for i, v in enumerate(mem_id_list)})
                        
                        cursor.execute(f"""
                            UPDATE CAMPAIGN_EMAIL_SENT 
                            SET CES_SMTP_SERVER_HOST = :ds_value
                            WHERE CES_ID IN (
                                SELECT CES_ID FROM (
                                    SELECT CES_ID, ROW_NUMBER() OVER (ORDER BY CES_ID) rn 
                                    FROM CAMPAIGN_EMAIL_SENT 
                                    WHERE CES_SEND_ID = :camp_id 
                                      AND CES_EMAIL_DOMAIN NOT IN ({d_placeholders})
                                      AND CES_CLIENT_ID NOT IN ({m_placeholders})
                                      AND CES_SPLIT_GROUP = 'O'
                                ) WHERE rn > :st_point AND rn <= (:st_point + :d_value_limit)
                            )
                        """, params)
                    st_point += d_value_limit

        # Domain specific
        for d_value in server_domain_set:
            d_value_total_1 = CampaignsSendEmail.objects.filter(
                campSendId=dec_camp_id, emailDomain=d_value, splitGroup='O'
            ).count()
            if d_value_total_1 > 0:
                domain_servers = domain_in_server.get(d_value, [])
                if domain_servers:
                    d_value_limit_1 = math.ceil(d_value_total_1 / len(domain_servers))
                    st_point_1 = 0
                    for ds_value in domain_servers:
                        with connection.cursor() as cursor:
                            m_placeholders = ",".join([f":m{get_client_id_by_tenant_id(i)}" for i in range(len(mem_id_list))])
                            params = {
                                'ds_value': ds_value,
                                'camp_id': dec_camp_id,
                                'd_value': d_value,
                                'st_point': st_point_1,
                                'd_value_limit': d_value_limit_1
                            }
                            params.update({f"m{get_client_id_by_tenant_id(i)}": v for i, v in enumerate(mem_id_list)})
                            
                            cursor.execute(f"""
                                UPDATE CAMPAIGN_EMAIL_SENT 
                                SET CES_SMTP_SERVER_HOST = :ds_value
                                WHERE CES_ID IN (
                                    SELECT CES_ID FROM (
                                        SELECT CES_ID, ROW_NUMBER() OVER (ORDER BY CES_ID) rn 
                                        FROM CAMPAIGN_EMAIL_SENT 
                                        WHERE CES_SEND_ID = :camp_id 
                                          AND CES_EMAIL_DOMAIN = :d_value
                                          AND CES_CLIENT_ID NOT IN ({m_placeholders})
                                          AND CES_SPLIT_GROUP = 'O'
                                    ) WHERE rn > :st_point AND rn <= (:st_point + :d_value_limit)
                                )
                            """, params)
                        st_point_1 += d_value_limit_1

        # Dedicated IPs
        for mem_id, ds_value_all in dedicated_server_name.items():
            if mem_id == final_member_id:
                ds_list = ds_value_all.split(",")
                d_value_total_mem = CampaignsSendEmail.objects.filter(
                    campSendId=dec_camp_id, splitGroup='O', memberId=get_client_id_by_tenant_id(mem_id)
                ).count()
                if d_value_total_mem > 0:
                    d_value_limit_mem = math.ceil(d_value_total_mem / len(ds_list))
                    st_point_mem = 0
                    for ds_value in ds_list:
                        with connection.cursor() as cursor:
                            cursor.execute("""
                                UPDATE CAMPAIGN_EMAIL_SENT 
                                SET CES_SMTP_SERVER_HOST = :ds_value
                                WHERE CES_ID IN (
                                    SELECT CES_ID FROM (
                                        SELECT CES_ID, ROW_NUMBER() OVER (ORDER BY CES_ID) rn 
                                        FROM CAMPAIGN_EMAIL_SENT 
                                        WHERE CES_SEND_ID = :camp_id 
                                          AND CES_SPLIT_GROUP = 'O' 
                                          AND CES_CLIENT_ID = :member_id
                                    ) WHERE rn > :st_point AND rn <= (:st_point + :d_value_limit)
                                )
                            """, {
                                'ds_value': ds_value,
                                'camp_id': dec_camp_id,
                                'member_id': get_client_id_by_tenant_id(mem_id),
                                'st_point': st_point_mem,
                                'd_value_limit': d_value_limit_mem
                            })
                        st_point_mem += d_value_limit_mem

        res_body = {"msg": msg}
        return api_response(200, "Winner Set Successfully", res_body)
    except Exception as e:
        logger.error(f"setChooseWinner error: {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportMembersListAB(request):
    camp_id_param = request.GET.get('campId')
    split_group = request.GET.get('splitGroup')

    try:
        dec_camp_id = int(DecryptString.set_enc_dec_user(camp_id_param, "display", "Y"))
        camp_send_email = CampaignsEmailSend.objects.filter(id=dec_camp_id).first()
        camp_name = camp_send_email.camp_name if camp_send_email else ""
        
        queryset = CampaignsSendEmail.objects.filter(campSendId=dec_camp_id, splitGroup=split_group)
        members = []
        for m in queryset:
            members.append({
                "countTotalClick": 0,
                "email": m.email,
                "emailId": m.emailId,
                "firstName": m.firstName,
                "lastName": m.lastName,
                "linkDetail": [],
                "links": None,
                "phoneNumber": None,
                "smsStatus": None,
                "totalOpen": CampaignSubscriber.objects.filter(campId=dec_camp_id, subId=m.emailId).count(),
                "unsubscribeDate": ""
            })
            
        res_body = {
            "campName": camp_name,
            "members": members
        }
        return api_response(200, "Email Campaigns Tenant List Fetched Successfully", res_body)
    except Exception as e:
        return api_response(500, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getEmailCampaignsMemberOpenListPageAB(request, cursor):
    """
    Java: /emailCampaignReport/getEmailCampaignsMemberOpenListPage
    """
    try:
        camp_id_enc = request.query_params.get('campId')
        search_key = request.query_params.get('searchKey', '')
        page_no = int(request.query_params.get('page', 0))
        split_group = request.GET.get('splitGroup')
        page_size = int(request.query_params.get('size', 10))
        filter_type = request.query_params.get('filter', 'opened')  # default 'opened'
        
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        encCampId = DecryptString.set_enc_dec_user(str(camp_id), "", "Y")
            
        # 1. Base subscribers who opened
        email_id_list = list(
            CampaignSubscriber.objects.filter(campId=camp_id)
            .values_list('subId', flat=True)
            .distinct()
        )

        # 2. If filtering by 'visited', pre-filter users with valid link logs in ANALYTICS_EVENTS_LOGS
        if filter_type == 'visited':
            query_users = """
                SELECT DISTINCT JSON_VALUE(DATA, '$.user_id')
                FROM ANALYTICS_EVENTS_LOGS
                WHERE JSON_VALUE(DATA, '$.campaign_id') = :camp_id
                  AND JSON_VALUE(DATA, '$.user_id') IS NOT NULL
                  AND JSON_VALUE(DATA, '$.user_id') != 'unknown'
            """
            cursor.execute(query_users, {"camp_id": encCampId})
            visited_enc_user_ids = [row[0] for row in cursor.fetchall() if row[0]]

            # Decode user_ids back to integer emailId
            visited_sub_ids = []
            for enc_uid in visited_enc_user_ids:
                try:
                    raw_id = base64.b64decode(base64.b64decode(str(enc_uid).encode('utf-8'))).decode('utf-8')
                    visited_sub_ids.append(int(raw_id))
                except Exception:
                    continue

            # Intersect with the original opened subscriber IDs
            email_id_list = list(set(email_id_list).intersection(visited_sub_ids))

        # 3. Build and paginate the SQL queryset
        queryset = CampaignsSendEmail.objects.filter(campSendId=camp_id, splitGroup=split_group, emailId__in=email_id_list)
        if search_key:
            queryset = queryset.filter(
                Q(email__icontains=search_key) | 
                Q(firstName__icontains=search_key) | 
                Q(lastName__icontains=search_key)
            )
            
        paginator = Paginator(queryset.order_by("firstName"), page_size)
        page_obj = paginator.get_page(page_no + 1)
        group_id = CampaignsEmailSend.objects.filter(id=camp_id).values_list('grouplist', flat=True).first()
        
        # 4. Process only items in the current page
        members_list = []
        for item in page_obj:
            total_open = CampaignSubscriber.objects.filter(campId=camp_id, subId=item.emailId).count()
            if total_open > 0:
                encEmailID = base64.b64encode(base64.b64encode(str(item.emailId).encode('utf-8'))).decode('utf-8')
                query_links = """
                    SELECT JSON_QUERY(DATA, '$.log')
                    FROM ANALYTICS_EVENTS_LOGS
                    WHERE JSON_VALUE(DATA, '$.session_id') IN (
                        SELECT DISTINCT JSON_VALUE(DATA, '$.session_id')
                        FROM ANALYTICS_EVENTS_LOGS
                        WHERE JSON_VALUE(DATA, '$.campaign_id') = :camp_id
                          AND JSON_VALUE(DATA, '$.user_id') = :enc_email_id
                    )
                    ORDER BY JSON_VALUE(DATA, '$.timestamp' RETURNING NUMBER) ASC
                """
                cursor.execute(query_links, {"camp_id": encCampId, "enc_email_id": encEmailID})
                rows = cursor.fetchall()
                final_links = []
                for row in rows:
                    log_str = row[0]
                    if hasattr(log_str, 'read'):
                        log_str = log_str.read()
                    logs = json.loads(log_str) if isinstance(log_str, str) else (log_str or [])
                    if isinstance(logs, list):
                        for l in logs:
                            if isinstance(l, dict) and l.get("page_url"):
                                final_links.append(str(l.get("page_url")))

                members_list.append({
                    "firstName": item.firstName,
                    "lastName": item.lastName,
                    "emailId": item.emailId,
                    "email": item.email if item.email else "",
                    "totalOpen": total_open,
                    "links": final_links,
                    "groupId": int(group_id) if group_id is not None else 0
                })

        total_pages = paginator.num_pages
        total_campaigns_send_email = paginator.count

        res_body = {
            "getTotalPages": total_pages,
            "getNumber": page_no,
            "getSize": page_size,
            "emailCampaignsReportMembers": members_list,
            "totalCampaignsSendEmail": total_campaigns_send_email
        }
        
        return api_response(200, "Email Campaigns Tenant Open List Fetched Successfully", res_body)
        
    except Exception as e:
        logger.error(f"getEmailCampaignsMemberOpenListPage Error: {e}")
        return api_response(500, "Internal Server Error")

