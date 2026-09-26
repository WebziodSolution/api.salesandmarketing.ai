import logging
import base64
import json
from django.db import connection
from django.db.models import Q, Count
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from django.core.paginator import Paginator
from common_app.models import (CampaignsEmailSend, CampaignLinks, CampaignLinkClick, CampaignSubscriber, Userlist, Contact, MyPages, Groups, CampaignsSendEmail)
from common_app.decrypt_string import DecryptString
from common_app.utils import api_response, display_date_time, convert_event_timezone_to_user, get_final_tenant_id, get_browser_name, get_client_id_by_tenant_id

logger = logging.getLogger(__name__)

def with_oracle_db(view_func):
    """Decorator to inject Oracle DB cursor into the view."""
    def _wrapped_view(request, *args, **kwargs):
        try:
            connection.ensure_connection()
            raw_conn = connection.connection
            with raw_conn.cursor() as cursor:
                return view_func(request, cursor, *args, **kwargs)
        except Exception as e:
            logger.error(f"{view_func.__name__} error: {str(e)}")
            return api_response(500, str(e), {})
    _wrapped_view.__name__ = view_func.__name__
    return _wrapped_view


# --- Helper Functions ---

def get_total_campaigns_email_send(final_member_id, camp_id):
    try:
        return CampaignsEmailSend.objects.filter(member_id=get_client_id_by_tenant_id(final_member_id), camp_id=camp_id).count()
    except Exception:
        return 0

# --- Views ---

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportListPage(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportListPage
    """
    try:
        # finalMemberId = CommonFunction.getFinalMemberId(member)
        # Note: In our system request.user is already the member
        final_member_id = get_final_tenant_id(request=request)
        id_param = request.query_params.get('id')
        search_key = request.query_params.get('searchKey', '')
        time_zone = request.query_params.get('timeZone', 'UTC')
        
        page_no = int(request.query_params.get('page', 0))
        page_size = int(request.query_params.get('size', 10))
        
        queryset = CampaignsEmailSend.objects.filter(member_id=get_client_id_by_tenant_id(final_member_id), camp_id=id_param).order_by('-id')
        if search_key:
            queryset = queryset.filter(Q(camp_name__icontains=search_key))
            
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page_no + 1)
        
        total_campaigns_email_send = get_total_campaigns_email_send(final_member_id, id_param)
        
        report_list = []
        for item in page_obj:
            report_item = {
                "campName": item.camp_name,
                "campId": item.id,
                "encCampId": DecryptString.set_enc_dec_user(str(item.id), "", "Y"),
            }
            if item.camp_main_type:
                report_item["campMainType"] = item.camp_main_type
                
            if item.send_date:
                report_item["createdOn"] = display_date_time(item.send_date)
                
            if item.sendondate:
                report_item["sendOnDate"] = convert_event_timezone_to_user(display_date_time(item.sendondate), "UTC", time_zone)
                
            report_list.append(report_item)
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page_no,
            "getSize": page_size,
            "totalCampaignsEmailSend": total_campaigns_email_send,
            "emailCampaignsReportList": report_list
        }
        
        return api_response(200, "Email Campaigns Fetched Successfully", res_body)
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportListPage Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportDashboard(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportDashboard
    """
    try:
        time_zone = request.query_params.get('timeZone', 'UTC')
        camp_id_enc = request.query_params.get('campId')

        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        campaign_send = CampaignsEmailSend.objects.filter(id=camp_id).first()
        if not campaign_send:
            return api_response(404, "Campaign Not Found")

        dashboard = dict()
        dashboard["campName"] = campaign_send.camp_name
        dashboard["totalQueued"] = campaign_send.total_queued if hasattr(campaign_send, 'total_queued') else 0
        dashboard["subject"] = campaign_send.subject
        dashboard["senderName"] = campaign_send.from_name
        dashboard["senderEmail"] = campaign_send.from_add

        if campaign_send.sendondate:
            dashboard["sentOn"] = convert_event_timezone_to_user(display_date_time(campaign_send.sendondate), "UTC", time_zone)
            
        # Mailing Group
        group_name = ""
        if campaign_send.grouplist:
            # Java: this.groupRepository.findByGroupNameById(campaignsEmailSendDto.getGroupList())
            # Assuming groupList is a comma separated string of IDs
            try:
                g_ids = [int(x) for x in campaign_send.grouplist.split(',') if x.strip()]
                groups = Groups.objects.filter(grpId__in=g_ids).values_list('grpGroupName', flat=True)
                group_name = ", ".join(groups)
            except:
                pass
        dashboard["mailingGroup"] = group_name
        
        # Template Name
        template_name = ""
        if campaign_send.mypageid:
            template = MyPages.objects.filter(mpId=campaign_send.mypageid).first()
            if template:
                template_name = template.mpName
        dashboard["templateName"] = template_name
        
        cse_queryset = CampaignsSendEmail.objects.filter(campSendId=camp_id)
        
        sent = cse_queryset.count()
        deliveries = cse_queryset.filter(isSend='Y', isBounced='N').count()
        exception = cse_queryset.filter(isSend='Y', isBounced__in=['E', 'D']).count()
        opened = cse_queryset.filter(isRead='Y').count()
        bounced = cse_queryset.filter(isBounced='Y').count()
        unsubscribed = cse_queryset.filter(isUnsubscribed='Y').count()
        unread = deliveries - opened
        
        dashboard.update({
            "sent": sent,
            "delivered": deliveries,
            "exception": exception,
            "opened": opened,
            "bounced": bounced,
            "unread": unread,
            "unsubscribed": unsubscribed,
        })
        
        link_count_total = 0
        ui = 0
        total_desktop = 0
        total_mobile = 0
        
        campaign_links = CampaignLinks.objects.filter(campId=camp_id)
        for link in campaign_links:
            link_count_total += (link.linkCount or 0)
            pc = CampaignLinkClick.objects.filter(linkId=link.id, sources='PC').count()
            total_desktop += pc
            phone = CampaignLinkClick.objects.filter(linkId=link.id, sources='Phone').count()
            total_mobile += phone
            
            # Java: ui++ for each unique user per link
            unique_users_per_link = CampaignLinkClick.objects.filter(linkId=link.id).values('userId').distinct().count()
            ui += unique_users_per_link
            
        successful_deliveries = deliveries
        successful_deliveries_per = 0.0
        if sent > 0:
            successful_deliveries_per = (successful_deliveries / sent) * 100
            
        bounced_per = 0.0
        if sent > 0:
            bounced_per = (bounced * 100) / sent
            
        unsubscribed_per = 0.0
        if sent > 0:
            unsubscribed_per = (unsubscribed * 100) / sent
            
        open_rate_per = 0.0
        if successful_deliveries > 0:
            open_rate_per = (opened * 100) / successful_deliveries
            
        total_click_through_rate_per = 0.0
        if deliveries > 0:
            total_click_through_rate_per = (link_count_total * 100) / deliveries
            
        unique_click_through_rate_per = 0.0
        if successful_deliveries > 0:
            unique_click_through_rate_per = (ui * 100) / successful_deliveries
            
        dashboard.update({
            "totalDesktop": total_desktop,
            "totalMobile": total_mobile,
            "successfulDeliveries": successful_deliveries,
            "successfulDeliveriesPer": round(successful_deliveries_per, 2),
            "bouncedPer": round(bounced_per, 2),
            "unsubscribedPer": round(unsubscribed_per, 2),
            "openRatePer": round(open_rate_per, 2),
            "totalClickThroughRate": link_count_total,
            "totalClickThroughRatePer": round(total_click_through_rate_per, 2),
            "uniqueClickThroughRate": ui,
            "uniqueClickThroughRatePer": round(unique_click_through_rate_per, 2)
        })
        
        if hasattr(campaign_send, 'last_opened') and campaign_send.last_opened:
            dashboard["lastOpened"] = display_date_time(campaign_send.last_opened)
            
        return api_response(200, "Email Campaigns Dashboard Fetched Successfully", {"dashboard": dashboard})
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportDashboard Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportProductLinks(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportProductLinks
    """
    try:
        camp_id_enc = request.query_params.get('campId')
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        # campaignSendEmailRepository.findDeliveriesCount(campId) where campId is camp_send_id
        deliveries = CampaignsSendEmail.objects.filter(campSendId=camp_id, isSend='Y', isBounced='N').count()
        
        product_links = []
        links = CampaignLinks.objects.filter(campId=camp_id)
        for link in links:
            unique_clicks = CampaignLinkClick.objects.filter(linkId=link.id).values('userId').distinct().count()
            
            ctr = 0.0
            if deliveries > 0:
                ctr = (unique_clicks * 100) / deliveries
            user_detail_list = []
            user_wise_clicks = CampaignLinkClick.objects.filter(linkId=link.id).values('userId').annotate(link_count=Count('id'))
            for user_click in user_wise_clicks:
                user_id = user_click["userId"]
                click_user_detail = CampaignsSendEmail.objects.filter(emailId=user_id).first()
                first_name = ""
                last_name = ""
                if click_user_detail:
                    first_name = click_user_detail.firstName or ""
                    last_name = click_user_detail.lastName or ""
                location_list = []
                # Equivalent of findDetailByLinkIdAndUserId()
                click_details = CampaignLinkClick.objects.filter(linkId=link.id, userId=user_id)
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

                user_detail_list.append({
                    "userId": user_id,
                    "userName": f"{first_name} {last_name}".strip(),
                    "totalClicked": user_click["link_count"],
                    "locationList": location_list
                })
                
            product_links.append({
                "id": link.id,
                "campLink": link.campLink,
                "uniqueClicks": unique_clicks,
                "totalClicks": link.linkCount or 0,
                "clickThroughRate": ctr,
                "userDetailList": user_detail_list
            })
            
        return api_response(200, "Email Campaigns Product Links Fetched Successfully", {"productLinks": product_links})
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportProductLinks Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportProductLinksClickUser(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportProductLinksClickUser
    """
    try:
        link_id = request.query_params.get('linkId')
        
        clicks = CampaignLinkClick.objects.filter(linkId=link_id).values('userId').annotate(totalClicks=Count('id'))
        
        user_detail_list = []
        for click in clicks:
            # Java: this.campaignSendEmailRepository.findByCampIdAndEmailId(link.getCampId(), click.getUserId());
            # Wait, link check
            link_obj = CampaignLinks.objects.filter(id=link_id).first()
            if not link_obj:
                continue
                
            cse = CampaignsSendEmail.objects.filter(campSendId=link_obj.campId, emailId=click['userId']).first()
            if not cse:
                continue
                
            user_detail_list.append({
                "userName": f"{cse.firstName} {cse.lastName}",
                "email": cse.email,
                "linkCount": click['totalClicks']
            })
            
        return api_response(200, "Email Campaigns Product Links Click User Fetched Successfully", {"productLinksClickUser": user_detail_list})
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportProductLinksClickUser Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportMembersListPage(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportMembersListPage
    """
    try:
        camp_id_enc = request.query_params.get('campId')
        search_key = request.query_params.get('searchKey', '')
        page_no = int(request.query_params.get('page', 0))
        page_size = int(request.query_params.get('size', 10))
        
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        queryset = CampaignsSendEmail.objects.filter(campSendId=camp_id)
        if search_key:
            queryset = queryset.filter(Q(email__icontains=search_key) | Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key))
            
        paginator = Paginator(queryset.order_by('firstName'), page_size)
        page_obj = paginator.get_page(page_no + 1)
        
        members_list = []
        for item in page_obj:
            total_open = CampaignSubscriber.objects.filter(campId=camp_id, subId=item.emailId).count()
            
            member_dto = {
                "firstName": item.firstName,
                "lastName": item.lastName,
                "emailId": item.emailId,
                "email": item.email,
                "totalOpen": total_open
            }
            
            members_list.append(member_dto)
            
        res_body = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page_no,
            "getSize": page_size,
            "emailCampaignsReportMembers": members_list,
            "totalCampaignsSendEmail": queryset.count()
        }
        
        return api_response(200, "Email Campaigns Report Members Fetched Successfully", res_body)
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportMembersListPage Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportMemberClick(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportMemberClick
    """
    try:
        camp_id_enc = request.query_params.get('campId')
        email_id = request.query_params.get('emailId')
        
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        # totalEmailOpen
        total_email_open = CampaignSubscriber.objects.filter(campId=camp_id, subId=email_id).count()
        
        # productLinks
        product_links = []
        campaign_links = CampaignLinks.objects.filter(campId=camp_id)
        for link in campaign_links:
            link_clicked = CampaignLinkClick.objects.filter(linkId=link.id, userId=email_id).count()
            product_links.append({
                "link": link.campLink,
                "linkClicked": link_clicked
            })
            
        # technology
        technology_list = []
        for link in campaign_links:
            pc = CampaignLinkClick.objects.filter(linkId=link.id, sources='PC', userId=email_id).count()
            phone = CampaignLinkClick.objects.filter(linkId=link.id, sources='Phone', userId=email_id).count()
            technology_list.append({
                "id": link.id,
                "campLink": link.campLink,
                "pc": pc,
                "mobile": phone,
                "clickThroughRate": None
            })
            
        # location
        locations = []
        for link in campaign_links:
            clicks = CampaignLinkClick.objects.filter(linkId=link.id, userId=email_id)
            for click in clicks:
                locations.append({
                    "link": link.campLink,
                    "location": click.city,
                    "date": display_date_time(click.clickDate),
                    "browser": get_browser_name(click.sourceDetails) # Using helper
                })
                
        res_body = {
            "totalEmailOpen": total_email_open,
            "productLinks": product_links,
            "technology": technology_list,
            "location": locations
        }
        
        return api_response(200, "Email Campaigns Tenant Click Fetched Successfully", res_body)
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportMemberClick Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportSources(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportSources
    """
    try:
        camp_id_enc = request.query_params.get('campId')
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        sources_list = []
        links = CampaignLinks.objects.filter(campId=camp_id)
        for link in links:
            pc = CampaignLinkClick.objects.filter(linkId=link.id, sources='PC').count()
            mobile = CampaignLinkClick.objects.filter(linkId=link.id, sources='Phone').count()
            sources_list.append({
                "id": link.id,
                "campLink": link.campLink,
                "clickThroughRate": None,
                "pc": pc,
                "mobile": mobile
            })
            
        return api_response(200, "Email Campaigns Report Sources Fetched Successfully", {"emailCampaignsReportSourceLinks": sources_list})
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportSources Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getCampaignsReportPrint(request):
    """
    Java: /emailCampaignReport/getCampaignsReportPrint
    """
    try:
        camp_id_enc = request.query_params.get('campId')
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        # Product Links
        deliveries = CampaignsSendEmail.objects.filter(campSendId=camp_id, isSend='Y', isBounced='N').count()
        product_links = []
        links = CampaignLinks.objects.filter(campId=camp_id)
        for link in links:
            unique_clicks = CampaignLinkClick.objects.filter(linkId=link.id).values('userId').distinct().count()
            ctr = (unique_clicks * 100) / deliveries if deliveries > 0 else 0.0
            product_links.append({
                "campLink": link.campLink,
                "uniqueClicks": unique_clicks,
                "totalClicks": link.linkCount or 0,
                "clickThroughRate": ctr
            })
            
        # Members
        cse_list = CampaignsSendEmail.objects.filter(campSendId=camp_id)
        members_list = []
        for item in cse_list:
            total_open = CampaignSubscriber.objects.filter(campId=camp_id, subId=item.emailId).count()
            members_list.append({
                "firstName": item.firstName,
                "lastName": item.lastName,
                "email": item.email if item.email else "",
                "totalOpen": total_open
            })
            
        # Sources
        sources_list = []
        for link in links:
            pc = CampaignLinkClick.objects.filter(linkId=link.id, sources='PC').count()
            mobile = CampaignLinkClick.objects.filter(linkId=link.id, sources='Phone').count()
            sources_list.append({
                "campLink": link.campLink,
                "pc": pc,
                "mobile": mobile
            })
            
        res_body = {
            "productLinks": product_links,
            "members": members_list,
            "sourceLinks": sources_list
        }
        
        return api_response(200, "Email Campaigns Report Print Fetched Successfully", res_body)
        
    except Exception as e:
        logger.error(f"getCampaignsReportPrint Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsReportMembersList(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsReportMembersList
    """
    try:
        member_id = get_final_tenant_id(request=request)
        camp_id_enc = request.query_params.get('campId')
        camp_id = int(DecryptString.set_enc_dec_user(camp_id_enc, "display", "Y"))
        
        campaign_send = CampaignsEmailSend.objects.filter(id=camp_id).first()
        camp_name = campaign_send.camp_name if campaign_send else ""
        
        cse_list = CampaignsSendEmail.objects.filter(campSendId=camp_id)
        members_list = []
        for item in cse_list:
            total_open = CampaignSubscriber.objects.filter(campId=camp_id, subId=item.emailId).count()
            unsubscribe_date = Contact.objects.filter(emailId=item.emailId, memberId=get_client_id_by_tenant_id(member_id), optId=camp_id, status='Unsubscribed').first()
            unsubscribe_date_str = display_date_time(unsubscribe_date.optDate) if unsubscribe_date and unsubscribe_date.optDate else ""
            members_list.append({
                "firstName": item.firstName,
                "lastName": item.lastName,
                "email": item.email,
                "totalOpen": total_open,
                "unsubscribeDate": unsubscribe_date_str
            })
            
        return api_response(200, "Email Campaigns Report Members List Fetched Successfully", {"campName": camp_name, "members": members_list})
        
    except Exception as e:
        logger.error(f"getEmailCampaignsReportMembersList Error: {e}")
        return api_response(500, "Internal Server Error")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getBouncedEmailReportList(request):
    """
    Java: /emailCampaignReport/getBouncedEmailReportList
    """
    try:
        final_member_id = get_final_tenant_id(request=request)
        camp_send_id = request.query_params.get('campSendId')
        if camp_send_id:
            camp_send_id = DecryptString.set_enc_dec_user(camp_send_id, "display", "Y")
        split_group = request.query_params.get('splitGroup')
        
        queryset = CampaignsSendEmail.objects.filter(campSendId=camp_send_id, isBounced='Y')
        if split_group:
            queryset = queryset.filter(splitGroup=split_group)
            
        bounced_list = []
        for item in queryset:
            contact = Contact.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id), emailId=item.emailId).first()
            bounced_list.append({
                "email": item.email,
                "firstName": item.firstName,
                "lastName": item.lastName,
                "bounceReason": contact.bounceReason if contact else "",
                "status": contact.status if contact else ""
            })
            
        return api_response(200, "Bounced Email Report Fetched Successfully", {"bouncedEmailList": bounced_list})
        
    except Exception as e:
        logger.error(f"getBouncedEmailReportList Error: {e}")
        return api_response(500, "Internal Server Error")


@api_view(['GET'])
@permission_classes([WhitelistPermission])
@with_oracle_db
def getEmailCampaignsMemberOpenListPage(request, cursor):
    """
    Java: /emailCampaignReport/getEmailCampaignsMemberOpenListPage
    """
    try:
        camp_id_enc = request.query_params.get('campId')
        search_key = request.query_params.get('searchKey', '')
        page_no = int(request.query_params.get('page', 0))
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
        queryset = CampaignsSendEmail.objects.filter(campSendId=camp_id, emailId__in=email_id_list)
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
    
# Constants for contact headers
CONTACT_HEADER_KEYS = ["firstName", "lastName", "fullName", "email", "phoneNumber", "phone", "usDefaultLanguage", "streetAddress1", "streetAddress2", "city", "stateProvRegion", "zipPostalCode", "country", "birthday", "gender", "emailDomain", "dateRegistered", "status", "smsStatus", "totalOpen"]
CONTACT_HEADER_VALUES = ["First Name", "Last Name", "Full Name", "Email", "Mobile", "Phone", "Language", "Street Address1", "Street Address2", "City", "State", "Zip Code", "Country", "Birthday", "Gender", "Email Domain", "Registered Date", "Status", "SMS Status", "Total Open"]

def find_contact_header_list(email_id):
    res_body = {}
    for i in range(len(CONTACT_HEADER_KEYS)):
        res_body[CONTACT_HEADER_KEYS[i]] = CONTACT_HEADER_VALUES[i]
        
    # UDFs
    try:
        contact = Userlist.objects.filter(emailId=email_id).first()
        if contact:
            # This logic in Java seems to get group ID then UDFs
            # For now simplified as per Java snippet
            pass
    except:
        pass
    return res_body

def find_contact_header_key_list():
    return list(CONTACT_HEADER_KEYS)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEmailCampaignsMemberOpenList(request):
    """
    Java: /emailCampaignReport/getEmailCampaignsMemberOpenList
    """
    try:
        final_member_id = get_final_tenant_id(request=request)
        camp_id = request.query_params.get('campId')
        
        email_id_list = CampaignSubscriber.objects.filter(campId=camp_id).values_list('subId', flat=True).distinct()
        
        cse_list = CampaignsSendEmail.objects.filter(campSendId=camp_id, emailId__in=email_id_list)
        
        user_fields_list = []
        first_email_id = None
        
        for item in cse_list:
            if first_email_id is None:
                first_email_id = item.emailId
                
            userlist = Userlist.objects.filter(memberId=final_member_id, emailId=item.emailId).first()
            if not userlist:
                continue
                
            total_open = CampaignSubscriber.objects.filter(campId=camp_id, subId=item.emailId).count()
            if total_open > 0:
                user_data = {
                    "firstName": userlist.firstName,
                    "lastName": userlist.lastName,
                    "fullName": userlist.fullName,
                    "email": userlist.email if userlist.email else "",
                    "phoneNumber": userlist.phoneNumber,
                    "phone": userlist.phone,
                    "usDefaultLanguage": userlist.usDefaultLanguage,
                    "streetAddress1": userlist.streetAddress1,
                    "streetAddress2": userlist.streetAddress2,
                    "city": userlist.city,
                    "stateProvRegion": userlist.stateProvRegion,
                    "zipPostalCode": userlist.zipPostalCode,
                    "country": userlist.country,
                    "birthday": userlist.birthday,
                    "gender": userlist.gender,
                    "emailDomain": userlist.emailDomain,
                    "dateRegistered": display_date_time(userlist.dateRegistered) if userlist.dateRegistered else "",
                    "status": userlist.status,
                    "smsStatus": userlist.smsStatus,
                    "totalOpen": total_open
                }
                user_fields_list.append(user_data)
                
        res_body = {
            "contactHeader": find_contact_header_list(first_email_id),
            "contactHeaderKey": find_contact_header_key_list(),
            "emailCampaignsReportMembers": user_fields_list
        }
        
        return api_response(200, "Email Campaigns Tenant Open List Fetched Successfully", res_body)
        
    except Exception as e:
        logger.error(f"getEmailCampaignsMemberOpenList Error: {e}")
        return api_response(500, "Internal Server Error")
