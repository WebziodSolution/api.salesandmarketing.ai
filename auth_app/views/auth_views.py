from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from common_app.utils import api_response, check_duplicate_records, check_type_email, check_total_member, get_tenants, get_tenant_common_object, get_client_id_by_tenant_id, get_phone_numbers_first
from auth_app.models import Tenants, TenantDetails
from django.db.models import F, Q
from django.conf import settings
from common_app.services import CommonServices, MailRequestDTO
from common_app.custom_permissions import WhitelistPermission
from common_app.decrypt_string import DecryptString
import telnyx
from common_app.telnyx_utils import send_sms_telnyx
import random
import json
import os
import shutil
import re
from api_app.views.zero_bounce_helper import ZeroBounceHelper
from api_app.utils.proofy_helper import ProofyHelper
import base64
from common_app.models import Country, CountrySetting, BrandKits, Plans, PlanModule, SubaccountPage, SubaccountPagePermission, Groups, SecurityQuestion, SmsTemplates, MyPages, TranslateTemplate, Domains, DomainEmails, RegistrationSteps, TenantPlanDetails, AffiliateProgram, AffiliateCommissionSchedule, CalendarSetup, Clients
from django.utils import timezone, timezone as tz
from django.db import connection
import traceback

import logging
logger = logging.getLogger(__name__)

def extract_tenant_id_from_token(token_data):
    if not token_data:
        return 0
    try:
        parts = token_data.split('.')
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += '=' * (-len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
            return int(json.loads(payload_json).get('tenId', 0))
    except Exception:
        pass
    return 0


telnyx.api_key = getattr(settings, 'TELNYX_API_KEY', '')

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    
    refresh['firstName'] = user.ten_first_name
    refresh['lastName'] = user.ten_last_name
    refresh['sub'] = user.ten_email
    
    return str(refresh.access_token)

def map_brand_kits(brand_kits_list):
    mapped_list = []
    for bk in brand_kits_list:
        fonts = {}
        if bk.get('brand_fonts'):
            try:
                fonts = json.loads(bk.get('brand_fonts'))
            except Exception:
                pass
        
        mapped_list.append({
            "brandId": bk.get('brand_id'),
            "brandName": bk.get('brand_name'),
            "brandWebsite": bk.get('brand_website'),
            "brandLogo": bk.get('brand_logo'),
            "brandColors": bk.get('brand_colors'),
            "brandFonts": fonts
        })
    return mapped_list

def map_country_setting(cs):
    if not cs:
        return None
    return {
        "id": cs.id,
        "cntyId": cs.cnty_id,
        "cntyISO2": cs.cnty_iso2,
        "cntyName": cs.cnty_name,
        "cntyPriceSymbol": cs.cnty_price_symbol,
        "cntyAssessmentPrice": cs.cnty_assessment_price or 0.0,
        "cntySurveyPrice": cs.cnty_survey_price or 0.0,
        "cntyIndividualPrice": cs.cnty_individual_price or 0.0,
        "cntySocialMediaPrice": cs.cnty_social_media_price or 0.0,
        "cntyCampaignPerPrice": cs.cnty_campaign_per_price or 0.0,
        "cntySurveyPerPrice": cs.cnty_survey_per_price or 0.0,
        "cntyAssessmentPerPrice": cs.cnty_assessment_per_price or 0.0,
        "cntyMMSPerPrice": cs.cnty_mms_per_price or 0.0,
        "cntySMSPerPrice": cs.cnty_sms_per_price or 0.0,
        "cntySMSNumberPerPrice": cs.cnty_sms_number_per_price or 0.0,
        "cntyFirstInvFreeAmt": cs.cnty_first_inv_free_amt or 0.0,
        "cntyInvLessAmtNotCharge": cs.cnty_inv_less_amt_not_charge or 0.0,
        "cntyTranslateCharCharge": cs.cnty_translate_char_charge or 0.0,
        "cntySMSConversationsPerPrice": cs.cnty_sms_conversations_per_price or 0.0,
        "cntyCallPerMinPrice": cs.cnty_call_per_min_price or 0.0,
        "cntyContactsIncluded": cs.cnty_contacts_included,
        "cntyMaxNumberOfEmail": cs.cnty_max_number_of_email,
        "cntyPlanId": cs.cnty_plan_id,
        "cntyPlanPrice": cs.cnty_plan_price or 0.0,
        "cntySupport": cs.cnty_support,
        "cntyMultiUser": cs.cnty_multi_user,
        "cntyAutomation": cs.cnty_automation,
        "cntyWhiteListing": cs.cnty_white_listing,
        "cntyCalendar": cs.cnty_calendar,
        "cntyZoomConferences": cs.cnty_zoom_conferences,
        "cntySocialMedia": cs.cnty_social_media,
        "cntySmsInbox": cs.cnty_sms_inbox,
        "cntyAbTesting": cs.cnty_ab_testing,
        "cntyPlanPopular": cs.cnty_plan_popular,
        "cntyPlanDisplayOrder": cs.cnty_plan_display_order,
        "cntyFormResponse": cs.cnty_form_response or 0.0,
        "cntyAdditionalContacts": cs.cnty_additional_contacts,
        "cntyAdditionalContactsPrice": cs.cnty_additional_contacts_price or 0.0,
        "cnty10DLCPrice": cs.cnty_10dlc_price or 0.0,
        "cnty10DLCCampaignTypeCharge": cs.cnty_10dlc_campaign_type_charge or 0.0,
        "cnty10DLCOtherCharge": cs.cnty_10dlc_other_charge or 0.0,
        "cntyWarmupPrice": cs.cnty_warmup_price or 0.0,
        "ctnyAiGeneratedImage": cs.ctny_ai_generated_image or 0.0,
        "ctnyAiEditedImage": cs.ctny_ai_edited_image or 0.0,
        "ctnyContactPerPrice": cs.ctny_contact_per_price or 0.0,
    }

def set_login_dto_data(tenant, tenant_type="tenant"):
    login_dto = dict()

    if tenant.ten_parent_id == 0 and tenant_type == "subTenant":
        login_dto['memberId'] = 0
    else:
        login_dto['memberId'] = tenant.ten_id
    login_dto['encMemberId'] = DecryptString.set_enc_dec_user(str(tenant.ten_id), "", "Y")

    login_dto['firstName'] = tenant.ten_first_name
    login_dto['lastName'] = tenant.ten_last_name
    login_dto['username'] = tenant.ten_username
    login_dto['loginPreference'] = tenant.td_login_preference
    login_dto['defaultLanguage'] = tenant.ten_default_language
    login_dto['email'] = tenant.ten_email
    login_dto['address'] = tenant.ten_street_address1
    login_dto['streetAddress2'] = tenant.ten_street_address2
    login_dto['city'] = tenant.ten_city
    login_dto['state'] = tenant.ten_state
    login_dto['postCode'] = tenant.ten_post_code
    login_dto['phone'] = tenant.ten_phone
    login_dto['cell'] = tenant.ten_cell_phone
    login_dto['country'] = tenant.ten_country
    login_dto['googleAuthenticatorSecret'] = tenant.td_google_authenticator_secret
    login_dto['microsoftAuthenticatorSecret'] = tenant.td_microsoft_authenticator_secret

    login_dto['billingFirstName'] = tenant.td_billing_first_name
    login_dto['billingLastName'] = tenant.td_billing_last_name
    login_dto['billingAddress'] = tenant.td_billing_address1
    login_dto['billingCity'] = tenant.td_billing_city
    login_dto['billingState'] = tenant.td_billing_state
    login_dto['billingPostCode'] = tenant.td_billing_post_code
    login_dto['billingPhone'] = tenant.td_billing_phone
    login_dto['billingCountry'] = tenant.td_billing_country
    login_dto['password'] = None
    login_dto['optin'] = tenant.td_opt_in

    country_id = 100
    if tenant.ten_country:
        try:
            country_id = int(tenant.ten_country)
        except ValueError:
            pass
    country_obj = Country.objects.filter(country_id=country_id).first()
    login_dto['countryCode'] = country_obj.cnt_code if country_obj else ""

    phone_number = get_phone_numbers_first(tenant.ten_id, "CAMPAIGN")
    chat_phone_number = get_phone_numbers_first(tenant.ten_id, "CHAT")
    login_dto['twilioNumber'] = phone_number.phPhoneNumber if phone_number else ""
    login_dto['conversationsTwilioNumber'] = chat_phone_number.phPhoneNumber if chat_phone_number else ""

    google_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant.ten_id), csCalendarType="GOOGLE").first()
    outlook_calendar_setup = CalendarSetup.objects.filter(csClientId=get_client_id_by_tenant_id(tenant.ten_id), csCalendarType="MICROSOFT").first()
    email_notification = ""
    sms_notification = ""
    web_conference = ""
    default_calendar = "google"
    if google_calendar_setup:
        email_notification = google_calendar_setup.csEmailNotification
        sms_notification = google_calendar_setup.csSmsNotification
        web_conference = google_calendar_setup.csWebConferenceUrl
        if google_calendar_setup.csDefaultCalendar == "Y":
            default_calendar = "google"
    elif outlook_calendar_setup:
        email_notification = outlook_calendar_setup.csEmailNotification
        sms_notification = outlook_calendar_setup.csSmsNotification
        web_conference = outlook_calendar_setup.csWebConferenceUrl
        if outlook_calendar_setup.csDefaultCalendar == "Y":
            default_calendar = "outlook"

    login_dto['emailNotification'] = email_notification
    login_dto['smsNotification'] = sms_notification
    login_dto['webConference'] = web_conference
    login_dto['defaultCalendar'] = default_calendar

    client = Clients.objects.get(cliTenantId=tenant.ten_id)
    login_dto['imageUrl'] = client.cliProfileImageUrl
    login_dto['timeZone'] = client.cliTimeZone
    login_dto['businessName'] = client.cliBusinessName

    login_dto['planId'] = tenant.td_plan_id
    login_dto['encPlanId'] = DecryptString.set_enc_dec_user(str(tenant.td_plan_id), "", "Y") if tenant.td_plan_id else ""

    related_tenant_id = tenant.ten_id if tenant.ten_parent_id == 0 else tenant.ten_parent_id
    brand_kits_qs = BrandKits.objects.filter(brand_client_id=get_client_id_by_tenant_id(related_tenant_id)).annotate(
        brandId=F('brand_id'),
        brandName=F('brand_name'),
        brandWebsite=F('brand_website'),
        brandLogo=F('brand_logo'),
        brandColors=F('brand_colors'),
        brandFonts=F('brand_fonts')
    ).values('brandId', 'brandName', 'brandWebsite', 'brandLogo', 'brandColors', 'brandFonts')

    brand_kits_list = list(brand_kits_qs)
    for kit in brand_kits_list:
        # Get the raw value safely
        raw_fonts = kit.get('brandFonts')

        # Check if it is a non-empty string before parsing
        if isinstance(raw_fonts, str) and raw_fonts.strip():
            try:
                kit['brandFonts'] = json.loads(raw_fonts)
            except (json.JSONDecodeError, TypeError):
                # Fallback if the JSON is corrupted
                kit['brandFonts'] = {}
        elif isinstance(raw_fonts, (dict, list)):
            # Already parsed (case for some Django field types)
            pass
        else:
            # Default for empty strings or None
            kit['brandFonts'] = {}

    login_dto['brandKits'] = brand_kits_list
    for kit in brand_kits_list:
        if isinstance(kit.get('brandFonts'), str):
            kit['brandFonts'] = json.loads(kit['brandFonts'])  # converts to dict/list

    login_dto['brandKits'] = brand_kits_list

    country_setting = CountrySetting.objects.filter(cnty_id=country_id).first()
    if country_setting:
        login_dto['countryPriceSymbol'] = country_setting.cnty_price_symbol
    else:
        login_dto['countryPriceSymbol'] = "$"

    login_dto['alreadyExistsToken'] = None
    login_dto['agreeAffiliateProgram'] = tenant.td_agree_affiliate_program

    if tenant.td_plan_id and tenant.td_plan_id > 0:
        plan = Plans.objects.filter(plan_id=tenant.td_plan_id).first()
        if plan:
            login_dto['planVisibility'] = plan.plan_visibility
            module_titles = []
            if plan.plan_pm_id_list:
                pm_ids = [int(p) for p in plan.plan_pm_id_list.split(",") if p.strip().isdigit()]
                modules = PlanModule.objects.filter(pm_id__in=pm_ids)
                module_titles = [m.pm_title for m in modules]
            login_dto['planModuleList'] = module_titles
        else:
            login_dto['planVisibility'] = ""
            login_dto['planModuleList'] = []
    else:
        login_dto['planVisibility'] = ""
        login_dto['planModuleList'] = []
    return login_dto

def set_res_body(tenant):
    res_body = dict()
    
    res_body['token'] = get_tokens_for_user(tenant)

    country_setting = CommonServices.country_setting_by_tenant_id(tenant.ten_id)
    res_body['countrySetting'] = map_country_setting(country_setting)
    creditcard_status = ""
    creditcard_error = ""

    menu_list = []
    module_list = {}

    if tenant.ten_parent_id and tenant.ten_parent_id > 0:
        subaccount_pages = SubaccountPage.objects.all()
        for page in subaccount_pages:
            permissions = SubaccountPagePermission.objects.filter(
                spp_pg_id=page.sp_id,
                spp_sub_id=tenant.td_sub_account_type_id,
                spp_client_id=get_client_id_by_tenant_id(tenant.ten_parent_id)
            )
            row = []
            for perm in permissions:
                if perm.spp_action_name and perm.spp_action_name == "View":
                    menu_name_lw = page.sp_menu_name.lower() if page.sp_menu_name else ""
                    if menu_name_lw not in menu_list:
                        menu_list.append(menu_name_lw)
                row.append(perm.spp_action_name.lower() if perm.spp_action_name else "")
            
            module_name_lw = page.sp_module_name.lower() if page.sp_module_name else ""
            module_list[module_name_lw] = row

        parent_tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant.ten_parent_id
                }
            }
        )
        if parent_tenant:
            res_body['member'] = set_login_dto_data(parent_tenant, "tenant")
            if parent_tenant.td_creditcard_status:
                creditcard_status = parent_tenant.td_creditcard_status
                creditcard_error = parent_tenant.td_creditcard_error or ""
        else:
            res_body['member'] = set_login_dto_data(tenant, "tenant")
            
        res_body['subMember'] = set_login_dto_data(tenant, "subTenant")

    else:
        res_body['member'] = set_login_dto_data(tenant, "tenant")
        res_body['subMember'] = set_login_dto_data(tenant, "subTenant")
        if tenant.td_creditcard_status:
            creditcard_status = tenant.td_creditcard_status
            creditcard_error = tenant.td_creditcard_error or ""

    res_body['moduleList'] = module_list
    res_body['menuList'] = menu_list

    if creditcard_status == "deactivate":
        res_body['redirectPage'] = "deactivate"
        res_body['redirectPageMessage'] = f"Last transaction on your Credit card has an issue.\n\"{creditcard_error}\"\nPlease update your credit card to use the service"
    else:
        res_body['redirectPage'] = ""
        res_body['redirectPageMessage'] = ""

    return res_body


@api_view(['POST'])
@permission_classes([WhitelistPermission])  
def token(request):
    resBody = dict()
    data = request.data
    already_exists_token = data.get('alreadyExistsToken')

    if already_exists_token is not None:
        tenant_id = extract_tenant_id_from_token(already_exists_token)
        tenant = Tenants.objects.get(ten_id=tenant_id)
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
    else:
        login_pref = data.get('loginPreference')
        username = data.get('username', '')
        password = data.get('password', '')
        
        if login_pref in ['authidAuthenticator', 'googleAuthenticator', 'microsoftAuthenticator']:
            tenant = Tenants.objects.get(Q(ten_username=username) | Q(ten_email=username))
            tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant.ten_id)
        elif username and password:
            tenant = Tenants.objects.get(Q(ten_username=username) | Q(ten_email=username))
            tenant_details = TenantDetails.objects.filter(tenant__ten_id=tenant.ten_id, td_password=password).first()
        else:
            return api_response(500, "Username Or Password Is Blank", resBody)


    if tenant and tenant_details:
        if tenant.ten_status == 3:
            return api_response(400, "Your Account Is Suspended. Please Contact Administrator", resBody)
        elif tenant.ten_status == 1:
            resBody['id'] = tenant.ten_id
            return api_response(401, "Account Is InActive ", resBody)
        elif tenant.ten_status == 0 and (tenant_details and tenant_details.td_is2fa == 1) and not already_exists_token:
            logger.error(f"Yes already_exists_token is true")
            otp = CommonServices.generate_otp()
            if not otp: 
                otp = f"{random.randint(100000, 999999)}"
            tenant_details.td_otp = otp
            tenant.save()
            tenant_details.save()
            
            # Send Telnyx SMS
            telnyx_from_phone = getattr(settings, 'TELNYX_FROM_PHONE_NO', '')
            site_name = "SalesAndMarketing"
            msg = f"{site_name} Mobile Authentication Code. Your Authentication Code Is : {otp}"
            try:
                country_code = ""
                if tenant.ten_country:
                    try:
                        country_obj = Country.objects.filter(country_id=int(tenant.ten_country)).first()
                        if country_obj and country_obj.cnt_code:
                            country_code = country_obj.cnt_code
                    except ValueError:
                        pass
                if not country_code:
                    country_code = "+1" # Default fallback
                
                phone_number = f"{country_code}{tenant.ten_cell_phone}" if not tenant.ten_cell_phone.startswith('+') else tenant.ten_cell_phone
                send_sms_telnyx(
                    mobile_no=phone_number,
                    telnyx_number=telnyx_from_phone,
                    sms_type="onlytext",
                    sms_details=msg,
                    sms_count="",
                    opt_out_msg="",
                    sms_status_url=None
                )
            except Exception as e:                
                logger.error(f"[ tenantId : {tenant.ten_id} ] sendSms error : {e}")
                

            resBody['otp'] = otp # Java returns decrypted OTP here usually, but keeping straight map
            resBody['id'] = tenant.ten_id
            return api_response(304, "An Authentication Code Has Been Sent To Your Registered Mobile Device.", resBody)
        elif tenant.ten_status == 0:
            country_setting = CommonServices.country_setting_by_tenant_id(tenant.ten_id)
            if country_setting is None:
                resBody['encTenantId'] = DecryptString.set_enc_dec_user(str(tenant.ten_id), "", "Y")

                return api_response(406, "Your Plan Is No Longer Available In The System. Please Choose Another Plan", resBody)    
            else:
                resBody = set_res_body(get_tenant_common_object(tenant,tenant_details))
            return api_response(200, "Login Successfully", resBody)
        else:
            return api_response(404, "Tenant Not Found", resBody)
    else:
        return api_response(404, "Tenant Not Found", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def changePlan(request):
    resBody = dict()
    try:
        tenant_id = int(DecryptString.set_enc_dec_user(request.data.get('encTenantId'), "display", "Y"))
        plan_id = int(DecryptString.set_enc_dec_user(request.data.get('encPlanId'), "display", "Y"))
        tenant = Tenants.objects.get(ten_id=tenant_id)
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        if tenant_details:
            tenant_details.td_plan_id = plan_id
            tenant_details.save()
            resBody = set_res_body(get_tenant_common_object(tenant, tenant_details))
            return api_response(200, "Login Successfully", resBody)
        return api_response(500, "Tenant not found", resBody)
    except Exception:
        return api_response(500, "Error", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def processActivation(request):
    resBody = dict()
    try:
        v = request.GET.get('v')
        v = DecryptString.set_enc_dec_user(v, "display", "Y")
        tenant_id = int(v) if v else 0
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        if tenant:
            if tenant.ten_status == 1:
                resBody['userId'] = tenant_id
                resBody['username'] = tenant.ten_username
                resBody['callingPage'] = "onboarding"
                return api_response(200, "Your Account Is Activated Now. Please Update Your Profile Details.", resBody)
            else:
                resBody['callingPage'] = "login"
                return api_response(200, "Your Account Is Already Activated.", resBody)
        return api_response(500, "Error", resBody)
    except:
        return api_response(500, "Error", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def forgotPassword(request):
    resBody = dict()
    resBody['error'] = ''
    resBody['tenant'] = ''
    username = request.data.get('username', '')
    tenant = get_tenants(
        where_conditions={
            "tenant": {
                "or": {
                    "ten_username": username,
                    "ten_email": username,
                },
                "ten_status__in": [0, 2]
            }
        }
    )
    if not tenant:
        # Also check suspended/inactive for specific error messages
        any_tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "or": {
                        "ten_username": username,
                        "ten_email": username,
                    }
                }
            }
        )
        if any_tenant:
            if any_tenant.ten_status == 3:
                resBody['error'] = '3'
                return api_response(400, "Your Account Is Suspended. Please Contact Administrator", resBody)
            elif any_tenant.ten_status == 1:
                resBody['error'] = '1'
                return api_response(401, "Account Is InActive", resBody)
        return api_response(304, "Username Does Not Exists.", resBody)

    # Pick a random security question (1-3)
    rand = random.randint(1, 3)
    question_id = 0
    question_text = ''
    if rand == 1:
        if tenant.td_sec_qus_1 and tenant.td_sec_qus_1 > 0:
            question_id = tenant.td_sec_qus_1
            sq = SecurityQuestion.objects.filter(sec_id=question_id).first()
            question_text = sq.sec_question if sq else ''
    elif rand == 2:
        if tenant.td_sec_qus_2 and tenant.td_sec_qus_2 > 0:
            question_id = tenant.td_sec_qus_2
            sq = SecurityQuestion.objects.filter(sec_id=question_id).first()
            question_text = sq.sec_question if sq else ''
    else:
        if tenant.td_sec_qus_3 and tenant.td_sec_qus_3 > 0:
            question_id = tenant.td_sec_qus_3
            sq = SecurityQuestion.objects.filter(sec_id=question_id).first()
            question_text = sq.sec_question if sq else ''

    resBody['tenant'] = {
        'tenantId': tenant.ten_id,
        'questionId': question_id,
        'question': question_text,
        'secQus1': tenant.td_sec_qus_1,
        'secQus2': tenant.td_sec_qus_2,
        'secQus3': tenant.td_sec_qus_3,
    }
    return api_response(200, "Fetch Tenant Successfully.", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def forgotPasswordVerify(request):
    resBody = dict()
    tenant_id = request.data.get('tenantId')
    question_id = request.data.get('questionId')
    answer = request.data.get('answer', '')

    tenant = get_tenants(
        where_conditions={
            "tenant": {
                "ten_id": tenant_id
            }
        }
    )
    if not tenant:
        return api_response(304, "Sorry!! Security Question Answer You Provide Is Not Valid.", resBody)

    # Verify security question answer
    flag = False
    q_id = int(question_id) if question_id else 0
    if tenant.td_sec_qus_1 and tenant.td_sec_qus_1 == q_id:
        if (tenant.td_sec_ans_1 or '') == answer:
            flag = True
    elif tenant.td_sec_qus_2 and tenant.td_sec_qus_2 == q_id:
        if (tenant.td_sec_ans_2 or '') == answer:
            flag = True
    else:
        if (tenant.td_sec_ans_3 or '') == answer:
            flag = True

    if not flag:
        return api_response(304, "Sorry!! Security Question Answer You Provide Is Not Valid.", resBody)

    model = {
        "Url": f"{getattr(settings, 'SITE_URL', 'https://qawebapp.salesandmarketing.ai/')}resetpassword?v={tenant.ten_id}",
        "siteName": getattr(settings, 'SITE_NAME', 'SalesAndMarketing'),
        "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai'),
        "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', 'SalesAndMarketing'),
        "SITEURL": getattr(settings, 'SITE_URL', 'https://qawebapp.salesandmarketing.ai/'),
        "siteUrlWWW": getattr(settings, 'SITE_URL_WWW', ''),
        "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', ''),
        "companyName": getattr(settings, 'COMPANY_NAME', 'SAM'),
        "siteUrlAddress": getattr(settings, 'SITE_URL_ADDRESS', ''),
        "companyNumber": getattr(settings, 'COMPANY_NUMBER', ''),
    }
    req = MailRequestDTO(to=tenant.ten_email, subject="Reset Password Link", template_name="reset-password-link-template.ftl")
    CommonServices.sendEmail(req, model)
    return api_response(200, f"Password Reset Link Has Been Sent To You At {tenant.ten_email}.", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def resetPassword(request):
    tenant_id = request.data.get('memId')
    new_password = request.data.get('newPassword')
    try:
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        if tenant_details:
            tenant_details.td_password = new_password
            tenant_details.save()
            return api_response(200, "Password Reset Successfully.", "")
    except (ValueError, TypeError):
        pass
    return api_response(304, "Tenant Not Found.", "")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def onboarding(request, step):
    resBody = dict()
    data = request.data
    tenant_id = data.get('memberId')
    tenant = Tenants.objects.get(ten_id=tenant_id)
    tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
    if not tenant:
        return api_response(404, "Tenant Not Found", resBody)
    
    try:
        step = int(step)
        if step == 1:
            tenant_details.td_registration_step = data.get('registrationStep', tenant_details.td_registration_step)
            tenant_details.td_login_preference = data.get('loginPreference', tenant_details.td_login_preference)
            tenant_details.td_sec_ans_1 = data.get('secAns1', '') or ''
            tenant_details.td_sec_ans_2 = data.get('secAns2', '') or ''
            tenant_details.td_sec_ans_3 = data.get('secAns3', '') or ''
            tenant_details.td_sec_qus_1 = int(data.get('secQus1', 0) or 0)
            tenant_details.td_sec_qus_2 = int(data.get('secQus2', 0) or 0)
            tenant_details.td_sec_qus_3 = int(data.get('secQus3', 0) or 0)

        elif step == 2:
            tenant_details.td_registration_step = data.get('registrationStep', tenant_details.td_registration_step)
            tenant.ten_first_name = data.get('firstName', tenant.ten_first_name)
            tenant.ten_last_name = data.get('lastName', tenant.ten_last_name)
            tenant.ten_street_address1 = data.get('address', tenant.ten_street_address1)
            tenant.ten_street_address2 = data.get('streetAddress', tenant.ten_street_address2)
            tenant.ten_city = data.get('city', tenant.ten_city)
            tenant.ten_state = data.get('state', tenant.ten_state)
            tenant.ten_post_code = data.get('postCode', tenant.ten_post_code)
            tenant.ten_phone = data.get('phone', tenant.ten_phone)
            tenant.ten_country = data.get('country', tenant.ten_country)
            tenant.ten_cell_phone = data.get('cell', tenant.ten_cell_phone)
            tenant.ten_default_language = data.get('memberDefaultLanguage', tenant.ten_default_language)
            tenant_details.td_billing_first_name = data.get('billingFirstName', tenant_details.td_billing_first_name)
            tenant_details.td_billing_last_name = data.get('billingLastName', tenant_details.td_billing_last_name)
            tenant_details.td_billing_address1 = data.get('billingAddress', tenant_details.td_billing_address1)
            tenant_details.td_billing_city = data.get('billingCity', tenant_details.td_billing_city)
            tenant_details.td_billing_state = data.get('billingState', tenant_details.td_billing_state)
            tenant_details.td_billing_post_code = data.get('billingPostCode', tenant_details.td_billing_post_code)
            tenant_details.td_billing_phone = data.get('billingPhone', tenant_details.td_billing_phone)
            tenant_details.td_billing_country = data.get('billingCountry', tenant_details.td_billing_country)
            tenant_details.td_country = data.get('country', tenant.ten_country)

        elif step == 3:
            tenant_details.td_registration_step = data.get('registrationStep', tenant_details.td_registration_step)
            tenant.save()
            tenant_details.save()
            client = Clients.objects.get(cliTenantId=tenant_id)
            client.cliBusinessName = data.get('businessName', client.cliBusinessName)
            client.cliWebsite = data.get('brandWebsite', client.cliWebsite)
            client.save()
            brand_name = data.get('brandName', '')
            brand_website = data.get('brandWebsite', '')
            if brand_name and brand_website:
                existing_brands = list(BrandKits.objects.filter(brand_client_id=get_client_id_by_tenant_id(tenant.ten_id)))
                now = timezone.now()
                if not existing_brands:
                    bk = BrandKits()
                    bk.brand_client_id = get_client_id_by_tenant_id(tenant.ten_id)
                    bk.brand_name = brand_name
                    bk.brand_website = brand_website
                    bk.brand_logo = data.get('brandLogo', '')
                    bk.brand_colors = data.get('brandColors', '')
                    bk.brand_created_date = now
                    bk.brand_updated_date = now
                    bk.save()
                else:
                    bk = existing_brands[0]
                    bk.brand_name = brand_name
                    bk.brand_website = brand_website
                    bk.brand_logo = data.get('brandLogo', bk.brand_logo)
                    bk.brand_colors = data.get('brandColors', bk.brand_colors)
                    bk.brand_updated_date = now
                    bk.save()
            else:
                BrandKits.objects.filter(brand_client_id=get_client_id_by_tenant_id(tenant.ten_id)).delete()

        elif step == 4:
            tenant_details.td_registration_step = data.get('registrationStep', tenant_details.td_registration_step)
            newsletter = data.get('newsletterSubscribe', '')
            tenant_details.td_newsletter_subscribe = 0 if newsletter == '' else int(newsletter or 0)
            tenant.ten_status = 0
            tenant_details.td_creditcard_error = None
            tenant_details.td_creditcard_status = None
            tenant.save()
            tenant_details.save()

            email = tenant.ten_email or ''
            domain_name = email.split('@')[1] if '@' in email else ''

            try:
                if domain_name:
                    domain_email_exists = DomainEmails.objects.filter(de_client_id=get_client_id_by_tenant_id(tenant.ten_id), de_email=email).exists()
                    if not domain_email_exists:
                        domain = Domains.objects.filter(domClientId=get_client_id_by_tenant_id(tenant.ten_id), domDomain=domain_name).first()
                        if not domain:
                            domain = Domains()
                            domain.domClientId = get_client_id_by_tenant_id(tenant.ten_id)
                            domain.domDomain = domain_name
                            domain.domStatus = 0
                            domain.save()
                        de = DomainEmails()
                        de.de_client_id = get_client_id_by_tenant_id(tenant.ten_id)
                        de.de_did = domain.domId
                        de.de_email = email
                        de.de_create_date = timezone.now()
                        de.save()

                        welcome_model = {
                            "firstName": tenant.ten_first_name or '',
                            "lastName": tenant.ten_last_name or '',
                            "SITEURL": getattr(settings, 'IMAGE_SITE_URL', getattr(settings, 'SITE_URL', '')),
                            "siteName": getattr(settings, 'SITE_NAME', 'SalesAndMarketing'),
                            "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', ''),
                            "siteUrlWWW": getattr(settings, 'SITE_URL_WWW', ''),
                            "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', ''),
                            "companyName": getattr(settings, 'COMPANY_NAME', 'SAM'),
                            "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', 'SalesAndMarketing'),
                            "siteUrlAddress": getattr(settings, 'SITE_URL_ADDRESS', ''),
                            "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', ''),
                            "companyNumber": getattr(settings, 'COMPANY_NUMBER', ''),
                            "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', ''),
                            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', ''),
                        }
                        site_name_big_com = getattr(settings, 'SITE_NAME_BIG_COM', 'SalesAndMarketing.ai')
                        req_welcome = MailRequestDTO(to=email, subject=f"Welcome to {site_name_big_com}!", template_name="welcome-email-template.ftl")
                        try:
                            CommonServices.sendEmail(req_welcome, welcome_model)
                        except Exception as em:
                            logger.error(f"Welcome email error: {em}")
            except Exception as de_err:
                logger.error(f"Domain/DomainEmail onboarding error: {de_err}")

            try:
                first_name = tenant.ten_first_name or ''
                group_exists = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(tenant.ten_id), grpGroupName=first_name).exists()
                if not group_exists:
                    g = Groups()
                    g.grpGroupName = first_name
                    g.grpClientId = get_client_id_by_tenant_id(tenant.ten_id)
                    g.save()
            except Exception as ge:
                logger.error(f"Default group creation error: {ge}")

            if (tenant.ten_parent_id or 0) == 0:
                try:
                    opt_in_msg = ("##Business Name## has added you as one of their contacts and given you the right "
                                  "to maintain your own data. Please ensure your SMS and email address are correct "
                                  "by clicking the below link.\n\n##Link##\n\nMsg & Data Rates May Apply. Message "
                                  "frequency varies. Reply HELP for help. Reply STOP to unsubscribe.")
                    opt_out_msg = ("Sorry to see you go! Rest assured, you have been unsubscribed.\n\nIf you would "
                                   "like to receive SMS again from ##Business Name##'s contact list, please reply "
                                   "with word \"start\".")
                    if not SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(tenant.ten_id), stName='Opt In').exists():
                        st = SmsTemplates()
                        st.stClientId = get_client_id_by_tenant_id(tenant.ten_id)
                        st.stDate = timezone.now()
                        st.stName = 'Opt In'
                        st.stDetails = opt_in_msg
                        st.save()
                    if not SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(tenant.ten_id), stName='Opt Out').exists():
                        st = SmsTemplates()
                        st.stClientId = get_client_id_by_tenant_id(tenant.ten_id)
                        st.stDate = timezone.now()
                        st.stName = 'Opt Out'
                        st.stDetails = opt_out_msg
                        st.save()
                except Exception as ste:
                    logger.error(f"SmsTemplate creation error: {ste}")

                for mp_cfg in [
                    ('Opt In', 'optin'),
                    ('Opt Out', 'optout'),
                    ('Rejoin Group', 'rejoingroup'),
                ]:
                    mp_name, mp_folder = mp_cfg
                    try:
                        if not MyPages.objects.filter(mpClientId=get_client_id_by_tenant_id(tenant.ten_id), mpName=mp_name).exists():
                            file_dir = getattr(settings, 'FILE_UPLOAD_DIR', '')
                            read_path = os.path.join(file_dir, mp_folder, 'index.html')
                            mp_details = ''
                            if os.path.exists(read_path):
                                with open(read_path, 'r', encoding='utf-8') as f:
                                    mp_details = f.read()

                            mp = MyPages()
                            mp.mpName = mp_name
                            mp.mpTags = ''
                            mp.mpType = 1
                            mp.mpStage = 2
                            mp.mpGroupId = 0
                            mp.mpClientId = get_client_id_by_tenant_id(tenant.ten_id)
                            mp.mpTemplateLanguage = 'en'
                            mp.mpTemplateConvertLangList = ''
                            mp.mpAllowConvertLang = 'N'
                            mp.mpBuilditPublish = 'Y'
                            mp.mpPublicUrl = 'Y'
                            mp.mpDetails = mp_details
                            mp.save()

                            # File system sync mirroring Java logic
                            dest_dir = os.path.join(file_dir, str(tenant.ten_id), 'images', 'mypage', str(mp.mpId))
                            if not os.path.exists(dest_dir):
                                os.makedirs(dest_dir)

                            src_dir = os.path.join(file_dir, mp_folder)
                            if os.path.exists(src_dir):
                                for filename in os.listdir(src_dir):
                                    src_file = os.path.join(src_dir, filename)
                                    if os.path.isfile(src_file):
                                        shutil.copy2(src_file, os.path.join(dest_dir, filename))

                            tt = TranslateTemplate()
                            tt.ttMyPageId = mp.mpId
                            tt.ttClientId = mp.mpClientId
                            tt.ttCampDetail = mp.mpDetails
                            tt.ttCampDetailSend = mp.mpDetails
                            tt.ttMasterCopy = 'Y'
                            tt.ttTemplateLanguage = mp.mpTemplateLanguage
                            tt.ttPublishDate = timezone.now()
                            tt.save()
                    except Exception as mpe:
                        logger.error(f"MyPage {mp_name} creation error: {mpe}")

            try:
                RegistrationSteps.objects.filter(
                    rl_username=tenant.ten_username, rl_email=tenant.ten_email
                ).delete()
            except Exception as rle:
                logger.error(f"RegistrationSteps delete error: {rle}")

        tenant_details.td_membership_type = 'Platinum'
        tenant.save()
        tenant_details.save()

        # Build response as per AuthController.onBoarding
        resBody = dict()
        if step == 4:
            resBody = set_res_body(get_tenant_common_object(tenant,tenant_details))
        else:
            # For steps 1-3, AuthController returns empty resBody Map if updateOnboarding succeeds
            pass

        return api_response(200, "Updated Successfully.", resBody)

    except Exception as e:
        logger.error(f"Onboarding Error step {step}: {e}")
        return api_response(500, "Error: " + str(e), {})


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def logout(request):
    # Google Drive logout is not applicable in Django context; return success
    return api_response(200, "Logout Successfully.", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkEmail(request, email):
    resBody = dict()
    existing = get_tenants(
        where_conditions={
            "tenant": {
                "ten_email": email
            }
        }
    )
    if not existing:
        resBody['status'] = False
        return api_response(200, "Successfully", resBody)
    else:
        resBody['status'] = True
        resBody['tenantId'] = existing.ten_id
        return api_response(500, f"This {email} Is Already Registered. Please Reset Your Password <a href='resetpassword?v={existing.ten_id}'>Click Here</a>", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkActiveSubaccount(request):
    resBody = {'error': '', 'firstName': '', 'lastName': '', 'email': '', 'memberId': 0}
    try:
        enc_tenant_id = request.GET.get('encMemberId', 0)
        tenant_id = DecryptString.set_enc_dec_user(enc_tenant_id, "display", "Y")
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        if not tenant:
            resBody['error'] = "Your Account is deleted. <br>Please Contact Your Administrator."
            return api_response(200, "Successfully", resBody)

        diff_hrs = 0
        if tenant.td_suba_reg_link_expire:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT ROUND((SYSDATE - CAST(TD_SUBA_REG_LINK_EXPIRE AS DATE)) * 24) FROM TENANT_DETAILS WHERE TD_TENANT_ID = %s",
                        [tenant_id]
                    )
                    row = cursor.fetchone()
                    if row:
                        diff_hrs = int(row[0] or 0)
            except Exception:
                diff = timezone.now() - tenant.td_suba_reg_link_expire
                diff_hrs = int(diff.total_seconds() / 3600)

        if diff_hrs > 24:
            resBody['error'] = "Link Is Expired. <br>Please Contact Your Administrator."
        else:
            if tenant.ten_status == 0:
                resBody['error'] = "You Are Already Active. <br>Please Login."

        resBody['firstName'] = tenant.ten_first_name or ''
        resBody['lastName'] = tenant.ten_last_name or ''
        resBody['email'] = tenant.ten_email or ''
        resBody['memberId'] = tenant.ten_id
    except Exception as e:
        logging.getLogger(__name__).error(f"CheckActiveSubaccount Error: {e}")
        resBody['error'] = "error"
    return api_response(200, "Successfully", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def activeSubaccount(request):
    resBody = dict()
    data = request.data
    tenant_id = data.get('memberId')
    tenant = Tenants.objects.get(ten_id=tenant_id)
    tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
    if not tenant:
        return api_response(404, "Tenant Not Found", resBody)
    try:
        tenant.ten_status = 0
        tenant.ten_username = data.get('username', tenant.ten_username)
        tenant_details.td_password = data.get('password', tenant_details.td_password)
        tenant_details.td_login_preference = data.get('loginPreference', tenant_details.td_login_preference)
        tenant_details.td_sec_ans_1 = data.get('secAns1', '') or ''
        tenant_details.td_sec_ans_2 = data.get('secAns2', '') or ''
        tenant_details.td_sec_ans_3 = data.get('secAns3', '') or ''
        tenant_details.td_sec_qus_1 = int(data.get('secQus1', 0) or 0)
        tenant_details.td_sec_qus_2 = int(data.get('secQus2', 0) or 0)
        tenant_details.td_sec_qus_3 = int(data.get('secQus3', 0) or 0)
        tenant_details.td_membership_type = 'Platinum'
        tenant.save()
        tenant_details.save()
        return api_response(200, "Your Account Is Now Activated.", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"checkRegistrationLink Error: {e}")
        return api_response(500, "Error", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def verifiedOtp(request):
    resBody = dict()
    try:
        data = request.data
        otp = data.get('otp', '')
        verified_otp_enc = data.get('verifyedOtp', '') # Note the typo 'verifyed' from Java
        tenant_id = data.get('tenantId')
        
        verified_otp = DecryptString.set_enc_dec_user(verified_otp_enc, "", "Y")
        
        if otp == verified_otp:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": tenant_id
                    }
                }
            )
            if tenant:
                resBody = set_res_body(tenant)
                return api_response(200, "Login Successfully", resBody)
            else:
                return api_response(404, "Tenant Not Found", resBody)
        else:
            return api_response(401, "Otp Not Matched", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"verifiedOtp Error: {e}")
        return api_response(500, "Error", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def processActivation(request):
    resBody = dict()
    try:
        v = request.GET.get('v', '')
        tenant_id = int(DecryptString.set_enc_dec_user(v, "display", "Y"))
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        if tenant:
            if tenant.ten_status == 1:
                resBody['userId'] = tenant_id
                resBody['username'] = tenant.ten_username
                resBody['callingPage'] = "onboarding"
                return api_response(200, "Your Account Is Activated Now. Please Update Your Profile Details.", resBody)
            else:
                resBody['callingPage'] = "login"
                return api_response(200, "Your Account Is Already Activated.", resBody)
        else:
            return api_response(404, "Tenant Not Found", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"processActivation Error: {e}")
        return api_response(500, "Error", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def changepassword(request):
    resBody = dict()
    try:
        data = request.data
        tenant_id = data.get('memberId')
        old_password = data.get('password')
        new_password = data.get('newPassword')

        tenant_details = TenantDetails.objects.filter(tenant__ten_id=tenant_id, td_password=old_password).first()
        if not tenant_details:
            return api_response(304, "Old Password Not Matched", resBody)
            
        tenant_details.td_password = new_password
        tenant_details.save()
        return api_response(200, "Password Changed Successfully", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"changepassword Error: {e}")
        return api_response(500, "Error", resBody)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def resendActivationEmail(request, tenantId):
    resBody = dict()
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenantId
                }
            }
        )
        if not tenant:
            return api_response(404, "Tenant Not Found", resBody)
            
        email = tenant.ten_email
        
        mailRequestDTO = MailRequestDTO()
        mailRequestDTO.to = email
        mailRequestDTO.template_name = "email-template.ftl"
        mailRequestDTO.subject = f"{getattr(settings, 'SITE_NAME', 'SalesAndMarketing')} Activate Account"
        
        model = {
            "Url": f"{getattr(settings, 'SITE_URL', '')}activesetup?v={DecryptString.set_enc_dec_user(str(tenantId), '', 'Y')}",
            "SITEURL": getattr(settings, 'IMAGE_SITE_URL', ''),
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
            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', '')
        }
        
        CommonServices.sendEmail(mailRequestDTO, model)
        return api_response(200, "Account Activation Email Sent To Your Registered Email.", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"resendActivationEmail Error: {e}")
        return api_response(500, "Error", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def changePlan(request):
    resBody = {}
    try:
        data = request.data
        enc_tenant_id = data.get('encTenantId')
        enc_plan_id = data.get('encPlanId')
        
        tenant_id = int(DecryptString.set_enc_dec_user(enc_tenant_id, "display", "Y"))
        plan_id = int(DecryptString.set_enc_dec_user(enc_plan_id, "display", "Y"))

        tenant = Tenants.objects.get(ten_id=tenant_id)
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        if tenant_details:
            tenant_details.td_plan_id = plan_id
            tenant_details.save()
            resBody = set_res_body(get_tenant_common_object(tenant,tenant_details))
            return api_response(200, "Login Successfully", resBody)
        else:
            return api_response(404, "Tenant Not Found", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"changePlan Error: {e}")
        return api_response(500, "Error", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def sendOtpOnboarding(request):
    resBody = dict()
    tenant_id = request.data.get('memberId')
    country_code = request.data.get('countryCode', '+1')
    cell = request.data.get('cell', '')
    
    try:
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        if tenant_details:
            otp = f"{random.randint(100000, 999999)}"
            tenant_details.td_otp = otp
            tenant_details.save()
            
            site_name = getattr(settings, 'SITE_NAME', 'SalesAndMarketing')
            phone_number = f"{country_code}{cell}"
            msg = f"{site_name} Mobile Authentication Code. Your Authentication Code Is : {otp}"
            
            telnyx_from_phone = getattr(settings, 'TELNYX_FROM_PHONE_NO', '')
            
            send_sms_telnyx(
                mobile_no=phone_number,
                telnyx_number=telnyx_from_phone,
                sms_type="onlytext",
                sms_details=msg,
                sms_count="",
                opt_out_msg="",
                sms_status_url=None
            )
            return api_response(200, "Send OTP Successfully", resBody)
        else:
            return api_response(404, "Tenant Not Found", resBody)
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] SendOtpOnboarding Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def addOptInOptOutTemplate(request):
    resBody = dict()
    opt_in_msg = ("##Business Name## has added you as one of their contacts and given you the right "
                  "to maintain your own data. Please ensure your SMS and email address are correct "
                  "by clicking the below link.\n\n##Link##\n\nMsg & Data Rates May Apply. Message "
                  "frequency varies. Reply HELP for help. Reply STOP to unsubscribe.")
    opt_out_msg = ("Sorry to see you go! Rest assured, you have been unsubscribed.\n\nIf you would "
                   "like to receive SMS again from ##Business Name##'s contact list, please reply "
                   'with word "start".')
    try:
        file_dir = getattr(settings, 'FILE_UPLOAD_DIR', '')
        mp_details_map = {}
        for folder in ['optin', 'optout', 'rejoingroup']:
            read_path = os.path.join(file_dir, folder, 'index.html')
            if os.path.exists(read_path):
                with open(read_path, 'r', encoding='utf-8') as f:
                    mp_details_map[folder] = f.read()
            else:
                mp_details_map[folder] = ''

        tenants = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_parent_id": 0
                }
            }
        )
        for m in tenants:
            ten_id = m.ten_id
            if not SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(ten_id), stName='Opt In').exists():
                st = SmsTemplates()
                st.stClientId = get_client_id_by_tenant_id(ten_id)
                st.stDate = timezone.now()
                st.stName = 'Opt In'
                st.stDetails = opt_in_msg
                st.save()
            if not SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(ten_id), stName='Opt Out').exists():
                st = SmsTemplates()
                st.stClientId = get_client_id_by_tenant_id(ten_id)
                st.stDate = timezone.now()
                st.stName = 'Opt Out'
                st.stDetails = opt_out_msg
                st.save()

            for mp_cfg in [('Opt In', 'optin'), ('Opt Out', 'optout'), ('Rejoin Group', 'rejoingroup')]:
                mp_name, mp_folder = mp_cfg
                try:
                    if not MyPages.objects.filter(mpClientId=get_client_id_by_tenant_id(ten_id), mpName=mp_name).exists():
                        mp = MyPages()
                        mp.mpName = mp_name
                        mp.mpTags = ''
                        mp.mpType = 1
                        mp.mpStage = 2
                        mp.mpGroupId = 0
                        mp.mpClientId = get_client_id_by_tenant_id(ten_id)
                        mp.mpTemplateLanguage = 'en'
                        mp.mpTemplateConvertLangList = ''
                        mp.mpAllowConvertLang = 'N'
                        mp.mpBuilditPublish = 'Y'
                        mp.mpPublicUrl = 'Y'
                        mp.mpDetails = mp_details_map.get(mp_folder, '')
                        mp.save()

                        # File system sync mirroring Java logic
                        dest_dir = os.path.join(file_dir, str(ten_id), 'images', 'mypage', str(mp.mpId))
                        if not os.path.exists(dest_dir):
                            os.makedirs(dest_dir)

                        src_dir = os.path.join(file_dir, mp_folder)
                        if os.path.exists(src_dir):
                            for filename in os.listdir(src_dir):
                                src_file = os.path.join(src_dir, filename)
                                if os.path.isfile(src_file):
                                    shutil.copy2(src_file, os.path.join(dest_dir, filename))

                        if not TranslateTemplate.objects.filter(ttMyPageId=mp.mpId, ttClientId=get_client_id_by_tenant_id(ten_id)).exists():
                            tt = TranslateTemplate()
                            tt.ttMyPageId = mp.mpId
                            tt.ttClientId = mp.mpClientId
                            tt.ttCampDetail = mp.mpDetails
                            tt.ttCampDetailSend = mp.mpDetails
                            tt.ttMasterCopy = 'Y'
                            tt.ttTemplateLanguage = 'en'
                            tt.ttPublishDate = timezone.now()
                            tt.save()
                except Exception as mpe:
                    logger.error(f"addOptInOptOutTemplate MyPage {mp_name} error for tenant {ten_id}: {mpe}")
    except Exception as e:
        logger.error(f"addOptInOptOutTemplate Error: {e}")
        return api_response(500, "Error", resBody)
    return api_response(200, "Add Opt-In And Opt-Out Template Successfully", resBody)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteOptInOptOutTemplate(request):
    resBody = dict()
    try:
        tenants = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_parent_id": 0
                }
            }
        )
        for m in tenants:
            SmsTemplates.objects.filter(stClientId=get_client_id_by_tenant_id(m.ten_id), stName__in=['Opt In', 'Opt Out']).delete()
    except Exception as e:
        logger.error(f"deleteOptInOptOutTemplate Error: {e}")
        return api_response(500, "Error", resBody)
    return api_response(200, "Delete Opt-In And Opt-Out Template Successfully", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def updateGroupFields(request):
    resBody = {}
    try:
        groups = Groups.objects.all()
        for g in groups:
            try:
                check_duplicate_records(g.grpId, g.grpClientId)
                check_type_email(g.grpId, g.grpClientId)
                check_total_member(g.grpId, g.grpClientId)
            except Exception as ge:
                logger.error(f"updateGroupFields group {g.grpId} error: {ge}")
    except Exception as e:
        logger.error(f"updateGroupFields Error: {e}")
        return api_response(500, "Error", resBody)
    return api_response(200, "Update Groups Successfully", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def sendOtpAuthenticationCode(request, tenantId):
    resBody = dict()
    try:
        tenant = Tenants.objects.get(ten_id=tenantId)
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenantId)
        if tenant_details:
            otp = f"{random.randint(100000, 999999)}"
            tenant_details.td_otp = otp
            tenant_details.save()
            
            country_code = "+1"
            if tenant.ten_country:
                try:
                    country_obj = Country.objects.filter(country_id=int(tenant.ten_country)).first()
                    if country_obj and country_obj.cnt_code:
                        country_code = country_obj.cnt_code
                except ValueError:
                    pass
            phone_number = f"{country_code}{tenant.ten_cell_phone}" if not tenant.ten_cell_phone.startswith('+') else tenant.ten_cell_phone
            
            site_name = getattr(settings, 'SITE_NAME', 'SalesAndMarketing')
            msg = f"{site_name} Mobile Authentication Code. Your Authentication Code Is : {otp}"
            
            telnyx_from_phone = getattr(settings, 'TELNYX_FROM_PHONE_NO', '')
            send_sms_telnyx(
                mobile_no=phone_number,
                telnyx_number=telnyx_from_phone,
                sms_type="onlytext",
                sms_details=msg,
                sms_count="",
                opt_out_msg="",
                sms_status_url=None
            )
            
            resBody['otp'] = otp
            resBody['id'] = tenantId
            return api_response(304, "An Authentication Code Has Been Sent To Your Registered Mobile Device.", resBody)
        else:
            return api_response(404, "Tenant Not Found", resBody)
    except Exception as e:
        logger.error(f"[ tenantId : {tenantId} ] sendOtpAuthenticationCode Error : {e}")
        return api_response(500, "Error", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def checkLogin(request):
    resBody = dict()
    resBody['error'] = ""
    try:
        data = request.data
        username = data.get('username', '')
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "or": {
                        "ten_username": username,
                        "ten_email": username,
                    }
                }
            }
        )
        if not tenant:
            resBody['error'] = "Tenant Not Found"
            return api_response(404, "Tenant Not Found", resBody)
        login_pref = tenant.td_login_preference or ''
        resBody['loginPreference'] = login_pref
        if login_pref == "googleAuthenticator":
            resBody['secret'] = tenant.td_google_authenticator_secret or ''
        elif login_pref == "microsoftAuthenticator":
            resBody['secret'] = tenant.td_microsoft_authenticator_secret or ''
        resBody['tenantId'] = tenant.ten_id
        resBody['tenStatus'] = tenant.ten_status
        return api_response(200, "Login Successfully", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"checkLogin Error: {e}")
        resBody['error'] = str(e)
        return api_response(500, "Error", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def verifyEmail(request):
    res_body = {"error": "", "verified": False}
    data = request.data
    email = data.get('email', '')
    tenant_id = data.get('memberId', 0)

    try:
        tenant_id = int(tenant_id)
    except (ValueError, TypeError):
        tenant_id = 0

    if not email:
        return api_response(500, "Invalid Email", res_body)

    email = email.lower().strip()

    try:
        # Regex equivalent to Java's checkEmailValidation
        regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.search(regex, email):
            verified = False
            tenant = None

            try:
                if tenant_id > 0:
                    tenant = get_tenants(
                        detail_filters={
                            "tenant": {
                                "ten_email": email
                            }
                        },
                        exclude_conditions={
                            "tenant": {
                                "ten_id": tenant_id
                            }
                        }
                    )
                else:
                    tenant = get_tenants(
                        where_conditions={
                            "tenant": {
                                "ten_email": email
                            }
                        }
                    )
            except Exception:
                pass

            if tenant is None:
                # ZeroBounce Validation
                inner_res_body = ZeroBounceHelper.validate(email)
                verified = inner_res_body.get("status", False)

                if not verified:
                    # Proofy Validation
                    inner_res_body = ProofyHelper.validate(email)
                    if inner_res_body.get("error", "") != "":
                        verified = inner_res_body.get("status", False)
                    else:
                        # Mirror Java: If Proofy has error, default verified to True
                        verified = True
            else:
                res_body["error"] = "error1"

            res_body["verified"] = verified

        # Response structure and overall logic same as Java
        if res_body.get("error") == "" and res_body.get("verified"):
            return api_response(200, "Successfully", res_body)
        elif res_body.get("error") == "error1":
            return api_response(409, "Email Is Already Register", res_body, sendErrorAs200=True)
        else:
            return api_response(500, "Invalid Email", res_body, sendErrorAs200=True)

    except Exception as e:
        logging.getLogger(__name__).error(f"verifyEmail Error: {e}")
        return api_response(500, "Something Went Wrong", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkUsername(request):
    resBody = dict()
    username = request.GET.get('u', '') or request.GET.get('username', '')
    tenant_id = request.GET.get('memberId')

    if int(tenant_id) > 0:
        tenant = Tenants.objects.filter(ten_username=username).exclude(ten_id=tenant_id).first()
    else :
        tenant = Tenants.objects.filter(ten_username=username).first()

    if not tenant:
        resBody['status'] = False
        return api_response(200, "Successfully", resBody)
    else:
        resBody['status'] = True
        return api_response(500, f"Username <strong>{username}</strong> Is Already Registered", resBody)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def registration(request):
    resBody = dict()
    data = request.data
    email = data.get('email')
    
    # Check if email is already registered
    existing_tenant = get_tenants(
        where_conditions={
            "tenant": {
                "ten_email": email
            }
        }
    )
    if existing_tenant:
        resBody['memberId'] = str(existing_tenant.ten_id)
        resBody['status'] = False
        msg = f"This {email} Is Already Registered. Please Reset Your Password <a href='resetpassword?v={existing_tenant.ten_id}'>Click Here</a>"
        return api_response(500, msg, resBody)
    
    tenant_id = data.get('memberId', 0)
    
    if tenant_id == 0 or not tenant_id:
        tenant = Tenants()
        tenant_details = TenantDetails()
        try:
            tenant_details.td_plan_id = int(DecryptString.set_enc_dec_user(data.get('planId'),"display", "Y")) if data.get('planId') else 0
        except ValueError:
            tenant_details.td_plan_id = 0
        tenant.ten_status = 1
    else:
        tenant = Tenants.objects.get(ten_id=tenant_id)
        if not tenant:
            return api_response(404, "Tenant Not Found", resBody)
        tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        tenant.ten_status = 0
        
    tenant.ten_username = data.get('username')
    tenant.ten_email = email
    tenant.ten_cell_phone = data.get('cell')
    tenant_details.td_password = data.get('password')
    tenant_details.td_opt_in = data.get('optin')

    tenant_details.td_sec_ans_1 = ""
    tenant_details.td_sec_ans_2 = ""
    tenant_details.td_sec_ans_3 = ""
    tenant_details.td_sec_qus_1 = 0
    tenant_details.td_sec_qus_2 = 0
    tenant_details.td_sec_qus_3 = 0
    tenant_details.td_membership_type = "Platinum"
    tenant.ten_date_registered = timezone.now()
    tenant.ten_parent_id = 0
    
    try:
        tenant.save()
        tenant_details.tenant=tenant
        tenant_details.save()

        if not tenant_id or tenant_id == 0:
            client = Clients()
            client.cliTenantId=tenant.ten_id
            client.save()
            try:
                pl = TenantPlanDetails()
                pl.tpd_client_id = get_client_id_by_tenant_id(tenant.ten_id)
                pl.tpd_plan_id = tenant_details.td_plan_id
                pl.tpd_added_date = tz.now()
                pl.save()
            except Exception as ple:
                logging.getLogger(__name__).error(f"TenantPlanDetails save error: {ple}")

        # Affiliate Program logic
        code = data.get('code', '') or ''
        if code:
            try:
                code = DecryptString.set_enc_dec_user(code, "display", "Y")
                code_parts = code.split('~')
                if len(code_parts) >= 2:
                    referred_tenant_id = int(code_parts[0])
                    aff_code = code_parts[1]
                    aff_prog = AffiliateProgram.objects.filter(aff_pcode=aff_code).first()
                    if aff_prog:
                        aff_cs = AffiliateCommissionSchedule()
                        aff_cs.aff_c_referred_tenant_id = referred_tenant_id
                        aff_cs.aff_c_tenant_id = tenant.ten_id
                        aff_cs.aff_cpid = aff_prog.aff_pid
                        aff_cs.aff_title = aff_prog.aff_ptitle
                        aff_amount = 0.0
                        if aff_prog.aff_pcommission_type == 1:
                            try:
                                cs = CountrySetting.objects.filter(cnty_plan_id=tenant_details.td_plan_id).first()
                                if cs and cs.cnty_plan_price and cs.cnty_plan_price > 0:
                                    comm = float(aff_prog.aff_pcommission or 0)
                                    aff_amount = (cs.cnty_plan_price * comm) / 100.0
                            except Exception:
                                pass
                        else:
                            aff_amount = float(aff_prog.aff_pcommission or 0)
                        aff_cs.aff_commission_amount = aff_amount
                        aff_cs.aff_commission_type = aff_prog.aff_pcommission_type
                        aff_cs.aff_plan_id = tenant_details.td_plan_id
                        aff_cs.aff_status = 'Pending'
                        aff_cs.aff_c_invoice_date = tz.now()
                        aff_cs.save()
            except Exception as ae:
                logging.getLogger(__name__).error(f"Affiliate schedule error: {ae}")

        # --- Notification Sequence ---
        model = {
            "Details": f"New User Is Registered In {getattr(settings, 'SITE_NAME_BIG_COM', 'SalesAndMarketing.ai')}",
            "UserId": tenant.ten_id,
            "UserName": tenant.ten_username,
            "Email": tenant.ten_email,
            "PlanName": str(tenant_details.td_plan_id),
            "Url": f"{getattr(settings, 'SITE_URL', 'https://qawebapp.salesandmarketing.ai/')}activesetup?v={DecryptString.set_enc_dec_user(str(tenant.ten_id), '', 'Y')}",
            "SITEURL": getattr(settings, 'SITE_URL', 'https://qawebapp.salesandmarketing.ai/'),
            "siteName": getattr(settings, 'SITE_NAME', 'SalesAndMarketing'),
            "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai'),
            "siteUrlWWW": getattr(settings, 'SITE_URL_WWW', 'https://www.salesandmarketing.ai'),
            "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', 'www.salesandmarketing.ai'),
            "companyName": getattr(settings, 'COMPANY_NAME', 'SAM'),
            "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', 'SalesAndMarketing'),
            "siteUrlAddress": getattr(settings, 'SITE_URL_ADDRESS', '6701 Koll Center Parkway #250 Pleasanton, California 94566'),
            "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', '6701 Koll Center Parkway #250 <br>Pleasanton, California 94566'),
            "companyNumber": getattr(settings, 'COMPANY_NUMBER', '415-906-4001 Ext 2'),
            "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', 'salesandmarketing.ai'),
            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', 'SalesAndMarketing.ai')
        }

        # Admin Support Notice
        req_admin = MailRequestDTO(to="support@salesandmarketing.ai", subject="New User Registration In Qa", template_name="notify-registration-template.ftl")
        CommonServices.sendEmail(req_admin, model)

        # User Welcome Notice
        req_user = MailRequestDTO(to=tenant.ten_email, subject="SalesAndMarketing Activate Account", template_name="email-template.ftl")
        CommonServices.sendEmail(req_user, model)

    except Exception as e:
        traceback.print_exc()
        return api_response(500, "Registration Error: " + str(e), resBody)

    # Mimic Java RegistrationDto returned in response body
    resBody['member'] = {
        'memberId': tenant.ten_id,
        'email': tenant.ten_email,
        'username': tenant.ten_username,
        'planId': str(tenant_details.td_plan_id),
        'optin': tenant_details.td_opt_in,
        'cell': tenant.ten_cell_phone
    }
    resBody['status'] = True
    
    return api_response(200, "Registration successful. Please check your email to activate your account.", resBody)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def cancelRegistration(request):
    resBody = dict()
    tenant_id = request.data.get('tenantId')
    email = request.data.get('tenEmail')
    if not tenant_id or not email:
        return api_response(500, "Error", resBody)
    tenant = get_tenants(
        where_conditions={
            "tenant": {
                "ten_id": tenant_id,
                "ten_email": email
            }
        }
    )
    if not tenant:
        return api_response(500, "Error", resBody)
    try:
        # Delete TenantPlanDetails
        try:
            TenantPlanDetails.objects.filter(tpd_client_id=get_client_id_by_tenant_id(tenant_id)).delete()
        except Exception as pe:
            logger.error(f"cancelRegistration TenantPlanDetails delete error: {pe}")
        # Delete BrandKits
        try:
            BrandKits.objects.filter(brand_client_id=get_client_id_by_tenant_id(tenant_id)).delete()
        except Exception as be:
            logger.error(f"cancelRegistration BrandKits delete error: {be}")
        # Delete Tenant
        tenant_obj = Tenants.objects.get(ten_id=tenant_id)
        if tenant_obj:
            tenant_obj.delete()
        return api_response(200, "Registration Cancel Successfully", resBody)
    except Exception as e:
        logger.error(f"cancelRegistration Error: {e}")
        return api_response(500, "Error", resBody)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def checkRegistrationLink(request):
    resBody = {"status": "Y"}
    v = request.GET.get('v', '')
    w = request.GET.get('w', '')
    try:
        # v is encrypted planId in Java: DecryptString.set_enc_dec_user(v, "display", "Y")
        try:
            plan_id = int(DecryptString.set_enc_dec_user(v, "display", "Y"))
        except:
            plan_id = 0
            
        code_str = DecryptString.set_enc_dec_user(w, "display", "Y")
        code_parts = code_str.split("~")
        
        if len(code_parts) >= 2:
            aff_code = code_parts[1]
            try:
                aff_prog = AffiliateProgram.objects.filter(aff_pcode=aff_code).first()
                if aff_prog and aff_prog.aff_pis_active == 'E':
                    resBody['status'] = 'E'
                    return api_response(400, "Affiliate Program Is Closed.", resBody)
            except Exception:
                pass

        plan = Plans.objects.filter(plan_id=plan_id).first()
        if plan and plan.plan_visibility == 'Private':
            # Check if link is expired: cntyLinkExpiryDateTime > SYSDATE
            count = CountrySetting.objects.filter(cnty_plan_id=plan_id, cntyLinkExpiryDateTime__gt=timezone.now()).count()
            if count == 0:
                resBody['status'] = 'N'
                return api_response(400, "This Link Has Been Expired.", resBody)
        
        return api_response(200, "Successfully", resBody)
    except Exception as e:
        logging.getLogger(__name__).error(f"checkRegistrationLink Error: {e}")
        resBody['status'] = 'N'
        return api_response(400, "This Link Has Been Expired.", resBody)
