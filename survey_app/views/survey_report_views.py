import json
from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.models import Surveys, SurveysStatistics, SurveysQuestions, SurveysAnswers, SurveysOptions, SurveysOptionsColumns, SurveysPages
from common_app.utils import api_response, get_final_tenant_id
from common_app.decrypt_string import DecryptString
import logging

logger = logging.getLogger(__name__)

def get_country_list(survey_id):
    country_wise_count = SurveysStatistics.objects.filter(ssSryId=survey_id).values('ssCountry').annotate(visit=Count('ssId'))
    survey_report_country_list = []
    
    for country_data in country_wise_count:
        country_name = country_data['ssCountry'] if country_data['ssCountry'] else "Not Determinable"
        visit = country_data['visit']
        
        survey_report_country = {
            "countryName": country_name,
            "visit": str(visit)
        }
        
        state_wise_count = SurveysStatistics.objects.filter(ssSryId=survey_id, ssCountry=country_data['ssCountry']).values('ssState').annotate(visit=Count('ssId'))
        survey_report_state_list = []
        
        for state_data in state_wise_count:
            state_name = state_data['ssState'] if state_data['ssState'] else "Not Determinable"
            
            survey_report_state = {
                "stateName": state_name,
                "visit": str(state_data['visit'])
            }
            
            city_wise_count = SurveysStatistics.objects.filter(ssSryId=survey_id, ssCountry=country_data['ssCountry'], ssState=state_data['ssState']).values('ssCity').annotate(visit=Count('ssId'))
            survey_report_city_list = []
            
            for city_data in city_wise_count:
                city_name = city_data['ssCity'] if city_data['ssCity'] else "Not Determinable"
                survey_report_city_list.append({
                    "cityName": city_name,
                    "visit": str(city_data['visit'])
                })
            
            survey_report_state["cityList"] = survey_report_city_list
            survey_report_state_list.append(survey_report_state)
            
        survey_report_country["stateList"] = survey_report_state_list
        survey_report_country_list.append(survey_report_country)
        
    return survey_report_country_list

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyReportDemographic(request):
    res_body = dict()
    member_id = get_final_tenant_id(request=request)
    sry_id_enc = request.query_params.get('sryId')
    
    try:
        sry_id = int(DecryptString.set_enc_dec_user(sry_id_enc, "display", "Y"))
        survey = Surveys.objects.get(sryId=sry_id)
        surveys_statistics_data = SurveysStatistics.objects.filter(ssSryId=sry_id)
        
        res_body['surveyName'] = survey.sryName
        res_body['peopleParticipated'] = surveys_statistics_data.count()
        
        country_wise_count = SurveysStatistics.objects.filter(ssSryId=sry_id).values('ssCountry').annotate(visit=Count('ssId'))
        survey_report_country_list = []
        
        for item in country_wise_count:
            country_name = item['ssCountry'] if item['ssCountry'] else "Not Determinable"
            survey_report_country_list.append({
                "countryName": country_name,
                "visit": str(item['visit'])
            })
            
        res_body['countryFirstList'] = survey_report_country_list
        res_body['countrySecondList'] = get_country_list(sry_id)
        
        return api_response(status.HTTP_200_OK, "Survey Demographic Report Fetched Successfully.", res_body)
        
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSurveyReportDemographic Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyReportTechnologyUse(request):
    res_body = dict()
    technologies = dict()
    member_id = get_final_tenant_id(request=request)
    sry_id_enc = request.query_params.get('sryId')
    
    try:
        sry_id = int(DecryptString.set_enc_dec_user(sry_id_enc, "display", "Y"))
        survey = Surveys.objects.get(sryId=sry_id)
        res_body['surveyName'] = survey.sryName
        
        tech_list = ["Firefox", "IE", "iPhone", "iPad", "Android Phone", "Android Tab", "Chrome", "Safari", "Air", "Fluid", "Others"]
        tech_map = {
            "Firefox": "firefox", "IE": "ie", "iPhone": "iPhone", "iPad": "iPad", 
            "Android Phone": "androidPhone", "Android Tab": "androidTab", 
            "Chrome": "chrome", "Safari": "safari", "Air": "air", "Fluid": "fluid", "Others": "others"
        }
        
        for tech in tech_list:
            count = SurveysStatistics.objects.filter(ssSryId=sry_id, ssTechnology__icontains=tech).count()
            technologies[tech_map[tech]] = count
        
        res_body['technologies'] = technologies
        return api_response(status.HTTP_200_OK, "Survey Technology Use Report Fetched Successfully.", res_body)
        
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSurveyReportTechnologyUse Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

def get_matrix_type(survey_data, que_id):
    try:
        data = json.loads(survey_data)
        for page in data.get('surveysPages', []):
            if page.get('spgType') == "Question Page":
                for question in page.get('surveysQuestions', []):
                    if question.get('squeId') == que_id:
                        return int(question.get('answerType', 0))
    except Exception as e:
        logger.error(f"GetMatrixType Error : {e}")
    return 0

def get_matrix_rows(survey_data, que_id):
    rows = []
    try:
        data = json.loads(survey_data)
        for page in data.get('surveysPages', []):
            if page.get('spgType') == "Question Page":
                for question in page.get('surveysQuestions', []):
                    if question.get('squeId') == que_id:
                        for row in question.get('rows', []):
                            rows.append(row.get('soptValue'))
                        return rows
    except Exception as e:
        logger.error(f"GetMatrixRows Error : {e}")
    return rows

def get_matrix_columns(survey_data, que_id):
    columns = []
    try:
        data = json.loads(survey_data)
        for page in data.get('surveysPages', []):
            if page.get('spgType') == "Question Page":
                for question in page.get('surveysQuestions', []):
                    if question.get('squeId') == que_id:
                        for col in question.get('columns', []):
                            columns.append(col.get('soptValue'))
                        return columns
    except Exception as e:
        logger.error(f"GetMatrixColumns Error : {e}")
    return columns

def get_constant_sum_questions(survey_data, que_id):
    questions = []
    try:
        data = json.loads(survey_data)
        for page in data.get('surveysPages', []):
            if page.get('spgType') == "Question Page":
                for question in page.get('surveysQuestions', []):
                    if question.get('squeId') == que_id:
                        return question.get('labelList', [])
    except Exception as e:
        logger.error(f"GetConstantSumQuestions Error : {e}")
    return questions

def get_image_options(survey_data, que_id):
    options = []
    try:
        data = json.loads(survey_data)
        for page in data.get('surveysPages', []):
            if page.get('spgType') == "Question Page":
                for question in page.get('surveysQuestions', []):
                    if question.get('squeId') == que_id:
                        for opt in question.get('surveysOptions', []):
                            options.append([opt.get('soptValue'), opt.get('soptDescription', '')])
                        return options
    except Exception as e:
        logger.error(f"GetImageOptions Error : {e}")
    return options

def get_labels_for_contact_form(survey_data, que_id):
    labels = []
    try:
        data = json.loads(survey_data)
        for page in data.get('surveysPages', []):
            if page.get('spgType') == "Question Page":
                for question in page.get('surveysQuestions', []):
                    if question.get('squeId') == que_id:
                        for lbl in question.get('labelList', []):
                            labels.append(lbl.get('name'))
                        return labels
    except Exception as e:
        logger.error(f"GetLabelsForContactForm Error : {e}")
    return labels

def filter_by_questions_type(question_type, sry_id):
    option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
    text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
    rating_type = ["rating_box", "rating_radio", "rating_symbol"]
    
    question_list = SurveysQuestions.objects.filter(squeSpgId__in=SurveysPages.objects.filter(spgSryId=sry_id).values_list('spgId', flat=True)).order_by('squeDisplayOrder')
    
    if question_type == 1:
        return question_list
    elif question_type == 3:
        filtered_list = []
        survey = Surveys.objects.get(sryId=sry_id)
        for q in question_list:
            if q.squeType in text_answers_type:
                filtered_list.append(q)
            elif q.squeType == "matrix" and get_matrix_type(survey.sryData, q.squeId) == 3:
                filtered_list.append(q)
            elif q.squeType == "contact_form":
                filtered_list.append(q)
        return filtered_list
    else:
        filtered_list = []
        survey = Surveys.objects.get(sryId=sry_id)
        for q in question_list:
            if q.squeType in option_type or q.squeType in rating_type:
                filtered_list.append(q)
            elif q.squeType == "matrix" and get_matrix_type(survey.sryData, q.squeId) != 3:
                filtered_list.append(q)
            elif q.squeType in ["rank", "constant_sum", "consent_agreement"]:
                filtered_list.append(q)
        return filtered_list

def filter_by_control_type(control_types, surveys_questions):
    if control_types:
        return [q for q in surveys_questions if q.squeType in control_types]
    return surveys_questions

def get_statistics_id(que_ans_list, sry_id):
    option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
    text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
    rating_type = ["rating_box", "rating_radio", "rating_symbol"]
    
    ss_ans_ids = list(SurveysStatistics.objects.filter(ssSryId=sry_id).values_list('ssId', flat=True))
    
    if not que_ans_list:
        return ss_ans_ids
        
    survey = Surveys.objects.get(sryId=sry_id)
    
    try:
        for que_ans in que_ans_list:
            que_id = que_ans.get('queId')
            ans = que_ans.get('ans')
            question = SurveysQuestions.objects.get(squeId=que_id)
            que_type = question.squeType
            
            if que_type in option_type:
                match_ss_ids = list(SurveysAnswers.objects.filter(sansSqueId=que_id, sansAnswers__icontains=ans, sansSsId__in=ss_ans_ids).values_list('sansSsId', flat=True))
                if match_ss_ids:
                    ss_ans_ids = list(set(ss_ans_ids) & set(match_ss_ids))
                else:
                    return []
            elif que_type in text_answers_type:
                if que_type != "phone":
                    match_ss_ids = list(SurveysAnswers.objects.filter(sansSqueId=que_id, sansAnswers__icontains=ans, sansSsId__in=ss_ans_ids).values_list('sansSsId', flat=True))
                    if match_ss_ids:
                        ss_ans_ids = list(set(ss_ans_ids) & set(match_ss_ids))
                    else:
                        return []
                else:
                    parts = ans.split(' ')
                    code = parts[0] if len(parts) > 1 else ""
                    num = parts[1] if len(parts) > 1 else parts[0]
                    match_ss_ids = list(SurveysAnswers.objects.filter(sansSqueId=que_id, sansSsId__in=ss_ans_ids, sansAnswers__icontains=code).filter(sansAnswers__icontains=num).values_list('sansSsId', flat=True))
                    if match_ss_ids:
                        ss_ans_ids = list(set(ss_ans_ids) & set(match_ss_ids))
                    else:
                        return []
            elif que_type == "matrix":
                matrix_answers = SurveysAnswers.objects.filter(sansSqueId=que_id, sansSsId__in=ss_ans_ids)
                current_match_ids = []
                m_type = get_matrix_type(survey.sryData, que_id)
                if m_type != 3:
                    answer_row = ans.split("=")[0] if "=" in ans else ans
                    answer_column = ans.split("=")[1] if "=" in ans else ""
                    for m_ans in matrix_answers:
                        try:
                            ans_json = json.loads(m_ans.sansAnswers).get('value', {})
                            if not answer_column:
                                if answer_row in ans_json:
                                    current_match_ids.append(m_ans.sansSsId)
                            else:
                                if answer_row in ans_json and answer_column in str(ans_json.get(answer_row)):
                                    current_match_ids.append(m_ans.sansSsId)
                        except: continue
                else:
                    answer_row = ans.split("=")[0] if "=" in ans else ans
                    answer_column = ans.split("=")[1] if "=" in ans else ""
                    answer_value = ans.split("=")[2] if "=" in ans and len(ans.split("=")) > 2 else ""
                    for m_ans in matrix_answers:
                        try:
                            ans_json = json.loads(m_ans.sansAnswers).get('value', {})
                            if not answer_column and not answer_value:
                                if answer_row in ans_json:
                                    current_match_ids.append(m_ans.sansSsId)
                            elif not answer_column:
                                pass
                            else:
                                if answer_row in ans_json and answer_column in ans_json.get(answer_row, {}) and str(ans_json.get(answer_row).get(answer_column)) == answer_value:
                                    current_match_ids.append(m_ans.sansSsId)
                        except: continue
                if current_match_ids:
                    ss_ans_ids = list(set(ss_ans_ids) & set(current_match_ids))
                else:
                    return []
            elif que_type in rating_type:
                rating_answers = SurveysAnswers.objects.filter(sansSqueId=que_id, sansSsId__in=ss_ans_ids)
                current_match_ids = []
                for r_ans in rating_answers:
                    try:
                        if json.loads(r_ans.sansAnswers).get('value') == int(ans):
                            current_match_ids.append(r_ans.sansSsId)
                    except: continue
                if current_match_ids:
                    ss_ans_ids = list(set(ss_ans_ids) & set(current_match_ids))
                else:
                    return []
            elif que_type == "consent_agreement":
                consent_answers = list(SurveysAnswers.objects.filter(sansSqueId=que_id, sansSsId__in=ss_ans_ids).values_list('sansSsId', flat=True))
                if ans == "Agree":
                    if consent_answers:
                        ss_ans_ids = list(set(ss_ans_ids) & set(consent_answers))
                    else:
                        return []
                else:
                    ss_ans_ids = list(set(ss_ans_ids) - set(consent_answers))
                if not ss_ans_ids:
                    return []
            elif que_type == "contact_form":
                answer_label = ans.split("=")[0] if "=" in ans else ans
                answer_value = ans.split("=")[1] if "=" in ans else ""
                contact_answers = SurveysAnswers.objects.filter(sansSqueId=que_id, sansSsId__in=ss_ans_ids)
                current_match_ids = []
                for c_ans in contact_answers:
                    try:
                        ans_json = json.loads(c_ans.sansAnswers).get('value', {})
                        if not answer_value:
                            if answer_label in ans_json and ans_json.get(answer_label):
                                current_match_ids.append(c_ans.sansSsId)
                        else:
                            if answer_label in ans_json and str(ans_json.get(answer_label)) == answer_value:
                                current_match_ids.append(c_ans.sansSsId)
                    except: continue
                if current_match_ids:
                    ss_ans_ids = list(set(ss_ans_ids) & set(current_match_ids))
                else:
                    return []
            elif que_type == "constant_sum":
                answer_label = ans.split("=")[0] if "=" in ans else ans
                answer_value = ans.split("=")[1] if "=" in ans else ""
                cs_answers = SurveysAnswers.objects.filter(sansSqueId=que_id, sansSsId__in=ss_ans_ids)
                current_match_ids = []
                for cs_ans in cs_answers:
                    try:
                        ans_json = json.loads(cs_ans.sansAnswers).get('value', {}).get('questions', {})
                        if not answer_value:
                            current_match_ids.append(cs_ans.sansSsId)
                        else:
                            if str(ans_json.get(answer_label)) == answer_value:
                                current_match_ids.append(cs_ans.sansSsId)
                    except: continue
                if current_match_ids:
                    ss_ans_ids = list(set(ss_ans_ids) & set(current_match_ids))
                else:
                    return []
    except Exception as e:
        logger.error(f"GetStatistaicsId Error : {e}")
        return []
    return ss_ans_ids

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyReportQuestions(request):
    res_body = dict()
    questions_list = []
    member_id = get_final_tenant_id(request=request)
    sry_id_enc = request.query_params.get('sryId')
    
    try:
        sry_id = int(DecryptString.set_enc_dec_user(sry_id_enc, "display", "Y"))
        survey = Surveys.objects.get(sryId=sry_id)
        res_body['surveyName'] = survey.sryName
        
        text_answers_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
        rating_type = ["rating_box", "rating_radio", "rating_symbol"]
        
        que_count = 1
        questions = SurveysQuestions.objects.filter(squeSpgId__in=SurveysPages.objects.filter(spgSryId=sry_id).values_list('spgId', flat=True)).order_by('squeDisplayOrder')
        
        for question in questions:
            question_data = {}
            if question.squeType in text_answers_type:
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['question'] = question.squeQuestion
                total_ans_4_que = SurveysAnswers.objects.filter(sansSqueId=question.squeId).count()
                question_data['totalAnsForQues'] = total_ans_4_que
                question_data['queTypeId'] = 1
                
                options = SurveysOptions.objects.filter(soptSqueId=question.squeId)
                option_list = []
                for opt in options:
                    total_ans = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansAnswers__contains=opt.soptValue).count()
                    per_color = round(total_ans * 100 / total_ans_4_que) if total_ans_4_que > 0 else 0
                    option_list.append({
                        "optionVal": opt.soptValue,
                        "totalAns": total_ans,
                        "perColor": per_color
                    })
                question_data['optionList'] = option_list
                questions_list.append(question_data)
                
            elif question.squeType == "matrix":
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['question'] = question.squeQuestion
                answers = SurveysAnswers.objects.filter(sansSqueId=question.squeId).values_list('sansAnswers', flat=True)
                total_ans_4_que = len(answers)
                question_data['totalAnsForQues'] = total_ans_4_que
                question_data['queTypeId'] = 3
                
                rows_list = SurveysOptions.objects.filter(soptSqueId=question.squeId)
                columns_list = SurveysOptionsColumns.objects.filter(soptSqueId=question.squeId)
                rows = []
                for row_data in rows_list:
                    rows.append(row_data.soptValue)
                    option_list = []
                    for col_data in columns_list:
                        total_ans = 0
                        for ans_str in answers:
                            try:
                                ans_json = json.loads(ans_str).get('value', {})
                                if row_data.soptValue in ans_json and col_data.soptValue in str(ans_json.get(row_data.soptValue)):
                                    total_ans += 1
                            except: continue
                        per_color = round(total_ans * 100 / total_ans_4_que) if total_ans_4_que > 0 else 0
                        option_list.append({
                            "optionVal": col_data.soptValue,
                            "totalAns": total_ans,
                            "perColor": per_color
                        })
                    question_data[row_data.soptValue] = option_list
                question_data['rows'] = rows
                questions_list.append(question_data)
                
            elif question.squeType in rating_type:
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['question'] = question.squeQuestion
                answers = SurveysAnswers.objects.filter(sansSqueId=question.squeId).values_list('sansAnswers', flat=True)
                total_ans_4_que = len(answers)
                
                ratings_number = 10
                if question.squeType == "rating_symbol":
                    opt = SurveysOptions.objects.filter(soptSqueId=question.squeId).first()
                    ratings_number = int(opt.soptValue) if opt else 10
                
                question_data['totalAnsForQues'] = total_ans_4_que
                question_data['queTypeId'] = 1
                option_list = []
                for i in range(1, ratings_number + 1):
                    total_ans = 0
                    for ans_str in answers:
                        try:
                            if json.loads(ans_str).get('value') == i:
                                total_ans += 1
                        except: continue
                    per_color = round(total_ans * 100 / total_ans_4_que) if total_ans_4_que > 0 else 0
                    option_list.append({
                        "optionVal": i,
                        "totalAns": total_ans,
                        "perColor": per_color
                    })
                question_data['optionList'] = option_list
                questions_list.append(question_data)
                
            elif question.squeType == "consent_agreement":
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['question'] = question.squeQuestion
                total_ans_4_que = SurveysStatistics.objects.filter(ssSryId=sry_id).count()
                total_agree = SurveysAnswers.objects.filter(sansSqueId=question.squeId).count()
                total_disagree = total_ans_4_que - total_agree
                
                option_list = []
                per_color_agree = round(total_agree * 100 / total_ans_4_que) if total_ans_4_que > 0 else 0
                option_list.append({"optionVal": "Agree", "totalAns": total_agree, "perColor": per_color_agree})
                
                per_color_disagree = round(total_disagree * 100 / total_ans_4_que) if total_ans_4_que > 0 else 0
                option_list.append({"optionVal": "Disagree", "totalAns": total_disagree, "perColor": per_color_disagree})
                
                question_data['totalAnsForQues'] = total_ans_4_que
                question_data['queTypeId'] = 1
                question_data['optionList'] = option_list
                questions_list.append(question_data)
                
            elif question.squeType == "rank":
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['question'] = question.squeQuestion
                answers = SurveysAnswers.objects.filter(sansSqueId=question.squeId).values_list('sansAnswers', flat=True)
                total_ans_4_que = len(answers)
                
                option_list = []
                if total_ans_4_que > 0:
                    try:
                        lbl_arr = json.loads(answers[0]).get('value', [])
                        avg_score = {lbl: 0.0 for lbl in lbl_arr}
                        num_labels = len(lbl_arr)
                        for ans_str in answers:
                            ans_arr = json.loads(ans_str).get('value', [])
                            temp = num_labels
                            for val in ans_arr:
                                if val in avg_score:
                                    avg_score[val] += (temp / num_labels)
                                    temp -= 1
                        
                        for lbl in lbl_arr:
                            per_color = round(avg_score[lbl] * 100 / total_ans_4_que) if total_ans_4_que > 0 else 0
                            option_list.append({"optionVal": lbl, "perColor": per_color})
                    except: pass
                
                question_data['optionList'] = option_list
                question_data['totalAnsForQues'] = total_ans_4_que
                question_data['queTypeId'] = 1
                questions_list.append(question_data)
                
            elif question.squeType == "constant_sum":
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['question'] = question.squeQuestion
                answers_objs = SurveysAnswers.objects.filter(sansSqueId=question.squeId)
                options = get_constant_sum_questions(survey.sryData, question.squeId)
                
                avg_total = {opt: 0.0 for opt in options}
                avg_percent_total = {opt: 0.0 for opt in options}
                
                if answers_objs.exists():
                    for ans_obj in answers_objs:
                        try:
                            ans_json = json.loads(ans_obj.sansAnswers).get('value', {}).get('questions', {})
                            option_sum = sum([ans_json.get(opt, 0.0) for opt in options])
                            for opt in options:
                                val = ans_json.get(opt, 0.0)
                                avg_total[opt] += val
                                if option_sum > 0:
                                    avg_percent_total[opt] += (val * 100 / option_sum)
                        except: continue
                        
                    option_list = []
                    num_ans = answers_objs.count()
                    for opt in options:
                        per_color = round(avg_percent_total[opt] / num_ans)
                        option_list.append({
                            "optionVal": opt,
                            "totalAns": f"{round(avg_total[opt] / num_ans):,}",
                            "perColor": per_color
                        })
                    question_data['optionList'] = option_list
                else:
                    question_data['optionList'] = [{"optionVal": opt, "perColor": 0.0, "totalAns": 0} for opt in options]
                
                question_data['totalAnsForQues'] = answers_objs.count()
                question_data['queTypeId'] = 6
                questions_list.append(question_data)
                
            que_count += 1
            
        res_body['questions'] = questions_list
        return api_response(status.HTTP_200_OK, "Survey Questions Report Fetched Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSurveyReportQuestions Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyReportTextAnswers(request):
    res_body = dict()
    text_answers_list = []
    member_id = get_final_tenant_id(request=request)
    sry_id_enc = request.query_params.get('sryId')
    
    try:
        sry_id = int(DecryptString.set_enc_dec_user(sry_id_enc, "display", "Y"))
        survey = Surveys.objects.get(sryId=sry_id)
        res_body['surveyName'] = survey.sryName
        
        text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
        
        que_count = 1
        questions = SurveysQuestions.objects.filter(squeSpgId__in=SurveysPages.objects.filter(spgSryId=sry_id).values_list('spgId', flat=True)).order_by('squeDisplayOrder')
        
        for question in questions:
            question_data = {}
            if question.squeType in text_answers_type:
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['queTypeId'] = 2
                question_data['question'] = question.squeQuestion
                
                answers = SurveysAnswers.objects.filter(sansSqueId=question.squeId)
                option_list = []
                for ans in answers:
                    try:
                        temp_json = json.loads(ans.sansAnswers)
                        if question.squeType == "phone":
                            val = temp_json.get('value', {})
                            phone = f"{val.get('countryCode', '')} {val.get('PhoneNo', '')}"
                            option_list.append({"optionVal": phone})
                        else:
                            option_list.append({"optionVal": temp_json.get('value')})
                    except: continue
                question_data['optionList'] = option_list
                text_answers_list.append(question_data)
                
            elif question.squeType == "contact_form":
                question_data['queId'] = question.squeId
                question_data['disOrder'] = que_count
                question_data['queTypeId'] = 4
                question_data['question'] = question.squeQuestion
                
                answers_strs = SurveysAnswers.objects.filter(sansSqueId=question.squeId).values_list('sansAnswers', flat=True)
                lbls = []
                response_list = []
                if answers_strs:
                    try:
                        first_ans = json.loads(answers_strs[0]).get('value', {})
                        labels = list(first_ans.keys())
                        lbls = labels
                        for ans_str in answers_strs:
                            try:
                                ans_val = json.loads(ans_str).get('value', {})
                                response = {lbl: ans_val.get(lbl, "") for lbl in labels}
                                response_list.append(response)
                            except: continue
                    except: pass
                
                question_data['lables'] = lbls
                question_data['optionList'] = response_list
                text_answers_list.append(question_data)
                
            elif question.squeType == "matrix" and get_matrix_type(survey.sryData, question.squeId) == 3:
                question_data['queTypeId'] = 5
                question_data['question'] = question.squeQuestion
                question_data['disOrder'] = que_count
                question_data['queId'] = question.squeId
                
                answers_strs = SurveysAnswers.objects.filter(sansSqueId=question.squeId).values_list('sansAnswers', flat=True)
                rows = get_matrix_rows(survey.sryData, question.squeId)
                cols = get_matrix_columns(survey.sryData, question.squeId)
                
                option_list = []
                for ans_str in answers_strs:
                    try:
                        ans_json = json.loads(ans_str).get('value', {})
                        response = {}
                        for row in rows:
                            column_list = []
                            row_json = ans_json.get(row, {})
                            for col in cols:
                                column_list.append({
                                    "label": col,
                                    "optVal": row_json.get(col, "")
                                })
                            response[row] = column_list
                        option_list.append(response)
                    except: continue
                
                question_data['rows'] = rows
                question_data['columns'] = cols
                question_data['optionList'] = option_list
                text_answers_list.append(question_data)
                
            que_count += 1
            
        res_body['textAnswers'] = text_answers_list
        return api_response(status.HTTP_200_OK, "Survey Text Answers Report Fetched Successfully.", res_body)
        
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSurveyReportTextAnswers Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyReportQuestionsComboList(request):
    res_body = {}
    try:
        sry_id_enc = request.query_params.get('sryId')
        sry_id = int(DecryptString.set_enc_dec_user(sry_id_enc, "display", "Y"))
        
        questions = SurveysQuestions.objects.filter(squeSpgId__in=SurveysPages.objects.filter(spgSryId=sry_id).values_list('spgId', flat=True)).order_by('squeDisplayOrder')
        questions_data = [{"queId": q.squeId, "question": q.squeQuestion} for q in questions]
        
        res_body['questions'] = questions_data
        return api_response(status.HTTP_200_OK, "Survey Report Question Combo List Fetched Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {request.user.id} ] GetSurveyReportQuestionsComboList Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyReportAnswersComboList(request):
    res_body = dict()
    member_id = get_final_tenant_id(request=request)
    que_id = request.query_params.get('queId')
    sry_id_enc = request.query_params.get('sryId')
    
    try:
        sry_id = int(DecryptString.set_enc_dec_user(sry_id_enc, "display", "Y"))
        survey = Surveys.objects.get(sryId=sry_id)
        question = SurveysQuestions.objects.filter(squeId=que_id).first()
        if not question:
            return api_response(status.HTTP_200_OK, "Survey Report Answer Combo List Fetched Successfully.", res_body)
        
        text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
        option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
        rating_type = ["rating_box", "rating_radio", "rating_symbol"]
        
        if question.squeType in text_answers_type:
            answers = []
            ans_objs = SurveysAnswers.objects.filter(sansSqueId=que_id)
            for ans in ans_objs:
                try:
                    val = json.loads(ans.sansAnswers).get('value')
                    if question.squeType == "phone":
                        phone = f"{val.get('countryCode', '')} {val.get('PhoneNo', '')}"
                        answers.append(phone)
                    else:
                        answers.append(val)
                except: continue
            res_body['answers'] = list(set(answers))
            res_body['queTypeId'] = 1
            
        elif question.squeType in option_type:
            opts = SurveysOptions.objects.filter(soptSqueId=que_id).values_list('soptValue', flat=True)
            res_body['queTypeId'] = 2
            res_body['answers'] = list(opts)
            
        elif question.squeType == "matrix":
            rows_list = SurveysOptions.objects.filter(soptSqueId=que_id)
            cols_list = SurveysOptionsColumns.objects.filter(soptSqueId=que_id)
            rows = [r.soptValue for r in rows_list]
            
            if get_matrix_type(survey.sryData, question.squeId) != 3:
                for row in rows_list:
                    res_body[row.soptValue] = [c.soptValue for c in cols_list]
                res_body['rows'] = rows
                res_body['queTypeId'] = 3
            else:
                ans_strs = SurveysAnswers.objects.filter(sansSqueId=que_id).values_list('sansAnswers', flat=True)
                for row in rows_list:
                    col_details = {}
                    for col in cols_list:
                        responses = []
                        for ans_str in ans_strs:
                            try:
                                ans_json = json.loads(ans_str).get('value', {})
                                if row.soptValue in ans_json and col.soptValue in ans_json.get(row.soptValue, {}):
                                    responses.append(ans_json.get(row.soptValue).get(col.soptValue))
                            except: continue
                        col_details[col.soptValue] = responses
                    res_body[row.soptValue] = col_details
                res_body['rows'] = rows
                res_body['columns'] = [c.soptValue for c in cols_list]
                res_body['queTypeId'] = 5
                
        elif question.squeType in rating_type:
            ratings_number = 10
            if question.squeType == "rating_symbol":
                opt = SurveysOptions.objects.filter(soptSqueId=que_id).first()
                ratings_number = int(opt.soptValue) if opt else 10
            res_body['queTypeId'] = 1
            res_body['answers'] = [str(i) for i in range(1, ratings_number + 1)]
            
        elif question.squeType == "consent_agreement":
            res_body['queTypeId'] = 1
            res_body['answers'] = ["Agree", "Disagree"]
            
        elif question.squeType == "contact_form":
            ans_strs = SurveysAnswers.objects.filter(sansSqueId=que_id).values_list('sansAnswers', flat=True)
            if ans_strs:
                try:
                    val = json.loads(ans_strs[0]).get('value', {})
                    labels = list(val.keys())
                    res_body['labels'] = labels
                    for lbl in labels:
                        lbl_answers = []
                        for ans_str in ans_strs:
                            try:
                                ans_val = json.loads(ans_str).get('value', {}).get(lbl)
                                if ans_val: lbl_answers.append(ans_val)
                            except: continue
                        res_body[lbl] = list(set(lbl_answers))
                    res_body['queTypeId'] = 4
                except: pass
                
        elif question.squeType == "rank":
            ans_strs = SurveysAnswers.objects.filter(sansSqueId=que_id).values_list('sansAnswers', flat=True)
            if ans_strs:
                try:
                    res_body['answers'] = json.loads(ans_strs[0]).get('value', [])
                except: pass
            res_body['queTypeId'] = 1
            
        elif question.squeType == "constant_sum":
            ans_strs = SurveysAnswers.objects.filter(sansSqueId=que_id).values_list('sansAnswers', flat=True)
            if ans_strs:
                try:
                    val = json.loads(ans_strs[0]).get('value', {}).get('questions', {})
                    rows = list(val.keys())
                    res_body['rows'] = rows
                    for row in rows:
                        row_answers = []
                        for ans_str in ans_strs:
                            try:
                                ans_val = json.loads(ans_str).get('value', {}).get('questions', {}).get(row)
                                if ans_val is not None: row_answers.append(str(ans_val))
                            except: continue
                        res_body[row] = list(set(row_answers))
                except: pass
            else:
                res_body['rows'] = []
            res_body['queTypeId'] = 6
        return api_response(status.HTTP_200_OK, "Survey Report Answer Combo List Fetched Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSurveyReportAnswersComboList Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def surveyReportDataBrowser(request):
    res_body = dict()
    member_id = get_final_tenant_id(request=request)
    data = request.data
    sry_id_enc = data.get('sryId')
    
    try:
        sry_id = int(DecryptString.set_enc_dec_user(sry_id_enc, "display", "Y"))
        survey = Surveys.objects.get(sryId=sry_id)
        res_body['surveyName'] = survey.sryName
        res_body['countryList'] = get_country_list(sry_id)
        
        participant_id = data.get('participantId')
        question_type = data.get('questionType', 1)
        control_types = data.get('controlTypes', [])
        question_numbers = data.get('questionNumbers', [])
        que_ans_list = data.get('queAnsList', [])
        
        if participant_id and participant_id != 0:
            ss_ans_ids = [participant_id]
        else:
            ss_ans_ids = get_statistics_id(que_ans_list, sry_id)

        questions_list = []
        q_list = filter_by_questions_type(question_type, sry_id)
        q_list = filter_by_control_type(control_types, q_list)
        if question_numbers:
            q_list = [q for q in q_list if q.squeId in question_numbers]
            
        option_type_tags = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
        text_answers_type_tags = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
        rating_type_tags = ["rating_box", "rating_radio", "rating_symbol"]

        que_count = 1
        if ss_ans_ids:
            for question in q_list:
                question_data = {
                    "queId": question.squeId,
                    "disOrder": que_count,
                    "question": question.squeQuestion
                }
                
                if question.squeType in text_answers_type_tags:
                    question_data['queTypeId'] = 2
                    answers_list = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids).values_list('sansAnswers', flat=True)
                    option_list = []
                    for ans_str in answers_list:
                        try:
                            temp_json = json.loads(ans_str)
                            if question.squeType == "phone":
                                val = temp_json.get('value', {})
                                phone = f"{val.get('countryCode', '')} {val.get('PhoneNo', '')}"
                                option_list.append({"optionVal": phone})
                            else:
                                option_list.append({"optionVal": temp_json.get('value')})
                        except: continue
                    question_data['optionList'] = option_list
                    
                elif question.squeType in option_type_tags:
                    ans_data = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids)
                    answers_json_strings = [a.sansAnswers for a in ans_data]
                    comments_json_strings = [a.sansComments for a in ans_data]
                    
                    total_ans_for_que = len(answers_json_strings)
                    question_data['totalAnsForQues'] = total_ans_for_que
                    question_data['queTypeId'] = 1
                    
                    option_list = []
                    if question.squeType in ["image_form", "image_with_text_form"]:
                        img_opts = get_image_options(survey.sryData, question.squeId)
                        for opt_val, opt_desc in img_opts:
                            total_ans = sum(1 for s in answers_json_strings if opt_val in s)
                            per_color = round(total_ans * 100 / total_ans_for_que) if total_ans_for_que > 0 else 0
                            option_list.append({
                                "optionVal": opt_val,
                                "totalAns": total_ans,
                                "perColor": per_color,
                                "optionDescription": opt_desc
                            })
                    else:
                        surveys_options = SurveysOptions.objects.filter(soptSqueId=question.squeId)
                        for opt in surveys_options:
                            total_ans = sum(1 for s in answers_json_strings if opt.soptValue in s)
                            comments_list = []
                            for c_json in comments_json_strings:
                                if c_json:
                                    try:
                                        c_data = json.loads(c_json)
                                        if opt.soptValue in c_data:
                                            comments_list.append(c_data[opt.soptValue])
                                    except: continue
                            
                            per_color = round(total_ans * 100 / total_ans_for_que) if total_ans_for_que > 0 else 0
                            option_data = dict()
                            option_data["optionVal"] = opt.soptValue
                            option_data["totalAns"] = total_ans
                            option_data["perColor"] = per_color
                            option_data["hasComment"] = opt.soptHasComments == 1
                            if opt.soptHasComments == 1:
                                option_data["comments"] = comments_list
                            option_list.append(option_data)
                    question_data['optionList'] = option_list
                    
                elif question.squeType == "matrix":
                    answers_json_strings = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids).values_list('sansAnswers', flat=True)
                    if get_matrix_type(survey.sryData, question.squeId) != 3:
                        total_ans_for_que = len(answers_json_strings)
                        question_data['totalAnsForQues'] = total_ans_for_que
                        question_data['queTypeId'] = 3
                        rows_data = SurveysOptions.objects.filter(soptSqueId=question.squeId)
                        columns_data = SurveysOptionsColumns.objects.filter(soptSqueId=question.squeId)
                        rows = []
                        for row in rows_data:
                            rows.append(row.soptValue)
                            row_option_list = []
                            for col in columns_data:
                                total_ans = 0
                                for ans_str in answers_json_strings:
                                    try:
                                        ans_val = json.loads(ans_str).get('value', {})
                                        if row.soptValue in ans_val and col.soptValue in str(ans_val.get(row.soptValue, [])):
                                            total_ans += 1
                                    except: continue
                                per_color = round(total_ans * 100 / total_ans_for_que) if total_ans_for_que > 0 else 0
                                row_option_list.append({
                                    "optionVal": col.soptValue,
                                    "totalAns": total_ans,
                                    "perColor": per_color
                                })
                            question_data[row.soptValue] = row_option_list
                        question_data['rows'] = rows
                    else:
                        question_data['queTypeId'] = 5
                        rows = get_matrix_rows(survey.sryData, question.squeId)
                        cols = get_matrix_columns(survey.sryData, question.squeId)
                        question_data['rows'] = rows
                        question_data['columns'] = cols
                        option_list = []
                        for ans_str in answers_json_strings:
                            try:
                                ans_json = json.loads(ans_str).get('value', {})
                                response = {}
                                for row in rows:
                                    col_map = {}
                                    row_json = ans_json.get(row, {})
                                    for col in cols:
                                        col_map[col] = row_json.get(col, "")
                                    response[row] = col_map
                                option_list.append(response)
                            except: continue
                        question_data['optionList'] = option_list
                        
                elif question.squeType in rating_type_tags:
                    answers_json_strings = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids).values_list('sansAnswers', flat=True)
                    ratings_number = 10
                    if question.squeType == "rating_symbol":
                        opt = SurveysOptions.objects.filter(soptSqueId=question.squeId).first()
                        ratings_number = int(opt.soptValue) if opt else 10
                    
                    total_ans_for_que = len(answers_json_strings)
                    question_data['totalAnsForQues'] = total_ans_for_que
                    question_data['queTypeId'] = 1
                    option_list = []
                    for i in range(1, ratings_number + 1):
                        total_ans = 0
                        for ans_str in answers_json_strings:
                            try:
                                if json.loads(ans_str).get('value') == i:
                                    total_ans += 1
                            except: continue
                        per_color = round(total_ans * 100 / total_ans_for_que) if total_ans_for_que > 0 else 0
                        option_list.append({
                            "optionVal": i,
                            "totalAns": total_ans,
                            "perColor": per_color
                        })
                    question_data['optionList'] = option_list
                    
                elif question.squeType == "consent_agreement":
                    total_ans_for_que = len(ss_ans_ids)
                    total_agree = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids).count()
                    total_disagree = total_ans_for_que - total_agree
                    option_list = []
                    per_color_agree = round(total_agree * 100 / total_ans_for_que) if total_ans_for_que > 0 else 0
                    option_list.append({"optionVal": "Agree", "totalAns": total_agree, "perColor": per_color_agree})
                    per_color_disagree = round(total_disagree * 100 / total_ans_for_que) if total_ans_for_que > 0 else 0
                    option_list.append({"optionVal": "Disagree", "totalAns": total_disagree, "perColor": per_color_disagree})
                    question_data['totalAnsForQues'] = total_ans_for_que
                    question_data['queTypeId'] = 1
                    question_data['optionList'] = option_list
                    
                elif question.squeType == "contact_form":
                    question_data['queTypeId'] = 4
                    ans_data = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids).values_list('sansAnswers', flat=True)
                    lbls = []
                    option_list = []
                    if ans_data:
                        lbls = get_labels_for_contact_form(survey.sryData, question.squeId)
                        for ans_str in ans_data:
                            try:
                                ans_json = json.loads(ans_str).get('value', {})
                                response = {}
                                for lbl in lbls:
                                    response[lbl] = ans_json.get(lbl, "")
                                option_list.append(response)
                            except: continue
                    question_data['labels'] = lbls
                    question_data['optionList'] = option_list
                    
                elif question.squeType == "rank":
                    ans_data = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids).values_list('sansAnswers', flat=True)
                    total_ans_for_que = len(ans_data)
                    option_list = []
                    if total_ans_for_que > 0:
                        try:
                            first_ans = json.loads(ans_data[0]).get('value', [])
                            avg_score = {lbl: 0.0 for lbl in first_ans}
                            num_labels = len(first_ans)
                            for ans_str in ans_data:
                                ans_arr = json.loads(ans_str).get('value', [])
                                temp = num_labels
                                for lbl in ans_arr:
                                    if lbl in avg_score:
                                        avg_score[lbl] += (temp / num_labels)
                                        temp -= 1
                            for lbl in first_ans:
                                per_color = round(avg_score[lbl] * 100 / total_ans_for_que) if total_ans_for_que > 0 else 0
                                option_list.append({
                                    "optionVal": lbl,
                                    "totalAns": round(avg_score[lbl]),
                                    "perColor": per_color
                                })
                        except: pass
                    question_data['optionList'] = option_list
                    question_data['totalAnsForQues'] = total_ans_for_que
                    question_data['queTypeId'] = 1
                    
                elif question.squeType == "constant_sum":
                    ans_objs = SurveysAnswers.objects.filter(sansSqueId=question.squeId, sansSsId__in=ss_ans_ids)
                    opts = get_constant_sum_questions(survey.sryData, question.squeId)
                    avg_total = {opt: 0.0 for opt in opts}
                    avg_percent_total = {opt: 0.0 for opt in opts}
                    
                    if ans_objs.exists():
                        for ans_obj in ans_objs:
                            try:
                                ans_json = json.loads(ans_obj.sansAnswers).get('value', {}).get('questions', {})
                                option_sum = sum([float(ans_json.get(opt, 0)) for opt in opts])
                                for opt in opts:
                                    val = float(ans_json.get(opt, 0))
                                    avg_total[opt] += val
                                    if option_sum > 0:
                                        avg_percent_total[opt] += (val * 100 / option_sum)
                            except: continue
                        
                        option_list = []
                        num_ans = ans_objs.count()
                        for opt in opts:
                            per_color = round(avg_percent_total[opt] / num_ans)
                            option_list.append({
                                "optionVal": opt,
                                "totalAns": f"{round(avg_total[opt] / num_ans):,}",
                                "perColor": per_color
                            })
                        question_data['optionList'] = option_list
                    else:
                        question_data['optionList'] = []
                    question_data['totalAnsForQues'] = ans_objs.count()
                    question_data['queTypeId'] = 6
                    
                questions_list.append(question_data)
                que_count += 1
        else:
            for question in q_list:
                question_data = {
                    "queId": question.squeId,
                    "disOrder": que_count,
                    "question": question.squeQuestion
                }
                if question.squeType in text_answers_type_tags:
                    question_data['queTypeId'] = 2
                    question_data['optionList'] = []
                elif question.squeType in option_type_tags:
                    question_data['totalAnsForQues'] = 0
                    question_data['queTypeId'] = 1
                    surveys_options = SurveysOptions.objects.filter(soptSqueId=question.squeId)
                    option_list = []
                    for opt in surveys_options:
                        option_list.append({
                            "optionVal": opt.soptValue,
                            "totalAns": 0,
                            "perColor": 0,
                            "hasComment": opt.soptHasComments == 1,
                            "comments": [] if opt.soptHasComments == 1 else None
                        })
                    question_data['optionList'] = option_list
                elif question.squeType == "matrix":
                    if get_matrix_type(survey.sryData, question.squeId) != 3:
                        question_data['totalAnsForQues'] = 0
                        question_data['queTypeId'] = 3
                        rows_data = SurveysOptions.objects.filter(soptSqueId=question.squeId)
                        columns_data = SurveysOptionsColumns.objects.filter(soptSqueId=question.squeId)
                        rows = []
                        for row in rows_data:
                            rows.append(row.soptValue)
                            row_option_list = []
                            for col in columns_data:
                                row_option_list.append({
                                    "optionVal": col.soptValue,
                                    "totalAns": 0,
                                    "perColor": 0
                                })
                            question_data[row.soptValue] = row_option_list
                        question_data['rows'] = rows
                    else:
                        question_data['queTypeId'] = 5
                        question_data['optionList'] = []
                elif question.squeType in rating_type_tags:
                    question_data['totalAnsForQues'] = 0
                    question_data['queTypeId'] = 1
                    ratings_number = 10
                    if question.squeType == "rating_symbol":
                        opt = SurveysOptions.objects.filter(soptSqueId=question.squeId).first()
                        ratings_number = int(opt.soptValue) if opt else 10
                    option_list = []
                    for i in range(1, ratings_number + 1):
                        option_list.append({"optionVal": i, "totalAns": 0, "perColor": 0})
                    question_data['optionList'] = option_list
                elif question.squeType == "consent_agreement":
                    question_data['queTypeId'] = 1
                    question_data['optionList'] = [
                        {"optionVal": "Agree", "totalAns": 0, "perColor": 0},
                        {"optionVal": "Disagree", "totalAns": 0, "perColor": 0}
                    ]
                elif question.squeType == "contact_form":
                    question_data['queTypeId'] = 4
                    question_data['optionList'] = []
                elif question.squeType == "rank":
                    question_data['totalAnsForQues'] = 0
                    question_data['queTypeId'] = 1
                    question_data['optionList'] = []
                elif question.squeType == "constant_sum":
                    opts = get_constant_sum_questions(survey.sryData, question.squeId)
                    question_data['optionList'] = [{"optionVal": opt, "perColor": 0.0, "totalAns": 0} for opt in opts]
                    question_data['totalAnsForQues'] = 0
                    question_data['queTypeId'] = 6
                
                questions_list.append(question_data)
                que_count += 1

        res_body['questions'] = questions_list
        return api_response(status.HTTP_200_OK, "Survey Data Browser Fetched Successfully.", res_body)
        
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] SurveyReportDataBrowser Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyReportParticipant(request):
    res_body = dict()
    member_id = get_final_tenant_id(request=request)
    participant_id = request.query_params.get('participantId')
    
    try:
        stat = SurveysStatistics.objects.get(ssId=participant_id)
        res_body['participantInfo'] = {
            "participantId": stat.ssId,
            "ipAddress": stat.ssIpAddress,
            "date": stat.ssDate.strftime("%m-%d-%Y %H:%M:%S"),
            "city": stat.ssCity,
            "state": stat.ssState,
            "country": stat.ssCountry,
            "technology": stat.ssTechnology,
            "sources": stat.ssSources,
            "isComplete": stat.ssIsComplete
        }
        
        ans_data = SurveysAnswers.objects.filter(sansSsId=stat.ssId)
        responses = []
        for ans in ans_data:
            question = SurveysQuestions.objects.filter(squeId=ans.sansSqueId).first()
            if not question: continue
            
            try:
                ans_val = json.loads(ans.sansAnswers).get('value')
                if question.squeType == "phone":
                    ans_val = f"{ans_val.get('countryCode', '')} {ans_val.get('PhoneNo', '')}"
                elif question.squeType == "contact_form":
                    ans_val = ", ".join([f"{k}: {v}" for k, v in ans_val.items()])
                elif question.squeType == "matrix":
                    ans_val = str(ans_val)
                elif question.squeType == "rank":
                    ans_val = ", ".join(ans_val)
                elif question.squeType == "constant_sum":
                    ans_val = str(ans_val.get('questions', {}))
            except:
                ans_val = ans.sansAnswers
                
            responses.append({
                "question": question.squeQuestion,
                "answer": ans_val
            })
        res_body['responses'] = responses
        
        return api_response(status.HTTP_200_OK, "Survey Participant Data Fetched Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSurveyReportParticipant Error : {e}")
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error", res_body)
