import os
import json
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


class BaseDropboxView(APIView):
    authentication_classes = [MemberJWTAuthentication]
    permission_classes = [WhitelistPermission]

    def get_user_identifier(self, tenant):
        return f"{tenant.ten_first_name}_{tenant.ten_last_name}_{tenant.ten_id}"

    def get_token_path(self, tenant):
        user_id = self.get_user_identifier(tenant)
        return os.path.join(settings.DROPBOX_TOKEN_DIR, f"{user_id}.json")

    def save_token(self, tenant, access_token):
        path = self.get_token_path(tenant)
        data = {"access_token": access_token}
        with open(path, 'w') as f:
            json.dump(data, f)

    def get_token(self, tenant):
        path = self.get_token_path(tenant)
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                return data.get("access_token")
        return None

    def is_authenticated(self, tenant):
        token = self.get_token(tenant)
        return token is not None and token != ""

class AuthenticateView(BaseDropboxView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)

        if self.is_authenticated(tenant):
            return api_response(200, "Already Authenticated.", {"authenticate": True})
        
        return api_response(500, "Not Authenticated.", {"authenticate": False}, sendErrorAs200=True)

class DropboxSignInView(BaseDropboxView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        url = f"https://www.dropbox.com/oauth2/authorize?client_id={settings.DROPBOX_KEY}&response_type=code&redirect_uri={settings.DROPBOX_CALLBACK_URL}"
        return redirect(url)

class OAuthCallbackView(BaseDropboxView):
    def get(self, request):
        code = request.query_params.get('code')
        file_type = request.query_params.get('fileType', "")
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)

        if not code:
             return api_response(500, "Failed to authenticate. Code missing.", {})

        url = f"{settings.DROPBOX_URL}oauth2/token?code={code}&client_id={settings.DROPBOX_KEY}&client_secret={settings.DROPBOX_SECRET}&grant_type=authorization_code&redirect_uri={settings.DROPBOX_CALLBACK_URL}"
        
        try:
            response = requests.post(url)
            data = response.json()
            if "error" in data:
                return api_response(500, "Failed to authenticate.", {})
            
            access_token = data.get("access_token")
            self.save_token(tenant, access_token)
            
            service = DropboxService(tenant, access_token)
            folders = service.get_folders()
            images = service.get_images("", file_type)
            
            return api_response(200, "Authenticated Successfully .", {
                "folderList": folders,
                "imageList": images
            })
        except Exception as e:
            return api_response(500, f"Error: {str(e)}", {})

class GetFoldersView(BaseDropboxView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        
        if not self.is_authenticated(tenant):
            return api_response(200, "Login First", {"login": False})
            
        try:
            service = DropboxService(tenant, self.get_token(tenant))
            res_body = dict()
            res_body["folderList"] = service.get_folders()
            res_body["login"] = True
            return api_response(200, "Fetched Folders Successfully", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class GetImagesView(BaseDropboxView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        folder_path = request.query_params.get("F", "")
        file_type = request.query_params.get("fileType", "")
        
        if not self.is_authenticated(tenant):
            return api_response(200, "Login First", {"login": False})
            
        try:
            decoded_path = unquote(folder_path) if folder_path else ""
            service = DropboxService(tenant, self.get_token(tenant))
            res_body = dict()
            res_body["imageList"] = service.get_images(decoded_path, file_type)
            res_body["login"] = True
            return api_response(200, "Fetched Images Successfully", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class SearchView(BaseDropboxView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        path = request.query_params.get("path", "")
        search_str = request.query_params.get("searchStr", "")
        file_type = request.query_params.get("fileType", "")
        
        if not self.is_authenticated(tenant):
            return api_response(200, "Login First", {"login": False})
            
        try:
            if path == "root":
                path = ""
            decoded_path = unquote(path) if path else ""
            service = DropboxService(tenant, self.get_token(tenant))
            res_body = service.get_search_result(decoded_path, search_str, file_type)
            res_body["login"] = True
            return api_response(200, "", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class DownloadView(BaseDropboxView):
    def get(self, request):
        tenant_id = get_final_tenant_id(request=request)
        path = request.query_params.get("path", "")
        fn = request.query_params.get("fn", "")
        
        try:
            if path == "root":
                path = ""
            decoded_path = unquote(path) if path else ""
            decoded_fn = unquote(fn) if fn else ""
            
            tenant = Tenants.objects.get(ten_id=tenant_id)
            service = DropboxService(tenant, self.get_token(tenant))
            res_body = service.download_image(decoded_path, decoded_fn)
            return api_response(200, "", res_body)
        except Exception as e:
            return api_response(500, "Internal Server Error", {"error": str(e)})

class DropboxService:
    def __init__(self, tenant, token):
        self.tenant = tenant
        self.token = token
        self.tenant_id = tenant.ten_id

    def get_folders(self):
        root_list = []
        self.walk("", None, root_list)
        return root_list

    def walk(self, path, name, result_list):
        current = {}
        if not path:
            current["text"] = "My Drive"
            current["pathValue"] = "?F="
        else:
            current["text"] = name
            current["pathValue"] = f"?F={path}"
        
        entries = self.get_file_folder_api_call(path)
        folder_entries = [e for e in entries if e.get(".tag") == "folder"]
        
        if folder_entries:
            nodes = []
            current["nodes"] = nodes
            for fe in folder_entries:
                self.walk(fe["path_lower"], fe["name"], nodes)
        
        result_list.append(current)

    def get_images(self, path, file_type):
        entries = self.get_file_folder_api_call(path)
        
        filtered = []
        for e in entries:
            if e.get(".tag") != "file":
                continue
            
            name = e.get("name", "")
            ext = name.split(".")[-1].lower() if "." in name else ""
            
            is_match = False
            if not file_type or file_type == "image":
                if ext in ["jpg", "jpeg", "png", "gif", "bmp"]:
                    is_match = True
            
            if not is_match and (not file_type or file_type == "file"):
                if ext == "pdf":
                    is_match = True
            
            if is_match:
                filtered.append(e)
        
        file_list = []
        for f in filtered:
            ext = f["name"].split(".")[-1] if "." in f["name"] else ""
            item = {
                "fileName": f["name"],
                "extension": ext,
                "fileType": "pdf" if ext.lower() == "pdf" else "image",
                "thumbnail": self.get_thumbnail_api_call(f["path_lower"]),
                "size": f.get("size", 0),
                "path": f["path_lower"]
            }
            try:
                item["lastModifiedTime"] = display_date_time(f.get("client_modified", ""))
                item["imageHeight"] = 0
                item["imageWidth"] = 0
            except:
                pass
            file_list.append(item)
            
        return file_list

    def get_search_result(self, path, query, file_type):
        url = "https://api.dropboxapi.com/2/files/search_v2"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "query": query,
            "options": {
                "path": path,
                "file_status": "active",
                "filename_only": False
            }
        }
        resp = requests.post(url, headers=headers, json=payload)
        data = resp.json()
        obj = dict()
        obj["found"] = True
        matches = data.get("matches", [])
        if not matches:
            obj["found"] = False
            return obj
            
        lst = []
        for m in matches:
            meta = m.get("metadata", {}).get("metadata", {})
            if meta.get(".tag") != "file":
                continue
            
            name = meta.get("name", "")
            ext = name.split(".")[-1].lower() if "." in name else ""
            
            is_match = False
            if not file_type or file_type == "image":
                if ext in ["jpg", "jpeg", "png", "gif", "bmp"]:
                    is_match = True
            if not is_match and (not file_type or file_type == "file"):
                if ext == "pdf":
                    is_match = True
            
            if is_match:
                item = {
                    "fileName": name,
                    "extension": ext,
                    "fileType": "pdf" if ext.lower() == "pdf" else "image",
                    "path": meta.get("path_lower"),
                    "thumbnail": self.get_thumbnail_api_call(meta.get("path_lower")),
                    "size": meta.get("size", 0)
                }
                try:
                    item["lastModifiedTime"] = display_date_time(meta.get("client_modified", ""))
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

    def download_image(self, path, file_name:str):
        file_name = re.sub(r"[^a-zA-Z0-9.\-]+", "_", file_name)
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(self.tenant_id), "images")
        if not os.path.exists(root_path):
            os.makedirs(root_path)
            
        try:
            temp_link = self.get_temp_link_api_call(path)
            if temp_link:
                resp = requests.get(temp_link)
                dest = os.path.join(root_path, file_name)
                with open(dest, "wb") as f:
                    f.write(resp.content)
        except:
            pass
            
        return {
            "downloadPath": f"{settings.IMAGE_CONTEXT_PATH}{settings.EAS_DRIVE_NAME}/{self.tenant_id}/images/{file_name}"
        }

    def get_file_folder_api_call(self, path):
        url = "https://api.dropboxapi.com/2/files/list_folder"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {"path": path}
        try:
            resp = requests.post(url, headers=headers, json=payload)
            return resp.json().get("entries", [])
        except:
            return []

    def get_thumbnail_api_call(self, path):
        url = "https://content.dropboxapi.com/2/files/get_thumbnail"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "text/plain",
            "Accept": "*/*",
            "Dropbox-API-Arg": json.dumps({"path": path, "size": "w128h128", "format": "jpeg"})
        }
        try:
            resp = requests.post(url, headers=headers)
            if resp.status_code == 200:
                encoded = base64.b64encode(resp.content).decode("utf-8")
                return f"data:image/jpg;base64,{encoded}"
        except:
            pass
        return ""

    def get_temp_link_api_call(self, path):
        url = "https://api.dropboxapi.com/2/files/get_temporary_link"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {"path": path}
        try:
            resp = requests.post(url, headers=headers, json=payload)
            return resp.json().get("link")
        except:
            return ""
