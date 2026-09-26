import json
from rest_framework.views import APIView
from common_app.custom_permissions import WhitelistPermission
from django.db.models import Count, Sum
from assessment_app.models import Assessments, AssessmentsAnswers, AssessmentsOptions, AssessmentsOptionsColumns, AssessmentsQuestions, AssessmentsStatistics
from common_app.utils import api_response
from common_app.decrypt_string import DecryptString
from django.db import connection

class AssessmentReportViewsHelper:
    @staticmethod
    def get_matrix_type(assessment_data, que_id):
        try:
            data = json.loads(assessment_data)
            for page in data.get("assessmentsPages", []):
                if page.get("apgType") == "Question Page":
                    for q in page.get("assessmentsQuestions", []):
                        if q.get("aqueId") == que_id:
                            return int(q.get("answerType", 0))
        except:
            pass
        return 0

    @staticmethod
    def get_matrix_rows(assessment_data, que_id):
        rows = []
        try:
            data = json.loads(assessment_data)
            for page in data.get("assessmentsPages", []):
                if page.get("apgType") == "Question Page":
                    for q in page.get("assessmentsQuestions", []):
                        if q.get("aqueId") == que_id:
                            for row in q.get("rows", []):
                                rows.append(row.get("aoptValue"))
        except:
            pass
        return rows

    @staticmethod
    def get_matrix_columns(assessment_data, que_id):
        cols = []
        try:
            data = json.loads(assessment_data)
            for page in data.get("assessmentsPages", []):
                if page.get("apgType") == "Question Page":
                    for q in page.get("assessmentsQuestions", []):
                        if q.get("aqueId") == que_id:
                            for col in q.get("columns", []):
                                cols.append(col.get("aoptValue"))
        except:
            pass
        return cols

    @staticmethod
    def get_labels_for_contact_form(assessment_data, que_id):
        labels = []
        try:
            data = json.loads(assessment_data)
            for page in data.get("assessmentsPages", []):
                if page.get("apgType") == "Question Page":
                    for q in page.get("assessmentsQuestions", []):
                        if q.get("aqueId") == que_id:
                            for lbl in q.get("labelList", []):
                                labels.append(lbl.get("name"))
        except:
            pass
        return labels

    @staticmethod
    def get_constant_sum_questions(assessment_data, que_id):
        questions = []
        try:
            data = json.loads(assessment_data)
            for page in data.get("assessmentsPages", []):
                if page.get("apgType") == "Question Page":
                    for q in page.get("assessmentsQuestions", []):
                        if q.get("aqueId") == que_id:
                            questions = q.get("labelList", [])
        except:
            pass
        return questions

    @staticmethod
    def get_country_list(stats):
        country_wise = stats.values('as_country').annotate(count=Count('as_id'))
        country_list = []
        for country_data in country_wise:
            c_name = country_data['as_country'] or "Not Determinable"
                
            state_wise = stats.filter(as_country=country_data['as_country']).values('as_state').annotate(count=Count('as_id'))
            state_list = []
            for state_data in state_wise:
                s_name = state_data['as_state'] or "Not Determinable"
                    
                city_wise = stats.filter(as_country=country_data['as_country'], as_state=state_data['as_state']).values('as_city').annotate(count=Count('as_id'))
                city_list = [{"cityName": c['as_city'] or "Not Determinable", "visit": str(c['count'])} for c in city_wise]
                
                state_list.append({"stateName": s_name, "visit": str(state_data['count']), "cityList": city_list})
            
            country_list.append({"countryName": c_name, "visit": str(country_data['count']), "stateList": state_list})
        return country_list

    @staticmethod
    def getImageOptions(assessment_data, que_id):
        options = []
        try:
            data = json.loads(assessment_data)
            for page in data.get("assessmentsPages", []):
                if page.get("apgType") == "Question Page":
                    for q in page.get("assessmentsQuestions", []):
                        if q.get("aqueId") == que_id:
                            for opt in q.get("assessmentsOptions", []):
                                options.append([opt.get("aoptValue"), opt.get("aoptDescription", "")])
                            break
        except: pass
        return options

    @staticmethod
    def filterByQuestionsType(question_type, assessment_id):
        option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
        text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
        rating_type = ["rating_box", "rating_radio", "rating_symbol"]
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT AQ_QUE_ID FROM ASSESSMENTS_QUESTIONS WHERE AQ_PAGE_ID IN (SELECT AP_ID FROM ASSESSMENTS_PAGES WHERE AP_ASS_ID = %s)", [assessment_id])
            aque_ids = [row[0] for row in cursor.fetchall()]
        
        question_list = AssessmentsQuestions.objects.filter(aq_que_id__in=aque_ids).order_by('aq_que_id')
        
        if question_type == 1: return question_list
            
        filtered_list = []
        assessment = Assessments.objects.get(assId=assessment_id)
        if question_type == 3: # Text based
            for q in question_list:
                if q.aq_type in text_answers_type: filtered_list.append(q)
                elif q.aq_type == "matrix" and AssessmentReportViewsHelper.get_matrix_type(assessment.assData, q.aq_que_id) == 3: filtered_list.append(q)
                elif q.aq_type == "contact_form": filtered_list.append(q)
        else: # Option based
             for q in question_list:
                if q.aq_type in option_type or q.aq_type in rating_type: filtered_list.append(q)
                elif q.aq_type == "matrix" and AssessmentReportViewsHelper.get_matrix_type(assessment.assData, q.aq_que_id) != 3: filtered_list.append(q)
                elif q.aq_type in ["rank", "constant_sum", "consent_agreement"]: filtered_list.append(q)
        
        return filtered_list

    @staticmethod
    def getStatistaicsId(que_ans_list, assessment_id, assessment_data):
        option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
        text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
        rating_type = ["rating_box", "rating_radio", "rating_symbol"]
        
        stats_ids = list(AssessmentsStatistics.objects.filter(as_ass_id=assessment_id).values_list('as_id', flat=True))
        if not que_ans_list: return stats_ids
            
        for item in que_ans_list:
            que_id = item.get('queId')
            ans = str(item.get('ans'))
            try:
                question = AssessmentsQuestions.objects.get(aq_que_id=que_id)
                que_type = question.aq_type
            except: continue
                
            if not stats_ids: break
            ans_qs = AssessmentsAnswers.objects.filter(aa_aque_id=que_id, aa_as_id__in=stats_ids)
            
            if que_type in option_type:
                stats_ids = list(ans_qs.filter(aa_answers__icontains=ans).values_list('aa_as_id', flat=True))
                if not stats_ids: break
            elif que_type in text_answers_type:
                if que_type != 'phone':
                    stats_ids = list(ans_qs.filter(aa_answers__icontains=ans).values_list('aa_as_id', flat=True))
                    if not stats_ids: break
                else:
                    parts = ans.split(" ")
                    code, phone = parts[0] if len(parts) > 0 else "", parts[1] if len(parts) > 1 else ""
                    stats_ids = list(ans_qs.filter(aa_answers__icontains=code).filter(aa_answers__icontains=phone).values_list('aa_as_id', flat=True))
                    if not stats_ids: break
            elif que_type == "matrix":
                m_type = AssessmentReportViewsHelper.get_matrix_type(assessment_data, que_id)
                new_ids, ans_parts = [], ans.split("=")
                row_val = ans_parts[0] if len(ans_parts) > 0 else ans
                col_val = ans_parts[1] if len(ans_parts) > 1 else ""
                if m_type != 3:
                     for m_ans in ans_qs:
                        try:
                            val = json.loads(m_ans.aa_answers).get("value", {})
                            if col_val == "":
                                if row_val in val: new_ids.append(m_ans.aa_as_id)
                            else:
                                if row_val in val and col_val in str(val.get(row_val)): new_ids.append(m_ans.aa_as_id)
                        except: pass
                else:
                    opt_val = ans_parts[2] if len(ans_parts) > 2 else ""
                    for m_ans in ans_qs:
                        try:
                            val = json.loads(m_ans.aa_answers).get("value", {})
                            if col_val == "" and opt_val == "":
                                if row_val in val: new_ids.append(m_ans.aa_as_id)
                            elif col_val == "":
                                if row_val in val and col_val in val.get(row_val): new_ids.append(m_ans.aa_as_id)
                            else:
                                if row_val in val and col_val in val.get(row_val) and str(val.get(row_val).get(col_val)) == opt_val: new_ids.append(m_ans.aa_as_id)
                        except: pass
                stats_ids = new_ids
                if not stats_ids: break
            elif que_type in rating_type:
                new_ids = []
                for r_ans in ans_qs:
                    try:
                        if str(json.loads(r_ans.aa_answers).get("value")) == ans: new_ids.append(r_ans.aa_as_id)
                    except: pass
                stats_ids = new_ids
                if not stats_ids: break
            elif que_type == "consent_agreement":
                agree_ids = list(ans_qs.values_list('aa_as_id', flat=True))
                stats_ids = agree_ids if ans == "Agree" else [sid for sid in stats_ids if sid not in agree_ids]
                if not stats_ids: break
            elif que_type == "contact_form":
                new_ids, ans_parts = [], ans.split("=")
                lbl, val_to_match = ans_parts[0] if len(ans_parts) > 0 else ans, ans_parts[1] if len(ans_parts) > 1 else ""
                for c_ans in ans_qs:
                    try:
                        val = json.loads(c_ans.aa_answers).get("value", {})
                        if val_to_match == "":
                            if lbl in val and val.get(lbl) != "": new_ids.append(c_ans.aa_as_id)
                        elif lbl in val and str(val.get(lbl)) == val_to_match: new_ids.append(c_ans.aa_as_id)
                    except: pass
                stats_ids = new_ids
                if not stats_ids: break
            elif que_type == "constant_sum":
                new_ids, ans_parts = [], ans.split("=")
                lbl, val_to_match = ans_parts[0] if len(ans_parts) > 0 else ans, ans_parts[1] if len(ans_parts) > 1 else ""
                for cs_ans in ans_qs:
                    try:
                        val = json.loads(cs_ans.aa_answers).get("value", {}).get("questions", {})
                        if val_to_match == "": new_ids.append(cs_ans.aa_as_id)
                        elif lbl in val and str(val.get(lbl)) == val_to_match: new_ids.append(cs_ans.aa_as_id)
                    except: pass
                stats_ids = new_ids
                if not stats_ids: break
        return stats_ids

class AssessmentReportDemographicView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get(request):
        ass_id_enc = request.query_params.get('assId')
        if not ass_id_enc:
            return api_response(400, "assId is required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            assessment = Assessments.objects.get(assId=assessment_id)
            stats = AssessmentsStatistics.objects.filter(as_ass_id=assessment_id)
            
            country_wise = stats.values('as_country').annotate(count=Count('as_id'))
            country_first_list = []
            for country_data in country_wise:
                c_name = country_data['as_country'] or "Not Determinable"
                country_first_list.append({
                    "countryName": c_name,
                    "visit": str(country_data['count'])
                })

            res_body = {
                "countrySecondList": AssessmentReportViewsHelper.get_country_list(stats),
                "peopleParticipated": stats.count(),
                "assessmentName": assessment.assName,
                "countryFirstList": country_first_list
            }
            return api_response(200, "Assessment Demographic Report Fetched Successfully.", res_body)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")

class AssessmentReportTechnologyUseView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get(request):
        ass_id_enc = request.query_params.get('assId')
        if not ass_id_enc:
            return api_response(400, "assId is required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            assessment = Assessments.objects.get(assId=assessment_id)
            stats = AssessmentsStatistics.objects.filter(as_ass_id=assessment_id)
            
            def get_tech_count(tech_name):
                return stats.filter(as_technology=tech_name).count()

            tech_map = {
                "firefox": "Firefox",
                "ie": "IE",
                "iPhone": "iPhone",
                "iPad": "iPad",
                "androidPhone": "Android Phone",
                "androidTab": "Android Tab",
                "chrome": "Chrome",
                "safari": "Safari",
                "air": "Air",
                "fluid": "Fluid"
            }

            technologies = {key: get_tech_count(val) for key, val in tech_map.items()}
            
            # Others logic: count everything not in the primary list
            primary_techs = list(tech_map.values())
            technologies["others"] = stats.exclude(as_technology__in=primary_techs).count()

            res_body = {
                "assessmentName": assessment.assName,
                "technologies": technologies
            }
            return api_response(200, "Assessment Technology Use Report Fetched Successfully.", res_body)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")

class AssessmentReportQuestionsView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get(request):
        ass_id_enc = request.query_params.get('assId')
        if not ass_id_enc:
            return api_response(400, "assId is required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            assessment = Assessments.objects.get(assId=assessment_id)
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT aq_que_id FROM ASSESSMENTS_QUESTIONS WHERE aq_page_id IN (SELECT ap_id FROM ASSESSMENTS_PAGES WHERE ap_ass_id = %s)", [assessment_id])
                aque_ids = [row[0] for row in cursor.fetchall()]
            
            questions = AssessmentsQuestions.objects.filter(aq_que_id__in=aque_ids).order_by('aq_que_id')
            stats = AssessmentsStatistics.objects.filter(as_ass_id=assessment_id)
            as_ids = list(stats.values_list('as_id', flat=True))
            
            option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
            text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
            rating_type = ["rating_box", "rating_radio", "rating_symbol"]

            question_data_list = []
            for idx, q in enumerate(questions):
                q_data = dict()
                q_data["queId"] = q.aq_que_id
                q_data["disOrder"] = idx + 1
                q_data["question"] = q.aq_question
                ans_qs = AssessmentsAnswers.objects.filter(aa_aq_que_id=q.aq_que_id, aa_as_id__in=as_ids)
                total_ans_for_ques = ans_qs.count()
                q_data["totalAnsForQues"] = total_ans_for_ques

                if q.aq_type in text_answers_type:
                    q_data["queTypeId"] = 2
                    q_data["optionList"] = []
                elif q.aq_type in option_type:
                    q_data["queTypeId"] = 1
                    options = AssessmentsOptions.objects.filter(ao_que_id=q.aq_que_id)
                    opt_list = []
                    for opt in options:
                        count = ans_qs.filter(aa_answers__icontains=opt.ao_value).count()
                        per_color = round(count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0
                        opt_data = dict()
                        opt_data["optionVal"] = opt.ao_value
                        opt_data["totalAns"] = count
                        opt_data["perColor"] = per_color
                        opt_data["hasComment"] = opt.ao_has_comments == 1
                        if opt.ao_has_comments == 1:
                            opt_data["comments"] = list(ans_qs.filter(aa_answers__icontains=opt.ao_value).exclude(aa_comments__isnull=True).values_list('aa_comments', flat=True))
                        opt_list.append(opt_data)
                    q_data["optionList"] = opt_list
                elif q.aq_type == "matrix":
                    m_type = AssessmentReportViewsHelper.get_matrix_type(assessment.assData, q.aq_que_id)
                    if m_type != 3:
                        q_data["queTypeId"] = 3
                        rows = AssessmentReportViewsHelper.get_matrix_rows(assessment.assData, q.aq_que_id)
                        cols = AssessmentReportViewsHelper.get_matrix_columns(assessment.assData, q.aq_que_id)
                        q_data["rows"] = rows
                        for r in rows:
                            col_list = []
                            for c in cols:
                                count = 0
                                for ans in ans_qs:
                                    try:
                                        ans_val = json.loads(ans.aa_answers).get("value", {})
                                        if isinstance(ans_val, dict) and c in ans_val.get(r, []): count += 1
                                    except: pass
                                per_color = round(count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0
                                col_list.append({"optionVal": c, "totalAns": count, "perColor": per_color})
                            q_data[r] = col_list
                    else:
                        q_data["queTypeId"] = 5
                        q_data["optionList"] = []
                elif q.aq_type in rating_type:
                    q_data["queTypeId"] = 1
                    # Java line 830
                    if q.aq_type == "rating_symbol":
                        opt0 = AssessmentsOptions.objects.filter(ao_que_id=q.aq_que_id).first()
                        ratings_number = int(opt0.ao_value) if opt0 else 10
                    else:
                        ratings_number = 10
                    opt_list = []
                    for i in range(1, ratings_number + 1):
                        count = 0
                        for ans in ans_qs:
                            try:
                                if json.loads(ans.aa_answers).get("value") == i: count += 1
                            except: pass
                        per_color = round(count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0
                        opt_list.append({"optionVal": i, "totalAns": count, "perColor": per_color})
                    q_data["optionList"] = opt_list
                elif q.aq_type == "consent_agreement":
                    q_data["queTypeId"] = 1
                    agree_count = ans_qs.count()
                    q_data["optionList"] = [
                        {"optionVal": "Agree", "totalAns": agree_count, "perColor": round(agree_count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0},
                        {"optionVal": "Disagree", "totalAns": total_ans_for_ques - agree_count, "perColor": round((total_ans_for_ques - agree_count) * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0}
                    ]
                elif q.aq_type == "contact_form":
                    q_data["queTypeId"] = 4
                    labels = AssessmentReportViewsHelper.get_labels_for_contact_form(assessment.assData, q.aq_que_id)
                    q_data["labels"] = labels
                    opt_list = []
                    for ans in ans_qs:
                        try:
                            val = json.loads(ans.aa_answers).get("value", {})
                            opt_list.append(val)
                        except: pass
                    q_data["optionList"] = opt_list
                elif q.aq_type == "rank":
                    q_data["queTypeId"] = 1
                    # Simplified rank avg logic line 888-919
                    opt_list = []
                    if total_ans_for_ques > 0:
                        try:
                            ans = ans_qs.first()
                            if ans:
                                first_ans = json.loads(ans.aa_answers).get("value", [])
                            else:
                                first_ans = []
                            for lbl in first_ans:
                                opt_list.append({"optionVal": lbl, "totalAns": 0, "perColor": 0})
                        except: pass
                    q_data["optionList"] = opt_list
                elif q.aq_type == "constant_sum":
                    q_data["queTypeId"] = 6
                    options = AssessmentReportViewsHelper.get_constant_sum_questions(assessment.assData, q.aq_que_id)
                    opt_list = []
                    for opt in options:
                        opt_list.append({"optionVal": opt, "totalAns": "0", "perColor": 0})
                    q_data["optionList"] = opt_list

                question_data_list.append(q_data)

            res_body = {"assessmentName": assessment.assName, "peopleParticipated": stats.count(), "questions": question_data_list}
            return api_response(200, "Success", res_body)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")

class AssessmentReportTextAnswersView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get(request):
        ass_id_enc = request.query_params.get('assId')
        que_id = request.query_params.get('queId')
        if not ass_id_enc or not que_id:
            return api_response(400, "assId and queId are required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            
            as_ids = AssessmentsStatistics.objects.filter(as_ass_id=assessment_id).values_list('as_id', flat=True)
            answers = AssessmentsAnswers.objects.filter(aa_aque_id=que_id, aa_as_id__in=as_ids)

            result = []
            for ans in answers:
                try:
                    val = json.loads(ans.aa_answers).get('value')
                    if val:
                        result.append(val)
                except:
                    if ans.aa_answers:
                        result.append(ans.aa_answers)

            return api_response(200, "Success", result)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")

class AssessmentReportQuestionsComboListView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get(request):
        ass_id_enc = request.query_params.get('assId')
        if not ass_id_enc:
            return api_response(400, "assId is required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            
            with connection.cursor() as cursor:
                cursor.execute("SELECT AQ_QUE_ID, AQ_QUESTION FROM ASSESSMENTS_QUESTIONS WHERE AQ_PAGE_ID IN (SELECT AP_ID FROM ASSESSMENTS_PAGES WHERE AP_ASS_ID = %s) ORDER BY AQ_QUE_ID", [assessment_id])
                questions = {"questions":[{"queId": row[0], "question": row[1]} for row in cursor.fetchall()]}

            return api_response(200, "Assessment Report Question Combo List Fetched Successfully.", questions)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")

class AssessmentReportAnswersComboListView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get(request):
        ass_id_enc = request.query_params.get('assId')
        que_id = request.query_params.get('queId')
        if not ass_id_enc or not que_id:
            return api_response(400, "assId and queId are required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
            option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
            rating_type = ["rating_box", "rating_radio", "rating_symbol"]

            try:
                question = AssessmentsQuestions.objects.get(aq_que_id=que_id)
            except AssessmentsQuestions.DoesNotExist:
                return api_response(404, "Question not found")

            res_body = {}
            if question.aq_type in text_answers_type:
                answers_qs = AssessmentsAnswers.objects.filter(aa_aque_id=que_id)
                answers_list = []
                for ans in answers_qs:
                    try:
                        temp = json.loads(ans.aa_answers)
                        if question.aq_type == "phone":
                            val = temp.get("value", {})
                            phone = f"{val.get('countryCode', '')} {val.get('PhoneNo', '')}".strip()
                            answers_list.append(phone)
                        else:
                            answers_list.append(temp.get('value', ''))
                    except:
                        if ans.aa_answers:
                            answers_list.append(ans.aa_answers)
                res_body["answers"] = sorted(list(set(answers_list)))
                res_body["queTypeId"] = 1

            elif question.aq_type in option_type:
                options = AssessmentsOptions.objects.filter(ao_que_id=que_id)
                res_body["answers"] = [opt.ao_value for opt in options]
                res_body["queTypeId"] = 2

            elif question.aq_type == "matrix":
                assessment = Assessments.objects.get(assId=assessment_id)
                rows = AssessmentReportViewsHelper.get_matrix_rows(assessment.assData, que_id)
                cols_list = AssessmentsOptionsColumns.objects.filter(aoc_que_id=que_id)
                m_type = AssessmentReportViewsHelper.get_matrix_type(assessment.assData, que_id)
                
                if m_type != 3:
                    for r in rows:
                        res_body[r] = [c.aoc_value for c in cols_list]
                    res_body["rows"] = rows
                    res_body["queTypeId"] = 3
                else:
                    ans_qs = AssessmentsAnswers.objects.filter(aa_aque_id=que_id)
                    ans_json_list = [json.loads(a.aa_answers).get('value', {}) for a in ans_qs]
                    for r in rows:
                        col_details = {}
                        for c in cols_list:
                            responses = []
                            for val in ans_json_list:
                                if r in val and c.aoc_value in val.get(r, {}):
                                    responses.append(val.get(r).get(c.aoc_value))
                            col_details[c.aoc_value] = responses
                        res_body[r] = col_details
                    res_body["rows"] = rows
                    res_body["columns"] = [c.aoc_value for c in cols_list]
                    res_body["queTypeId"] = 5

            elif question.aq_type in rating_type:
                if question.aq_type == "rating_symbol":
                    opt0 = AssessmentsOptions.objects.filter(ao_que_id=que_id).first()
                    ratings_number = int(opt0.ao_value) if opt0 else 10
                else:
                    ratings_number = 10
                res_body["queTypeId"] = 1
                res_body["answers"] = [str(i) for i in range(1, ratings_number + 1)]

            elif question.aq_type == "consent_agreement":
                res_body["queTypeId"] = 1
                res_body["answers"] = ["Agree", "Disagree"]

            elif question.aq_type == "contact_form":
                ans_qs = AssessmentsAnswers.objects.filter(aa_aque_id=que_id)
                ans_json_list = [json.loads(a.aa_answers).get('value', {}) for a in ans_qs]
                label_list = []
                if ans_json_list:
                    # Java line 593: labels = new JSONObject(answersJsonList.get(0)).getJSONObject("value").names();
                    labels = list(ans_json_list[0].keys())
                    for lbl in labels:
                        label_list.append(lbl)
                        label_answers = []
                        for val in ans_json_list:
                            if val.get(lbl):
                                label_answers.append(val.get(lbl))
                        res_body[lbl] = sorted(list(set(label_answers)))
                    res_body["labels"] = label_list
                    res_body["queTypeId"] = 4

            elif question.aq_type == "rank":
                ans0 = AssessmentsAnswers.objects.filter(aa_aque_id=que_id).first()
                answers = []
                if ans0:
                    try:
                        labels = json.loads(ans0.aa_answers).get("value", [])
                        answers = labels
                    except: pass
                res_body["queTypeId"] = 1
                res_body["answers"] = answers

            elif question.aq_type == "constant_sum":
                ans_qs = AssessmentsAnswers.objects.filter(aa_aque_id=que_id)
                ans_json_list = [json.loads(a.aa_answers).get('value', {}).get('questions', {}) for a in ans_qs]
                if ans_json_list:
                    options = list(ans_json_list[0].keys())
                    res_body["rows"] = options
                    for opt in options:
                        temp_list = []
                        for val in ans_json_list:
                            if opt in val:
                                temp_list.append(str(val.get(opt)))
                        res_body[opt] = sorted(list(set(temp_list)))
                    res_body["queTypeId"] = 6
                else:
                    res_body["queTypeId"] = 6
                    res_body["rows"] = []

            return api_response(200, "Assessment Report Answers Combo List Fetched Successfully.", res_body)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")

class AssessmentReportDataBrowserView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def post(request):
        data = request.data
        ass_id_enc = data.get('assId')
        if not ass_id_enc:
            return api_response(400, "assId is required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            assessment = Assessments.objects.get(assId=assessment_id)
            stats = AssessmentsStatistics.objects.filter(as_ass_id=assessment_id)
            
            question_type = data.get('questionType', 1)
            control_types = data.get('controlTypes', [])
            question_numbers = data.get('questionNumbers', [])
            que_ans_list = data.get('queAnsList', [])
            participant_id = data.get('participantId', 0)

            if participant_id == 0:
                stats_ids = AssessmentReportViewsHelper.getStatistaicsId(que_ans_list, assessment_id, assessment.assData)
            else:
                stats_ids = [participant_id]

            question_list = AssessmentReportViewsHelper.filterByQuestionsType(question_type, assessment_id)
            if participant_id == 0:
                if control_types:
                    question_list = [q for q in question_list if q.aq_type in control_types]
                if question_numbers:
                    question_list = [q for q in question_list if q.aq_que_id in question_numbers]

            question_list = sorted(list(question_list), key=lambda x: x.aq_que_id)

            option_type = ["single_answer", "single_answer_checkbox", "single_answer_combo", "single_answer_button", "yes_no", "image_form", "image_with_text_form", "gender", "marital_status", "education", "employment_status", "employer_type", "housing", "household_income", "race"]
            text_answers_type = ["open_ended", "age", "date_control", "time_control", "email", "phone"]
            rating_type = ["rating_box", "rating_radio", "rating_symbol"]

            questions_data = []
            if stats_ids:
                for idx, q in enumerate(question_list):
                    q_data = dict()
                    q_data["queId"] = q.aq_que_id
                    q_data["disOrder"] = idx + 1
                    q_data["question"] = q.aq_question
                    ans_qs = AssessmentsAnswers.objects.filter(aa_aque_id=q.aq_que_id, aa_as_id__in=stats_ids)
                    total_ans_for_ques = ans_qs.count()
                    
                    if q.aq_type in text_answers_type:
                        q_data["queTypeId"] = 2
                        opt_list = []
                        for ans in ans_qs:
                            try:
                                temp = json.loads(ans.aa_answers)
                                if q.aq_type == "phone":
                                    phone = temp.get("value", {}).get("countryCode", "") + " " + temp.get("value", {}).get("PhoneNo", "")
                                    opt_list.append({"optionVal": phone})
                                else:
                                    opt_list.append({"optionVal": temp.get("value")})
                            except: pass
                        q_data["optionList"] = opt_list
                    elif q.aq_type in option_type:
                        q_data["queTypeId"] = 1
                        q_data["totalAnsForQues"] = total_ans_for_ques
                        opt_list = []
                        if q.aq_type in ["image_form", "image_with_text_form"]:
                            for img_opt in AssessmentReportViewsHelper.getImageOptions(assessment.assData, q.aq_que_id):
                                name, desc = img_opt[0], img_opt[1]
                                count = 0
                                for ans in ans_qs:
                                    if name in ans.aa_answers:
                                        count += 1
                                per = round(count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0
                                opt_list.append({"optionVal": name, "totalAns": count, "perColor": float(per), "optionDescription": desc})
                        else:
                            options = AssessmentsOptions.objects.filter(ao_que_id=q.aq_que_id)
                            for opt in options:
                                count = 0
                                for ans in ans_qs:
                                    if opt.ao_value in ans.aa_answers:
                                        count += 1
                                # Java calculates comments separately but using count calculation
                                commentsList = []
                                for ans in ans_qs:
                                    if ans.aa_comments and opt.ao_value in ans.aa_comments:
                                        try:
                                            c_temp = json.loads(ans.aa_comments)
                                            if opt.ao_value in c_temp:
                                                commentsList.append(c_temp.get(opt.ao_value))
                                        except: pass
                                
                                opt_list.append({
                                    "optionVal": opt.ao_value, "totalAns": count,
                                    "perColor": float(round(count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0),
                                    "hasComment": opt.ao_has_comments == 1,
                                    "comments": commentsList if opt.ao_has_comments == 1 else []
                                })
                        q_data["optionList"] = opt_list
                    elif q.aq_type == "matrix":
                        m_type = AssessmentReportViewsHelper.get_matrix_type(assessment.assData, q.aq_que_id)
                        if m_type != 3:
                            q_data["queTypeId"] = 3
                            q_data["totalAnsForQues"] = total_ans_for_ques
                            rows = AssessmentReportViewsHelper.get_matrix_rows(assessment.assData, q.aq_que_id)
                            cols = AssessmentReportViewsHelper.get_matrix_columns(assessment.assData, q.aq_que_id)
                            q_data["rows"] = rows
                            for r in rows:
                                col_list = []
                                for c in cols:
                                    count = 0
                                    for ans in ans_qs:
                                        try:
                                            val = json.loads(ans.aa_answers).get("value", {})
                                            if r in val and c in str(val.get(r)): count += 1
                                        except: pass
                                    col_list.append({"optionVal": c, "totalAns": count, "perColor": float(round(count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0)})
                                q_data[r] = col_list
                        else:
                            q_data["queTypeId"] = 5
                            res_list = []
                            rows, cols = AssessmentReportViewsHelper.get_matrix_rows(assessment.assData, q.aq_que_id), AssessmentReportViewsHelper.get_matrix_columns(assessment.assData, q.aq_que_id)
                            q_data["rows"], q_data["columns"] = rows, cols
                            for ans in ans_qs:
                                try:
                                    val, row_map = json.loads(ans.aa_answers).get("value", {}), {}
                                    for r in rows:
                                        row_map[r] = {c: val.get(r, {}).get(c, "") for c in cols}
                                    res_list.append(row_map)
                                except: pass
                            q_data["optionList"] = res_list
                    elif q.aq_type in rating_type:
                        q_data["queTypeId"] = 1
                        q_data["totalAnsForQues"] = total_ans_for_ques
                        if q.aq_type == "rating_symbol":
                            opt0 = AssessmentsOptions.objects.filter(ao_que_id=q.aq_que_id).first()
                            ratings_number = int(opt0.ao_value) if opt0 else 10
                        else: ratings_number = 10
                        opt_list = []
                        for i in range(1, ratings_number + 1):
                            count = 0
                            for ans in ans_qs:
                                try:
                                    if json.loads(ans.aa_answers).get("value") == i: count += 1
                                except: pass
                            opt_list.append({"optionVal": i, "totalAns": count, "perColor": float(round(count * 100 / total_ans_for_ques) if total_ans_for_ques > 0 else 0)})
                        q_data["optionList"] = opt_list
                    elif q.aq_type == "consent_agreement":
                        q_data["queTypeId"] = 1
                        total_agree_ids = len(stats_ids)
                        agree_count = ans_qs.count()
                        disagree_count = total_agree_ids - agree_count
                        q_data["totalAnsForQues"] = total_agree_ids
                        q_data["optionList"] = [
                            {"optionVal": "Agree", "totalAns": agree_count, "perColor": float(round(agree_count * 100 / total_agree_ids)) if total_agree_ids > 0 else 0.0},
                            {"optionVal": "Disagree", "totalAns": disagree_count, "perColor": float(round(disagree_count * 100 / total_agree_ids)) if total_agree_ids > 0 else 0.0}
                        ]
                    elif q.aq_type == "contact_form":
                        q_data["queTypeId"] = 4
                        q_data["labels"] = AssessmentReportViewsHelper.get_labels_for_contact_form(assessment.assData, q.aq_que_id)
                        res_list = []
                        for ans in ans_qs:
                            try:
                                temp = json.loads(ans.aa_answers).get("value", {})
                                res_list.append(temp)
                            except: pass
                        q_data["optionList"] = res_list
                    elif q.aq_type == "rank":
                        q_data["queTypeId"] = 1
                        q_data["totalAnsForQues"] = total_ans_for_ques
                        opt_list = []
                        if total_ans_for_ques > 0:
                            try:
                                ans = ans_qs.first()
                                if ans:
                                    lbl_arr = json.loads(ans.aa_answers).get("value", [])
                                else:
                                    lbl_arr = []
                                avg_score = {lbl: 0.0 for lbl in lbl_arr}
                                n = len(lbl_arr)
                                for ans in ans_qs:
                                    arr = json.loads(ans.aa_answers).get("value", [])
                                    for i, key in enumerate(arr):
                                        if key in avg_score: avg_score[key] += (n - i) / n
                                for lbl in lbl_arr:
                                    opt_list.append({"optionVal": lbl, "totalAns": int(round(avg_score[lbl])), "perColor": float(round(avg_score[lbl] * 100 / total_ans_for_ques))})
                            except: pass
                        q_data["optionList"] = opt_list
                    elif q.aq_type == "constant_sum":
                        q_data["queTypeId"] = 6
                        q_data["totalAnsForQues"] = total_ans_for_ques
                        options = AssessmentReportViewsHelper.get_constant_sum_questions(assessment.assData, q.aq_que_id)
                        if total_ans_for_ques > 0:
                            avg_total, avg_per_total = {opt: 0.0 for opt in options}, {opt: 0.0 for opt in options}
                            for ans in ans_qs:
                                try:
                                    qs = json.loads(ans.aa_answers).get("value", {}).get("questions", {})
                                    sum_val = sum(qs.get(opt, 0) for opt in options)
                                    for opt in options:
                                        val = qs.get(opt, 0)
                                        avg_total[opt] += val
                                        if sum_val > 0: avg_per_total[opt] += (val * 100 / sum_val)
                                except: pass
                            q_data["optionList"] = [{"optionVal": opt, "totalAns": f"{round(avg_total[opt]/total_ans_for_ques):,}", "perColor": float(round(avg_per_total[opt]/total_ans_for_ques))} for opt in options]
                        else:
                            q_data["optionList"] = [{"optionVal": opt, "totalAns": 0, "perColor": 0.0} for opt in options]
                    questions_data.append(q_data)
            else:
                for idx, q in enumerate(question_list):
                    q_data = dict()
                    q_data["queId"] = q.aq_que_id
                    q_data["disOrder"] = idx + 1
                    q_data["question"] = q.aq_question
                    if q.aq_type in text_answers_type:
                        q_data["queTypeId"] = 2
                        q_data["optionList"] = []
                    elif q.aq_type in option_type:
                        q_data["queTypeId"] = 1
                        q_data["totalAnsForQues"] = 0
                        opt_list = []
                        if q.aq_type in ["image_form", "image_with_text_form"]:
                            for img_opt in AssessmentReportViewsHelper.getImageOptions(assessment.assData, q.aq_que_id):
                                opt_list.append({"optionVal": img_opt[0], "totalAns": 0, "perColor": 0.0, "optionDescription": img_opt[1]})
                        else:
                            options = AssessmentsOptions.objects.filter(ao_que_id=q.aq_que_id)
                            for opt in options:
                                opt_data = dict()
                                opt_data["optionVal"] = opt.ao_value
                                opt_data["totalAns"] = 0
                                opt_data["perColor"] = 0.0
                                opt_data["hasComment"] = opt.ao_has_comments == 1
                                if opt.ao_has_comments == 1: opt_data["comments"] = []
                                opt_list.append(opt_data)
                        q_data["optionList"] = opt_list
                    elif q.aq_type == "matrix":
                        m_type = AssessmentReportViewsHelper.get_matrix_type(assessment.assData, q.aq_que_id)
                        if m_type != 3:
                            q_data["queTypeId"] = 3
                            q_data["totalAnsForQues"] = 0
                            rows = AssessmentReportViewsHelper.get_matrix_rows(assessment.assData, q.aq_que_id)
                            cols = AssessmentReportViewsHelper.get_matrix_columns(assessment.assData, q.aq_que_id)
                            q_data["rows"] = rows
                            for r in rows:
                                q_data[r] = [{"optionVal": c, "totalAns": 0, "perColor": 0.0} for c in cols]
                        else:
                            q_data["queTypeId"] = 5
                            q_data["rows"] = AssessmentReportViewsHelper.get_matrix_rows(assessment.assData, q.aq_que_id)
                            q_data["columns"] = AssessmentReportViewsHelper.get_matrix_columns(assessment.assData, q.aq_que_id)
                            q_data["optionList"] = []
                    elif q.aq_type in rating_type:
                        q_data["queTypeId"] = 1
                        q_data["totalAnsForQues"] = 0
                        if q.aq_type == "rating_symbol":
                            opt0 = AssessmentsOptions.objects.filter(ao_que_id=q.aq_que_id).first()
                            ratings_number = int(opt0.ao_value) if opt0 else 10
                        else: ratings_number = 10
                        q_data["optionList"] = [{"optionVal": i, "totalAns": 0, "perColor": 0.0} for i in range(1, ratings_number + 1)]
                    elif q.aq_type == "consent_agreement":
                        q_data["queTypeId"] = 1
                        q_data["totalAnsForQues"] = 0
                        q_data["optionList"] = [
                            {"optionVal": "Agree", "totalAns": 0, "perColor": 0.0},
                            {"optionVal": "Disagree", "totalAns": 0, "perColor": 0.0}
                        ]
                    elif q.aq_type == "contact_form":
                        q_data["queTypeId"] = 4
                        q_data["optionList"] = []
                    elif q.aq_type == "rank":
                        q_data["queTypeId"] = 1
                        q_data["totalAnsForQues"] = 0
                        opt_list = []
                        # Java tries to find any existing answer to get labels for rank
                        ans0 = AssessmentsAnswers.objects.filter(aa_aque_id=q.aq_que_id).first()
                        if ans0:
                            try:
                                lbl_arr = json.loads(ans0.aa_answers).get("value", [])
                                opt_list = [{"optionVal": lbl, "perColor": 0.0} for lbl in lbl_arr]
                            except: pass
                        q_data["optionList"] = opt_list
                    elif q.aq_type == "constant_sum":
                        q_data["queTypeId"] = 6
                        q_data["totalAnsForQues"] = 0
                        options = AssessmentReportViewsHelper.get_constant_sum_questions(assessment.assData, q.aq_que_id)
                        q_data["optionList"] = [{"optionVal": opt, "totalAns": 0, "perColor": 0.0} for opt in options]
                    questions_data.append(q_data)
            
            res_body = {
                "assessmentName": assessment.assName,
                "questions": questions_data,
                "countryList": AssessmentReportViewsHelper.get_country_list(stats)
            }
            return api_response(200, "Assessment Data Browser Fetched Successfully.", res_body)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")

class AssessmentReportParticipantView(APIView):
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get(request):
        ass_id_enc = request.query_params.get('assId')
        if not ass_id_enc:
            return api_response(400, "assId is required")

        try:
            assessment_id = int(DecryptString.set_enc_dec_user(ass_id_enc, "display", "Y"))
            assessment = Assessments.objects.get(assId=assessment_id)
            stats = AssessmentsStatistics.objects.filter(as_ass_id=assessment_id)
            
            participants_list = []
            for s in stats:
                obtained_points = AssessmentsAnswers.objects.filter(aa_as_id=s.as_id).aggregate(Sum('aa_opt_points'))['aa_opt_points__sum'] or 0
                participants_list.append({
                    "participantId": s.as_id,
                    "city": s.as_city,
                    "state": s.as_state,
                    "country": s.as_country,
                    "technology": s.as_technology,
                    "source": s.as_sources,
                    "overallPoints": f"{obtained_points}"
                })

            res_body = {
                "assessmentName": assessment.assName,
                "peopleParticipated": stats.count(),
                "participantsList": participants_list
            }
            return api_response(200, "Success", res_body)
        except Exception as e:
            return api_response(500, f"Error: {str(e)}")
