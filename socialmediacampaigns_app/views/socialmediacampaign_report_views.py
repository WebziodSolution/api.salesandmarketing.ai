from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from common_app.decrypt_string import DecryptString
from common_app.models import (EiSocialMedia, EiSocialMediaPublish, EiSocialMediaFacebookReport, EiSocialMediaTwitterReport, EiSocialMediaLinkedinReport, EiSocialMediaLinkedinReaction, EiSocialMediaComment, Clients, EiSocialMediaFacebookReaction)
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
from requests_oauthlib import OAuth1
from datetime import datetime
import requests
import logging
import json

logger = logging.getLogger(__name__)

# Helper Functions
def format_display_date(dt):
    if not dt: return ""
    if isinstance(dt, str): return dt
    return dt.strftime("%m/%d/%Y")

def format_display_datetime(dt):
    if not dt: return ""
    if isinstance(dt, str): return dt
    return dt.strftime("%m/%d/%Y %H:%M:%S")

def uc_words(s):
    if not s: return ""
    return ' '.join(word.capitalize() for word in s.split())

# Facebook Helpers (Mirroring FacebookService)
def get_facebook_page_name(access_token, page_id):
    try:
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"fields": "id,name"}
        res = requests.get(url, headers=headers, params=params).json()
        return res.get("name", "error")
    except Exception:
        return "error"

def get_page_access_token(access_token, page_id):
    try:
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"fields": "access_token"}
        res = requests.get(url, headers=headers, params=params).json()
        return res.get("access_token", "error")
    except Exception:
        return "error"

def check_page_post(access_token, page_id, page_post_id):
    try:
        page_token = get_page_access_token(access_token, page_id)
        if page_token == "error": return "error"
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_post_id}/"
        headers = {"Authorization": f"Bearer {page_token}"}
        res = requests.get(url, headers=headers)
        return "200" if res.status_code == 200 else "error"
    except Exception:
        return "error"

def get_post_people_reached(access_token, page_id, page_post_id):
    try:
        page_token = get_page_access_token(access_token, page_id)
        if page_token == "error": return "0"
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_post_id}/insights/post_impressions"
        headers = {"Authorization": f"Bearer {page_token}"}
        res = requests.get(url, headers=headers).json()
        data = res.get("data", [])
        if data:
            values = data[0].get("values", [])
            if values:
                return str(values[0].get("value", "0"))
        return "0"
    except Exception:
        return "0"

def get_post_engagement(access_token, page_id, page_post_id):
    try:
        total_value = 0
        page_token = get_page_access_token(access_token, page_id)
        if page_token == "error": return "0"
        
        # Clicks
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_post_id}/insights/post_clicks"
        headers = {"Authorization": f"Bearer {page_token}"}
        res = requests.get(url, headers=headers).json()
        data = res.get("data", [])
        if data:
            values = data[0].get("values", [])
            if values:
                total_value += int(values[0].get("value", 0))

        # Reactions
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_post_id}/insights/post_reactions_by_type_total"
        res = requests.get(url, headers=headers).json()
        data = res.get("data", [])
        if data:
            values = data[0].get("values", [])
            if values:
                multi_value = values[0].get("value", {})
                total_value += sum(int(v) for v in multi_value.values())

        # Comments
        comments_total = get_post_comments(access_token, page_id, page_post_id, "total")
        total_value += int(comments_total)

        return str(total_value)
    except Exception:
        return "0"

def get_post_reactions(access_token, page_id, page_post_id, query_string):
    try:
        page_token = get_page_access_token(access_token, page_id)
        if page_token == "error": return "0"
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_post_id}/reactions?{query_string}"
        headers = {"Authorization": f"Bearer {page_token}"}
        res = requests.get(url, headers=headers).json()
        return str(res.get("summary", {}).get("total_count", 0))
    except Exception:
        return "0"

def get_post_comments(access_token, page_id, page_post_id, flag):
    try:
        page_token = get_page_access_token(access_token, page_id)
        if page_token == "error": return "0" if flag == "total" else "{}"
        url = f"{settings.FACEBOOK_GRAPH_URL}{page_post_id}/comments?summary=total_count"
        headers = {"Authorization": f"Bearer {page_token}"}
        res = requests.get(url, headers=headers).json()
        if flag == "total":
            return str(res.get("summary", {}).get("total_count", 0))
        else:
            return json.dumps(res)
    except Exception:
        return "0" if flag == "total" else "{}"

# Twitter Helpers
def get_tw_tweet_details(client, tweet_id):
    try:
        oauth = OAuth1(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET,
                       client.cliTwOauthtoken, client.cliTwOauthtokenSecret)
        # Using v2 API for consistency with posting
        url = f"https://api.twitter.com/2/tweets/{tweet_id}"
        params = {"tweet.fields": "public_metrics"}
        res = requests.get(url, auth=oauth, params=params)            
        try:
            data = res.json()
        except ValueError:
            logger.error(f"get_tw_tweet_details: Invalid JSON response from Twitter API: {res.text}")
            return {"retweetCount": 0, "favoriteCount": 0}

        metrics = data.get('data', {}).get('public_metrics', {})
        return {
            "retweetCount": metrics.get('retweet_count', 0),
            "favoriteCount": metrics.get('like_count', 0)
        }
    except Exception as e:
        logger.error(f"get_tw_tweet_details exception: {str(e)}")
        return {"retweetCount": 0, "favoriteCount": 0}

# LinkedIn Helpers
def get_linkedin_wall_post_details(auth_token, post_id):
    try:
        url = f"https://api.linkedin.com/v2/socialActions/{post_id}"
        headers = {"Authorization": f"Bearer {auth_token}"}
        res = requests.get(url, headers=headers).json()
        return {
            "totalComments": res.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
            "totalReactions": res.get("likesSummary", {}).get("totalLikes", 0),
            "msg": ""
        }
    except Exception:
        return {"totalComments": 0, "totalReactions": 0, "msg": "Your Social Media Post Is Deleted From Social Media Account"}

def get_linkedin_page_name_by_id(auth_token, page_id):
    try:
        url = f"https://api.linkedin.com/v2/organizations/{page_id}?projection=(localizedName)"
        headers = {"Authorization": f"Bearer {auth_token}"}
        res = requests.get(url, headers=headers).json()
        return {"pageName": res.get("localizedName", "error")}
    except Exception:
        return {"pageName": "error"}

def get_linkedin_likes_details(auth_token, post_id):
    try:
        url = f"https://api.linkedin.com/v2/socialMetadata/{post_id}"
        headers = {"Authorization": f"Bearer {auth_token}"}
        res = requests.get(url, headers=headers).json()
        summaries = res.get("reactionSummaries", {})
        return {
            "slraLikes": summaries.get("LIKE", {}).get("count", 0),
            "slraCelebrates": summaries.get("PRAISE", {}).get("count", 0),
            "slraSupports": summaries.get("APPRECIATION", {}).get("count", 0),
            "slraLoves": summaries.get("EMPATHY", {}).get("count", 0),
            "slraInsightfuls": summaries.get("INTEREST", {}).get("count", 0),
            "slraCuriouses": summaries.get("ENTERTAINMENT", {}).get("count", 0)
        }
    except Exception:
        return {k: 0 for k in ["slraLikes", "slraCelebrates", "slraSupports", "slraLoves", "slraInsightfuls", "slraCuriouses"]}

def get_linkedin_user_name_by_id(auth_token, user_id):
    try:
        url = f"https://api.linkedin.com/v2/people/id={user_id}?projection=(localizedFirstName,localizedLastName)"
        headers = {"Authorization": f"Bearer {auth_token}"}
        res = requests.get(url, headers=headers).json()
        return f"{res.get('localizedFirstName', '')} {res.get('localizedLastName', '')}".strip()
    except Exception:
        return "LinkedIn User"

def get_linkedin_comments_details(auth_token, post_id):
    try:
        url = f"https://api.linkedin.com/v2/socialActions/{post_id}/comments"
        headers = {"Authorization": f"Bearer {auth_token}"}
        res = requests.get(url, headers=headers).json()
        comment_list = []
        elements = res.get("elements", [])
        if elements:
            for obj in elements:
                actor = obj.get("actor", "")
                if "person" not in actor:
                    # Impersonator logic as in Java
                    person_id = obj.get("created", {}).get("impersonator", "").replace("urn:li:person:", "")
                else:
                    person_id = actor.replace("urn:li:person:", "")
                
                comment_list.append({
                    "scUser": get_linkedin_user_name_by_id(auth_token, person_id),
                    "scComment": obj.get("message", {}).get("text", "")
                })
            return {"msg": "", "commentList": comment_list}
        return {"msg": "No Comment Available.", "commentList": []}
    except Exception:
        return {"msg": "No Comment Available.", "commentList": []}

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSocialMediaCampaignReportListPage(request):
    tenant_id = get_final_tenant_id(request=request)
    search_key = request.GET.get('searchKey', '')
    page = int(request.GET.get('page', 0))
    size = int(request.GET.get('size', 10))
    sm_id = request.GET.get('smId', None)

    queryset = EiSocialMedia.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId=sm_id)
    if search_key:
        queryset = queryset.filter(smName__icontains=search_key)

    total_elements = queryset.count()
    start = page * size
    end = start + size
    sends = queryset.order_by('-publishDateTime')[start:end]

    report_list = []
    for send in sends:
        report_list.append({
            "smId": send.smId,
            "smName": send.smName if send else "",
            "encSsId": DecryptString.set_enc_dec_user(str(send.smId), "", "Y"),
            "ssCreatedDate": format_display_datetime(send.publishDateTime),
            "ssSendDate": format_display_datetime(send.publishDateTime)
        })

    data = {
        "getTotalPages": (total_elements + size - 1) // size if size > 0 else 0,
        "getNumber": page,
        "getSize": size,
        "countTotalSocialMediaCampaignSend": total_elements,
        "socialMediaCampaignSendList": report_list
    }
    return api_response(200, "Fetch Social Media Campaign Successfully.", data)



@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getReportFacebookPageDetails(request):
    tenant_id = get_final_tenant_id(request=request)
    sm_id = request.GET.get('smId')
    enc_ss_id = request.GET.get('encSsId')

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        sm_fb_access_token = client.cliFbAccessToken
        
        ei_sm = EiSocialMedia.objects.filter(smId=sm_id).first()
        sm_name = uc_words(ei_sm.smName if ei_sm else "")
        
        ei_publishs = EiSocialMediaPublish.objects.filter(smId=sm_id)
        
        smp_response_facebook = ""
        for ei_publish in ei_publishs:
            if ei_publish and ei_publish.smpPublishFor == "facebook":
                smp_response_facebook = ei_publish.smpResponse or ""

        facebook_page_list = []
        if smp_response_facebook:
            page_post_ids = smp_response_facebook.split(",")
            if len(page_post_ids) > 0 and page_post_ids[0] != "[]":
                for page_post_id in page_post_ids:
                    page_id_parts = page_post_id.split("_")
                    if len(page_id_parts) > 0 and page_id_parts[0] != "[]":
                        page_id = page_id_parts[0]
                        page_name = get_facebook_page_name(sm_fb_access_token, page_id)
                        if page_name != "" and page_name != "error":
                            facebook_page_list.append({
                                "pageId": page_id,
                                "pagePostId": page_post_id,
                                "pageName": page_name,
                                "smpId": sm_id,
                                "smId": sm_id,
                                "encSsId": enc_ss_id
                            })

        return api_response(200, "Fetch Facebook Page Details Successfully.", {
            "smName": sm_name,
            "facebookPageList": facebook_page_list
        })
    except Exception as e:
        logger.error(f"getReportFacebookPageDetails error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def reportFacebookPostDetails(request):
    tenant_id = get_final_tenant_id(request=request)
    data = request.data
    page_id = data.get('pageId')
    page_post_id = data.get('pagePostId')
    smp_id = data.get('smpId')
    
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        access_token = client.cliFbAccessToken

        today_dto = {
            "sfrPageId": page_id,
            "pagePostId": page_post_id,
            "sfrSmpId": smp_id,
            "sfrPeopleReached": 0,
            "sfrEngagements": 0,
            "sfrTotalReactions": 0,
            "sfrTotalComments": 0
        }

        if check_page_post(access_token, page_id, page_post_id) == "200":
            reached = get_post_people_reached(access_token, page_id, page_post_id)
            today_dto["sfrPeopleReached"] = int(reached) if reached != "error" else 0
            
            engagement = get_post_engagement(access_token, page_id, page_post_id)
            today_dto["sfrEngagements"] = int(engagement) if engagement != "error" else 0
            
            reactions = get_post_reactions(access_token, page_id, page_post_id, "summary=total_count")
            today_dto["sfrTotalReactions"] = int(reactions) if reactions != "error" else 0
            
            comments = get_post_comments(access_token, page_id, page_post_id, "total")
            today_dto["sfrTotalComments"] = int(comments) if comments != "error" else 0

        # Historical reports
        reports = EiSocialMediaFacebookReport.objects.filter(
            memberId=get_client_id_by_tenant_id(tenant_id), sfrSmpId=smp_id, sfrPageId=page_id
        ).order_by('-sfrDate')
        
        report_list = []
        for r in reports:
            report_list.append({
                "sfrId": r.sfrId,
                "tenantId": r.memberId,
                "sfrSmpId": r.sfrSmpId,
                "sfrPageId": r.sfrPageId,
                "sfrDate": format_display_date(r.sfrDate),
                "sfrPeopleReached": r.sfrPeopleReached,
                "sfrEngagements": r.sfrEngagements,
                "sfrTotalReactions": r.sfrTotalReactions,
                "sfrTotalComments": r.sfrTotalComments,
                "pagePostId": page_post_id
            })

        return api_response(200, "Fetch Facebook Post Details Successfully.", {
            "today": today_dto,
            "facebookPostList": report_list
        })
    except Exception as e:
        logger.error(f"reportFacebookPostDetails error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def reportFacebookPostReactions(request):
    tenant_id = get_final_tenant_id(request=request)
    data = request.data
    page_id = data.get('pageId')
    page_post_id = data.get('pagePostId')
    
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        access_token = client.cliFbAccessToken

        reactions_dto = {
            "sfraLikesCares": 0,
            "sfraLoves": 0,
            "sfraHahas": 0,
            "sfraWows": 0,
            "sfraSads": 0,
            "sfraAngries": 0
        }

        if data["flagType"] == "today":
            if check_page_post(access_token, page_id, page_post_id) == "200":
                reactions_dto["sfraLikesCares"] = int(get_post_reactions(access_token, page_id, page_post_id, "type=LIKE&summary=total_count"))
                reactions_dto["sfraLoves"] = int(get_post_reactions(access_token, page_id, page_post_id, "type=LOVE&summary=total_count"))
                reactions_dto["sfraHahas"] = int(get_post_reactions(access_token, page_id, page_post_id, "type=HAHA&summary=total_count"))
                reactions_dto["sfraWows"] = int(get_post_reactions(access_token, page_id, page_post_id, "type=WOW&summary=total_count"))
                reactions_dto["sfraSads"] = int(get_post_reactions(access_token, page_id, page_post_id, "type=SAD&summary=total_count"))
                reactions_dto["sfraAngries"] = int(get_post_reactions(access_token, page_id, page_post_id, "type=ANGRY&summary=total_count"))
        else:
            if data["flagType"]:
                clean_date = datetime.strptime(data["flagType"].strip(), "%m/%d/%Y").date()
                eiSocialMediaFacebookReport = EiSocialMediaFacebookReport.objects.filter(
                    memberId = client.cliId,
                    sfrPageId = page_id,
                    sfrDate__year=clean_date.year,
                    sfrDate__month=clean_date.month,
                    sfrDate__day=clean_date.day
                ).first()
                if eiSocialMediaFacebookReport:
                    eiSocialMediaFacebookReaction = EiSocialMediaFacebookReaction.objects.filter(
                        sfraSfrId = eiSocialMediaFacebookReport.sfrId
                    ).first()
                    reactions_dto["sfraLikesCares"] = eiSocialMediaFacebookReaction.sfraLikesCares if eiSocialMediaFacebookReaction else 0
                    reactions_dto["sfraLoves"] = eiSocialMediaFacebookReaction.sfraLoves if eiSocialMediaFacebookReaction else 0
                    reactions_dto["sfraHahas"] = eiSocialMediaFacebookReaction.sfraHahas if eiSocialMediaFacebookReaction else 0
                    reactions_dto["sfraWows"] = eiSocialMediaFacebookReaction.sfraWows if eiSocialMediaFacebookReaction else 0
                    reactions_dto["sfraSads"] = eiSocialMediaFacebookReaction.sfraSads if eiSocialMediaFacebookReaction else 0
                    reactions_dto["sfraAngries"] = eiSocialMediaFacebookReaction.sfraAngries if eiSocialMediaFacebookReaction else 0

        return api_response(200, "Fetch Facebook Post Reactions Successfully.", {"facebookPostReactions": reactions_dto})
    except Exception as e:
        logger.error(f"reportFacebookPostReactions error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def reportFacebookPostComments(request):
    tenant_id = get_final_tenant_id(request=request)
    data = request.data
    page_id = data.get('pageId')
    page_post_id = data.get('pagePostId')
    
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        access_token = client.cliFbAccessToken

        comments_list = []
        if check_page_post(access_token, page_id, page_post_id) == "200":
            comments_json = get_post_comments(access_token, page_id, page_post_id, "all")
            comments_data = json.loads(comments_json)
            for comment in comments_data.get('data', []):
                comments_list.append({
                    "scUser": comment.get('from', {}).get('name', 'Facebook User'),
                    "scComment": comment.get('message', '')
                })

        return api_response(200, "Fetch Facebook Post Comments Successfully.", {"facebookPostComments": comments_list})
    except Exception as e:
        logger.error(f"reportFacebookPostComments error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getReportTwitterTweetsDetails(request):
    tenant_id = get_final_tenant_id(request=request)
    sm_id = request.GET.get('smId')

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        ei_sm = EiSocialMedia.objects.filter(smId=sm_id).first()
        sm_name = uc_words(ei_sm.smName if ei_sm else "")

        ei_publishs = EiSocialMediaPublish.objects.filter(smId=sm_id)

        smp_response_twitter = ""
        for ei_publish in ei_publishs:
            if ei_publish and ei_publish.smpPublishFor == "twitter":
                smp_response_twitter = ei_publish.smpResponse or ""
                break

        today_dto = {
            "stwrTotalRetweets": 0,
            "stwrTotalLikes": 0,
            "stwrDate": "",
            "msg": ""
        }

        if smp_response_twitter:
            metrics = get_tw_tweet_details(client, smp_response_twitter)
            # Map metrics to Java DTO fields
            today_dto.update({
                "stwrTotalRetweets": metrics.get("retweetCount", 0),
                "stwrTotalLikes": metrics.get("favoriteCount", 0),
                "msg": ""
            })

        reports = EiSocialMediaTwitterReport.objects.filter(
            memberId=get_client_id_by_tenant_id(tenant_id), stwrSmpId=sm_id
        ).order_by('-stwrDate')

        report_list = []
        for r in reports:
            report_list.append({
                "stwrDate": format_display_date(r.stwrDate),
                "stwrTotalRetweets": r.stwrTotalRetweets,
                "stwrTotalLikes": r.stwrTotalLikes,
                "msg": ""
            })

        result = dict()
        result["smName"] = sm_name
        result["twitterTweetsList"] = report_list
        if smp_response_twitter:
            result["today"] = today_dto

        return api_response(200, "Fetch Twitter Details Successfully.", result)
    except Exception as e:
        logger.error(f"getReportTwitterTweetsDetails error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getReportLinkedinWallDetails(request):
    tenant_id = get_final_tenant_id(request=request)
    sm_id = request.GET.get('smId')

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        ei_sm = EiSocialMedia.objects.filter(smId=sm_id).first()
        sm_name = uc_words(ei_sm.smName if ei_sm else "")

        ei_publishs = EiSocialMediaPublish.objects.filter(smId=sm_id)

        smp_response_linkedin = ""
        linkedin_ids = ""
        smp_id = 0
        for ei_publish in ei_publishs:
            if ei_publish and ei_publish.smpPublishFor == "linkedin":
                smp_id = ei_publish.smpId
                smp_response_linkedin = ei_publish.smpResponse or ""
                linkedin_ids = ei_publish.linkdinIds or ""
                break

        # response_ids = smp_response_linkedin.split(",") if smp_response_linkedin else []    
        if smp_response_linkedin is not None:
            response_ids = smp_response_linkedin.split(",") if "," in smp_response_linkedin else [smp_response_linkedin]
        else:
            response_ids = []

        lids = linkedin_ids.split(":") if linkedin_ids else []

        post_id = ""
        if response_ids is not None and len(response_ids) > 0:
            for i, lid in enumerate(lids):
                if lid == "default" and i < len(response_ids):
                    post_id = response_ids[i]
                    break

        # for i, lid in enumerate(lids):
        #         if lid == "default" and i < len(response_ids):
        #             post_id = response_ids[i]
        #             break 
        if not post_id:
            return api_response(200, "Fetch Linkedin Wall Details Successfully.", {})

        today_data = get_linkedin_wall_post_details(client.cliLinAuthToken, post_id)
        today_data["postId"] = post_id

        reports = EiSocialMediaLinkedinReport.objects.filter(
            memberId=get_client_id_by_tenant_id(tenant_id), slrSmpId=sm_id, slrPageId='default'
        ).order_by('-slrDate')

        report_list = []
        for r in reports:
            report_list.append({
                "date": format_display_date(r.slrDate),
                "totalReactions": r.slrTotalReactions,
                "totalComments": r.slrTotalComments,
                "postId": r.slrId,
                "smpId": smp_id
            })

        return api_response(200, "Fetch Linkedin Wall Details Successfully.", {
            "smName": sm_name,
            "postId": post_id,
            "today": today_data,
            "linkedinPostList": report_list
        })
    except Exception as e:
        logger.error(f"getReportLinkedinWallDetails error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getReportLinkedinPageList(request):
    tenant_id = get_final_tenant_id(request=request)
    sm_id = request.GET.get('smId')

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        ei_sm = EiSocialMedia.objects.filter(smId=sm_id).first()
        sm_name = uc_words(ei_sm.smName if ei_sm else "")

        ei_publishs = EiSocialMediaPublish.objects.filter(smId=sm_id)

        pages = []
        auth_token = client.cliLinAuthToken

        for ei_publish in ei_publishs:
            if ei_publish and ei_publish.smpPublishFor == "linkedin":
                smp_id = ei_publish.smpId
                response_ids = (ei_publish.smpResponse or "").split(",") if ei_publish.smpResponse is not None else []
                lids = (ei_publish.linkdinIds or "").split(":")

                if response_ids is not None and len(response_ids) > 0:
                    for i, lid in enumerate(lids):
                        if lid and lid != "default" and i < len(response_ids):
                            page_name_res = get_linkedin_page_name_by_id(auth_token, lid)
                            pages.append({
                                "pageId": lid,
                                "responseId": response_ids[i],
                                "smpId": smp_id,
                                "pageName": page_name_res.get("pageName", "Unknown Page")
                            })

        res_body = {
            "smName": sm_name,
            "linkedinPageList": pages
        }
        return api_response(200, "Fetch Linkedin Page List Successfully.", res_body)
    except Exception as e:
        logger.error(f"getReportLinkedinPageList error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getReportLinkedinPageDetails(request):
    tenant_id = get_final_tenant_id(request=request)
    smp_id = request.GET.get('smpId')
    page_id = request.GET.get('pageId')
    response_id = request.GET.get('responseId')

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        today_data = get_linkedin_wall_post_details(client.cliLinAuthToken, response_id)
        today_data["postId"] = response_id

        reports = EiSocialMediaLinkedinReport.objects.filter(
            memberId=get_client_id_by_tenant_id(tenant_id), slrSmpId=smp_id, slrPageId=page_id
        ).order_by('-slrDate')

        report_list = []
        for r in reports:
            report_list.append({
                "date": format_display_date(r.slrDate),
                "totalReactions": r.slrTotalReactions,
                "totalComments": r.slrTotalComments,
                "postId": r.slrId
            })

        return api_response(200, "Fetch Linkedin Page Details Successfully.", {
            "today": today_data,
            "linkedinPostList": report_list
        })
    except Exception as e:
        logger.error(f"getReportLinkedinPageDetails error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getReportLinkedinReactionReport(request):
    tenant_id = get_final_tenant_id(request=request)
    post_id = request.GET.get('postId')
    mode = request.GET.get('flagType')

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        if mode == "today":
            res_body = get_linkedin_likes_details(client.cliLinAuthToken, post_id)
        else:
            reaction = EiSocialMediaLinkedinReaction.objects.filter(
                memberId=get_client_id_by_tenant_id(tenant_id), slraSlrId=post_id
            ).first()
            if reaction:
                res_body = {
                    "slraLikes": reaction.slraLikes,
                    "slraCelebrates": reaction.slraCelebrates,
                    "slraSupports": reaction.slraSupports,
                    "slraLoves": reaction.slraLoves,
                    "slraInsightfuls": reaction.slraInsightfuls,
                    "slraCuriouses": reaction.slraCuriouses
                }
            else:
                res_body = {k: 0 for k in ["slraLikes", "slraCelebrates", "slraSupports", "slraLoves", "slraInsightfuls", "slraCuriouses"]}

        return api_response(200, "Fetch Linkedin Reaction Report Successfully.", res_body)
    except Exception as e:
        logger.error(f"getReportLinkedinReactionReport error: {str(e)}")
        return api_response(500, str(e), {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getReportLinkedinCommentsReport(request):
    tenant_id = get_final_tenant_id(request=request)
    post_id = request.GET.get('postId')
    mode = request.GET.get('flagType')

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        if mode == "today":
            res_body = get_linkedin_comments_details(client.cliLinAuthToken, post_id)
        else:
            comments = EiSocialMediaComment.objects.filter(
                scParentId=post_id
            )
            comment_list = []
            for c in comments:
                comment_list.append({
                    "scUser": c.scUser,
                    "scComment": c.scComment
                })
            
            res_body = {
                "msg": "" if comment_list else "No Comment Available.",
                "commentList": comment_list
            }

        return api_response(200, "Fetch Linkedin Comments Report Details Successfully.", res_body)
    except Exception as e:
        logger.error(f"getReportLinkedinCommentsReport error: {str(e)}")
        return api_response(500, str(e), {})
