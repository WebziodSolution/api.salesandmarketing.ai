from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id, get_tenant_id_by_client_id
from common_app.models import (Surveys, SurveysPages, SurveysQuestions, SurveysOptions, SurveysOptionsColumns, SurveysAnswers, SurveysStatistics, SurveysTemplate, CampaignTransaction, Country)
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime
from django.conf import settings
import logging
import os
import shutil
import json
import uuid
import traceback
from common_app.decrypt_string import DecryptString
from common_app.services import CommonServices
from user_agents import parse

logger = logging.getLogger(__name__)

def display_date(dt):
    if not dt:
        return None

    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            return None

    return dt.strftime('%m/%d/%Y')

def display_datetime(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            return None

    return dt.strftime('%m/%d/%Y %H:%M:%S')

def technology_detection(ua_string):
    """
    Modular User-Agent parsing to match Java backend data structure.
    """
    try:
        ua = parse(ua_string)
        return f"{ua.os.family} {ua.browser.family}"
    except:
        return "Unknown"

@api_view(['GET'])
def getSurveyAllList(request):
    resBody = dict()
    try:
        final_member_id = get_final_tenant_id(request=request)

        # Match Java: surveysRepository.findSurveyAllList(memberId, 1)
        surveys = Surveys.objects.filter(memberId=final_member_id, sryStatus=1)
        survey_list = []
        site_url = getattr(settings, 'SITE_URL', '')
        for sry in surveys:
            encrypted_id = DecryptString.set_enc_dec_user(str(sry.sryId), "", "Y")
            survey_list.append({
                "sryUrl": f"{site_url}survey?v={encrypted_id}",
                "sryName": sry.sryName
            })
        resBody["surveyList"] = survey_list
        return api_response(200, "Fetch Survey Successfully.", resBody)
    except Exception as e:
        logger.error(f"GetSurveyAllList Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['GET'])
def getSurveyAllListAuto(request: Request):
    return getSurveyAllList(request._request if hasattr(request, '_request') else request)

@api_view(['DELETE'])
def deleteSurvey(request: Request):
    resBody = dict()
    try:
        final_member_id = get_final_tenant_id(request=request)

        sry_ids = request.data.get('sryId', [])
        file_upload_dir = getattr(settings, 'FILE_UPLOAD_DIR', '')

        for sry_id in sry_ids:
            try:
                survey = Surveys.objects.get(sryId=sry_id)
                survey.delete()
                # Match Java: Delete folder matching MemberId/SryId
                folder_path = os.path.join(file_upload_dir, "survey", str(final_member_id), str(sry_id))
                if os.path.exists(folder_path):
                    shutil.rmtree(folder_path)
            except Surveys.DoesNotExist:
                continue
                
        return api_response(200, "Survey Deleted Successfully.", resBody)
    except Exception as e:
        logger.error(f"DeleteSurvey Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['GET'])
def getSurveyListPages(request: Request):
    resBody = dict()
    try:
        final_member_id = get_final_tenant_id(request=request)

        search_key = request.GET.get('searchKey')
        page_size = int(request.GET.get('size', 10))
        page_number = int(request.GET.get('page', 0)) + 1

        query = Q(memberId=get_client_id_by_tenant_id(final_member_id))
        if search_key:
            query &= Q(sryName__icontains=search_key)

        surveys_qs = Surveys.objects.filter(query).order_by('-sryId')
        paginator = Paginator(surveys_qs, page_size)
        page_obj = paginator.get_page(page_number)

        site_url = getattr(settings, 'SITE_URL', '')
        survey_list = []
        for sry in page_obj:
            try:
                trans = CampaignTransaction.objects.filter(tran_campaign_id=sry.sryId, tran_type='survey').first()
                total_responses = trans.tran_total_member if trans else 0
            except:
                total_responses = 0
            
            encrypted_id = DecryptString.set_enc_dec_user(str(sry.sryId), "", "Y")
            survey_list.append({
                "sryId": sry.sryId,
                "sryName": sry.sryName,
                "sryStatus": sry.sryStatus,
                "sryStTotalQuestions": sry.sryStTotalQuestions,
                "sryUrl": f"{site_url}survey?v={encrypted_id}",
                "id": encrypted_id,
                "sryCreatedDate": display_date(sry.sryCreatedDate),
                "totalResponses": total_responses
            })

        resBody["getTotalPages"] = paginator.num_pages
        resBody["getNumber"] = page_number - 1
        resBody["getSize"] = page_size
        resBody["surveyList"] = survey_list
        resBody["totalSurvey"] = Surveys.objects.filter(memberId=get_client_id_by_tenant_id(final_member_id)).count()

        return api_response(200, "Fetch Survey Successfully.", resBody)
    except Exception as e:
        logger.error(f"GetSurveyListPages Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['GET'])
def getSurveyById(request, sryId):
    resBody = dict()
    try:
        survey = Surveys.objects.get(sryId=sryId)
        
        # Match Java: If status > 0, nullify sryData and category list
        sry_data = survey.sryData
        sry_st_category_page_list = survey.sryStCategoryPageList
        if survey.sryStatus > 0:
            sry_data = None
            sry_st_category_page_list = None
            
        resBody["survey"] = {
            "sryId": survey.sryId,
            "sryName": survey.sryName,
            "sryDescription": survey.sryDescription,
            "sryData": sry_data,
            "sryStCategoryPageList": sry_st_category_page_list,
            "sryCountryList": survey.sryCountryList,
            "sryStatus": survey.sryStatus,
            "sryStId": survey.sryStId,
            "sryStTotalQuestions": survey.sryStTotalQuestions,
            "memberId": survey.memberId,
            "sryCreatedDate": display_date(survey.sryCreatedDate),
            "sryUpdateDate": display_date(survey.sryUpdateDate)
        }
        return api_response(200, "Fetch Survey Successfully.", resBody)
    except Surveys.DoesNotExist:
        return api_response(404, "Data Not Found", resBody)
    except Exception as e:
        logger.error(f"GetSurveyById Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['POST'])
def closeSurvey(request: Request):
    resBody = {}
    try:
        sry_ids = request.data.get('sryId', [])
        Surveys.objects.filter(sryId__in=sry_ids).update(sryStatus=2)
        return api_response(200, "Survey Close Successfully.", resBody)
    except Exception as e:
        logger.error(f"CloseSurvey Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['POST'])
def saveSurveyData(request: Request):
    resBody = {"error": "", "location": "", "surveyLinkUrl": ""}
    try:
        data = request.data
        sry_id = data.get('sryId', 0)
        sry_name = data.get('sryName', '')
        sry_description = data.get('sryDescription', '')
        sry_status = data.get('sryStatus', 0)
        sry_data = data.get('sryData', '')
        sry_st_category_page_list = data.get('sryStCategoryPageList', '')
        sry_country_list = data.get('sryCountryList', '')
        sry_st_total_questions = data.get('sryStTotalQuestions', 0)
        sry_st_id = data.get('sryStId', 0)

        final_member_id = get_final_tenant_id(request=request)

        # Match Java: Check if survey name exists
        if Surveys.objects.filter(memberId=final_member_id, sryName__iexact=sry_name).exclude(sryId=sry_id).exists():
            resBody["error"] = "Name Already Exists"
            return api_response(200, "Name Already Exists", resBody)

        # Match Java: If sryStId > 0, fetch template data
        if sry_st_id > 0:
            try:
                template = SurveysTemplate.objects.get(st_id=sry_st_id)
                sry_data = template.st_data
                sry_st_category_page_list = template.st_category_page_list
                sry_st_total_questions = template.st_total_questions
            except SurveysTemplate.DoesNotExist:
                pass

        if sry_id == 0:
            survey = Surveys()
            survey.memberId = get_client_id_by_tenant_id(final_member_id)
            survey.sryCreatedDate = timezone.now().date()
            survey.save()
            sry_id = survey.sryId
        else:
            try:
                survey = Surveys.objects.get(sryId=sry_id)
                sry_id = survey.sryId
            except Surveys.DoesNotExist:
                return api_response(404, "Survey Not Found", resBody)

        survey.sryName = sry_name
        survey.sryDescription = sry_description
        survey.sryStatus = sry_status
        survey.sryStId = sry_st_id
        survey.sryCountryList = sry_country_list
        survey.sryUpdateDate = timezone.now().date()

        file_upload_dir = getattr(settings, 'FILE_UPLOAD_DIR', '')
        SITEURL = getattr(settings, 'SITE_URL', '')
        # Handle sryData and image paths
        if sry_data:
            # Replace "surveytemplate" and "temp" with "survey" to match Java logic
            # sry_data = sry_data.replace("surveytemplate", "survey").replace("/temp/", "/survey/")
            oldPath = SITEURL +  "usercontent/" + str(final_member_id) + "/images/surveytemplate/" + str(sry_st_id)
            newPath = SITEURL + "usercontent/" + str(final_member_id) + "/images/survey/" + str(sry_id)
            sry_data = sry_data.replace(oldPath,newPath)
            # Physical folder moving/copying logic
            if sry_st_id > 0:
                src_dir = os.path.join(file_upload_dir,str(final_member_id), "images", "surveytemplate", str(sry_st_id))
                dest_dir = os.path.join(file_upload_dir,str(final_member_id), "images", "survey", str(sry_id))
                print("--- src_dir ----",src_dir)
                print("--- dest_dir ----",dest_dir)

                if os.path.exists(src_dir):
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir, exist_ok=True)
                    for item in os.listdir(src_dir):
                        s = os.path.join(src_dir, item)
                        d = os.path.join(dest_dir, item)
                        if os.path.isdir(s):
                            if os.path.exists(d): shutil.rmtree(d)
                            shutil.copytree(s, d)
                        else:
                            shutil.copy2(s, d)

            survey.sryData = sry_data
            survey.sryStCategoryPageList = sry_st_category_page_list
            survey.sryStTotalQuestions = sry_st_total_questions

        survey.save()
        sry_id = survey.sryId

        # Publish logic (sryStatus == 1)
        if sry_status == 1:
            # Recursive Save to Nested Tables
            if sry_data:
                try:
                    sry_json = json.loads(sry_data)
                    pages = sry_json.get('surveysPages', [])
                    for pg_data in pages:
                        spg = SurveysPages(
                            spgSryId=sry_id,
                            spgNumber=pg_data.get('spgNumber', 0),
                            spgType=pg_data.get('spgType', '')
                        )
                        spg.save()
                        pg_data['spgId'] = spg.spgId
                        
                        questions = pg_data.get('surveysQuestions', [])
                        for q_data in questions:
                            sque = SurveysQuestions(
                                squeSpgId=spg.spgId,
                                squeType=q_data.get('squeType', ''),
                                squeQuestion=q_data.get('squeQuestion', ''),
                                squeDisplayOrder=q_data.get('squeDisplayOrder', 0),
                                squeCatId=q_data.get('squeCatId', 0)
                            )
                            sque.save()
                            q_data['squeId'] = sque.squeId
                            
                            options = q_data.get('surveysOptions', [])
                            if q_data.get('squeType') == 'matrix':
                                for opt_data in options:
                                    sopt = SurveysOptions(
                                        soptSqueId=sque.squeId,
                                        soptValue=opt_data.get('soptValue', ''),
                                        soptDisplayOrder=opt_data.get('soptDisplayOrder', 0),
                                        soptHasComments=opt_data.get('soptHasComments', 0),
                                        soptDescription=opt_data.get('soptDescription', '')
                                    )
                                    sopt.save()
                                    opt_data['soptId'] = sopt.soptId
                                columns = q_data.get('surveysOptionsColumns', [])
                                for col_data in columns:
                                    scol = SurveysOptionsColumns(
                                        soptSqueId=sque.squeId,
                                        soptValue=col_data.get('soptValue', ''),
                                        soptDisplayOrder=col_data.get('soptDisplayOrder', 0)
                                    )
                                    scol.save()
                                    col_data['soptId'] = scol.soptId
                            else:
                                for opt_data in options:
                                    sopt = SurveysOptions(
                                        soptSqueId=sque.squeId,
                                        soptValue=opt_data.get('soptValue', ''),
                                        soptDisplayOrder=opt_data.get('soptDisplayOrder', 0),
                                        soptHasComments=opt_data.get('soptHasComments', 0),
                                        soptDescription=opt_data.get('soptDescription', '')
                                    )
                                    sopt.save()
                                    opt_data['soptId'] = sopt.soptId
                    
                    survey.sryData = json.dumps(sry_json)
                    survey.save()

                    # Folder Rename Logic: temp -> member_id/sry_id
                    src_temp = os.path.join(file_upload_dir, "survey", "temp", str(final_member_id))
                    dest_final = os.path.join(file_upload_dir, "survey", str(final_member_id), str(sry_id))
                    if os.path.exists(src_temp):
                        if not os.path.exists(os.path.dirname(dest_final)):
                            os.makedirs(os.path.dirname(dest_final), exist_ok=True)
                        if os.path.exists(dest_final): shutil.rmtree(dest_final)
                        shutil.move(src_temp, dest_final)
                        
                        survey.sryData = survey.sryData.replace(f"survey/temp/{final_member_id}", f"survey/{final_member_id}/{sry_id}")
                        survey.save()

                except Exception as ex:
                    logger.error(f"Nested Save Error: {ex}")

            # Transaction and Invoicing
            country_setting = CommonServices.country_setting_by_tenant_id(final_member_id)
            if country_setting:
                tran_member_rate = country_setting.cnty_survey_per_price
                CommonServices.saveCampaignTransaction(
                    sry_id, sry_name, 0, "survey", None, "uninvoiced", None,
                    get_client_id_by_tenant_id(final_member_id), "0", 0.0, tran_member_rate, 0, None, None,
                    0
                )

            site_url = getattr(settings, 'SITE_URL', '')
            encrypted_id = DecryptString.set_enc_dec_user(str(sry_id), "", "Y")
            resBody["surveyLinkUrl"] = f"{site_url}survey?v={encrypted_id}"

        resBody["location"] = str(sry_id)
        resBody["error"] = ""
        return api_response(200, "Survey Saved Successfully.", resBody)
    except Exception as e:
        logger.error(f"SaveSurveyData Error : {e}")
        return api_response(500, "Error", {"error": "Invalid Data"})

@api_view(['GET'])
def getSurveyCopy(request, subMemberId, sryId):
    resBody = dict()
    resBody["error"] = ""
    try:
        final_member_id = get_final_tenant_id(request=request)

        # Match Java logic: getSurveyCopy native query
        try:
            old_survey = Surveys.objects.get(sryId=sryId, memberId=final_member_id)
        except Surveys.DoesNotExist:
            return api_response(404, "Survey Not Found", resBody)

        new_survey = Surveys.objects.create(
            sryName=f"{old_survey.sryName} copy",
            sryDescription=old_survey.sryDescription,
            sryData=old_survey.sryData,
            sryStCategoryPageList=old_survey.sryStCategoryPageList,
            sryCountryList=old_survey.sryCountryList,
            sryStatus=0,
            sryStId=old_survey.sryStId,
            memberId=get_client_id_by_tenant_id(final_member_id),
            sryCreatedDate=timezone.now().date(),
            sryUpdateDate=timezone.now().date(),
            sryStTotalQuestions=old_survey.sryStTotalQuestions
        )

        # Mirror Java: copy image folders
        file_upload_dir = getattr(settings, 'FILE_UPLOAD_DIR', '')
        src_path = os.path.join(file_upload_dir, "survey", str(final_member_id), str(sryId))
        dest_path = os.path.join(file_upload_dir, "survey", str(final_member_id), str(new_survey.sryId))

        if os.path.exists(src_path):
            if not os.path.exists(os.path.dirname(dest_path)):
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copytree(src_path, dest_path)
            
            # Update paths in sryData
            if new_survey.sryData:
                new_survey.sryData = new_survey.sryData.replace(f"survey/{final_member_id}/{sryId}", f"survey/{final_member_id}/{new_survey.sryId}")
                new_survey.save()

        resBody["sryId"] = new_survey.sryId
        return api_response(200, "Survey Copied Successfully.", resBody)
    except Exception as e:
        logger.error(f"GetSurveyCopy Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['GET'])
def getPreviewSurveyData(request: Request):
    resBody = dict()
    resBody["error"] = ""
    try:
        encrypted_id = request.GET.get('id')
        ss_session_id = request.GET.get('ssSessionId')
        
        sry_id = DecryptString.set_enc_dec_user(encrypted_id, "display", "Y")
        try:
            survey = Surveys.objects.get(sryId=sry_id)
        except Surveys.DoesNotExist:
            return api_response(404, "Survey Not Found", resBody)

        # countryNameList lookup
        country_name_list = []
        if survey.sryCountryList:
            try:
                country_ids = [int(cid.strip()) for cid in survey.sryCountryList.split(',') if cid.strip().isdigit()]
                if country_ids:
                    country_name_list = list(Country.objects.filter(country_id__in=country_ids).values_list('iso2', flat=True))
            except Exception as e:
                logger.error(f"Error fetching countryNameList: {e}")

        resBody["survey"] = {
            "sryId": survey.sryId,
            "sryData": survey.sryData,
            "countryNameList": country_name_list
        }

        # Match Java: "close" field (Y if status=2, else N)
        resBody["close"] = "Y" if survey.sryStatus == 2 else "N"

        # Match Java: fetch existing answers if ssSessionId is provided
        resBody["surveyAnswers"] = []
        if ss_session_id:
            try:
                stats = SurveysStatistics.objects.get(ssSessionId=ss_session_id, ssSryId=sry_id)
                answers = SurveysAnswers.objects.filter(sansSsId=stats.ssId)
                resBody["surveyAnswers"] = [{
                    "sansId": ans.sansId,
                    "sansSsId": ans.sansSsId,
                    "sansSpgId": ans.sansSpgId,
                    "sansSqueId": ans.sansSqueId,
                    "sansAnswers": ans.sansAnswers,
                    "sansComments": ans.sansComments
                } for ans in answers]
            except SurveysStatistics.DoesNotExist:
                pass

        return api_response(200, "Fetch Survey Data Successfully.", resBody)
    except Exception as e:
        logger.error(f"GetPreviewSurveyData Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['POST'])
def saveSurveyAnswers(request: Request):
    resBody = dict()
    resBody["error"] = ""
    try:
        data = request.data
        ss_sry_id = data.get('ssSryId')
        ss_session_id = data.get('ssSessionId', '')
        ss_is_complete = data.get('ssIsComplete', 0)
        survey_answers = data.get('surveyAnswers', [])

        try:
            survey = Surveys.objects.get(sryId=ss_sry_id)
        except Surveys.DoesNotExist:
            return api_response(404, "Survey Not Found", resBody)

        # 1. Source Detection (PC vs Phone)
        ua_string = request.META.get('HTTP_USER_AGENT', '')
        ua = parse(ua_string)
        sources = "Phone" if (ua.is_mobile or ua.is_tablet) else "PC"

        # 2. Campaign Transaction Handling (Only if new session)
        if not ss_session_id or ss_session_id == "":
            country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(survey.memberId))
            tran_member_rate = country_setting.cnty_survey_per_price if country_setting else 0.0
            
            try:
                # findUninvoicedById equivalent
                ct = CampaignTransaction.objects.filter(
                    tran_campaign_id=ss_sry_id, 
                    tran_type='survey', 
                    tran_invoiced_status='uninvoiced',
                    ct_client_id=survey.memberId
                ).first()
            except Exception as e:
                logger.error(f"SaveSurveyAnswers Error 1: {e}")
                ct = None

            if ct is None:
                CommonServices.saveCampaignTransaction(
                    ss_sry_id, survey.sryName, 1, "survey", 
                    None, "uninvoiced", None, survey.memberId, 
                    "0", tran_member_rate, tran_member_rate, 
                    0, None, None, 0
                )
            else:
                ct.tran_total_member = (ct.tran_total_member or 0) + 1
                ct.tran_total_amount = ct.tran_total_member * (ct.tran_member_rate or 0.0)
                ct.tran_campaign_date = timezone.now()
                ct.save()
            
            # Fix: Avoid request.session if sessions are disabled in settings
            if not ss_session_id or ss_session_id == "":
                try:
                    if hasattr(request, 'session') and request.session:
                        if not request.session.session_key:
                            request.session.create()
                        ss_session_id = request.session.session_key
                except Exception:
                    pass
                
                if not ss_session_id:
                    ss_session_id = str(uuid.uuid4()).replace('-', '').upper()

        # 3. Statistics Save
        try:
            stats = SurveysStatistics.objects.get(ssSessionId=ss_session_id, ssSryId=ss_sry_id)
        except SurveysStatistics.DoesNotExist:
            stats = SurveysStatistics(ssSessionId=ss_session_id, ssSryId=ss_sry_id)
            stats.ssDate = timezone.now()
            # Fix: Save IP, location, and technology metadata from request
            stats.ssIpAddress = request.META.get('REMOTE_ADDR')
            stats.ssCity = data.get('ssCity', stats.ssCity)
            stats.ssState = data.get('ssState', stats.ssState)
            stats.ssCountry = data.get('ssCountry', stats.ssCountry)
            stats.ssTechnology = technology_detection(ua_string)
            stats.ssSources = sources
            stats.ssIsComplete = ss_is_complete
            stats.save()

        # 4. Answers Processing
        saved_answers_dtos = []
        for ans_data in survey_answers:
            sans_id = ans_data.get('sansId', 0)
            sans_spg_id = ans_data.get('sansSpgId')
            sans_sque_id = ans_data.get('sansSqueId')
            sans_answers = ans_data.get('sansAnswers')
            sans_comments = ans_data.get('sansComments')
            reset_question = ans_data.get('resetQuestion', 'No')

            # Reset Question Logic (Early Return)
            if sans_answers is None and reset_question == "Yes":
                SurveysAnswers.objects.filter(sansId=sans_id).delete()
                resBody["surveysAnswers"] = {
                    "ssId": stats.ssId,
                    "ssSryId": stats.ssSryId,
                    "ssSessionId": stats.ssSessionId,
                    "ssSqueComplete": stats.ssSqueComplete or 0,
                    "ssIsComplete": stats.ssIsComplete or 0,
                    "surveyAnswers": []
                }
                return api_response(200, "Saved Successfully.", resBody)

            if sans_answers is not None and reset_question == "Yes":
                try:
                    ans_json = json.loads(sans_answers) if isinstance(sans_answers, str) else sans_answers
                    if isinstance(ans_json, dict) and ans_json.get('value') is False:
                        SurveysAnswers.objects.filter(sansId=sans_id).delete()
                        resBody["surveysAnswers"] = {
                            "ssId": stats.ssId,
                            "ssSryId": stats.ssSryId,
                            "ssSessionId": stats.ssSessionId,
                            "ssSqueComplete": stats.ssSqueComplete or 0,
                            "ssIsComplete": stats.ssIsComplete or 0,
                            "surveyAnswers": []
                        }
                        return api_response(200, "Saved Successfully.", resBody)
                except Exception:
                    pass

            # Cleaning Comments JSON (Match Java Logic)
            if sans_comments == "":
                sans_comments = None
            
            if sans_comments is not None:
                try:
                    c_json = json.loads(sans_comments) if isinstance(sans_comments, str) else sans_comments
                    if isinstance(c_json, dict):
                        # Remove empty or null values
                        keys_to_remove = [k for k, v in c_json.items() if v is None or v == ""]
                        for k in keys_to_remove:
                            del c_json[k]
                        
                        if not c_json:
                            sans_comments = None
                        else:
                            sans_comments = json.dumps(c_json)
                except Exception:
                    pass

            # Database Save
            if sans_id != 0:
                try:
                    ans_obj = SurveysAnswers.objects.get(sansId=sans_id)
                except SurveysAnswers.DoesNotExist:
                    ans_obj = SurveysAnswers(sansSsId=stats.ssId, sansSqueId=sans_sque_id)
            else:
                ans_obj = SurveysAnswers.objects.filter(sansSsId=stats.ssId, sansSqueId=sans_sque_id).first()
                if not ans_obj:
                    ans_obj = SurveysAnswers(sansSsId=stats.ssId, sansSqueId=sans_sque_id)

            if ans_obj:
                ans_obj.sansSpgId = sans_spg_id
                ans_obj.sansAnswers = sans_answers
                ans_obj.sansComments = sans_comments
                ans_obj.save()
            
                # For response DTO
                saved_answers_dtos.append({
                    "sansId": ans_obj.sansId,
                    "sansSsId": ans_obj.sansSsId,
                    "sansSpgId": ans_obj.sansSpgId,
                    "sansSqueId": ans_obj.sansSqueId,
                    "sansAnswers": ans_obj.sansAnswers,
                    "sansComments": ans_obj.sansComments
                })

        # 5. Progress Update (Total Unique Questions Answered)
        try:
            total_complete = SurveysAnswers.objects.filter(sansSsId=stats.ssId).values('sansSqueId').distinct().count()
            stats.ssSqueComplete = total_complete
            stats.save()
        except Exception as e:
            logger.error(f"SaveSurveyAnswers Error 3: {e}")

        # 6. Final Response
        resBody["surveysAnswers"] = {
            "ssId": stats.ssId,
            "ssSryId": stats.ssSryId,
            "ssSessionId": stats.ssSessionId,
            "ssSqueComplete": stats.ssSqueComplete,
            "ssIsComplete": stats.ssIsComplete or 0,
            "ssIpAddress": stats.ssIpAddress,
            "ssCity": stats.ssCity,
            "ssState": stats.ssState,
            "ssCountry": stats.ssCountry,
            "ssTechnology": stats.ssTechnology,
            "surveyAnswers": saved_answers_dtos
        }
        return api_response(200, "Save Data Successfully", resBody)
    except Exception as e:
        logger.error(f"SaveSurveyAnswers Error : {str(e)}")
        logger.error(traceback.format_exc())
        return api_response(500, "Error", {"error": "Invalid Data", "details": str(e)})

@api_view(['POST'])
def finalSendSurvey(request: Request):
    resBody = {"error": ""}
    try:
        data = request.data
        sry_id = data.get('sryId')
        try:
            survey = Surveys.objects.get(sryId=sry_id)
        except Surveys.DoesNotExist:
            return api_response(404, "Survey Not Found", resBody)

        survey.sryStatus = 1
        survey.save()

        # Match Java: finalSendSurvey logic
        country_setting = CommonServices.country_setting_by_tenant_id(survey.memberId)
        if country_setting:
            tran_member_rate = country_setting.cnty_survey_per_price
            CommonServices.saveCampaignTransaction(
                survey.sryId, survey.sryName, 0, "survey", None, "uninvoiced", None,
                survey.memberId, "0", 0.0, tran_member_rate, 0, None, None,
                0
            )

        return api_response(200, "Survey Sent Successfully.", resBody)
    except Exception as e:
        logger.error(f"FinalSendSurvey Error : {e}")
        return api_response(500, "Error", {"error": "Invalid Data"})

@api_view(['GET'])
def checkSurveyNameExists(request: Request):
    resBody = {"nameExists": False}
    try:
        survey_name = request.GET.get('surveyName')
        survey_id = int(request.GET.get('surveyId', 0))
        
        final_member_id = get_final_tenant_id(request=request)

        # Match Java logic: checkSurveyNameExists
        if survey_id == 0:
            exists = Surveys.objects.filter(memberId=final_member_id, sryName__iexact=survey_name).exists()
        else:
            exists = Surveys.objects.filter(memberId=final_member_id, sryName__iexact=survey_name).exclude(sryId=survey_id).exists()

        resBody["nameExists"] = exists
        return api_response(200, "Success", resBody)
    except Exception as e:
        logger.error(f"CheckSurveyNameExists Error : {e}")
        return api_response(500, "Error", resBody)
