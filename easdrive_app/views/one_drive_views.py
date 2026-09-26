import os
import json
import time
import requests
import re
import base64
from urllib.parse import unquote
from django.conf import settings
from django.shortcuts import redirect
from rest_framework.views import APIView
from common_app.custom_permissions import WhitelistPermission
from auth_app.authentication import MemberJWTAuthentication
from common_app.utils import get_final_tenant_id, api_response, display_date_time
from auth_app.models import Tenants


class BaseOneDriveView(APIView):
    authentication_classes = [MemberJWTAuthentication]
    permission_classes = [WhitelistPermission]

    def get_user_identifier(self, tenant):
        return f"{tenant.ten_first_name}_{tenant.ten_last_name}_{tenant.ten_id}"

    def get_token_path(self, tenant):
        user_id = self.get_user_identifier(tenant)
        return os.path.join(settings.ONEDRIVE_TOKEN_DIR, f"{user_id}.json")

    def save_token_data(self, tenant, token_data):
        path = self.get_token_path(tenant)
        data = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in"),
            "obtained_at": int(time.time())
        }
        with open(path, 'w') as f:
            json.dump(data, f)

    def get_token_data(self, tenant):
        path = self.get_token_path(tenant)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return {}

    def is_authenticated(self, tenant):
        data = self.get_token_data(tenant)
        if not data or not data.get("access_token"):
            return False
        
        # Buffer of 60 seconds mirroring Java
        remaining = (data["obtained_at"] + data["expires_in"]) - int(time.time())
        if remaining <= 60:
            return self.refresh_token(tenant, data.get("refresh_token"))
        return True

    def refresh_token(self, tenant, refresh_token):
        if not refresh_token:
            return False
        
        url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        payload = {
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        try:
            response = requests.post(url, data=payload)
            if response.status_code == 200:
                self.save_token_data(tenant, response.json())
                return True
        except:
            pass
        return False

    def get_token(self, tenant):
        data = self.get_token_data(tenant)
        return data.get("access_token") if data else None

class AuthenticateView(BaseOneDriveView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)

        if self.is_authenticated(tenant):
            return api_response(200, "Already Authenticated.", {"authenticate": True})
        
        return api_response(500, "Not Authenticated.", {"authenticate": False}, sendErrorAs200=True)

class OneDriveSignInView(BaseOneDriveView):
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        return redirect(settings.ONEDRIVE_AUTHORIZE_URL)

class OAuthCallbackView(BaseOneDriveView):
    def get(self, request):
        code = request.query_params.get('code')
        file_type = request.query_params.get('fileType', "")
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        
        if not code:
             return api_response(500, "Failed to authenticate. Code Parameter is Missing", {"authenticate": False})

        url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        payload = {
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
            "redirect_uri": settings.ONEDRIVE_REDIRECT_URI,
            "code": code,
            "grant_type": "authorization_code"
        }
        
        try:
            response = requests.post(url, data=payload)
            if response.status_code == 200:
                token_data = response.json()
                self.save_token_data(tenant, token_data)
                
                # Fetch folders and images to match Java response
                service = OneDriveService(tenant, self.get_token(tenant))
                folders = service.get_folders()
                images = service.get_images("", file_type, "")
                
                return api_response(200, "Authenticate successfully.", {
                    "folderList": folders,
                    "imageList": images
                })
            else:
                return api_response(500, f"Failed to authenticate. {response.text}", {})
        except Exception as e:
            return api_response(500, f"Failed to authenticate. {str(e)}", {})

class GetFoldersView(BaseOneDriveView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        
        if not self.is_authenticated(tenant):
            return api_response(200, "Login First", {"login": False})
            
        try:
            service = OneDriveService(tenant, self.get_token(tenant))
            res_body = dict()
            res_body["folderList"] = service.get_folders()
            res_body["login"] = True
            return api_response(200, "Fetched Folders Successfully", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class GetImagesView(BaseOneDriveView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        folder_id = request.query_params.get("F", "")
        search_str = request.query_params.get("searchStr", "")
        file_type = request.query_params.get("fileType", "")
        
        if not self.is_authenticated(tenant):
            return api_response(200, "Login First", {"login": False})
            
        try:
            decoded_f = unquote(folder_id) if folder_id else ""
            service = OneDriveService(tenant, self.get_token(tenant))
            res_body = dict()
            res_body["imageList"] = service.get_images(decoded_f, file_type, search_str)
            res_body["login"] = True
            return api_response(200, "Fetched Images Successfully", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class SearchView(BaseOneDriveView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        search_str = request.query_params.get("searchStr", "")

        if not self.is_authenticated(tenant):
            return api_response(200, "Login First", {"login": False})
            
        try:
            service = OneDriveService(tenant, self.get_token(tenant))
            res_body = service.get_search_result(search_str)
            res_body["login"] = True
            return api_response(200, "", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class DownloadView(BaseOneDriveView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        path = request.query_params.get("path", "")
        fn = request.query_params.get("fn", "")
        
        try:
            if path == "root":
                path = ""
            
            tenant = Tenants.objects.get(ten_id=tenant_id)
            service = OneDriveService(tenant, self.get_token(tenant))
            res_body = service.download_image(unquote(path), unquote(fn))
            return api_response(200, "", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class OneDriveService:
    def __init__(self, tenant, token):
        self.tenant = tenant
        self.token = token
        self.tenant_id = tenant.ten_id

    def get_folders(self):
        root_list = []
        self.walk("", None, root_list)
        return root_list

    def walk(self, folder_id, name, result_list):
        current = {}
        if not folder_id:
            current["text"] = "My Drive"
            current["pathValue"] = "?F="
        else:
            current["text"] = name
            current["pathValue"] = f"?F={folder_id}"
        
        children_resp = self.get_children_api(folder_id)
        children = children_resp.get("children", [])
        
        folder_children = [c for c in children if c.get("folder") is not None]
        
        if folder_children:
            nodes = []
            current["nodes"] = nodes
            for fc in folder_children:
                self.walk(fc["id"], fc["name"], nodes)
        
        result_list.append(current)

    def get_images(self, folder_id, file_type, search_str):
        children_resp = self.get_children_api(folder_id)
        children = children_resp.get("children", [])
        
        filtered = []
        for child in children:
            if child.get("folder") is not None:
                continue
            
            name = child.get("name", "")
            ext = name.split(".")[-1].lower() if "." in name else ""
            
            is_match = False
            if not file_type or file_type == "image":
                if ext in ["jpg", "jpeg", "png", "gif", "bmp"]:
                    is_match = True
            
            if not is_match and (not file_type or file_type == "file"):
                if ext == "pdf":
                    is_match = True
            
            if is_match:
                if not search_str or search_str.lower() in name.lower():
                    filtered.append(child)
        
        file_list = []
        for f in filtered:
            meta = self.get_file_metadata_api(f["id"])
            ext = f["name"].split(".")[-1] if "." in f["name"] else ""
            
            item = {
                "fileName": f["name"],
                "extension": ext,
                "fileType": "pdf" if ext.lower() == "pdf" else "image",
                "size": f.get("size", 0),
                "path": f["id"]
            }
            try:
                item["thumbnail"] = self.get_thumbnail_api(f["id"])
                item["lastModifiedTime"] = display_date_time(meta.get("fileSystemInfo", {}).get("lastModifiedDateTime", ""))
                
                item["imageHeight"] = 0
                item["imageWidth"] = 0
            except:
                pass
            file_list.append(item)
            
        return file_list

    def get_search_result(self, query):
        url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{query}')"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers)
        data = resp.json()
        obj = dict()
        obj["found"] = True
        values = data.get("value", [])
        if not values:
            obj["found"] = False
            return obj
            
        filtered = []
        for v in values:
            if v.get("folder") is not None:
                continue
            
            mime = v.get("file", {}).get("mimeType", "")
            if "image" in mime or "pdf" in mime:
                filtered.append(v)
        
        if not filtered:
            obj["found"] = False
            return obj
            
        lst = []
        for v in filtered:
            name = v.get("name", "")
            ext = name.split(".")[-1] if "." in name else ""
            item = {
                "fileName": name,
                "extension": ext,
                "fileType": "pdf" if ext.lower() == "pdf" else "image",
                "path": v["id"],
                "size": v.get("size", 0)
            }
            try:
                item["thumbnail"] = self.get_thumbnail_api(v["id"])
                item["lastModifiedTime"] = display_date_time(v.get("fileSystemInfo", {}).get("lastModifiedDateTime", ""))
                item["imageHeight"] = 0
                item["imageWidth"] = 0
            except:
                pass
            lst.append(item)
            
        if not lst:
            obj["found"] = False
        else:
            obj["imageList"] = lst
        return obj

    def download_image(self, path, file_name: str):
        file_name = re.sub(r"[^a-zA-Z0-9.\-]+", "_", file_name)
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(self.tenant_id), "images")
        if not os.path.exists(root_path):
            os.makedirs(root_path)
            
        try:
            meta = self.get_file_metadata_api(path)
            download_url = meta.get("@microsoft.graph.downloadUrl")
            if download_url:
                resp = requests.get(download_url)
                dest = os.path.join(root_path, file_name)
                with open(dest, "wb") as f:
                    f.write(resp.content)
        except:
            pass
            
        return {
            "downloadPath": f"{settings.IMAGE_CONTEXT_PATH}{settings.EAS_DRIVE_NAME}/{self.tenant_id}/images/{file_name}"
        }

    def get_children_api(self, folder_id):
        if not folder_id:
            url = "https://graph.microsoft.com/v1.0/me/drive/root?expand=children(select=id,name,folder,size)"
        else:
            url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}?expand=children(select=id,name,folder,size)"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers)
        return resp.json()

    def get_file_metadata_api(self, file_id):
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}?select=name,size,@microsoft.graph.downloadUrl,fileSystemInfo"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers)
        return resp.json()

    def get_thumbnail_api(self, file_id):
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/thumbnails"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers)
        data = resp.json()
        
        values = data.get("value", [])
        if values:
            thumb_url = values[0].get("medium", {}).get("url")
            if thumb_url:
                r = requests.get(thumb_url)
                encoded = base64.b64encode(r.content).decode("utf-8")
                return f"data:image/jpg;base64,{encoded}"
        return ""
