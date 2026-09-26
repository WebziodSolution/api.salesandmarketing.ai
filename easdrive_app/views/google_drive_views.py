import os
import json
import re
import io
from django.conf import settings
from django.shortcuts import redirect
from rest_framework.views import APIView
from common_app.custom_permissions import WhitelistPermission
from auth_app.authentication import MemberJWTAuthentication
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from common_app.utils import get_final_tenant_id, api_response, display_date_time
from auth_app.models import Tenants
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/drive']
# Constant verifier to resolve PKCE 'Missing code verifier' in stateless OAuth flow
GOOGLE_DRIVE_CODE_VERIFIER = "samai_google_drive_auth_verifier_static_string_at_least_43_chars_long"

class BaseGoogleDriveView(APIView):
    authentication_classes = [MemberJWTAuthentication]
    permission_classes = [WhitelistPermission]

    def get_user_identifier(self, tenant):
        return f"{tenant.ten_first_name}_{tenant.ten_last_name}_{tenant.ten_id}"

    def get_credentials(self, tenant):
        user_id = self.get_user_identifier(tenant)
        token_path = os.path.join(settings.GOOGLE_OAUTH_TOKEN_DIR, f"{user_id}.json")
        if os.path.exists(token_path):
            try:
                return Credentials.from_authorized_user_file(token_path, SCOPES)
            except Exception:
                return None
        return None

    def get_drive_service(self, credentials):
        return build('drive', 'v3', credentials=credentials)

class AuthenticateView(BaseGoogleDriveView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        creds = self.get_credentials(tenant)
        
        auth_status = False
        if creds and creds.valid:
            auth_status = True
        elif creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed credentials
                user_id = self.get_user_identifier(tenant)
                token_path = os.path.join(settings.GOOGLE_OAUTH_TOKEN_DIR, f"{user_id}.json")
                with open(token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                auth_status = True
            except:
                auth_status = False

        if auth_status:
            return api_response(200, "Authenticate Successfully.", {"authenticate": True})
        return api_response(500, "Failed To Authenticate.", {"authenticate": False}, sendErrorAs200=True)

class GoogleSignInView(BaseGoogleDriveView):
    # This might need to be unprotected if called directly, but Java uses it as a redirect.
    # Actually, it's a GET /googleDrive/googleSignIn.
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        flow = Flow.from_client_secrets_file(
            settings.GOOGLE_OAUTH_CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_OAUTH_CALLBACK_URL
        )
        flow.code_verifier = GOOGLE_DRIVE_CODE_VERIFIER
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            prompt='consent',
            include_granted_scopes='true'
        )
        return redirect(authorization_url)

class OAuthCallbackView(BaseGoogleDriveView):
    def get(self, request):
        code = request.query_params.get('code')
        file_type = request.query_params.get('fileType')
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)

        if not code:
            return api_response(500, "Failed to authenticate.", {"authenticate": False})

        flow = Flow.from_client_secrets_file(
            settings.GOOGLE_OAUTH_CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_OAUTH_CALLBACK_URL
        )
        flow.code_verifier = GOOGLE_DRIVE_CODE_VERIFIER
        flow.fetch_token(code=code)
        creds = flow.credentials

        user_id = self.get_user_identifier(tenant)
        token_path = os.path.join(settings.GOOGLE_OAUTH_TOKEN_DIR, f"{user_id}.json")
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())

        service = self.get_drive_service(creds)
        
        images = self._get_list_images(service, "root", file_type)
        folders = self._get_folders_and_files(service, "root")

        return api_response(200, "Authenticate Successfully.", {
            "getImages": images,
            "getFolders": json.dumps(folders, separators=(',', ':')),
            "authenticate": True
        })

    def _get_list_images(self, service, folder_id, file_type):
        q = f"'{folder_id}' in parents and trashed=false"
        mime_types = []
        if not file_type:
            mime_types = ["image/jpeg", "image/png", "application/pdf"]
        elif file_type == "image":
            mime_types = ["image/jpeg", "image/png"]
        elif file_type == "file":
            mime_types = ["application/pdf"]
        
        if mime_types:
            q += " and (" + " or ".join([f"mimeType='{m}'" for m in mime_types]) + ")"

        results = service.files().list(
            q=q, fields="nextPageToken, files(id, name, mimeType, thumbnailLink, size, imageMediaMetadata, modifiedTime)").execute()
        items = results.get('files', [])
        
        response_list = []
        for file in items:
            item = {
                "id": file.get('id'),
                "name": file.get('name'),
                "mimeType": file.get('mimeType'),
                "thumbnailLink": file.get('thumbnailLink'),
                "size": int(file.get('size', 0)) if file.get('size') else 0,
                "fileType": "file" if file.get('mimeType') == "application/pdf" else "image",
                "modifiedTime": display_date_time(file.get('modifiedTime')) if file.get('modifiedTime') else ""
            }
            meta = file.get('imageMediaMetadata', {})
            item["imageMediaMetadata"] = {
                "width": meta.get('width', 0),
                "height": meta.get('height', 0)
            }
            response_list.append(item)
        return response_list

    def _get_folders_and_files(self, service, folder_id):
        # Recursive folder fetch mirroring Java
        root = dict()
        root["text"] = "My Drive"
        root["pathValue"] = ""
        nodes = self._get_recursive_folders(service, folder_id)
        if nodes:
            root["nodes"] = nodes
        return [root]

    def _get_recursive_folders(self, service, folder_id):
        nodes = []
        page_token = None
        while True:
            q = f"mimeType='application/vnd.google-apps.folder' and '{folder_id}' in parents and trashed=false"
            results = service.files().list(
                q=q, 
                pageToken=page_token,
                fields="nextPageToken, files(id, name, mimeType, parents)"
            ).execute()
            files = results.get('files', [])
            
            for file in files:
                node = {
                    "text": file.get('name'),
                    "pathValue": f"?F={file.get('id')}&PF={folder_id}"
                }
                sub_nodes = self._get_recursive_folders(service, file.get('id'))
                if sub_nodes:
                    node["nodes"] = sub_nodes
                nodes.append(node)
            
            page_token = results.get('nextPageToken')
            if not page_token:
                break
        return nodes

class GetListViewImagesView(OAuthCallbackView): # Inherit shared logic
    def get(self, request, folder_id):
        file_type = request.query_params.get('fileType')
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        creds = self.get_credentials(tenant)
        if not creds:
             return api_response(500, "Failed to authenticate.", {"authenticate": False})
        
        service = self.get_drive_service(creds)
        images = self._get_list_images(service, folder_id, file_type)
        return api_response(200, "Fetched Images Successfully.", {
            "getImages": images,
            "authenticate": True
        })

class GetFoldersAndFilesView(OAuthCallbackView):
    def get(self, request, folder_id):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        creds = self.get_credentials(tenant)
        if not creds:
             return api_response(500, "Failed to authenticate.", {"authenticate": False})
        
        service = self.get_drive_service(creds)
        folders = self._get_folders_and_files(service, folder_id)
        # Java returns list of folders as stringified JSON in 'str' key
        return api_response(200, "Fetched Folders Successfully.", {
            "getFolders": json.dumps(folders, separators=(',', ':')),
            "authenticate": True
        })

class GetSearchFilesView(OAuthCallbackView):
    def get(self, request, folder_id, search_string):
        file_type = request.query_params.get('fileType')
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        creds = self.get_credentials(tenant)
        if not creds:
             return api_response(500, "Failed to authenticate.", {"authenticate": False})
        
        service = self.get_drive_service(creds)
        
        q = f"'{folder_id}' in parents and name contains '{search_string}' and trashed=false"
        mime_types = []
        if not file_type:
            mime_types = ["image/jpeg", "image/png", "application/pdf"]
        elif file_type == "image":
            mime_types = ["image/jpeg", "image/png"]
        elif file_type == "file":
            mime_types = ["application/pdf"]
        
        if mime_types:
            q += " and (" + " or ".join([f"mimeType='{m}'" for m in mime_types]) + ")"

        results = service.files().list(
            q=q, fields="files(id, name, mimeType, thumbnailLink, size, imageMediaMetadata, modifiedTime)").execute()
        items = results.get('files', [])
        
        response_list = []
        for file in items:
            item = {
                "id": file.get('id'),
                "name": file.get('name'),
                "mimeType": file.get('mimeType'),
                "thumbnailLink": file.get('thumbnailLink'),
                "size": int(file.get('size', 0)) if file.get('size') else 0,
                "fileType": "file" if file.get('mimeType') == "application/pdf" else "image",
                "modifiedTime": display_date_time(file.get('modifiedTime')) if file.get('modifiedTime') else ""
            }
            meta = file.get('imageMediaMetadata', {})
            item["imageMediaMetadata"] = {
                "width": meta.get('width', 0),
                "height": meta.get('height', 0)
            }
            response_list.append(item)

        return api_response(200, "Fetched Images Successfully.", {
            "getImages": response_list,
            "authenticate": True
        })

class DownloadFileView(BaseGoogleDriveView):
    def get(self, request, file_id):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        creds = self.get_credentials(tenant)
        if not creds:
             return api_response(500, "Internal Server Error", {"authenticate": False})
        
        service = self.get_drive_service(creds)
        
        try:
            file_metadata = service.files().get(fileId=file_id).execute()
            file_name = re.sub(r"[^a-zA-Z0-9.\-]+", "_", file_metadata.get('name'))
            
            tenant_images_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(tenant_id), "images")
            if not os.path.exists(tenant_images_path):
                os.makedirs(tenant_images_path)
            
            dest_path = os.path.join(tenant_images_path, file_name)
            
            request_download = service.files().get_media(fileId=file_id)
            with io.FileIO(dest_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request_download)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
            
            image_url = f"{settings.SITE_URL}{settings.EAS_DRIVE_NAME}/{tenant_id}/images/{file_name}"
            return api_response(200, "Fetched Image Successfully.", {
                "imagePath": image_url,
                "authenticate": True
            })
        except Exception:
            return api_response(500, "Sorry Your File Is Not Imported Please Try Again.", {
                "imagePath": "1",
                "authenticate": True
            })
