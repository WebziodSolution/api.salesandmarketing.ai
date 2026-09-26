from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from common_app.custom_permissions import WhitelistPermission
from common_app.utils import api_response, get_final_tenant_id, total_uninvoiced_amt, get_browser_name, get_tenants, get_client_id_by_tenant_id, get_tenant_id_by_client_id
from common_app.services import CommonServices
from common_app.decrypt_string import DecryptString
from django.conf import settings
import logging
import json
import os
import shutil
import uuid
from django.utils import timezone
from django.db import transaction
from common_app.models import ( Invoices, CountrySetting, CampaignTransaction, Country)
from assessment_app.models import Assessments, AssessmentQuestionCategory, AssessmentsAnswers, AssessmentsOptions, AssessmentsOptionsColumns, AssessmentsPages, AssessmentsQuestions, AssessmentsStatistics, AssessmentsTemplate
from django.core.paginator import Paginator
from user_agents import parse
from django.db.models import Sum

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentAllList(request):
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        assessments = Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id), assStatus=1)
        assessment_list = []
        site_url = getattr(settings, 'SITE_URL', 'https://qawebapp.salesandmarketing.ai/')

        for ass in assessments:
            ass_id_str = str(ass.assId)
            encrypted_ass_id = DecryptString.set_enc_dec_user(ass_id_str, "", "Y")

            assessment_list.append({
                "assUrl": f"{site_url}assessment?v={encrypted_ass_id}",
                "assName": ass.assName
            })

        res_body["assessmentList"] = assessment_list
        return api_response(200, "Fetch Assessment Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAssessmentAllList Error : {e}")
        return api_response(500, "Error occurred while fetching assessments.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentAllListAuto(request:Request):
    # This mirrors the Java implementation which calls the same service method
    return getAssessmentAllList(request._request)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveAssessmentData(request):
    tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    res_body["error"] = ""
    res_body["location"] = ""
    res_body["assessmentLinkUrl"] = ""
    data = request.data
    ass_id = data.get('assId', 0)
    ass_at_id = data.get('assAtId', 0)
    
    try:
        with transaction.atomic():
            # Find data assessment template
            if ass_at_id > 0:
                try:
                    template = AssessmentsTemplate.objects.get(at_id=ass_at_id)
                    data['assData'] = template.at_data
                    data['assAtAnalysis'] = template.at_analysis
                    data['assAtCategoryPageList'] = template.at_category_page_list
                    data['assAtTotalQuestions'] = template.at_total_questions
                except AssessmentsTemplate.DoesNotExist:
                    pass

            site_url = getattr(settings, 'SITE_URL', 'https://qawebapp.salesandmarketing.ai/')
            
            if ass_id == 0:
                assessment = Assessments(
                    assClientId=get_client_id_by_tenant_id(tenant_id),
                    assName=data.get('assName'),
                    assDescription=data.get('assDescription'),
                    assData=data.get('assData'),
                    assAtAnalysis=data.get('assAtAnalysis'),
                    assAtCategoryPageList=data.get('assAtCategoryPageList'),
                    assCountryList=data.get('assCountryList'),
                    assStatus=data.get('assStatus', 0),
                    assAtId=ass_at_id,
                    assAtTotalQuestions=data.get('assAtTotalQuestions', 0),
                    assGroupId=data.get('assGroupId', 0),
                    assCreatedDate=timezone.now().date(),
                    assUpdateDate=timezone.now().date()
                )
                assessment.save()
                ass_id = assessment.assId
            else:
                try:
                    assessment = Assessments.objects.get(assId=ass_id)
                    assessment.assName = data.get('assName')
                    assessment.assDescription = data.get('assDescription')
                    assessment.assData = data.get('assData')
                    assessment.assCountryList = data.get('assCountryList')
                    assessment.assStatus = data.get('assStatus', 0)
                    assessment.assAtId = ass_at_id
                    assessment.assAtTotalQuestions = data.get('assAtTotalQuestions', 0)
                    assessment.assUpdateDate = timezone.now().date()
                    assessment.assGroupId = data.get('assGroupId', 0)
                    assessment.assAtAnalysis = data.get('assAtAnalysis')
                    assessment.assAtCategoryPageList = data.get('assAtCategoryPageList')
                    assessment.save()
                except Assessments.DoesNotExist:
                    return api_response(404, "Assessment not found.", res_body)

            # Change image path
            ass_data_str = assessment.assData
            if ass_data_str:
                old_path = f"{site_url}usercontent/{tenant_id}/images/assessmenttemplate/{ass_at_id}"
                new_path = f"{site_url}usercontent/{tenant_id}/images/assessment/{ass_id}"
                ass_data_str = ass_data_str.replace(old_path, new_path)
                assessment.assData = ass_data_str
                assessment.save()

                file_dir = getattr(settings, 'FILE_UPLOAD_DIR', '')
                if file_dir:
                    old_folder = os.path.join(file_dir, str(tenant_id), "images", "assessmenttemplate", str(ass_at_id))
                    new_folder = os.path.join(file_dir, str(tenant_id), "images", "assessment", str(ass_id))
                    if os.path.exists(old_folder):
                        if not os.path.exists(new_folder):
                            os.makedirs(new_folder, exist_ok=True)
                        # Copy contents of old_folder to new_folder
                        for item in os.listdir(old_folder):
                            s = os.path.join(old_folder, item)
                            d = os.path.join(new_folder, item)
                            if os.path.isdir(s):
                                shutil.copytree(s, d, dirs_exist_ok=True)
                            else:
                                shutil.copy2(s, d)

                # If published, create sub-entities
                if assessment.assStatus == 1 and ass_data_str:
                    try:
                        ass_json_data = json.loads(ass_data_str)
                        pages = ass_json_data.get('assessmentsPages', [])
                        for page in pages:
                            ass_pg = AssessmentsPages.objects.create(
                                ap_page_number=page.get('apgNumber'),
                                ap_ass_id=ass_id,
                                ap_page_type=page.get('apgType')
                            )
                            page_id = ass_pg.ap_id

                            ass_data_str = ass_data_str.replace('"apgId":0', f'"apgId":{page_id}', 1)

                            questions = page.get('assessmentsQuestions', [])
                            for que in questions:
                                ass_que = AssessmentsQuestions.objects.create(
                                    aq_page_id=page_id,
                                    aq_question=que.get('aqueQuestion'),
                                    aq_type=que.get('aqueType'),
                                    aq_display_order=que.get('aqueDisplayOrder'),
                                    aq_que_cat_id=que.get('aqueCatId')
                                )
                                aque_id = ass_que.aq_que_id
                                ass_data_str = ass_data_str.replace('"aqueId":0', f'"aqueId":{aque_id}', 1)

                                if que.get('aqueType') == "matrix":
                                    rows = que.get('rows', [])
                                    for row in rows:
                                        AssessmentsOptions.objects.create(
                                            ao_que_id=aque_id,
                                            ao_value=row.get('aoptValue'),
                                            ao_display_order=row.get('aoptDisplayOrder'),
                                            ao_has_comments=0,
                                            ao_opt_points=row.get('aoptPoints', 0)
                                        )
                                    cols = que.get('columns', [])
                                    for col in cols:
                                        AssessmentsOptionsColumns.objects.create(
                                            aoc_que_id=aque_id,
                                            aoc_value=col.get('aoptValue'),
                                            aoc_display_order=col.get('aoptDisplayOrder'),
                                            aoc_points=col.get('aoptPoints', 0)
                                        )
                                else:
                                    opts = que.get('assessmentsOptions', [])
                                    for opt in opts:
                                        AssessmentsOptions.objects.create(
                                            ao_que_id=aque_id,
                                            ao_value=opt.get('aoptValue'),
                                            ao_display_order=opt.get('aoptDisplayOrder'),
                                            ao_description=opt.get('aoptDescription'),
                                            ao_opt_points=opt.get('aoptPoints', 0),
                                            ao_has_comments=1 if opt.get('aoptComment') == "yes" else 0
                                        )
                        
                        assessment.assData = ass_data_str
                        assessment.save()

                        tenant = get_tenants(
                            where_conditions={
                                "tenant": {
                                    "ten_id": tenant_id
                                }
                            }
                        )
                        cnt_id = tenant.ten_country or "100"
                        pl_id = tenant.td_plan_id or 1
                        try:
                            country_setting = CountrySetting.objects.get(cnty_id=int(cnt_id), cnty_plan_id=pl_id)
                        except CountrySetting.DoesNotExist:
                            country_setting = CountrySetting.objects.get(cnty_id=100, cnty_plan_id=2)
                        
                        tran_member_rate = country_setting.cnty_survey_per_price or 0
                        
                        if tenant.td_authorize_customer_profile_id and tenant.td_authorize_customer_payment_profile_id:
                            CommonServices.saveCampaignTransaction(
                                assessment.assId, assessment.assName, 0, "assessment", 
                                None, "uninvoiced", None, get_client_id_by_tenant_id(tenant_id), "0", 0.0,
                                tran_member_rate, 0, None, None, 0
                            )
                        else:
                            inv_id = 0
                            try:
                                inv = Invoices.objects.filter(member_id=get_client_id_by_tenant_id(tenant_id)).order_by('-invId').first()
                                if inv:
                                    inv_id = inv.invId
                            except Exception:
                                pass
                            
                            if inv_id == 0:
                                total_uninvoiced = total_uninvoiced_amt(tenant_id)
                                if total_uninvoiced >= (country_setting.cnty_first_inv_free_amt or 0):
                                    assessment.assStatus = 0
                                    assessment.save()
                                    encrypted_id = DecryptString.set_enc_dec_user(str(ass_id), "", "Y")
                                    res_body["assessmentLinkUrl"] = f"{site_url}assessment?v={encrypted_id}"
                                    res_body["assId"] = assessment.assId
                                    res_body["location"] = "paymentProfile"
                                    return api_response(200, "Redirect to payment profile.", res_body)
                                else:
                                    CommonServices.saveCampaignTransaction(
                                        assessment.assId, assessment.assName, 0, "assessment", 
                                        None, "uninvoiced", None, get_client_id_by_tenant_id(tenant_id), "0", 0.0,
                                        tran_member_rate, 0, None, None, 0
                                    )
                            else:
                                assessment.assStatus = 0
                                assessment.save()
                                encrypted_id = DecryptString.set_enc_dec_user(str(ass_id), "", "Y")
                                res_body["assessmentLinkUrl"] = f"{site_url}assessment?v={encrypted_id}"
                                res_body["assId"] = assessment.assId
                                res_body["location"] = "paymentProfile"
                                return api_response(200, "Redirect to payment profile.", res_body)
                    except Exception as e:
                        logger.error(f"[ tenantId : {tenant_id} ] SaveAssessmentData Error JSON/Table : {e}")

            if assessment.assStatus == 1:
                encrypted_id = DecryptString.set_enc_dec_user(str(ass_id), "", "Y")
                res_body["assessmentLinkUrl"] = f"{site_url}assessment?v={encrypted_id}"
            
            msg = "Assessment Data Added Successfully." if data.get('assId', 0) == 0 else "Assessment Data Updated Successfully."
            return api_response(200, msg, res_body)

    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] SaveAssessmentData Error : {e}")
        res_body["error"] = "Invalid data"
        return api_response(500, "Error occurred while saving assessment.", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteAssessment(request):
    final_tenant_id = get_final_tenant_id(request=request)
    res_body = {}
    data = request.data
    ass_ids = data.get('assId', [])
    try:
        file_dir = getattr(settings, 'FILE_UPLOAD_DIR', '')
        for ass_id in ass_ids:
            assessments = Assessments.objects.filter(assId=ass_id, assClientId=get_client_id_by_tenant_id(final_tenant_id))
            assessments.delete()
            new_path = f"{file_dir}/usercontent/{final_tenant_id}/images/assessment/{ass_id}"
            if os.path.exists(new_path):
                shutil.rmtree(new_path)
        
        return api_response(200, "Delete Assessment Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] DeleteAssessment Error : {e}")
        return api_response(500, "Error occurred while deleting assessments.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentListPages(request):
    final_tenant_id = get_final_tenant_id(request=request)
    search_key = request.query_params.get('searchKey', '')
    ass_group_id = request.query_params.get('assGroupId')
    page_num = int(request.query_params.get('page', 0)) + 1 # Spring uses 0-based, Django uses 1-based
    page_size = int(request.query_params.get('size', 10))
    
    res_body = {}
    try:
        queryset = Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id))
        if ass_group_id:
            queryset = queryset.filter(assGroupId=ass_group_id)
        if search_key:
            queryset = queryset.filter(assName__icontains=search_key)
            
        paginator = Paginator(queryset.order_by('-assId'), page_size)
        page_obj = paginator.get_page(page_num)
        
        assessment_list = []
        for ass in page_obj:
            ass_id_str = str(ass.assId)
            encrypted_id = DecryptString.set_enc_dec_user(ass_id_str, "", "Y")
            
            total_responses = AssessmentsStatistics.objects.filter(as_ass_id=ass.assId).count()
            
            assessment_list.append({
                "assId": ass.assId,
                "assName": ass.assName,
                "assStatus": ass.assStatus,
                "assCreatedDate": ass.assCreatedDate.strftime("%m/%d/%Y") if ass.assCreatedDate else "",
                "id": encrypted_id,
                "assUrl": f"{getattr(settings, 'SITE_URL', 'https://qawebapp.salesandmarketing.ai/')}assessment?v={encrypted_id}",
                "assAtTotalQuestions": ass.assAtTotalQuestions,
                "totalResponses": total_responses
            })
            
        res_body["getNumber"] = page_num - 1
        res_body["getSize"] = page_size
        res_body["totalAssessment"] = paginator.count
        res_body["assessmentList"] = assessment_list
        res_body["getTotalPages"] = paginator.num_pages
        
        return api_response(200, "Fetch Assessment Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAssessmentListPages Error : {e}")
        return api_response(500, "Error occurred while fetching assessments.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentById(request, assId):
    final_tenant_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        try:
            ass = Assessments.objects.get(assId=assId, assClientId=get_client_id_by_tenant_id(final_tenant_id))
            res_body["assessment"] = {
                "assId": ass.assId,
                "assName": ass.assName,
                "assDescription": ass.assDescription,
                "assData": ass.assData,
                "assAtAnalysis": ass.assAtAnalysis,
                "assAtCategoryPageList": ass.assAtCategoryPageList,
                "assCountryList": ass.assCountryList,
                "assStatus": ass.assStatus,
                "assAtId": ass.assAtId,
                "assAtTotalQuestions": ass.assAtTotalQuestions,
                "assClientId": ass.assClientId,
                "assCreatedDate": ass.assCreatedDate.strftime("%m-%d-%Y %H:%M:%S") if ass.assCreatedDate else None,
                "assUpdateDate": ass.assUpdateDate.strftime("%m-%d-%Y %H:%M:%S") if ass.assUpdateDate else None,
                "assGroupId": ass.assGroupId
            }
        except Assessments.DoesNotExist:
            pass
        return api_response(200, "Fetch Assessment Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAssessmentById Error : {e}")
        return api_response(500, "Error occurred while fetching assessment.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def closeAssessment(request):
    data = request.data
    final_tenant_id = get_final_tenant_id(request=request)
    assId = data.get('assId',[]) 
    res_body = {}
    try:
        try:
            for ass_id in assId:
                assessment = Assessments.objects.get(assId=ass_id, assClientId=get_client_id_by_tenant_id(final_tenant_id))
                assessment.assStatus = 2
                assessment.save()
        except Assessments.DoesNotExist:
            pass
            
        return api_response(200, "Close Assessment Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] CloseAssessment Error : {e}")
        return api_response(500, "Error occurred while closing assessment.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentCopy(request, subTenantId, assId):
    final_tenant_id = get_final_tenant_id(request=request)
    ass_id = assId
    res_body = dict()
    try:
        try:
            original = Assessments.objects.get(assId=ass_id, assClientId=get_client_id_by_tenant_id(final_tenant_id))
            # Create a copy
            res_body = Assessments.objects.create(
                assName=f"{original.assName} copy",
                assDescription=original.assDescription,
                assData=original.assData,
                assAtAnalysis=original.assAtAnalysis,
                assAtCategoryPageList=original.assAtCategoryPageList,
                assCountryList=original.assCountryList,
                assStatus=0,
                assAtId=original.assAtId,
                assAtTotalQuestions=original.assAtTotalQuestions,
                assClientId=get_client_id_by_tenant_id(final_tenant_id),
                assCreatedDate=timezone.now().date(),
                assUpdateDate=timezone.now().date(),
                assGroupId=original.assGroupId
            )
        except Assessments.DoesNotExist:
            pass
            
        return api_response(200, "Copy Assessment Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetAssessmentCopy Error : {e}")
        return api_response(500, "Error occurred while copying assessment.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getPreviewAssessmentData(request):
    id_param = request.query_params.get('id')
    if not id_param:
        id_param = request.query_params.get('assId')
        
    as_session_id = request.query_params.get('asSessionId', '')
    res_body = dict()
    res_body["error"] = ""
    res_body["close"] = "N"
    res_body["assessmentAnswers"] = []
    try:
        id_param = DecryptString.set_enc_dec_user(id_param, "display", "Y")
        ass_id = int(id_param)
    except (TypeError, ValueError):
        ass_id = 0
    try:
        try:
            assessment = Assessments.objects.get(assId=ass_id)
            if assessment.assStatus == 2:
                print("if part")
                res_body["close"] = "Y"
            else:
                print("else part")
                country_name_list = []
                if assessment.assCountryList:
                    country_ids = assessment.assCountryList.split(',')
                    for cid in country_ids:
                        try:
                            country = Country.objects.get(country_id=int(cid))
                            if country.iso2:
                                country_name_list.append(country.iso2)
                        except (Country.DoesNotExist, ValueError):
                            pass
                
                res_body["assessment"] = {
                    "assId": assessment.assId,
                    "assData": assessment.assData,
                    "countryNameList": country_name_list
                }
                
                if as_session_id:
                    try:
                        stats = AssessmentsStatistics.objects.get(as_session_id=as_session_id, as_ass_id=ass_id)
                        answers = AssessmentsAnswers.objects.filter(aa_as_id=stats.as_id)
                        
                        answer_list = []
                        for ans in answers:
                            answer_list.append({
                                "aansId": ans.aa_id,
                                "aansAsId": ans.aa_as_id,
                                "aansApgId": ans.aa_apg_id,
                                "aansAqueId": ans.aa_aque_id,
                                "aansAnswers": ans.aa_answers,
                                "aansComments": ans.aa_comments,
                                "aansOptPoints": ans.aa_opt_points
                            })
                        
                        res_body["assessmentAnswers"] = {
                            "asId": stats.as_id,
                            "asAssId": stats.as_ass_id,
                            "asAqueComplete": stats.as_aque_complete,
                            "asIsComplete": stats.as_is_complete,
                            "asSessionId": stats.as_session_id,
                            "asIpAddress": stats.as_ip_address,
                            "asDate": stats.as_date.strftime("%m-%d-%Y %H:%M:%S") if stats.as_date else None,
                            "asCity": stats.as_city,
                            "asState": stats.as_state,
                            "asCountry": stats.as_country,
                            "asTechnology": stats.as_technology,
                            "asSources": stats.as_sources,
                            "assessmentAnswers": answer_list
                        }
                    except AssessmentsStatistics.DoesNotExist:
                        pass
        except Assessments.DoesNotExist:
            res_body["error"] = "Data Not Found"
            
        if res_body.get("error"):
            return api_response(500, "Data Not Found", res_body)
        else:
            return api_response(200, "Fetch Assessment Data Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetPreviewAssessmentData Error : {e}")
        res_body["error"] = "Data Not Found"
        return api_response(500, "Data Not Found", res_body)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveAssessmentAnswers(request):
    res_body = dict()
    res_body["error"] = ""
    data = request.data
    ass_id = data.get('asAssId')
    session_id = data.get('asSessionId', '')
    
    try:
        ua_string = request.META.get('HTTP_USER_AGENT', '')
        user_agent = parse(ua_string)
        sources = "Phone" if (user_agent.is_mobile or user_agent.is_tablet) else "PC"
        
        try:
            assessment = Assessments.objects.get(assId=ass_id)
        except Assessments.DoesNotExist:
            return api_response(404, "Assessment not found.", res_body)
            
        if not session_id:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": get_tenant_id_by_client_id(assessment.assClientId)
                    }
                }
            )
            cnt_id = tenant.ten_country or "100"
            pl_id = tenant.td_plan_id or 1
            try:
                country_setting = CountrySetting.objects.get(cnty_id=int(cnt_id), cnty_plan_id=pl_id)
            except CountrySetting.DoesNotExist:
                country_setting = CountrySetting.objects.get(cnty_id=100, cnty_plan_id=2)
            
            rate = country_setting.cnty_survey_per_price or 0
            
            camp_tran = CampaignTransaction.objects.filter(tran_campaign_id=ass_id, tran_type='assessment', tran_invoiced_status='uninvoiced').first()
            
            if not camp_tran:
                CommonServices.saveCampaignTransaction(
                    ass_id, assessment.assName, 1, 'assessment', 
                    None, 'uninvoiced', None, assessment.assClientId,
                    '0', rate, rate, 0, None, None, 0
                )
            else:
                camp_tran.tran_total_member = (camp_tran.tran_total_member or 0) + 1
                camp_tran.tran_total_amount = camp_tran.tran_total_member * (camp_tran.tran_member_rate or 0)
                camp_tran.tran_campaign_date = timezone.now()
                camp_tran.save()
            
            if hasattr(request, 'session') and request.session.session_key:
                session_id = request.session.session_key
            elif hasattr(request, '_request') and hasattr(request, 'session') and request.session.session_key:
                session_id = request.session.session_key
            else:
                session_id = str(uuid.uuid4())
            
        # Get or create stats
        stats, created = AssessmentsStatistics.objects.get_or_create(
            as_session_id=session_id, 
            as_ass_id=ass_id,
            as_ip_address=data.get('asIpAddress'),
            as_city=data.get('asCity'),
            as_state=data.get('asState'),
            as_country=data.get('asCountry'),            
            defaults={'as_date': timezone.now()}
        )
        
        if not created:
            stats.as_date = timezone.now()
        
        stats.as_technology = get_browser_name(ua_string)
        stats.as_sources = sources
        stats.save()
        
        def stats_to_dict(stats_obj, answers=None):
            return {
                "asId": stats_obj.as_id,
                "asAssId": stats_obj.as_ass_id,
                "asAqueComplete": stats_obj.as_aque_complete,
                "asIsComplete": stats_obj.as_is_complete,
                "asSessionId": stats_obj.as_session_id,
                "asIpAddress": stats_obj.as_ip_address,
                "asDate": stats_obj.as_date.strftime("%m-%d-%Y %H:%M:%S") if stats_obj.as_date else None,
                "asCity": stats_obj.as_city,
                "asState": stats_obj.as_state,
                "asCountry": stats_obj.as_country,
                "asTechnology": stats_obj.as_technology,
                "asSources": stats_obj.as_sources,
                "assessmentAnswers": answers or []
            }

        answers_data = data.get('assessmentAnswers', [])
        saved_answers = []
        
        for ans_dto in answers_data:
            reset_question = ans_dto.get('resetQuestion', 'No')
            if not ans_dto.get('aansAnswers') and reset_question == 'Yes':
                AssessmentsAnswers.objects.filter(aa_id=ans_dto.get('aansId')).delete()
                res_body["assessmentsAnswers"] = stats_to_dict(stats)
                return api_response(200, "Reset Successful.", res_body)
            
            if ans_dto.get('aansAnswers') and reset_question == 'Yes':
                try:
                    js = json.loads(ans_dto['aansAnswers'])
                    if js.get('value') is False:
                        AssessmentsAnswers.objects.filter(aa_id=ans_dto.get('aansId')).delete()
                        res_body["assessmentsAnswers"] = stats_to_dict(stats)
                        return api_response(200, "Reset Successful.", res_body)
                except: pass

            comments = ans_dto.get('aansComments')
            if comments:
                try:
                    cjs = json.loads(comments)
                    cleaned_cjs = {k: v for k, v in cjs.items() if v}
                    comments = json.dumps(cleaned_cjs) if cleaned_cjs else None
                except: pass
            
            points = 0
            if ans_dto.get('aansAnswers'):
                try:
                    ajs = json.loads(ans_dto['aansAnswers'])
                    val = ajs.get('value')
                    aque_id = ans_dto.get('aansAqueId')
                    if isinstance(val, list):
                        for v in val:
                            opt = AssessmentsOptions.objects.filter(ao_que_id=aque_id, ao_value=str(v)).first()
                            if opt: points += (opt.ao_opt_points or 0)
                    elif isinstance(val, str):
                        opt = AssessmentsOptions.objects.filter(ao_que_id=aque_id, ao_value=str(val)).first()
                        if opt: points += (opt.ao_opt_points or 0)
                except: pass
            
            ans_obj, _ = AssessmentsAnswers.objects.update_or_create(
                aa_as_id=stats.as_id, aa_aque_id=ans_dto.get('aansAqueId'),
                defaults={
                    'aa_apg_id': ans_dto.get('aansApgId'),
                    'aa_answers': ans_dto.get('aansAnswers'),
                    'aa_comments': comments,
                    'aa_opt_points': points
                }
            )
            saved_answers.append({
                "aansId": ans_obj.aa_id,
                "aansAsId": ans_obj.aa_as_id,
                "aansApgId": ans_obj.aa_apg_id,
                "aansAqueId": ans_obj.aa_aque_id,
                "aansAnswers": ans_obj.aa_answers,
                "aansComments": ans_obj.aa_comments,
                "aansOptPoints": ans_obj.aa_opt_points
            })

        # Update complete count
        stats.as_aque_complete = AssessmentsAnswers.objects.filter(aa_as_id=stats.as_id).count()
        stats.save()

        # Overall results
        overall_points = AssessmentsAnswers.objects.filter(aa_as_id=stats.as_id).aggregate(Sum('aa_opt_points'))['aa_opt_points__sum'] or 0
        
        page_ids = AssessmentsAnswers.objects.filter(aa_as_id=stats.as_id).values_list('aa_apg_id', flat=True).distinct()
        cat_points_list = []
        for pid in page_ids:
            pg_points = AssessmentsAnswers.objects.filter(aa_as_id=stats.as_id, aa_apg_id=pid).aggregate(Sum('aa_opt_points'))['aa_opt_points__sum'] or 0
            que = AssessmentsQuestions.objects.filter(aq_page_id=pid).first()
            cat_name = ""
            if que:
                cat = AssessmentQuestionCategory.objects.filter(aqcId=que.aq_que_cat_id).first()
                if cat: cat_name = cat.aqcCatName
            cat_points_list.append({"points": pg_points, "catName": cat_name})
            
        res_body["assessmentsAnswers"] = stats_to_dict(stats, saved_answers)
        res_body["overAll"] = {
            "overAllPoints": overall_points,
            "assessmentsCatPointsList": cat_points_list
        }
        res_body["assAtAnalysis"] = assessment.assAtAnalysis
        
        return api_response(200, "Answers Saved Successfully.", res_body)
    except Exception as e:
        logger.error(f"SaveAssessmentAnswers Error : {e}")
        res_body["error"] = "Invalid data"
        return api_response(500, "Error occurred while saving answers.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def finalSendAssessment(request):
    res_body = {"error": ""}
    data = request.data
    ass_id = data.get('assId')
    try:
        assessment = Assessments.objects.get(assId=ass_id)
        assessment.assStatus = 1
        assessment.save()
        
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": get_tenant_id_by_client_id(assessment.assClientId)
                }
            }
        )
        cnt_id = tenant.ten_country or "100"
        pl_id = tenant.td_plan_id or 1
        try:
            country_setting = CountrySetting.objects.get(cnty_id=int(cnt_id), cnty_plan_id=pl_id)
        except CountrySetting.DoesNotExist:
            country_setting = CountrySetting.objects.get(cnty_id=100, cnty_plan_id=2)
            
        rate = country_setting.cnty_survey_per_price or 0
        
        CommonServices.saveCampaignTransaction(
            ass_id, assessment.assName, 0, 'assessment', 
            None, 'uninvoiced', None, assessment.assClientId,
            '0', 0, rate, 0, None, None, 0
        )
        
        return api_response(200, "Final Send Assessment Successfully.", res_body)
    except Exception as e:
        logger.error(f"FinalSendAssessment Error : {e}")
        res_body["error"] = "Invalid Data"
        return api_response(500, "Error occurred during final send.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkAssessmentNameExists(request):
    final_tenant_id = get_final_tenant_id(request=request)
    name = request.query_params.get('assessmentName', '')
    ass_id = int(request.query_params.get('assessmentId', 0))
    try:
        if ass_id == 0:
            exists = Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id), assName__iexact=name).exists()
        else:
            exists = Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id), assName__iexact=name).exclude(assId=ass_id).exists()
            
        return api_response(200, "Checked Successfully.", exists)
    except Exception as e:
        logger.error(f"CheckAssessmentNameExists Error : {e}")
        return api_response(500, "Error occurred while checking name existence.", False)