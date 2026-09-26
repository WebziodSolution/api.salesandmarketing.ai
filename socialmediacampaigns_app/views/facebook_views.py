from rest_framework.decorators import api_view
from django.shortcuts import redirect
from django.conf import settings
from rest_framework.request import Request
from common_app.models import Clients
from common_app.utils import api_response, get_final_tenant_id
from socialmediacampaigns_app.serializers import FacebookPostDtoSerializer
import requests
import logging
import json
import os
import urllib3

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

@api_view(['GET'])
def facebookLogin(request):
    """
    Redirects to Facebook OAuth login page.
    """
    fb_auth_url = (
        f"https://www.facebook.com/v18.0/dialog/oauth?"
        f"client_id={settings.FACEBOOK_APP_ID}&"
        f"redirect_uri={settings.FACEBOOK_CALLBACK_URL}&"
        f"scope=email,public_profile,pages_manage_posts,pages_read_engagement,pages_show_list,publish_video"
    )
    return redirect(fb_auth_url)

@api_view(['GET'])
def facebookOauth(request: Request):
    resBody = dict()
    resBody["error"] = ""
    code = request.GET.get('code')
    if not code:
        return api_response(400, "Authorization code not provided", {})

    tenant_id = get_final_tenant_id(request=request)
    if not tenant_id:
        return api_response(401, "User not authenticated", {})

    try:
        # 1. Exchange code for access token
        token_url = f"https://graph.facebook.com/v18.0/oauth/access_token"
        params = {
            'client_id': settings.FACEBOOK_APP_ID,
            'client_secret': settings.FACEBOOK_APP_SECRET,
            'redirect_uri': settings.FACEBOOK_CALLBACK_URL,
            'code': code
        }
        token_response = requests.get(token_url, params=params).json()
        access_token = token_response.get('access_token')

        if not access_token:
            return api_response(400, "Failed to obtain access token", token_response)

        # 2. Get user's Facebook ID
        profile_url = f"https://graph.facebook.com/v18.0/me"
        profile_params = {'access_token': access_token, 'fields': 'id'}
        profile_response = requests.get(profile_url, params=profile_params).json()
        fb_id = profile_response.get('id')

        Clients.objects.filter(cliTenantId=tenant_id).update(
            cliFbAccessToken=access_token,
            cliFbId=fb_id
        )

        return api_response(200, "Facebook Connected Successfully.", resBody) 

    except Exception as e:
        resBody["error"] = str(e)
        logger.error(f"facebookOauth error: {str(e)}")
        return api_response(500, "Error during Facebook OAuth", {"error": str(e)})

@api_view(['GET'])
def getFacebookUserData(request):
    """
    Fetches user's Facebook profile data.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        access_token = client.cliFbAccessToken

        if not access_token:
            return api_response(400, "Facebook access token not found", {})

        profile_url = f"https://graph.facebook.com/v18.0/me"
        params = {
            'access_token': access_token,
            'fields': 'id,name,email,picture'
        }
        res = requests.get(profile_url, params=params).json()

        data = {
            "id": res.get("id"),
            "name": res.get("name"),
            "email": res.get("email"),
            "picture": res.get("picture", {}).get("data", {}).get("url") if res.get("picture") else None
        }
        return api_response(200, "Facebook User Data Fetched Successfully.", data)

    except Clients.DoesNotExist:
        return api_response(404, "Client not found", {})
    except Exception as e:
        logger.error(f"getFacebookUserData error: {str(e)}")
        return api_response(500, "Error fetching Facebook user data", {"error": str(e)})

def set_facebook_post_internal(client, message, link):
    access_token = client.cliFbAccessToken
    if not access_token:
        return {"status": "error", "message": "Facebook access token not found"}

    try:
        accounts_url = f"https://graph.facebook.com/v18.0/me/accounts"
        accounts_res = requests.get(accounts_url, params={'access_token': access_token}).json()
        accounts = accounts_res.get('data', [])

        responses = []
        for account in accounts:
            page_id = account.get('id')
            page_token = account.get('access_token')
            if not page_token: continue

            post_url = f"https://graph.facebook.com/v18.0/{page_id}/feed"
            payload = {'access_token': page_token}
            if message: payload['message'] = message
            if link: payload['link'] = json.loads(link)

            res = requests.post(post_url, data=payload).json()
            # responses.append(res)
            if 'id' in res:
                responses.append(res['id'])

        return {"status": "success", "responses": ",".join(responses)}
    except Exception as e:
        logger.error(f"set_facebook_post_internal error: {str(e)}")
        return {"status": "error", "message": str(e)}

def set_facebook_image_post_internal(client, message, images):
    access_token = client.cliFbAccessToken
    if not access_token:
        return {"status": "error", "message": "Facebook access token not found"}

    try:
        accounts_url = f"https://graph.facebook.com/v18.0/me/accounts"
        accounts_res = requests.get(accounts_url, params={'access_token': access_token}).json()
        accounts = accounts_res.get('data', [])

        responses = []
        for account in accounts:
            page_id = account.get('id')
            page_token = account.get('access_token')
            if not page_token: continue

            media_ids = []
            for img_url in images:
                # 1. Fetch the image locally into memory
                try:
                    img_response = requests.get(img_url, timeout=10, verify=False)
                    img_response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to fetch image from {img_url}: {str(e)}")
                    continue # Skip this image but continue with others

                # 2. Extract a filename from the URL (or default to 'image.jpg')
                filename = os.path.basename(img_url.split('?')[0])
                if not filename:
                    filename = "image.jpg"

                photo_url = f"https://graph.facebook.com/v18.0/{page_id}/photos"
                
                # 3. Standard payload without the 'url' parameter
                photo_payload = {
                    'access_token': page_token,
                    'published': 'false'
                }
                
                # 4. Attach the raw image bytes to the 'source' parameter
                files = {
                    'source': (filename, img_response.content, 'image/jpeg')
                }

                # 5. Send as a multipart/form-data POST request
                photo_res = requests.post(photo_url, data=photo_payload, files=files).json()
                
                if photo_res.get('id'):
                    media_ids.append(photo_res.get('id'))
                else:
                    logger.error(f"Facebook photo upload failed: {photo_res}")

            if media_ids:
                feed_url = f"https://graph.facebook.com/v18.0/{page_id}/feed"
                attached_media = [{"media_fbid": m_id} for m_id in media_ids]
                
                feed_payload = {
                    'access_token': page_token,
                    'message': message,
                    'attached_media': json.dumps(attached_media)
                }
                res = requests.post(feed_url, data=feed_payload).json()
                
                if 'id' in res:
                    responses.append(res['id'])
                else:
                    logger.error(f"Facebook feed post failed: {res}")

        return {"status": "success", "responses": ",".join(responses)}
    except Exception as e:
        logger.error(f"set_facebook_image_post_internal error: {str(e)}")
        return {"status": "error", "message": str(e)}

@api_view(['POST'])
def setFacebookPost(request: Request):
    """
    Posts a message and/or link to the user's Facebook pages.
    """
    serializer = FacebookPostDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)

    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        res = set_facebook_post_internal(client, serializer.validated_data.get('message'), serializer.validated_data.get('postLink'))
        if res["status"] == "success":
            return api_response(200, "Post shared on Facebook pages successfully.", res["responses"])
        else:
            return api_response(400, res["message"], {})
    except Clients.DoesNotExist:
        return api_response(404, "Client not found", {})
    except Exception as e:
        logger.error(f"setFacebookPost error: {str(e)}")
        return api_response(500, "Error posting to Facebook", {"error": str(e)})

@api_view(['POST'])
def setFacebookImagePost(request: Request):
    """
    Posts a message and images to the user's Facebook pages.
    """
    serializer = FacebookPostDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)

    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        res = set_facebook_image_post_internal(client, serializer.validated_data.get('message'), serializer.validated_data.get('imageList', []))
        if res["status"] == "success":
            return api_response(200, "Image post shared on Facebook pages successfully.", res["responses"])
        else:
            return api_response(400, res["message"], {})
    except Clients.DoesNotExist:
        return api_response(404, "Client not found", {})
    except Exception as e:
        logger.error(f"setFacebookImagePost error: {str(e)}")
        return api_response(500, "Error posting images to Facebook", {"error": str(e)})

@api_view(['GET'])
def facebookLogout(request):
    """
    Clears Facebook credentials from user's account.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        Clients.objects.filter(cliTenantId=tenant_id).update(
            cliFbAccessToken=None,
            cliFbId=None
        )
        return api_response(200, "Facebook Logout Successfully.", {})
    except Exception as e:
        logger.error(f"facebookLogout error: {str(e)}")
        return api_response(500, "Error during Facebook logout", {"error": str(e)})
