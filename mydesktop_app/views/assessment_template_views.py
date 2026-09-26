import os
import re
import json
import base64
import shutil
import requests
from datetime import datetime
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from bs4 import BeautifulSoup
from assessment_app.models import AssessmentsTemplate
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id


# Helper to format dates according to user requirements (MM-dd-yyyy)
def format_date(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.strftime('%m-%d-%Y')

def format_date_time(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    return dt.strftime('%m-%d-%Y %H:%M:%S')

def remove_parameter(url):
    if '?' in url:
        return url.split('?')[0]
    return url

def find_and_return_last_url(text):
    regex_url = r"((http|https)://)(www\.)?[a-zA-Z0-9@:%._\+~#?&//=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%._\+~#?&//=]*)"
    matches = re.findall(regex_url, text)
    if matches:
        # re.findall returns tuples if there are groups. We want the full URL.
        # This regex has groups, so we need to be careful.
        # Better to use re.finditer or adjust regex.
        urls = [m.group() for m in re.finditer(regex_url, text)]
        return urls[-1] if urls else ""
    return ""

def replace_assessment_text_and_copy_image(at_data, old_link, tenant_id, at_id):
    site_url = getattr(settings, 'SITE_URL', '')
    file_directory_absolute = getattr(settings, 'ABSOLUTE_SITE_URL', '')
    
    bits = old_link.split('/')
    img_name = bits[-1]
    new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{at_id}/{img_name}"
    at_data = at_data.replace(old_link, new_link)
    
    old_path = os.path.join(file_directory_absolute, old_link.replace(site_url, "").replace("/", os.sep))
    new_path = os.path.join(file_directory_absolute, new_link.replace(site_url, "").replace("/", os.sep))
    
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if os.path.exists(old_path):
        shutil.copy2(old_path, new_path)
    
    return at_data

def replace_assessment_html_and_copy_image(at_data, part_data, tenant_id, at_id):
    site_url = getattr(settings, 'SITE_URL', '')
    file_directory_absolute = getattr(settings, 'ABSOLUTE_SITE_URL', '')
    
    soup = BeautifulSoup(part_data, 'html.parser')
    tags = soup.find_all(class_="mcnImage")
    for tag in tags:
        old_link = tag.get('src')
        if old_link and "assessmenttemplate" not in old_link:
            link = remove_parameter(old_link)
            bits = link.split('/')
            img_name = bits[-1]
            new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{at_id}/{img_name}"
            at_data = at_data.replace(old_link, new_link)
            
            old_path = os.path.join(file_directory_absolute, link.replace(site_url, "").replace("/", os.sep))
            new_path = os.path.join(file_directory_absolute, new_link.replace(site_url, "").replace("/", os.sep))
            
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            if os.path.exists(old_path):
                shutil.copy2(old_path, new_path)
                
    return at_data

def replace_assessment_text_and_copy_image_copy(at_data, old_link, tenant_id, at_id):
    site_url = getattr(settings, 'SITE_URL', '')
    bits = old_link.split('/')
    img_name = bits[-1]
    new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{at_id}/{img_name}"
    at_data = at_data.replace(old_link, new_link)
    return at_data

def replace_assessment_html_and_copy_image_copy(at_data, part_data, tenant_id, at_id):
    site_url = getattr(settings, 'SITE_URL', '')
    soup = BeautifulSoup(part_data, 'html.parser')
    tags = soup.find_all(class_="mcnImage")
    for tag in tags:
        old_link = tag.get('src')
        if old_link:
            link = remove_parameter(old_link)
            bits = link.split('/')
            img_name = bits[-1]
            new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{at_id}/{img_name}"
            at_data = at_data.replace(old_link, new_link)
    return at_data

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentTemplateList(request, atStatus):
    tenant_id = get_final_tenant_id(request=request)
    templates = AssessmentsTemplate.objects.filter(at_client_id=get_client_id_by_tenant_id(tenant_id), at_status=atStatus).only('at_id', 'at_name')

    assessment_template_list = []
    for at in templates:
        assessment_template_list.append({
            "atId": at.at_id,
            "atName": at.at_name
        })
        
    return api_response(200, "Success", {"assessmentTemplate": assessment_template_list})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def saveAssessmentTemplate(request):
    tenant_id = get_final_tenant_id(request=request)
    data = request.data
    at_id = int(data.get('atId', 0))
    
    res_body = {"error": ""}
    
    site_url = getattr(settings, 'SITE_URL', '')
    file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')
    file_directory_absolute = getattr(settings, 'ABSOLUTE_SITE_URL', '')
    
    try:
        if at_id == 0:
            at = AssessmentsTemplate()
            at.at_client_id = get_client_id_by_tenant_id(tenant_id)
            at.at_name = data.get('atName')
            at.at_data = data.get('atData')
            at.at_status = data.get('atStatus', 0)
            at.at_html = data.get('atHtml', "")
            at.at_logic_flow = data.get('atLogicFlow', "")
            at.at_analysis = data.get('atAnalysis', "")
            at.at_category_page_list = data.get('atCategoryPageList', "")
            at.at_total_questions = data.get('atTotalQuestions', 0)
            at.at_create_date = datetime.now()
            at.at_update_date = datetime.now()
            at.save()
            at_id = at.at_id
        else:
            at = get_object_or_404(AssessmentsTemplate, at_id=at_id)
            at.at_name = data.get('atName')
            at.at_data = data.get('atData')
            at.at_status = data.get('atStatus', 0)
            at.at_html = data.get('atHtml', "")
            at.at_logic_flow = data.get('atLogicFlow', "")
            at.at_analysis = data.get('atAnalysis', "")
            at.at_category_page_list = data.get('atCategoryPageList', "")
            at.at_total_questions = data.get('atTotalQuestions', 0)
            at.at_update_date = datetime.now()
            at.save()

        # ThumbData processing
        thumb_data = data.get("thumbData", "")
        if thumb_data:
            thumb_data = thumb_data.replace("data:image/png;base64,", "").replace(" ", "")
            try:
                decoded_bytes = base64.b64decode(thumb_data)
                # Note: Adjusting path to match Java: FILE_DIRECTORY + memberId +"/images/assessmenttemplate/"+atId
                thumb_dir = os.path.join(file_directory, str(tenant_id), "images", "assessmenttemplate", str(at_id))
                os.makedirs(thumb_dir, exist_ok=True)
                thumb_path = os.path.join(thumb_dir, "thumb.png")
                with open(thumb_path, "wb") as f:
                    f.write(decoded_bytes)
            except Exception as e:
                print(f"Error saving thumb: {e}")

        # HTML cleaning
        at_html = data.get("atHtml", "")
        at_html = at_html.replace("\u200C", "").replace("\u200B", "")
        at_html = at_html.replace("&ZeroWidthSpace;", "")

        soup = BeautifulSoup(at_html, 'html.parser')
        at_html = str(soup)
        
        # Element processing (mcnImage)
        tags = soup.find_all(class_="mcnImage")
        for tag in tags:
            old_link = str(tag.get('src'))
            if old_link and "assessmenttemplate" not in old_link:
                link = remove_parameter(old_link)
                bits = link.split('/')
                img_name = bits[-1]
                new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{at_id}/{img_name}"
                at_html = at_html.replace(old_link, new_link)
                
                old_path = os.path.join(file_directory_absolute, link.replace(site_url, "").replace("/", os.sep))
                new_path = os.path.join(file_directory_absolute, new_link.replace(site_url, "").replace("/", os.sep))
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                if os.path.exists(old_path):
                    shutil.copy2(old_path, new_path)

        # Center tags with item-path
        tags = soup.find_all("center")
        for tag in tags:
            old_link = str(tag.get('item-path'))
            if old_link:
                link = remove_parameter(old_link)
                bits = link.split('/')
                img_name = bits[-1]
                new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{at_id}/{img_name}"
                at_html = at_html.replace(old_link, new_link)

        # JSON Data processing
        at_data = data.get("atData", "{}")
        try:
            ass_data = json.loads(at_data)
            
            if "thankYou" in ass_data:
                at_data = replace_assessment_html_and_copy_image(at_data, ass_data["thankYou"], tenant_id, at_id)
            
            if "header" in ass_data:
                at_data = replace_assessment_html_and_copy_image(at_data, ass_data["header"], tenant_id, at_id)

            settings_json = ass_data.get("settings", {})
            page_settings = settings_json.get("pageSettings", {})
            background_image = page_settings.get("backgroundImage", "none")
            if background_image != "none":
                old_link = find_and_return_last_url(background_image)
                if old_link:
                    at_data = replace_assessment_text_and_copy_image(at_data, old_link, tenant_id, at_id)

            assessments_pages = ass_data.get("assessmentsPages", [])
            old_link_layout_list = []
            for page in assessments_pages:
                if page.get("apgType") == "Question Page":
                    if "imageBlockPageLayoutSetting" in page:
                        img_setting = page["imageBlockPageLayoutSetting"]
                        if img_setting.get("layoutType") != "imageBlockPageLayout1" and img_setting.get("layoutImage") != "none":
                            old_link = find_and_return_last_url(img_setting["layoutImage"])
                            if old_link:
                                old_link_layout_list.append(old_link)
                                at_data = replace_assessment_text_and_copy_image(at_data, old_link, tenant_id, at_id)
                    
                    if "assessmentsQuestions" in page:
                        for question in page["assessmentsQuestions"]:
                            if question.get("aqueType") in ["image_form", "image_with_text_form"]:
                                if "assessmentsOptions" in question:
                                    for option in question["assessmentsOptions"]:
                                        old_link = option.get("aoptValue", "")
                                        if old_link:
                                            at_data = replace_assessment_text_and_copy_image(at_data, old_link, tenant_id, at_id)
                
                if page.get("apgType") == "Landing Page" and "blockList" in page:
                    at_data = replace_assessment_html_and_copy_image(at_data, page["blockList"], tenant_id, at_id)

            # Further layout replacements in at_html
            for old_link in old_link_layout_list:
                link = remove_parameter(old_link)
                bits = link.split('/')
                img_name = bits[-1]
                new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{at_id}/{img_name}"
                at_html = at_html.replace(old_link, new_link)

        except Exception as e:
            print(f"Error processing atData: {e}")

        # Minification
        at_html = re.sub(r"[\r\n]+", "", at_html)
        at_html = re.sub(r">\s+<", "><", at_html)
        
        at.at_html = at_html
        at.at_data = at_data
        at.save()

    except Exception as ex:
        print(f"SaveAssessmentTemplate Error: {ex}")
        res_body["error"] = "Invalid data"
        return api_response(400, "Invalid data", res_body)
        
    return api_response(200, "Assessment Data Added Successfully" if at_id == 0 else "Assessment Data Updated Successfully", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentTemplateById(request, at_id):
    res_body = dict()
    res_body["error"] = ""
    try:
        at = get_object_or_404(AssessmentsTemplate, at_id=at_id)
        
        # Mapping to match DTO
        res_body["assessmentTemplate"] = {
            "atId": at.at_id,
            "clientId": at.at_client_id,
            "atName": at.at_name,
            "atData": at.at_data,
            "atStatus": at.at_status,
            "atCreateDate": format_date(at.at_create_date),
            "atUpdateDate": format_date(at.at_update_date),
            "atHtml": at.at_html,
            "atLogicFlow": at.at_logic_flow,
            "atAnalysis": at.at_analysis,
            "atCategoryPageList": at.at_category_page_list,
            "atTotalQuestions": at.at_total_questions
        }
    except Exception as ex:
        print(f"GetAssessmentTemplateById Error: {ex}")
        return api_response(400, "Data Not Found", {"error": "Data Not Found"})
        
    return api_response(200, "Success", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def deleteAssessmentTemplate(request, at_id):
    tenant_id = get_final_tenant_id(request=request)
    file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')
    
    try:
        if at_id > 0:
            AssessmentsTemplate.objects.filter(at_id=at_id, at_client_id=get_client_id_by_tenant_id(tenant_id)).delete()
            at_dir = os.path.join(file_directory, str(tenant_id), "images", "assessmenttemplate", str(at_id))
            if os.path.exists(at_dir):
                shutil.rmtree(at_dir, ignore_errors=True)
        return api_response(200, "Deleted Successfully", "")
    except Exception as e:
        print(f"DeleteAssessmentTemplate Error: {e}")
        return api_response(500, "Exception While Deleting Assessment Template", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentTemplateOnlyDataById(request, at_id):
    res_body = dict()
    res_body["error"] = ""
    try:
        at = get_object_or_404(AssessmentsTemplate, at_id=at_id)
        res_body["assessmentTemplate"] = {
            "atId": at.at_id,
            "atData": at.at_data
        }
    except Exception as ex:
        print(f"GetAssessmentTemplateOnlyDataById Error: {ex}")
        return api_response(400, "Data Not Found", {"error": "Data Not Found"})
        
    return api_response(200, "Success", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def getAssessmentTemplateCopy(request, subMemberId, atId):
    tenant_id = get_final_tenant_id(request=request)
    res_body = {"error": "", "atId": 0}
    
    site_url = getattr(settings, 'SITE_URL', '')
    file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')
    
    try:
        # Replicating the INSERT ... SELECT logic
        old_at = get_object_or_404(AssessmentsTemplate, at_id=atId, at_client_id=get_client_id_by_tenant_id(tenant_id))
        new_at = AssessmentsTemplate.objects.create(
            at_client_id=old_at.at_client_id,
            at_name=old_at.at_name + " copy",
            at_data=old_at.at_data,
            at_status=old_at.at_status,
            at_html=old_at.at_html,
            at_logic_flow=old_at.at_logic_flow,
            at_analysis=old_at.at_analysis,
            at_category_page_list=old_at.at_category_page_list,
            at_total_questions=old_at.at_total_questions,
            at_create_date=datetime.now(),
            at_update_date=datetime.now()
        )
        new_at_id = new_at.at_id
        res_body["atId"] = new_at_id
        
        # Copy directory
        old_dir = os.path.join(file_directory, str(tenant_id), "images", "assessmenttemplate", str(atId))
        new_dir = os.path.join(file_directory, str(tenant_id), "images", "assessmenttemplate", str(new_at_id))
        
        if os.path.exists(old_dir):
            os.makedirs(new_dir, exist_ok=True)
            for item in os.listdir(old_dir):
                s = os.path.join(old_dir, item)
                d = os.path.join(new_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)

        # Process atHtml for the copy
        at_html = new_at.at_html
        at_html = at_html.replace("\u200C", "").replace("\u200B", "")
        at_html = at_html.replace("&ZeroWidthSpace;", "")
        
        soup = BeautifulSoup(at_html, 'html.parser')
        at_html = str(soup)

        # Element processing (mcnImage)
        tags = soup.find_all(class_="mcnImage")
        for tag in tags:
            old_link = str(tag.get('src'))
            if old_link:
                link = remove_parameter(old_link)
                bits = link.split('/')
                img_name = bits[-1]
                new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{new_at_id}/{img_name}"
                at_html = at_html.replace(old_link, new_link)
                
                if "easdrive" in old_link:
                    try:
                        resp = requests.get(old_link)
                        if resp.status_code == 200:
                            target_path = os.path.join(new_dir, img_name)
                            with open(target_path, "wb") as f:
                                f.write(resp.content)
                    except Exception as e:
                        print(f"Error downloading easdrive image: {e}")

        # Center tags
        tags = soup.find_all("center")
        for tag in tags:
            old_link = str(tag.get('item-path'))
            if old_link:
                link = remove_parameter(old_link)
                bits = link.split('/')
                img_name = bits[-1]
                new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{new_at_id}/{img_name}"
                at_html = at_html.replace(old_link, new_link)
                
                if "easdrive" in old_link:
                    try:
                        resp = requests.get(old_link)
                        if resp.status_code == 200:
                            target_path = os.path.join(new_dir, img_name)
                            with open(target_path, "wb") as f:
                                f.write(resp.content)
                    except Exception as e:
                        print(f"Error downloading easdrive image: {e}")

        # JSON Data processing for copy
        at_data = new_at.at_data
        try:
            ass_data = json.loads(at_data)
            
            if "thankYou" in ass_data:
                at_data = replace_assessment_html_and_copy_image_copy(at_data, ass_data["thankYou"], tenant_id, new_at_id)
            
            if "header" in ass_data:
                at_data = replace_assessment_html_and_copy_image_copy(at_data, ass_data["header"], tenant_id, new_at_id)

            settings_json = ass_data.get("settings", {})
            page_settings = settings_json.get("pageSettings", {})
            background_image = page_settings.get("backgroundImage", "none")
            if background_image != "none":
                old_link = find_and_return_last_url(background_image)
                if old_link:
                    at_data = replace_assessment_text_and_copy_image_copy(at_data, old_link, tenant_id, new_at_id)

            assessments_pages = ass_data.get("assessmentsPages", [])
            old_link_layout_list = []
            for page in assessments_pages:
                # Replace apgId with 0
                apg_id = page.get("apgId")
                if apg_id:
                    at_data = at_data.replace(f'"apgId":{apg_id}', '"apgId":0')
                
                if page.get("apgType") == "Question Page":
                    if "imageBlockPageLayoutSetting" in page:
                        img_setting = page["imageBlockPageLayoutSetting"]
                        if img_setting.get("layoutType") != "imageBlockPageLayout1" and img_setting.get("layoutImage") != "none":
                            old_link = find_and_return_last_url(img_setting["layoutImage"])
                            if old_link:
                                old_link_layout_list.append(old_link)
                                at_data = replace_assessment_html_and_copy_image_copy(at_data, old_link, tenant_id, new_at_id)
                    
                    if "assessmentsQuestions" in page:
                        for question in page["assessmentsQuestions"]:
                            # Replace aqueId with 0
                            aque_id = question.get("aqueId")
                            if aque_id:
                                at_data = at_data.replace(f'"aqueId":{aque_id}', '"aqueId":0')

                            if question.get("aqueType") in ["image_form", "image_with_text_form"]:
                                if "assessmentsOptions" in question:
                                    for option in question["assessmentsOptions"]:
                                        old_link = option.get("aoptValue", "")
                                        if old_link:
                                            at_data = replace_assessment_text_and_copy_image_copy(at_data, old_link, tenant_id, new_at_id)
                
                if page.get("apgType") == "Landing Page" and "blockList" in page:
                    at_data = replace_assessment_html_and_copy_image_copy(at_data, page["blockList"], tenant_id, new_at_id)

            # Further layout replacements in at_html
            for old_link in old_link_layout_list:
                link = remove_parameter(old_link)
                bits = link.split('/')
                img_name = bits[-1]
                new_link = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{new_at_id}/{img_name}"
                at_html = at_html.replace(old_link, new_link)

        except Exception as e:
            print(f"Error processing atData Copy: {e}")

        # Minification
        at_html = re.sub(r"[\r\n]+", "", at_html)
        at_html = re.sub(r">\s+<", "><", at_html)
        
        new_at.at_html = at_html
        new_at.at_data = at_data
        new_at.save()

    except Exception as e:
        print(f"GetAssessmentTemplateCopy Error: {e}")
        return api_response(400, "Invalid Data", {"error": "Invalid Data", "atId": 0})
        
    return api_response(200, "Success", res_body)
