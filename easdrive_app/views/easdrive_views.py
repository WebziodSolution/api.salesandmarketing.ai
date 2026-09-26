import os
import shutil
import base64
import time
import requests
import re
from django.conf import settings
from rest_framework.views import APIView
from common_app.custom_permissions import WhitelistPermission
from auth_app.authentication import MemberJWTAuthentication
from common_app.utils import get_final_tenant_id, set_file_permissions, display_date_time, api_response, \
    get_client_id_by_tenant_id
from easdrive_app.utils import get_tree, join_images
from PIL import Image
from common_app.services import CommonServices

class BaseEasDriveView(APIView):
    authentication_classes = [MemberJWTAuthentication]
    permission_classes = [WhitelistPermission]

    def get_member_id(self, request):
        return get_final_tenant_id(request=request)

    def record_ai_transaction(self, request, transaction_type):
        member_id = self.get_member_id(request)

        country_setting = CommonServices.country_setting_by_tenant_id(member_id)
        if not country_setting:
            return
            
        total_amount = 0
        transaction_name = ""
        if transaction_type == 1:
            transaction_name = "AI Generated Image"
            total_amount = getattr(country_setting, 'ctny_ai_generated_image', 0)
        elif transaction_type == 2:
            transaction_name = "AI Edited Image"
            total_amount = getattr(country_setting, 'ctny_ai_edited_image', 0)
            
        CommonServices.saveCampaignTransaction(
            None,
            transaction_name,
            1,
            "AI",
            None,
            "uninvoiced",
            None,
            get_client_id_by_tenant_id(member_id),
            "0",
            total_amount,
            total_amount,
            0,
            None,
            None,
            0
        )

class GetFoldersView(BaseEasDriveView):
    def get(self, request):
        member_id = self.get_member_id(request)
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        if not os.path.exists(root_path):
            os.makedirs(root_path)
        
        folder_list = get_tree(root_path)
        return api_response(200, "Fetched folders successfully", {"getFolders": folder_list})

class CreateFolderView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        data = request.data
        destination = data.get("destination", "root")
        new_folder_name = data.get("newFolderName", "").strip()
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        
        if destination == "root":
            dest_path = os.path.join(root_path, new_folder_name)
        else:
            dest_path = os.path.join(root_path, destination, new_folder_name)
            
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)
            return api_response(200, "1", {})
        else:
            return api_response(200, "2", {})

class CopyFoldersAndFilesView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        data = request.data
        destination = data.get("destination", "root")
        sources = data.get("source", [])
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        dest_dir = root_path if destination == "root" else os.path.join(root_path, destination)
        
        for src_rel in sources:
            src_path = os.path.join(root_path, src_rel)
            if os.path.exists(src_path):
                dest_path = os.path.join(dest_dir, os.path.basename(src_path))
                if os.path.isdir(src_path):
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)
                    shutil.copytree(src_path, dest_path)
                else:
                    shutil.copy2(src_path, dest_path)
        
        return api_response(200, "Copy Successfully", {})


class DeleteFoldersAndFilesView(BaseEasDriveView):
    def post(self, request):
        data = request.data
        member_id = self.get_member_id(request)
        if member_id > 0:
            member_id = self.get_member_id(request)
        else:
            member_id = data.get("memberId",None)
            
        sources = data.get("source", [])
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        
        for src_rel in sources:
            src_path = os.path.join(root_path, src_rel)
            if os.path.exists(src_path):
                if os.path.isdir(src_path):
                    shutil.rmtree(src_path)
                else:
                    os.remove(src_path)
                    
        return api_response(200, "Deletion Successfully", {})

class CutFoldersAndFilesView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        data = request.data
        destination = data.get("destination", "root")
        sources = data.get("source", [])
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        dest_dir = root_path if destination == "root" else os.path.join(root_path, destination)
        
        for src_rel in sources:
            src_path = os.path.join(root_path, src_rel)
            if os.path.exists(src_path):
                dest_path = os.path.join(dest_dir, os.path.basename(src_path))
                if os.path.exists(dest_path):
                    if os.path.isdir(dest_path):
                        shutil.rmtree(dest_path)
                    else:
                        os.remove(dest_path)
                shutil.move(src_path, dest_path)
                
        return api_response(200, "Cut Successfully", {})

class GetImagesView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        data = request.data
        current_folder = data.get("currentFolder", "root")
        search_term = data.get("searchTerm", "").lower()
        file_type_requested = data.get("fileType", "")
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        folder_path = root_path if current_folder == "root" else os.path.join(root_path, current_folder)
        
        base_url = f"{settings.IMAGE_CONTEXT_PATH}{settings.EAS_DRIVE_NAME}/{member_id}/images/"
        if current_folder != "root":
            base_url += current_folder + "/"

        file_list = []
        if os.path.exists(folder_path):
            entries = os.listdir(folder_path)
            for entry in entries:
                if search_term and search_term not in entry.lower():
                    continue
                
                full_path = os.path.join(folder_path, entry)
                if not os.path.isfile(full_path):
                    continue
                    
                is_img = entry.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'))
                
                item_type = "image" if is_img else "file"
                if file_type_requested and file_type_requested != item_type:
                    continue
                
                stat = os.stat(full_path)
                if stat.st_size == 0 and is_img:
                    continue
                
                img_data = {
                    "fileType": item_type,
                    "imageWidth": 0,
                    "imageHeight": 0,
                    "url": base_url + entry,
                    "fileName": entry,
                    "imageSize": stat.st_size,
                    "lastModifiedTime": display_date_time(round(stat.st_mtime))
                }
                
                if is_img:
                    try:
                        with Image.open(full_path) as img:
                            img_data["imageWidth"], img_data["imageHeight"] = img.size
                    except:
                        pass
                
                file_list.append(img_data)
                
        return api_response(200, "", {"fileList": file_list})

class FileUploadView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        destination = request.data.get("destination", "root")
        file_type = request.data.get("fileType", "")
        file_url_base64 = request.data.get("fileURL", "")
        
        uploaded_file = request.FILES.get('file')
        if not uploaded_file and not file_url_base64:
             return api_response(400, "File or destination folder path is missing", {})

        if uploaded_file:
            filename = re.sub(r"[^a-zA-Z0-9.\-]+", "_", uploaded_file.name)
        else:
            filename = f"upload_{int(time.time())}.{file_type.split('/')[-1]}"
            
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        dest_dir = root_path if destination == "root" else os.path.join(root_path, destination)
        
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            
        dest_file_path = os.path.join(dest_dir, filename)
        
        if file_url_base64:
            head = f"data:{file_type};base64,"
            clean_base64 = file_url_base64.replace(head, "").replace(" ", "")
            decoded_bytes = base64.b64decode(clean_base64)
            set_file_permissions(dest_file_path, decoded_bytes)
        elif uploaded_file:
            with open(dest_file_path, 'wb+') as destination_file:
                for chunk in uploaded_file.chunks():
                    destination_file.write(chunk)
        
        rel_path = "" if destination == "root" else destination + "/"
        image_url = f"{settings.SITE_URL}easdrive/{member_id}/images/{rel_path}{filename}"
        return api_response(200, "", {"imageUrl": image_url})


class ImportImageFromUrlView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        if member_id > 0:
            member_id = self.get_member_id(request)
        else:
            member_id = request.data.get("memberId",None)
            
        image_url = request.data.get("imageUrl")
        destination = request.data.get("destination", "root")
        
        filename = re.sub(r"[^a-zA-Z0-9.\-]+", "_", image_url.split("/")[-1])
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        dest_dir = root_path if destination == "root" else os.path.join(root_path, destination)
        
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            
        dest_file_path = os.path.join(dest_dir, filename)
        
        response = requests.get(image_url, timeout=5, verify=False)
        if response.status_code == 200:
            set_file_permissions(dest_file_path, response.content)
            
        rel_path = "" if destination == "root" else destination + "/"
        return api_response(200, "Image Imported Successfully", {"imageUrl": f"{settings.SITE_URL}easdrive/{member_id}/images/{rel_path}{filename}"})

class ImportImageFromAiUrlView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        image_url = request.data.get("imageUrl")
        filename = request.data.get("fileName")
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        if not os.path.exists(root_path):
            os.makedirs(root_path)
            
        dest_file_path = os.path.join(root_path, filename)
        
        response = requests.get(image_url)
        if response.status_code == 200:
            with open(dest_file_path, "wb") as f:
                f.write(response.content)
            
        self.record_ai_transaction(request, 1)
        
        return api_response(200, "Image Imported Successfully", {"imageUrl": f"{settings.SITE_URL}easdrive/{member_id}/images/{filename}"})

class ImportVideoImageFromUrlView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        download_url = request.data.get("downloadImageUrl")
        
        filename = f"{int(time.time() * 1000)}{download_url.split('/')[-1]}"
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        if not os.path.exists(root_path):
            os.makedirs(root_path)
            
        dest_file_path = os.path.join(root_path, filename)
        
        bg_response = requests.get(download_url)
        if bg_response.status_code == 200:
            with open(dest_file_path, "wb") as f:
                f.write(bg_response.content)
                
            play_button_url = f"{settings.SITE_URL}img/play-button.png"
            play_response = requests.get(play_button_url, timeout=5)
            if play_response.status_code == 200:
                play_btn_temp = os.path.join(settings.BASE_DIR, "tmp_play_button.png")
                with open(play_btn_temp, "wb") as f:
                    f.write(play_response.content)
                
                join_images(dest_file_path, play_btn_temp, dest_file_path)
                try: os.remove(play_btn_temp)
                except: pass
                    
        return_url = f"{settings.IMAGE_CONTEXT_PATH}{settings.EAS_DRIVE_NAME}/{member_id}/images/{filename}"
        return api_response(200, "Image Imported Successfully", {"imageUrl": return_url})

class EditImageView(BaseEasDriveView):
    def post(self, request):
        member_id = self.get_member_id(request)
        data = request.data
        image_data = data.get("imageData", "")
        image_name = data.get("imageName", "")
        image_path = data.get("imagePath", "")
        
        root_path = os.path.join(settings.EAS_DRIVE_BASE_PATH, str(member_id), "images")
        
        if not image_path:
            full_dest_path = os.path.join(root_path, image_name)
        else:
            if "mypage" in image_path:
                full_dest_path = os.path.join(root_path, image_name)
            else:
                full_dest_path = os.path.join(root_path, image_path, image_name)
                
        clean_base64 = image_data.replace("data:image/png;base64,", "").replace(" ", "")
        decoded_bytes = base64.b64decode(clean_base64)
        
        set_file_permissions(full_dest_path, decoded_bytes)
        
        self.record_ai_transaction(request, 2)
        
        rel_path = "" if not image_path or "mypage" in image_path else image_path
        return_path = f"{settings.IMAGE_CONTEXT_PATH}{settings.EAS_DRIVE_NAME}/{member_id}/images/{rel_path}{image_name}"
        
        return api_response(200, "Save image successfully", {"imagePath": return_path})

class AiTransactionsView(BaseEasDriveView):
    def post(self, request):
        try:
            ai_transaction_type = int(request.query_params.get("aiTransactionType", 0))
            self.record_ai_transaction(request, ai_transaction_type)
            return api_response(200, "AI Transaction saved successfully", {})
        except Exception:
            return api_response(500, "Error saving AI Transaction", {})
