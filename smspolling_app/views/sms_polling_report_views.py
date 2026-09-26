import math
import logging
from django.db import connection, models
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.models import (SpSmsPolling, SpQuestions, SpOptions, SpReply, Country)
from common_app.utils import (api_response)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_country_image(country_name):
    """
    Returns the flag image filename for a country.
    Java: iso2.toLowerCase() + ".gif" or "noflag.png"
    """
    if not country_name:
        return "noflag.png"
    try:
        # Search by cntName or ISO2
        country = Country.objects.filter(models.Q(cntName__iexact=country_name) | models.Q(iso2__iexact=country_name)).first()
        if country and country.iso2:
            return f"{country.iso2.lower()}.gif"
    except Exception:
         pass
    return "noflag.png"

def _get_polling_id(request, data=None):
    """
    Helper to resolve the numeric iId from either 'iId' or 'sid' (rndHash).
    Handles both GET params and POST data.
    """
    i_id = request.GET.get('iId')
    sid = request.GET.get('sid')
    
    # Also check post data if provided
    if not i_id and data:
        i_id = data.get('iId')
    if not sid and data:
        sid = data.get('sid')
        
    # Check if i_id is numeric
    if i_id and str(i_id).isdigit():
        return int(i_id)
        
    # Check if sid is numeric (sometimes it's passed as sid=integer)
    if sid and str(sid).isdigit():
        return int(sid)
        
    # If it's a string, look up by rndHash
    if sid:
        polling = SpSmsPolling.objects.filter(rndHash=sid).first()
        if polling:
            return polling.iId
            
    return None


def _get_country_list(i_id):
    """
    Returns country, state, and city statistics (Java's getCountryList).
    """
    total_ask = SpReply.objects.filter(smsPollingId=i_id).values('toNo').distinct().count()
    
    countries = SpReply.objects.filter(smsPollingId=i_id).values_list('fromCountry', flat=True).distinct()
    
    country_list = []
    for from_country in countries:
        display_country = from_country if from_country else "Not Determinable"
        
        c_visit = SpReply.objects.filter(smsPollingId=i_id, fromCountry=from_country).values('toNo').distinct().count()
        c_visit_per = (c_visit * 100 / total_ask) if total_ask > 0 else 0
        country_dto = dict()
        country_dto["countryName"] = display_country
        country_dto["countryImage"] = _get_country_image(from_country)
        country_dto["visit"] = c_visit
        country_dto["visitPer"] = float(c_visit_per)
        country_dto["stateList"] = []

        from_states = SpReply.objects.filter(smsPollingId=i_id, fromCountry=from_country).values_list('fromState', flat=True).distinct()
        for from_state in from_states:
            display_state = from_state if from_state else "Not Determinable"
            
            s_visit = SpReply.objects.filter(smsPollingId=i_id, fromCountry=from_country, fromState=from_state).values('toNo').distinct().count()
            s_visit_per = (s_visit * 100 / total_ask) if total_ask > 0 else 0
            state_dto = dict()
            state_dto["stateName"] = display_state
            state_dto["visit"] = s_visit
            state_dto["visitPer"] = float(s_visit_per)
            state_dto["cityList"] = []

            from_cities = SpReply.objects.filter(smsPollingId=i_id, fromCountry=from_country, fromState=from_state).values_list('fromCity', flat=True).distinct()
            for from_city in from_cities:
                display_city = from_city if from_city else "Not Determinable"
                
                ci_visit = SpReply.objects.filter(smsPollingId=i_id, fromCountry=from_country, fromState=from_state, fromCity=from_city).values('toNo').distinct().count()
                ci_visit_per = (ci_visit * 100 / total_ask) if total_ask > 0 else 0
                
                city_dto = {
                    "cityName": display_city,
                    "visit": ci_visit,
                    "visitPer": float(ci_visit_per)
                }
                state_dto["cityList"].append(city_dto)
            
            country_dto["stateList"].append(state_dto)
        
        country_list.append(country_dto)
    
    return country_list

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingReportDemographic(request):
    res_body = {}
    try:
        i_id = _get_polling_id(request)
        if not i_id:
            return api_response(400, "iId is required", res_body)

        try:
            sp = SpSmsPolling.objects.get(iId=i_id)
        except SpSmsPolling.DoesNotExist:
            return api_response(404, "SMS Polling not found.", res_body)

        people_ask = SpReply.objects.filter(smsPollingId=i_id).values('toNo').distinct().count()
        
        participated_count = SpReply.objects.filter(smsPollingId=i_id, userReply__isnull=False).values('toNo').distinct().count()
        
        participated_per = math.ceil((participated_count * 100) / people_ask) if people_ask > 0 else 0
        
        res_body['smsPolling'] = sp.vHeading
        res_body['participatedPer'] = float(participated_per)
        res_body['peopleParticipated'] = participated_count
        res_body['peopleAsk'] = people_ask

        # countryFirstList (Only basic stats)
        country_data = _get_country_list(i_id)
        country_first_list = []
        for c in country_data:
            country_first_list.append({
                "countryName": c["countryName"],
                "countryImage": c["countryImage"],
                "visit": c["visit"],
                "visitPer": c["visitPer"]
            })
        
        res_body['countryFirstList'] = country_first_list
        res_body['countrySecondList'] = country_data
        
        return api_response(200, "Fetch SMS Polling Demographic Report Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingReportDemographic Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)

# ---------------------------------------------------------------------------

# 2. GET /smsPollingReport/getSmsPollingReportQuestions
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingReportQuestions(request):
    res_body = {}
    try:
        i_id = _get_polling_id(request)
        if not i_id:
            return api_response(400, "iId is required", res_body)

        questions = SpQuestions.objects.filter(iSmspollingId=i_id).order_by('disOrder')
        question_list_dto = []
        
        for q in questions:
            q_id = q.queId
            # Total ans for this question
            total_ans_for_que = SpReply.objects.filter(quesId=q_id, ansVal__isnull=False).exclude(ansVal='').count()
            q_dto = dict()
            q_dto["queId"] = q_id
            q_dto["disOrder"] = q.disOrder
            q_dto["question"] = q.question
            q_dto["queTypeId"] = q.queTypeId
            q_dto["totalAnsForQues"] = total_ans_for_que
            q_dto["optionList"] = []

            if q.queTypeId in (1, 2):  # Choice questions
                options = SpOptions.objects.filter(queId=q_id).order_by('optId')
                for opt in options:
                    opt_val = opt.optionVal
                    # Count total ans for this option
                    # Java: countTotalAns(queId, optionVal) -> uses LIKE %optionVal%
                    # Actually Java code uses countTotalAns(qId, optVal) which is SpReplyRepository.countTotalAns(queId, optionVal)
                    total_ans = SpReply.objects.filter(quesId=q_id, ansVal__icontains=opt_val).count()
                    
                    bar_width = (total_ans / total_ans_for_que * 100) if total_ans_for_que > 0 else 0
                    
                    opt_dto = {
                        "optionVal": opt_val,
                        "totalAns": total_ans,
                        "barWidth": round(bar_width, 2),
                        "perColor": round(bar_width, 2)
                    }
                    q_dto["optionList"].append(opt_dto)
            
            question_list_dto.append(q_dto)
            
        res_body['questionList'] = question_list_dto
        return api_response(200, "Fetch Result Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingReportQuestions Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)

# ---------------------------------------------------------------------------
# 3. GET /smsPollingReport/getSmsPollingReportTextAnswers
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingReportTextAnswers(request):
    res_body = {}
    try:
        que_id = request.GET.get('queId')
        if not que_id:
            return api_response(400, "queId is required", res_body)
        
        que_id = int(que_id)
        
        ans_vals = SpReply.objects.filter(quesId=que_id, userReply__isnull=False).values_list('ansVal', flat=True).order_by('ansVal')
        
        ans_list = [{"ansVal": val} for val in ans_vals]
        res_body['ansList'] = ans_list
        return api_response(200, "Fetch Result Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingReportTextAnswers Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)

# ---------------------------------------------------------------------------
# 4. GET /smsPollingReport/getSmsPollingReportQuestionsComboList
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingReportQuestionsComboList(request):
    res_body = {}
    try:
        i_id = _get_polling_id(request)
        if not i_id:
            return api_response(400, "iId is required", res_body)

        
        # Only Choice questions (type 1, 2)
        questions = SpQuestions.objects.filter(iSmspollingId=i_id, queTypeId__in=[1, 2]).order_by('disOrder')
        q_list = [{"queId": q.queId, "question": q.question} for q in questions]
        
        res_body['questions'] = q_list
        return api_response(200, "Fetch Result Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingReportQuestionsComboList Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)

# ---------------------------------------------------------------------------
# 5. GET /smsPollingReport/getSmsPollingReportAnswersComboList
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingReportAnswersComboList(request):
    res_body = {}
    try:
        que_id = request.GET.get('queId')
        if not que_id:
            return api_response(400, "queId is required", res_body)
        
        que_id = int(que_id)
        
        try:
            q = SpQuestions.objects.get(queId=que_id)
        except SpQuestions.DoesNotExist:
            return api_response(404, "Question not found.", res_body)

        que_type_id = q.queTypeId
        option_val_list = []

        if que_type_id == 1: # Option
            # Java: findOptionVal(queId)
            option_val_list = list(SpOptions.objects.filter(queId=que_id).order_by('optId').values_list('optionVal', flat=True))
        elif que_type_id == 2: # Text Ans
            # Java: getAnsVal(queId)
            option_val_list = list(SpReply.objects.filter(quesId=que_id).values_list('ansVal', flat=True).exclude(ansVal=None).exclude(ansVal='').distinct())

        res_body['answers'] = option_val_list
        return api_response(200, "Fetch SMS Polling Answers List Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingReportAnswersComboList Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)

# ---------------------------------------------------------------------------
# 6. POST /smsPollingReport/smsPollingReportDataBrowser
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def smsPollingReportDataBrowser(request):
    res_body = {}
    try:
        data = request.data
        i_id = _get_polling_id(request, data)
        if not i_id:
            return api_response(400, "iId/sid is required", res_body)
        
        try:
            sp = SpSmsPolling.objects.get(iId=i_id)
        except SpSmsPolling.DoesNotExist:
            return api_response(404, "SMS Polling not found.", res_body)

        v_heading = sp.vHeading
        res_body["smsPolling"] = v_heading

        to_number = (data.get('toNumber') or "").strip()
        que_ans_list = data.get('queAnsList', [])
        question_type = int(data.get('questionType', 0) or 0)
        control_types = data.get('controlTypes', [])
        question_numbers = data.get('questionNumbers', [])

        # --- sc Filtering (Participants) ---
        if to_number:
            sc = [to_number]
        else:
            # getToNumbersByIid
            sc = list(SpReply.objects.filter(smsPollingId=i_id).values_list('toNo', flat=True).distinct())

        for qa in que_ans_list:
            q_id = qa.get('queId')
            ans_val = qa.get('ans')
            if q_id is not None:
                if not ans_val or ans_val == "All":
                    # getToNumbersByQuesId
                    sc = list(SpReply.objects.filter(toNo__in=sc, quesId=q_id, ansVal__isnull=False).exclude(ansVal='').values_list('toNo', flat=True).distinct())
                else:
                    # getToNumbersByQuesIdAndAnsVal
                    sc = list(SpReply.objects.filter(toNo__in=sc, quesId=q_id, ansVal=ans_val).values_list('toNo', flat=True).distinct())

        # --- Question Selection Logic ---
        if question_type == 1 and len(control_types) > 0 >= len(question_numbers):
            # getQuestionsByIidAndQueTypes
            sp_questions_list = SpQuestions.objects.filter(iSmspollingId=i_id, queTypeId__in=control_types)
        elif (question_type == 2 and len(control_types) == 1 and "2" in control_types) or \
             (question_type == 3 and len(control_types) == 1 and "1" in control_types):
            sp_questions_list = SpQuestions.objects.none()
        else:
            if len(question_numbers) > 0:
                if question_type == 1:
                    # findAllDataByQueIds
                    sp_questions_list = SpQuestions.objects.filter(iSmspollingId=i_id, queId__in=question_numbers)
                elif question_type == 2:
                    # getQuestionsByIidAndQueTypeAndQueIds (type 1 = Option)
                    sp_questions_list = SpQuestions.objects.filter(iSmspollingId=i_id, queTypeId=1, queId__in=question_numbers)
                else:
                    # getQuestionsByIidAndQueTypeAndQueIds (type 2 = Text Ans)
                    sp_questions_list = SpQuestions.objects.filter(iSmspollingId=i_id, queTypeId=2, queId__in=question_numbers)
            else:
                if question_type == 1:
                    # findAllData
                    sp_questions_list = SpQuestions.objects.filter(iSmspollingId=i_id)
                elif question_type == 2:
                    # getQuestionsByIidAndQueType (type 1 = Option)
                    sp_questions_list = SpQuestions.objects.filter(iSmspollingId=i_id, queTypeId=1)
                else:
                    # getQuestionsByIidAndQueType (type 2 = Text Ans)
                    sp_questions_list = SpQuestions.objects.filter(iSmspollingId=i_id, queTypeId=2)

        sp_questions_list = sp_questions_list.order_by('disOrder')

        # --- Response Generation ---
        sms_polling_question_dtos = []
        dis_order = 1
        
        # Determine if we should fail open/closed for participants
        # Java: sc filter builds "and to_no in (...)"
        # If sc is empty, Java does "and 2 < 1" (which is always false)
        
        for arow in sp_questions_list:
            q_dto = {
                "queId": arow.queId,
                "queTypeId": arow.queTypeId,
                "disOrder": dis_order,
                "question": arow.question,
                "totalAnsForQues": 0,
                "optionList": []
            }
            dis_order += 1

            # totalAns4Que
            # select count(ques_id) where ques_id=:q_id and ans_val is not null and to_no in (:sc)
            if sc:
                total_ans_4_que = SpReply.objects.filter(quesId=arow.queId, ansVal__isnull=False, toNo__in=sc).count()
            else:
                total_ans_4_que = 0
            
            q_dto["totalAnsForQues"] = total_ans_4_que

            # Options
            sp_options_list = SpOptions.objects.filter(queId=arow.queId).order_by('optId')
            option_dto_list = []

            for arow2 in sp_options_list:
                if arow.queTypeId == 2: # Text Ans
                    if sc:
                        ans_vals = SpReply.objects.filter(quesId=arow.queId, toNo__in=sc).values_list('ansVal', flat=True).exclude(ansVal=None).exclude(ansVal='')
                        for val in ans_vals:
                            option_dto_list.append({"optionVal": val})
                else: # Option type
                    if sc:
                        total_ans = SpReply.objects.filter(quesId=arow.queId, ansVal__icontains=arow2.optionVal, toNo__in=sc).count()
                    else:
                        total_ans = 0
                    
                    denominator = total_ans_4_que if total_ans_4_que > 0 else 1
                    bar_width = math.floor((total_ans * 250) / denominator)
                    per_color = round((total_ans * 100) / denominator)

                    option_dto_list.append({
                        "optionVal": arow2.optionVal,
                        "totalAns": total_ans,
                        "barWidth": float(bar_width),
                        "perColor": float(per_color)
                    })
            
            q_dto["optionList"] = option_dto_list
            sms_polling_question_dtos.append(q_dto)

        res_body["questions"] = sms_polling_question_dtos
        res_body["countryList"] = _get_country_list(i_id)
        
        return api_response(200, "Fetch Result Successfully.", res_body)
    except Exception as e:
        logger.error(f"SmsPollingReportDataBrowser Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)

# ---------------------------------------------------------------------------
# 7. GET /smsPollingReport/getSmsPollingReportParticipate
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingReportParticipate(request):
    res_body = {}
    try:
        i_id = _get_polling_id(request)
        if not i_id:
            return api_response(400, "iId is required", res_body)

        
        # Raw SQL query from ContactRepository.getUserListByEmailIDs
        query = """
            SELECT tul.UL_EMAIL_ID, tul.UL_FIRST_NAME, tul.UL_LAST_NAME, ps.PSS_TO_CONTACT, r.PSR_FROM_COUNTRY, r.PSR_FROM_STATE, r.PSR_FROM_CITY 
            FROM USER_LIST tul, POLLING_SMS_SENT ps, POLLING_SMS_RESPONSES r 
            WHERE ps.PSS_SMS_POLL_ID=%s 
              AND ps.PSS_CONTACT_ID=tul.UL_EMAIL_ID 
              AND ps.PSS_SMS_POLL_ID=r.PSR_SP_ID 
              AND ps.PSS_TO_CONTACT=r.PSR_TO_NO 
            GROUP BY tul.UL_EMAIL_ID, tul.UL_FIRST_NAME, tul.UL_LAST_NAME, ps.PSS_TO_CONTACT, r.PSR_FROM_COUNTRY, r.PSR_FROM_STATE, r.PSR_FROM_CITY
        """
        
        participate_list = []
        with connection.cursor() as cursor:
            cursor.execute(query, [i_id])
            rows = cursor.fetchall()
            for row in rows:
                participate_list.append({
                    "emailId": row[0],
                    "firstName": row[1] or "",
                    "lastName": row[2] or "",
                    "toNumber": row[3] or "",
                    "fromCountry": row[4] or "",
                    "fromState": row[5] or "",
                    "fromCity": row[6] or ""
                })
                
        res_body['participateList'] = participate_list
        return api_response(200, "Fetch Result Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingReportParticipate Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)
