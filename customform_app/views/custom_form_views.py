import os
import logging
import base64
import json
import time
import uuid
import shutil
import re
from django.conf import settings
from django.db import transaction, connection
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from bs4 import BeautifulSoup
from django.core.paginator import Paginator
from django.utils import timezone
from rest_framework.request import Request
from common_app.models import (
    CustomForm, CustomFormPages, CustomFormQuestions, CustomFormOptions,
    CustomFormOptionsColumns, CustomFormStatistics, CustomFormAnswers,
    CustomFormToGroups, Surveys, CustomFormReportPdf
)
from assessment_app.models import Assessments
from django.db.models import Q
from common_app.utils import api_response, get_final_tenant_id, set_file_permissions, get_client_id_by_tenant_id
from common_app.decrypt_string import DecryptString
from common_app.services import CommonServices, MailRequestDTO

logger = logging.getLogger(__name__)

# Helper Functions
def entity_to_dto_custom_form_pages(entities):
    dtos = []
    for entity in entities:
        dtos.append({
            "pageId": entity.pageId,
            "pageCfId": entity.pageCfId,
            "pageNumber": entity.pageNumber,
            "pageType": entity.pageType
        })
    return dtos

def entity_to_dto_custom_form_questions(entities):
    dtos = []
    for entity in entities:
        dtos.append({
            "queId": entity.queId,
            "quePageId": entity.quePageId,
            "queType": entity.queType,
            "queQuestion": entity.queQuestion,
            "queDisplayOrder": entity.queDisplayOrder
        })
    return dtos

def entity_to_dto_custom_form_options(entities):
    dtos = []
    for entity in entities:
        dtos.append({
            "optId": entity.optId,
            "optQueId": entity.optQueId,
            "optValue": entity.optValue,
            "optDescription": entity.optDescription,
            "optDisplayOrder": entity.optDisplayOrder,
            "optHasCommnets": entity.optHasCommnets
        })
    return dtos

def entity_to_dto_custom_form_options_columns(entities):
    dtos = []
    for entity in entities:
        dtos.append({
            "optId": entity.optId,
            "optQueId": entity.optQueId,
            "optValue": entity.optValue,
            "optDisplayOrder": entity.optDisplayOrder
        })
    return dtos

def entity_to_dto_custom_form_statistics(entity):
    return {
        "stId": entity.stId,
        "stCfId": entity.stCfId,
        "stSessionId": entity.stSessionId,
        "stIpAddress": entity.stIpAddress,
        "stCity": entity.stCity,
        "stState": entity.stState,
        "stCountry": entity.stCountry,
        "stTechnology": entity.stTechnology,
        "stSources": entity.stSources,
        "stIsComplete": entity.stIsComplete,
        "stQueComplete": entity.stQueComplete,
        "stDate": entity.stDate.strftime('%m-%d-%Y %H:%M:%S') if getattr(entity, 'stDate', None) else None
    }

def entity_to_dto_custom_form_answers(entities):
    dtos = []
    for entity in entities:
        dtos.append({
            "ansId": entity.ansId,
            "ansStId": entity.ansStId,
            "ansQueId": entity.ansQueId,
            "ansPageId": entity.ansPageId,
            "ansAnswers": entity.ansAnswers,
            "ansComments": entity.ansComments
        })
    return dtos

def entity_to_dto_custom_form(entity):
    return {
        "cfId": entity.cfId,
        "memberId": entity.memberId,
        "cfFormName": entity.cfFormName,
        "cfFormMetaKeyWord": entity.cfFormMetaKeyWord,
        "cfFormMetaDescription": entity.cfFormMetaDescription,
        "cfFormData": entity.cfFormData,
        "cfFormHtml": entity.cfFormHtml,
        "cfFormStatus": entity.cfFormStatus,
        "cfCreateDate": entity.cfCreateDate.strftime('%m/%d/%Y') if entity.cfCreateDate else None,
        "cfUpdateDate": entity.cfUpdateDate.strftime('%m/%d/%Y') if entity.cfUpdateDate else None,
        "cfSendNotificationEmail": entity.cfSendNotificationEmail,
        "cfSendNotificationConfirmation": entity.cfSendNotificationConfirmation,
        "cfFormType": entity.cfFormType,
        "cfFormToGroupYN": entity.cfFormToGroupYN,
        "cfGroupId": entity.cfGroupId,
        "cfMapping": entity.cfMapping if entity.cfMapping != '' and entity.cfMapping else None
    }

def get_new_link(old_link, member_id, cf):
    if not old_link: return ""
    # Remove parameters and get filename
    link_base = old_link.split('?')[0]
    img_name = os.path.basename(link_base)
    return f"{settings.SITE_URL}usercontent/{member_id}/images/customform/{cf.cfId}/{img_name}"

def get_local_path(url):
    # Maps usercontent URL to local path
    if not url or settings.SITE_URL not in url:
        return ""
    rel_path = url.replace(settings.SITE_URL, settings.ABSOLUTE_SITE_URL)
    return rel_path

def copy_image(old_link, new_link):
    old_path = get_local_path(old_link.split('?')[0])
    new_path = get_local_path(new_link)
    if old_path and os.path.exists(old_path) and old_path != new_path:
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        try:
            shutil.copy2(old_path, new_path)
        except Exception as e:
            logger.error(f"Image copy error from {old_path} to {new_path}: {e}")

def find_and_return_last_url(text):
    if not text:
        return ""
    regex_url = r"((?:http|https)://)(?:www\.)?[a-zA-Z0-9@:%._\+~#?&//=]{2,256}\.[a-z]{2,6}\b[-a-zA-Z0-9@:%._\+~#?&//=]*"
    url = ""
    for m in re.finditer(regex_url, text):
        url = m.group()
    return url

def replace_custom_form_text_and_copy_image(cf_form_data, old_link, client_id, cf_id):
    if not old_link:
        return cf_form_data
    link = old_link.split('?')[0]
    img_name = os.path.basename(link)
    new_link = f"{settings.SITE_URL}usercontent/{client_id}/images/customform/{cf_id}/{img_name}"
    cf_form_data = cf_form_data.replace(old_link, new_link)
    copy_image(old_link, new_link)
    return cf_form_data

def replace_custom_form_html_and_copy_image(cf_form_data, part_data, client_id, cf_id):
    if not part_data:
        return cf_form_data
    soup = BeautifulSoup(part_data, 'html.parser')
    tags = soup.select(".mcnImage")
    for tag in tags:
        old_link = tag.get('src')
        if old_link and "customform" not in old_link:
            link = old_link.split('?')[0]
            img_name = os.path.basename(link)
            new_link = f"{settings.SITE_URL}usercontent/{client_id}/images/customform/{cf_id}/{img_name}"
            cf_form_data = cf_form_data.replace(old_link, new_link)
            copy_image(old_link, new_link)
    return cf_form_data

def replace_custom_form_text_and_copy_image_copy(cf_form_data, old_link, client_id, new_cf_id):
    if not old_link:
        return cf_form_data
    link = old_link.split('?')[0]
    img_name = os.path.basename(link)
    new_link = f"{settings.SITE_URL}usercontent/{client_id}/images/customform/{new_cf_id}/{img_name}"
    cf_form_data = cf_form_data.replace(old_link, new_link)
    return cf_form_data

def replace_custom_form_html_and_copy_image_copy(cf_form_data, part_data, client_id, new_cf_id):
    if not part_data:
        return cf_form_data
    soup = BeautifulSoup(part_data, 'html.parser')
    tags = soup.select(".mcnImage")
    for tag in tags:
        old_link = tag.get('src')
        if old_link:
            link = old_link.split('?')[0]
            img_name = os.path.basename(link)
            new_link = f"{settings.SITE_URL}usercontent/{client_id}/images/customform/{new_cf_id}/{img_name}"
            cf_form_data = cf_form_data.replace(old_link, new_link)
    return cf_form_data

@api_view(['GET'])
def getCustomFormList(request, cfFormStatus):
    """
    Retrieve a list of custom forms for a member.
    Path: /v1/customForm/getCustomFormList
    """
    try:
        final_member_id = get_final_tenant_id(request=request)
        
        custom_forms = CustomForm.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id), cfFormStatus=cfFormStatus)
        
        res_list = []
        for cf in custom_forms:
            res_list.append({
                "cfId": cf.cfId,
                "cfFormName": cf.cfFormName,
                "customFormUrl": f"{settings.SITE_URL}customform?v={DecryptString.set_enc_dec_user(str(cf.cfId), '', 'Y')}",
                "cfCreateDate": cf.cfCreateDate.strftime('%m-%d-%Y') if cf.cfCreateDate else None,
                "id": DecryptString.set_enc_dec_user(str(cf.cfId), "", "Y")
            })
            
        return api_response(200, "Success", {"customFormList": res_list})
    except Exception as e:
        logger.error(f"getCustomFormList Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['GET'])
def getCustomForm(request, cfId):
    """
    Retrieve details of a specific custom form by ID.
    Path: /v1/customForm/getCustomForm/{cfId}
    """
    try:
        cf = get_object_or_404(CustomForm, cfId=cfId)
        res_body = {
            "cfId": cf.cfId,
            "cfFormName": cf.cfFormName,
            "cfFormHtml": cf.cfFormHtml,
            "cfFormData": cf.cfFormData,
            "cfFormToGroupYN": cf.cfFormToGroupYN,
            "cfGroupId": cf.cfGroupId,
            "cfMapping": cf.cfMapping,
            "cfSendNotificationConfirmation": cf.cfSendNotificationConfirmation,
            "cfSendNotificationEmail": cf.cfSendNotificationEmail
        }
        return api_response(200, "Success", {"customForm": res_body})
    except Exception as e:
        logger.error(f"getCustomForm Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['POST'])
def saveCustomForm(request: Request):
    """
    Save or update a custom form.
    Path: /v1/customForm/saveCustomForm
    """
    data = request.data
    final_member_id = get_final_tenant_id(request=request)
    client_id = get_client_id_by_tenant_id(final_member_id)
    cf_id_original = int(data.get('cfId', 0))
    
    res_body = {
        "error": "",
        "customFormLinkUrl": ""
    }
    inner_res_body = {}
    
    try:
        try:
            with transaction.atomic():
                cf_id = cf_id_original
                if cf_id == 0:
                    cf = CustomForm()
                    cf.memberId = client_id
                    cf.cfFormName = data.get('cfFormName')
                    cf.cfFormMetaKeyWord = data.get('cfFormMetaKeyWord')
                    cf.cfFormMetaDescription = data.get('cfFormMetaDescription')
                    cf.cfFormData = data.get('cfFormData', '')
                    cf.cfFormStatus = data.get('cfFormStatus')
                    cf.cfCreateDate = timezone.now().date()
                    cf.cfUpdateDate = timezone.now().date()
                    cf.cfSendNotificationEmail = data.get('cfSendNotificationEmail')
                    cf.cfFormHtml = data.get('cfFormHtml', '')
                    cf.cfSendNotificationConfirmation = data.get('cfSendNotificationConfirmation', 'N')
                    cf.cfFormType = data.get('cfFormType')
                    cf.cfFormToGroupYN = data.get('cfFormToGroupYN', 'No')
                    cf.cfGroupId = data.get('cfGroupId', 0)
                    cf.cfMapping = data.get('cfMapping')
                    cf.subMemberId = data.get('subMemberId', 0)
                    cf.save()
                    cf_id = cf.cfId
                    if cf.cfFormStatus == 1:
                        cf.cfTinyUrl = f"{settings.SITE_URL}customform?v={DecryptString.set_enc_dec_user(str(cf_id), '', 'Y')}"
                        cf.save()
                else:
                    cf = CustomForm.objects.select_for_update().get(cfId=cf_id)
                    cf.cfFormName = data.get('cfFormName')
                    cf.subMemberId = data.get('subMemberId', 0)
                    cf.cfFormMetaKeyWord = data.get('cfFormMetaKeyWord')
                    cf.cfFormMetaDescription = data.get('cfFormMetaDescription')
                    cf.cfFormData = data.get('cfFormData', '')
                    cf.cfFormStatus = data.get('cfFormStatus')
                    cf.cfSendNotificationEmail = data.get('cfSendNotificationEmail')
                    cf.cfUpdateDate = timezone.now().date()
                    cf.cfFormHtml = data.get('cfFormHtml', '')
                    cf.cfSendNotificationConfirmation = data.get('cfSendNotificationConfirmation', 'N')
                    cf.cfFormType = data.get('cfFormType')
                    cf.cfFormToGroupYN = data.get('cfFormToGroupYN', 'No')
                    cf.cfGroupId = data.get('cfGroupId', 0)
                    cf.cfMapping = data.get('cfMapping')
                    
                    if cf.cfFormStatus == 1:
                        cf.cfTinyUrl = f"{settings.SITE_URL}customform?v={DecryptString.set_enc_dec_user(str(cf_id), '', 'Y')}"
                    cf.save()

                # Form to Group Mapping Start
                try:
                    CustomFormToGroups.objects.filter(ftgCfId=cf_id).delete()
                except Exception:
                    pass
                # Form to Group Mapping End

                # Thumbnail replacement
                thumb_data = data.get('thumbData')
                if thumb_data:
                    thumb_data = thumb_data.replace("data:image/png;base64,", "").replace(" ", "")
                    missing_padding = len(thumb_data) % 4
                    if missing_padding:
                        thumb_data += '=' * (4 - missing_padding)
                    decoded_bytes = base64.b64decode(thumb_data)
                    folder_path = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), 'images', 'customform', str(cf_id))
                    os.makedirs(folder_path, exist_ok=True)
                    thumb_path = os.path.join(folder_path, "thumb.png")
                    set_file_permissions(thumb_path, decoded_bytes)

                # HTML replacement
                cf_form_html = cf.cfFormHtml
                if cf_form_html:
                    cf_form_html = cf_form_html.replace("\u200C", "").replace("\u200B", "")
                    cf_form_html = cf_form_html.replace("\\xE2\\x80\\x8B", "").replace("\\xE2\\x80\\x8C", "")
                    cf_form_html = cf_form_html.replace("&ZeroWidthSpace;", "")

                    soup = BeautifulSoup(cf_form_html, 'html.parser')
                    cf_form_html = str(soup)

                    tags = soup.select(".mcnImage")
                    for tag in tags:
                        old_link = tag.get('src')
                        if old_link and "customform" not in old_link:
                            link = old_link.split('?')[0]
                            img_name = os.path.basename(link)
                            new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/customform/{cf_id}/{img_name}"
                            cf_form_html = cf_form_html.replace(old_link, new_link)
                            copy_image(old_link, new_link)

                    try:
                        center_tags = soup.find_all("center", attrs={"item-path": True})
                        for tag in center_tags:
                            old_link = tag.get("item-path")
                            if old_link:
                                link = old_link.split('?')[0]
                                img_name = os.path.basename(link)
                                new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/customform/{cf_id}/{img_name}"
                                cf_form_html = cf_form_html.replace(old_link, new_link)
                    except Exception as e:
                        logger.error(f"[ memberId : {client_id} ] SaveCustomFormData Error 0 : {e}")

                # JSON cfFormData replacement
                old_link_layout_list = []
                cf_form_data = cf.cfFormData
                if cf_form_data:
                    try:
                        form_data_json = json.loads(cf_form_data)

                        if "thankYou" in form_data_json:
                            cf_form_data = replace_custom_form_html_and_copy_image(cf_form_data, form_data_json["thankYou"], final_member_id, cf_id)

                        if "header" in form_data_json:
                            cf_form_data = replace_custom_form_html_and_copy_image(cf_form_data, form_data_json["header"], final_member_id, cf_id)

                        settings_block = form_data_json.get("settings", {})
                        page_settings = settings_block.get("pageSettings", {})
                        background_image = page_settings.get("backgroundImage", "none")

                        if background_image != "none":
                            old_link = find_and_return_last_url(background_image)
                            if old_link:
                                cf_form_data = replace_custom_form_text_and_copy_image(cf_form_data, old_link, final_member_id, cf_id)

                        custom_form_pages_list = form_data_json.get("customFormPages", [])
                        for page in custom_form_pages_list:
                            page_type = page.get("pageType", "")
                            if page_type == "Question Page":
                                if "imageBlockPageLayoutSetting" in page:
                                    layout_setting = page["imageBlockPageLayoutSetting"]
                                    if layout_setting.get("layoutType") != "imageBlockPageLayout1" and layout_setting.get("layoutImage") != "none":
                                        old_link = find_and_return_last_url(layout_setting.get("layoutImage", ""))
                                        if old_link:
                                            old_link_layout_list.append(old_link)
                                            cf_form_data = replace_custom_form_text_and_copy_image(cf_form_data, old_link, final_member_id, cf_id)

                                if "customFormQuestions" in page:
                                    for question in page["customFormQuestions"]:
                                        que_type = question.get("queType", "")
                                        if que_type in ["image_form", "image_with_text_form"]:
                                            if "customFormOptions" in question:
                                                for option in question["customFormOptions"]:
                                                    opt_value = option.get("optValue", "")
                                                    if opt_value:
                                                        cf_form_data = replace_custom_form_text_and_copy_image(cf_form_data, opt_value, final_member_id, cf_id)

                            elif page_type == "Landing Page":
                                if "blockList" in page:
                                    cf_form_data = replace_custom_form_html_and_copy_image(cf_form_data, page["blockList"], final_member_id, cf_id)

                        try:
                            for old_link in old_link_layout_list:
                                link = old_link.split('?')[0]
                                img_name = os.path.basename(link)
                                new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/customform/{cf_id}/{img_name}"
                                cf_form_html = cf_form_html.replace(old_link, new_link)
                        except Exception as e:
                            logger.error(f"[ memberId : {client_id} ] SaveCustomFormData Error 1 : {e}")

                    except Exception as json_err:
                        logger.error(f"JSON processing error in image replacement: {json_err}")

                # Save updated HTML/JSON to CustomForm
                if cf_form_html:
                    cf_form_html = re.sub(r'[\r\n]+', '', cf_form_html)
                    cf_form_html = re.sub(r'>\s+<', '><', cf_form_html)
                    cf.cfFormHtml = cf_form_html

                cf.cfFormData = cf_form_data
                cf.save()

                # Publish logic if status == 1
                if cf.cfFormStatus == 1:
                    if cf.cfFormData:
                        # Clean up existing structure to avoid duplicates/orphans
                        page_ids = CustomFormPages.objects.filter(pageCfId=cf_id).values_list('pageId', flat=True)
                        que_ids = CustomFormQuestions.objects.filter(quePageId__in=page_ids).values_list('queId', flat=True)
                        
                        CustomFormOptions.objects.filter(optQueId__in=que_ids).delete()
                        CustomFormOptionsColumns.objects.filter(optQueId__in=que_ids).delete()
                        CustomFormQuestions.objects.filter(quePageId__in=page_ids).delete()
                        CustomFormPages.objects.filter(pageCfId=cf_id).delete()

                        json_cf_form_data = cf.cfFormData
                        cf_data = json.loads(json_cf_form_data)
                        
                        custom_form_pages = cf_data.get("customFormPages", [])
                        for p_data in custom_form_pages:
                            page = CustomFormPages.objects.create(
                                pageCfId=cf_id,
                                pageNumber=p_data.get('pageNumber', 0),
                                pageType=p_data.get('pageType')
                            )
                            json_cf_form_data = json_cf_form_data.replace('"pageId":0', f'"pageId":{page.pageId}', 1)

                            custom_form_questions = p_data.get("customFormQuestions", [])
                            for q_data in custom_form_questions:
                                que = CustomFormQuestions.objects.create(
                                    quePageId=page.pageId,
                                    queQuestion=q_data.get('queQuestion'),
                                    queType=q_data.get('queType'),
                                    queDisplayOrder=q_data.get('queDisplayOrder', 0)
                                )

                                # Form to Group Mapping Start
                                if cf.cfFormToGroupYN == 'Yes' and cf.cfMapping:
                                    try:
                                        mapping_json = json.loads(cf.cfMapping)
                                        for key, val in mapping_json.items():
                                            if val == que.queQuestion:
                                                inner_res_body[key] = que.queId
                                    except Exception as e:
                                        logger.error(f"Error mapping form to group: {e}")
                                # Form to Group Mapping End

                                json_cf_form_data = json_cf_form_data.replace('"queId":0', f'"queId":{que.queId}', 1)

                                if que.queType == 'matrix':
                                    for row in q_data.get('rows', []):
                                        CustomFormOptions.objects.create(
                                            optQueId=que.queId,
                                            optValue=row.get('optValue'),
                                            optDisplayOrder=row.get('optDisplayOrder', 0),
                                            optHasCommnets=0
                                        )
                                    for col in q_data.get('columns', []):
                                        CustomFormOptionsColumns.objects.create(
                                            optQueId=que.queId,
                                            optValue=col.get('optValue'),
                                            optDisplayOrder=col.get('optDisplayOrder', 0)
                                        )
                                else:
                                    for opt in q_data.get('customFormOptions', []):
                                        CustomFormOptions.objects.create(
                                            optQueId=que.queId,
                                            optValue=opt.get('optValue'),
                                            optDisplayOrder=opt.get('optDisplayOrder', 0),
                                            optDescription=opt.get('optDescription'),
                                            optHasCommnets=1 if opt.get('optComment') == 'yes' else 0
                                        )

                        cf.cfFormData = json_cf_form_data
                        cf.save()

                # Form to Group Mapping Save
                if cf.cfFormToGroupYN == 'Yes':
                    for key, val in inner_res_body.items():
                        CustomFormToGroups.objects.create(
                            ftgGroupId=cf.cfGroupId,
                            ftgCfId=cf_id,
                            ftgField=key,
                            ftgValue=val
                        )

                # Set customFormLinkUrl if status == 1
                res_body["customFormLinkUrl"] = ""
                if cf.cfFormStatus == 1:
                    res_body["customFormLinkUrl"] = f"{settings.SITE_URL}customform?v={DecryptString.set_enc_dec_user(str(cf_id), '', 'Y')}"

        except Exception as ex:
            logger.error(f"[ memberId : {client_id} ] SaveCustomFormData Error : {ex}")
            res_body["error"] = "Invalid data"

        if res_body["error"] == "":
            message = "Custom Form Data Added Successfully." if cf_id_original == 0 else "Custom Form Data Updated Successfully."
            return api_response(200, message, res_body)
        else:
            return api_response(500, "Invalid Data", res_body)

    except Exception as ex:
        logger.error(f"SaveCustomFormData Error : {ex}")
        message = "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It."
        return api_response(500, message, res_body)

@api_view(['DELETE'])
def deleteCustomForm(request, cfId):
    """
    Delete a custom form by setting status to 0.
    Path: /v1/customForm/deleteCustomForm/{cfId}
    """
    try:
        final_member_id = get_final_tenant_id(request=request)
        
        cf = get_object_or_404(CustomForm, cfId=cfId, memberId=get_client_id_by_tenant_id(final_member_id))
        # cf.cfFormStatus = 0
        cf.delete()
        
        # Cleanup images folder
        shutil.rmtree(os.path.join(settings.FILE_UPLOAD_DIR, str(get_client_id_by_tenant_id(final_member_id)), 'images', 'customform', str(cfId)), ignore_errors=True)
        
        return api_response(200, "Custom Form Deleted Successfully.", {"error": ""})
    except Exception as e:
        logger.error(f"deleteCustomForm Error: {e}")
        return api_response(500, "Invalid Data", {"error": str(e)})

@api_view(['GET'])
def getCustomFormPages(request, cfId):
    """
    Retrieve pages and questions for a specific custom form.
    Path: /v1/customForm/getCustomFormPages/{cfId}
    """
    try:
        pages = CustomFormPages.objects.filter(pageCfId=cfId).order_by('pageNumber')
        res_list = []
        for p in pages:
            p_dto = {
                "pageId": p.pageId,
                "pageCfId": p.pageCfId,
                "pageNumber": p.pageNumber,
                "pageType": p.pageType,
                "customFormQuestions": entity_to_dto_custom_form_questions(CustomFormQuestions.objects.filter(quePageId=p.pageId).order_by('queDisplayOrder'))
            }
            res_list.append(p_dto)
        return api_response(200, "Success", res_list)
    except Exception as e:
        logger.error(f"getCustomFormPages Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['GET'])
def getCustomFormQuestion(request, queId):
    """
    Retrieve details of a specific question, including its options.
    Path: /v1/customForm/getCustomFormQuestion/{queId}
    """
    try:
        q = get_object_or_404(CustomFormQuestions, queId=queId)
        res_body = dict()
        res_body["queId"] = q.queId,
        res_body["quePageId"] = q.quePageId,
        res_body["queType"] = q.queType,
        res_body["queQuestion"] = q.queQuestion,
        res_body["queDisplayOrder"] = q.queDisplayOrder
        if q.queType == 'matrix':
            res_body['rows'] = entity_to_dto_custom_form_options(CustomFormOptions.objects.filter(optQueId=queId).order_by('optDisplayOrder'))
            res_body['columns'] = entity_to_dto_custom_form_options_columns(CustomFormOptionsColumns.objects.filter(optQueId=queId).order_by('optDisplayOrder'))
        else:
            res_body['customFormOptions'] = entity_to_dto_custom_form_options(CustomFormOptions.objects.filter(optQueId=queId).order_by('optDisplayOrder'))
            
        return api_response(200, "Success", res_body)
    except Exception as e:
        logger.error(f"getCustomFormQuestion Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['GET'])
def getCustomFormCopy(request, subMemberId, cfId):
    """
    Copy an existing custom form.
    Path: /v1/customForm/getCustomFormCopy/{subMemberId}/{cfId}
    Matches Java: CustomFormServiceImpl.getCustomFormCopy
    """
    final_member_id = get_final_tenant_id(request=request)
    client_id = get_client_id_by_tenant_id(final_member_id)
    
    res_body = {
        "error": "",
        "cfId": 0
    }
    
    try:
        try:
            with transaction.atomic():
                old_cf = CustomForm.objects.get(cfId=cfId, memberId=client_id)
                
                # Create a copy in DB with status 0
                new_cf = CustomForm.objects.create(
                    memberId=old_cf.memberId,
                    cfFormName=f'{old_cf.cfFormName}-Copy',
                    cfFormMetaKeyWord=old_cf.cfFormMetaKeyWord,
                    cfFormMetaDescription=old_cf.cfFormMetaDescription,
                    cfFormData=old_cf.cfFormData,
                    cfFormStatus=0,
                    cfCreateDate=timezone.now().date(),
                    cfUpdateDate=timezone.now().date(),
                    cfSendNotificationEmail=old_cf.cfSendNotificationEmail,
                    cfFormHtml=old_cf.cfFormHtml,
                    cfSendNotificationConfirmation=old_cf.cfSendNotificationConfirmation,
                    cfFormType=old_cf.cfFormType,
                    cfFormToGroupYN=old_cf.cfFormToGroupYN,
                    cfGroupId=old_cf.cfGroupId,
                    cfMapping=old_cf.cfMapping
                )
                
                # Copy mapping data
                try:
                    old_mappings = CustomFormToGroups.objects.filter(ftgCfId=cfId)
                    for m in old_mappings:
                        CustomFormToGroups.objects.create(
                            ftgCfId=new_cf.cfId,
                            ftgField=m.ftgField,
                            ftgValue=m.ftgValue,
                            ftgGroupId=m.ftgGroupId
                        )
                except Exception:
                    pass
                
                # Copy directory
                old_folder = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "customform", str(cfId))
                new_folder = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "customform", str(new_cf.cfId))
                
                if os.path.exists(old_folder):
                    os.makedirs(new_folder, exist_ok=True)
                    for item in os.listdir(old_folder):
                        s = os.path.join(old_folder, item)
                        d = os.path.join(new_folder, item)
                        if os.path.isdir(s):
                            shutil.copytree(s, d, dirs_exist_ok=True)
                        else:
                            shutil.copy2(s, d)

                cf_form_html = new_cf.cfFormHtml
                if cf_form_html:
                    cf_form_html = cf_form_html.replace("\u200C", "").replace("\u200B", "")
                    cf_form_html = cf_form_html.replace("\\xE2\\x80\\x8B", "").replace("\\xE2\\x80\\x8C", "")
                    cf_form_html = cf_form_html.replace("&ZeroWidthSpace;", "")

                    soup = BeautifulSoup(cf_form_html, 'html.parser')
                    cf_form_html = str(soup)

                    tags = soup.select(".mcnImage")
                    for tag in tags:
                        old_link = tag.get('src')
                        if old_link:
                            link = old_link.split('?')[0]
                            img_name = os.path.basename(link)
                            new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/customform/{new_cf.cfId}/{img_name}"
                            cf_form_html = cf_form_html.replace(old_link, new_link)

                            if "easdrive" in old_link:
                                try:
                                    import requests
                                    response = requests.get(old_link, timeout=10)
                                    if response.status_code == 200:
                                        dest_path = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "customform", str(new_cf.cfId), img_name)
                                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                        with open(dest_path, "wb") as f:
                                            f.write(response.content)
                                except Exception as dl_err:
                                    logger.error(f"Failed to download easdrive image {old_link}: {dl_err}")

                    try:
                        center_tags = soup.find_all("center", attrs={"item-path": True})
                        for tag in center_tags:
                            old_link = tag.get("item-path")
                            if old_link:
                                link = old_link.split('?')[0]
                                img_name = os.path.basename(link)
                                new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/customform/{new_cf.cfId}/{img_name}"
                                cf_form_html = cf_form_html.replace(old_link, new_link)

                                if "easdrive" in old_link:
                                    try:
                                        import requests
                                        response = requests.get(old_link, timeout=10)
                                        if response.status_code == 200:
                                            dest_path = os.path.join(settings.FILE_UPLOAD_DIR, str(final_member_id), "images", "customform", str(new_cf.cfId), img_name)
                                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                            with open(dest_path, "wb") as f:
                                                f.write(response.content)
                                    except Exception as dl_err:
                                        logger.error(f"Failed to download easdrive center image {old_link}: {dl_err}")
                    except Exception as e:
                        logger.error(f"[ memberId : {client_id} ] GetCustomFormCopy Error 1 : {e}")

                old_link_layout_list = []
                cf_form_data = new_cf.cfFormData
                if cf_form_data:
                    try:
                        form_data_json = json.loads(cf_form_data)

                        if "thankYou" in form_data_json:
                            cf_form_data = replace_custom_form_html_and_copy_image_copy(cf_form_data, form_data_json["thankYou"], final_member_id, new_cf.cfId)

                        if "header" in form_data_json:
                            cf_form_data = replace_custom_form_html_and_copy_image_copy(cf_form_data, form_data_json["header"], final_member_id, new_cf.cfId)

                        settings_block = form_data_json.get("settings", {})
                        page_settings = settings_block.get("pageSettings", {})
                        background_image = page_settings.get("backgroundImage", "none")

                        if background_image != "none":
                            old_link = find_and_return_last_url(background_image)
                            if old_link:
                                cf_form_data = replace_custom_form_text_and_copy_image_copy(cf_form_data, old_link, final_member_id, new_cf.cfId)

                        custom_form_pages_list = form_data_json.get("customFormPages", [])
                        for page in custom_form_pages_list:
                            page_id = page.get("pageId", 0)
                            cf_form_data = cf_form_data.replace(f'"pageId":{page_id}', '"pageId":0')

                            page_type = page.get("pageType", "")
                            if page_type == "Question Page":
                                if "imageBlockPageLayoutSetting" in page:
                                    layout_setting = page["imageBlockPageLayoutSetting"]
                                    if layout_setting.get("layoutType") != "imageBlockPageLayout1" and layout_setting.get("layoutImage") != "none":
                                        old_link = find_and_return_last_url(layout_setting.get("layoutImage", ""))
                                        if old_link:
                                            old_link_layout_list.append(old_link)
                                            cf_form_data = replace_custom_form_text_and_copy_image_copy(cf_form_data, old_link, final_member_id, new_cf.cfId)

                                if "customFormQuestions" in page:
                                    for question in page["customFormQuestions"]:
                                        que_id = question.get("queId", 0)
                                        cf_form_data = cf_form_data.replace(f'"queId":{que_id}', '"queId":0')

                                        que_type = question.get("queType", "")
                                        if que_type in ["image_form", "image_with_text_form"]:
                                            if "customFormOptions" in question:
                                                for option in question["customFormOptions"]:
                                                    opt_value = option.get("optValue", "")
                                                    if opt_value:
                                                        cf_form_data = replace_custom_form_text_and_copy_image_copy(cf_form_data, opt_value, final_member_id, new_cf.cfId)

                            elif page_type == "Landing Page":
                                if "blockList" in page:
                                    cf_form_data = replace_custom_form_html_and_copy_image_copy(cf_form_data, page["blockList"], final_member_id, new_cf.cfId)

                        try:
                            for old_link in old_link_layout_list:
                                link = old_link.split('?')[0]
                                img_name = os.path.basename(link)
                                new_link = f"{settings.SITE_URL}usercontent/{final_member_id}/images/customform/{new_cf.cfId}/{img_name}"
                                cf_form_html = cf_form_html.replace(old_link, new_link)
                        except Exception as e:
                            logger.error(f"[ memberId : {client_id} ] GetCustomFormCopy Error 2 : {e}")

                    except Exception as json_err:
                        logger.error(f"JSON processing error in copy replacement: {json_err}")

                if cf_form_html:
                    cf_form_html = re.sub(r'[\r\n]+', '', cf_form_html)
                    cf_form_html = re.sub(r'>\s+<', '><', cf_form_html)
                    new_cf.cfFormHtml = cf_form_html

                new_cf.cfFormData = cf_form_data
                new_cf.save()
                
                res_body["cfId"] = new_cf.cfId

        except Exception as e:
            logger.error(f"[ memberId : {client_id} ] GetCustomFormCopy Error 3 : {e}")
            res_body = {
                "error": "Invalid data",
                "cfId": 0
            }

        if res_body["error"] == "":
            return api_response(200, "Fetch Custom Form Data Successfully.", res_body)
        else:
            return api_response(500, "Custom Form Not Found", res_body)

    except Exception as ex:
        logger.error(f"GetCustomFormCopy Error : {ex}")
        message = "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It."
        return api_response(500, message, res_body)

@api_view(['GET'])
def getPreviewCustomFormData(request: Request):
    """
    Retrieve preview data for a custom form, optionally with session answers.
    Path: /v1/customForm/getPreviewCustomFormData
    """
    try:
        enc_id = request.query_params.get('id')
        cf_id = int(DecryptString.set_enc_dec_user(enc_id, "display", "Y"))
        st_session_id = request.query_params.get('stSessionId', '')
        
        cf = get_object_or_404(CustomForm, cfId=cf_id)
        res_body = {
            "error": "",
            "customFormAnswers": "",
            "customForm": {
                "cfId": cf.cfId,
                "cfFormData": cf.cfFormData
            }
        }
        
        if st_session_id:
            try:
                stats = CustomFormStatistics.objects.filter(stSessionId=st_session_id, stCfId=cf_id).first()
                if stats:
                    stats_dto = dict()
                    stats_dto["stId"] = stats.stId,
                    stats_dto["stCfId"] = stats.stCfId,
                    stats_dto["stQueComplete"] = stats.stQueComplete,
                    stats_dto["stIsComplete"] = stats.stIsComplete,
                    stats_dto["stSessionId"] = stats.stSessionId,
                    stats_dto["customFormAnswers"] = []
                    answers = CustomFormAnswers.objects.filter(ansStId=stats.stId)
                    for ans in answers:
                        stats_dto["customFormAnswers"].append({
                            "ansId": ans.ansId,
                            "ansStId": ans.ansStId,
                            "ansPageId": ans.ansPageId,
                            "ansQueId": ans.ansQueId,
                            "ansAnswers": ans.ansAnswers,
                            "ansComments": ans.ansComments
                        })
                    res_body["customFormAnswers"] = stats_dto
            except Exception as e:
                logger.error(f"Preview Stats Error: {e}")
                
        return api_response(200, "Success", res_body)
    except Exception as e:
        logger.error(f"getPreviewCustomFormData Error: {e}")
        return api_response(400, "Data Not Found")

def saveFormToGroup(cf_id, st_id, cf_group_id, member_id):
    try:
        mapping = CustomFormToGroups.objects.filter(ftgCfId=cf_id)
        answers = CustomFormAnswers.objects.filter(ansStId=st_id)
        
        sql_fields = []
        sql_values = []
        params = []
        flag_email = 0
        
        for m in mapping:
            for ans in answers:
                if ans.ansQueId == m.ftgValue:
                    ans_json = json.loads(ans.ansAnswers)
                    que_type = CustomFormQuestions.objects.get(queId=ans.ansQueId).queType
                    
                    if que_type in ["rating_box", "rating_symbol", "rating_radio"]:
                        tmp_value = str(ans_json.get("value", "")).split("/")[0]
                    elif que_type == "phone":
                        tmp_value = ans_json.get("value", {}).get("PhoneNo", "")
                    else:
                        tmp_value = str(ans_json.get("value", ""))
                    
                    if m.ftgField == "UL_EMAIL":
                        flag_email = 1
                        email = tmp_value.lower().strip()
                        domain = email.split("@")[1] if "@" in email else ""
                        sql_fields.extend(["UL_EMAIL", "UL_EMAIL_DOMAIN"])
                        sql_values.extend(["%s", "%s"])
                        params.extend([email, domain])
                    elif m.ftgField == "UL_BIRTHDAY":
                        birthday = tmp_value.strip()
                        sql_fields.append("UL_BIRTHDAY")
                        sql_values.append("%s")
                        params.append(birthday)
                    else:
                        sql_fields.append(m.ftgField)
                        sql_values.append("%s")
                        params.append(tmp_value)
                        
        if sql_fields:
            fields_str = ", ".join(sql_fields)
            values_str = ", ".join(sql_values)
            type_email = 'unverified' if flag_email == 1 else 'done'
            
            full_sql = f"INSERT INTO USER_LIST ({fields_str}, UL_GROUP_ID, UL_CLIENT_ID, UL_DATE_REGISTERED, UL_STATUS, UL_SMS_STATUS, UL_TYPE_EMAIL) " \
                       f"VALUES ({values_str}, %s, %s, CURRENT_TIMESTAMP, 'Subscribed', 'Subscribed', %s)"
            params.extend([cf_group_id, member_id, type_email])
            with connection.cursor() as cursor:
                cursor.execute(full_sql, params)
    except Exception as e:
        logger.error(f"saveFormToGroup Error: {e}")

@api_view(['POST'])
def saveCustomFormAnswers(request: Request):
    """
    Save answers for a custom form submission.
    Path: /v1/customForm/saveCustomFormAnswers
    """
    try:
        data = request.data
        cf_id = data.get('stCfId')
        cf = get_object_or_404(CustomForm, cfId=cf_id)
        
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        sources = "Phone" if any(x in user_agent.lower() for x in ["iphone", "android", "mobile", "tablet"]) else "PC"
        
        st_session_id_incoming = data.get('stSessionId', '')
        st_session_id = st_session_id_incoming
        
        # Java start session logic fallback
        if not st_session_id:
            st_session_id = str(uuid.uuid4())
            
            tran_type = data.get('tranType', '')
            if tran_type in ['survey', 'assessment']:
                tran_name = f"Individual Response : {cf.cfFormName} Filled"
                tran_id_val = data.get('id')
                if tran_type == 'survey' and tran_id_val:
                    sry = Surveys.objects.filter(sryId=tran_id_val).first()
                    if sry:
                        tran_name = f"{sry.sryName}<br>Survey Response : {cf.cfFormName} Filled"
                elif tran_type == 'assessment' and tran_id_val:
                    ass = Assessments.objects.filter(assId=tran_id_val).first()
                    if ass:
                        tran_name = f"{ass.assName}<br>Assessment Response : {cf.cfFormName} Filled"
                
                country_setting = CommonServices.country_setting_by_tenant_id(cf.memberId)
                if country_setting and country_setting.cntyIndividualPrice > 0:
                    CommonServices.saveCampaignTransaction(
                        cf.cfId,
                        tran_name,
                        1,
                        tran_type,
                        None,
                        "uninvoiced",
                        None,
                        cf.memberId,
                        "0",
                        country_setting.cntyIndividualPrice,
                        country_setting.cntyIndividualPrice,
                        0,
                        None,
                        None,
                        0
                    )

        with transaction.atomic():
            stats = CustomFormStatistics.objects.filter(stSessionId=st_session_id, stCfId=cf_id).first()
            if not stats:
                stats = CustomFormStatistics(
                    stCfId=cf_id,
                    stSessionId=st_session_id,
                    stIpAddress=data.get('stIpAddress'),
                    stDate=timezone.now()
                )
            
            stats.stCity = data.get('stCity')
            stats.stState = data.get('stState')
            stats.stCountry = data.get('stCountry')
            stats.stTechnology = user_agent[:255]
            stats.stSources = sources
            stats.stIsComplete = data.get('stIsComplete', 0)
            stats.save()
            res_body = dict()
            res_body["error"] = ""
            ans_list = data.get('customFormAnswers', [])
            for a_dto in ans_list:
                que_id = a_dto.get('ansQueId')
                
                ans_id = int(a_dto.get('ansId', 0) or 0)
                # Reset Question Logic
                if a_dto.get('resetQuestion') == 'Yes':
                    ans_val = a_dto.get('ansAnswers')
                    should_reset = False
                    if not ans_val:
                        should_reset = True
                    else:
                        try:
                            val_obj = json.loads(ans_val)
                            if val_obj.get('value') is False:
                                should_reset = True
                        except: pass
                    
                    if should_reset:
                        if ans_id and ans_id > 0:
                            CustomFormAnswers.objects.filter(ansId=ans_id).delete()
                        else:
                            CustomFormAnswers.objects.filter(ansStId=stats.stId, ansQueId=que_id).delete()
                        
                        stats_dto = entity_to_dto_custom_form_statistics(stats)
                        stats_dto['customFormAnswers'] = []
                        res_body["customFormAnswers"] = stats_dto
                        return api_response(200, "Save Data Successfully", res_body)

                ans_val = a_dto.get('ansAnswers')
                comments = a_dto.get('ansComments')

                if comments:
                    try:
                        c_json = json.loads(comments)
                        cleaned_c = {k: v for k, v in c_json.items() if v}
                        comments = json.dumps(cleaned_c) if cleaned_c else None
                    except: pass
                
                que_type = CustomFormQuestions.objects.filter(queId=que_id).values_list('queType', flat=True).first()
                if que_type == 'signature' and ans_val:
                    try:
                        ans_json = json.loads(ans_val)
                        data_url = ans_json.get('value', {}).get('dataURL', '')
                        if 'base64' in data_url:
                            base64_img = data_url.split(',')[1]
                            img_bytes = base64.b64decode(base64_img)
                            file_name = f"signature_{int(time.time())}.png"
                            folder_path = os.path.join(settings.FILE_UPLOAD_DIR, str(cf.memberId), 'images', 'customform', str(cf.cfId))
                            if not os.path.exists(folder_path):
                                os.makedirs(folder_path, exist_ok=True)
                            file_path = os.path.join(folder_path, file_name)
                            set_file_permissions(file_path, img_bytes)
                            
                            file_url = f"{settings.SITE_URL}usercontent/{cf.memberId}/images/customform/{cf.cfId}/{file_name}"
                            ans_json['value']['imageUrl'] = file_url
                            ans_val = json.dumps(ans_json)
                    except Exception as sig_e:
                        logger.error(f"Signature Save Error: {sig_e}")

                if ans_id == 0:
                    CustomFormAnswers.objects.create(
                        ansStId=stats.stId,
                        ansQueId=que_id,
                        ansPageId=a_dto.get('ansPageId', 0),
                        ansAnswers=ans_val,
                        ansComments=comments
                    )
                else:
                    # Robust update or create logic
                    ans_qs = CustomFormAnswers.objects.filter(ansId=ans_id)
                    if ans_qs.exists():
                        ans_qs.update(
                            ansStId=stats.stId,
                            ansQueId=que_id,
                            ansPageId=a_dto.get('ansPageId', 0),
                            ansAnswers=ans_val,
                            ansComments=comments
                        )
                    else:
                        CustomFormAnswers.objects.create(
                            ansStId=stats.stId,
                            ansQueId=que_id,
                            ansPageId=a_dto.get('ansPageId', 0),
                            ansAnswers=ans_val,
                            ansComments=comments
                        )
            
            stats.stQueComplete = CustomFormAnswers.objects.filter(ansStId=stats.stId).count()
            stats.save()
            
            # Prepare response data
            stats_dto = entity_to_dto_custom_form_statistics(stats)
            answers_entities = CustomFormAnswers.objects.filter(ansStId=stats.stId)
            stats_dto['customFormAnswers'] = entity_to_dto_custom_form_answers(answers_entities)
            res_body["customFormAnswers"] = stats_dto
            
            
            if stats.stIsComplete == 1:
                if cf.cfFormToGroupYN == 'Yes':
                    saveFormToGroup(cf.cfId, stats.stId, cf.cfGroupId, cf.memberId)
                
                if cf.cfSendNotificationConfirmation == 'Y':
                    email_context = {
                        "FormName": cf.cfFormName,
                        "SITEURL": settings.SITE_URL,
                        "siteName": settings.SITE_NAME,
                        "toAdminSupportEmail": getattr(settings, 'SUPPORT_EMAIL', ''),
                        "siteUrlWWW": settings.SITE_URL,
                        "siteUrlWWWDisplay": settings.SITE_URL.replace("https://", "").replace("http://", ""),
                        "companyName": settings.SITE_NAME,
                        "mainCompanyName": settings.SITE_NAME,
                        "siteUrlAddress": "",
                        "siteUrlAddressBr": "",
                        "companyNumber": "",
                        "siteNameSmallCom": settings.SITE_NAME,
                        "siteNameBigCom": settings.SITE_NAME.upper(),
                    }
                    CommonServices.sendEmail(
                        MailRequestDTO(to=cf.cfSendNotificationEmail,
                                     subject="New Form Entry Submitted",
                                     template_name="form-data-template.ftl"),
                        email_context
                    )
        
        return api_response(200, "Save Data Successfully", res_body)
    except Exception as e:
        logger.error(f"saveCustomFormAnswers Error: {e}")
        return api_response(500, "Invalid Data", {"error": str(e)})


@api_view(['GET'])
def getCustomFormListPages(request: Request):
    """
    Retrieve a paginated list of custom forms.
    Path: /v1/customForm/getCustomFormListPages
    """
    try:
        
        final_member_id  = get_final_tenant_id(request=request)
        search_key = request.query_params.get('searchKey', '')
        
        page_num = int(request.query_params.get('page', 0)) + 1
        page_size = int(request.query_params.get('size', 10))
        
        queryset = CustomForm.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id), cfFormStatus=1)
        if search_key:
            queryset = queryset.filter(cfFormName__icontains=search_key)
            
        paginator = Paginator(queryset.order_by('-cfId'), page_size)
        page_obj = paginator.get_page(page_num)
        
        res_list = []
        for cf in page_obj:
            res_list.append({
                "cfId": cf.cfId,
                "cfFormName": cf.cfFormName,
                "customFormUrl": f"{settings.SITE_URL}customform?v={DecryptString.set_enc_dec_user(str(cf.cfId), '', 'Y')}",
                "cfCreateDate": cf.cfCreateDate.strftime('%m-%d-%Y') if cf.cfCreateDate else None,
                "id": DecryptString.set_enc_dec_user(str(cf.cfId), "", "Y")
            })
            
        return api_response(200, "Success", {
            "customFormList": res_list,
            "getTotalPages": paginator.num_pages,
            "getNumber": page_num - 1,
            "getSize": page_size,
            "totalCustomForm": paginator.count
        })
    except Exception as e:
        logger.error(f"getCustomFormListPages Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['GET'])
def getCustomFormReport(request: Request):
    """
    Retrieve submission statistics for a specific custom form.
    Path: /v1/customForm/getCustomFormReport
    Matches Java: CustomFormServiceImpl.getCustomFormReport
    """
    try:
        enc_id = request.query_params.get('id')
        if not enc_id:
            return api_response(400, "Form ID missing")
            
        cf_id = int(DecryptString.set_enc_dec_user(enc_id, "display", "Y"))
        search_key = request.query_params.get('searchKey', '')
        
        # Pagination
        page_num = int(request.query_params.get('page', 0))
        page_size = int(request.query_params.get('size', 10))
        
        # 1. Get CustomForm details
        custom_form = get_object_or_404(CustomForm, cfId=cf_id)
        
        # 2. Get Statistics (Paginated)
        queryset = CustomFormStatistics.objects.filter(stCfId=cf_id, stIsComplete=1)
        if search_key:
            queryset = queryset.filter(
                Q(stSessionId__icontains=search_key) |
                Q(stIpAddress__icontains=search_key) |
                Q(stCity__icontains=search_key) |
                Q(stState__icontains=search_key) |
                Q(stCountry__icontains=search_key)
            )
            
        paginator = Paginator(queryset.order_by('-stDate'), page_size)
        # Java pagination is 0-indexed, Django is 1-indexed for get_page
        current_page = paginator.get_page(page_num + 1)
        
        # 3. Total Answer Count (Based on stats records)
        total_answer = CustomFormStatistics.objects.filter(stCfId=cf_id).count()
        
        # 4. Build Report List
        custom_form_report_list = []
        
        # Get all pages of type "Question Page" once to avoid redundant queries
        form_pages = CustomFormPages.objects.filter(pageCfId=cf_id, pageType="Question Page").order_by('pageNumber')
        
        for st in current_page:
            report_dto = {
                "stId": st.stId,
                "stCity": st.stCity,
                "stState": st.stState,
                "stCountry": st.stCountry,
                "stTechnology": st.stTechnology,
                "stSources": st.stSources,
                "stIpAddress": st.stIpAddress,
                "stDate": st.stDate.strftime('%m/%d/%Y %H:%M:%S') if st.stDate else ""
            }
            
            pages_dto_list = []
            for page in form_pages:
                page_dto = dict()
                page_dto["pageId"] = page.pageId,
                page_dto["pageCfId"] = page.pageCfId,
                page_dto["pageNumber"] = page.pageNumber,
                page_dto["pageType"] = page.pageType,
                page_dto["customFormQuestions"] = []

                # Get questions for this page
                questions = CustomFormQuestions.objects.filter(quePageId=page.pageId).order_by('queDisplayOrder')
                for que in questions:
                    que_dto = {
                        "queId": que.queId,
                        "quePageId": que.quePageId,
                        "queType": que.queType,
                        "queQuestion": que.queQuestion,
                        "queDisplayOrder": que.queDisplayOrder,
                        "queAnswers": None,
                        "queComments": None,
                        "commentsColumns": []
                    }
                    
                    # Get Answer for this specific submission/question/page
                    ans = CustomFormAnswers.objects.filter(ansStId=st.stId, ansPageId=page.pageId, ansQueId=que.queId).first()
                    if ans:
                        que_dto["queAnswers"] = ans.ansAnswers
                        que_dto["queComments"] = ans.ansComments
                        
                        # Handle comment columns for single_answer types
                        if que.queType in ["single_answer", "single_answer_checkbox"]:
                            options_with_comments = CustomFormOptions.objects.filter(
                                optQueId=que.queId, 
                                optHasCommnets=1
                            ).values_list('optValue', flat=True)
                            que_dto["commentsColumns"] = list(options_with_comments)
                            
                    page_dto["customFormQuestions"].append(que_dto)
                pages_dto_list.append(page_dto)
                
            report_dto["customFormPages"] = pages_dto_list
            custom_form_report_list.append(report_dto)
            
        res_body = {
            "error": "",
            "cfId": custom_form.cfId,
            "cfName": custom_form.cfFormName,
            "getTotalPages": paginator.num_pages,
            "getNumber": page_num,
            "getSize": page_size,
            "totalAnswer": total_answer,
            "customFormReport": custom_form_report_list
        }
        
        return api_response(200, "Fetch Custom Form Data Successfully.", res_body)
    except Exception as e:
        logger.error(f"getCustomFormReport Error: {e}")
        return api_response(500, "Invalid Data", {"error": "Data Not Found"})

@api_view(['DELETE'])
def deleteCustomFormAnswers(request: Request):
    """
    Delete custom form answers based on specified criteria.
    Matches Java: CustomFormServiceImpl.deleteCustomFormAnswers
    """
    try:
        data = request.data
        st_ids = data.get('stId', [])
        
        # Ensure st_ids is a list
        if not isinstance(st_ids, list):
            st_ids = [st_ids]
            
        with transaction.atomic():
            for st_id in st_ids:
                if CustomFormStatistics.objects.filter(stId=st_id).exists():
                    try:
                        CustomFormAnswers.objects.filter(ansStId=st_id).delete()
                    except Exception as e:
                        logger.error(f"Error deleting answers for st_id {st_id}: {e}")
                    CustomFormStatistics.objects.filter(stId=st_id).delete()
                    
        return api_response(200, "Custom Form Answers Deleted Successfully.", {"error": ""})
    except Exception as e:
        logger.error(f"DeleteCustomFormAnswers Error : {e}")
        return api_response(500, "Error deleting custom form answers")

@api_view(['GET'])
def getCustomFormAllDataReport(request: Request):
    """
    Retrieve all submission data for a custom form.
    Path: /v1/customForm/getCustomFormAllDataReport
    """
    try:
        enc_id = request.query_params.get('id')
        cf_id = int(DecryptString.set_enc_dec_user(enc_id, "display", "Y"))
        
        cf = get_object_or_404(CustomForm, cfId=cf_id)
        stats_list = CustomFormStatistics.objects.filter(stCfId=cf_id)
        
        res_report = []
        for st in stats_list:
            st_dto = dict()
            st_dto["stId"] = st.stId,
            st_dto["stDate"] = st.stDate.strftime('%m-%d-%Y %H:%M:%S'),
            st_dto["stIpAddress"] = st.stIpAddress,
            st_dto["stCity"] = st.stCity,
            st_dto["stState"] = st.stState,
            st_dto["stCountry"] = st.stCountry,
            st_dto["stTechnology"] = st.stTechnology,
            st_dto["stSources"] = st.stSources,
            st_dto["customFormPages"] = []

            pages = CustomFormPages.objects.filter(pageCfId=cf_id, pageType="Question Page").order_by('pageNumber')
            for p in pages:
                p_dto = dict()
                p_dto["pageId"] = p.pageId,
                p_dto["pageNumber"] = p.pageNumber,
                p_dto["customFormQuestions"] = []
                questions = CustomFormQuestions.objects.filter(quePageId=p.pageId).order_by('queDisplayOrder')
                for q in questions:
                    ans = CustomFormAnswers.objects.filter(ansStId=st.stId, ansPageId=p.pageId, ansQueId=q.queId).first()
                    comment_cols = []
                    if q.queType in ["single_answer", "single_answer_checkbox"]:
                        opts = CustomFormOptions.objects.filter(optQueId=q.queId)
                        for o in opts:
                            if o.optHasCommnets == 1:
                                comment_cols.append(o.optValue)
                                
                    p_dto["customFormQuestions"].append({
                        "queId": q.queId,
                        "queQuestion": q.queQuestion,
                        "queType": q.queType,
                        "queAnswers": ans.ansAnswers if ans else None,
                        "queComments": ans.ansComments if ans else None,
                        "commentsColumns": comment_cols
                    })
                st_dto["customFormPages"].append(p_dto)
            res_report.append(st_dto)
            
        return api_response(200, "Success", {
            "cfId": cf.cfId,
            "cfName": cf.cfFormName,
            "customFormReport": res_report,
            "error": ""
        })
    except Exception as e:
        logger.error(f"getCustomFormAllDataReport Error: {e}")
        return api_response(400, "Data Not Found")

@api_view(['GET'])
def checkCustomFormNameExists(request: Request):
    """
    Check if a custom form name already exists for a member.
    Path: /v1/customForm/checkCustomFormNameExists
    """
    try:
        
        final_member_id = get_final_tenant_id(request=request)
        name = request.query_params.get('customFormName')
        cf_id = int(request.query_params.get('customFormId', 0))
        
        exists = CustomForm.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id), cfFormName=name).exclude(cfId=cf_id).exists()
        if not exists:
            return api_response(200, "Form With Given Name Not Exists.")
        else:
            return api_response(500, "Form Name Already Exists.")
    except Exception as e:
        logger.error(f"checkCustomFormNameExists Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['POST'])
def reportExportFormToGroup(request: Request):
    """
    Batch export existing form submissions to a group.
    Path: /v1/customForm/reportExportFormToGroup
    """
    try:
        data = request.data
        cf_id = data.get('cfId')
        
        final_member_id  = get_final_tenant_id(request=request)
        
        stats_list = CustomFormStatistics.objects.filter(stCfId=cf_id)
        for st in stats_list:
            saveFormToGroup(cf_id, st.stId, data.get('cfGroupId'), get_client_id_by_tenant_id(final_member_id))

        return api_response(200, "Export Data Successfully", {"error": ""})
    except Exception as e:
        logger.error(f"reportExportFormToGroup Error: {e}")
        return api_response(400, "Invalid Data")

@api_view(['POST'])
def grabCustomFormPdfData(request: Request):
    """
    Initialize PDF generation for custom form reports.
    Path: /v1/customForm/grabCustomFormPdfData
    """
    try:
        data = request.data
        
        final_member_id  = get_final_tenant_id(request=request)
        
        CustomFormReportPdf.objects.create(
            custom_form_id=data.get('customFormId'),
            ans_ids=data.get('ansIds'),
            member_id=get_client_id_by_tenant_id(final_member_id),
            zip_url="Pending",
            is_started=0,
            is_processed=0
        )
        return api_response(200, "PDF Genereting process started", {"success": "Data Saved successfully"})
    except Exception as e:
        logger.error(f"grabCustomFormPdfData Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['GET'])
def getCustomFormLinkList(request):
    """
    Retrieve list of forms for quick linking.
    Path: /v1/customForm/getCustomFormLinkList
    """
    try:
        final_member_id = get_final_tenant_id(request=request)
        forms = CustomForm.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id), cfFormStatus=1).order_by('-cfId')
        
        res_list = []
        for cf in forms:
            res_list.append({
                "cfId": cf.cfId,
                "cfFormName": cf.cfFormName,
                "customFormUrl": f"{settings.SITE_URL}customform?v={DecryptString.set_enc_dec_user(str(cf.cfId), '', 'Y')}"
            })
        return api_response(200, "Fetch Custom Form Successfully.", {"customFormList": res_list})
    except Exception as e:
        logger.error(f"getCustomFormLinkList Error: {e}")
        return api_response(400, "Invalid data")

@api_view(['GET'])
def getCustomFormLinkListAuto(request: Request):
    return getCustomFormLinkList(request._request)

@api_view(['GET'])
def getCustomFormDataById(request, cfId):
    """
    Get custom form data by its ID.
    Path: /v1/customForm/getCustomFormDataById/{cfId}
    Matches Java: CustomFormServiceImpl.getCustomFormDataById
    """
    try:
        cf = CustomForm.objects.filter(cfId=cfId).first()
        res_body = dict()
        res_body["error"] = ""
        if cf:
            res_body["customForm"] = entity_to_dto_custom_form(cf)
            return api_response(200, "Fetch Custom Form Data Successfully.", res_body)
        else:
            res_body["error"] = "Data Not Found"
            return api_response(500, "Data Not Found", res_body)
    except Exception as e:
        logger.error(f"getCustomFormDataById Error : {e}")
        return api_response(500, "Error Fetching Data", {"error": str(e)})
