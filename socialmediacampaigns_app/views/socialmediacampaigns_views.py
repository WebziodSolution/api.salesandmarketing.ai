import os
import re
import logging
import requests
import shutil
import base64
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.models import EiSocialMedia, EiSocialMediaPublish, Clients
from common_app.utils import api_response, convert_event_timezone_to_user_db, get_final_tenant_id, get_client_id_by_tenant_id
from socialmediacampaigns_app.serializers import (DeleteSocialMediaPostDtoSerializer, UploadFileOrPicDtoSerializer, EiSocialMediaDtoSerializer)
from socialmediacampaigns_app.views.facebook_views import set_facebook_post_internal, set_facebook_image_post_internal
from socialmediacampaigns_app.views.twitter_views import set_twitter_post_internal, set_twitter_image_post_internal
from socialmediacampaigns_app.views.linkedin_views import set_linkedin_post_internal, set_linkedin_image_post_internal

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def postNow(request):
    tenant_id = get_final_tenant_id(request=request)
    client = Clients.objects.get(cliTenantId=tenant_id)
    res, camp = general_save(tenant_id, request.data)
    if res.get('error') != "" or not camp:
        return api_response(400, res.get('message', 'Error occurred'))
    
    last_id = res.get('lastId')
    smp_id_f = 0
    smp_id_t = 0
    smp_id_li = 0
    last_id_smp = ""

    if request.data.get('smId') and int(request.data.get('smId')) > 0:
        save_data = get_save_data(tenant_id, last_id)
        smp_id_f = save_data.get('smpIdF', 0)
        smp_id_t = save_data.get('smpIdT', 0)
        smp_id_li = save_data.get('smpIdLi', 0)

    social_media_path = f"{settings.IMAGE_SITE_URL}{settings.EAS_DRIVE_NAME}/{tenant_id}/images/socialmedia/"
    image_list = []
    if camp.smPostImage and camp.smPostImage.strip() != "":
        img_list = camp.smPostImage.split(',')
        for img in img_list:
            image_list.append(f"{social_media_path}{img}")

    video_fb_condition = bool(camp.smPostVideoFacebook and camp.smPostVideoFacebook.strip() != "")
    video_tw_condition = bool(camp.smPostVideoTwitter and camp.smPostVideoTwitter.strip() != "")
    video_li_condition = bool(camp.smPostVideoLinkedin and camp.smPostVideoLinkedin.strip() != "")

    # Facebook
    if camp.smFacebookPost:
        try:
            if client.cliFbId and client.cliFbAccessToken:
                post_id_list = ""
                if len(image_list) > 0:
                    fb_res = set_facebook_image_post_internal(client, camp.smFacebookPost, image_list)
                    # post_id_list = json.dumps(fb_res.get('responses', fb_res.get('message', '')))
                    post_id_list = fb_res.get('responses')
                elif not video_fb_condition:
                    fb_res = set_facebook_post_internal(client, camp.smFacebookPost, request.data.get('facebookPostLink'))
                    post_id_list = fb_res.get('responses')
                
                publish = None
                if smp_id_f > 0:
                    publish = EiSocialMediaPublish.objects.filter(smpId=smp_id_f).first()
                
                if not publish:
                    publish = EiSocialMediaPublish(memberId=get_client_id_by_tenant_id(tenant_id), smId=last_id, smpPublishFor='facebook')
                
                publish.smpPublishData = camp.smFacebookPost
                publish.smpPublishLink = request.data.get('facebookPostLink')
                publish.smpPublishImage = camp.smPostImage
                if video_fb_condition:
                    publish.hasVideo = 'Y'
                    publish.smpPublishVideoFacebook = camp.smPostVideoFacebook
                
                publish.smpResponse = post_id_list
                publish.smpStatus = 1
                publish.smpPublishDateTime = timezone.now()
                publish.smpScheduleDateTime = timezone.now()
                publish.save()
                last_id_smp += f"{publish.smpId},"
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] PostNow Facebook Error : {e}")

    # Twitter
    if camp.smTwitterPost:
        try:
            if client.cliTwOauthtoken and client.cliTwOauthtokenSecret:
                post_id_list = ""
                if len(image_list) > 0:
                    tw_res = set_twitter_image_post_internal(client, camp.smTwitterPost, image_list)
                    post_id_list = tw_res.get('postId') if tw_res.get('status') == 'success' else tw_res.get('message', '')
                elif not video_tw_condition:
                    tw_res = set_twitter_post_internal(client, camp.smTwitterPost)
                    post_id_list = tw_res.get('postId') if tw_res.get('status') == 'success' else tw_res.get('message', '')
                
                publish = None
                if smp_id_t > 0:
                    publish = EiSocialMediaPublish.objects.filter(smpId=smp_id_t).first()
                
                if not publish:
                    publish = EiSocialMediaPublish(memberId=get_client_id_by_tenant_id(tenant_id), smId=last_id, smpPublishFor='twitter')
                
                publish.smpPublishData = camp.smTwitterPost
                publish.smpPublishLink = request.data.get('twitterPostLink')
                publish.smpPublishImage = camp.smPostImage
                if video_tw_condition:
                    publish.hasVideo = 'Y'
                    publish.smpPublishVideoTwitter = camp.smPostVideoTwitter
                
                publish.smpResponse = post_id_list
                publish.smpStatus = 1
                publish.smpPublishDateTime = timezone.now()
                publish.smpScheduleDateTime = timezone.now()
                publish.save()
                last_id_smp += f"{publish.smpId},"
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] PostNow Twitter Error : {e}")

    # LinkedIn
    if camp.smLinkedinPost:
        try:
            if client.cliLinAuthToken and client.cliLinExpiresAt:
                post_id_list = ""
                if len(image_list) > 0:
                    li_res = set_linkedin_image_post_internal(client, camp.smLinkedinPost, image_list[0], request.data.get('linkedinSendTo', ''), "")
                    post_id_list = li_res.get('postIds', li_res.get('message', ''))
                elif not video_li_condition:
                    li_res = set_linkedin_post_internal(client, camp.smLinkedinPost, request.data.get('linkedinPostLink'), request.data.get('linkedinSendTo', ''), "")
                    post_id_list = li_res.get('postIds', li_res.get('message', ''))
                
                publish = None
                if smp_id_li > 0:
                    publish = EiSocialMediaPublish.objects.filter(smpId=smp_id_li).first()
                
                if not publish:
                    publish = EiSocialMediaPublish(memberId=get_client_id_by_tenant_id(tenant_id), smId=last_id, smpPublishFor='linkedin')
                
                publish.smpPublishData = camp.smLinkedinPost
                publish.smpPublishLink = request.data.get('linkedinPostLink')
                publish.smpPublishImage = camp.smPostImage
                if video_li_condition:
                    publish.hasVideo = 'Y'
                    publish.smpPublishVideoLinkedin = camp.smPostVideoLinkedin
                
                publish.smpResponse = post_id_list
                publish.smpStatus = 1
                publish.smpPublishDateTime = timezone.now()
                publish.smpScheduleDateTime = timezone.now()
                publish.linkdinIds = request.data.get('linkedinSendTo')
                publish.save()
                last_id_smp += f"{publish.smpId},"
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] PostNow LinkedIn Error : {e}")

    return api_response(200, "Your Post Published Successfully", {"smId": last_id})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSocialMediaAuthData(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        data = {
            "isFacebookAuth": "Y" if client.cliFbAccessToken else "N",
            "isTwitterAuth": "Y" if client.cliTwOauthtoken else "N",
            "isLinkedinAuth": "Y" if client.cliLinAuthToken else "N"
        }
        return api_response(200, "Auth data fetched successfully", data)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetAuthData Error : {e}")
        fallback = {"isFacebookAuth": "N", "isTwitterAuth": "N", "isLinkedinAuth": "N"}
        return api_response(200, "Auth data fetched successfully", fallback)

logger = logging.getLogger(__name__)

def display_date(dt):
    if not dt:
        return None
    return dt.strftime("%m/%d/%Y")

def display_date_time(dt):
    if not dt:
        return None
    return dt.strftime("%m/%d/%Y %H:%M:%S")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSocialMediaCampaignList(request):
    tenant_id = get_final_tenant_id(request=request)
    
    # Query parameters for pagination, sorting and filtering
    search_key = request.GET.get('searchKey', '')
    page_num = int(request.GET.get('page', 0))
    page_size = int(request.GET.get('size', 25))
    sort_param = request.GET.get('sort', 'smId,desc')
    timeZone = request.GET.get('timeZone', 'UTC')
    
    try:
        queryset = EiSocialMedia.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id))
        
        # Filtering by smName if searchKey is provided
        if search_key:
            queryset = queryset.filter(smName__icontains=search_key)
            
        # Sorting
        if sort_param:
            try:
                sort_field, sort_order = sort_param.split(',')
                if sort_order.lower() == 'desc':
                    queryset = queryset.order_by(f'-{sort_field}')
                else:
                    queryset = queryset.order_by(sort_field)
            except ValueError:
                queryset = queryset.order_by('-smId')
        else:
            queryset = queryset.order_by('-smId')
            
        total_count = EiSocialMedia.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id)).count()
        filtered_count = queryset.count()
        total_pages = (filtered_count + page_size - 1) // page_size if page_size > 0 else 1
        
        # Pagination
        start = page_num * page_size
        end = start + page_size
        campaigns = queryset[start:end]
        
        data_list = []
        for camp in campaigns:
            dto = EiSocialMediaDtoSerializer(camp).data
            
            # Replace empty strings with None to match Java nulls
            for key in dto:
                if dto[key] == "":
                    dto[key] = None
            
            # Status logic from Java SocialMediaCampaignServiceImpl.java
            status_str = "Published" # Default
            if camp.publishType == "saveasdraft":
                status_str = "Drafted"
            elif camp.publishType == "schedule":
                publish_rec = EiSocialMediaPublish.objects.filter(smId=camp.smId, smpScheduleDateTime__gt=timezone.now()).order_by('-smpId').first()
                if publish_rec and publish_rec.smpScheduleDateTime:
                    status_str = "Scheduled"
                    smp_dt_str = publish_rec.smpScheduleDateTime.strftime("%Y-%m-%d %H:%M:%S")
                    converted_dt_str = convert_event_timezone_to_user_db(smp_dt_str, "UTC", timeZone)
                    converted_dt = datetime.strptime(converted_dt_str, "%Y-%m-%d %H:%M:%S")
                    dto['smpScheduleDateTime'] = display_date_time(converted_dt)
                else:
                    status_str = "Published"
                    dto['smpScheduleDateTime'] = None
            elif camp.publishType == "postNow":
                status_str = "Published"
            
            dto['status'] = status_str
            dto['publishDateTime'] = display_date(camp.publishDateTime)
            data_list.append(dto)
            
        res_body = {
            "getNumber": page_num,
            "getSize": page_size,
            "totalCampaign": total_count,
            "socialMediaCampaign": data_list,
            "getTotalPages": total_pages
        }
            
        return api_response(200, "Fetch Social Media Campaign Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetSocialMediaCampaignList Error : {e}")
        # Return empty pagination structure on error to match expected structure
        res_body = {
            "getNumber": page_num,
            "getSize": page_size,
            "totalCampaign": 0,
            "socialMediaCampaign": [],
            "getTotalPages": 0
        }
        return api_response(200, "Fetch Social Media Campaign Successfully.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSocialMediaCampaign(request):
    tenant_id = get_final_tenant_id(request=request)
    sm_id = request.GET.get('smId')
    timeZone = request.GET.get('timeZone', 'UTC')
    try:
        camp = EiSocialMedia.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId=sm_id).first()
        if not camp:
            return api_response(404, "Campaign not found")
            
        dto = EiSocialMediaDtoSerializer(camp).data
        
        # Replace empty strings with None to match Java nulls
        for key in dto:
            if dto[key] == "":
                dto[key] = None
        
        status_str = "Published"
        if camp.publishType == "saveasdraft":
            status_str = "Drafted"
        elif camp.publishType == "schedule":
            publish_rec = EiSocialMediaPublish.objects.filter(smId=camp.smId, smpScheduleDateTime__gt=timezone.now()).order_by('-smpId').first()
            if publish_rec and publish_rec.smpScheduleDateTime:
                status_str = "Scheduled"
                smp_dt_str = publish_rec.smpScheduleDateTime.strftime("%Y-%m-%d %H:%M:%S")
                converted_dt_str = convert_event_timezone_to_user_db(smp_dt_str, "UTC", timeZone)
                converted_dt = datetime.strptime(converted_dt_str, "%Y-%m-%d %H:%M:%S")
                dto['smpScheduleDateTime'] = display_date_time(converted_dt)
            else:
                status_str = "Published"
                dto['smpScheduleDateTime'] = ""
        elif camp.publishType == "postNow":
            status_str = "Published"
            
        dto['status'] = status_str
        dto['publishDateTime'] = display_date(camp.publishDateTime)
        if dto.get('smpScheduleDateTime') is None:
            dto['smpScheduleDateTime'] = ""
                
        return api_response(200, "Fetch Social Media Campaign Successfully.", {"socialMediaCampaign": dto})
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetSocialMediaCampaign Error : {e}")
        return api_response(500, "Error fetching campaign")

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSocialMediaPost(request):
    tenant_id = get_final_tenant_id(request=request)
    serializer = DeleteSocialMediaPostDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid IDs")
    
    ids = serializer.validated_data['smId']
    try:
        EiSocialMedia.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId__in=ids).delete()
        EiSocialMediaPublish.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId__in=ids).delete()
        return api_response(200, "Post deleted successfully")
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] DeleteSocialMediaPost Error : {e}")
        return api_response(500, "Error deleting post")

def get_save_data(tenant_id, sm_id):
    res_body = {
        "editFSmpResponse": "", "smpIdF": 0,
        "editTSmpResponse": "", "smpIdT": 0,
        "editLiSmpResponse": "", "smpIdLi": 0,
        "ssId": 0
    }
    try:
        f_pub = EiSocialMediaPublish.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId=sm_id, smpPublishFor='facebook').order_by('-smpId').first()
        if f_pub:
            res_body["smpIdF"] = f_pub.smpId
            res_body["editFSmpResponse"] = f_pub.smpResponse or ""
            
        t_pub = EiSocialMediaPublish.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId=sm_id, smpPublishFor='twitter').order_by('-smpId').first()
        if t_pub:
            res_body["smpIdT"] = t_pub.smpId
            res_body["editTSmpResponse"] = t_pub.smpResponse or ""
            
        li_pub = EiSocialMediaPublish.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId=sm_id, smpPublishFor='linkedin').order_by('-smpId').first()
        if li_pub:
            res_body["smpIdLi"] = li_pub.smpId
            res_body["editLiSmpResponse"] = li_pub.smpResponse or ""
            
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetSaveData Error : {e}")
    
    return res_body

def general_save(tenant_id, data):
    sm_id = data.get('smId')
    sm_name = data.get('smName', '')
    
    if sm_name == "":
        return {"status": "error", "message": "Please Enter Name Of Post."}, None

    sm_facebook_post = data.get('smFacebookPost', '')
    sm_twitter_post = data.get('smTwitterPost', '')
    sm_linkedin_post = data.get('smLinkedinPost', '')

    if sm_facebook_post == "" and sm_twitter_post == "" and sm_linkedin_post == "":
        return {"status": "error", "message": "Select At Least One Social Media Profile And Put Content For Post."}, None

    existing_sm_id = 0
    try:
        existing_sm = EiSocialMedia.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smName=sm_name).first()
        if existing_sm:
            existing_sm_id = existing_sm.smId
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GeneralSave Error 1: {e}")

    if existing_sm_id == 0 or (sm_id and int(sm_id) > 0):
        if sm_id and int(sm_id) > 0:
            camp = EiSocialMedia.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId=sm_id).first()
            if not camp:
                return {"status": "error", "message": "Campaign not found"}, None
        else:
            camp = EiSocialMedia(memberId=get_client_id_by_tenant_id(tenant_id), smName=sm_name)
            camp.publishDateTime = timezone.now()

        camp.smName = sm_name
        camp.publishType = data.get('publishType')
        camp.publishStatus = 0
        camp.smFacebookPost = sm_facebook_post
        camp.smTwitterPost = sm_twitter_post
        camp.smLinkedinPost = sm_linkedin_post
        camp.smPostImage = data.get('smPostImage')
        camp.smPostVideoFacebook = data.get('smPostVideoFacebook')
        camp.smPostVideoTwitter = data.get('smPostVideoTwitter')
        camp.smPostVideoLinkedin = data.get('smPostVideoLinkedin')
        camp.save()
        return {"status": "success", "smId": camp.smId, "lastId": camp.smId, "error": ""}, camp
    else:
        return {"status": "error", "message": "Name Of Post Are Already Exist.", "error": "Name Of Post Are Already Exist."}, None

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveAsDraft(request):
    tenant_id = get_final_tenant_id(request=request)
    res, camp = general_save(tenant_id, request.data)
    if res.get('status') == 'error':
        return api_response(400, res.get('message', 'Error saving draft'))
    return api_response(200, "Your Post Save Successfully", res)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSchedule(request):
    tenant_id = get_final_tenant_id(request=request)
    client = Clients.objects.get(cliTenantId=tenant_id)
    res, camp = general_save(tenant_id, request.data)
    if res.get('error') != "" or not camp:
        return api_response(400, res.get('message', 'Error occurred'))
    
    last_id = res.get('lastId')
    smp_id_f = 0
    smp_id_t = 0
    smp_id_li = 0
    last_id_smp = ""

    if request.data.get('smId') and int(request.data.get('smId')) > 0:
        save_data = get_save_data(tenant_id, last_id)
        smp_id_f = save_data.get('smpIdF', 0)
        smp_id_t = save_data.get('smpIdT', 0)
        smp_id_li = save_data.get('smpIdLi', 0)

    sched_dt_str = request.data.get('smpScheduleDateTime')
    sched_dt = None
    if sched_dt_str:
        try:
            # Assuming format: MM/dd/yyyy HH:mm:ss
            # First convert to yyyy-MM-dd HH:mm:ss for convert_event_timezone_to_user_db
            dt_obj = datetime.strptime(sched_dt_str, "%m/%d/%Y %H:%M:%S")
            db_date_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            user_tz = request.data.get('timeZone', 'UTC')
            utc_date_str = convert_event_timezone_to_user_db(db_date_str, user_tz, "UTC")
            sched_dt = datetime.strptime(utc_date_str, "%Y-%m-%d %H:%M:%S")
            if timezone.is_naive(sched_dt):
                sched_dt = timezone.make_aware(sched_dt)
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] SaveSchedule Date Parsing Error : {e}")

    # Facebook
    if camp.smFacebookPost:
        try:
            if client.cliFbId and client.cliFbAccessToken:
                if client.cliFbId.strip() != "" and client.cliFbAccessToken.strip() != "":
                    publish = None
                    if smp_id_f > 0:
                        publish = EiSocialMediaPublish.objects.filter(smpId=smp_id_f).first()
                    if not publish:
                        publish = EiSocialMediaPublish(memberId=get_client_id_by_tenant_id(tenant_id), smId=last_id, smpPublishFor='facebook')
                    
                    publish.smpPublishData = camp.smFacebookPost
                    publish.smpPublishLink = request.data.get('facebookPostLink')
                    publish.smpPublishImage = camp.smPostImage
                    publish.smpPublishVideoFacebook = camp.smPostVideoFacebook
                    if camp.smPostVideoFacebook:
                        publish.hasVideo = 'Y'
                    publish.smpResponse = None
                    publish.smpStatus = 0
                    publish.smpScheduleDateTime = sched_dt
                    publish.save()
                    last_id_smp += f"{publish.smpId},"
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] SaveSchedule Facebook Error : {e}")

    # Twitter
    if camp.smTwitterPost:
        try:
            if client.cliTwOauthtoken and client.cliTwOauthtokenSecret:
                if client.cliTwOauthtoken.strip() != "" and client.cliTwOauthtokenSecret.strip() != "":
                    publish = None
                    if smp_id_t > 0:
                        publish = EiSocialMediaPublish.objects.filter(smpId=smp_id_t).first()
                    if not publish:
                        publish = EiSocialMediaPublish(memberId=get_client_id_by_tenant_id(tenant_id), smId=last_id, smpPublishFor='twitter')
                    
                    publish.smpPublishData = camp.smTwitterPost
                    publish.smpPublishLink = request.data.get('twitterPostLink')
                    publish.smpPublishImage = camp.smPostImage
                    publish.smpPublishVideoTwitter = camp.smPostVideoTwitter
                    if camp.smPostVideoTwitter:
                        publish.hasVideo = 'Y'
                    publish.smpResponse = None
                    publish.smpStatus = 0
                    publish.smpScheduleDateTime = sched_dt
                    publish.save()
                    last_id_smp += f"{publish.smpId},"
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] SaveSchedule Twitter Error : {e}")

    # LinkedIn
    if camp.smLinkedinPost:
        try:
            if client.cliLinAuthToken and client.cliLinExpiresAt:
                if client.cliLinAuthToken.strip() != "" and client.cliLinExpiresAt.strip() != "":
                    publish = None
                    if smp_id_li > 0:
                        publish = EiSocialMediaPublish.objects.filter(smpId=smp_id_li).first()
                    if not publish:
                        publish = EiSocialMediaPublish(memberId=get_client_id_by_tenant_id(tenant_id), smId=last_id, smpPublishFor='linkedin')
                    
                    publish.smpPublishData = camp.smLinkedinPost
                    publish.smpPublishLink = request.data.get('linkedinPostLink')
                    publish.smpPublishImage = camp.smPostImage
                    publish.smpPublishVideoLinkedin = camp.smPostVideoLinkedin
                    if camp.smPostVideoLinkedin:
                        publish.hasVideo = 'Y'
                    publish.smpResponse = None
                    publish.smpStatus = 0
                    publish.smpScheduleDateTime = sched_dt
                    publish.linkdinIds = request.data.get('linkedinSendTo')
                    publish.save()
                    last_id_smp += f"{publish.smpId},"
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] SaveSchedule LinkedIn Error : {e}")

    return api_response(200, "Your Post Scheduled Successfully", {"smId": last_id})

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def editSocialMediaPostSchedule(request):
    tenant_id = get_final_tenant_id(request=request)
    sm_id = request.data.get('smId')
    sched_dt_str = request.data.get('smpScheduleDateTime')
    user_tz = request.data.get('timeZone', 'UTC')
    
    try:
        # Parsing format MM/dd/yyyy HH:mm:ss
        dt_obj = datetime.strptime(sched_dt_str, "%m/%d/%Y %H:%M:%S")
        db_date_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
        
        # Convert to UTC for DB storage
        utc_date_str = convert_event_timezone_to_user_db(db_date_str, user_tz, "UTC")
        sched_dt = datetime.strptime(utc_date_str, "%Y-%m-%d %H:%M:%S")
        
        if timezone.is_naive(sched_dt):
            sched_dt = timezone.make_aware(sched_dt)
            
        EiSocialMediaPublish.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), smId=sm_id).update(smpScheduleDateTime=sched_dt)
        return api_response(200, "Schedule updated successfully")
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] EditSchedule Error : {e}")
        return api_response(500, "Error updating schedule")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getLinkPreview(request):
    url = request.GET.get('url', '').strip()
    res_body = {"message": "", "status": False}
    try:
        if url:
            request_url = f"https://meta.mehari.workers.dev/?url={url}"
            headers = {"Content-Type": "application/json", "user-agent": "Application"}
            response = requests.post(request_url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                res_body = {
                    "url": url,
                    "siteName": data.get("siteName", ""),
                    "title": data.get("title", ""),
                    "image": data.get("image", ""),
                    "description": data.get("description", ""),
                    "img": data.get("image", ""),
                    "oUrl": url,
                    "message": "",
                    "status": True
                }
                return api_response(200, "Fetch Link Preview Successfully", res_body)
            else:
                res_body["message"] = "Can't reach the server for the given url"
        else:
            res_body["message"] = "URL is required"
    except Exception as e:
        logger.error(f"GetLinkPreview Error : {e}")
        res_body["message"] = str(e)
    
    return api_response(200, "Fetch Link Preview Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSocialMediaAuthentication(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        res_body = {
            "facebook": False,
            "twitter": False,
            "linkedin": False
        }
        
        if client.cliFbId and client.cliFbAccessToken:
            if client.cliFbId.strip() and client.cliFbAccessToken.strip():
                res_body["facebook"] = True
                
        if client.cliTwOauthtoken and client.cliTwOauthtokenSecret:
            if client.cliTwOauthtoken.strip() and client.cliTwOauthtokenSecret.strip():
                res_body["twitter"] = True
                
        if client.cliLinAuthToken and client.cliLinExpiresAt:
            if client.cliLinAuthToken.strip() and client.cliLinExpiresAt.strip():
                res_body["linkedin"] = True
                
        return api_response(200, "Fetch Social Media Authentication Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] GetSocialMediaAuthentication Error : {e}")
        return api_response(500, "Internal Server Error")

def handle_file_upload(request, file_type_key):
    tenant_id = get_final_tenant_id(request=request)
    serializer = UploadFileOrPicDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    upload_dto = serializer.validated_data
    file_data = upload_dto.get('file', '')
    if not file_data or file_data == "":
        return api_response(500, "Request must contains file")

    
    # Matching Java: CommonFunction.renameFileName(uploadFileOrPicDto.getFileName())
    original_filename = upload_dto.get('fileName', 'file')
    # Java logic: fileName.replaceAll("[^a-zA-Z0-9\\.\\-]+", "_")
    original_filename = re.sub(r'[^a-zA-Z0-9.\-]+', '_', original_filename)
    
    base_dir = os.path.join(settings.EAS_DRIVE_PATH, str(tenant_id), "images", "socialmedia")
    os.makedirs(base_dir, exist_ok=True)
    
    file_path = os.path.join(base_dir, original_filename)
    
    # Java: fileData.replaceAll("data:" + uploadFileOrPicDto.getFileType() + ";base64,", "").replaceAll(" ", "");
    file_type = upload_dto.get('fileType', '')
    if file_type:
        prefix = f"data:{file_type};base64,"
        if file_data.startswith(prefix):
            file_data = file_data[len(prefix):]
    file_data = file_data.replace(" ", "")
    
    try:
        decoded_bytes = base64.b64decode(file_data)
        with open(file_path, "wb") as f:
            f.write(decoded_bytes)
            
        # Java: Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rw-r--r--"));
        if os.name != 'nt':
             os.chmod(file_path, 0o644)
             
        save_path = f"{settings.IMAGE_SITE_URL}{settings.EAS_DRIVE_NAME}/{tenant_id}/images/socialmedia/{original_filename}"
        
        res_body = {
            f"{file_type_key}Path": save_path,
            f"{file_type_key}Name": original_filename
        }
        message = "The Image Uploaded Successfully" if file_type_key == "image" else "The Video Uploaded Successfully"
        return api_response(200, message, res_body)
        
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] Upload{file_type_key.capitalize()} Error : {e}")
        return api_response(500, "Internal Server Error")

def handle_file_upload_chunked(request, file_type_key):
    tenant_id = get_final_tenant_id(request=request)
    upload_id = request.data.get('uploadId')
    chunk_index = request.data.get('chunkIndex')
    total_chunks = request.data.get('totalChunks')
    file_name = request.data.get('fileName')
    file_data = request.data.get('fileData') # Base64 chunk
    
    if not all([file_name, file_data, chunk_index is not None, total_chunks is not None]):
        return api_response(400, "Missing required chunked upload parameters")

    try:
        chunk_index = int(chunk_index)
        total_chunks = int(total_chunks)
    except (ValueError, TypeError):
        return api_response(400, "Invalid chunk index or total chunks")

    # Sanitize filename and upload_id to prevent path traversal
    file_name = re.sub(r'[^a-zA-Z0-9.\-]+', '_', file_name)
    upload_id = re.sub(r'[^a-zA-Z0-9.\-]+', '_', str(upload_id))
    
    # Handle base64 prefix if present (e.g. data:video/mp4;base64,...)
    if "," in file_data:
        file_data = file_data.split(",")[1]
    file_data = file_data.replace(" ", "")

    # Temporary directory for this specific upload session
    temp_dir = os.path.join(settings.EAS_DRIVE_PATH, str(tenant_id), "temp_uploads", upload_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    chunk_file_path = os.path.join(temp_dir, f"chunk_{chunk_index}.part")
    
    try:
        # Decode and save chunk as a separate part
        decoded_bytes = base64.b64decode(file_data)
        with open(chunk_file_path, 'wb') as f:
            f.write(decoded_bytes)

        # Java: Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rw-r--r--"));
        if os.name != 'nt':
             os.chmod(chunk_file_path, 0o644)
            
        # Check if all chunks are uploaded to reassemble
        all_present = True
        for i in range(total_chunks):
            if not os.path.exists(os.path.join(temp_dir, f"chunk_{i}.part")):
                all_present = False
                break
        
        if all_present:
            final_dir = os.path.join(settings.EAS_DRIVE_PATH, str(tenant_id), "images", "socialmedia")
            os.makedirs(final_dir, exist_ok=True)
            final_file_path = os.path.join(final_dir, file_name)
            
            # Reassemble all chunks in correct order using buffered streaming
            with open(final_file_path, 'wb') as final_file:
                for i in range(total_chunks):
                    part_path = os.path.join(temp_dir, f"chunk_{i}.part")
                    if os.path.exists(part_path):
                        with open(part_path, 'rb') as part_file:
                            shutil.copyfileobj(part_file, final_file)
                        os.remove(part_path)
                        
                        # Java: Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rw-r--r--"));
                        if os.name != 'nt':
                            os.chmod(final_file_path, 0o644)
                    else:
                        # Should not happen given the all_present check, but for safety:
                        logger.error(f"Missing chunk part {i} during assembly")
            
            # Clean up the session temp directory
            try:
                os.rmdir(temp_dir)
            except Exception as cleanup_err:
                logger.warning(f"Failed to remove temp dir {temp_dir}: {cleanup_err}")
                
            save_path = f"{settings.IMAGE_SITE_URL}{settings.EAS_DRIVE_NAME}/{tenant_id}/images/socialmedia/{file_name}"
            return api_response(200, f"{file_type_key.capitalize()} Uploaded Successfully", {f"{file_type_key}Path": save_path, f"{file_type_key}Name": file_name})
            
        return api_response(200, f"Chunk {chunk_index} uploaded", {"status": "uploading"})
    except Exception as e:
        logger.error(f"Chunk upload error: {e}")
        return api_response(500, "Error during chunk upload")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def uploadImage(request):
    # If not chunked, fallback to legacy single upload
    upload_id = request.data.get('uploadId')

    if not upload_id:
        return handle_file_upload(request, "image")
    else:
        return handle_file_upload_chunked(request, "image")
    
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def uploadVideo(request):
    # If not chunked, fallback to legacy single upload
    upload_id = request.data.get('uploadId')
    
    if not upload_id:
        return handle_file_upload(request, "video")
    else:
        return handle_file_upload_chunked(request, "video")
    

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def removeImage(request, smId, imageName):
    tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        file_path = os.path.join(settings.EAS_DRIVE_PATH, str(tenant_id), "images", "socialmedia", imageName)
        if os.path.exists(file_path):
            os.remove(file_path)
            
            if smId > 0:
                camp = EiSocialMedia.objects.filter(smId=smId, memberId=get_client_id_by_tenant_id(tenant_id)).first()
                if camp and camp.smPostImage:
                    images = camp.smPostImage.split(",")
                    if imageName in images:
                        images.remove(imageName)
                        camp.smPostImage = ",".join(images)
                        camp.save()
                    res_body[imageName] = "deleted"
            else:
                res_body[imageName] = "deleted"
                
        return api_response(200, "The Image Deleted Successfully", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] RemoveImage Error : {e}")
        return api_response(500, "Image Not Found", res_body)
