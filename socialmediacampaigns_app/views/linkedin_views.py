from rest_framework.decorators import api_view
from django.shortcuts import redirect
from django.conf import settings
from rest_framework.request import Request
from common_app.models import Clients
from common_app.utils import api_response, get_image_content, get_final_tenant_id
from socialmediacampaigns_app.serializers import LinkedinPostDtoSerializer
import requests
import logging
import json
import regex
import time

logger = logging.getLogger(__name__)

def replace_linkedin_supported_characters(text):
    if not text: return ""
    chars_to_escape = ['@', '|', '{', '}', '[', ']', '(', ')', '<', '>', '#', '*', '_', '~']
    for char in chars_to_escape:
        text = text.replace(char, f"\\{char}")
    return text

def replace_emoji(text):
    if not text: return ""
    character_filter = r"[^\p{L}\p{M}\p{N}\p{P}\p{Z}\p{Cf}\p{Cs}\s]"
    return regex.sub(character_filter, "", text)

@api_view(['GET'])
def linkedinLogin(request):
    """
    Redirects to LinkedIn OAuth login page.
    """
    scopes = "r_basicprofile r_liteprofile r_emailaddress w_member_social w_organization_social rw_organization_admin r_organization_social"
    linkedin_auth_url = (
        f"https://www.linkedin.com/oauth/v2/authorization?"
        f"response_type=code&"
        f"client_id={settings.LINKEDIN_CLIENT_ID}&"
        f"redirect_uri={settings.LINKEDIN_OAUTH_CALLBACK}&"
        f"scope={scopes.replace(' ', '%20')}"
    )
    return redirect(linkedin_auth_url)

@api_view(['GET'])
def linkedInOauth(request: Request):
    code = request.GET.get('code')
    if not code:
        return api_response(400, "Authorization code not provided", {"error": "code_missing"})

    tenant_id = get_final_tenant_id(request=request)
    if not tenant_id:
        return api_response(401, "User not authenticated", {"error": "unauthorized"})

    try:
        # 1. Exchange code for access token
        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.LINKEDIN_OAUTH_CALLBACK,
            'client_id': settings.LINKEDIN_CLIENT_ID,
            'client_secret': settings.LINKEDIN_CLIENT_SECRET
        }
        res = requests.post(token_url, data=data).json()
        access_token = res.get('access_token')
        expires_in = res.get('expires_in')

        if not access_token:
            return api_response(500, "Linkedin Failed To Authenticate.", {"error": res.get('error_description', 'no_token')})

        Clients.objects.filter(cliTenantId=tenant_id).update(
            cliLinAuthToken=access_token,
            cliLinExpiresAt=str(expires_in) if expires_in else None
        )

        # 3. Fetch user data immediately as Java does
        return api_response(200, "Linkedin Connected Successfully.", {}) # Pass original request

    except Exception as e:
        logger.error(f"linkedInOauth error: {str(e)}")
        return api_response(500, "Linkedin Failed To Authenticate.", {"error": str(e)})

@api_view(['GET'])
def getLinkedinUserData(request):
    """
    Fetches user's LinkedIn profile data.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        access_token = client.cliLinAuthToken

        if not access_token:
            return api_response(400, "Linkedin access token not found", {"error": "token_missing"})

        headers = {
            'Authorization': f'Bearer {access_token}',
            'LinkedIn-Version': '202411'
        }

        # Profile basic info
        profile_url = "https://api.linkedin.com/v2/me?projection=(id,firstName,lastName,profilePicture(displayImage~:playableStreams))"
        profile_res = requests.get(profile_url, headers=headers).json()

        lid = profile_res.get('id')
        first_name = profile_res.get('firstName', {}).get('localized', {}).get('en_US', '')
        last_name = profile_res.get('lastName', {}).get('localized', {}).get('en_US', '')

        img = ""
        pic_obj = profile_res.get('profilePicture')
        if pic_obj:
            elements = pic_obj.get('displayImage~', {}).get('elements', [])
            if elements:
                identifiers = elements[0].get('identifiers', [])
                if identifiers:
                    img = identifiers[0].get('identifier', '')

        # Email info
        email_url = "https://api.linkedin.com/v2/emailAddress?q=members&projection=(elements*(handle~))"
        email_res = requests.get(email_url, headers=headers).json()
        email = ""
        elements = email_res.get('elements', [])
        if elements:
            email = elements[0].get('handle~', {}).get('emailAddress', '')

        data = {
            "id": lid,
            "name": f"{first_name} {last_name}".strip(),
            "email": email,
            "img": img,
            "error": None
        }
        return api_response(200, "Fetch User Data Successfully.", data)

    except Clients.DoesNotExist:
        return api_response(404, "Client not found", {"error": "client_not_found"})
    except Exception as e:
        logger.error(f"getLinkedinUserData error: {str(e)}")
        return api_response(500, str(e), {"error": str(e)})

@api_view(['GET'])
def getLinkedinPagesData(request):
    """
    Fetches user's LinkedIn organization pages.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        access_token = client.cliLinAuthToken

        if not access_token:
            return api_response(400, "Linkedin access token not found", {"error": "token_missing"})

        headers = {
            'Authorization': f'Bearer {access_token}',
            'LinkedIn-Version': '202411'
        }

        request_url = "https://api.linkedin.com/v2/organizationalEntityAcls?q=roleAssignee&role=ADMINISTRATOR&state=APPROVED&projection=(roleAssignee,elements*(*,organizationalTarget~(localizedName)))"
        res = requests.get(request_url, headers=headers).json()
        entities = res.get('elements', [])

        pages = []
        for entity in entities:
            target = entity.get('organizationalTarget', '')
            target_info = entity.get('organizationalTarget~', {})
            page_id = target.split(':')[-1] if target else ''
            page_name = target_info.get('localizedName', '')
            pages.append({"pageId": page_id, "pageName": page_name})

        return api_response(200, "Fetch Pages Data Successfully.", {"pageData": pages})

    except Exception as e:
        logger.error(f"getLinkedinPagesData error: {str(e)}")
        return api_response(500, str(e), {"error": str(e)})

def set_linkedin_post_internal(client, message, link, send_to_str, edit_response):
    access_token = client.cliLinAuthToken
    if not access_token:
        return {"status": "error", "message": "Token not found"}

    try:
        # We need the user profile ID for the author URN
        profile_url = "https://api.linkedin.com/v2/me?projection=(id)"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'LinkedIn-Version': '202411'
        }
        profile_res = requests.get(profile_url, headers=headers).json()
        user_id = profile_res.get('id')

        message = replace_emoji(replace_linkedin_supported_characters(message or ''))
        
        response_ids = []
        headers.update({
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        })

        if not edit_response:
            for send_to in send_to_str.split(':'):
                author = f"urn:li:person:{user_id}" if send_to == "default" else f"urn:li:organization:{send_to}"
                payload = dict()
                payload["author"] = author
                payload["commentary"] = message
                payload["visibility"] = "PUBLIC"
                payload["distribution"] = {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": []
                }
                payload["lifecycleState"] = "PUBLISHED"
                payload["isReshareDisabledByAuthor"] = False
                if link:
                    try:
                        link_preview = json.loads(link)
                        payload["content"] = {
                            "article": {
                                "source": link_preview.get("url"),
                                "title": link_preview.get("description", "")[:200]
                            }
                        }
                    except: pass
                
                res = requests.post("https://api.linkedin.com/v2/posts", headers=headers, json=payload)
                resp_id = res.headers.get('x-restli-id')
                if resp_id: response_ids.append(resp_id)
        else:
            for sm_response in edit_response.split(','):
                patch_headers = headers.copy()
                patch_headers['X-RestLi-Method'] = 'PARTIAL_UPDATE'
                payload = {"patch": {"$set": {"commentary": message}}}
                requests.post(f"https://api.linkedin.com/v2/posts/{sm_response}", headers=patch_headers, json=payload)
                response_ids.append(sm_response)

        return {"status": "success", "postIds": ",".join(response_ids)}
    except Exception as e:
        logger.error(f"set_linkedin_post_internal error: {str(e)}")
        return {"status": "error", "message": str(e)}

def set_linkedin_image_post_internal(client, message, image_url, send_to_str, edit_response):
    access_token = client.cliLinAuthToken
    if not access_token:
        return {"status": "error", "message": "Token not found"}

    try:
        profile_url = "https://api.linkedin.com/v2/me?projection=(id)"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'LinkedIn-Version': '202411'
        }
        profile_res = requests.get(profile_url, headers=headers).json()
        user_id = profile_res.get('id')

        message = replace_emoji(replace_linkedin_supported_characters(message or ''))
        
        response_ids = []
        headers.update({
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        })

        if not edit_response:
            for send_to_item in send_to_str.split(':'):
                author = f"urn:li:person:{user_id}" if send_to_item == "default" else f"urn:li:organization:{send_to_item}"

                init_url = "https://api.linkedin.com/v2/images?action=initializeUpload"
                init_payload = {"initializeUploadRequest": {"owner": author}}
                init_res = requests.post(init_url, headers=headers, json=init_payload).json()
                upload_url = init_res.get('value', {}).get('uploadUrl')
                image_id = init_res.get('value', {}).get('image')

                img_data = get_image_content(image_url)
                requests.post(upload_url, headers={'Authorization': f'Bearer {access_token}'}, data=img_data)

                time.sleep(10)

                post_payload = {
                    "author": author, "commentary": message, "visibility": "PUBLIC",
                    "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                    "content": {"media": {"id": image_id, "altText": "Image Could Not Be Loaded"}},
                    "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False
                }
                post_res = requests.post("https://api.linkedin.com/v2/posts", headers=headers, json=post_payload)
                resp_id = post_res.headers.get('x-restli-id')
                if resp_id: response_ids.append(resp_id)
        else:
            for sm_response in edit_response.split(','):
                patch_headers = headers.copy()
                patch_headers['X-RestLi-Method'] = 'PARTIAL_UPDATE'
                payload = {"patch": {"$set": {"commentary": message}}}
                requests.post(f"https://api.linkedin.com/v2/posts/{sm_response}", headers=patch_headers, json=payload)
                response_ids.append(sm_response)

        return {"status": "success", "postIds": ",".join(response_ids)}
    except Exception as e:
        logger.error(f"set_linkedin_image_post_internal error: {str(e)}")
        return {"status": "error", "message": str(e)}

@api_view(['POST'])
def setLinkedinPost(request: Request):
    """
    Shares a post on LinkedIn.
    """
    serializer = LinkedinPostDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)

    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        res = set_linkedin_post_internal(
            client,
            serializer.validated_data.get('message'), 
            serializer.validated_data.get('postLink'),
            serializer.validated_data.get('sendTo', ''),
            serializer.validated_data.get('editLSmpResponse', '')
        )
        if res["status"] == "success":
            return api_response(200, "Post Successfully Added.", {"postIds": res["postIds"]})
        else:
            return api_response(400, res["message"], {"postIds": "404"})
    except Exception as e:
        logger.error(f"setLinkedinPost error: {str(e)}")
        return api_response(500, str(e), {"error": str(e), "postIds": "404"})

@api_view(['POST'])
def setLinkedinImagePost(request: Request):
    """
    Shares an image post on LinkedIn.
    """
    serializer = LinkedinPostDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)

    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        res = set_linkedin_image_post_internal(
            client,
            serializer.validated_data.get('message'),
            serializer.validated_data.get('image', ''),
            serializer.validated_data.get('sendTo', ''),
            serializer.validated_data.get('editLSmpResponse', '')
        )
        if res["status"] == "success":
            return api_response(200, "Post Successfully Added.", {"postIds": res["postIds"]})
        else:
            return api_response(400, res["message"], {})
    except Exception as e:
        logger.error(f"setLinkedinImagePost error: {str(e)}")
        return api_response(500, str(e), {"error": str(e)})

@api_view(['GET'])
def linkedinLogout(request):
    """
    Clears LinkedIn credentials from user's account.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        Clients.objects.filter(cliTenantId=tenant_id).update(
            cliLinAuthToken=None,
            cliLinExpiresAt=None
        )
        return api_response(200, "Linkedin Disconnected Successfully.", {})
    except Exception as e:
        logger.error(f"linkedinLogout error: {str(e)}")
        return api_response(500, "Error during LinkedIn logout", {"error": str(e)})
