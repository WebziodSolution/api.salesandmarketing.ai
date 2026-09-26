import json
import logging
import os
import shutil
from django.utils import timezone
import requests
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from django.conf import settings
from bs4 import BeautifulSoup, Tag
from common_app.custom_permissions import WhitelistPermission
from automation_app.models import (Automation, AutomationCampaignMaster, AutomationCampaignNode, AutomationSmsDetails, AutomationSendContact)
from common_app.models import TranslateTemplate, AutomationSmsReplyLog, TranslateTemplateSend, MyPages, Groups, CampaignsSendEmail, CampaignsEmailSend, CampaignLinks, CampaignLinkClick, CampaignSubscriber, UnsubscribeLogs, Userlist
from common_app.utils import api_response, get_final_tenant_id, convert_event_timezone_to_user_db, get_browser_name, get_client_timezone, get_client_id_by_tenant_id, display_date_time
from common_app.decrypt_string import DecryptString
from datetime import datetime, timedelta
from mycrm_app.views.contact_views import format_date_parity
import re

logger = logging.getLogger(__name__)
# --- Helper Functions ---

def convert_date(date_str):
    if not date_str:
        return None
    try:
        if isinstance(date_str, datetime):
            if timezone.is_naive(date_str):
                return timezone.make_aware(date_str)
            return date_str
        
        parsed_dt = None
        # Try MM/DD/YYYY format first (common from UI)
        try:
            parsed_dt = datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
        except ValueError:
            # Fallback to ISO format
            try:
                parsed_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        
        if parsed_dt:
            # Assuming the strings being parsed are already in UTC or the intended DB timezone
            return timezone.make_aware(parsed_dt)
    except Exception:
        pass
    return None

def format_date_output(dt):
    if not dt or not isinstance(dt, datetime):
        return ""
    return dt.strftime("%m/%d/%Y %H:%M:%S")

def recursive_data(source_id, acm_id, am_id):
    prev_mypage = ""
    try:
        node = AutomationCampaignNode.objects.filter(acnNodeId=source_id, acnMasterId=acm_id, acnAutId=am_id).first()
        if node:
            node_type = node.acnNodeType
            source_id = node.acnSourceId
            if node_type == "Email":
                node_detail = json.loads(node.acnNodeDetail or '{}')
                prev_mypage = node_detail.get('emailTemplateSelected', {}).get('mpName', "")
            elif node_type == "Sms":
                node_detail = json.loads(node.acnNodeDetail or '{}')
                prev_mypage = node_detail.get('smsTemplateSelected', {}).get('sstName', "")
            elif node_type == "Trigger":
                node_detail = json.loads(node.acnNodeDetail or '{}')
                prev_mypage = node_detail.get('selectedEmailTemplate', {}).get('mpName', "")
            
            if not prev_mypage and node_type not in ["Start", "Trigger", "Email", "Sms"]:
                return recursive_data(source_id, acm_id, am_id)
    except Exception:
        pass
    return prev_mypage

def get_default_condition_details():
    return {
        "unread": 0,
        "delivered": 0,
        "opened": 0,
        "bounced": 0,
        "sent": 0,
        "sendMypage": None,
        "oldMypage": None,
        "subject": None,
        "fromName": None,
        "fromEmail": None,
        "totalQueued": 0,
        "exception": 0,
        "unsubscribed": 0,
        "uniqueClickThroughRate": 0,
        "totalClickThroughRate": 0,
        "campSendId": 0,
        "nodeType": None,
        "notSent": 0,
        "fromNumber": None
    }

def get_sms_node_stats(am_id, camp_send_id):
    stats = {
        "totalQueued": 0,
        "sent": 0,
        "delivered": 0,
        "notSent": 0
    }
    if am_id and camp_send_id:
        stats["totalQueued"] = AutomationSendContact.objects.filter(automationId=am_id, campSendId=camp_send_id).count()
        stats["sent"] = AutomationSendContact.objects.filter(automationId=am_id, campSendId=camp_send_id, smsStatus__in=['sent', 'sending', 'queued', 'delivered']).count()
        stats["delivered"] = AutomationSendContact.objects.filter(automationId=am_id, campSendId=camp_send_id, smsStatus='delivered').count()
        stats["notSent"] = stats["totalQueued"] - stats["delivered"]
    return stats


def get_trigger_object(json_array):
    if not json_array:
        return {}
    for node in json_array:
        if node.get('type') == 'Trigger':
            return node
    return {}

def get_node_stats(camp_send_id, node_id=None):
    stats = {
        "totalQueued": 0, "sent": 0, "delivered": 0, "opened": 0, "bounced": 0,
        "unread": 0, "exception": 0, "unsubscribed": 0, "uniqueClickThroughRate": 0, "totalClickThroughRate": 0
    }
    if camp_send_id and camp_send_id > 0:
        ces = CampaignsEmailSend.objects.filter(id=camp_send_id).first()
        if ces:
            stats['totalQueued'] = ces.total_queued or 0
        
        email_stats = CampaignsSendEmail.objects.filter(campSendId=camp_send_id)
        stats['sent'] = email_stats.filter(isProcessed='Y').count()
        stats['delivered'] = email_stats.filter(isSend='Y', isBounced='N').count()
        stats['opened'] = email_stats.filter(isRead='Y').count()
        stats['bounced'] = email_stats.filter(isBounced='Y').count()
        stats['unread'] = max(0, stats['delivered'] - stats['opened'])
        stats['exception'] = email_stats.filter(emailStatus='Error').count()
        stats['unsubscribed'] = email_stats.filter(isUnsubscribed='Y').count()

        if node_id:
            campaign_links = CampaignLinks.objects.filter(nodeId=node_id)
            total_clicks = 0
            unique_users_total = 0
            for cl in campaign_links:
                total_clicks += cl.linkCount
                unique_users_total += CampaignLinkClick.objects.filter(linkId=cl.id).values_list('userId', flat=True).distinct().count()
            stats['totalClickThroughRate'] = total_clicks
            stats['uniqueClickThroughRate'] = unique_users_total
            
    return stats

def get_product_links_helper(camp_send_id, node_id):
    product_links = []
    try:
        email_stats = CampaignsSendEmail.objects.filter(campSendId=camp_send_id)
        total_receipt = email_stats.filter(isSend='Y', isBounced='N').count()

        campaign_links = CampaignLinks.objects.filter(nodeId=node_id)
        for cl in campaign_links:
            unique_clicks = CampaignLinkClick.objects.filter(linkId=cl.id).values('userId').distinct().count()
            click_through_rate = 0
            if total_receipt > 0:
                click_through_rate = (cl.linkCount / total_receipt) * 100
            
            user_details = []
            user_wise_clicks = CampaignLinkClick.objects.filter(linkId=cl.id).values('userId').annotate(total_clicked=Count('id'))
            for uwc in user_wise_clicks:
                user_id = uwc['userId']
                cse = CampaignsSendEmail.objects.filter(emailId=user_id, campSendId=camp_send_id).first()
                user_name = f"{cse.firstName} {cse.lastName}" if cse else "Unknown User"
                
                location_list = []
                click_locs = CampaignLinkClick.objects.filter(linkId=cl.id, userId=user_id)
                for loc in click_locs:
                    source_type = "Desktop" if loc.sources == "PC" else "Mobile" if loc.sources == "Phone" else loc.sources
                    click_date_str = loc.clickDate.strftime("%m/%d/%Y %H:%M:%S") if loc.clickDate else ""
                    location_list.append({
                        "location": loc.city,
                        "clickDate": click_date_str,
                        "browser": get_browser_name(loc.sourceDetails),
                        "technology": source_type
                    })

                user_details.append({
                    "userId": user_id,
                    "userName": user_name,
                    "totalClicked": uwc['total_clicked'],
                    "locationList": location_list
                })

            product_links.append({
                "id": cl.id,
                "campLink": cl.campLink,
                "uniqueClicks": unique_clicks,
                "totalClicks": cl.linkCount,
                "userDetailList": user_details,
                "clickThroughRate": click_through_rate
            })
    except Exception as e:
        logger.error(f"get_product_links_helper Error: {e}")
    return product_links

def get_sources_helper(node_id):
    product_sources = []
    try:
        links = CampaignLinks.objects.filter(nodeId=node_id)
        for link in links:
            pc_clicks = CampaignLinkClick.objects.filter(linkId=link.id, sources='PC').count()
            mobile_clicks = CampaignLinkClick.objects.filter(linkId=link.id, sources='Phone').count()
            product_sources.append({
                "id": link.id,
                "campLink": link.campLink,
                "pc": pc_clicks,
                "mobile": mobile_clicks
            })
    except Exception as e:
        logger.error(f"get_sources_helper Error: {e}")
    return product_sources

def storeNodeDataSMS(tenant_id, am_id, am_json, automation):
    try:
        root_node = json.loads(am_json)
        nodes = root_node.get('nodes', [])
        if len(nodes) > 0:
            for node in nodes:
                node_type = node.get('type')
                data = node.get('data', {})
                if node_type == "Trigger":
                    automation.autEstimatedCompletionDateTime = timezone.now()
                    automation.autSmsFromNumber = data.get('smsFromNumber')
                    automation.autSmsFromNumberSid = data.get('smsFromNumberSid')
                    automation.autSmsOptinYn = data.get('smsOptinYn')
                    automation.autSmsGroupId = data.get('smsGroupId')
                    automation.save()
                elif node_type == "SmsResponse":
                    AutomationSmsDetails.objects.create(
                        detSmsId=am_id,
                        detReceiveReply=data.get('detReceiveReply'),
                        detSendReplyDetails=data.get('detSendReplyDetails')
                    )
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] StoreNodeDataSMS Error : {e}")

def get_next_object(next_edge_data, current_node, node_array, edges_array):
    target_id = next_edge_data.get('target')
    current_node_type = current_node.get('type')
    current_node_edges = []
    
    if current_node_type == "Link":
        source_handle = next_edge_data.get('sourceHandle')
        if not source_handle:
            next_node = next((n for n in node_array if n.get('id') == target_id), {})
            if next_node and next_node.get('type') != "Stop":
                for edge in edges_array:
                    if edge.get('source') == target_id:
                        current_node_edges.append(edge)
        else:
            next_node = next((n for n in node_array if n.get('id') == target_id), {})
            if next_node and next_node.get('type') != "Stop":
                links_array = current_node.get('data', {}).get('links', [])
                try:
                    idx_str = source_handle.split('_')[-1]
                    link_index = int(idx_str) if idx_str else 0
                except (ValueError, IndexError):
                    link_index = 0

                return {
                    "link_email_node": next_node.get('data'),
                    "link": links_array[link_index] if link_index < len(links_array) else "",
                    "linkNodeId": current_node.get('id')
                }
            else:
                return None
    else:
        next_node = next((n for n in node_array if n.get('id') == target_id), {})
        if next_node and next_node.get('type') != "Stop":
            for edge in edges_array:
                if edge.get('source') == target_id:
                    current_node_edges.append(edge)

    if next_node:
        next_node['sourceHandle'] = next_edge_data.get('sourceHandle')
        next_node['source'] = current_node.get('id')
        return {
            "currentNodeEdges": current_node_edges,
            "currentNode": next_node
        }
    return None

def storeNodeData(tenant_id, current_node_data, nodes_array, edges_array, acm_id, am_id, links_node_data):
    try:
        current_node = current_node_data.get('currentNode')
        acn_node_id = current_node.get('id')
        
        node = AutomationCampaignNode()
        node.acnMasterId = acm_id
        node.acnAutId = am_id
        node.acnNodeDetail = json.dumps(current_node.get('data', {}))
        node.acnNodeId = acn_node_id
        node.acnNodeType = current_node.get('type')
        node.acnSourceId = current_node.get('source',None)
        node.acnSourceHandle = current_node.get('sourceHandle',None)
        node.save()
        
        next_edges = current_node_data.get('currentNodeEdges', [])
        for edge in next_edges:
            next_node_data = get_next_object(edge, current_node, nodes_array, edges_array)
            if next_node_data:
                if "link_email_node" in next_node_data:
                    links_node_data.append(next_node_data)
                else:
                    storeNodeData(tenant_id, next_node_data, nodes_array, edges_array, acm_id, am_id, links_node_data)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] StoreNodeData Error : {e}")

def get_start_object(node_array, edges_array):
    start_obj = {}
    for node in node_array:
        if node.get('type') == 'Start':
            start_obj = node
            start_obj["sourceHandle"] = None
            break
    
    if not start_obj:
        return None
        
    object_id = start_obj.get('id')
    current_node_edges = []
    for edge in edges_array:
        if edge.get('source') == object_id:
            current_node_edges.append(edge)
            
    return {
        "currentNodeEdges": current_node_edges,
        "currentNode": start_obj,
        "source": None
    }

def update_path(
    element: Tag | None,
    attr: str,
    tenant_id: int,
    am_id: int,
    node_id: int,
    dest_dir: str,
    html_content: str
) -> str:
    if element and element.has_attr(attr):
        old_link = str(element[attr])
        if "automation" not in old_link:
            img_name = old_link.split("/")[-1]
            if node_id > 0:
                new_link = (
                    f"{settings.SITE_URL}usercontent/{tenant_id}/images/"
                    f"automation/{am_id}/{node_id}/{img_name}"
                )
            else:
                new_link = (
                    f"{settings.SITE_URL}usercontent/{tenant_id}/images/"
                    f"automation/{am_id}/{img_name}"
                )
            if "easdrive" in old_link:
                try:
                    resp = requests.get(str(old_link))
                    if resp.status_code == 200:
                        with open(os.path.join(dest_dir, img_name), "wb") as img_f:
                            img_f.write(resp.content)
                except Exception:
                    pass
            html_content = html_content.replace(
                str(old_link),
                str(new_link)
            )
    return html_content

def copyMyPage(tenant_id, my_page_id, am_id, node_id):
    all_data = ""
    try:
        base_dir = os.path.join(settings.FILE_UPLOAD_DIR, str(tenant_id), "images")
        source_dir = os.path.join(base_dir, "mypage", str(my_page_id))
        dest_dir = os.path.join(base_dir, "automation", str(am_id))
        
        if node_id > 0:
            dest_dir = os.path.join(dest_dir, str(node_id))
            
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            
        if os.path.exists(source_dir):
            for file_name in os.listdir(source_dir):
                shutil.copy2(os.path.join(source_dir, file_name), os.path.join(dest_dir, file_name))
        
        html_file = os.path.join(dest_dir, "index.html")
        if not os.path.exists(html_file):
            return ""
            
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        soup = BeautifulSoup(html_content, 'html.parser')

        # Background images
        html_content = update_path(
            soup.find(id="mcd"),
            "item-path",
            tenant_id,
            am_id,
            node_id,
            dest_dir,
            html_content
        )

        html_content = update_path(
            soup.find(id="templateBody"),
            "item-path",
            tenant_id,
            am_id,
            node_id,
            dest_dir,
            html_content
        )
        
        # Regular images
        for img in soup.find_all(class_="mcnImage"):
            if img.has_attr('src'):
                old_link = str(img['src'])
                if "automation" not in old_link:
                    img_name = old_link.split('/')[-1]
                    new_link = f"{settings.SITE_URL}usercontent/{tenant_id}/images/automation/{am_id}/{img_name}"
                    if node_id > 0:
                        new_link = f"{settings.SITE_URL}usercontent/{tenant_id}/images/automation/{am_id}/{node_id}/{img_name}"
                    
                    if "easdrive" in old_link:
                        try:
                            resp = requests.get(str(old_link))
                            if resp.status_code == 200:
                                with open(os.path.join(dest_dir, img_name), 'wb') as img_f:
                                    img_f.write(resp.content)
                        except Exception: pass
                    
                    html_content = html_content.replace(str(old_link), str(new_link))
        
        all_data = html_content
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] CopyMyPage Error : {e}")
    return all_data


def storeLinks(tenant_id, my_page_id, am_id, camp_html, automation_campaign_master, email_flag, node_id, links_node_data):
    try:
        nfl = ["javascript:void(0);", "#dialog_1", "#dialog_2", "#dialog_3", "#dialog_4", "#dialog_5", "http://www.yourgaragesale.com", "http://qa.yourgaragesale.com"]
        camp_html = camp_html.replace("?", "~~~~~~")
        soup = BeautifulSoup(camp_html, "html.parser")
        tags = soup.find_all("a")
        t_val_count = 0
        key_val_array = {}

        for tag in tags:
            href_link = str(tag.get("href", ""))
            link = href_link
            if (href_link.lower() not in nfl
                and settings.SITE_NAME_SMALL_COM not in href_link.lower()
                and "mailto:" not in href_link.lower()
                and "tel:" not in href_link.lower()
            ):

                if "flink=" in href_link:
                    link = href_link.split("flink=")[1]

                if link:
                    clean_link = link.replace("~~~~~~", "?")
                    tid = CampaignLinks.objects.filter(campLink=clean_link, nodeId=node_id).values_list("id", flat=True).first()

                    if not tid:
                        campaign_link = CampaignLinks()
                        campaign_link.campId = 0
                        campaign_link.campLink = clean_link
                        campaign_link.linkCount = 0
                        campaign_link.nodeId = node_id

                        if links_node_data:
                            for node_data in links_node_data:
                                if clean_link == node_data.get("link"):
                                    campaign_link.automationEmailNodeDetails = json.dumps(node_data.get("link_email_node", {}))
                        campaign_link.save()

                        new_link = (
                            f"{settings.SITE_URL}linkclick?"
                            f"n={DecryptString.set_enc_dec_user(str(node_id), '', 'Y')}"
                            f"&d={DecryptString.set_enc_dec_user(str(am_id), '', 'Y')}"
                            f"&flink={link}"
                            f"&m=~~~uid~~~"
                        )

                        n_link = f"~~~~{t_val_count}~~~~"
                        camp_html = re.sub(re.escape(str(link)), n_link, camp_html, count=1)
                        camp_html = re.sub(re.escape(str(link)), n_link, camp_html, count=1)
                        key_val_array[n_link] = new_link
                        t_val_count += 1

        all_language = []

        my_page = MyPages.objects.filter(mpId=my_page_id).first()
        assert my_page is not None
        all_lan = my_page.mpTemplateLanguage or ""

        if my_page.mpTemplateConvertLangList:
            all_lan += "," + my_page.mpTemplateConvertLangList

        if all_lan:
            all_language = all_lan.split(",")

        for lang in all_language:
            translate_template_send = (TranslateTemplateSend.objects.filter(ttMyPageId=my_page_id, ttTemplateLanguage=lang, ttNodeId=node_id).first())
            if translate_template_send:
                html_trans = translate_template_send.ttCampDetailSend
                html_trans = html_trans.replace("?", "~~~~~~")
                soup = BeautifulSoup(html_trans, "html.parser")
                tags = soup.find_all("a")

                for tag in tags:
                    href_link = str(tag.get("href", ""))
                    link = href_link

                    if href_link.lower() not in nfl and settings.SITE_NAME_SMALL_COM not in href_link.lower() and "mailto:" not in href_link.lower() and "tel:" not in href_link.lower():

                        if "flink=" in href_link:
                            link = href_link.split("flink=")[1]

                        if link:
                            new_link = f"{settings.SITE_URL}linkclick?n={DecryptString.set_enc_dec_user(str(node_id), '', 'Y')}&d={DecryptString.set_enc_dec_user(str(am_id), '', 'Y')}&flink={link}&m=~~~uid~~~"

                            n_link = f"~~~~{t_val_count}~~~~"
                            html_trans = re.sub(re.escape(str(link)), n_link, html_trans, count=1)
                            html_trans = re.sub(re.escape(str(link)), n_link, html_trans, count=1)

                            key_val_array[n_link] = new_link
                            t_val_count += 1

                # cleanup
                html_trans = re.sub(r'[\r\n]+', '', html_trans)
                html_trans = re.sub(r'>\s+<', '><', html_trans)
                html_trans = html_trans.replace("~~~~~~", "?")

                translate_template_send.ttCampDetailSend = html_trans
                translate_template_send.save()

        if key_val_array:
            for key, value in key_val_array.items():
                camp_html = re.sub(re.escape(str(key)), value, camp_html, count=1)
                camp_html = re.sub(re.escape(str(key)), value, camp_html, count=1)

            for lang in all_language:
                translate_template_send = (TranslateTemplateSend.objects.filter(ttMyPageId=my_page_id, ttTemplateLanguage=lang, ttNodeId=node_id).first())

                if translate_template_send:
                    html_trans = translate_template_send.ttCampDetailSend
                    for key, value in key_val_array.items():
                        temp_link = value.replace("~~~~~~", "?")
                        html_trans = re.sub(re.escape(str(key)), temp_link, html_trans, count=1)
                        html_trans = re.sub(re.escape(str(key)), temp_link, html_trans, count=1)

                    html_trans = re.sub(r'[\r\n]+', '', html_trans)
                    html_trans = re.sub(r'>\s+<', '><', html_trans)
                    html_trans = html_trans.replace("~~~~~~", "?")

                    translate_template_send.ttCampDetailSend = html_trans
                    translate_template_send.save()

            if not email_flag:
                camp_html = re.sub(r'[\r\n]+', '', camp_html)
                camp_html = re.sub(r'>\s+<', '><', camp_html)
                camp_html = camp_html.replace("~~~~~~", "?")
                automation_campaign_master.campDetail = camp_html
                automation_campaign_master.save()
        return camp_html
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] StoreLinks Error : {str(e)}")
        return camp_html

def createTranslateTemplateSend(tenant_id, my_page_id, node_id):
    try:
        TranslateTemplateSend.objects.filter(ttMyPageId=my_page_id, ttNodeId=node_id).delete()
        
        templates = TranslateTemplate.objects.filter(ttMyPageId=my_page_id)
        
        for t in templates:
            TranslateTemplateSend.objects.create(
                ttMyPageId=t.ttMyPageId,
                ttMemberId=t.ttClientId,
                ttCampDetailSend=t.ttCampDetailSend,
                ttMasterCopy=t.ttMasterCopy,
                ttTemplateLanguage=t.ttTemplateLanguage,
                ttPublishDate=t.ttPublishDate,
                ttApiError=t.ttApiError,
                ttNodeId=node_id
            )
            
    except Exception as e:
        logger.exception(e)
        logger.error(f"[ tenantId : {tenant_id} ] CreateTranslateTemplateSend Error : {e}")

def add_date_time(start_date, duration_type, value):
    if not start_date:
        return datetime.now()
    try:
        if duration_type == "minutes":
            return start_date + timedelta(minutes=int(value))
        elif duration_type == "hours":
            return start_date + timedelta(hours=int(value))
        elif duration_type == "days":
            return start_date + timedelta(days=int(value))
        elif duration_type == "weeks":
            return start_date + timedelta(weeks=int(value))
        elif duration_type == "months":
            # Approximation
            return start_date + timedelta(days=30 * int(value))
    except Exception:
        pass
    return start_date

# --- Views ---

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def createAutomation(request):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    data = request.data
    try:
        am_id = data.get('amId', 0)
        if am_id > 0:
            automation = Automation.objects.get(autId=am_id, autClientId=get_client_id_by_tenant_id(final_tenant_id))
        else:
            automation = Automation()
            automation.autClientId = get_client_id_by_tenant_id(final_tenant_id)
        automation.autStartCondition = data.get('amStartCondition')
        automation.autName = data.get('amName')
        automation.autDescription = data.get('amDesc')
        automation.autEmailTemplateId = data.get('amTemplateId')
        automation.autGroupId = data.get('amGroupId')
        automation.autJsonData = data.get('amJSON')
        automation.autStartAction = data.get('amStartingAction')
        automation.autSaveStatus = data.get('saveStatus')
        automation.autStartDateTime = timezone.now()
        
        sch_type = data.get('schType', 0)
        user_tz = get_client_timezone(final_tenant_id)
        if sch_type == 1:
            automation.autSendDateTime = timezone.now()
            automation.autAutomationCampaignStatus = "Running"
        else:
            automation.autAutomationCampaignStatus = "Scheduled"
            if data.get('sendDateTime'):
                utc_date_str = convert_event_timezone_to_user_db(data.get('sendDateTime'), user_tz, 'UTC')
                automation.autSendDateTime = convert_date(utc_date_str)
        
        automation.save()
        am_id = automation.autId

        if automation.autStartCondition == "SMS Response Automation":
            if am_id > 0:
                AutomationSmsDetails.objects.filter(detSmsId=am_id).delete()
            storeNodeDataSMS(final_tenant_id, am_id, automation.autJsonData, automation)
        else:
            camp_detail = json.loads(data.get('campDetails', '{}'))
            acm = AutomationCampaignMaster.objects.filter(amId=am_id).first()
            if not acm:
                acm = AutomationCampaignMaster()
            
            acm.amId = am_id
            acm.memberId = get_client_id_by_tenant_id(final_tenant_id)
            if camp_detail.get('id') and am_id > 0:
                acm.id = camp_detail.get('id')
            
            acm.campName = camp_detail.get('name', '')
            acm.campDetail = camp_detail.get('detail', '')
            acm.campType = 2
            acm.campGroupId = automation.autGroupId or 0
            acm.formName = camp_detail.get('fromName', '')
            acm.formAdd = camp_detail.get('fromEmail', '')
            acm.replyToAdd = camp_detail.get('fromEmail', '')
            acm.subject = camp_detail.get('subject', '')
            acm.mailType = camp_detail.get('mailType', 'Newsletter')
            acm.templateName = str(automation.autEmailTemplateId or '')
            acm.myPageId = data.get('myPageId')
            acm.sendDate = automation.autSendDateTime
            acm.sendOnDate = automation.autSendDateTime
            
            if automation.autSendDateTime:
                t = automation.autSendDateTime.time()
                acm.sendOnTime = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
            
            acm.isSend = 0
            acm.isProcessed = 0
            acm.save()

            if am_id > 0:
                AutomationCampaignNode.objects.filter(acnAutId=am_id).delete()
            
            am_json_obj = json.loads(automation.autJsonData or '{}')
            nodes_array = am_json_obj.get('nodes', [])
            edges_array = am_json_obj.get('edges', [])
            start_object = get_start_object(nodes_array, edges_array)
            links_node_data = []
            # if start_object:
            assert start_object is not None
            storeNodeData(final_tenant_id, start_object, nodes_array, edges_array, acm.id, am_id, links_node_data)
            
            trigger_node = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnNodeType='Trigger').first()
            
            if automation.autSaveStatus == 'publish' and automation.autStartCondition == 'Email Campaign':
                createTranslateTemplateSend(final_tenant_id, acm.myPageId, trigger_node.acnId if trigger_node else 0)
            
            all_data = copyMyPage(final_tenant_id, data.get('myPageId'), am_id, trigger_node.acnId if trigger_node else 0)
            
            after_trigger_node = None
            if trigger_node:
                after_trigger_node = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnSourceId=trigger_node.acnNodeId).first()
            
            if after_trigger_node:
                if after_trigger_node.acnNodeType == "Link":
                    links_temp = []
                    for link_node_obj in links_node_data:
                        if link_node_obj["linkNodeId"] == after_trigger_node.acnNodeId:
                            links_temp.append(link_node_obj)
                    storeLinks(final_tenant_id, data.get('myPageId'), am_id, all_data, acm, "", trigger_node.acnId if trigger_node else 0, links_temp)
                else:
                    storeLinks(final_tenant_id, data.get('myPageId'), am_id, all_data, acm, "", trigger_node.acnId if trigger_node else 0, [])
            else:
                if trigger_node:
                    storeLinks(final_tenant_id, data.get('myPageId'), am_id, all_data, acm, "", trigger_node.acnId, [])

            if automation.autSaveStatus == 'publish' and automation.autStartCondition == 'Email Campaign':
                timer_nodes = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnMasterId=acm.id, acnNodeType='Timer')
                if timer_nodes.exists():
                    est_date = automation.autSendDateTime
                    for t_node in timer_nodes:
                        t_detail = json.loads(t_node.acnNodeDetail or '{}')
                        est_date = add_date_time(est_date, t_detail.get('duration'), t_detail.get('value'))
                    automation.autEstimatedCompletionDateTime = est_date
                    automation.save()
                
                email_nodes = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnNodeType='Email')
                for e_node in email_nodes:
                    e_detail = json.loads(e_node.acnNodeDetail or '{}')
                    mp_id = e_detail.get('emailTemplateSelected', {}).get('mpId')
                    createTranslateTemplateSend(final_tenant_id, mp_id, e_node.acnId)
                    
                    next_node = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnSourceId=e_node.acnNodeId).first()
                    all_data = copyMyPage(final_tenant_id, mp_id, am_id, e_node.acnId)
                    
                    if next_node:
                        if next_node.acnNodeType == "Link":
                            links_temp = []
                            for link_node_obj in links_node_data:
                                if link_node_obj["linkNodeId"] == next_node.acnNodeId:
                                    links_temp.append(link_node_obj)
                            storeLinks(final_tenant_id, mp_id, am_id, all_data, acm, "", e_node.acnId, links_temp)
                        else:
                            storeLinks(final_tenant_id, mp_id, am_id, all_data, acm, "", e_node.acnId, [])
                    else:
                        storeLinks(final_tenant_id, mp_id, am_id, all_data, acm, "", e_node.acnId, [])

        res_body['automationId'] = automation.autId
        return api_response(status.HTTP_200_OK, "Automation Created Successfully.", res_body)
    except Exception as e:
        logger.exception(e)
        logger.error(f"[ tenantId : {final_tenant_id} ] CreateAutomation Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationList(request):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    search_key = request.query_params.get('searchKey', '')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 10))
    try:
        queryset = Automation.objects.filter(autClientId=get_client_id_by_tenant_id(final_tenant_id))
        if search_key:
            queryset = queryset.filter(Q(autName__icontains=search_key) | Q(autDescription__icontains=search_key))
        queryset = queryset.order_by('-autId')
        paginator = Paginator(queryset, size)
        page_obj = paginator.get_page(page + 1)
        automation_list = []
        user_tz = get_client_timezone(final_tenant_id)
        for am in page_obj:
            def convert_tz(dt):
                if not dt: return ""
                # Use the utility directly as requested
                # Format MM/DD/YYYY HH:MM:SS is required for the response
                c_str = convert_event_timezone_to_user_db(dt.strftime("%Y-%m-%d %H:%M:%S"), 'UTC', user_tz)
                return datetime.strptime(c_str, "%Y-%m-%d %H:%M:%S").strftime("%m/%d/%Y %H:%M:%S")

            item = {
                "amId": am.autId,
                "memberId": am.autClientId,
                "amStartCondition": am.autStartCondition,
                "amName": am.autName,
                "amDesc": am.autDescription,
                "amGroupId": am.autGroupId,
                "amJSON": am.autJsonData,
                "amStartingAction": am.autStartAction,
                "saveStatus": am.autSaveStatus.capitalize() if am.autSaveStatus else None,
                "sendDateTime": convert_tz(am.autSendDateTime),
                "startDateTime": convert_tz(am.autStartDateTime),
                "schType": 0,
                "automationCampaignStatus": am.autAutomationCampaignStatus,
                "estimatedCompletionDateTime": convert_tz(am.autEstimatedCompletionDateTime),
                "timeZone": get_client_timezone(final_tenant_id)
            }
            automation_list.append(item)
        res_body['getNumber'] = page_obj.number - 1
        res_body['getSize'] = size
        res_body['totalRecords'] = paginator.count
        res_body['automationList'] = automation_list
        res_body['getTotalPages'] = paginator.num_pages
        return api_response(status.HTTP_200_OK, "Fetch Automation Data Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAutomationList Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteAutomation(request):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        am_ids = request.data.get('amIds', [])
        if not isinstance(am_ids, list):
            am_ids = [am_ids]

        # Cascading deletion starting from nodes
        node_objs = AutomationCampaignNode.objects.filter(acnAutId__in=am_ids)
        node_ids = list(node_objs.values_list('acnId', flat=True))
        
        if node_ids:
            # Delete links and their clicks linked to these nodes
            link_objs = CampaignLinks.objects.filter(nodeId__in=node_ids)
            link_ids = list(link_objs.values_list('id', flat=True))
            if link_ids:
                CampaignLinkClick.objects.filter(linkId__in=link_ids).delete()
                link_objs.delete()
        
        # Delete related automation data
        AutomationCampaignMaster.objects.filter(amId__in=am_ids).delete()
        AutomationSmsDetails.objects.filter(detSmsId__in=am_ids).delete()

        # Finally delete nodes and the automation master records
        node_objs.delete()
        Automation.objects.filter(autId__in=am_ids, autClientId=get_client_id_by_tenant_id(final_tenant_id)).delete()
        
        return api_response(status.HTTP_200_OK, "Automation Deleted Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] DeleteAutomation Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationById(request, amId):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        automation = Automation.objects.filter(autId=amId, autClientId=get_client_id_by_tenant_id(final_tenant_id)).first()
        
        if automation:
            if automation.autSaveStatus == "publish":
                autName = automation.autName
                automation.autId = 0
                automation.autJsonData = automation.autJsonData.replace(autName, f"{autName} Copy")
                automation.autName = f"{autName} Copy"
                
            acm = None
            if automation.autStartCondition.lower() != "sms response automation":
                acm = AutomationCampaignMaster.objects.filter(amId=amId).first()

            try:
                am_json_obj = json.loads(automation.autJsonData or '{}')
                nodes = am_json_obj.get('nodes', [])
                trigger_node = get_trigger_object(nodes)
                if trigger_node:
                    trigger_data = trigger_node.get('data', {})
                    # If not publish and master exists, add master ID to trigger data
                    if automation.autSaveStatus != 'publish' and acm:
                        trigger_data['id'] = acm.id
                    res_body['campaignDetailsData'] = trigger_data
            except Exception as e:
                logger.error(f"getAutomationById JSON Parse Error: {e}")


            res_body['automationData'] = {
                "amId": automation.autId,
                "memberId": automation.autClientId,
                "amStartCondition": automation.autStartCondition,
                "amName": automation.autName,
                "amDesc": automation.autDescription,
                "amTemplateId": automation.autEmailTemplateId,
                "amGroupId": automation.autGroupId,
                "sendDateTime": int(automation.autSendDateTime.timestamp() * 1000) if automation.autSendDateTime else None,
                "startDateTime": int(automation.autStartDateTime.timestamp() * 1000) if automation.autStartDateTime else None,
                "amJSON": automation.autJsonData,
                "amStartingAction": automation.autStartAction,
                "saveStatus": automation.autSaveStatus,
                "estimatedCompletionDateTime": int(automation.autEstimatedCompletionDateTime.timestamp() * 1000) if automation.autEstimatedCompletionDateTime else None,
                "automationCampaignStatus": automation.autAutomationCampaignStatus,
                "smsFromNumber": automation.autSmsFromNumber,
                "smsFromNumberSid": automation.autSmsFromNumberSid,
                "smsGroupId": automation.autSmsGroupId,
                "smsOptinYn": automation.autSmsOptInYn
            }
            return api_response(status.HTTP_200_OK, "Fetch Automation Successfully.", res_body)
        else:
            return api_response(status.HTTP_404_NOT_FOUND, "Automation Not Found.", {})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAutomationById Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportById(request, amId):
    return getAutomationReportDashboard(request, amId)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportDashboard(request, amId):
    res_body = {}
    final_tenant_id = get_final_tenant_id(request=request)
    am_id = amId
    try:
        ac_node = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnNodeType="Trigger").first()
        if not ac_node:
            report = {
                "amId": am_id,
                "campSendId": 0,
                "error": "Trigger node not found."
            }
            res_body['campaignDetails'] = report
            res_body['conditionDetails'] = []
            res_body['withoutConditionEmail'] = []
            res_body['withoutConditionSms'] = []
            res_body['error'] = "Trigger node not found."
            return api_response(status.HTTP_200_OK, "Fetch Automation Successfully.", res_body)

        camp_send_id = ac_node.acnSendId
        report = {
            "amId": am_id,
            "campSendId": camp_send_id,
        }

        # Parse nodeDetail from trigger node
        try:
            node_detail = json.loads(ac_node.acnNodeDetail or '{}')
            report['name'] = node_detail.get('name', "")
            report['subject'] = node_detail.get('subject', "")
            report['mailingGroup'] = node_detail.get('amGroupName', "")
            report['senderName'] = node_detail.get('fromName', "")
            report['senderEmail'] = node_detail.get('fromEmail', "")
            report['sentOn'] = node_detail.get('sendDateTime', "")
        except Exception:
            report['name'] = ""
            report['subject'] = ""
            report['mailingGroup'] = ""
            report['senderName'] = ""
            report['senderEmail'] = ""
            report['sentOn'] = ""

        # Link Click Statistics
        # ... (rest of stats calculation remains similar but reordered for campaignDetails)
        
        # Initialize Counters
        total_queued = 0
        sent = 0
        delivered = 0
        opened = 0
        bounced = 0
        unread = 0
        exception = 0
        unsubscribed = 0
        total_mobile = 0
        total_desktop = 0
        unique_click_through_rate = 0
        total_click_through_rate = 0

        if camp_send_id and camp_send_id > 0:
            ces = CampaignsEmailSend.objects.filter(id=camp_send_id).first()
            if ces:
                total_queued = ces.total_queued or 0
            
            email_stats = CampaignsSendEmail.objects.filter(campSendId=camp_send_id)
            sent = email_stats.count()
            delivered = email_stats.filter(isSend='Y', isBounced='N').count()
            opened = email_stats.filter(isRead='Y').count()
            bounced = email_stats.filter(isBounced='Y').count()
            unread = max(0, delivered - opened)
            exception = email_stats.filter(isSend='Y',isBounced__in=['E','D']).count()
            unsubscribed = email_stats.filter(isUnsubscribed='Y').count()

            # Link Click Statistics
            campaign_links = CampaignLinks.objects.filter(nodeId=ac_node.acnId)
            ui = 0
            link_count_total = 0
            
            for cl in campaign_links:
                link_count_total += cl.linkCount
                total_desktop += CampaignLinkClick.objects.filter(linkId=cl.id, sources='PC').count()
                total_mobile += CampaignLinkClick.objects.filter(linkId=cl.id, sources='Phone').count()
                ui += CampaignLinkClick.objects.filter(linkId=cl.id).values_list('userId', flat=True).distinct().count()

            total_click_through_rate = link_count_total
            unique_click_through_rate = ui

        report = {
            "amId": am_id,
            "subject": report.get('subject', ""),
            "mailingGroup": report.get('mailingGroup', ""),
            "name": report.get('name', ""),
            "senderName": report.get('senderName', ""),
            "sentOn": report.get('sentOn', ""),
            "senderEmail": report.get('senderEmail', ""),
            "totalMobile": total_mobile,
            "totalDesktop": total_desktop,
            "unread": unread,
            "delivered": delivered,
            "opened": opened,
            "bounced": bounced,
            "sent": sent,
            "totalQueued": total_queued,
            "exception": exception,
            "unsubscribed": unsubscribed,
            "uniqueClickThroughRate": unique_click_through_rate,
            "totalClickThroughRate": total_click_through_rate,
            "campSendId": camp_send_id
        }
        res_body['campaignDetails'] = report
        
        # Condition Details
        condition_details = []
        old_mypage = ""
        try:
            node_detail_init = json.loads(ac_node.acnNodeDetail or '{}')
            old_mypage = node_detail_init.get('selectedEmailTemplate', {}).get('mpName', "")
        except Exception:
            pass

        flag = 0
        automation_condition_list = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnNodeType="Condition")
        for condition_node in automation_condition_list:
            node_detail_js = json.loads(condition_node.acnNodeDetail or '{}')
            if flag == 1:
                old_mypage = recursive_data(condition_node.acnSourceId, condition_node.acnMasterId, am_id)
            else:
                flag = 1
            
            auto_report = {
                "conditionType": node_detail_js.get('label', ""),
                "yes": {},
                "no": {}
            }

            # YES branch
            yes_node = AutomationCampaignNode.objects.filter(acnSourceId=condition_node.acnNodeId, acnMasterId=condition_node.acnMasterId, acnAutId=am_id, acnSourceHandle="yes").first()
            c_yes = get_default_condition_details()
            c_yes["oldMypage"] = old_mypage
            if yes_node:
                c_yes["campSendId"] = yes_node.acnSendId
                if yes_node.acnNodeType == "Email":
                    c_yes["nodeType"] = "Email"
                    y_detail = json.loads(yes_node.acnNodeDetail or '{}')
                    c_yes["subject"] = y_detail.get('subject', "")
                    c_yes["fromName"] = y_detail.get('fromName', "")
                    c_yes["fromEmail"] = y_detail.get('fromEmail', "")
                    c_yes["sendMypage"] = y_detail.get('emailTemplateSelected', {}).get('mpName', "")
                    if yes_node.acnSendId > 0:
                        c_yes.update(get_node_stats(yes_node.acnSendId, yes_node.acnId))
                elif yes_node.acnNodeType == "Sms":
                    c_yes["nodeType"] = "Sms"
                    y_detail = json.loads(yes_node.acnNodeDetail or '{}')
                    c_yes["fromNumber"] = y_detail.get('phoneNumber', {}).get('scmNumber', "")
                    c_yes["sendMypage"] = y_detail.get('smsTemplateSelected', {}).get('sstName', "")
                    if yes_node.acnSendId > 0:
                        c_yes.update(get_sms_node_stats(am_id, yes_node.acnSendId))
            auto_report["yes"] = c_yes

            # NO branch
            no_node = AutomationCampaignNode.objects.filter(acnSourceId=condition_node.acnNodeId, acnMasterId=condition_node.acnMasterId, acnAutId=am_id, acnSourceHandle="no").first()
            c_no = get_default_condition_details()
            c_no["oldMypage"] = old_mypage
            if no_node:
                c_no["campSendId"] = no_node.acnSendId
                if no_node.acnNodeType == "Email":
                    c_no["nodeType"] = "Email"
                    n_detail = json.loads(no_node.acnNodeDetail or '{}')
                    c_no["subject"] = n_detail.get('subject', "")
                    c_no["fromName"] = n_detail.get('fromName', "")
                    c_no["fromEmail"] = n_detail.get('fromEmail', "")
                    c_no["sendMypage"] = n_detail.get('emailTemplateSelected', {}).get('mpName', "")
                    if no_node.acnSendId > 0:
                        c_no.update(get_node_stats(no_node.acnSendId, no_node.acnId))
                elif no_node.acnNodeType == "Sms":
                    c_no["nodeType"] = "Sms"
                    n_detail = json.loads(no_node.acnNodeDetail or '{}')
                    c_no["fromNumber"] = n_detail.get('phoneNumber', {}).get('scmNumber', "")
                    c_no["sendMypage"] = n_detail.get('smsTemplateSelected', {}).get('sstName', "")
                    if no_node.acnSendId > 0:
                        c_no.update(get_sms_node_stats(am_id, no_node.acnSendId))
            auto_report["no"] = c_no
            
            condition_details.append(auto_report)


        res_body['conditionDetails'] = condition_details

        # Without Condition Email/Sms
        without_email_list = []
        we_nodes = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnNodeType="Email").exclude(acnSourceHandle__in=["yes", "no"])
        for we in we_nodes:
            if we.acnId == ac_node.acnId: continue
            we_stats = get_default_condition_details()
            we_stats["campSendId"] = we.acnSendId
            we_stats["nodeType"] = "Email"
            w_detail = json.loads(we.acnNodeDetail or '{}')
            we_stats["subject"] = w_detail.get('subject', "")
            we_stats["fromName"] = w_detail.get('fromName', "")
            we_stats["fromEmail"] = w_detail.get('fromEmail', "")
            we_stats["sendMypage"] = w_detail.get('emailTemplateSelected', {}).get('mpName', "")
            
            # Find old mypage
            try:
                temp_camp_send_id = we.acnSendId
                # Matches Java findPreviousCampSendIdByAmId
                prev_asc = AutomationSendContact.objects.filter(automationId=am_id, campSendId__lt=temp_camp_send_id).order_by('-id').first()
                prev_camp_send_id = prev_asc.campSendId if prev_asc else 0
                
                # Matches Java findByCampSendIdOnly(amId, tempCampSendId, "Email")
                previous_data = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnSendId=prev_camp_send_id, acnNodeType="Email").first()
                if previous_data:
                    p_detail = json.loads(previous_data.acnNodeDetail or '{}')
                    if previous_data.acnNodeType == "Trigger":
                        we_stats["oldMypage"] = p_detail.get('selectedEmailTemplate', {}).get('mpName', "")
                    else:
                        we_stats["oldMypage"] = p_detail.get('emailTemplateSelected', {}).get('mpName', "")
                else:
                    we_stats["oldMypage"] = recursive_data(we.acnSourceId, we.acnMasterId, am_id)
            except Exception:
                pass

            if we.acnSendId > 0:
                we_stats.update(get_node_stats(we.acnSendId, we.acnId))
            without_email_list.append(we_stats)
        res_body['withoutConditionEmail'] = without_email_list

        without_sms_list = []
        ws_nodes = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnNodeType="Sms").exclude(acnSourceHandle__in=["yes", "no"])
        for ws in ws_nodes:
            ws_stats = get_default_condition_details()
            ws_stats["campSendId"] = ws.acnSendId
            ws_stats["nodeType"] = "Sms"
            w_detail = json.loads(ws.acnNodeDetail or '{}')
            ws_stats["fromNumber"] = w_detail.get('phoneNumber', {}).get('scmNumber', "")
            ws_stats["sendMypage"] = w_detail.get('smsTemplateSelected', {}).get('sstName', "")
            
            # Find old mypage
            try:
                temp_camp_send_id = ws.acnSendId
                # Matches Java findPreviousCampSendIdByAmId (Sms)
                prev_asc = AutomationSendContact.objects.filter(automationId=am_id, campSendId__lt=temp_camp_send_id).order_by('-id').first()
                if not prev_asc:
                    # findPreviousSmsCampSendIdByAmId
                    prev_asc = AutomationSendContact.objects.filter(automationId=am_id).order_by('id').first()
                
                prev_camp_send_id = prev_asc.campSendId if prev_asc else 0
                previous_data = AutomationCampaignNode.objects.filter(acnAutId=am_id, acnSendId=prev_camp_send_id, acnNodeType="Sms").first()
                if previous_data:
                    p_detail = json.loads(previous_data.acnNodeDetail or '{}')
                    if previous_data.acnNodeType == "Trigger":
                        ws_stats["oldMypage"] = p_detail.get('selectedEmailTemplate', {}).get('mpName', "")
                    else:
                        ws_stats["oldMypage"] = p_detail.get('smsTemplateSelected', {}).get('sstName', "")
                else:
                    ws_stats["oldMypage"] = recursive_data(ws.acnSourceId, ws.acnMasterId, am_id)
            except Exception:
                pass

            if ws.acnSendId > 0:
                ws_stats.update(get_sms_node_stats(am_id, ws.acnSendId))
            without_sms_list.append(ws_stats)
        res_body['withoutConditionSms'] = without_sms_list


        res_body['error'] = ""
        return api_response(status.HTTP_200_OK, "Fetch Automation Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAutomationReportDashboard Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"error": str(e)})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationMyPageLinkList(request):
    final_tenant_id = get_final_tenant_id(request=request)
    my_page_id = request.query_params.get('myPageId')
    res_body = {"linkList": [], "error": ""}
    
    if not my_page_id:
        return api_response(status.HTTP_200_OK, "Fetch Automation Link List Successfully.", res_body)

    try:
        nfl = [
            "javascript:void(0);", "#dialog_1", "#dialog_2", "#dialog_3", 
            "#dialog_4", "#dialog_5", "http://www.yourgaragesale.com", 
            "http://qa.yourgaragesale.com"
        ]

        # Path logic from Java: FILE_DIRECTORY + memberId + "/images/mypage/" + myPageId +"/index.html"
        # We use FILE_UPLOAD_DIR from settings.
        # Note: FILE_UPLOAD_DIR in settings has a leading slash indicating a Linux-style path.
        # On Windows local env, we might need to handle this.
        upload_dir = settings.FILE_UPLOAD_DIR
        if os.name == 'nt' and upload_dir.startswith('/'):
            # Convert to relative to drive if possible, or assume it's relative to project root for local testing
            # But here we'll try to find it.
            # In local env, usually usercontent is inside project or at a specific path.
            # Let's hope the path mapping is handled by the OS or the server.
            pass
            
        read_path = os.path.join(upload_dir, str(final_tenant_id), "images", "mypage", str(my_page_id), "index.html")
        
        # Adjust for local Windows testing if needed (though on server it will be correct)
        if not os.path.exists(read_path) and os.name == 'nt':
            # Try a local relative path if the absolute one fails
            local_path = os.path.join(settings.BASE_DIR, "usercontent", str(final_tenant_id), "images", "mypage", str(my_page_id), "index.html")
            if os.path.exists(local_path):
                read_path = local_path

        if os.path.exists(read_path):
            with open(read_path, 'r', encoding='utf-8') as f:
                content = f.read()
                soup = BeautifulSoup(content, 'html.parser')
                tags = soup.find_all('a')
                link_list = []
                for tag in tags:
                    href_link = str(tag.get('href', ''))
                    if href_link:
                        href_lower = href_link.lower()
                        # Filtering logic exactly matching Java
                        if (href_lower not in [x.lower() for x in nfl] and 
                            settings.SITENAMESMALLCOM not in href_lower and 
                            "mailto:" not in href_lower and 
                            "tel:" not in href_lower):
                            if href_link not in link_list:
                                link_list.append(href_link)
                res_body['linkList'] = link_list
        else:
            logger.warning(f"getAutomationMyPageLinkList File not found: {read_path}")
            
        return api_response(status.HTTP_200_OK, "Fetch Automation Link List Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAutomationMyPageLinkList Error : {e}")
        res_body['error'] = "error"
        return api_response(status.HTTP_200_OK, "Fetch Automation Link List Successfully.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def stopAutomationById(request):
    final_tenant_id = get_final_tenant_id(request=request)
    aut_id = request.query_params.get('autId')
    try:
        automation = Automation.objects.filter(autId=aut_id, autClientId=get_client_id_by_tenant_id(final_tenant_id)).first()
        if automation:
            automation.autAutomationCampaignStatus = "Stop"
            automation.save()
            return api_response(status.HTTP_200_OK, "Automation Stopped Successfully.", {})
        return api_response(status.HTTP_404_NOT_FOUND, "Automation not found.", {})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] StopAutomationById Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def startAutomationById(request):
    final_tenant_id = get_final_tenant_id(request=request)
    aut_id = request.query_params.get('autId')
    try:
        automation = Automation.objects.filter(autId=aut_id, autClientId=get_client_id_by_tenant_id(final_tenant_id)).first()
        if automation:
            automation.autAutomationCampaignStatus = "Running"
            automation.save()
            return api_response(status.HTTP_200_OK, "Automation Started Successfully.", {})
        return api_response(status.HTTP_404_NOT_FOUND, "Automation not found.", {})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] StartAutomationById Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def copyAutomationById(request):
    final_tenant_id = get_final_tenant_id(request=request)
    aut_id = request.query_params.get('amId')
    try:
        source = Automation.objects.filter(
            autId=aut_id,
            autClientId=get_client_id_by_tenant_id(final_tenant_id)
        ).first()

        if not source:
            return api_response(
                status.HTTP_404_NOT_FOUND,
                "Automation not found.",
                {}
            )

        if source.autStartCondition and source.autStartCondition.lower() == "sms response automation":
            source.autAutomationCampaignStatus = "close"
            source.save()

        original_name = source.autName
        new_name = f"{original_name} Copy"
        updated_json = source.autJsonData.replace(original_name, new_name) if source.autJsonData else None

        new_auto = Automation()
        new_auto.autClientId = source.autClientId
        new_auto.autStartDateTime = timezone.now()
        new_auto.autSendDateTime = timezone.now()
        new_auto.autEstimatedCompletionDateTime = None
        new_auto.autAutomationCampaignStatus = "Running"
        new_auto.autJsonData = updated_json
        new_auto.autName = new_name
        new_auto.autSaveStatus = "draft"
        new_auto.autDescription = source.autDescription
        new_auto.autGroupId = source.autGroupId
        new_auto.autStartCondition = source.autStartCondition
        new_auto.autStartAction = source.autStartAction
        new_auto.autEmailTemplateId = source.autEmailTemplateId
        new_auto.autSmsFromNumber = source.autSmsFromNumber
        new_auto.autSmsFromNumberSid = source.autSmsFromNumberSid
        new_auto.autSmsOptInYn = source.autSmsOptInYn
        new_auto.autSmsGroupId = source.autSmsGroupId
        new_auto.save()

        if not (new_auto.autStartCondition and new_auto.autStartCondition.lower() == "sms response automation"):
            master = AutomationCampaignMaster.objects.filter(amId=aut_id).first()
            if master:
                new_master = AutomationCampaignMaster()
                new_master.myPageId = master.myPageId
                new_master.amId = new_auto.autId
                new_master.campDetail = master.campDetail
                new_master.campGroupId = master.campGroupId
                new_master.campName = new_name
                new_master.campType = master.campType
                new_master.formAdd = master.formAdd
                new_master.formName = master.formName
                new_master.isProcessed = master.isProcessed
                new_master.isSend = master.isSend
                new_master.memberId = master.memberId
                new_master.readyToSend = master.readyToSend
                new_master.replyToAdd = master.replyToAdd
                new_master.sendDate = timezone.now()
                new_master.sendOnTime = None
                new_master.subject = master.subject
                new_master.templateName = master.templateName
                new_master.save()

        return api_response(status.HTTP_200_OK, "Automation Copied Successfully.", {"autId": new_auto.autId})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] CopyAutomationById Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationBouncedReportList(request):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    cs_id = request.query_params.get('csId')
    try:
        bounced_emails = CampaignsSendEmail.objects.filter(campSendId=cs_id, isBounced='Y')
        bounced_list = []
        for cse in bounced_emails:
            bounced_list.append({
                "firstName": cse.firstName,
                "lastName": cse.lastName,
                "email": cse.email
            })
        res_body['bouncedEmailList'] = bounced_list
        return api_response(status.HTTP_200_OK, "Fetch Bounced Email Report List Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAutomationBouncedReportList Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportProductLinks(request):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    aut_id = request.query_params.get('amId')
    try:
        automation = Automation.objects.filter(autId=aut_id, autClientId=get_client_id_by_tenant_id(final_tenant_id)).first()
        
        camp_details = {"amId": aut_id, "productLinks": [], "productSources": []}
        res_body['campaignDetails'] = camp_details
        res_body['conditionDetails'] = []
        res_body['withoutConditionEmail'] = []

        if automation:
            ac_node = AutomationCampaignNode.objects.filter(acnAutId=aut_id, acnNodeType="Trigger").first()
            if ac_node:
                node_detail = json.loads(ac_node.acnNodeDetail or '{}')
                sel_template = node_detail.get('selectedEmailTemplate', {})
                old_mypage = sel_template.get('mpName', "")
                camp_send_id = ac_node.acnSendId
                
                camp_details['name'] = node_detail.get('name', "")
                camp_details['productLinks'] = get_product_links_helper(camp_send_id, ac_node.acnId)

                # Condition Details
                condition_details = []
                flag = 0
                condition_nodes = AutomationCampaignNode.objects.filter(acnAutId=aut_id, acnNodeType="Condition")
                for c_node in condition_nodes:
                    c_detail = json.loads(c_node.acnNodeDetail or '{}')
                    if flag == 1:
                        this_old_mypage = recursive_data(c_node.acnSourceId, c_node.acnMasterId, aut_id)
                    else:
                        this_old_mypage = old_mypage
                        flag = 1
                    
                    auto_report = {"conditionType": c_detail.get('label', ""), "yes": {}, "no": {}}
                    
                    # Yes Branch
                    yes_node = AutomationCampaignNode.objects.filter(acnSourceId=c_node.acnNodeId, acnMasterId=c_node.acnMasterId, acnAutId=aut_id, acnSourceHandle="yes").first()
                    if yes_node and yes_node.acnNodeType == "Email":
                        y_detail = json.loads(yes_node.acnNodeDetail or '{}')
                        y_template = y_detail.get('emailTemplateSelected', {})
                        res_links = get_product_links_helper(yes_node.acnSendId, yes_node.acnId)
                        auto_report["yes"] = {
                            "oldMypage": this_old_mypage,
                            "sendMypage": y_template.get('mpName', ""),
                            "productLinks": res_links,
                            "productSources": []
                        }
                    
                    # No Branch
                    no_node = AutomationCampaignNode.objects.filter(acnSourceId=c_node.acnNodeId, acnMasterId=c_node.acnMasterId, acnAutId=aut_id, acnSourceHandle="no").first()
                    if no_node and no_node.acnNodeType == "Email":
                        n_detail = json.loads(no_node.acnNodeDetail or '{}')
                        n_template = n_detail.get('emailTemplateSelected', {})
                        res_links = get_product_links_helper(no_node.acnSendId, no_node.acnId)
                        auto_report["no"] = {
                            "oldMypage": this_old_mypage,
                            "sendMypage": n_template.get('mpName', ""),
                            "productLinks": res_links,
                            "productSources": []
                        }
                    condition_details.append(auto_report)
                res_body['conditionDetails'] = condition_details

                # Without Condition Nodes
                without_condition_list = []
                we_nodes = AutomationCampaignNode.objects.filter(acnAutId=aut_id, acnNodeType="Email").exclude(acnSourceHandle__in=["yes", "no"])
                # The Java code has more complex logic to find "orphaned" nodes, for now exclude those with handles
                for we in we_nodes:
                    if we.acnId == ac_node.acnId: continue # Skip trigger
                    w_detail = json.loads(we.acnNodeDetail or '{}')
                    w_template = w_detail.get('emailTemplateSelected', {})
                    
                    # Find old mypage for this orphaned node
                    prev_old_mypage = ""
                    prev_node = AutomationCampaignNode.objects.filter(acnNodeId=we.acnSourceId, acnAutId=aut_id).first()
                    if prev_node:
                        if prev_node.acnNodeType == "Trigger":
                            prev_old_mypage = json.loads(prev_node.acnNodeDetail or '{}').get('selectedEmailTemplate', {}).get('mpName', "")
                        else:
                            prev_old_mypage = recursive_data(we.acnSourceId, we.acnMasterId, aut_id)

                    res_links = get_product_links_helper(we.acnSendId, we.acnId)
                    without_condition_list.append({
                        "oldMypage": prev_old_mypage,
                        "sendMypage": w_template.get('mpName', ""),
                        "productLinks": res_links,
                        "productSources": None
                    })
                res_body['withoutConditionEmail'] = without_condition_list

        return api_response(status.HTTP_200_OK, "Fetch Automation Report Product Links Successfully.", res_body)
    except Exception as e:
        logger.error(f"getAutomationReportProductLinks Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportMembersListPage(request):
    res_body = {}
    cs_id = request.query_params.get('csId')
    search_key = request.query_params.get('searchKey', '')
    node_type = request.query_params.get('nodeType', '')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 10))
    final_tenant_id = get_final_tenant_id(request=request)

    try:
        member_list = []

        if node_type == "Sms":
            queryset = AutomationSendContact.objects.filter(campSendId=cs_id)
            if search_key:
                queryset = queryset.filter(
                    Q(firstName__icontains=search_key) | 
                    Q(lastName__icontains=search_key) | 
                    Q(email__icontains=search_key) | 
                    Q(toContact__icontains=search_key)
                )
            queryset = queryset.order_by('firstName')
            paginator = Paginator(queryset, size)
            page_obj = paginator.get_page(page + 1)
            total_records = paginator.count
            total_pages = paginator.num_pages

            for asc in page_obj:
                member_list.append({
                    "firstName": asc.firstName,
                    "lastName": asc.lastName,
                    "emailId": asc.emailId,
                    "phoneNumber": asc.toContact,
                    "smsStatus": asc.smsStatus,
                    "email": asc.email if asc.email else ""
                })
        else:
            # Email logic
            automation_campaign_node = AutomationCampaignNode.objects.filter(acnSendId=cs_id).first()
            queryset = CampaignsSendEmail.objects.filter(campSendId=cs_id)
            if search_key:
                queryset = queryset.filter(
                    Q(firstName__icontains=search_key) | 
                    Q(lastName__icontains=search_key) | 
                    Q(email__icontains=search_key)
                )
            queryset = queryset.order_by('firstName')
            
            paginator = Paginator(queryset, size)
            page_obj = paginator.get_page(page + 1)
            total_records = paginator.count
            total_pages = paginator.num_pages
            
            for cse in page_obj:
                display_email = cse.email if cse.email else ""
                unsub_log = UnsubscribeLogs.objects.filter(email=cse.email, member_id=get_client_id_by_tenant_id(final_tenant_id), campaign_id=cs_id).first()
                unsubscribe_date_str = format_date_output(unsub_log.created_date) if unsub_log and unsub_log.created_date else ""

                subscriber = CampaignSubscriber.objects.filter(campId=cs_id, subId=cse.emailId).first()
                total_open = subscriber.totalOpen if subscriber else 0

                node_id = automation_campaign_node.acnId if automation_campaign_node else 0
                campaign_links = CampaignLinks.objects.filter(nodeId=node_id)
                link_ids = list(campaign_links.values_list('id', flat=True))
                
                click_stats = CampaignLinkClick.objects.filter(userId=cse.emailId, linkId__in=link_ids).aggregate(total_clicks=Sum('linkCount'))
                count_total_click = click_stats.get('total_clicks') or 0

                link_detail = []
                if count_total_click > 0:
                    for cl in campaign_links:
                        link_clicked = CampaignLinkClick.objects.filter(linkId=cl.id, userId=cse.emailId).aggregate(user_clicks=Sum('linkCount'))
                        user_clicks = link_clicked.get('user_clicks') or 0
                        if user_clicks > 0:
                            link_detail.append({
                                "link": cl.campLink,
                                "linkClicked": user_clicks
                            })

                member_list.append({
                    "firstName": cse.firstName,
                    "lastName": cse.lastName,
                    "emailId": cse.emailId,
                    "email": display_email,
                    "unsubscribeDate": unsubscribe_date_str,
                    "totalOpen": total_open,
                    "countTotalClick": count_total_click,
                    "linkDetail": link_detail
                })

        res_body['totalCampaignsSendEmail'] = total_records
        res_body['automationReportMembers'] = member_list
        res_body['getTotalPages'] = total_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        return api_response(status.HTTP_200_OK, "Fetch Automation Report Tenants List Page Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetAutomationReportMembersListPage Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportSources(request):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    aut_id = request.query_params.get('amId')
    try:
        automation = Automation.objects.filter(autId=aut_id, autClientId=get_client_id_by_tenant_id(final_tenant_id)).first()
        
        # campaignDetails initialization
        camp_details = {"amId": aut_id, "productSources": [], "productLinks": []}
        res_body['campaignDetails'] = camp_details
        res_body['conditionDetails'] = []
        res_body['withoutConditionEmail'] = []

        if automation:
            # Trigger node
            ac_node = AutomationCampaignNode.objects.filter(acnAutId=aut_id, acnNodeType="Trigger").first()
            if ac_node:
                node_detail = json.loads(ac_node.acnNodeDetail or '{}')
                sel_template = node_detail.get('selectedEmailTemplate', {})
                old_mypage_init = sel_template.get('mpName', "")
                
                camp_details['name'] = node_detail.get('name', "")
                camp_details['productSources'] = get_sources_helper(ac_node.acnId)

                # Condition Details
                condition_details = []
                flag = 0
                condition_nodes = AutomationCampaignNode.objects.filter(acnAutId=aut_id, acnNodeType="Condition", acnIsProcessed='Y', acnIsSend='Y').order_by('acnId')
                old_mypage = old_mypage_init
                for c_node in condition_nodes:
                    c_detail = json.loads(c_node.acnNodeDetail or '{}')
                    if flag == 1:
                        old_mypage = recursive_data(c_node.acnSourceId, c_node.acnMasterId, aut_id)
                    else:
                        flag = 1
                    
                    auto_report = {"conditionType": c_detail.get('label', ""), "yes": {}, "no": {}}
                    
                    # Yes Branch
                    yes_node = AutomationCampaignNode.objects.filter(acnSourceId=c_node.acnNodeId, acnMasterId=c_node.acnMasterId, acnAutId=aut_id, acnSourceHandle="yes", acnNodeType="Email").first()
                    if yes_node:
                        y_detail = json.loads(yes_node.acnNodeDetail or '{}')
                        y_template = y_detail.get('emailTemplateSelected', {})
                        res_sources = get_sources_helper(yes_node.acnId)
                        auto_report["yes"] = {
                            "oldMypage": old_mypage,
                            "sendMypage": y_template.get('mpName', ""),
                            "productLinks": [],
                            "productSources": res_sources
                        }
                    else:
                        auto_report["yes"] = {"productLinks": [], "oldMypage": old_mypage, "productSources": []}
                    
                    # No Branch
                    no_node = AutomationCampaignNode.objects.filter(acnSourceId=c_node.acnNodeId, acnMasterId=c_node.acnMasterId, acnAutId=aut_id, acnSourceHandle="no", acnNodeType="Email").first()
                    if no_node:
                        n_detail = json.loads(no_node.acnNodeDetail or '{}')
                        n_template = n_detail.get('emailTemplateSelected', {})
                        res_sources = get_sources_helper(no_node.acnId)
                        auto_report["no"] = {
                            "oldMypage": old_mypage,
                            "sendMypage": n_template.get('mpName', ""),
                            "productLinks": [],
                            "productSources": res_sources
                        }
                    else:
                        auto_report["no"] = {"productLinks": [], "oldMypage": old_mypage, "productSources": []}

                    condition_details.append(auto_report)
                res_body['conditionDetails'] = condition_details

                # Without Condition Email
                without_condition_list = []
                we_nodes = AutomationCampaignNode.objects.filter(acnAutId=aut_id, acnNodeType="Email").filter(Q(acnSourceHandle='null') | Q(acnSourceHandle__isnull=True)).order_by('acnId')
                for we in we_nodes:
                    if we.acnId == ac_node.acnId: continue # Skip if trigger is somehow marked as Email
                    
                    w_detail = json.loads(we.acnNodeDetail or '{}')
                    w_template = w_detail.get('emailTemplateSelected', {})
                    
                    # Finding old mypage for this orphaned node
                    prev_old_mypage = ""
                    prev_node = AutomationCampaignNode.objects.filter(acnNodeId=we.acnSourceId, acnAutId=aut_id).first()
                    if prev_node:
                        p_detail = json.loads(prev_node.acnNodeDetail or '{}')
                        if prev_node.acnNodeType == "Trigger":
                            prev_old_mypage = p_detail.get('selectedEmailTemplate', {}).get('mpName', "")
                        else:
                            prev_old_mypage = p_detail.get('emailTemplateSelected', {}).get('mpName', "")
                    
                    res_sources = get_sources_helper(we.acnId)
                    without_condition_list.append({
                        "oldMypage": prev_old_mypage,
                        "sendMypage": w_template.get('mpName', ""),
                        "productLinks": None,
                        "productSources": res_sources
                    })
                res_body['withoutConditionEmail'] = without_condition_list

        return api_response(status.HTTP_200_OK, "Automation Sources Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"getAutomationReportSources Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportProductLinksClickUser(request):
    res_body = {}
    link_id = request.query_params.get('linkId')
    try:
        clicks = CampaignLinkClick.objects.filter(linkId=link_id)
        user_list = []
        for click in clicks:
            cse = CampaignsSendEmail.objects.filter(emailId=click.userId).order_by('-id').first()
            if cse:
                user_list.append({
                    "userName": f"{cse.firstName} {cse.lastName}",
                    "linkCount": CampaignLinkClick.objects.filter(linkId=link_id, userId=click.userId).count()
                })
        res_body['productLinksClickUser'] = user_list
        return api_response(status.HTTP_200_OK, "Fetch Product Links Click User Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetAutomationReportProductLinksClickUser Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportMemberClick(request):
    res_body = {"productLinks": [], "technology": [], "location": [], "totalEmailOpen": 0}
    email_id = request.query_params.get('emailId')
    cs_id = request.query_params.get('csId')
    try:
        if not email_id or not cs_id:
            return api_response(status.HTTP_400_BAD_REQUEST, "Missing emailId or csId.", res_body)
        
        email_id = int(email_id)
        cs_id = int(cs_id)
        
        automation_campaign_node = AutomationCampaignNode.objects.filter(acnSendId=cs_id).first()
        if not automation_campaign_node:
            raise ValueError("AutomationCampaignNode not found for csId")
        
        total_open = CampaignSubscriber.objects.filter(campId=cs_id, subId=email_id).count()
        res_body["totalEmailOpen"] = total_open

        campaign_links_list = CampaignLinks.objects.filter(nodeId=automation_campaign_node.acnId).order_by('id')

        product_links_list = []
        for campaign_link in campaign_links_list:
            link_clicked = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id).count()
            product_links_list.append({
                "link": campaign_link.campLink,
                "linkClicked": link_clicked
            })

        technology_list = []
        for campaign_link in campaign_links_list:
            pc = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id, sources="PC").count()
            phone = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id, sources="Phone").count()
            technology_list.append({
                "id": campaign_link.id,
                "campLink": campaign_link.campLink,
                "clickThroughRate": None,
                "pc": pc,
                "mobile": phone
            })

        locations_list = []
        for campaign_link in campaign_links_list:
            campaign_links_detail_list = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id)
            for campaign_link_click in campaign_links_detail_list:
                click_date = ""
                if campaign_link_click.clickDate:
                    click_date = display_date_time(campaign_link_click.clickDate)
                city = campaign_link_click.city
                browser = get_browser_name(campaign_link_click.sourceDetails)
                locations_list.append({
                    "link": campaign_link.campLink,
                    "location": city,
                    "date": click_date,
                    "browser": browser
                })

        # Duplicating the loops as per the exact Java implementation logic
        for campaign_link in campaign_links_list:
            link_clicked = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id).count()
            product_links_list.append({
                "link": campaign_link.campLink,
                "linkClicked": link_clicked
            })

        for campaign_link in campaign_links_list:
            pc = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id, sources="PC").count()
            phone = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id, sources="Phone").count()
            technology_list.append({
                "id": campaign_link.id,
                "campLink": campaign_link.campLink,
                "clickThroughRate": None,
                "pc": pc,
                "mobile": phone
            })

        for campaign_link in campaign_links_list:
            campaign_links_detail_list = CampaignLinkClick.objects.filter(linkId=campaign_link.id, userId=email_id)
            for campaign_link_click in campaign_links_detail_list:
                click_date = ""
                if campaign_link_click.clickDate:
                    click_date = display_date_time(campaign_link_click.clickDate)
                city = campaign_link_click.city
                browser = get_browser_name(campaign_link_click.sourceDetails)
                locations_list.append({
                    "link": campaign_link.campLink,
                    "location": city,
                    "date": click_date,
                    "browser": browser
                })

        res_body["productLinks"] = product_links_list
        res_body["technology"] = technology_list
        res_body["location"] = locations_list

        return api_response(status.HTTP_200_OK, "Automation Member Information Fetched Successfully", res_body)
    except Exception as e:
        logger.error(f"GetAutomationReportMemberClick Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationReportMembersList(request):
    res_body = {}
    cs_id = request.query_params.get('csId')
    node_type = request.query_params.get('nodeType')
    try:
        tenant_id = get_final_tenant_id(request=request)
        member_list = []
        res_body["members"] = member_list
        if node_type == 'Sms':
            obj = AutomationCampaignNode.objects.filter(acnSendId=cs_id).first()
            aut_id = obj.acnAutId if obj else None
            ces = Automation.objects.get(autClientId=get_client_id_by_tenant_id(tenant_id), autId=aut_id)
            res_body['campName'] = ces.autName

            members = AutomationSendContact.objects.filter(campSendId=cs_id).order_by('firstName')
            for cse in members:
                member_list.append({
                    "firstName": cse.firstName,
                    "lastName": cse.lastName,
                    "emailId": cse.emailId,
                    "phoneNumber": cse.toContact,
                    "smsStatus":cse.smsStatus
                })

            res_body["members"] = member_list
        else:
            try:
                ces = CampaignsEmailSend.objects.get(id=cs_id)
                res_body['campName'] = ces.camp_name

                members = CampaignsSendEmail.objects.filter(campSendId=cs_id).order_by('firstName')
                for cse in members:
                    obj = Userlist.objects.filter(
                        emailId=cse.emailId,
                        memberId=cse.memberId,
                        optId=cs_id
                    ).first()
                    unsubscribe_date = obj.optDate if obj else None

                    unsubscribe_date_str = ""
                    try:
                        if unsubscribe_date is not None:
                            unsubscribe_date_str =  format_date_parity(unsubscribe_date)
                    except Exception:
                        pass

                    total_open = CampaignSubscriber.objects.filter(campId=cs_id, subId = cse.emailId).count()

                    member_list.append({
                        "firstName": cse.firstName,
                        "lastName": cse.lastName,
                        "emailId": cse.emailId,
                        "email": cse.email,
                        "unsubscribeDate": unsubscribe_date_str,
                        "totalOpen":total_open
                    })

                res_body["members"] = member_list
            except Exception as ee:
                logger.error(f"GetAutomationReportMembersList Error : {ee}")

        return api_response(status.HTTP_200_OK, "Fetch Automation Report Tenants List Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetAutomationReportMembersList Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAutomationSmsReportById(request):
    res_body = dict()
    res_body["automationSms"] = ""
    res_body["smsLogs"] = []

    try:
        # Get parameters
        tenant_id = get_final_tenant_id(request=request)
        aut_id = request.query_params.get('autId')

        if not aut_id:
            return api_response(status.HTTP_400_BAD_REQUEST, "autId is required", res_body)

        # Step 1: Fetch Automation record
        try:
            automation = Automation.objects.get(autId=aut_id, autClientId=get_client_id_by_tenant_id(tenant_id))
        except Automation.DoesNotExist:
            return api_response(status.HTTP_404_NOT_FOUND, "Automation not found", res_body)

        # Step 2: Build main automation DTO
        automation_sms_dto = dict()
        automation_sms_dto["autId" ] = automation.autId
        automation_sms_dto["autName"] = automation.autName or ""
        automation_sms_dto["autDescription"] = automation.autDescription or ""
        automation_sms_dto["autSaveStatus"] = automation.autSaveStatus or ""
        automation_sms_dto["autGroupId"] = automation.autGroupId or 0
        automation_sms_dto["autSmsFromNumber"] = getattr(automation, 'autSmsFromNumber', '')
        automation_sms_dto["autSmsFromNumberSid"] = getattr(automation, 'autSmsFromNumberSid', '')
        automation_sms_dto["autSmsOptInYn"] = getattr(automation, 'autSmsOptInYn', '')
        automation_sms_dto["autSmsGroupId"] = automation.autSmsGroupId or 0
        automation_sms_dto["groupName"] = ""

        # Step 3: Get tenant's timezone
        time_zone = get_client_timezone(tenant_id)

        # Step 5: Get SMS Group Name
        if automation.autGroupId:
            try:
                group = Groups.objects.get(grpId=automation.autGroupId)
                automation_sms_dto["groupName"] = group.grpGroupName or ""
            except:
                automation_sms_dto["groupName"] = ""

        res_body["automationSms"] = automation_sms_dto

        # Step 6: Fetch SMS Details and Reply Logs
        logs = []

        try:
            # Get all SMS details for this automation
            sms_details_list = AutomationSmsDetails.objects.filter(detSmsId=aut_id)

            for sms_detail in sms_details_list:
                detail_obj = {
                    "logReceiveReply": sms_detail.detReceiveReply or "",
                    "logs": []
                }

                # Step 7: For each detail, fetch corresponding reply logs
                try:
                    # Get reply logs for this specific received reply
                    reply_logs = AutomationSmsReplyLog.objects.filter(
                        log_sms_id=aut_id,
                        log_receive_reply = sms_detail.detReceiveReply
                    )

                    # Filter by received reply if needed
                    if sms_detail.detReceiveReply:
                        # Match logs that correspond to this reply detail
                        # Note: The relationship depends on your actual data model
                        reply_logs = reply_logs.order_by('log_id')

                    report_dtos_list = []


                    for reply_log in reply_logs:
                        # Step 8: Build report DTO for each reply log
                        report_dto = {
                            "logToNumber": reply_log.log_to_number or "",
                            "logSendReplyDetails": reply_log.log_send_reply_details or "",
                            "logFromPhone": reply_log.log_from_number or "",
                            "logCreatedDate": reply_log.log_created_date
                        }

                        # Convert received datetime to user's timezone
                        if reply_log.log_created_date:
                            try:
                                dt_str = reply_log.log_created_date.strftime("%Y-%m-%d %H:%M:%S")
                                converted_dt = convert_event_timezone_to_user_db(dt_str, "UTC", time_zone)
                                report_dto["logCreatedDate"] = converted_dt
                            except Exception as e:
                                logger.error(f"Error converting reply datetime: {e}")
                                report_dto["logCreatedDate"] = reply_log.log_created_date.strftime("%Y-%m-%d %H:%M:%S")

                        report_dtos_list.append(report_dto)

                    if report_dtos_list:
                        detail_obj["logs"] = report_dtos_list
                    else:
                        detail_obj["logs"] = []

                except Exception as e:
                    logger.error(f"Error fetching reply logs: {e}")
                    detail_obj["logs"] = []

                logs.append(detail_obj)

        except Exception as e:
            logger.error(f"Error fetching SMS details: {e}")
            logs = []

        res_body["smsLogs"] = logs

        return api_response(status.HTTP_200_OK, "Fetch Automation SMS Report Successfully.", res_body)

    except Exception as e:
        logger.error(f"[ AUT ID : {request.query_params.get('autId')} ] GetAutomationSmsReportById Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def automationSmsCloseById(request):
    aut_id = request.query_params.get('amId')
    try:
        automation = Automation.objects.filter(autId=aut_id).first()
        if automation:
            automation.autAutomationCampaignStatus = 'close'
            automation.save()
            return api_response(status.HTTP_200_OK, "Automation SMS Closed Successfully.", {})
        return api_response(status.HTTP_404_NOT_FOUND, "Automation not found.", {})
    except Exception as e:
        logger.error(f"[ AUT ID : {request.query_params.get('amId')} ] AutomationSmsCloseById Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {})
