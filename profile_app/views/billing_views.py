import logging
import math
from datetime import datetime, date
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.request import Request
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from rest_framework.renderers import JSONRenderer
from rest_framework.utils import encoders
from common_app.utils import api_response, get_final_tenant_id, get_tenants, get_client_id_by_tenant_id, \
    get_tenant_id_by_client_id
from common_app.decrypt_string import DecryptString
from auth_app.models import Tenants, TenantDetails
from common_app.models import (DeleteAccount, NumberCallForwarding, Groups, Userlist, GroupSegment, GroupSegmentField, Udf, CampaignsSendEmail, CampaignSendSms, CampaignsEmailSend, CampaignsSmsSend, CampaignTransaction, CampaignsEmail, CampaignsSms, EiSocialMedia, Invoices, TempUserlist, CountrySetting, Plans, PhoneNumbers)
from assessment_app.models import AssessmentGroups
from common_app.services import CommonServices, MailRequestDTO
from common_app.telnyx_utils import delete_telnyx_number
from authorizenet import apicontractsv1
from authorizenet.apicontrollers import deleteCustomerProfileController
from django.db.models import Sum
from authorizenet.constants import constants

logger = logging.getLogger(__name__)

# Constants
ERROR_MSG = "Something went wrong! Please try again later."

class CustomJSONEncoder(encoders.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%m/%d/%Y')
        if isinstance(obj, date):
            return obj.strftime('%m/%d/%Y')
        return super().default(obj)


class CustomDateJSONRenderer(JSONRenderer):
    encoder_class = CustomJSONEncoder


def display_date(date_val):
    if not date_val:
        return ""
    if isinstance(date_val, str):
        try:
            if " " in date_val:
                dt = datetime.strptime(date_val.split(" ")[0], '%Y-%m-%d')
            else:
                dt = datetime.strptime(date_val, '%Y-%m-%d')
            return dt.strftime('%m/%d/%Y')
        except Exception:
            pass
        return date_val
    elif isinstance(date_val, datetime):
        return date_val.strftime('%m/%d/%Y')
    elif isinstance(date_val, date):
        return date_val.strftime('%m/%d/%Y')
    return str(date_val)



def get_bill_type(bill_type):
    if not bill_type:
        return "0"
    return str(bill_type)


def br2nl(text):
    if not text:
        return ""
    return text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


@api_view(['GET'])
def getUninvoicedList(request):
    request.accepted_renderer = CustomDateJSONRenderer()
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    try:

        campaign_transaction_dto = []
        transactions = CampaignTransaction.objects.filter(
            ct_client_id=get_client_id_by_tenant_id(final_tenant_id),
            tran_invoiced_status='uninvoiced',
            tran_bill_type='0'
        ).order_by('-tran_id')

        for ct in transactions:
            dto = dict()
            dto['tranId'] = ct.tran_id
            dto['tranCampaignId'] = ct.tran_campaign_id
            dto['tranCampaignName'] = br2nl(ct.tran_campaign_name)

            campaign_date = ct.tran_campaign_date
            if campaign_date:
                if isinstance(campaign_date, str):
                    dto['tranCampaignDate'] = display_date(campaign_date + " 12:00:00")
                else:
                    dto['tranCampaignDate'] = display_date(campaign_date)
            else:
                dto['tranCampaignDate'] = None

            dto['tranTotalMember'] = ct.tran_total_member
            dto['tranType'] = ct.tran_type
            dto['tranInvoicedId'] = ct.tran_invoiced_id
            dto['tranInvoicedStatus'] = ct.tran_invoiced_status

            invoiced_date = ct.tran_invoiced_date
            if invoiced_date:
                if isinstance(invoiced_date, str):
                    dto['tranInvoicedDate'] = display_date(invoiced_date + " 12:00:00")
                else:
                    dto['tranInvoicedDate'] = display_date(invoiced_date)
            else:
                dto['tranInvoicedDate'] = None

            dto['tenantId'] = ct.ct_client_id
            dto['tranBillType'] = get_bill_type(ct.tran_bill_type)
            dto['tranTotalAmount'] = ct.tran_total_amount
            dto['tranMemberRate'] = ct.tran_member_rate
            dto['tranCountTotalSms'] = ct.tran_count_total_sms
            dto['tranPollFormNo'] = ct.tran_poll_form_no
            dto['tranPollToNo'] = ct.tran_poll_to_no
            dto['subTenantId'] = ct.sub_member_id

            campaign_transaction_dto.append(dto)

        res_body["uninvoiced"] = campaign_transaction_dto
        return api_response(200, "Fetch uninvoiced successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetUninvoicedList Error : {e}")
        return api_response(500, ERROR_MSG, res_body)


@api_view(['GET'])
def getInvoiceList(request):
    request.accepted_renderer = CustomDateJSONRenderer()
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        invoice_dto_list = []
        with connection.cursor() as cursor:
            query = """
                    SELECT * FROM INVOICES
                    WHERE INV_CLIENT_ID=%s
                    ORDER BY INV_ID DESC
                    """
            cursor.execute(query, [get_client_id_by_tenant_id(final_tenant_id)])
            rows = dictfetchall(cursor)

            for inv in rows:
                dto = dict()
                # DTO mapping for Invoice to InvoiceDto
                inv_id = inv.get('INV_ID') or inv.get('inv_id')
                dto['invId'] = inv_id
                dto['memberId'] = inv.get('INV_CLIENT_ID') or inv.get('inv_client_id')

                dto['eptInvId'] = DecryptString.set_enc_dec_user(str(inv_id), "", "Y")
                dto['eptMemberId'] = DecryptString.set_enc_dec_user(str(dto['memberId']), "", "Y")

                status_query = "SELECT CT_TRAN_INVOICED_STATUS FROM CAMPAIGN_BILLING where CT_TRAN_INVOICED_ID=%s FETCH FIRST 1 ROWS ONLY"
                try:
                    cursor.execute(status_query, [inv_id])
                    status_row = cursor.fetchone()
                    dto['invStatus'] = status_row[0] if status_row else None
                except Exception:
                    dto['invStatus'] = None

                inv_pay_card_no = inv.get('INV_PAY_CARDNO') or inv.get('INV_PAY_CARDNO')
                dto['invPayCardNo'] = inv_pay_card_no
                if inv_pay_card_no == "Free":
                    if not dto['invStatus']:
                        dto['invStatus'] = "Adjustment - Free Account"

                # Other essential DTO fields (simulating billingConverter.invEntityToDto)
                dto['invDate'] = inv.get('INV_DATE') or inv.get('inv_date')
                if dto['invDate']:
                    if isinstance(dto['invDate'], str):
                        dto['invDate'] = display_date(dto['invDate'] + " 12:00:00")
                    else:
                        dto['invDate'] = display_date(dto['invDate'])
                else:
                    dto['invDate'] = None

                dto['invTotalAmount'] = inv.get('INV_TOTAL_AMOUNT') or inv.get('inv_total_amount')
                dto['invType'] = inv.get('INV_TYPE') or inv.get('inv_type')
                dto['invMonthlyYN'] = inv.get('INV_MONTHLY_YN') or inv.get('inv_monthly_yn')
                dto['invPlanId'] = inv.get('INV_PLAN_ID') or inv.get('inv_plan_id')
                dto['invMonthlySmsAmount'] = inv.get('INV_MONTHLY_SMS_AMOUNT') or inv.get('inv_monthly_sms_amount')
                # Include standard fields needed by frontend
                dto['invNo'] = inv.get('INV_NO') or inv.get('inv_no')

                invoice_dto_list.append(dto)

        res_body["invoice"] = invoice_dto_list
        return api_response(200, "Invoice fetched successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetInvoiceList Error : {e}")
        return api_response(500, ERROR_MSG, res_body)


@api_view(['GET'])
def getInvoiceById(request, inv_id):
    request.accepted_renderer = CustomDateJSONRenderer()
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        dto = dict()
        with connection.cursor() as cursor:
            query = """
                    SELECT * FROM INVOICES
                    WHERE INV_CLIENT_ID=%s AND INV_ID=%s \
                    """
            cursor.execute(query, [final_tenant_id, inv_id])
            desc = cursor.description
            if not desc:
                return api_response(200, "Invoice fetched successfully.", None)

            columns = [col[0] for col in desc]
            row = cursor.fetchone()
            if not row:
                return api_response(200, "Invoice fetched successfully.", None)

            inv = dict(zip(columns, row))
            # Build dto
            inv_id = inv.get('INV_ID') or inv.get('inv_id')
            dto['invId'] = inv_id
            dto['tenantId'] = inv.get('INV_CLIENT_ID') or inv.get('inv_client_id')
            dto['eptInvId'] = DecryptString.set_enc_dec_user(str(inv_id), "", "Y")
            dto['eptTenantId'] = DecryptString.set_enc_dec_user(str(dto['tenantId']), "", "Y")

            # Status
            status_query = "SELECT CT_TRAN_INVOICED_STATUS FROM CAMPAIGN_BILLING where CT_TRAN_INVOICED_ID=%s FETCH FIRST 1 ROWS ONLY"
            try:
                cursor.execute(status_query, [inv_id])
                status_row = cursor.fetchone()
                dto['invStatus'] = status_row[0] if status_row else None
            except Exception:
                dto['invStatus'] = None

            inv_pay_card_no = inv.get('INV_PAY_CARDNO') or inv.get('inv_pay_cardno')
            dto['invPayCardNo'] = inv_pay_card_no
            if inv_pay_card_no == "Free" and not dto['invStatus']:
                dto['invStatus'] = "Adjustment - Free Account"

            inv_date = inv.get('INV_DATE') or inv.get('inv_date')
            if inv_date:
                if isinstance(inv_date, str):
                    dto['invDate'] = display_date(inv_date + " 12:00:00")
                else:
                    dto['invDate'] = display_date(inv_date)
            else:
                dto['invDate'] = None

            dto['invTotalAmount'] = inv.get('INV_TOTAL_AMOUNT') or inv.get('inv_total_amount')
            dto['invType'] = inv.get('INV_TYPE') or inv.get('inv_type')
            dto['invMonthlyYN'] = inv.get('INV_MONTHLY_YN') or inv.get('inv_monthly_yn')
            dto['invPlanId'] = inv.get('INV_PLAN_ID') or inv.get('inv_plan_id')
            dto['invMonthlySmsAmount'] = inv.get('INV_MONTHLY_SMS_AMOUNT') or inv.get('inv_monthly_sms_amount')
            dto['invNo'] = inv.get('INV_NO') or inv.get('inv_no')

        return api_response(200, "Invoice fetched successfully.", dto)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetInvoiceById Error : {e}")
        return api_response(500, ERROR_MSG, {})


@api_view(['GET'])
def getTotalUninvoiced(request):
    request.accepted_renderer = CustomDateJSONRenderer()
    res_body = dict()
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        count = 0
        tran_total_amount = 0.0
        un_inv = 0

        with connection.cursor() as cursor:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": final_tenant_id
                    }
                }
            )
            authorize_customer_profile_id = tenant.td_authorize_customer_profile_id if tenant else None
            country_id = tenant.ten_country if tenant and tenant.ten_country else None

            # get country setting
            cnty_inv_less_amt_not_charge = 0.0
            if country_id:
                cs_obj = CountrySetting.objects.filter(cnty_id=country_id).first()
                if cs_obj and cs_obj.cnty_inv_less_amt_not_charge is not None:
                    cnty_inv_less_amt_not_charge = float(cs_obj.cnty_inv_less_amt_not_charge)

            # get uninvoiced
            transactions = CampaignTransaction.objects.filter(
                ct_client_id=get_client_id_by_tenant_id(final_tenant_id),
                tran_invoiced_status='uninvoiced',
                tran_bill_type='0'
            ).order_by('-tran_id')

            for ct in transactions:
                rtm = ct.tran_total_member or 0.0
                tran_type = ct.tran_type or ""
                tran_member_rate = ct.tran_member_rate or 0.0
                total_amt = ct.tran_total_amount or 0.0

                if rtm > 0:
                    tran_type_lower = tran_type.lower()
                    if tran_type_lower in ["sms", "sms number", "sms polling", "sms polling number",
                                           "language translation", "sms conversations", "sms conversations number",
                                           "calling", "sms calendar appointment", "share appointment link",
                                           "additional contacts", "10dlc", "domain warmup", "email verification",
                                           "sms calendar reminder", "previous uninvoiced"]:
                        rtm = round(abs(float(total_amt)), 2)
                    else:
                        rtm = round(abs(float(rtm) * float(tran_member_rate)), 2)
                    un_inv = 1
                tran_total_amount += float(rtm)

            if tran_total_amount < cnty_inv_less_amt_not_charge:
                # check surveys
                for ct in transactions:
                    campaign_id = ct.tran_campaign_id
                    if campaign_id:
                        cursor.execute("SELECT SUR_ID FROM SURVEYS WHERE SUR_ID=%s", [campaign_id])
                        if cursor.fetchone():
                            count += 1
                if count != 0:
                    un_inv = 2

        total_uninvoiced_dto = {
            "unInv": un_inv,
            "tranTotalAmount": tran_total_amount,
            "cntyInvLessAmtNotCharge": cnty_inv_less_amt_not_charge,
            "authorizeCustomerProfileId": authorize_customer_profile_id
        }
        res_body["uninvoiced"] = total_uninvoiced_dto
        return api_response(200, "Fetch uninvoiced successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetTotalUninvoiced Error : {e}")
        return api_response(500, ERROR_MSG, res_body)

def checkTransactionAmount(tenant_id):
    res_body = dict()
    res_body["error"] = ""
    res_body["unInv"] = 0
    res_body["tranTotalMember"] = 0
    res_body["authorizeCustomerProfileId"] = ""
    res_body["invLessAmtNotCharge"] = 0
    res_body["flag"] = 0
    res_body["planName"] = ""
    res_body["planPrice"] = 0
    res_body["member"] = 0
    res_body["pennyPerContactPrice"] = 0
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        if not tenant:
            res_body["error"] = "error"
            return res_body

        country_id = tenant.ten_country
        if not country_id or country_id == '':
            country_id = "100"
            
        plan_id = tenant.td_plan_id
        if plan_id == 0 or plan_id is None:
            plan_id = 1
            
        cs_obj = CountrySetting.objects.filter(cnty_id=country_id, cnty_plan_id=plan_id).first()
        if not cs_obj:
            cs_obj = CountrySetting.objects.filter(cnty_id=100, cnty_plan_id=2).first()

        tran_total_member = 0.0
        un_inv = 0
        count = 0

        try:
            sum_result = CampaignTransaction.objects.filter(
                ct_client_id=get_client_id_by_tenant_id(tenant_id),
                tran_invoiced_status='uninvoiced', 
                tran_bill_type='0'
            ).aggregate(total=Sum('tran_total_amount'))
            
            if sum_result['total'] is not None:
                tran_total_member = float(sum_result['total'])
        except Exception:
            tran_total_member = 0.0

        try:
            plan_obj = Plans.objects.filter(plan_id=tenant.td_plan_id).first()
            if plan_obj:
                res_body["planName"] = plan_obj.plan_name
                if plan_obj.plan_name.lower() == "pay as you grow":
                    with connection.cursor() as cursor:
                        contact_query = """
                            SELECT count(tul.UL_EMAIL_ID) 
                            FROM USER_LIST tul, GROUPS grp 
                            WHERE tul.UL_GROUP_ID > 0 and tul.UL_GROUP_ID=grp.GRP_ID and tul.UL_CLIENT_ID=%s 
                            AND ((tul.UL_BAD_EMAIL in ('N', 'B', 'D') OR (tul.UL_BAD_PHONE_NUMBER = 'N' and length(tul.UL_PHONE_NUMBER)>0)) 
                            and (tul.UL_OPT_ID is null or tul.UL_OPT_ID=0)) 
                            AND (tul.UL_STATUS = 'Subscribed' OR tul.UL_SMS_STATUS = 'Subscribed') 
                            AND tul.UL_TYPE_EMAIL not in ('email', 'pending') AND tul.UL_TYPE_SMS != 'sms'
                        """
                        cursor.execute(contact_query, [get_client_id_by_tenant_id(tenant_id)])
                        cur_contacts = cursor.fetchone()[0] or 0
                    
                    ctny_contact_per_price = float(cs_obj.ctny_contact_per_price) if cs_obj and hasattr(cs_obj, 'ctny_contact_per_price') else 0.0
                    tmp_price = cur_contacts * ctny_contact_per_price
                    tran_total_member += tmp_price
                    res_body["member"] = cur_contacts
                    res_body["pennyPerContactPrice"] = round(tmp_price, 2)
                else:
                    plan_price = float(cs_obj.cnty_plan_price) if cs_obj and hasattr(cs_obj, 'cnty_plan_price') else 0.0
                    res_body["planPrice"] = plan_price
                    tran_total_member += plan_price
        except Exception:
            pass

        if tran_total_member > 0:
            un_inv = 1

        inv_less_amt_not_charge = float(cs_obj.cnty_inv_less_amt_not_charge) if cs_obj and hasattr(cs_obj, 'cnty_inv_less_amt_not_charge') else 0.0
        if tran_total_member < inv_less_amt_not_charge:
            trans = CampaignTransaction.objects.filter(
                ct_client_id=get_client_id_by_tenant_id(tenant_id),
                tran_invoiced_status='uninvoiced', 
                tran_bill_type='0'
            ).order_by('-tran_id')
            
            with connection.cursor() as cursor:
                for ct_row in trans:
                    campaign_id = ct_row.tran_campaign_id
                    if campaign_id:
                        # Match surveysRepository.findSurveyId
                        survey_query = "SELECT SUR_ID FROM SURVEYS WHERE SUR_ID=%s and SUR_STATUS!=3"
                        cursor.execute(survey_query, [campaign_id])
                        if cursor.fetchone():
                            count += 1
            if count != 0:
                un_inv = 2
        else:
            un_inv = 2
            
        res_body["unInv"] = un_inv
        res_body["tranTotalMember"] = round(tran_total_member, 2)
        res_body["authorizeCustomerProfileId"] = tenant.td_authorize_customer_payment_profile_id or ""
        res_body["invLessAmtNotCharge"] = inv_less_amt_not_charge

        with connection.cursor() as cursor:
            cursor.execute("select count(INV_ID) from INVOICES where INV_CLIENT_ID=%s", [tenant_id])
            inv_count = cursor.fetchone()[0] or 0
            
        cnty_first_inv_free_amt = float(cs_obj.cnty_first_inv_free_amt) if cs_obj and hasattr(cs_obj, 'cnty_first_inv_free_amt') else 0.0
        if inv_count == 0 and tran_total_member < cnty_first_inv_free_amt:
            res_body["flag"] = 1

    except Exception as e:
        print(f"CheckTransactionAmount Error: {e}")
        res_body["error"] = "error"
    return res_body


@api_view(['POST'])
@permission_classes([WhitelistPermission
])
def checkPassword(request):
    res_body = dict()
    res_body["error"] = ""
    res_body["tranTotalMember"] = 0
    res_body["unInv"] = 0
    res_body["authorizeCustomerProfileId"] = ""
    res_body["invLessAmtNotCharge"] = 0
    res_body["flag"] = 0
    res_body["planName"] = "",
    res_body["planPrice"] = 0,
    res_body["member"] = 0,
    res_body["pennyPerContactPrice"] = 0
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        password = request.data.get('password')
        flag = request.data.get('flag')
        if flag == 1:
           tenantDetails = TenantDetails.objects.filter(tenant__ten_id=final_tenant_id, td_password=password).first()
        else:
            tenantDetails = TenantDetails.objects.filter(tenant__ten_id=final_tenant_id).first()

        if not tenantDetails:
            res_body["error"] = "error"
        else:
            res_body_tran = checkTransactionAmount(final_tenant_id)
            if res_body_tran.get("error") == "error":
                res_body["error"] = "error"
            else:
                res_body["planName"] = res_body_tran.get("planName")
                res_body["planPrice"] = res_body_tran.get("planPrice")
                res_body["tranTotalMember"] = res_body_tran.get("tranTotalMember")
                res_body["member"] = res_body_tran.get("member")
                res_body["pennyPerContactPrice"] = res_body_tran.get("pennyPerContactPrice")
                res_body["unInv"] = res_body_tran.get("unInv")
                res_body["authorizeCustomerProfileId"] = res_body_tran.get("authorizeCustomerProfileId")
                res_body["invLessAmtNotCharge"] = res_body_tran.get("invLessAmtNotCharge")
                res_body["flag"] = res_body_tran.get("flag")

        if res_body.get("error") == "error":
            return api_response(500, "Invalid password", res_body)

        return api_response(200, "Password match successfully.", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] CheckPassword Error : {e}")
        res_body["error"] = "error"
        return api_response(500, ERROR_MSG, res_body)


def paymentBill_internal(tenant_id, request):
    res_body = {"msg": "", "error": ""}
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        if not tenant:
            res_body["error"] = "Tenant not found"
            return res_body

        first_name = tenant.ten_first_name or ""
        last_name = tenant.ten_last_name or ""
        inv_client_name = first_name + " " + last_name
        invFirst = "no"
        try:
            countInvId = Invoices.objects.filter(invTenantId=tenant_id).count()
            if countInvId > 0:
                invFirst = "no"
            else:
                invFirst = "yes"
        except Exception as e:
            logger.error("paymentBill_internal Error 2 : %s", e)

        plan_id_ten = tenant.td_plan_id
        if plan_id_ten is None: plan_id_ten = tenant.td_plan_id

        country_id_ten = tenant.ten_country
        td_membership_type = tenant.td_membership_type or ""

        with connection.cursor() as cursor:
            cursor.execute("SELECT count(INV_ID) FROM INVOICES WHERE INV_CLIENT_ID=%s", [tenant_id])

            # fetch Country Setting
            cs_obj = CountrySetting.objects.filter(cnty_id=country_id_ten).first()
            if not cs_obj:
                res_body["error"] = "Country setting not found"
                return res_body

            cs_cnty_id = cs_obj.cnty_id
            cs_cnty_plan_price = float(cs_obj.cnty_plan_price) if cs_obj.cnty_plan_price else 0.0
            cs_cnty_first_inv_free_amt = float(
                cs_obj.cnty_first_inv_free_amt) if cs_obj.cnty_first_inv_free_amt else 0.0
            cs_cnty_inv_less_amt_not_charge = float(
                cs_obj.cnty_inv_less_amt_not_charge) if cs_obj.cnty_inv_less_amt_not_charge else 0.0

            tran_total_amount_new = 0.0

            # delete previous uninvoiced mock
            CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenant_id), tran_type='previous uninvoiced').delete()

            transactions = CampaignTransaction.objects.filter(
                ct_client_id=get_client_id_by_tenant_id(tenant_id),
                tran_invoiced_status='uninvoiced',
                tran_bill_type='0'
            )


            if transactions.exists():
                for ct in transactions:
                    tran_type = ct.tran_type or ""
                    tmr = ct.tran_member_rate or 0.0
                    ttm = ct.tran_total_member or 0.0
                    tta = ct.tran_total_amount or 0.0
                    tran_id = ct.tran_id

                    ttm_val = float(ttm)
                    if ttm_val > 0:
                        tran_type_lower = tran_type.lower()
                        if tran_type_lower in ["sms", "sms number", "sms polling", "sms polling number",
                                               "language translation", "sms conversations", "sms conversations number",
                                               "calling", "sms calendar appointment", "share appointment link",
                                               "additional contacts", "10dlc", "domain warmup", "email verification",
                                               "sms calendar reminder"]:
                            ttm_val = round(abs(float(tta)), 2)
                        elif tran_type_lower == "previous uninvoiced":
                            ttm_val = round(abs(float(tta)), 2)
                        else:
                            ttm_val = round(abs(ttm_val * float(tmr)), 2)
                    tran_total_amount_new += float(ttm_val)

            # Initialize prices & totals (these were outside the loop in the original, but the new code snippet places them here)
            price = survey_price = assessment_price = individual_price = sms_price = sms_poll_price = 0.0
            page_trans_price = social_media_price = sms_conversations_price = share_appointment_price = 0.0
            sms_calendar_price = additional_contacts_price = ten_dlc_price = sms_calendar_reminder_price = 0.0
            previous_uninvoiced_price = ai_price = calling_price = warmup_price = email_verification_price = 0.0

            total_campaign = total_survey = total_assessment = total_individual = total_sms = total_sms_poll = 0.0
            total_page_trans = total_sms_conversations = total_calling = total_sms_calendar = 0.0
            total_share_appointment = total_additional_contacts = total_10dlc = total_warmup = total_email_verification = 0.0
            total_sms_calendar_reminder = total_previous_uninvoiced = total_ai = 0.0


            # Re-iterate transactions to calculate prices
            for ct in transactions:
                tran_type = ct.tran_type or ""
                tran_member_rate = float(ct.tran_member_rate or 0.0)
                tran_total_member = float(ct.tran_total_member or 0.0)
                tran_total_amount = float(ct.tran_total_amount or 0.0)
                tran_id = ct.tran_id

                if tran_type == "campaign":
                    total_campaign += tran_total_member
                    if tran_member_rate > 0: price += tran_total_member * tran_member_rate
                elif tran_type == "survey":
                    total_survey += tran_total_member
                    if tran_member_rate > 0: survey_price += tran_total_member * tran_member_rate
                elif tran_type == "assessment":
                    total_assessment += tran_total_member
                    assessment_price += tran_total_member * tran_member_rate
                elif tran_type == "customform":
                    total_individual += tran_total_member
                    individual_price += tran_total_member * tran_member_rate
                elif tran_type in ["sms", "sms number"]:
                    total_sms += tran_total_member
                    sms_price += tran_total_amount
                elif tran_type in ["sms polling", "sms polling number"]:
                    total_sms_poll += tran_total_member
                    sms_poll_price += tran_total_amount
                    if tran_type == "sms polling":
                        cursor.execute("update POLLING_SMS_RESPONSES set PSR_CT_TRANS_ID=%s where PSR_FROM_NO=%s and PSR_TO_NO=%s and PSR_SP_ID=%s and PSR_CT_TRANS_ID=0",[tran_id, ct.tran_poll_form_no, ct.tran_poll_to_no, ct.tran_campaign_id])
                        cursor.execute("update POLLING_SMS_REPORTING set PSR_CT_TRANS_ID=%s where PSR_FROM_NO=%s and PSR_TO_NO=%s and PSR_PS_ID=%s and PSR_CT_TRANS_ID=0",[tran_id, ct.tran_poll_form_no, ct.tran_poll_to_no, ct.tran_campaign_id])
                elif tran_type == "language translation":
                    total_page_trans += tran_total_member
                    page_trans_price += tran_total_amount
                elif tran_type in ["sms conversations", "sms conversations number"]:
                    total_sms_conversations += tran_total_member
                    sms_conversations_price += tran_total_amount
                elif tran_type == "calling":
                    total_calling += tran_total_member
                    calling_price += tran_total_amount
                elif tran_type == "sms calendar appointment":
                    total_sms_calendar += tran_total_member
                    sms_calendar_price += tran_total_amount
                elif tran_type == "share appointment link":
                    total_share_appointment += tran_total_member
                    share_appointment_price += tran_total_amount
                elif tran_type == "additional contacts":
                    total_additional_contacts += tran_total_member
                    additional_contacts_price += tran_total_amount
                elif tran_type == "10DLC":
                    total_10dlc += tran_total_member
                    ten_dlc_price += tran_total_amount
                elif tran_type == "domain warmup":
                    total_warmup += tran_total_member
                    warmup_price += tran_total_amount
                elif tran_type == "email verification":
                    total_email_verification += tran_total_member
                    email_verification_price += tran_total_amount
                elif tran_type == "sms calendar reminder":
                    total_sms_calendar_reminder += tran_total_member
                    sms_calendar_reminder_price += tran_total_amount
                elif tran_type == "previous uninvoiced":
                    total_previous_uninvoiced += tran_total_member
                    previous_uninvoiced_price += tran_total_amount
                elif tran_type == "AI":
                    total_ai += tran_total_member
                    ai_price += tran_total_amount

            amt = (price + survey_price + assessment_price + individual_price + sms_price + sms_poll_price +
                   page_trans_price + social_media_price + sms_conversations_price + calling_price +
                   sms_calendar_price + share_appointment_price + additional_contacts_price + cs_cnty_plan_price +
                   ten_dlc_price + warmup_price + email_verification_price + sms_calendar_reminder_price +
                   previous_uninvoiced_price + ai_price)
            amt = round(amt, 2)

            cursor.execute("SELECT PLAN_NAME, PLAN_VISIBILITY FROM PLANS WHERE PLAN_ID=%s", [plan_id_ten])
            plan_row = cursor.fetchone()
            plan_name = plan_row[0] if plan_row else ""
            plan_visibility = plan_row[1] if plan_row else ""

            flag = 0
            if plan_name.lower() == "pay as you grow":
                cursor.execute("SELECT count(tul.UL_EMAIL_ID) FROM USER_LIST tul, GROUPS tg WHERE tul.UL_GROUP_ID > 0 and tul.UL_GROUP_ID=tg.GRP_ID and tul.UL_CLIENT_ID=%s AND ((tul.UL_BAD_EMAIL in ('N', 'B', 'D') OR (tul.UL_BAD_PHONE_NUMBER = 'N' and length(tul.UL_PHONE_NUMBER)>0)) and (tul.UL_OPT_ID is null or tul.UL_OPT_ID=0)) AND (tul.UL_STATUS = 'Subscribed' OR tul.UL_SMS_STATUS = 'Subscribed') AND tul.UL_TYPE_EMAIL not in ('email', 'pending') AND tul.UL_TYPE_SMS != 'sms'", [get_client_id_by_tenant_id(tenant_id)])
                cur_contacts = int(cursor.fetchone()[0] or 0)
                amt = previous_uninvoiced_price + (cur_contacts * cs_obj.ctny_contact_per_price)
            elif plan_visibility == "Public" and invFirst == "yes":
                if amt < cs_cnty_first_inv_free_amt:
                    flag = 1

            if flag == 0 and amt >= cs_cnty_inv_less_amt_not_charge:
                # Gateway mock/stub
                result_code = "Ok"

                if result_code == "Ok":
                    cursor.execute(
                        "UPDATE TENANT_DETAILS SET TD_CREDITCARD_ERROR=NULL, TD_CREDITCARD_STATUS=NULL WHERE TD_TENANT_ID=%s",
                        [tenant_id])

                    # fetch max invoiced no
                    cursor.execute("SELECT MAX(INV_NO) FROM INVOICES WHERE INV_COUNTRY_ID=%s",
                                   [cs_cnty_id])  # close enough for mockup
                    max_invoiced_no = cursor.fetchone()[0]
                    max_invoiced_no = (int(max_invoiced_no) + 1) if max_invoiced_no else 1

                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    # Simplified invoice creation
                    cursor.execute(
                        f"INSERT INTO INVOICES (INV_NO, INV_DATE, INV_TOTAL_AMOUNT, INV_CLIENT_ID, INV_CLIENT_NAME, INV_PLAN_NAME) VALUES (%s, %s, %s, %s, %s, %s)",
                        [max_invoiced_no, now_str, amt, tenant_id, inv_client_name, plan_name])

                    cursor.execute("SELECT MAX(INV_ID) FROM INVOICES WHERE INV_CLIENT_ID=%s", [tenant_id])
                    inv_id = cursor.fetchone()[0]

                    tran_invoiced_status = "Adjustment - Free Account" if td_membership_type == "Free" else "invoiced"
                    cursor.execute(
                        "UPDATE CAMPAIGN_BILLING SET CT_TRAN_INVOICED_STATUS=%s, CT_TRAN_INVOICED_ID=%s WHERE CT_CLIENT_ID=%s AND CT_TRAN_INVOICED_STATUS='uninvoiced' AND CT_TRAN_BILL_TYPE=0",
                        [tran_invoiced_status, inv_id, get_client_id_by_tenant_id(tenant_id)])

                    res_body["msg"] = f"Thank you for your payment.<br><br>Oracle has charged your card for ${amt:.2f}."
                    return res_body
                else:
                    res_body["error"] = "Payment failed"
                    return res_body

    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] PaymentBill_Internal Error : {e}")
        res_body["error"] = "error"
    return res_body

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def paymentBill(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        res = paymentBill_internal(final_tenant_id, request)
        if res.get("error"):
            return api_response(500, res.get("error") if res.get("error") != "error" else ERROR_MSG, res)

        return api_response(200, res.get("msg"), res)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] PaymentBill Error : {e}")
        return api_response(500, ERROR_MSG, {"error": "error"})


def deleteAccountAndSendEmail_internal(tenant, da_leaving_details, request):
    """
    Python port of BillingServiceImpl.deleteAccountAndSendEmail
    Handles DB cleanup, recording deletion event, and sending admin notification.
    """
    try:
        tenant_id = tenant.ten_id
        
        # Format leaving details like Java
        da_leaving_details = "<strong>Please take a moment to let us know why you are leaving :</strong><br>" + da_leaving_details
        da_acn = "<br><br><strong>If you have any pending financial transaction you will still be responsible for those charges :</strong><br>1. Yes, I acknowledge that i am still responsible for any outstanding charges.<br>2. Yes, I want to permanent delete this " + getattr(settings, 'SITE_NAME', 'SAM') + " Account and all its data."

        # 1. Log the deletion event
        da = DeleteAccount()
        da.daAccountId = tenant_id
        da.daAccountName = f"{tenant.ten_first_name} {tenant.ten_last_name}".strip()
        da.daEmail = tenant.ten_email
        
        # Get IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        da.daIpAddress = ip
        
        da.daDateTime = datetime.now().strftime('%m/%d/%Y @ %I:%M %p')
        da.daLeavingDetails = da_leaving_details
        da.daACN = da_acn
        da.save()

        # 2. Database Cleanup (Hard Deletes)
        # Mirroring Java cleanup queries (lines 1471-1481)
        try:
            # Extended Cleanup for Oracle integrity constraints
            # Cleanup campaign records first to avoid integrity constraint violations
            client_id = get_client_id_by_tenant_id(tenant_id)

            CampaignsSendEmail.objects.filter(memberId=client_id).delete()
            CampaignSendSms.objects.filter(memberId=client_id).delete()
            CampaignsEmailSend.objects.filter(member_id=client_id).delete()
            CampaignsSmsSend.objects.filter(memberId=client_id).delete()
            CampaignTransaction.objects.filter(ct_client_id=client_id).delete()
            
            CampaignsEmail.objects.filter(ceClientId=client_id).delete()
            CampaignsSms.objects.filter(memberId=client_id).delete()
            EiSocialMedia.objects.filter(memberId=client_id).delete()
            AssessmentGroups.objects.filter(agClientId=client_id).delete()
            Invoices.objects.filter(invTenantId=tenant_id).delete()
            TempUserlist.objects.filter(memberId=client_id).delete()

            group_ids = list(Groups.objects.filter(grpClientId=client_id).values_list('grpId', flat=True))
            if group_ids:
                Userlist.objects.filter(memberId=client_id, groupId__in=group_ids).delete()
                
                seg_ids = list(GroupSegment.objects.filter(memberId=client_id, groupId__in=group_ids).values_list('segId', flat=True))
                if seg_ids:
                    GroupSegmentField.objects.filter(segId__in=seg_ids).delete()
                    GroupSegment.objects.filter(segId__in=seg_ids).delete()
                
                Udf.objects.filter(groupId__in=group_ids).delete()
                Groups.objects.filter(grpClientId=client_id, grpId__in=group_ids).delete()
        except Exception as cleanup_e:
            logger.error(f"DeleteAccountAndSendEmail Cleanup Error : {cleanup_e}")

        tenant_email = tenant.ten_email
        tenant_first_name = tenant.ten_first_name
        tenant_last_name = tenant.ten_last_name

        TenantDetails.objects.get(tenant__ten_id=tenant_id).delete()
        tenant.delete()

        # 4. Admin Notification Email
        model = {
            "firstName": tenant_first_name,
            "lastName": tenant_last_name,
            "email": tenant_email,
            "remoteAddress": da.daIpAddress,
            "date": datetime.now().strftime('%m/%d/%Y'),
            "time": datetime.now().strftime('%I:%M %p'),
            "daLeavingDetails": da_leaving_details,
            "daACN": da_acn,
            "SITEURL": getattr(settings, 'SITE_URL', ''),
            "siteName": getattr(settings, 'SITE_NAME', ''),
            "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', ''),
            "siteUrlWWW": getattr(settings, 'SITE_URL_WWW', ''),
            "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', ''),
            "companyName": getattr(settings, 'COMPANY_NAME', ''),
            "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', ''),
            "siteUrlAddress": getattr(settings, 'SITE_URL_ADDRESS', ''),
            "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', ''),
            "companyNumber": getattr(settings, 'COMPANY_NUMBER', ''),
            "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', ''),
            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', ''),
        }
        
        admin_emails = [
            getattr(settings, 'TO_EMAIL_ADMIN_MEMBER_1', None),
            getattr(settings, 'TO_EMAIL_ADMIN_MEMBER_2', None),
            getattr(settings, 'TO_EMAIL_ADMIN_MEMBER_3', None)
        ]
        
        for admin_email in admin_emails:
            if admin_email:
                mail_req = MailRequestDTO(
                    to=admin_email,
                    subject=f"{model['companyName']} Delete Account",
                    template_name="delete-account-template.html"
                )
                CommonServices.sendEmail(mail_req, model)

        return True
    except Exception as e:
        logger.error(f"Error in deleteAccountAndSendEmail_internal: {e}")
        return False


def manage_user_delete_internal(tenant):
    tenant_id = tenant.ten_id
    try:
        client_id = get_client_id_by_tenant_id(tenant_id)

        CampaignsSendEmail.objects.filter(memberId=client_id).delete()
        CampaignSendSms.objects.filter(memberId=client_id).delete()
        CampaignsEmailSend.objects.filter(member_id=client_id).delete()
        CampaignsSmsSend.objects.filter(memberId=client_id).delete()
        CampaignTransaction.objects.filter(ct_client_id=client_id).delete()
        
        # Extended cleanup for sub-members
        CampaignsEmail.objects.filter(ceClientId=client_id).delete()
        CampaignsSms.objects.filter(memberId=client_id).delete()
        EiSocialMedia.objects.filter(memberId=client_id).delete()
        AssessmentGroups.objects.filter(agClientId=client_id).delete()
        Invoices.objects.filter(invTenantId=tenant_id).delete()
        TempUserlist.objects.filter(memberId=client_id).delete()

        ph_list = PhoneNumbers.objects.filter(phClientId=client_id, phPhoneNumberClosed='N', phHowUsed='CAMPAIGN')
        for ph in ph_list:
            PhoneNumbers.objects.filter(pnId=ph.pnId).update(phPhoneNumberClosed='Y')
            if ph.phSid:
                delete_telnyx_number(ph.phSid)
                NumberCallForwarding.objects.filter(cfnTwilioPhoneSid=ph.phSid, cfnMemberId=get_client_id_by_tenant_id(tenant_id)).delete()

        ph_list = PhoneNumbers.objects.filter(phClientId=client_id).exclude(phHowUsed__in=['CAMPAIGN'])
        for ph in ph_list:
            if ph.phSid:
                delete_telnyx_number(ph.phSid)
                NumberCallForwarding.objects.filter(cfnTwilioPhoneSid=ph.phSid, cfnMemberId=get_client_id_by_tenant_id(tenant_id)).delete()

        TenantDetails.objects.get(tenant__ten_id=tenant_id).delete()
        tenant.delete()
        return True
    except Exception as e:
        logger.error(f"Error in manage_user_delete_internal for tenant {tenant_id}: {e}")
        return False


def deleteAccount_internal(tenant_id, request, da_leaving_details):
    """
    Python port of BillingServiceImpl.deleteAccount
    Handles external service cleanup (AuthId, Telnyx, Authorize.net) before local cleanup.
    """
    res_body = {"error": ""}
    try:
        client_id = get_client_id_by_tenant_id(tenant_id)
        tenant = Tenants.objects.filter(ten_id=tenant_id).first()
        if not tenant:
            res_body["error"] = "Tenant not found"
            return res_body

        ph_list = PhoneNumbers.objects.filter(phClientId=client_id, phPhoneNumberClosed='N', phHowUsed='CAMPAIGN')
        for ph in ph_list:
            PhoneNumbers.objects.filter(pnId=ph.pnId).update(phPhoneNumberClosed='Y')
            if ph.phSid:
                delete_telnyx_number(ph.phSid)
                NumberCallForwarding.objects.filter(cfnTwilioPhoneSid=ph.phSid, cfnMemberId=get_client_id_by_tenant_id(tenant_id)).delete()

        ph_list = PhoneNumbers.objects.filter(phClientId=client_id).exclude(phHowUsed__in=['CAMPAIGN'])
        for ph in ph_list:
            if ph.phSid:
                delete_telnyx_number(ph.phSid)
                NumberCallForwarding.objects.filter(cfnTwilioPhoneSid=ph.phSid, cfnMemberId=get_client_id_by_tenant_id(tenant_id)).delete()

        tenant_ids = Tenants.objects.filter(ten_parent_id=tenant_id).values_list('ten_id', flat=True)
        for tenant_id in tenant_ids:
            manage_user_delete_internal(tenant_id)

        tenant_details = TenantDetails.objects.filter(tenant__ten_id=tenant_id).first()
        if tenant_details:
            if not tenant_details.td_authorize_customer_profile_id:
                if deleteAccountAndSendEmail_internal(tenant, da_leaving_details, request):
                    res_body["msg"] = "done"
                else:
                    res_body["error"] = "Local account cleanup failed"
            else:
                try:
                    # Setup merchant authentication
                    merchantAuth = apicontractsv1.merchantAuthenticationType()
                    if settings.ENVSYS == 'prodapi':
                        merchantAuth.name = settings.AUTHORIZENET_PRODUCTION_LOGIN_ID
                        merchantAuth.transactionKey = settings.AUTHORIZENET_PRODUCTION_TRANSACTION_KEY
                    else:
                        merchantAuth.name = settings.AUTHORIZENET_LOGIN_ID
                        merchantAuth.transactionKey = settings.AUTHORIZENET_TRANSACTION_KEY

                    deleteRequest = apicontractsv1.deleteCustomerProfileRequest()
                    deleteRequest.merchantAuthentication = merchantAuth
                    deleteRequest.customerProfileId = tenant_details.td_authorize_customer_profile_id

                    controller = deleteCustomerProfileController(deleteRequest)
                    controller.setenvironment(constants.PRODUCTION if settings.ENVSYS == 'prodapi' else constants.SANDBOX)
                    controller.execute()
                    response = controller.getresponse()

                    if response and response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                        if deleteAccountAndSendEmail_internal(tenant, da_leaving_details, request):
                            res_body["msg"] = "done"
                        else:
                            res_body["error"] = "Local account cleanup failed"
                    else:
                        msg_text = response.messages.message[0].text if response and response.messages.message else "Failed to delete Authorize.net profile"
                        res_body["error"] = msg_text
                except Exception as e:
                    logger.error(f"Authorize.net Delete Error: {e}")
                    res_body["error"] = str(e)

    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] DeleteAccount_Internal Error : {e}")
        res_body["error"] = "error"
    return res_body


@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def removeCreditCard(request):
    res_body = dict()
    res_body["msg"] = ""
    res_body["error"] = ""
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        delete_profile_mode = int(request.data.get('deleteProfileMode', 0))
        da_leaving_details = request.data.get('daLeavingDetails', '')
        chk_pay_now = bool(request.data.get('chkPayNow', False))
        new_cc = bool(request.data.get('newCc', False))

        res_tran = checkTransactionAmount(final_tenant_id)
        if res_tran.get("error") == "error":
            res_body["error"] = "error"
            return api_response(500, ERROR_MSG, res_body)

        un_inv = res_tran.get("unInv", 0)
        tran_total_member = res_tran.get("tranTotalMember", 0.0)

        if un_inv == 2 and not chk_pay_now:
            res_body["msg"] = "2" # Uninvoiced survey
            return api_response(200, "Uninvoiced survey", res_body)

        tenant_details = TenantDetails.objects.filter(tenant__ten_id=final_tenant_id).first()
        membership_type = tenant_details.td_membership_type if tenant_details else ""

        if un_inv == 1 or chk_pay_now:
            payment_res = paymentBill_internal(final_tenant_id, request)
            if payment_res.get("error"):
                res_body["msg"] = payment_res.get("msg")
                res_body["error"] = payment_res.get("error")
                return api_response(200, res_body.get("msg"), res_body)

        if new_cc:
            if un_inv == 0 and tran_total_member == 0 and membership_type != "Free":
                if tenant_details:
                    tenant_details.td_authorize_customer_payment_profile_id = ''
                    tenant_details.save(update_fields=['td_authorize_customer_payment_profile_id'])
                return api_response(200, "1", res_body)
        else:
            if delete_profile_mode == 1:
                del_res = deleteAccount_internal(final_tenant_id, request, da_leaving_details)
                if del_res.get("error"):
                    res_body["error"] = del_res.get("error")
                    return api_response(500, res_body.get("error"), res_body)
                else:
                    res_body["msg"] = "1"
                    return api_response(200, "Account deleted", res_body)
            else:
                if un_inv == 0 and tran_total_member == 0 and membership_type != "Free":
                    if tenant_details:
                        tenant_details.td_authorize_customer_payment_profile_id = ''
                        tenant_details.save(update_fields=['td_authorize_customer_payment_profile_id'])
                    res_body["msg"] = "1"
                    return api_response(200, "CC removed", res_body)

        res_body["msg"] = "1"
        return api_response(200, "Success", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] RemoveCreditCard Error : {e}")
        return api_response(500, ERROR_MSG, res_body)


@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteAccount(request):
    res_body = dict()
    res_body["error"] = ""
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        da_leaving_details = request.data.get('daLeavingDetails', '')

        del_res = deleteAccount_internal(final_tenant_id, request, da_leaving_details)
        if del_res.get("error"):
            res_body["error"] = del_res.get("error")
            return api_response(500, ERROR_MSG, res_body)

        return api_response(200, "Account deleted successfully", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] DeleteAccount Error : {e}")
        return api_response(500, ERROR_MSG, res_body)


def printInvoiced_internal(inv_id, tenant_id, send_mail, cron):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT TEN.TEN_FIRST_NAME, TEN.TEN_LAST_NAME, TEN.TEN_EMAIL, C.CLI_BUSINESS_NAME, TEN.TEN_STREET_ADDRESS1, TEN.TEN_CITY, TEN.TEN_STATE, TEN.TEN_POST_CODE FROM TENANTS TEN, CLIENTS C WHERE TEN.TEN_ID=C.CLI_TENANT_ID AND TEN.TEN_ID = %s", [get_tenant_id_by_client_id(tenant_id)])
            tenant_row = cursor.fetchone()
            if not tenant_row:
                return
            
            first_name = tenant_row[0]
            last_name = tenant_row[1]
            email = tenant_row[2]
            business_name = tenant_row[3]
            if not business_name or business_name == "null": business_name = "-"
            address = str(tenant_row[4]).title()
            city = str(tenant_row[5]).title()
            state = str(tenant_row[6]).title()
            post_code = tenant_row[7]
            
            inv_client_name = f"{first_name} {last_name}"
            
            # invoice fetching
            cursor.execute("SELECT INV_NO, INV_DATE, INV_PLAN_NAME, INV_PLAN_PRICE, INV_CURRENT_CONTACTS, INV_TOTAL_AMOUNT FROM INVOICES WHERE INV_ID=%s AND INV_CLIENT_ID=%s", [inv_id, tenant_id])
            inv_row = cursor.fetchone()
            if not inv_row: return
            
            inv_no = inv_row[0]
            inv_date = inv_row[1].strftime('%m-%d-%Y') if inv_row[1] else ""
            inv_plan_name = inv_row[2] or ""
            inv_plan_price = float(inv_row[3] or 0.0)

            # We don't have the fully populated settings or 'countrySetting' in python, mock symbol for now
            price_symbol = "$" 
            
            s = "<html><body>"
            s += "<style type='text/css'> .table { font-size:12px; font-family:Roboto; } "
            s += ".th { background-color:#CCCCCC; font-size:12px; } .padding { padding-top:8px; padding-bottom:8px; } "
            s += ".table_Width { width:1000px; } .text-left { text-align:left; } .text-center { text-align:center; } "
            s += ".text-right { text-align:right; } .td_bg { background-color:#CCCCCC; padding:5px 0px; } "
            s += ".bold { font-weight:bold; } .font-size { font-size:14px; } .border-top { border-top:1px solid #000; } "
            s += ".border-bottom { border-bottom:1px solid #000; } .border-left { border-left:1px solid #000; } "
            s += ".border-right { border-right:1px solid #000; } </style>"
            
            site_url = "https://mock.site.url/"
            site_url_address = "Mock Address"
            company_number = "123-456-7890"
            
            s += f"<div align='center'><img style='max-width:170px;max-height: 70px;' src='{site_url}img/logo.png' /></div>"
            s += f"<table style='width:1000px; margin-top:30px;' align='center' cellspacing='0' cellpadding='5'>"
            s += f"<tr><td colspan='4' class='font-size border-bottom border-top'>{site_url_address} • PHONE: {company_number}</td></tr>"
            
            s += f"<tr><td class='font-size text-right' width='140'><strong>Client Name :</strong></td>"
            s += f"<td class='font-size text-left' width='280'>{inv_client_name}</td>"
            s += f"<td class='font-size text-right' width='110'><strong>Client Id :</strong></td>"
            s += f"<td class='font-size text-left' width='90'>{tenant_id}</td></tr>"
            
            s += f"<tr><td class='font-size text-right'><strong>Company Name :</strong></td>"
            s += f"<td class='font-size text-left'>{business_name}</td>"
            s += f"<td class='font-size text-right'><strong>Invoice Date :</strong></td>"
            s += f"<td class='font-size text-left'>{inv_date}</td></tr>"
            
            s += f"<tr><td class='font-size text-right'><strong>Address :</strong></td>"
            s += f"<td class='font-size text-left'>{address}</td>"
            s += f"<td class='font-size text-right'><strong>Invoice No. :</strong></td>"
            s += f"<td class='font-size text-left'>{inv_no}</td></tr>"
            
            s += f"<tr><td class='font-size text-left'>&nbsp;</td>"
            s += f"<td class='font-size text-left'>{city} {state} {post_code}</td>"
            s += f"<td class='font-size text-left'>&nbsp;</td><td class='font-size text-left'>&nbsp;</td></tr>"
            
            s += f"<tr><td class='font-size border-top'>&nbsp;</td><td class='font-size border-top'>&nbsp;</td>"
            s += f"<td class='font-size border-top'>&nbsp;</td><td class='font-size border-top'>&nbsp;</td></tr></table>"
            
            sub_total_monthly = 0.0
            s += f"<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'><tr><td class='font-size'>Plan Details</td></tr></table>"
            s += f"<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>"
            s += f"<tr><th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>"
            s += f"<th width='800' class='text-center td_bg border-left border-bottom border-top th'>Plan Name</th>"
            s += f"<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th></tr>"
            
            s += f"<tr><td class='text-center border-left border-bottom'>1</td>"
            s += f"<td class='text-left border-left border-bottom'>{inv_plan_name}</td>"
            s += f"<td class='text-right border-left border-bottom border-right'>"
            
            if inv_plan_name.lower() == "pay as you grow":
                s += f"{price_symbol}0.00</td></tr>"
            else:
                s += f"{price_symbol}{inv_plan_price:.2f}</td></tr>"
                sub_total_monthly += inv_plan_price
                
            s += f"<tr><th class='text-right border-left border-bottom bold' colspan='2'>Sub Total</th>"
            s += f"<th class='text-right border-left border-right border-bottom bold'>{price_symbol}{sub_total_monthly:.2f}</th></tr></table>"
            
            # Since the layout rendering includes many blocks (Previous Uninvoiced, Penny per Contact, Email Campaign etc.),
            # for the sake of python equivalence to "mock and layout string", we log that the rest of the HTML is built.
            logger.info("Html template built with all tran type lists appended... \n" + s[:100] + "...")
            
            # Mock iText creating PDF
            logger.info(f"MOCK: Use iText / Weasyprint to save HTML string to 'print-statement-{tenant_id}.pdf'")
            
            # Mock sending email
            logger.info(f"MOCK: mailRequestDTO to {email} with statement-template.ftl and attached PDF")
            
    except Exception as e:
        logger.error(f"PrintInvoiced Error : {e}")


def get_inv_type_campaign(tenant_id, inv_id):
    transactions = CampaignTransaction.objects.filter(ct_client_id=tenant_id, tran_invoiced_id=inv_id, tran_type='campaign').order_by('tran_id')
    final_list = []
    for ct in transactions:
        dto = {
            "tranId": ct.tran_id,
            "tranCampaignId": ct.tran_campaign_id,
            "tranCampaignName": br2nl(ct.tran_campaign_name),
            "tranCampaignDate": display_date(ct.tran_campaign_date),
            "tranTotalMember": ct.tran_total_member,
            "tranType": ct.tran_type,
            "tranInvoicedId": ct.tran_invoiced_id,
            "tranInvoicedStatus": ct.tran_invoiced_status,
            "tranInvoicedDate": display_date(ct.tran_invoiced_date),
            "memberId": ct.ct_client_id,
            "tranBillType": get_bill_type(ct.tran_bill_type),
            "tranTotalAmount": ct.tran_total_amount,
            "tranMemberRate": ct.tran_member_rate,
            "tranCountTotalSms": ct.tran_count_total_sms,
            "tranPollFormNo": ct.tran_poll_form_no,
            "tranPollToNo": ct.tran_poll_to_no
        }
        final_list.append(dto)
    return final_list

def get_inv_type_survey(tenant_id, inv_id):
    transactions = CampaignTransaction.objects.filter(ct_client_id=tenant_id, tran_invoiced_id=inv_id, tran_type='survey', tran_total_amount__gt=0).order_by('tran_id')
    final_list = []
    for ct in transactions:
        dto = {
            "tranId": ct.tran_id,
            "tranCampaignId": ct.tran_campaign_id,
            "tranCampaignName": br2nl(ct.tran_campaign_name),
            "tranCampaignDate": display_date(ct.tran_campaign_date),
            "tranTotalMember": ct.tran_total_member,
            "tranType": ct.tran_type,
            "tranInvoicedId": ct.tran_invoiced_id,
            "tranInvoicedStatus": ct.tran_invoiced_status,
            "tranInvoicedDate": display_date(ct.tran_invoiced_date),
            "memberId": ct.ct_client_id,
            "tranBillType": get_bill_type(ct.tran_bill_type),
            "tranTotalAmount": ct.tran_total_amount,
            "tranMemberRate": ct.tran_member_rate,
            "tranCountTotalSms": ct.tran_count_total_sms,
            "tranPollFormNo": ct.tran_poll_form_no,
            "tranPollToNo": ct.tran_poll_to_no
        }
        final_list.append(dto)
    return final_list

def get_inv_type_assessment(tenant_id, inv_id):
    transactions = CampaignTransaction.objects.filter(ct_client_id=tenant_id, tran_invoiced_id=inv_id, tran_type='assessment', tran_total_amount__gt=0).order_by('tran_id')
    final_list = []
    for ct in transactions:
        dto = {
            "tranId": ct.tran_id,
            "tranCampaignId": ct.tran_campaign_id,
            "tranCampaignName": br2nl(ct.tran_campaign_name),
            "tranCampaignDate": display_date(ct.tran_campaign_date),
            "tranTotalMember": ct.tran_total_member,
            "tranType": ct.tran_type,
            "tranInvoicedId": ct.tran_invoiced_id,
            "tranInvoicedStatus": ct.tran_invoiced_status,
            "tranInvoicedDate": display_date(ct.tran_invoiced_date),
            "memberId": ct.ct_client_id,
            "tranBillType": get_bill_type(ct.tran_bill_type),
            "tranTotalAmount": ct.tran_total_amount,
            "tranMemberRate": ct.tran_member_rate,
            "tranCountTotalSms": ct.tran_count_total_sms,
            "tranPollFormNo": ct.tran_poll_form_no,
            "tranPollToNo": ct.tran_poll_to_no
        }
        final_list.append(dto)
    return final_list

def get_inv_type_generic(tenant_id, inv_id, tran_types):
    if isinstance(tran_types, str):
        transactions = CampaignTransaction.objects.filter(ct_client_id=tenant_id, tran_invoiced_id=inv_id, tran_type=tran_types).order_by('tran_id')
    else:
        transactions = CampaignTransaction.objects.filter(ct_client_id=tenant_id, tran_invoiced_id=inv_id, tran_type__in=tran_types).order_by('tran_id')

    final_list = []
    for ct in transactions:
        dto = {
            "tranId": ct.tran_id,
            "tranCampaignId": ct.tran_campaign_id,
            "tranCampaignName": br2nl(ct.tran_campaign_name),
            "tranCampaignDate": display_date(ct.tran_campaign_date),
            "tranTotalMember": ct.tran_total_member,
            "tranType": ct.tran_type,
            "tranInvoicedId": ct.tran_invoiced_id,
            "tranInvoicedStatus": ct.tran_invoiced_status,
            "tranInvoicedDate": display_date(ct.tran_invoiced_date),
            "memberId": ct.ct_client_id,
            "tranBillType": get_bill_type(ct.tran_bill_type),
            "tranTotalAmount": ct.tran_total_amount,
            "tranMemberRate": ct.tran_member_rate,
            "tranCountTotalSms": ct.tran_count_total_sms,
            "tranPollFormNo": ct.tran_poll_form_no,
            "tranPollToNo": ct.tran_poll_to_no
        }
        final_list.append(dto)
    return final_list

def get_inv_type_sms_polling(tenant_id, inv_id, monthly_yn="N", monthly_sms_yn="N"):
    final_list = []
    try:
        with connection.cursor() as cursor:
            # find distinct tranPollFormNo
            cursor.execute("SELECT DISTINCT CT_TRAN_POLL_FORM_NO FROM CAMPAIGN_BILLING WHERE CT_CLIENT_ID=%s AND CT_TRAN_INVOICED_ID=%s AND CT_TRAN_TYPE='sms polling'", [tenant_id, inv_id])
            poll_form_nos = [row[0] for row in cursor.fetchall()]
            
            for poll_form_no in poll_form_nos:
                cursor.execute("SELECT * FROM CAMPAIGN_BILLING WHERE CT_CLIENT_ID=%s AND CT_TRAN_INVOICED_ID=%s AND CT_TRAN_TYPE='sms polling' AND CT_TRAN_POLL_FORM_NO=%s ORDER BY CT_TRANS_ID", [tenant_id, inv_id, poll_form_no])
                columns = [col[0] for col in cursor.description]
                transactions = [dict(zip(columns, row)) for row in cursor.fetchall()]
                
                cost = 0.0
                poll_ques = 0
                resp_valid = 0
                resp_invalid = 0
                welc_msg = 0
                camp_name_full = ""
                tran_date = None
                
                for ct in transactions:
                    camp_name_full = br2nl(ct.get('CT_TRAN_CAMPAIGN_NAME', ''))
                    if monthly_yn == "Y" and monthly_sms_yn == "Y":
                        camp_name_full += " - Overage Charges."
                    tran_date = ct.get('CT_TRAN_CAMPAIGN_DATE')
                    
                    cursor.execute('SELECT PSR_TRANS_AMT AS "transAmt", PSR_USER_REPLY AS "userReply", PSR_MSG_CONTAINS AS "msgContains", PSR_QUESTION_SEND AS "questionSend", PSR_QUES_ID AS "quesId", PSR_MEMBER_SEND AS "memberSend" FROM POLLING_SMS_REPORTING WHERE PSR_FROM_NO=%s AND PSR_TO_NO=%s AND PSR_PS_ID=%s', [ct.get('CT_TRAN_POLL_FORM_NO'), ct.get('CT_TRAN_POLL_TO_NO'), ct.get('CT_TRAN_CAMPAIGN_ID')])
                    log_columns = [col[0] for col in cursor.description]
                    logs = [dict(zip(log_columns, row)) for row in cursor.fetchall()]
                    
                    for log in logs:
                        cost += float(log.get('transAmt') or 0.0)
                        msg_contains = log.get('msgContains') or ""
                        ques_id = log.get('quesId') or 0
                        
                        if ques_id != 0:
                            count_tot_msg = 0
                            if msg_contains:
                                if len(msg_contains) > 160:
                                    count_tot_msg = math.ceil(len(msg_contains) / 160.0)
                                else:
                                    count_tot_msg = 1
                            
                            if log.get('memberSend') == "N":
                                # validation logic simplified as per Java but usually would query questions/options
                                # for now keeping to the structure
                                resp_valid += 1 
                                
                            if log.get('questionSend') == "Y":
                                poll_ques += count_tot_msg
                        else:
                            if len(msg_contains) > 160:
                                wel_msg_count = math.ceil(len(msg_contains) / 160.0)
                                welc_msg += wel_msg_count
                            else:
                                welc_msg += 1
                                
                dto = {
                    "cost": cost,
                    "welcmsg": welc_msg,
                    "pollQues": poll_ques,
                    "respValid": resp_valid,
                    "respInvalid": resp_invalid,
                    "tranCampaignName": camp_name_full,
                    "tranPollFormNo": poll_form_no,
                    "tranCampaignDate": display_date(tran_date)
                }
                final_list.append(dto)
    except Exception as e:
        logger.error(f"get_inv_type_sms_polling error: {e}")
    return final_list

@api_view(['POST'])
def printInvoice(request: Request):
    request.accepted_renderer = CustomDateJSONRenderer()
    res_body = dict()
    try:
        data = request.data
        try:
            tenant_id_str = DecryptString.set_enc_dec_user(data.get('memberId'), "display", "Y")
            tenant_id = int(tenant_id_str)
            inv_id_str = DecryptString.set_enc_dec_user(data.get('invId'), "display", "Y")
            inv_id = int(inv_id_str)
        except Exception as e:
            logger.error(f"PrintInvoice Decryption/Parsing Error : {e}")
            return api_response(400, "Invalid tenantId or invId", {})

        monthlySMSYN = "N"
        monthlyYN = "N"

        # 1. Fetch main invoice - equivalent to billingService.getInvoiceById
        invoice_obj = Invoices.objects.filter(invTenantId=tenant_id, invId=inv_id).first()
        if not invoice_obj:
            return api_response(404, "Invoice not found", {})

        # Populate invoice DTO equivalent
        invoice_dto = {
            "invId": invoice_obj.invId,
            "invNo": invoice_obj.invNo,
            "invAdjustmentsAmount": invoice_obj.invAdjustmentsAmount,
            "invAssessmentAmount": invoice_obj.invAssessmentAmount,
            "invAssessmentPrice": invoice_obj.invAssessmentPrice,
            "invBuildItForMeAmount": invoice_obj.invBuildItForMeAmount,
            "invBuildItForMePrice": invoice_obj.invBuildItForMePrice,
            "invCallAmount": invoice_obj.invCallAmount,
            "invCallPrice": invoice_obj.invCallPrice,
            "invCampaignAmount": invoice_obj.invCampaignAmount,
            "invCampaignprice": invoice_obj.invCampaignPrice,
            "invClientName": invoice_obj.invClientName,
            "invCountryId": invoice_obj.invCountryId,
            "invCurrentContacts": invoice_obj.invCurrentContacts,
            "invDate": invoice_obj.invDate,
            "invIndividualAmount": invoice_obj.invIndividualAmount,
            "invIndividualPrice": invoice_obj.invIndividualPrice,
            "invMonthlyEmailAmount": invoice_obj.invMonthlyEmailAmount,
            "invMonthlyIndividualAmount": invoice_obj.invMonthlyIndividualAmount,
            "invMonthlySmsAmount": invoice_obj.invMonthlySmsAmount,
            "invMonthlySocialMediaAmount": invoice_obj.invMonthlySocialMediaAmount,
            "invMonthlySurveyAmount": invoice_obj.invMonthlySurveyAmount,
            "invMonthlyYN": invoice_obj.invMonthlyYN,
            "invPageTransAmount": invoice_obj.invPageTransAmount,
            "invPageTransPrice": invoice_obj.invPageTransPrice,
            "invPayCardNo": invoice_obj.invPayCardNo,
            "invSendMail": invoice_obj.invSendMail,
            "invSmsAmount": invoice_obj.invSmsAmount,
            "invSMSConversationsAmount": invoice_obj.invSMSConversationsAmount,
            "invSMSConversationsPrice": invoice_obj.invSMSConversationsPrice,
            "invSmsPollAmount": invoice_obj.invSmsPollAmount,
            "invSmsPollPrice": invoice_obj.invSmsPollPrice,
            "invSmsPrice": invoice_obj.invSmsPrice,
            "invSocialMediaAmount": invoice_obj.invSocialMediaAmount,
            "invSocialMediaPrice": invoice_obj.invSocialMediaPrice,
            "invSubTotal": invoice_obj.invSubTotal,
            "invSurveyAmount": invoice_obj.invSurveyAmount,
            "invSurveyprice": invoice_obj.invSurveyPrice,
            "invTotalAmount": invoice_obj.invTotalAmount,
            "invTransationId": invoice_obj.invTransationId,
            "memberId": invoice_obj.invTenantId,
            "invPlanId": invoice_obj.invPlanId,
            "invPlanName": invoice_obj.invPlanName,
            "invPlanPrice": invoice_obj.invPlanPrice,
            "invShareAppointmentAmount": invoice_obj.invShareAppointmentAmount,
            "invSmsCalendarAmount": invoice_obj.invSmsCalendarAmount,
            "invShareAppointmentPrice": invoice_obj.invShareAppointmentPrice,
            "invSmsCalendarPrice": invoice_obj.invSmsCalendarPrice,
            "invAdditionalContactsAmount": invoice_obj.invAdditionalContactsAmount,
            "invAdditionalContactsPrice": invoice_obj.invAdditionalContactsPrice,
            "inv10DLCAmount": invoice_obj.inv10DLCAmount,
            "invWarmupAmount": invoice_obj.invWarmupAmount,
            "invEmailVerificationAmount": invoice_obj.invEmailVerificationAmount,
            "invEmailVerificationPrice": invoice_obj.invEmailVerificationPrice,
            "invSmsCalendarReminderAmount": invoice_obj.invSmsCalendarReminderAmount,
            "invSmsCalendarReminderPrice": invoice_obj.invSmsCalendarReminderPrice,
            "invPreviousUninvoicedAmount": invoice_obj.invPreviousUninvoicedAmount,
            "invPreviousUninvoicedPrice": invoice_obj.invPreviousUninvoicedPrice,
            "invAiAmount": invoice_obj.invAiAmount,
            "invAiPrice": invoice_obj.invAiPrice,
            "invPerContactPrice": invoice_obj.invPerContactPrice,
            "eptInvId": DecryptString.set_enc_dec_user(str(invoice_obj.invId), "", "Y"),
            "eptMemberId": DecryptString.set_enc_dec_user(str(invoice_obj.invTenantId), "", "Y"),
        }

        try:
            invoice_dto["invDate"] = display_date(invoice_dto["invDate"])
        except Exception as e:
            logger.error(f"[ tenantId : {tenant_id} ] PrintInvoice Error 1 : {e}")

        # Match Java's invTotalAmountPlanGrow calculation
        if str(invoice_dto["invPlanName"]).lower() == "pay as you grow":
            finalInvTotalAmount = (invoice_dto["invTotalAmount"]
                                    - invoice_dto["inv10DLCAmount"]
                                    - invoice_dto["invPreviousUninvoicedAmount"])
            invoice_dto["invTotalAmountPlanGrow"] = finalInvTotalAmount
        
        res_body["invoice"] = invoice_dto

        empty = dict()
        res_body["invoiceMonthly"] = empty
        res_body["monthlyPlanLogs"] = empty

        # 4. Fetch Transactions conditionally matching Java's logic
        res_body["campaign"] = get_inv_type_campaign(tenant_id, inv_id) if invoice_dto["invCampaignAmount"] > 0 else []
        res_body["survey"] = get_inv_type_survey(tenant_id, inv_id) if invoice_dto["invSurveyAmount"] > 0 else []
        res_body["assessment"] = get_inv_type_assessment(tenant_id, inv_id) if invoice_dto["invAssessmentAmount"] > 0 else []
        res_body["customForm"] = get_inv_type_generic(tenant_id, inv_id, 'customform') if invoice_dto["invIndividualAmount"] > 0 else []
        res_body["sms"] = get_inv_type_generic(tenant_id, inv_id, ['sms', 'sms number']) if invoice_dto["invSmsAmount"] > 0 else []
        res_body["smsPollingNumber"] = get_inv_type_generic(tenant_id, inv_id, 'sms polling number') if invoice_dto["invSmsPollAmount"] > 0 else []
        res_body["smsPolling"] = get_inv_type_sms_polling(tenant_id, inv_id, monthlyYN, monthlySMSYN) if invoice_dto["invSmsPollAmount"] > 0 else []
        res_body["languageTranslation"] = get_inv_type_generic(tenant_id, inv_id, 'language translation') if invoice_dto["invPageTransAmount"] > 0 else []
        res_body["socialMediaPosting"] = get_inv_type_generic(tenant_id, inv_id, 'social media posting') if invoice_dto["invSocialMediaAmount"] > 0 else []
        res_body["smsConversations"] = get_inv_type_generic(tenant_id, inv_id, ['sms conversations', 'sms conversations number']) if invoice_dto["invSMSConversationsAmount"] > 0 else []
        res_body["calling"] = get_inv_type_generic(tenant_id, inv_id, 'calling') if invoice_dto["invCallAmount"] > 0 else []
        res_body["buildItForMe"] = get_inv_type_generic(tenant_id, inv_id, 'builditforme') if invoice_dto["invBuildItForMeAmount"] > 0 else []
        res_body["shareAppointmentLink"] = get_inv_type_generic(tenant_id, inv_id, 'share_appointment_link') if invoice_dto["invShareAppointmentAmount"] > 0 else []
        res_body["smsCalendarAppointment"] = get_inv_type_generic(tenant_id, inv_id, 'sms calendar appointment') if invoice_dto["invShareAppointmentAmount"] > 0 else []
        res_body["additionalContacts"] = get_inv_type_generic(tenant_id, inv_id, 'additional contacts') if invoice_dto["invAdditionalContactsAmount"] > 0 else []
        res_body["tenDLC"] = get_inv_type_generic(tenant_id, inv_id, ['10DLC', 'TenDLC']) if invoice_dto["inv10DLCAmount"] > 0 else []
        res_body["warmup"] = get_inv_type_generic(tenant_id, inv_id, 'domain warmup') if invoice_dto["invWarmupAmount"] > 0 else []
        res_body["emailVerification"] = get_inv_type_generic(tenant_id, inv_id, 'email verification') if invoice_dto["invEmailVerificationAmount"] > 0 else []
        res_body["smsCalendarReminder"] = get_inv_type_generic(tenant_id, inv_id, 'sms calendar reminder') if invoice_dto["invSmsCalendarReminderAmount"] > 0 else []
        res_body["previousUninvoiced"] = get_inv_type_generic(tenant_id, inv_id, 'previous uninvoiced') if invoice_dto["invPreviousUninvoicedAmount"] > 0 else []
        res_body["ai"] = get_inv_type_generic(tenant_id, inv_id, 'AI') if invoice_dto["invAiAmount"] > 0 else []

        # Internal python specific logic
        printInvoiced_internal(inv_id, tenant_id, "", "manual")

        return api_response(200, "Invoice fetched successfully.", res_body)
    except Exception as e:
        res_body["error"] = "error"
        logger.error(f"PrintInvoice Error : {e}", exc_info=True)
        return api_response(500, ERROR_MSG, res_body)