from rest_framework.decorators import api_view
from django.shortcuts import redirect
from django.conf import settings
from rest_framework.request import Request
from django.core.cache import cache
from common_app.models import Clients
from common_app.utils import api_response, get_image_content, get_final_tenant_id
from socialmediacampaigns_app.serializers import TwitterPostDtoSerializer
from requests_oauthlib import OAuth1Session, OAuth1
import requests
import logging
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)

# Twitter API URLs
REQUEST_TOKEN_URL = "https://api.twitter.com/oauth/request_token"
AUTHORIZE_URL = "https://api.twitter.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://api.twitter.com/oauth/access_token"
VERIFY_CREDENTIALS_URL = "https://api.twitter.com/1.1/account/verify_credentials.json"
TWEET_V2_URL = "https://api.twitter.com/2/tweets"
MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
REDIRECT_URL = f"""https://twitter.com/i/oauth2/authorize?response_type=code&client_id={settings.TWITTER_CONSUMER_SECRET}&redirect_uri={settings.TWITTER_CALLBACK_URL}&scope=tweet.read tweet.write users.read media.write offline.access&state=xyz&code_challenge=abc&code_challenge_method=S256"""

@api_view(['GET'])
def twitterLogin(request):
    try:
        oauth = OAuth1Session(settings.TWITTER_CONSUMER_KEY, client_secret=settings.TWITTER_CONSUMER_SECRET,
                              callback_uri=settings.TWITTER_CALLBACK_URL)
        fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL)
        oauth_token = fetch_response.get('oauth_token')
        oauth_token_secret = fetch_response.get('oauth_token_secret')
        cache_key = f"twitter_secret_{oauth_token}"
        cache.set(cache_key, oauth_token_secret, timeout=600)
        authorization_url = oauth.authorization_url(AUTHORIZE_URL)
        logger.error(f"authorization_url: {authorization_url}")
        return redirect(authorization_url)
    except Exception as e:
        logger.error(f"twitterLogin error: {str(e)}")
        return api_response(500, "Error during Twitter login", {"error": str(e)})

@api_view(['GET'])
def twitterOauth(request: Request):
    """
    Step 2: Handle callback from Twitter. Exchange verifier for access token and secret.
    """
    oauth_token = request.GET.get('oauth_token')
    oauth_verifier = request.GET.get('oauth_verifier')

    if not oauth_token or not oauth_verifier:
        return api_response(400, "oauth_token or oauth_verifier missing", {"error": "params_missing"})

    tenant_id = get_final_tenant_id(request=request)
    if not tenant_id:
        return api_response(401, "User not authenticated", {"error": "unauthorized"})

    try:
        # Since we are stateless and don't have the request_token_secret from Step 1,
        # we can still attempt the exchange if we have the consumer key/secret and the verifier.
        # Most OAuth1 libraries require the request_token_secret. 
        # However, the Java code does a POST to access_token URL directly.
        
        request_url = f"{ACCESS_TOKEN_URL}?oauth_verifier={oauth_verifier}&oauth_token={oauth_token}"
        res_text = requests.post(request_url).text
        res_dict = dict(parse_qsl(res_text))

        access_token = res_dict.get('oauth_token')
        access_token_secret = res_dict.get('oauth_token_secret')

        if not access_token or not access_token_secret:
            return api_response(500, "Twitter Failed To Authenticate.", {"error": "no_token"})

        Clients.objects.filter(cliTenantId=tenant_id).update(
            cliTwOauthtoken=access_token,
            cliTwOauthtokenSecret=access_token_secret
        )

        # Fetch and return user data
        return api_response(200, "Twitter Connected Successfully.", {})

    except Exception as e:
        logger.error(f"twitterOauth error: {str(e)}")
        return api_response(500, "Twitter Failed To Authenticate.", {"error": str(e)})

@api_view(['GET'])
def getTwitterUserData(request):
    """
    Fetches Twitter user profile data.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        if not client.cliTwOauthtoken or not client.cliTwOauthtokenSecret:
            return api_response(400, "Twitter credentials not found", {"error": "credentials_missing"})

        oauth = OAuth1(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET,
                       client.cliTwOauthtoken, client.cliTwOauthtokenSecret)

        res = requests.get(VERIFY_CREDENTIALS_URL, auth=oauth).json()

        data = {
            "id": res.get("id"),
            "name": res.get("name"),
            "screenName": res.get("screen_name"),
            "img": res.get("profile_image_url_https", res.get("profile_image_url", ""))
        }
        return api_response(200, "Fetch User Data Successfully.", data)

    except Clients.DoesNotExist:
        return api_response(404, "Client not found", {"error": "client_not_found"})
    except Exception as e:
        logger.error(f"getTwitterUserData error: {str(e)}")
        return api_response(500, str(e), {"error": str(e)})

def set_twitter_post_internal(client, message):
    if not client.cliTwOauthtoken:
        return {"status": "error", "message": "Twitter NOT account connected"}

    try:
        oauth = OAuth1(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET,
                       client.cliTwOauthtoken, client.cliTwOauthtokenSecret)

        payload = {"text": message or ''}
        res = requests.post(TWEET_V2_URL, auth=oauth, json=payload).json()
        
        tweet_id = res.get('data', {}).get('id', '')
        return {"status": "success", "postId": tweet_id, "response": res}
    except Exception as e:
        logger.error(f"set_twitter_post_internal error: {str(e)}")
        return {"status": "error", "message": str(e)}

def set_twitter_image_post_internal(client, message, image_list):
    if not client.cliTwOauthtoken:
        return {"status": "error", "message": "Twitter NOT account connected"}

    try:
        oauth = OAuth1(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET,
                       client.cliTwOauthtoken, client.cliTwOauthtokenSecret)

        media_ids = []
        for img_url in image_list[:4]:
            try:
                img_data = get_image_content(img_url)
                files = {'media': img_data}
                upload_res = requests.post(MEDIA_UPLOAD_URL, auth=oauth, files=files).json()
                media_id = upload_res.get('media_id_string')
                if media_id:
                    media_ids.append(media_id)
            except Exception as upload_err:
                logger.error(f"Media upload failed for {img_url}: {str(upload_err)}")

        payload = {"text": message or ''}
        if media_ids:
            payload["media"] = {"media_ids": media_ids}

        res = requests.post(TWEET_V2_URL, auth=oauth, json=payload).json()
        tweet_id = res.get('data', {}).get('id', '')
        
        return {"status": "success", "postId": tweet_id, "response": res}
    except Exception as e:
        logger.error(f"set_twitter_image_post_internal error: {str(e)}")
        return {"status": "error", "message": str(e)}

@api_view(['POST'])
def setTwitterPost(request: Request):
    """
    Posts a tweet (text only or with link).
    """
    serializer = TwitterPostDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)

    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        res = set_twitter_post_internal(client, serializer.validated_data.get('message'))
        if res["status"] == "success":
            return api_response(200, "Twitter Post Successfully.", {"postId": res["postId"]})
        else:
            return api_response(400, res["message"], {"postId": ""})
    except Exception as e:
        logger.error(f"setTwitterPost error: {str(e)}")
        return api_response(500, str(e), {"postId": ""})

@api_view(['POST'])
def setTwitterImagePost(request: Request):
    """
    Posts a tweet with images.
    """
    serializer = TwitterPostDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)

    tenant_id = get_final_tenant_id(request=request)
    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        res = set_twitter_image_post_internal(client, serializer.validated_data.get('message'), serializer.validated_data.get('imageList', []))
        if res["status"] == "success":
            return api_response(200, "Twitter Post Successfully.", {"postId": res["postId"]})
        else:
            return api_response(400, res["message"], {"postId": ""})
    except Exception as e:
        logger.error(f"setTwitterImagePost error: {str(e)}")
        return api_response(500, str(e), {"postId": ""})

@api_view(['GET'])
def twitterLogout(request):
    """
    Clears Twitter credentials.
    """
    tenant_id = get_final_tenant_id(request=request)
    try:
        Clients.objects.filter(cliTenantId=tenant_id).update(
            cliTwOauthtoken=None,
            cliTwOauthtokenSecret=None
        )
        return api_response(200, "Twitter Disconnected Successfully.", {})
    except Exception as e:
        logger.error(f"twitterLogout error: {str(e)}")
        return api_response(500, "Error during Twitter logout", {"error": str(e)})
