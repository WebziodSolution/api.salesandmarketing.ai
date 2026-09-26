import os
import re
import base64
import shutil
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from bs4 import BeautifulSoup
from common_app.models import MyPages, Language, CampaignTransaction, FreeTemplate, CatTemplate, TranslateTemplate, Groups, Userlist, CountrySetting, Clients
from auth_app.models import Tenants
from common_app.utils import api_response, get_final_tenant_id, cron_send_campaign_content_remove, nl2br, strip_slashes, \
    get_tenants, get_client_id_by_tenant_id, get_tenant_id_by_client_id
from common_app.decrypt_string import DecryptString
from common_app.services import CommonServices, MailRequestDTO

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
    urls = [m.group() for m in re.finditer(regex_url, text)]
    return urls[-1] if urls else ""

def return_link_parameter(url):
    if '?' in url:
        return url.split('?')[1]
    return ""

def replace_my_page_text_and_copy_image(all_temp_data, old_link, tenant_id, mp_id):
    site_url = getattr(settings, 'SITE_URL', '')
    file_directory_absolute = getattr(settings, 'ABSOLUTE_SITE_URL', '')
    
    link = remove_parameter(old_link)
    bits = link.split('/')
    img_name = bits[-1]
    
    new_link = f"{site_url}usercontent/{tenant_id}/images/mypage/{mp_id}/{img_name}"
    
    temp_parameter = return_link_parameter(old_link)
    if temp_parameter:
        all_temp_data = all_temp_data.replace(f"?{temp_parameter}", "")
    
    all_temp_data = all_temp_data.replace(link, new_link)
    
    old_path = os.path.join(file_directory_absolute, link.replace(site_url, "").replace("/", os.sep))
    new_path = os.path.join(file_directory_absolute, new_link.replace(site_url, "").replace("/", os.sep))
    
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if os.path.exists(old_path):
        shutil.copy2(old_path, new_path)
        
    return all_temp_data

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def listMyPageTags(request, mpStageId):
    tenant_id = get_final_tenant_id(request=request)
    try:
        mp_stage_id = int(mpStageId)
        if mp_stage_id == 2:
            # Published tags
            tags = MyPages.objects.filter(mpClientId=get_client_id_by_tenant_id(tenant_id), mpStage=mp_stage_id).values_list('mpTags', flat=True)
        elif mp_stage_id == 3:
            # All tags
            tags = MyPages.objects.filter(mpClientId=get_client_id_by_tenant_id(tenant_id)).values_list('mpTags', flat=True)
        else:
            # Draft tags
            tags = MyPages.objects.filter(mpClientId=get_client_id_by_tenant_id(tenant_id), mpStage=mp_stage_id, mpBuilditPublish='Y').values_list('mpTags', flat=True)
        
        # Process tags (comma separated)
        unique_tags = set()
        for tag_str in tags:
            if tag_str:
                for t in tag_str.split(','):
                    if t.strip():
                        unique_tags.add(t.strip().lower())
                        
        return api_response(200, "Tags Fetched Successfully.", {"tags": sorted(list(unique_tags))})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(500, "Exception While Fetching Tags", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def listMyPage(request, mpStageId):
    tenant_id = get_final_tenant_id(request=request)
    mp_stage_id = int(mpStageId)
    
    if mp_stage_id == 2:
        mypages = MyPages.objects.filter(mpClientId=get_client_id_by_tenant_id(tenant_id), mpStage=mp_stage_id).order_by('mpName')
    else:
        mypages = MyPages.objects.filter(mpClientId=get_client_id_by_tenant_id(tenant_id), mpStage=mp_stage_id, mpBuilditPublish='Y').order_by('mpName')
    
    data = []
    for mp in mypages:
        group_name = None
        if mp.mpGroupId and mp.mpGroupId > 0:
            try:
                group = Groups.objects.filter(grpId=mp.mpGroupId).first()
                if group:
                    group_name = group.grpGroupName
            except Exception:
                pass

        data.append({
            "mpId": mp.mpId,
            "mpName": mp.mpName,
            "mpTags": mp.mpTags,
            "mpType": mp.mpType,
            "mpStage": mp.mpStage,
            "groupId": mp.mpGroupId if mp.mpGroupId is not None else 0,
            "memberId": get_tenant_id_by_client_id(mp.mpClientId),
            "mpTemplateLanguage": mp.mpTemplateLanguage,
            "mpTemplateConvertLangList": mp.mpTemplateConvertLangList,
            "mpAllowConvertLang": mp.mpAllowConvertLang,
            "mpBuilditPublish": mp.mpBuilditPublish,
            "thumbData": None,
            "allTempData": None,
            "groupName": group_name,
            "bfMpdBfmId": None,
            "encMpId": DecryptString.set_enc_dec_user(str(mp.mpId), "", "Y"),
            "mpPublicUrl": mp.mpPublicUrl
        })
        
    return api_response(200, "My Page List Fetched Successfully.", {"mypage": data})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getMyPageById(request, mpId):
    mypage = get_object_or_404(MyPages, mpId=mpId)
    
    group_name = None
    if mypage.mpGroupId and mypage.mpGroupId > 0:
        try:
            group = Groups.objects.filter(grpId=mypage.mpGroupId).first()
            if group:
                group_name = group.grpGroupName
        except Exception:
            pass

    file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')
    all_temp_data = ""
    path = os.path.join(file_directory, str(get_tenant_id_by_client_id(mypage.mpClientId)), "images", "mypage", str(mpId), "index.html")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                # Java logic: replace newlines and spaces between tags
                all_temp_data = re.sub(r"[\r\n]+", "", content)
                all_temp_data = re.sub(r">\s+<", "><", all_temp_data)
        except Exception:
            pass

    data = {
        "mpId": mypage.mpId,
        "mpName": mypage.mpName,
        "mpTags": mypage.mpTags,
        "mpType": mypage.mpType,
        "mpStage": mypage.mpStage,
        "mpGroupId": mypage.mpGroupId if mypage.mpGroupId is not None else 0,
        "mpClientId": mypage.mpClientId,
        "mpTemplateLanguage": mypage.mpTemplateLanguage,
        "mpTemplateConvertLangList": mypage.mpTemplateConvertLangList,
        "mpAllowConvertLang": mypage.mpAllowConvertLang,
        "mpBuilditPublish": mypage.mpBuilditPublish,
        "thumbData": None,
        "allTempData": all_temp_data,
        "groupName": group_name,
        "bfMpdBfmId": None,
        "encMpId": DecryptString.set_enc_dec_user(str(mypage.mpId), "", "Y"),
        "mpPublicUrl": mypage.mpPublicUrl
    }
    
    return api_response(200, "Fetch My Page Data Successfully.", {"mypage": data, "error": ""})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def deleteMyPage(request, mpId):
    tenant_id = get_final_tenant_id(request=request)
    file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')
    
    try:
        MyPages.objects.filter(mpId=mpId, mpClientId=get_client_id_by_tenant_id(tenant_id)).delete()
        
        # Delete files
        mp_dir = os.path.join(file_directory, str(tenant_id), "images", "mypage", str(mpId))
        if os.path.exists(mp_dir):
            shutil.rmtree(mp_dir, ignore_errors=True)
            
        return api_response(200, "My Page Deleted Successfully.", "")
    except Exception as e:
        return api_response(500, "Exception While Deleting My Page", {"error": str(e)})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def getGroupLanguageList(request):
    tenant_id = get_final_tenant_id(request=request)
    data = request.data
    group_id = data.get('groupId', 0)
    all_temp_data = data.get('allTempData', '')

    # Match Java's character filter logic
    # [^\p{L}\p{M}\p{N}\p{P}\p{Z}\p{Cf}\p{Cs}\s]
    # Simple Python equivalent: strip HTML then clean common control chars
    soup = BeautifulSoup(all_temp_data, 'html.parser')
    text = soup.get_text()
    
    # Filtering non-printable / control chars (simplified)
    # The Java filter is quite broad. We'll strip common noise.
    text = re.sub(r'[\r\n\t]+', ' ', text).strip()
    
    if not text:
        lang_en = Language.objects.filter(lg_name='en').first()
        current_long = lang_en.lg_long_name if lang_en else "English"
        return api_response(200, "", {
            "msg": "notConvert",
            "currentLanguage": {"short": "en", "long": current_long},
            "languageList": None
        })

    # Java logic: detect language of cleaned text using Google Translate API
    detected_lang = "en"  # Default fallback
    google_key = getattr(settings, 'GOOGLE_TRANSLATE_KEY', None)
    
    if google_key and text:
        try:
            # Java equivalent: post to translate/v2/detect with text and key
            detect_url = "https://translation.googleapis.com/language/translate/v2/detect"
            # Limit text length for detection to avoid URL length issues or high cost
            detect_text = text[:1000]
            params = {
                "key": google_key,
                "q": detect_text
            }
            resp = requests.post(detect_url, params=params)
            if resp.status_code == 200:
                res_data = resp.json()
                # Java: response.getData().getDetections().get(0).get(0).getLanguage()
                detections = res_data.get('data', {}).get('detections', [])
                if detections and len(detections) > 0 and len(detections[0]) > 0:
                    detected_lang = detections[0][0].get('language', 'en')
        except Exception:
            # Fallback to English on detection failure
            detected_lang = "en"

    lang_obj = Language.objects.filter(lg_name=detected_lang).first()
    current_long = lang_obj.lg_long_name if lang_obj else "English"
    res_body = dict()
    res_body["currentLanguage"] = {"short": detected_lang, "long": current_long}

    # Query contacts for languages other than the detected one
    contacts = Userlist.objects.filter(
        memberId=get_client_id_by_tenant_id(tenant_id),
        status='Subscribed',
        badEmail__in=['N', 'B', 'D']
    ).filter(
        Q(optId=0) | Q(optId__isnull=True)
    )
    
    if group_id and int(group_id) > 0:
        contacts = contacts.filter(groupId=group_id)
        
    user_languages = contacts.exclude(
        usDefaultLanguage=detected_lang
    ).exclude(
        usDefaultLanguage__isnull=True
    ).exclude(
        usDefaultLanguage=''
    ).values_list('usDefaultLanguage', flat=True).distinct()

    if not user_languages:
        res_body["msg"] = "notConvert"
        res_body["languageList"] = None
    else:
        lang_list = []
        for ul in user_languages:
            l_obj = Language.objects.filter(lg_name=ul).first()
            if l_obj:
                lang_list.append({
                    "short": ul,
                    "long": l_obj.lg_long_name
                })
        res_body["languageList"] = lang_list

    return api_response(200, "", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getFreeTemplateTags(request):
    try:
        tags = FreeTemplate.objects.filter(ftStage=2).values_list('ftTags', flat=True)
        catTags = CatTemplate.objects.exclude(ctemId=5).order_by('ctemName').values_list('ctemName', flat=True)
        unique_tags = set()
        for tag_str in tags:
            if tag_str:
                for t in tag_str.split(','):
                    if t.strip():
                        unique_tags.add(t.strip().lower())
        for tag_str in catTags:
            if tag_str:
                for t in tag_str.split(','):
                    if t.strip():
                        unique_tags.add(t.strip().lower())
                        
        return api_response(200, "Free Template Tags Fetched Successfully.", {"tags": sorted(list(unique_tags))})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(500, "Internal Server Error", {"error": str(e)})

@transaction.atomic
def save_for_later_logic(tenant_id, data):
    mp_id = data.get('mpId')
    all_temp_data = data.get('allTempData', '')

    file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')

    try:
        # Clean special characters
        all_temp_data = all_temp_data.replace("\u200C", "").replace("\u200B", "")
        all_temp_data = all_temp_data.replace("&ZeroWidthSpace;", "")

        if mp_id and int(mp_id) > 0:
            mypage = get_object_or_404(MyPages, mpId=mp_id)
        else:
            mypage = MyPages()
            mypage.mpClientId = get_client_id_by_tenant_id(tenant_id)
            mypage.mpBuilditPublish = "Y"

        mypage.mpName = data.get('mpName')
        mypage.mpTags = data.get('mpTags')
        mypage.mpType = int(data.get('mpType', 1))
        mypage.mpStage = int(data.get('mpStage', 0))
        mypage.mpGroupId = data.get('groupId', 0)
        mypage.mpTemplateLanguage = data.get('mpTemplateLanguage', 'en')
        mypage.mpTemplateConvertLangList = data.get('mpTemplateConvertLangList', '')
        mypage.mpAllowConvertLang = data.get('mpAllowConvertLang', 'N')
        mypage.mpPublicUrl = data.get('mpPublicUrl', '')
        
        if mypage.mpType == 1:
            mypage.mpGroupId = 0

        mypage.save()
        mp_id = mypage.mpId

        # Create directories
        mp_dir = os.path.join(file_directory, str(tenant_id), "images", "mypage", str(mp_id))
        os.makedirs(mp_dir, exist_ok=True)

        # HTML Processing
        soup = BeautifulSoup(all_temp_data, 'html.parser')
        
        # MCD background
        div_mcd = soup.find(id="mcd")
        if div_mcd and div_mcd.has_attr('item-path'):
            old_link = div_mcd['item-path']
            if "mypage" not in old_link:
                all_temp_data = replace_my_page_text_and_copy_image(all_temp_data, old_link, tenant_id, mp_id)

        # templateBody background
        tpl_body = soup.find(id="templateBody")
        if tpl_body and tpl_body.has_attr('item-path'):
            old_link = tpl_body['item-path']
            if "mypage" not in old_link:
                all_temp_data = replace_my_page_text_and_copy_image(all_temp_data, old_link, tenant_id, mp_id)

        # mcnImage class
        images = soup.find_all(class_="mcnImage")
        for img in images:
            old_link = img.get('src')
            if old_link and "mypage" not in old_link:
                all_temp_data = replace_my_page_text_and_copy_image(all_temp_data, old_link, tenant_id, mp_id)

        # Minification and placeholders
        all_temp_data = re.sub(r"[\r\n]+", "", all_temp_data)
        all_temp_data = re.sub(r">\s+<", "><", all_temp_data)
        all_temp_data = all_temp_data.replace("{{memberId}}", str(tenant_id))
        all_temp_data = all_temp_data.replace("{{myPageId}}", str(mp_id))

        # Save index.html
        index_path = os.path.join(mp_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(all_temp_data)

        # ThumbData
        thumb_data = data.get("thumbData", "")
        if thumb_data:
            thumb_data = thumb_data.replace("data:image/png;base64,", "").replace(" ", "")
            try:
                decoded_bytes = base64.b64decode(thumb_data)
                thumb_path = os.path.join(mp_dir, "thumb.png")
                with open(thumb_path, "wb") as f:
                    f.write(decoded_bytes)
            except Exception as e:
                print(f"Error saving thumb: {e}")

        if mypage.mpName in ["Opt In", "Opt Out", "Rejoin Group"]:
            mypage.mpDetails = all_temp_data
            mypage.save()

        if mypage.mpStage == 2:
            TranslateTemplate.objects.filter(ttMyPageId=mp_id).delete()
            TranslateTemplate.objects.create(
                ttMyPageId=mp_id,
                ttClientId=get_client_id_by_tenant_id(tenant_id),
                ttCampDetail=all_temp_data,
                ttCampDetailSend=all_temp_data,
                ttMasterCopy="Y",
                ttTemplateLanguage=mypage.mpTemplateLanguage,
                ttPublishDate=timezone.now()
            )

        return api_response(200, "Successfully Saved To My Drafted Pages", {"mpId": mp_id})

    except Exception as e:
        print(f"save_for_later_logic Error: {e}")
        return api_response(400, "Invalid data", {"error": str(e)})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def saveForLater(request):
    tenant_id = get_final_tenant_id(request=request)
    return save_for_later_logic(tenant_id, request.data)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def publish(request):
    tenant_id = get_final_tenant_id(request=request)
    # Ensure mpStage is 2 for publish actions
    data = request.data.copy()
    data['mpStage'] = 2
    
    response = save_for_later_logic(tenant_id, data)
    
    if response.status_code == 200:
        mp_id = response.data.get('result', {}).get('mpId')
        if data.get('mpAllowConvertLang') == 'Y':
            convert_lang_list = data.get('mpTemplateConvertLangList', '').split(',')
            # Filter out empty strings
            convert_lang_list = [l.strip() for l in convert_lang_list if l.strip()]
            
            if convert_lang_list:
                # Use BeautifulSoup to find and mark content for translation
                # Re-parse the saved HTML content (ttCampDetail from the master copy)
                master_copy = TranslateTemplate.objects.get(ttMyPageId=mp_id, ttMasterCopy="Y")
                all_temp_data = master_copy.ttCampDetail
                
                soup = BeautifulSoup(all_temp_data, 'html.parser')
                
                classes_to_translate = ["textTdBlock", "genericlinkTdBlock", "surveyTdBlock", "assessmentTdBlock", "customformTdBlock"]
                elements_to_translate = []
                for cls in classes_to_translate:
                    elements_to_translate.extend(soup.find_all(class_=cls))
                
                if elements_to_translate:
                    convert_send_list = []
                    for i, element in enumerate(elements_to_translate):
                        # Java: convertSendStr += e.html() + " <!--~--> ";
                        # In bs4, element.decode_contents() gets the inner HTML
                        content = element.decode_contents()
                        convert_send_list.append(content)
                        # Replace content with marker
                        element.string = f"~~~{i}~~~"
                    
                    original_html_with_placeholders = str(soup)
                    convert_send_str = " <!--~--> ".join(convert_send_list)
                    
                    # Fetch translation charge
                    tenant = Tenants.objects.get(ten_id=tenant_id)
                    try:
                        # Assuming country string in Tenant is the ID
                        country_id = int(tenant.ten_country) if tenant.ten_country else 100
                    except:
                        country_id = 100
                    
                    setting = CountrySetting.objects.filter(cnty_id=country_id).first()
                    translate_charge = setting.cnty_translate_char_charge if setting else 0.001
                    
                    google_key = getattr(settings, 'GOOGLE_TRANSLATE_KEY', None)
                    master_lang = data.get('mpTemplateLanguage', 'en')
                    mp_name = data.get('mpName', '')
                    sub_tenant_id = data.get('subMemberId', 0)
                    
                    for lang_code in convert_lang_list:
                        target_lang_full = "Unknown"
                        l_obj = Language.objects.filter(lg_name=lang_code).first()
                        if l_obj:
                            target_lang_full = l_obj.lg_long_name
                        
                        tran_campaign_name = f"{mp_name}<br>Language translation:{master_lang} To {target_lang_full}"
                        
                        # Calculate amount (character count * charge)
                        total_amount = len(convert_send_str) * translate_charge
                        # Round to 3 decimal places (HALF_UP equivalent)
                        total_amount = float(Decimal(str(total_amount)).quantize(Decimal('0.000'), rounding=ROUND_HALF_UP))
                        
                        # Save Campaign Transaction (Language Translation)
                        CampaignTransaction.objects.create(
                            tran_campaign_id=mp_id,
                            tran_campaign_name=tran_campaign_name,
                            tran_total_member=1,
                            tran_type="language translation",
                            tran_invoiced_status="uninvoiced",
                            ct_client_id=get_client_id_by_tenant_id(tenant_id),
                            tran_bill_type="0",
                            tran_total_amount=total_amount,
                            tran_member_rate=total_amount,
                            tran_count_total_sms=0,
                            sub_member_id=sub_tenant_id
                        )
                        
                        translated_html = all_temp_data # Default fallback
                        api_error = ""
                        
                        if google_key:
                            try:
                                # Java: translateService.getTranslation(convertSendStr, languageList[num])
                                translate_url = "https://translation.googleapis.com/language/translate/v2"
                                payload = {
                                    "q": convert_send_list, # Google API accepts list of strings
                                    "target": lang_code,
                                    "format": "html"
                                }
                                params = {"key": google_key}
                                translate_resp = requests.post(translate_url, params=params, json=payload)
                                
                                if translate_resp.status_code == 200:
                                    res_json = translate_resp.json()
                                    translations = res_json.get('data', {}).get('translations', [])
                                    
                                    # Replace markers in the placeholder HTML
                                    temp_html = original_html_with_placeholders
                                    for i, trans_obj in enumerate(translations):
                                        translated_text = trans_obj.get('translatedText', '')
                                        temp_html = temp_html.replace(f"~~~{i}~~~", translated_text)
                                    translated_html = temp_html
                                else:
                                    api_error = translate_resp.text
                            except Exception as ex:
                                api_error = str(ex)
                                
                        # Save translated version to TranslateTemplate
                        TranslateTemplate.objects.create(
                            ttMyPageId=mp_id,
                            ttClientId=get_client_id_by_tenant_id(tenant_id),
                            ttCampDetail=translated_html,
                            ttCampDetailSend=translated_html,
                            ttMasterCopy="N",
                            ttTemplateLanguage=lang_code,
                            ttApiError=api_error,
                            ttPublishDate=timezone.now()
                        )
    response.data["message"] = "Successfully Published"
    return response

@api_view(['POST'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def autoSave(request):
    tenant_id = get_final_tenant_id(request=request)
    return save_for_later_logic(tenant_id, request.data)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
@transaction.atomic
def getMyPageClone(request, subTenantId, mpId):
    tenant_id = get_final_tenant_id(request=request)
    file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')

    try:
        old_mp = get_object_or_404(MyPages, mpId=mpId, mpClientId=get_client_id_by_tenant_id(tenant_id))
        new_mp = MyPages.objects.create(
            mpName=old_mp.mpName + " copy",
            mpTags=old_mp.mpTags,
            mpType=old_mp.mpType,
            mpStage=old_mp.mpStage,
            mpGroupId=old_mp.mpGroupId,
            mpClientId=get_client_id_by_tenant_id(tenant_id),
            mpTemplateLanguage=old_mp.mpTemplateLanguage,
            mpTemplateConvertLangList=old_mp.mpTemplateConvertLangList,
            mpAllowConvertLang=old_mp.mpAllowConvertLang,
            mpBuilditPublish=old_mp.mpBuilditPublish,
            mpPublicUrl=old_mp.mpPublicUrl,
            mpDetails=old_mp.mpDetails
        )
        new_mp_id = new_mp.mpId

        # Copy directory
        old_dir = os.path.join(file_directory, str(tenant_id), "images", "mypage", str(mpId))
        new_dir = os.path.join(file_directory, str(tenant_id), "images", "mypage", str(new_mp_id))
        
        if os.path.exists(old_dir):
            shutil.copytree(old_dir, new_dir, dirs_exist_ok=True)

        # Update index.html links
        index_path = os.path.join(new_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                all_temp_data = f.read()
            
            soup = BeautifulSoup(all_temp_data, 'html.parser')
            
            # Update links and download easdrive images
            # MCD
            div_mcd = soup.find(id="mcd")
            if div_mcd and div_mcd.has_attr('item-path'):
                old_link = div_mcd['item-path']
                all_temp_data = replace_my_page_text_and_copy_image_copy(all_temp_data, old_link, tenant_id, new_mp_id, new_dir)

            # templateBody
            tpl_body = soup.find(id="templateBody")
            if tpl_body and tpl_body.has_attr('item-path'):
                old_link = tpl_body['item-path']
                all_temp_data = replace_my_page_text_and_copy_image_copy(all_temp_data, old_link, tenant_id, new_mp_id, new_dir)

            # mcnImage
            images = soup.find_all(class_="mcnImage")
            for img in images:
                old_link = img.get('src')
                if old_link:
                    all_temp_data = replace_my_page_text_and_copy_image_copy(all_temp_data, old_link, tenant_id, new_mp_id, new_dir)

            with open(index_path, "w", encoding="utf-8") as f:
                f.write(all_temp_data)

        # Prepare full page data for response
        all_temp_data_for_dto = ""
        index_path = os.path.join(new_dir, "index.html")
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    all_temp_data_for_dto = re.sub(r"[\r\n]+", "", content)
                    all_temp_data_for_dto = re.sub(r">\s+<", "><", all_temp_data_for_dto)
            except Exception:
                pass

        group_name = None
        if new_mp.mpGroupId and new_mp.mpGroupId > 0:
            try:
                group = Groups.objects.filter(grpId=new_mp.mpGroupId).first()
                if group:
                    group_name = group.grpGroupName
            except Exception:
                pass

        data = {
            "mpId": new_mp.mpId,
            "mpName": new_mp.mpName,
            "mpTags": new_mp.mpTags,
            "mpType": new_mp.mpType,
            "mpStage": new_mp.mpStage,
            "mpGroupId": new_mp.mpGroupId if new_mp.mpGroupId is not None else 0,
            "mpClientId": new_mp.mpClientId,
            "mpTemplateLanguage": new_mp.mpTemplateLanguage,
            "mpTemplateConvertLangList": new_mp.mpTemplateConvertLangList,
            "mpAllowConvertLang": new_mp.mpAllowConvertLang,
            "mpBuilditPublish": new_mp.mpBuilditPublish,
            "thumbData": None,
            "allTempData": all_temp_data_for_dto,
            "groupName": group_name,
            "bfMpdBfmId": None,
            "encMpId": DecryptString.set_enc_dec_user(str(new_mp.mpId), "", "Y"),
            "mpPublicUrl": new_mp.mpPublicUrl
        }

        return api_response(200, "Fetch My Page Data Successfully.", {"mypage": data, "error": ""})

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"getMyPageClone Error: {e}")
        return api_response(500, "My Page Not Found", {"error": "Invalid Data", "mpId": 0})

def replace_my_page_text_and_copy_image_copy(all_temp_data, old_link, tenant_id, mp_id, new_dir):
    site_url = getattr(settings, 'SITE_URL', '')
    link = remove_parameter(old_link)
    bits = link.split('/')
    img_name = bits[-1]
    
    new_link = f"{site_url}usercontent/{tenant_id}/images/mypage/{mp_id}/{img_name}"
    
    temp_parameter = return_link_parameter(old_link)
    if temp_parameter:
        all_temp_data = all_temp_data.replace(f"?{temp_parameter}", "")
    
    all_temp_data = all_temp_data.replace(link, new_link)
    
    if "easdrive" in old_link:
        try:
            resp = requests.get(old_link)
            if resp.status_code == 200:
                with open(os.path.join(new_dir, img_name), "wb") as f:
                    f.write(resp.content)
        except Exception as e:
            print(f"Error downloading easdrive image: {e}")
            
    return all_temp_data

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getPreview(request):
    # Java: @RequestParam String id, @RequestParam(required = false) String lang
    encrypted_id = request.query_params.get('id')
    filter_lang = request.query_params.get('lang', '')
    
    if not encrypted_id:
        return api_response(400, "Missing ID", {})
        
    try:
        decrypted_id = DecryptString.set_enc_dec_user(encrypted_id, "display", "Y")
        mp_id = int(decrypted_id)
    except Exception as e:
        print(f"Decrypt/Parse ID Error: {e}")
        return api_response(400, "Invalid ID", {"error": f"ID {encrypted_id} is invalid."})

    try:
        mypage = get_object_or_404(MyPages, mpId=mp_id)
        tenant_id = get_tenant_id_by_client_id(mypage.mpClientId)
        
        all_lan = mypage.mpTemplateLanguage or ""
        master_lang = all_lan
        
        if mypage.mpTemplateConvertLangList and len(mypage.mpTemplateConvertLangList) > 0:
            if all_lan:
                all_lan += "," + mypage.mpTemplateConvertLangList
            else:
                all_lan = mypage.mpTemplateConvertLangList
        
        # If there are translations or a language filter is applied
        if all_lan != master_lang:
            if not filter_lang:
                camp_detail_obj = TranslateTemplate.objects.filter(ttMyPageId=mp_id, ttMasterCopy="Y").first()
            else:
                camp_detail_obj = TranslateTemplate.objects.filter(ttMyPageId=mp_id, ttTemplateLanguage=filter_lang).first()
            
            if camp_detail_obj:
                tt_camp_detail = camp_detail_obj.ttCampDetail
                tt_id = camp_detail_obj.ttId
            else:
                tt_camp_detail = "404 : Template Not Found"
                tt_id = None
                
            response_data = {
                "ttId": tt_id,
                "mpTemplateLanguage": mypage.mpTemplateLanguage,
                "mpTemplateConvertLangList": mypage.mpTemplateConvertLangList,
                "ttCampDetail": tt_camp_detail
            }
            return api_response(200, "Preview Successfully.", {"response": response_data})
        else:
            # Fetch from file system like Java
            file_directory = getattr(settings, 'FILE_UPLOAD_DIR', '')
            index_path = os.path.join(file_directory, str(tenant_id), "images", "mypage", str(mp_id), "index.html")
            
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                content = "404 : Template Not Found"
            
            response_data = {
                "ttId": None,
                "mpTemplateLanguage": mypage.mpTemplateLanguage,
                "mpTemplateConvertLangList": mypage.mpTemplateConvertLangList,
                "ttCampDetail": content
            }
            return api_response(200, "Preview Successfully.", {"response": response_data})
            
    except Exception as e:
        print(f"getPreview Error: {e}")
        return api_response(500, "Exception While Getting Preview", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getPreviewFreeTemplate(request, ftFolderName):
    # Java: getPreviewFreeTemplate(String ftFolderName)
    try:
        free_template_dir = getattr(settings, 'FREE_TEMPLATE_DIR', '')
        read_path = os.path.join(free_template_dir, ftFolderName, "index.html")
        
        if os.path.exists(read_path):
            with open(read_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Java: doc.html().replaceAll("[\\r\\n]+", "").replaceAll(">\\s+<", "><")
                content = re.sub(r'[\r\n]+', '', content)
                content = re.sub(r'>\s+<', '><', content)
            return api_response(200, "Preview Successfully.", {"freeTemplate": content})
        else:
            return api_response(400, "Invalid Data", {"error": "Template Not Found"})
            
    except Exception as e:
        print(f"getPreviewFreeTemplate Error: {e}")
        return api_response(500, "Internal Server Error", {"error": str(e)})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def sendMyPageEmailPreview(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        client = Clients.objects.get(cliTenantId=tenant_id)
        if tenant is None:
            return api_response(404, "Tenant Not Found", {"error": "Tenant not found"})
        email = request.data.get('email')
        all_temp_data = request.data.get('allTempData', '')
        mp_type = request.data.get('mpType', 0)
        
        # In Java, contactSelected is a list of emails
        contact_selected = request.data.get('contactSelected', [])
        if not contact_selected and email:
            contact_selected = [email]

        subject = "Preview Template"
        first_name = tenant.ten_first_name if tenant.ten_first_name else ""
        last_name = tenant.ten_last_name if tenant.ten_last_name else ""
        from_name = f"{first_name} {last_name}".strip()

        all_data = all_temp_data
        all_data = cron_send_campaign_content_remove(all_data)
        all_data = re.sub(r"[\r\n]+", "", all_data)
        all_data = re.sub(r">\s+<", "><", all_data)
        all_data = nl2br(all_data)

        tenant_data = CommonServices.find_tenant_record(tenant_id)
        if tenant_data:
            for key, value in tenant_data.items():
                if value is not None:
                    # Java uses ##key##
                    all_data = all_data.replace(f"##{key}##", str(value))

        country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
        site_url = getattr(settings, 'SITE_URL', '')
        site_url_backend = getattr(settings, 'SITE_URL_BACKEND', site_url)
        site_url_www = getattr(settings, 'SITE_URL_WWW', site_url)
        site_url_address = getattr(settings, 'SITE_URL_ADDRESS', '')
        
        cnty_white_listing = getattr(country_setting, 'cnty_white_listing', 'N') if country_setting else 'N'
        cli_logo = getattr(client, 'cliLogo', None)
        cli_customer_footer = getattr(client, 'cliCustomerFooter', None)

        if mp_type == 3:
            all_data += (f"<div style='color:#4285F4; font-size:12px; padding: 1px 0px; display: flex; margin: 0px auto; width: 600px;'>"
                        f"<div style='margin: 10px; width: calc(100% - 20px); max-width: 600px;'>"
                        f"<a href='{site_url}unsubscribe?ui=&ci=&e=&m=' style='color:#4285F4; padding-left:5px'>Opt Out</a>"
                        f"<img src='{site_url_backend}emailCampaign/openEmail?fg=1&ui=&ci=' />"
                        f"</div>"
                        f"</div>")
        else:
            all_data += "<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:'Myriad Pro',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
            all_data += "<div style='padding-top:2px'>"

            if cnty_white_listing.upper() == 'Y' and cli_logo:
                all_data += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
            else:
                logo_url = f"{site_url}img/logo.png"
                all_data += f'<a style="color:#00599A;margin: 0px auto;" href="{site_url_www}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{logo_url}" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'

            all_data += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"
            if cnty_white_listing.upper() == 'Y' and cli_customer_footer:
                all_data += nl2br(cli_customer_footer)
            else:
                all_data += site_url_address

            all_data += "</div></div>"
            all_data += "</div></div>"
            all_data += "<div align='center' style='color:#4285F4;font-size:12px;font-family:Arial, Helvetica Neue, Helvetica, sans-serif;'><a href='#' style='color:#4285F4'>View In Browser</a> | <a href='#' style='color:#4285F4'>Unsubscribe</a> | <a href='#' style='color:#4285F4'>Change Language</a> | <a href='#' style='color:#4285F4'>Update Contact Information</a></div>"

        subject = strip_slashes(subject)
        html_data = strip_slashes(all_data)

        mail_request = MailRequestDTO()
        mail_request.template_name = "preview-email-template.ftl"
        mail_request.subject = subject
        
        # In our Python CommonServices.sendEmail, sender is taken from settings. 
        # But we can pass from_name in model if the template uses it.
        model = {
            "data": html_data,
            "siteName": getattr(settings, 'SITE_NAME', ''),
            "siteUrlWWW": site_url_www,
            "siteUrlAddress": site_url_address,
            "companyName": getattr(settings, 'COMPANY_NAME', ''),
            "fromName": from_name
        }

        sent_count = 0
        for target_email in contact_selected:
            mail_request.to = target_email
            res = CommonServices.sendEmail(mail_request, model)
            if res.status:
                sent_count += 1
        
        if sent_count > 0:
            return api_response(200, "Preview Email Has Been Sent To All Email(s)", {"msg": "Preview Email Has Been Sent To All Email(s)", "error": ""})
        else:
            return api_response(400, "Failed to send email", {"error": "Failed to send preview emails"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return api_response(500, "Internal Server Error", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getFreeTemplateList(request):
    templates = FreeTemplate.objects.filter(ftStage=2).order_by('ftName')
    data = []
    for ft in templates:
        data.append({
            "ftId": ft.ftId,
            "ftName": ft.ftName,
            "ftFolderName": ft.ftFolderName.replace("/",""),
            "ftStage": ft.ftStage,
            "ftCatId": ft.ftCatId,
            "ftTags": ft.ftTags
        })
    return api_response(200, "Free Template Fetched Successfully.", {"freeTemplate": data})
