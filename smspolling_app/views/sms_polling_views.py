import logging
import traceback
from datetime import datetime
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from common_app.custom_permissions import WhitelistPermission
from common_app.models import (SpSmsPolling, SpQuestions, SpOptions, SpReply, PollingSmsTemp, SpQuestionCategory, SpCountry, PollingSmsSend, NumberCallForwarding, Country, Contact, PhoneNumbers, Clients)
from common_app.telnyx_utils import (delete_telnyx_number, check_assign_to_number, telnyx_sub_account, telnyx_call_forwarding,)
from common_app.utils import (api_response, get_final_tenant_id, get_ran_str, clean_me_number, display_date, add_one_month, last_characters, get_tenants, get_client_id_by_tenant_id)
from common_app.services import CommonServices
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage
import requests as req
from datetime import datetime as dt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_status_label(status):
    if status in (0, 1):
        return "Draft"
    elif status == 2:
        return "Published"
    elif status == 3:
        return "Close"
    return ""

def _delete_number_call_forwarding(phone_sid, tenant_id):
    try:
        NumberCallForwarding.objects.filter(cfnTwilioPhoneSid=phone_sid, cfnMemberId=get_client_id_by_tenant_id(tenant_id)).delete()
    except Exception:
        pass


def _save_number_call_forwarding(cfn_id, ph_phone_number, cc, fwd_no, tenant_id, phone_sid):
    try:
        if cfn_id and int(cfn_id) > 0:
            cf = NumberCallForwarding.objects.get(cfnId=cfn_id)
        else:
            cf = NumberCallForwarding()
        cf.cfnTwilioNumber = ph_phone_number
        cf.cfnForwardingCountryCode = cc
        cf.cfnForwardingNumber = fwd_no
        cf.cfnMemberId = get_client_id_by_tenant_id(tenant_id)
        cf.cfnTwilioPhoneSid = phone_sid
        cf.cfnDateTime = timezone.now()
        cf.save()
    except Exception as e:
        logger.error(f"SaveNumberCallForwarding Error: {e}")


def _build_polling_dto(sp):

    phone_number = PhoneNumbers.objects.filter(pnId=sp.pnId).first()

    d = {
        "noOfQuestions": sp.noOfQuestions,
        "rndHash": sp.rndHash,
        "groupList": sp.groupList if sp.groupList else None,
        "totalQuestion": 0,
        "status": _get_status_label(sp.iSPStatus),
        "questionFlowJson": sp.questionFlowJson if sp.questionFlowJson else None,
        "vsmspollingNumberPhoneSId": phone_number.phSid if phone_number else None,
        "vsmspollingNumber": clean_me_number(phone_number.phPhoneNumber) if phone_number else "",
        "iuserId": sp.iUserId,
        "vheading": sp.vHeading,
        "tfinalMsg": sp.tFinalMsg,
        "iid": sp.iId,
        "dpublishDate": display_date(sp.dPublishDate) if sp.dPublishDate else None,
        "ispstatus": sp.iSPStatus,
        "tdetail": sp.tDetail if sp.tDetail else None,
        "twelcomeMsg": sp.tWelcomeMsg,
        "tcompleteMsg": sp.tCompleteMsg if sp.tCompleteMsg else None,
    }

    # total questions
    try:
        d["totalQuestion"] = SpQuestions.objects.filter(iSmspollingId=sp.iId).count()
    except Exception:
        d["totalQuestion"] = 0

    # total members
    try:
        d["totalMember"] = SpReply.objects.filter(
            smsPollingId=sp.iId,
            userReply__isnull=False
        ).values("toNo").distinct().count()
    except Exception:
        d["totalMember"] = 0

    return d



def _build_question_with_options(q):
    options = list(SpOptions.objects.filter(queId=q.queId).order_by('optId'))
    option_vals = [o.optionVal for o in options]
    return {
        "queId": q.queId,
        "queTypeId": q.queTypeId,
        "question": q.question,
        "catId": q.catId,
        "optionVal": option_vals,
    }


def _question_flow_entry(q):
    options = list(SpOptions.objects.filter(queId=q.queId).order_by('optId'))
    option_flow = [{"positionNo": i, "condQue": o.condQue} for i, o in enumerate(options)]
    return {"queId": q.queId, "optionValNo": option_flow}


def _copy_temp_to_polling_sms_send(i_id, tenant_id, ph_phone_number):
    try:
        email_ids = list(PollingSmsTemp.objects.filter(iSmspollingId=i_id).values_list('emailId', flat=True))
        for email_id in email_ids:
            try:
                contact = Contact.objects.filter(memberId=tenant_id, emailId=email_id).first()
                if not contact:
                    continue
                cell_no = getattr(contact, 'phoneNumber', None) or ""
                country_name = getattr(contact, 'country', None) or ""
                if cell_no:
                    try:
                        country_obj = Country.objects.get(cnt_name=country_name)
                        country_code = country_obj.cnt_code or ""
                        phone_max = country_obj.phone_max_length if country_obj else 10
                    except Exception:
                        country_code = ""
                        phone_max = 10
                    cell_no = last_characters(clean_me_number(cell_no), phone_max)
                    cell_no = country_code + cell_no
                    polling_sms_send = PollingSmsSend(
                        iSmspollingId=i_id,
                        memberId=tenant_id,
                        emailId=email_id,
                        fromContact=ph_phone_number,
                        toContact=cell_no,
                    )
                    polling_sms_send.save()
            except Exception as e:
                logger.error(f"CopyTempToPollingSmsSend inner Error: {e}")
        try:
            PollingSmsTemp.objects.filter(iSmspollingId=i_id).delete()
        except Exception as e:
            logger.error(f"CopyTempToPollingSmsSend delete temp Error: {e}")
    except Exception as e:
        logger.error(f"CopyTempToPollingSmsSend Error: {e}")


# ---------------------------------------------------------------------------
# 1. GET /smsPolling/getSmsPollingList
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingList(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        search_key = request.GET.get('searchKey', None)
        page_num = int(request.GET.get('page', 0))
        page_size = int(request.GET.get('size', 10))

        qs = SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id)).order_by('-iId')
        if search_key:
            qs = qs.filter(vHeading__icontains=search_key)

        total = qs.count()
        paginator = Paginator(qs, page_size)
        try:
            page_obj = paginator.page(page_num + 1)
        except EmptyPage:
            page_obj = paginator.page(1)

        items = []
        for sp in page_obj.object_list:
            items.append(_build_polling_dto(sp))

        res_body['getNumber'] = page_num
        res_body['getSize'] = page_size
        res_body['smsPolling'] = items
        res_body['totalSmsPolling'] = total
        res_body['getTotalPages'] = paginator.num_pages


        return api_response(200, "Fetch SMS Polling Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingList Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 2. DELETE /smsPolling/deleteSmsPolling
# ---------------------------------------------------------------------------
@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSmsPolling(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        ids = request.data.get('ids', [])
        if ids:
            for id_ in ids:
                try:
                    sp = SpSmsPolling.objects.get(iId=id_)
                    phone_number = PhoneNumbers.objects.filter(pnId=sp.pnId).first()
                    if phone_number and phone_number.phSid:
                        try:
                            res = delete_telnyx_number(phone_number.phSid)
                            if res == 1:
                                phone_number.phPhoneNumberClosed = "Y"
                                phone_number.save()
                            _delete_number_call_forwarding(phone_number.phSid, final_tenant_id)
                        except Exception as e:
                            logger.error(f"DeleteSmsPolling Telnyx Delete Error: {e}")
                    que_ids = list(SpQuestions.objects.filter(iSmspollingId=id_).values_list('queId', flat=True))
                    for que_id in que_ids:
                        SpOptions.objects.filter(queId=que_id).delete()
                    SpQuestions.objects.filter(iSmspollingId=id_).delete()
                    SpSmsPolling.objects.filter(iId=id_).delete()
                except SpSmsPolling.DoesNotExist:
                    pass
        return api_response(200, "SMS Polling Delete Successfully.", res_body)
    except Exception as e:
        logger.error(f"DeleteSmsPolling Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 3. POST /smsPolling/closeSmsPolling
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def closeSmsPolling(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        ids = request.data.get('ids', [])
        for id_ in ids:
            try:
                sp = SpSmsPolling.objects.get(iId=id_)
                sp.iSPStatus = 3
                sp.save()
                phone_number = PhoneNumbers.objects.get(pnId=sp.pnId)
                if phone_number.phSid:
                    try:
                        res = delete_telnyx_number(phone_number.phSid)
                        if res == 1:
                            phone_number.phPhoneNumberClosed = "Y"
                            phone_number.save()
                        _delete_number_call_forwarding(phone_number.phSid, final_tenant_id)
                    except Exception as e:
                        logger.error(f"CloseSmsPolling Telnyx Delete Error: {e}")
            except SpSmsPolling.DoesNotExist:
                pass
        return api_response(200, "SMS Polling Close Successfully.", res_body)
    except Exception as e:
        logger.error(f"CloseSmsPolling Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 4. GET /smsPolling/getSmsPolling/{rndHash}
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPolling(request, rndHash):
    res_body = {}
    try:
        sp = SpSmsPolling.objects.get(rndHash=rndHash)
        dto = _build_polling_dto(sp)

        # Check active telnyx number
        try:
            phone_number = PhoneNumbers.objects.get(pnId=sp.pnId)
            if phone_number.phSid:
                flag = _check_active_telnyx_number(phone_number.phSid)
                if flag == "Inactive":
                    dto["vSmspollingNumber"] = ""
        except Exception as e:
            logger.error(f"FindSmsPolling Error 1: {e}")

        # Questions + options + flow
        try:
            questions = list(SpQuestions.objects.filter(iSmspollingId=sp.iId).order_by('disOrder'))
            q_dtos = [_build_question_with_options(q) for q in questions]
            q_flow = [_question_flow_entry(q) for q in questions]
            dto["questions"] = q_dtos
            dto["questionFlow"] = q_flow
        except Exception as e:
            logger.error(f"FindSmsPolling Error 2: {e}")

        # Tenant list
        try:
            tenant_list = list(PollingSmsTemp.objects.filter(iSmspollingId=sp.iId).values_list('emailId', flat=True))
            dto["memberList"] = tenant_list
        except Exception as e:
            logger.error(f"FindSmsPolling Error 3: {e}")

        # Countries
        try:
            countries = list(SpCountry.objects.filter(iSmsPollingId=sp.iId).values_list('country', flat=True))
            dto["country"] = countries
        except Exception as e:
            logger.error(f"FindSmsPolling Error 6: {e}")

        res_body["smsPolling"] = dto
        return api_response(200, "Fetch SMS Polling Successfully.", res_body)
    except SpSmsPolling.DoesNotExist:
        return api_response(404, "SMS Polling not found.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPolling Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


def _check_active_telnyx_number(phone_sid):
    try:
        base_url = getattr(settings, 'TELNYX_BASE_URL', 'https://api.telnyx.com/v2/')
        api_key = getattr(settings, 'TELNYX_API_KEY', '')
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        resp = req.get(f"{base_url}phone_numbers/{phone_sid}", headers=headers)
        if resp.status_code == 200:
            return "Active"
        return "Inactive"
    except Exception:
        return "Inactive"


# ---------------------------------------------------------------------------
# 5. POST /smsPolling/saveSmsInfo
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSmsInfo(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        data = request.data
        rnd_hash = data.get('rndHash', data.get('rndhash', ''))

        if not rnd_hash:
            sp = SpSmsPolling()
            sp.rndHash = get_ran_str(16)
        else:
            sp = SpSmsPolling.objects.get(rndHash=rnd_hash)

        sp.vHeading = data.get('vHeading', data.get('vheading', ''))
        sp.tDetail = data.get('tDetail', data.get('tdetail', ''))
        sp.tWelcomeMsg = data.get('tWelcomeMsg', data.get('twelcomeMsg', ''))
        sp.tFinalMsg = data.get('tFinalMsg', data.get('tfinalMsg', ''))
        sp.iUserId = get_client_id_by_tenant_id(final_tenant_id)
        sp.save()

        res_body['smsInfo'] = {
            "rndHash": sp.rndHash,
            "iid": sp.iId,
            "vHeading": sp.vHeading,
            "tDetail": sp.tDetail,
            "tWelcomeMsg": sp.tWelcomeMsg,
            "tFinalMsg": sp.tFinalMsg,
        }
        return api_response(200, "Save SMS Info Successfully.", res_body)
    except Exception as e:
        logger.error(f"SaveSmsInfo Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 6. POST /smsPolling/saveMemberList
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveMemberList(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        data = request.data
        rnd_hash = data.get('rndHash') or data.get('sid', '')
        group_list = data.get('groupList', '')
        lchst = data.get('lchst', '')
        tenant_list = data.get('memberList', [])

        try:
            sp = SpSmsPolling.objects.get(rndHash=rnd_hash)
            sp.groupList = group_list
            sp.save()
            i_id = sp.iId
        except SpSmsPolling.DoesNotExist:
            return api_response(404, "SMS Polling not found.", res_body)

        if lchst == 'A':
            group_ids = int(group_list)
            tenant_list = list(Contact.objects.filter(
                groupId=group_ids,
                memberId=get_client_id_by_tenant_id(final_tenant_id)
            ).values_list('emailId', flat=True))

        if tenant_list:
            PollingSmsTemp.objects.filter(iSmspollingId=i_id).delete()
            batch = []
            for email_id in tenant_list:
                if isinstance(email_id, str) and not email_id.isdigit():
                    continue 

                batch.append(PollingSmsTemp(
                    iSmspollingId=i_id,
                    memberId=get_client_id_by_tenant_id(final_tenant_id),
                    emailId=int(email_id),
                    is_send='N',
                ))
                if len(batch) >= 2000:
                    PollingSmsTemp.objects.bulk_create(batch)
                    batch = []
            if batch:
                PollingSmsTemp.objects.bulk_create(batch)


        # Get first question
        que_id = 0
        que_type_id = 0
        try:
            first_q = SpQuestions.objects.filter(iSmspollingId=i_id).order_by('disOrder').first()
            if first_q:
                que_id = first_q.queId
                que_type_id = first_q.queTypeId
        except Exception:
            pass

        res_body['saveTenantList'] = {
            "iid":i_id,
            "rndHash":rnd_hash,
            "groupList":group_list,
            "memberList":tenant_list,
            "queId":que_id,
            "queTypeId":que_type_id,
            "lchst":lchst
        }

        return api_response(200, "Save Tenant List Successfully.", res_body)
    except Exception as e:
        logger.error(f"SaveMemberList Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 7. POST /smsPolling/addSmsPollingCategory
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def addSmsPollingCategory(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        data = request.data
        cat_name = data.get('catName', '')

        cat_id = 0
        try:
            existing = SpQuestionCategory.objects.filter(catName=cat_name, memberId=get_client_id_by_tenant_id(final_tenant_id)).first()
            if existing:
                cat_id = existing.id
        except Exception as e:
            logger.error(f"AddSmsPollingCategory Error 1: {e}")

        if cat_id == 0:
            cat = SpQuestionCategory.objects.create(
                memberId=get_client_id_by_tenant_id(final_tenant_id),
                catName=cat_name,
            )
            cat_id = cat.id

        res_body['category'] = {
            "id": cat_id,
            "catName": cat_name,
            "memberId": final_tenant_id,
        }
        return api_response(200, "Add Category Successfully.", res_body)
    except Exception as e:
        logger.error(f"AddSmsPollingCategory Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 8. GET /smsPolling/getSmsPollingCategoryList
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingCategoryList(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        cats = SpQuestionCategory.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id)).order_by('catName')
        cat_list = [{"id": c.id, "catName": c.catName, "memberId": c.memberId} for c in cats]
        res_body['smsPollingCategory'] = cat_list
        return api_response(200, "Fetch Category List Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingCategoryList Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 9. DELETE /smsPolling/deleteSmsPollingQuestion
# ---------------------------------------------------------------------------
@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSmsPollingQuestion(request):
    res_body = {}
    try:
        data = request.data
        i_id = data.get('iid') or data.get('iId', 0)
        que_id = data.get('queId', 0)
        que_type_id = data.get('queTypeId', 0)

        que_ids = list(SpQuestions.objects.filter(iSmspollingId=i_id).values_list('queId', flat=True))
        for qid in que_ids:
            SpOptions.objects.filter(queId=qid).update(condQue=0)

        if que_type_id in (1, 2):
            SpOptions.objects.filter(queId=que_id).delete()
            SpQuestions.objects.filter(queId=que_id).delete()

        new_que_id = 0
        new_que_type_id = 0
        try:
            first_q = SpQuestions.objects.filter(iSmspollingId=i_id).order_by('disOrder').first()
            if first_q:
                new_que_id = first_q.queId
                new_que_type_id = first_q.queTypeId
        except Exception:
            pass

        res_body['question'] = {
            "iid": i_id,
            "queId": new_que_id,
            "queTypeId": new_que_type_id,
        }
        return api_response(200, "Question Delete Successfully.", res_body)
    except Exception as e:
        traceback.print_exc()
        logger.error(f"DeleteSmsPollingQuestion Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 10. POST /smsPolling/saveSmsPollingQuestion
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSmsPollingQuestion(request):
    res_body = dict()
    try:
        data = request.data
        i_id = data.get('iid') or data.get('iId', 0)
        que_id_in = data.get('queId', 0)
        que_type_id = data.get('queTypeId', 0)
        question_text = data.get('question', '')
        cat_id = data.get('catId', 0)
        option_vals = data.get('optionVal', [])
        rnd_hash = data.get('rndHash', '')

        ans_total = len(option_vals)

        # Calculate disOrder
        dis_order = 1
        try:
            max_dis = SpQuestions.objects.filter(iSmspollingId=i_id).order_by('-disOrder').values_list('disOrder', flat=True).first()
            if max_dis is None:
                max_dis = 0
            dis_order = max_dis + 1
        except Exception:
            pass

        if que_id_in and int(que_id_in) > 0:
            sp_q = SpQuestions.objects.get(queId=que_id_in)
            sp_q.queTypeId = que_type_id
            sp_q.question = question_text
            sp_q.noOfOptions = ans_total
            sp_q.catId = cat_id
            sp_q.save()
            que_id = sp_q.queId
            SpOptions.objects.filter(queId=que_id).delete()
        else:
            sp_q = SpQuestions.objects.create(
                iSmspollingId=i_id,
                queTypeId=que_type_id,
                question=question_text,
                noOfOptions=ans_total,
                disOrder=dis_order,
                catId=cat_id,
            )
            que_id = sp_q.queId

        for opt_val in option_vals:
            SpOptions.objects.create(
                optTypeId=que_type_id,
                queId=que_id,
                optionVal=opt_val,
            )

        res_body['question'] = {
            "iid": i_id,
            "queId": que_id,
            "queTypeId": que_type_id,
            "question": question_text,
            "catId": cat_id,
            "optionVal": option_vals,
            "rndHash": rnd_hash
        }
        return api_response(200, "Save Question Successfully.", res_body)
    except Exception as e:
        logger.error(f"SaveSmsPollingQuestion Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 11. GET /smsPolling/getDuplicateSmsPolling/{subMemberId}/{rndHash}
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getDuplicateSmsPolling(request, subTenantId, rndHash):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        new_rnd_hash = get_ran_str(16)
        sp = SpSmsPolling.objects.get(rndHash=rndHash)

        new_sp = SpSmsPolling.objects.create(
            iUserId=get_client_id_by_tenant_id(final_tenant_id),
            vHeading=str(sp.vHeading or '') + " Copy",
            tDetail=sp.tDetail,
            noOfQuestions=sp.noOfQuestions,
            rndHash=new_rnd_hash,
            iSPStatus=0,
            tWelcomeMsg=sp.tWelcomeMsg,
            tCompleteMsg=sp.tCompleteMsg,
            tFinalMsg=sp.tFinalMsg,
            groupList=sp.groupList,
            isSend='N',
            questionFlowJson=sp.questionFlowJson,
            pnId=sp.pnId
        )
        new_i_id = new_sp.iId

        try:
            qs = SpQuestions.objects.filter(iSmspollingId=sp.iId).order_by('disOrder')
            for q in qs:
                new_q = SpQuestions.objects.create(
                    iSmspollingId=new_i_id,
                    queTypeId=q.queTypeId,
                    question=q.question,
                    noOfOptions=q.noOfOptions,
                    queOrder=q.queOrder,
                    disOrder=q.disOrder,
                    ddQue=q.ddQue,
                    catId=q.catId,
                )
                opts = SpOptions.objects.filter(queId=q.queId)
                for opt in opts:
                    SpOptions.objects.create(
                        optTypeId=opt.optTypeId,
                        queId=new_q.queId,
                        optionVal=opt.optionVal,
                        optOrder=opt.optOrder,
                        ansAnalysis=opt.ansAnalysis,
                        condQue=opt.condQue,
                        regReq=opt.regReq,
                    )
        except Exception as e:
            logger.error(f"GetDuplicateSmsPolling Error 1: {e}")

        sp.iSPStatus = 3
        sp.save()

        try:
            temps = PollingSmsTemp.objects.filter(iSmspollingId=sp.iId)
            new_temps = [
                PollingSmsTemp(iSmspollingId=new_i_id, memberId=t.memberId, emailId=t.emailId, is_send='N')
                for t in temps
            ]
            PollingSmsTemp.objects.bulk_create(new_temps)
        except Exception as e:
            logger.error(f"GetDuplicateSmsPolling Error 2: {e}")

        res_body['rndHash'] = new_rnd_hash
        return api_response(200, "Fetch SMS Polling Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetDuplicateSmsPolling Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 12. POST /smsPolling/saveFinalizeQuestionOrder
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveFinalizeQuestionOrder(request):
    try:
        data = request.data
        i_id = data.get('iid') or data.get('iId', 0)
        questions = data.get('questions', [])
        count = 1
        for que_id in questions:
            try:
                q = SpQuestions.objects.get(queId=que_id, iSmspollingId=i_id)
                q.disOrder = count
                q.save()
                SpOptions.objects.filter(queId=que_id).update(condQue=0)
                count += 1
            except Exception:
                pass
        return api_response(200, "Change In Display Order Will Reset Your Question Logic Flow.", "")
    except Exception as e:
        logger.error(f"SaveFinalizeQuestionOrder Error: {e}")
        return api_response(500, "Oops!! There is some issue", "")


# ---------------------------------------------------------------------------
# 13. POST /smsPolling/clearQuestionLogicFlow
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def clearQuestionLogicFlow(request):
    try:
        data = request.data
        questions = data.get('questions', [])
        for que_id in questions:
            SpOptions.objects.filter(queId=que_id).update(condQue=0)
        return api_response(200, "Question Order Logic Cleared", "")
    except Exception as e:
        logger.error(f"ClearQuestionLogicFlow Error: {e}")
        return api_response(500, "Oops!! There is some issue", "")


# ---------------------------------------------------------------------------
# 14. POST /smsPolling/saveQuestionLogicFlow
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveQuestionLogicFlow(request):
    try:
        data = request.data
        polling_id = data.get('pollingId', 0)
        question_flow_json = data.get('questionFlowJson', '')
        question_flow_list = data.get('questionFlow', [])

        sp = SpSmsPolling.objects.get(iId=polling_id)
        sp.questionFlowJson = question_flow_json
        sp.save()

        for qf in question_flow_list:
            que_id = qf.get('queId', 0)
            option_vals = qf.get('optionValNo', [])
            opts = list(
                SpOptions.objects.filter(queId=que_id)
                .order_by('optId')
                .values_list('optId', flat=True)
            )
            for opt_flow in option_vals:
                pos = opt_flow.get('positionNo', -1)
                cond_que = opt_flow.get('condQue', 0)
                if 0 <= pos < len(opts):
                    SpOptions.objects.filter(optId=opts[pos]).update(
                        condQue=cond_que
                    )

        return api_response(200, "Save Question Logic Flow Successfully.", "")
    except Exception as e:
        logger.error(f"SaveQuestionLogicFlow Error: {e}")
        return api_response(500, "Oops!! There is some issue", "")


# ---------------------------------------------------------------------------
# 15. POST /smsPolling/saveDemographicLocation
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveDemographicLocation(request):
    try:
        data = request.data
        i_id = data.get('iid') or data.get('iId', 0)
        countries = data.get('country', [])

        SpCountry.objects.filter(iSmsPollingId=i_id).delete()
        for country in countries:
            SpCountry.objects.create(iSmsPollingId=i_id, country=country)

        return api_response(200, "Save Demographic Location Successfully.", "")
    except Exception as e:
        logger.error(f"SaveDemographicLocation Error: {e}")
        return api_response(500, "Oops!! There is some issue", "")


# ---------------------------------------------------------------------------
# 16. POST /smsPolling/saveAndConfirm
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveAndConfirm(request):
    try:
        data = request.data
        rnd_hash = data.get('rndHash', '')
        i_id = data.get('iid') or data.get('iId', 0)
        d_publish_date = data.get('dpublishDate', None)
        sp = SpSmsPolling.objects.get(rndHash=rnd_hash)
        if d_publish_date is not None:
            try:
                sp.dPublishDate = datetime.strptime(d_publish_date, '%m/%d/%Y').date()
            except Exception:
                pass
        sp.iSPStatus = 1
        sp.rndHash = rnd_hash
        sp.iId = i_id
        sp.save()

        return api_response(200, "Save SMS Polling Successfully.", "")
    except Exception as e:
        logger.error(f"SaveAndConfirm Error: {e}")
        return api_response(500, "Oops!! There is some issue", "")


# ---------------------------------------------------------------------------
# 17. POST /smsPolling/publishAndConfirm
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def publishAndConfirm(request):
    res_body = {"location": ""}
    try:
        tenant_id = get_final_tenant_id(request=request)
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )

        data = request.data
        rnd_hash = data.get('rndHash', '')
        i_id = data.get('iid') or data.get('iId', 0)
        d_publish_date = data.get('dpublishDate', None)

        # Check payment profile
        authorize_profile_id = getattr(tenant, 'td_authorize_customer_profile_id', None)
        authorize_payment_id = getattr(tenant, 'td_authorize_customer_payment_profile_id', None)
        has_payment = bool(authorize_profile_id and authorize_payment_id)

        sp = SpSmsPolling.objects.get(rndHash=rnd_hash)
        if d_publish_date:
            try:
                sp.dPublishDate = datetime.strptime(d_publish_date, '%m/%d/%Y').date()
            except Exception:
                pass
        sp.rndHash = rnd_hash
        sp.iId = i_id
        sp.save()

        # Check Telnyx number assignment
        phone_number = PhoneNumbers.objects.get(pnId=sp.pnId)
        client = Clients.objects.get(cliTenantId=tenant_id)
        try:
            check_assign_to_number(
                getattr(client, 'cliSmsAccountSid', ''),
                phone_number.phSid,
                cli_sip_connection_id=getattr(client, 'cliSipConnectionId', ''),
            )
        except Exception as e:
            logger.error(f"PublishAndConfirm checkAssignToNumber Error: {e}")

        if has_payment:
            sp.iSPStatus = 2
            sp.save()
            _copy_temp_to_polling_sms_send(sp.iId, sp.iUserId, phone_number.phPhoneNumber)
        else:
            res_body["location"] = "paymentProfile"

        if res_body["location"] == "":
            return api_response(200, "SMS Polling Publish Successfully.", res_body)
        else:
            return api_response(200, "Add Payment Profile.", res_body)
    except Exception as e:
        logger.error(f"PublishAndConfirm Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 18. POST /smsPolling/finalPublishAndConfirm
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def finalPublishAndConfirm(request):
    try:
        data = request.data
        rnd_hash = data.get('rndHash', '')

        sp = SpSmsPolling.objects.get(rndHash=rnd_hash)
        sp.iSPStatus = 2
        sp.save()
        phone_number = PhoneNumbers.objects.get(pnId=sp.pnId)
        _copy_temp_to_polling_sms_send(sp.iId, sp.iUserId, phone_number.phPhoneNumber)

        return api_response(200, "SMS Polling Publish Successfully.", "")
    except Exception as e:
        logger.error(f"FinalPublishAndConfirm Error: {e}")
        return api_response(500, "Oops!! There is some issue", "")


# ---------------------------------------------------------------------------
# 19. POST /smsPolling/buyNumberForSmsPolling
# ---------------------------------------------------------------------------
@api_view(['POST'])
@permission_classes([WhitelistPermission])
def buyNumberForSmsPolling(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        data = request.data        
        no_existing = data.get('noExisting', '')
        i_id = data.get('iid') or data.get('iId', 0)
        twilio_number = data.get('twilioNumber', '')
        sub_tenant_id = data.get('subMemberId', 0)
        sub_full_name = data.get('subFullName', '')
        full_name = data.get('fullName', '')
        check_forwarding = data.get('checkForwardingYesNo')
        fwd_country_code = data.get('callForwardingCountryCode', '')
        fwd_number = data.get('callForwardingNumber', '')
        conversations_twilio_number = data.get('conversationsTwilioNumber', '')

        out_result = {"error": "", "phPhoneNumber": ""}

        if no_existing == "Yes":
            out_result["phPhoneNumber"] = twilio_number
        
        if not out_result["error"]:
            if no_existing in ("No", ""):
                if sub_tenant_id and int(sub_tenant_id) > 0:
                    logged_user_id = int(sub_tenant_id)
                    fn = f"{sub_full_name} {sub_tenant_id}"
                else:
                    logged_user_id = final_tenant_id
                    fn = full_name

                env_sys = getattr(settings, 'ENVSYS', 'dev')
                sub_client = Clients.objects.get(cliTenantId=logged_user_id)
                out_result = telnyx_sub_account(
                    sms_reply_url=settings.SMS_REPLY_URL if hasattr(settings, 'SMS_REPLY_URL') else '',
                    cli_sip_friendly_name=f"{env_sys.upper()} {fn} {final_tenant_id}",
                    ph_phone_number=twilio_number,
                    cli_sms_account_sid=getattr(sub_client, 'cliSmsAccountSid', '') or '',
                    telnyx_base_url=settings.TELNYX_BASE_URL if hasattr(settings, 'TELNYX_BASE_URL') else None,
                    telnyx_api_key=settings.TELNYX_API_KEY if hasattr(settings, 'TELNYX_API_KEY') else None,
                    cli_sip_connection_id=getattr(sub_client, 'cliSipConnectionId', '') or '',
                    site_url_backend=settings.SITE_URL_BACKEND if hasattr(settings, 'SITE_URL_BACKEND') else '',
                    telnyx_outbound_voice_profile_id=settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID if hasattr(settings,'TELNYX_OUTBOUND_VOICE_PROFILE_ID') else None
                )

                logger.error(f"out_result: {out_result}")
                # Call Forwarding
                try:
                    if check_forwarding == "yes":
                        fwd_no_full = f"{fwd_country_code}{fwd_number}"
                        s_id = telnyx_call_forwarding(out_result.get('phSid', ''), fwd_no_full, True)
                        if s_id:
                            _save_number_call_forwarding(0, conversations_twilio_number, fwd_country_code, fwd_number, final_tenant_id, out_result.get('phSid', ''))
                except Exception as e:
                    logger.error(f"BuyNumber CallForwarding Error: {e}")

                try:
                    sub_client.cliSipFriendlyName = out_result.get('cliSipFriendlyName', '')
                    sub_client.cliSipUsername = out_result.get('cliSipFriendlyName', '')
                    sub_client.cliSipPassword = out_result.get('cliSipFriendlyName', '')
                    sub_client.cliSmsAccountSid = out_result.get('cliSmsAccountSid', '')
                    sub_client.cliSipConnectionId = (out_result.get('cliSipConnectionId', '') or '').strip()
                    sub_client.save()
                except Exception as e:
                    logger.error(f"BuyNumber member update Error 1: {e}")

                # Update sp sms polling
                try:
                    sp = SpSmsPolling.objects.filter(iId=i_id).first()
                    if sp is not None:
                        naive_dt = timezone.now()
                        try:
                            renew_date_str = add_one_month() + " " + timezone.now().strftime('%H:%M:%S')
                            naive_dt = dt.strptime(renew_date_str, '%Y-%m-%d %H:%M:%S')
                        except Exception:
                            pass

                        phone_number = PhoneNumbers.objects.create(
                            phClientId=get_client_id_by_tenant_id(final_tenant_id),
                            phPhoneNumber=out_result.get('phPhoneNumber', ''),
                            phSid=out_result.get('phSid', ''),
                            phHowUsed='SMSPOLLING',
                            phDatePurchased=timezone.now(),
                            phDateRenew = timezone.make_aware(naive_dt),
                            phPhoneNumberClosed = 'N'
                        )

                        sp.pnId = phone_number.pnId
                        sp.save()
                except Exception as e:
                    traceback.print_exc()
                    logger.error(f"BuyNumber sp update Error 3: {e}")

                # Campaign transaction
                try:
                    country_setting = CommonServices.country_setting_by_tenant_id(final_tenant_id)
                    price = getattr(country_setting, 'cnty_sms_number_per_price', 0) or 0
                    CommonServices.saveCampaignTransaction(
                        None,
                        f"SMS polling number purchased : {out_result.get('phPhoneNumber', '')}",
                        1,
                        "sms polling number",
                        None,
                        "uninvoiced",
                        None,
                        get_client_id_by_tenant_id(final_tenant_id),
                        "0",
                        price,
                        price,
                        None,
                        None,
                        None,
                        0,
                    )
                except Exception as e:
                    logger.error(f"BuyNumber campaign txn Error: {e}")

            # Copy temp to pollingSmsSend
            _copy_temp_to_polling_sms_send(i_id, get_client_id_by_tenant_id(final_tenant_id), out_result.get('phPhoneNumber', twilio_number))

            res_body["status"] = "ok"
            return api_response(200, "Buy SMS Polling Number Successfully.", res_body)
        else:
            res_body["status"] = "error"
            res_body["msg"] = out_result.get('error', 'Error')
            return api_response(500, out_result.get('error', 'Error'), res_body)

    except Exception as e:
        logger.error(f"BuyNumberForSmsPolling Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 20. GET /smsPolling/getSmsPollingPhoneList
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSmsPollingPhoneList(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        phone_numbers = list(
            PhoneNumbers.objects.filter(
                pnId__in=SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id)).exclude(iSPStatus=3).values_list('pnId', flat=True),
                phPhoneNumberClosed='N'
            )
            .values_list('phPhoneNumber', flat=True)
        )

        result_list = []
        count = 0
        for no in phone_numbers:
            if not no:
                continue
            phone_number = PhoneNumbers.objects.get(phPhoneNumber=no, phPhoneNumberClosed='N')
            sps = list(SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id), pnId=phone_number.pnId))
            ff = 0
            for sp in sps:
                item = {
                    "iid": sp.iId,
                    "vheading": sp.vHeading,
                    "vsmspollingNumber": clean_me_number(phone_number.phPhoneNumber or ''),
                    "position": count,
                }
                count += 1
                if ff == 0:
                    item["smsDisplay"] = "Y"
                    try:
                        client = Clients.objects.get(cliTenantId=final_tenant_id)
                        number_assign = check_assign_to_number(
                            getattr(client, 'cliSmsAccountSid', '') or '',
                            phone_number.phSid or '',
                            cli_sip_connection_id=getattr(client, 'cliSipConnectionId', '') or '',
                            )
                        item["numberStatus"] = "Provisioned" if number_assign == "Yes" else "Unprovisioned"
                    except Exception:
                        item["numberStatus"] = "Unprovisioned"
                else:
                    item["smsDisplay"] = "N"

                item["btnDelete"] = "Y" if sp.iSPStatus == 2 else "N"

                try:
                    cf = NumberCallForwarding.objects.filter(
                        cfnTwilioPhoneSid=phone_number.phSid,
                        cfnMemberId=get_client_id_by_tenant_id(final_tenant_id)
                    ).first()
                    if cf:
                        item["numberCallForwarding"] = {
                            "cfnId": cf.cfnId,
                            "cfnTwilioNumber": cf.cfnTwilioNumber,
                            "cfnForwardingCountryCode": cf.cfnForwardingCountryCode,
                            "cfnForwardingNumber": cf.cfnForwardingNumber,
                            "cfnTwilioPhoneSid": cf.cfnTwilioPhoneSid,
                        }
                    else:
                        item["numberCallForwarding"] = None
                except Exception:
                    item["numberCallForwarding"] = None

                result_list.append(item)
                ff += 1

        res_body['smsPolling'] = result_list
        return api_response(200, "Fetch SMS Polling Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetSmsPollingPhoneList Error: {e}")
        return api_response(500, "Oops!! There is some issue", res_body)


# ---------------------------------------------------------------------------
# 21. DELETE /smsPolling/deleteSmsPollingNumber/{iId}
# ---------------------------------------------------------------------------
@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSmsPollingNumber(request, iId):
    res_body = {}
    try:
        sp = SpSmsPolling.objects.get(iId=iId)
        sp.iSPStatus = 3
        sp.save()
        phone_number = PhoneNumbers.objects.get(pnId=sp.pnId)
        if phone_number.phSid and phone_number.phSid.strip():
            delete_telnyx_number(phone_number.phSid)
            try:
                _delete_number_call_forwarding(phone_number.phSid, sp.iUserId)
            except Exception:
                pass
        return api_response(200, "Delete Phone Number Successfully.", res_body)
    except SpSmsPolling.DoesNotExist:
        return api_response(404, "SMS Polling not found.", res_body)
    except Exception as e:
        logger.error(f"DeleteSmsPollingNumber Error: {e}")
        return api_response(500, "Oops !! There Is Some Problem While Phone Number Delete.", res_body)


# ---------------------------------------------------------------------------
# 22. POST /smsPolling/smsStatusUrl
# ---------------------------------------------------------------------------
@api_view(['POST'])
def smsStatusUrl(request: Request):
    try:
        response_data = request.data
        logger.info(f"SmsPollingStatusUrl Response: {response_data}")
    except Exception as e:
        logger.error(f"SmsStatusUrl Error: {e}")
    return api_response(200, "OK", {})


# ---------------------------------------------------------------------------
# Extra dashboard helpers (used by SmsCampaigns/Reports cross-app)
# ---------------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([WhitelistPermission])
def countTotalSmsPollingWithOutDraft(request):
    """GET /smsPolling/countTotalSmsPollingWithOutDraft"""
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        count = SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id), iSPStatus__gt=1).count()
        return api_response(200, "OK", {"count": count or 0})
    except Exception as e:
        logger.error(f"CountTotalSmsPollingWithOutDraft Error: {e}")
        return api_response(500, "Oops!! There is some issue", {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def findLimitSmsPollingListWithOutDraft(request):
    """GET /smsPolling/findLimitSmsPollingListWithOutDraft?limit=5"""
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        limit = int(request.GET.get('limit', 5))

        sps = SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id), iSPStatus__gt=1).order_by('-iId')[:limit]
        result = []
        for sp in sps:
            total_q = SpQuestions.objects.filter(iSmspollingId=sp.iId).count()
            total_r = SpReply.objects.filter(smsPollingId=sp.iId).values('fromNo').distinct().count()
            result.append({
                "iid": sp.iId,
                "vHeading": sp.vHeading,
                "createdDate": display_date(sp.dPublishDate) if sp.dPublishDate else None,
                "dPublishDate": display_date(sp.dPublishDate) if sp.dPublishDate else None,
                "totalQuestion": total_q,
                "totalResponses": total_r,
            })
        return api_response(200, "OK", {"smsPolling": result})
    except Exception as e:
        logger.error(f"FindLimitSmsPollingListWithOutDraft Error: {e}")
        return api_response(500, "Oops!! There is some issue", {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getTotalResponsesCount(request):
    """GET /smsPolling/getTotalResponsesCount"""
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        i_ids = list(SpSmsPolling.objects.filter(iUserId=get_client_id_by_tenant_id(final_tenant_id)).values_list('iId', flat=True))
        total = 0
        for i_id in i_ids:
            total += SpReply.objects.filter(smsPollingId=i_id).values('fromNo').distinct().count()
        return api_response(200, "OK", {"totalResponses": total})
    except Exception as e:
        logger.error(f"GetTotalResponsesCount Error: {e}")
        return api_response(500, "Oops!! There is some issue", {})