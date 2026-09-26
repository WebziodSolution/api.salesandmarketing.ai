import os
import base64
import re
import json
import shutil
from datetime import datetime
from bs4 import BeautifulSoup
import requests
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.models import SurveysTemplate
from common_app.utils import api_response, get_final_tenant_id, set_file_permissions, get_client_id_by_tenant_id
from mydesktop_app.serializers import SurveysTemplateDto, SurveysTemplateListDto, SurveysTemplateOnlyDataDto

def remove_parameter(url):
    if not url:
        return ""
    return url.split('?')[0]

def find_and_return_last_url(text):
    if not text:
        return ""
    # Look for url("...") or url(...)
    match = re.search(r'url\(["\']?(.*?)["\']?\)', text)
    if match:
        return match.group(1)
    return ""

def replace_survey_text_and_copy_image(st_data, old_link, member_id, st_id):
    bits = old_link.split("/")
    img_name = bits[-1]
    new_link = f"{settings.SITE_URL}usercontent/{member_id}/images/surveytemplate/{st_id}/{img_name}"
    st_data = st_data.replace(old_link, new_link)
    
    old_path = os.path.join(settings.ABSOLUTE_SITE_URL, old_link.replace(settings.SITE_URL, ""))
    new_path = os.path.join(settings.ABSOLUTE_SITE_URL, new_link.replace(settings.SITE_URL, ""))
    
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if os.path.exists(old_path):
        shutil.copy2(old_path, new_path)
    return st_data

def replace_survey_html_and_copy_image(st_data, part_data, member_id, st_id):
    soup = BeautifulSoup(part_data, 'html.parser')
    tags = soup.find_all(class_="mcnImage")
    for tag in tags:
        old_link = str(tag.get('src'))
        if old_link and "surveytemplate" not in old_link:
            link = remove_parameter(old_link)
            bits = link.split("/")
            img_name = bits[-1]
            new_link = f"{settings.SITE_URL}usercontent/{member_id}/images/surveytemplate/{st_id}/{img_name}"
            st_data = st_data.replace(old_link, new_link)
            
            old_path = os.path.join(settings.ABSOLUTE_SITE_URL, link.replace(settings.SITE_URL, ""))
            new_path = os.path.join(settings.ABSOLUTE_SITE_URL, new_link.replace(settings.SITE_URL, ""))
            
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            if os.path.exists(old_path):
                shutil.copy2(old_path, new_path)
    return st_data

def replace_survey_text_and_copy_image_copy(st_data, old_link, member_id, st_id):
    bits = old_link.split("/")
    img_name = bits[-1]
    new_link = f"{settings.SITE_URL}usercontent/{member_id}/images/surveytemplate/{st_id}/{img_name}"
    st_data = st_data.replace(old_link, new_link)
    return st_data

def replace_survey_html_and_copy_image_copy(st_data, part_data, member_id, st_id):
    soup = BeautifulSoup(part_data, 'html.parser')
    tags = soup.find_all(class_="mcnImage")
    for tag in tags:
        old_link = str(tag.get('src'))
        if old_link:
            link = remove_parameter(old_link)
            bits = link.split("/")
            img_name = bits[-1]
            new_link = f"{settings.SITE_URL}usercontent/{member_id}/images/surveytemplate/{st_id}/{img_name}"
            st_data = st_data.replace(old_link, new_link)
    return st_data

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def listSurveyTemplate(request, stStatus):
    try:
        final_member_id = get_final_tenant_id(request=request)

        templates = SurveysTemplate.objects.filter(member_id=get_client_id_by_tenant_id(final_member_id), st_status=stStatus).order_by('-st_id')
        serializer = SurveysTemplateListDto(templates, many=True)
        
        return api_response(status.HTTP_200_OK, "Survey List Successfully.", {"surveyTemplate": serializer.data})
    except Exception as e:
        print(f"ListSurveyTemplate Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"surveyTemplate": []})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSurveyTemplate(request):
    try:
        final_member_id = get_final_tenant_id(request=request)

        data = request.data
        st_id = data.get('stId', 0)
        
        serializer = SurveysTemplateDto(data=data)
        if not serializer.is_valid():
            return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invalid Data", {"error": "Invalid Data"})

        # Pop thumbData as it is not a model field
        serializer.validated_data.pop('thumbData', None)

        if st_id == 0:
            serializer.validated_data.pop('st_id', None)
            now = datetime.now().date()
            survey_template = serializer.save(
                member_id=get_client_id_by_tenant_id(final_member_id),
                st_status=data.get('stStatus', 0),
                st_create_date=now,
                st_update_date=now
            )
            st_id = survey_template.st_id
        else:
            survey_template = get_object_or_404(SurveysTemplate, st_id=st_id)
            for attr, value in serializer.validated_data.items():
                setattr(survey_template, attr, value)
            survey_template.st_update_date = datetime.now().date()
            survey_template.save()

        # Image Handling
        thumb_data = data.get('thumbData', '')
        if thumb_data:
            thumb_data = thumb_data.replace("data:image/png;base64,", "").replace(" ", "")
            decoded_bytes = base64.b64decode(thumb_data)
            
            file_dir = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "surveytemplate", str(st_id))
            os.makedirs(file_dir, exist_ok=True)
            file_path = os.path.join(file_dir, "thumb.png")
            set_file_permissions(file_path, decoded_bytes)

        # HTML Processing
        st_html = survey_template.st_html or ""
        # Remove zero-width characters
        st_html = st_html.replace("\u200C", "").replace("\u200B", "").replace("&ZeroWidthSpace;", "")
        
        soup = BeautifulSoup(st_html, 'html.parser')
        st_html = str(soup)
        
        tags = soup.find_all(class_="mcnImage")
        for tag in tags:
            old_link = str(tag.get('src'))
            if old_link and "surveytemplate" not in old_link:
                link = remove_parameter(old_link)
                bits = link.split("/")
                img_name = bits[-1]
                new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/surveytemplate/{st_id}/{img_name}"
                st_html = st_html.replace(old_link, new_link)
                
                old_path = os.path.join(settings.ABSOLUTE_SITE_URL, link.replace(settings.SITE_URL, ""))
                new_path = os.path.join(settings.ABSOLUTE_SITE_URL, new_link.replace(settings.SITE_URL, ""))
                
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                if os.path.exists(old_path):
                    shutil.copy2(old_path, new_path)

        # center tags with item-path
        center_tags = soup.find_all('center')
        for tag in center_tags:
            old_link = str(tag.get('item-path'))
            if old_link:
                link = remove_parameter(old_link)
                bits = link.split("/")
                img_name = bits[-1]
                new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/surveytemplate/{st_id}/{img_name}"
                st_html = st_html.replace(old_link, new_link)

        # process st_data
        st_data = survey_template.st_data or ""
        if st_data:
            sry_data = json.loads(st_data)
            if 'thankYou' in sry_data:
                st_data = replace_survey_html_and_copy_image(st_data, sry_data['thankYou'], final_member_id, st_id)
            if 'header' in sry_data:
                st_data = replace_survey_html_and_copy_image(st_data, sry_data['header'], final_member_id, st_id)
            
            if 'settings' in sry_data and 'pageSettings' in sry_data['settings']:
                bg_image = sry_data['settings']['pageSettings'].get('backgroundImage', 'none')
                if bg_image != 'none':
                    old_link = find_and_return_last_url(bg_image)
                    if old_link:
                        st_data = replace_survey_text_and_copy_image(st_data, old_link, final_member_id, st_id)

            if 'surveysPages' in sry_data:
                for page in sry_data['surveysPages']:
                    if page.get('spgType') == 'Question Page':
                        if 'imageBlockPageLayoutSetting' in page:
                            layout_setting = page['imageBlockPageLayoutSetting']
                            if layout_setting.get('layoutType') != 'imageBlockPageLayout1' and layout_setting.get('layoutImage') != 'none':
                                old_link = find_and_return_last_url(layout_setting['layoutImage'])
                                if old_link:
                                    st_data = replace_survey_text_and_copy_image(st_data, old_link, final_member_id, st_id)
                        
                        if 'surveysQuestions' in page:
                            for question in page['surveysQuestions']:
                                if question.get('squeType') in ['image_form', 'image_with_text_form']:
                                    if 'surveysOptions' in question:
                                        for option in question['surveysOptions']:
                                            old_link = option.get('soptValue', '')
                                            if old_link:
                                                st_data = replace_survey_text_and_copy_image(st_data, old_link, final_member_id, st_id)
                    
                    if page.get('spgType') == 'Landing Page':
                        if 'blockList' in page:
                            st_data = replace_survey_html_and_copy_image(st_data, page['blockList'], final_member_id, st_id)

        # compressed HTML
        st_html = re.sub(r'[\r\n]+', '', st_html)
        st_html = re.sub(r'>\s+<', '><', st_html)
        
        survey_template.st_html = st_html
        survey_template.st_data = st_data
        survey_template.save()

        msg = "Survey Data Added Successfully." if data.get('stId', 0) == 0 else "Survey Data Updated Successfully"
        return api_response(status.HTTP_200_OK, msg, {"error": ""})

    except Exception as e:
        print(f"SaveSurveyTemplate Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Invalid Data", {"error": "Invalid Data"})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyTemplateById(request, stId):
    try:
        survey_template = get_object_or_404(SurveysTemplate, st_id=stId)
        serializer = SurveysTemplateDto(survey_template)
        data = serializer.data
        
        # Java logic: if no_of_question is "0", set it to ""
        if data.get('stNoOfQuestion') == "0":
            data['stNoOfQuestion'] = ""
            
        return api_response(status.HTTP_200_OK, "Fetch Survey Data Successfully.", {"surveyTemplate": data, "error": ""})
    except Exception as e:
        print(f"GetSurveyTemplateById Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"error": "Data Not Found"})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSurveyTemplate(request, stId):
    try:
        final_member_id = get_final_tenant_id(request=request)

        if stId > 0:
            SurveysTemplate.objects.filter(st_id=stId, member_id=get_client_id_by_tenant_id(final_member_id)).delete()
            file_dir = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "surveytemplate", str(stId))
            if os.path.exists(file_dir):
                shutil.rmtree(file_dir)
        
        return api_response(status.HTTP_200_OK, "Survey Deleted Successfully.", {"error": ""})
    except Exception as e:
        print(f"DeleteSurveyTemplate Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"error": "Exception While Deleting Survey Template"})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyTemplateOnlyDataById(request, stId):
    try:
        survey_template = get_object_or_404(SurveysTemplate, st_id=stId)
        serializer = SurveysTemplateOnlyDataDto(survey_template)
        return api_response(status.HTTP_200_OK, "Fetch Survey Data Successfully.", {"surveyTemplate": serializer.data, "error": ""})
    except Exception as e:
        print(f"GetSurveyTemplateOnlyDataById Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"error": "Data Not Found"})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyTemplateCopy(request, subMemberId, stId):
    try:
        final_member_id = get_final_tenant_id(request=request)

        with transaction.atomic():
            # replicating surveyTemplateCopy logic
            # Typically this would be a procedure or a complex SQL, but we can do it with Django ORM if we know the structure.
            # Java: surveysTemplateRepository.surveyTemplateCopy(memberId, subMemberId, stId);
            # Then getLastInsertRecord
            

            original = get_object_or_404(SurveysTemplate, st_id=stId)
            copy = SurveysTemplate.objects.get(st_id=stId) # Load fresh
            copy.pk = None # Create new record
            copy.member_id = get_client_id_by_tenant_id(final_member_id)
            copy.sub_member_id = subMemberId
            copy.st_create_date = datetime.now()
            copy.st_update_date = datetime.now()
            copy.st_name = original.st_name + " copy"
            copy.st_data = original.st_data
            copy.st_html = original.st_html
            copy.st_logic_flow = original.st_logic_flow
            copy.st_category_page_list = original.st_category_page_list
            copy.st_total_questions = original.st_total_questions
            copy.st_description = original.st_description
            copy.st_type = original.st_type
            copy.st_survey_about = original.st_survey_about
            copy.st_survey_goal = original.st_survey_goal
            copy.st_survey_goal_description = original.st_survey_goal_description
            copy.st_survey_type = original.st_survey_type
            copy.st_no_of_question = original.st_no_of_question
            copy.save()
            new_st_id = copy.st_id

            # File handling
            old_folder = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "surveytemplate", str(stId))
            new_folder = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "surveytemplate", str(new_st_id))
            
            if os.path.exists(old_folder):
                os.makedirs(new_folder, exist_ok=True)
                # Need to be careful with copytree if new_folder already exists or is deep
                # using shutil.copytree(old_folder, new_folder, dirs_exist_ok=True) if python >= 3.8
                for item in os.listdir(old_folder):
                    s = os.path.join(old_folder, item)
                    d = os.path.join(new_folder, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)

            # HTML/Data link replacement
            st_html = copy.st_html or ""
            st_html = st_html.replace("\u200C", "").replace("\u200B", "").replace("&ZeroWidthSpace;", "")
            
            soup = BeautifulSoup(st_html, 'html.parser')
            st_html = str(soup)
            
            tags = soup.find_all(class_="mcnImage")
            for tag in tags:
                old_link = str(tag.get('src'))
                if old_link:
                    link = remove_parameter(old_link)
                    bits = link.split("/")
                    img_name = bits[-1]
                    new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/surveytemplate/{new_st_id}/{img_name}"
                    st_html = st_html.replace(old_link, new_link)
                    
                    if "easdrive" in old_link:
                        try:
                            resp = requests.get(old_link)
                            if resp.status_code == 200:
                                with open(os.path.join(new_folder, img_name), "wb") as f:
                                    f.write(resp.content)
                        except: pass

            center_tags = soup.find_all('center')
            for tag in center_tags:
                old_link = str(tag.get('item-path'))
                if old_link:
                    link = remove_parameter(old_link)
                    bits = link.split("/")
                    img_name = bits[-1]
                    new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/surveytemplate/{new_st_id}/{img_name}"
                    st_html = st_html.replace(old_link, new_link)
                    
                    if "easdrive" in old_link:
                        try:
                            resp = requests.get(old_link)
                            if resp.status_code == 200:
                                with open(os.path.join(new_folder, img_name), "wb") as f:
                                    f.write(resp.content)
                        except: pass

            st_data = copy.st_data or ""
            if st_data:
                data_json = json.loads(st_data)
                if 'thankYou' in data_json:
                    st_data = replace_survey_html_and_copy_image_copy(st_data, data_json['thankYou'], final_member_id, new_st_id)
                if 'header' in data_json:
                    st_data = replace_survey_html_and_copy_image_copy(st_data, data_json['header'], final_member_id, new_st_id)
                
                if 'settings' in data_json and 'pageSettings' in data_json['settings']:
                    bg_image = data_json['settings']['pageSettings'].get('backgroundImage', 'none')
                    if bg_image != 'none':
                        old_link = find_and_return_last_url(bg_image)
                        if old_link:
                            st_data = replace_survey_text_and_copy_image_copy(st_data, old_link, final_member_id, new_st_id)

                if 'surveysPages' in data_json:
                    for page in data_json['surveysPages']:
                        # Replace spgId with 0 as in Java
                        spg_id = page.get('spgId')
                        if spg_id:
                            st_data = st_data.replace(f'"spgId":{spg_id}', '"spgId":0')
                        
                        if page.get('spgType') == 'Question Page':
                            if 'imageBlockPageLayoutSetting' in page:
                                layout_setting = page['imageBlockPageLayoutSetting']
                                if layout_setting.get('layoutType') != 'imageBlockPageLayout1' and layout_setting.get('layoutImage') != 'none':
                                    old_link = find_and_return_last_url(layout_setting['layoutImage'])
                                    if old_link:
                                        st_data = replace_survey_html_and_copy_image_copy(st_data, old_link, final_member_id, new_st_id)
                            
                            if 'surveysQuestions' in page:
                                for question in page['surveysQuestions']:
                                    sque_id = question.get('squeId')
                                    if sque_id:
                                        st_data = st_data.replace(f'"squeId":{sque_id}', '"squeId":0')
                                    
                                    if question.get('squeType') in ['image_form', 'image_with_text_form']:
                                        if 'surveysOptions' in question:
                                            for option in question['surveysOptions']:
                                                old_link = option.get('soptValue', '')
                                                if old_link:
                                                    st_data = replace_survey_text_and_copy_image_copy(st_data, old_link, final_member_id, new_st_id)
                        
                        if page.get('spgType') == 'Landing Page':
                            if 'blockList' in page:
                                st_data = replace_survey_html_and_copy_image_copy(st_data, page['blockList'], final_member_id, new_st_id)

            st_html = re.sub(r'[\r\n]+', '', st_html)
            st_html = re.sub(r'>\s+<', '><', st_html)
            
            copy.st_html = st_html
            copy.st_data = st_data
            copy.save()

            return api_response(status.HTTP_200_OK, "Copy Survey Successfully.", {"stId": new_st_id, "error": ""})

    except Exception as e:
        print(f"GetSurveyTemplateCopy Error: {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", {"error": "Invalid Data", "stId": 0})
