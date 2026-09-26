from rest_framework.request import Request
import base64
import logging
import os
import math
import requests
import re
from django.db.models import Max, Q, Count
from django.utils.timezone import now
from rest_framework.decorators import api_view
from builditforme_app.views import eas_build_it_for_me_views
from django.conf import settings
from common_app.models import Invoices, CampaignTransaction, SpReply, AffiliateCommissionSchedule, AffiliateProgram, TblSettings, Plans, Userlist, SpTransLog, SpQuestions, SpOptions, CampaignsEmail, CountrySetting, TenantPlanDetails, WebContentGrab, TenDLCData, TenDLCRenew, TenDLCLogs, Clients
from auth_app.models import Tenants, TenantDetails
from common_app.decrypt_string import DecryptString
from common_app.services import commonServices, MailRequestDTO
from django.utils import timezone
from urllib.parse import urlparse
from lxml import html
from common_app.utils import (extract_image_urls_from_html, extract_image_urls_from_style_tags,
                              extract_image_urls_from_css_files, extract_image_urls_from_style_attr,
                              set_file_permissions, get_final_tenant_id, get_tenants, api_response, display_date,
                              uc_words, number_format, br2nl, add_month, convert_date, extract_colors_from_html,
                              extract_colors_from_css_file, get_phone_numbers_first, get_client_id_by_tenant_id,
                              country_setting_by_country_id_and_plan_id)
from decimal import Decimal
from rest_framework_simplejwt.tokens import RefreshToken
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)

@api_view(['GET', 'POST']) # Java maps conditionally GET
def getTenantById(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        client = Clients.objects.filter(cliTenantId=tenant_id).first()
        if tenant is None:
            return api_response(404, "Tenant Not Found", {})
        tenant_data = dict()
        tenant_data['memberId'] = tenant.ten_id
        tenant_data['businessName'] = client.cliBusinessName if client else None
        tenant_data['email'] = tenant.ten_email
        tenant_data['firstName'] = tenant.ten_first_name
        tenant_data['lastName'] = tenant.ten_last_name
        tenant_data['state'] = tenant.ten_state
        tenant_data['address'] = tenant.ten_street_address1
        tenant_data['streetAddress'] = tenant.ten_street_address2
        tenant_data['city'] = tenant.ten_city
        tenant_data['postCode'] = tenant.ten_post_code
        tenant_data['country'] = tenant.ten_country
        tenant_data['phone'] = tenant.ten_phone
        tenant_data['cell'] = tenant.ten_cell_phone
        tenant_data['website'] = client.cliWebsite if client else None
        tenant_data['username'] = tenant.ten_username
        tenant_data['memberDefaultLanguage'] = tenant.ten_default_language

        return api_response(200, "Tenant Fetched Successfully.", tenant_data)
    except Exception as e:
        logging.error(f"GetTenantById Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getMemberByEmail(request, email):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_email": email
                }
            }
        )
        if tenant is None:
            return api_response(404, "Tenant Not Found", {})
        return api_response(200, "Tenant Fetched Successfully.", tenant)
    except Exception as e:
        logging.error(f"GetMemberByEmail Error : {e}")
        return api_response(500, "Error Processing Request", {})

def clean_me_number(number):
    if not number: return number
    return re.sub(r'\D', '', str(number))


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    refresh['firstName'] = user.ten_first_name
    refresh['lastName'] = user.ten_last_name
    refresh['sub'] = user.ten_email

    return str(refresh.access_token)

@api_view(['POST'])
def updateMemberInfo(request: Request):
    try:
        data = request.data
        tenant_id = data.get('memberId')
        try:
            tenant = Tenants.objects.get(ten_id=tenant_id)
            tenant_detail = TenantDetails.objects.get(tenant__ten_id=tenant_id)
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Tenants.DoesNotExist:
             return api_response(404, "Tenant Not Found", {})
        
        resBody = dict()
        old_username = tenant.ten_username
        old_email = tenant.ten_email

        tenant.ten_username = data.get('username')
        tenant.ten_first_name = data.get('firstName')
        tenant.ten_last_name = data.get('lastName')
        tenant.ten_email = data.get('email')
        tenant.ten_default_language = data.get('defaultLanguage')
        tenant.ten_country = data.get('country')
        tenant.ten_state = data.get('state')
        tenant.ten_city = data.get('city')
        tenant.ten_street_address1 = data.get('address')
        tenant.ten_street_address2 = data.get('streetAddress')
        tenant.ten_post_code = data.get('postCode')
        tenant.ten_cell_phone = clean_me_number(data.get('cell'))
        tenant.ten_phone = clean_me_number(data.get('phone'))
        tenant.save()

        tenant_detail.td_country = data.get('country')
        tenant_detail.save()

        client.cliBusinessName = data.get('businessName')
        client.cliWebsite = data.get('websiteName')
        client.save()

        if old_username != data.get('username'):
            resBody["token"] = get_tokens_for_user(tenant)

        if old_email != data.get('email'):
            resBody["token"] = get_tokens_for_user(tenant)

        ret_data = {
            "memberId": tenant.ten_id,
            "businessName": client.cliBusinessName if client.cliBusinessName else None,
            "email": tenant.ten_email if tenant.ten_email else None,
            "firstName": tenant.ten_first_name if tenant.ten_first_name else None,
            "lastName": tenant.ten_last_name if tenant.ten_last_name else None,
            "username": tenant.ten_username if tenant.ten_username else None,
            "defaultLanguage": tenant.ten_default_language,
            "country": tenant.ten_country,
            "state": tenant.ten_state if tenant.ten_state else None,
            "city": tenant.ten_city if tenant.ten_city else None,
            "address": tenant.ten_street_address1 if tenant.ten_street_address1 else None,
            "streetAddress": tenant.ten_street_address2 if tenant.ten_street_address2 else None,
            "postCode": tenant.ten_post_code if tenant.ten_post_code else None,
            "phone": tenant.ten_phone if tenant.ten_phone else None,
            "cell": tenant.ten_cell_phone if tenant.ten_cell_phone else None,
            "websiteName": client.cliWebsite if client.cliWebsite else None,
        }
        resBody["member"] = ret_data
        
        return api_response(200, "Tenant Updated Successfully.", resBody)
    except Exception as e:
        logging.error(f"UpdateMemberInfo Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getSecurityQuestionTab(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        except TenantDetails.DoesNotExist:
             return api_response(404, "Tenant Not Found", {})

        resBody = {
            "member": {
                "memberId": tenant_details.tenant.ten_id,
                "is2FA": tenant_details.td_is2fa,
                "secQus1": tenant_details.td_sec_qus_1,
                "secAns1": tenant_details.td_sec_ans_1 if tenant_details.td_sec_ans_1 else None,
                "secQus2": tenant_details.td_sec_qus_2,
                "secAns2": tenant_details.td_sec_ans_2 if tenant_details.td_sec_ans_2 else None,
                "secQus3": tenant_details.td_sec_qus_3,
                "secAns3": tenant_details.td_sec_ans_3 if tenant_details.td_sec_ans_3 else None,
                "loginPreference": tenant_details.td_login_preference
            }
        }
        return api_response(200, "Security Questions Fetched Successfully.", resBody)
    except Exception as e:
        logging.error(f"GetSecurityQuestionTab Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
def updateSecurityQuestion(request: Request):
    try:
        data = request.data
        tenant_id = data.get('memberId')
        try:
            tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        except TenantDetails.DoesNotExist:
             return api_response(404, "Tenant Not Found", {})

        tenant_details.td_is2fa = data.get('is2FA')
        tenant_details.td_sec_qus_1 = data.get('secQus1')
        tenant_details.td_sec_ans_1 = data.get('secAns1')
        tenant_details.td_sec_qus_2 = data.get('secQus2')
        tenant_details.td_sec_ans_2 = data.get('secAns2')
        tenant_details.td_sec_qus_3 = data.get('secQus3')
        tenant_details.td_sec_ans_3 = data.get('secAns3')
        tenant_details.td_login_preference = data.get('loginPreference')
        tenant_details.save()

        resBody = {
            "member": {
                "memberId": tenant_details.tenant.ten_id,
                "is2FA": tenant_details.td_is2fa,
                "secQus1": tenant_details.td_sec_qus_1,
                "secAns1": tenant_details.td_sec_ans_1 if tenant_details.td_sec_ans_1 else None,
                "secQus2": tenant_details.td_sec_qus_2,
                "secAns2": tenant_details.td_sec_ans_2 if tenant_details.td_sec_ans_2 else None,
                "secQus3": tenant_details.td_sec_qus_3,
                "secAns3": tenant_details.td_sec_ans_3 if tenant_details.td_sec_ans_3 else None,
                "loginPreference": tenant_details.td_login_preference
            }
        }
        return api_response(200, "Updated Successfully.", resBody)
    except Exception as e:
        logging.error(f"UpdateSecurityQuestion Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getCommunicationPreferencesTab(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Clients.DoesNotExist:
             return api_response(404, "Client Not Found", {})
             
        resBody = {
            "member": {
                "memberId": tenant_id,
                "smsCvrMyphoneYn": client.cliSmsForwardMyphoneYn
            }
        }
        return api_response(200, "Communication Preferences Fetched Successfully.", resBody)
    except Exception as e:
        logging.error(f"GetCommunicationPreferencesTab Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
def verifiedOtpOnboarding(request: Request):
    try:
        data = request.data
        tenant_id = data.get('memberId')
        verifyed_otp = data.get('verifyedOtp')
        try:
            tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        except TenantDetails.DoesNotExist:
             return api_response(404, "Tenant Not Found", "")
             
        if tenant_details.td_otp == verifyed_otp:
            return api_response(200, "Otp Matched", "")
        else:
            return api_response(401, "Otp Not Matched", "")
    except Exception as e:
        logging.error(f"VerifiedOtpOnboarding Error : {e}")
        return api_response(500, "Error Processing Request", "")


@api_view(['POST'])
def fileUpload(request: Request):
    tenant_id = 0
    res_body = dict()
    try:
        data = request.data
        if not data.get('file'):
            return api_response(500, "Request Must Contains File", res_body)
            
        tenant_id = get_final_tenant_id(request=request)

        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except TenantDetails.DoesNotExist:
            return api_response(404, "Tenant Not Found", res_body)
        
        file_data = data.get('file', '')
        file_type = data.get('fileType', 'image/png')
        
        # Match Java's base64 prefix removal logic
        # fileData = fileData.replaceAll("data:" + uploadFileOrPicDto.getFileType() + ";base64,", "").replaceAll(" ", "");
        prefix = f"data:{file_type};base64,"
        file_data = file_data.replace(prefix, "").replace(" ", "")
        
        # Fallback for splitting if prefix didn't match exactly
        if "base64," in file_data:
            file_data = file_data.split("base64,")[1]
            
        decoded_bytes = base64.b64decode(file_data)
        
        # Use FILE_UPLOAD_DIR from settings which maps to Java's FILE_DIRECTORY
        base_dir = getattr(settings, 'FILE_UPLOAD_DIR', getattr(settings, 'FILE_DIRECTORY', os.path.join(settings.BASE_DIR, 'uploads')))
        
        # Ensure the path ends with a slash for directory concatenation consistency
        if not base_dir.endswith('/') and not base_dir.endswith('\\'):
            base_dir += '/'
            
        # Match Java nested directory structure: uploads/{tenantId}/images/profilepic/
        target_dir = os.path.join(base_dir, str(tenant_id), 'images', 'profilepic')
        os.makedirs(target_dir, exist_ok=True)
        
        file_path = os.path.join(target_dir, 'profilepic.png')
        
        # Save file and set POSIX permissions (rw-r--r--) equivalent to setFilePermissions
        set_file_permissions(file_path, decoded_bytes)
        
        image_context_path = getattr(settings, 'IMAGE_CONTEXT_PATH', 'https://webapp.salesandmarketing.ai/')
        if not image_context_path.endswith('/'):
            image_context_path += '/'
            
        fileDownloadUri = f"{image_context_path}usercontent/{tenant_id}/images/profilepic/profilepic.png"
        res_body["fileDownloadUri"] = fileDownloadUri
        
        client.cliProfileImageUrl = fileDownloadUri
        client.save()
        
        return api_response(200, "The File Uploaded Successfully", res_body)
    except Exception as e:
        # Match Java's error log format
        logging.error(f"[ tenantId : {tenant_id} ] FileUpload Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

@api_view(['GET'])
def getMemberDetails(request, tenantEncId):
    try:
        # Decipher the tenantEncId using native AES/CFB8 port of Java DecryptString.
        decrypted_tenant_id_str = DecryptString.set_enc_dec_user(tenantEncId, "display", "Y")
        if not (decrypted_tenant_id_str and str(decrypted_tenant_id_str).isdigit()) and tenantEncId.endswith('/'):
            decrypted_tenant_id_str = DecryptString.set_enc_dec_user(tenantEncId.rstrip('/'), "display", "Y")
        try:
            tenant_id = int(decrypted_tenant_id_str)
        except (ValueError, TypeError):
            return api_response(500, "Invalid Tenant ID Format", {})

        try:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": tenant_id
                    }
                }
            )
            phone_number = get_phone_numbers_first(tenant_id, "CAMPAIGN")
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Tenants.DoesNotExist:
             return api_response(404, "Tenant Not Found", {})
             
        resBody = {
            "firstName": tenant.ten_first_name,
            "lastName": tenant.ten_last_name,
            "imageUrl": client.cliProfileImageUrl,
            "twilioNumber": phone_number.phPhoneNumber if phone_number else ""
        }
        return api_response(200, "Tenant Fetched Successfully.", resBody)
    except Exception as e:
        logging.error(f"GetMemberDetails Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
def updateCommunicationPreferences(request: Request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Clients.DoesNotExist:
             return api_response(404, "Client Not Found", {})
             
        data = request.data
        client.cliSmsForwardMyphoneYn = data.get('smsCvrMyphoneYn', client.cliSmsForwardMyphoneYn)
        client.save()

        resBody = {
            "member": {
                "memberId": tenant_id,
                "smsCvrMyphoneYn": client.cliSmsForwardMyphoneYn
            }
        }
        return api_response(200, "Updated Successfully.", resBody)
    except Exception as e:
        logging.error(f"updateCommunicationPreferences Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def updateSmsCvrMyphoneYn(request: Request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Clients.DoesNotExist:
            return api_response(404, "Client Not Found", {})

        yn = request.GET.get('yn', 'N')
        client.cliSmsForwardMyphoneYn = yn
        client.save()

        return api_response(200, "Updated Successfully.", {})
    except Exception as e:
        logging.error(f"[ tenantId : {tenant_id} ] updateSmsCvrMyphoneYn Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getManageAppsTab(request):
    tenant_id = get_final_tenant_id(request=request)
    try:
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Clients.DoesNotExist:
            return api_response(404, "Client Not Found", {})

        resBody = {
            "member": {
                "memberId": tenant_id,
                "smFbId": client.cliFbId if client.cliFbId else "",
                "smFbAccessToken": client.cliFbAccessToken if client.cliFbAccessToken else "",
                "smTwOauthtoken": client.cliTwOauthtoken if client.cliTwOauthtoken else "",
                "smTwOauthtokenSecret": client.cliTwOauthtokenSecret if client.cliTwOauthtokenSecret else "",
                "smLinAuthToken": client.cliLinAuthToken if client.cliLinAuthToken else "",
                "smLinExpiresAt": client.cliLinExpiresAt if client.cliLinExpiresAt else "",
                "zoomToken": client.cliZoomToken if client.cliZoomToken else ""
            }
        }
        return api_response(200, "Apps Data Fetched Successfully.", resBody)
    except Exception as e:
        logging.error(f"[ tenantId : {tenant_id} ] GetManageAppsTab Error : {e}")
        return api_response(500, "Error Processing Request", {})


def print_invoiced(invId, tenantId, sendMail, cron):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenantId
                }
            }
        )
        client = Clients.objects.get(cliTenantId=tenantId)
        if tenant is None:
            return

        countrySetting = commonServices.country_setting_by_tenant_id(tenantId)

        try:
            inv = Invoices.objects.get(invTenantId=tenantId, invId=invId)
        except Invoices.DoesNotExist:
            return

        invDate = ""
        try:
            invDate = display_date(inv.invDate) if inv.invDate else ""
        except Exception:
            pass
        invCampaignAmount = inv.invCampaignAmount or 0.0
        invSurveyAmount = inv.invSurveyAmount or 0.0
        invAssessmentAmount = inv.invAssessmentAmount or 0.0
        invIndividualAmount = inv.invIndividualAmount or 0.0
        invSmsAmount = inv.invSmsAmount or 0.0
        invSmsPollAmount = inv.invSmsPollAmount or 0.0
        invBuildItForMeAmount = inv.invBuildItForMeAmount or 0.0
        invPageTransAmount = inv.invPageTransAmount or 0.0
        invSocialMediaAmount = inv.invSocialMediaAmount or 0.0
        invSMSConversationsAmount = inv.invSMSConversationsAmount or 0.0
        invCallAmount = inv.invCallAmount or 0.0
        invShareAppointmentAmount = inv.invShareAppointmentAmount or 0.0
        invSmsCalendarAmount = inv.invSmsCalendarAmount or 0.0
        invAdditionalContactsAmount = inv.invAdditionalContactsAmount or 0.0
        inv10DLCAmount = inv.inv10DLCAmount or 0.0
        invWarmupAmount = inv.invWarmupAmount or 0.0
        invEmailVerificationAmount = inv.invEmailVerificationAmount or 0.0
        invSmsCalendarReminderAmount = inv.invSmsCalendarReminderAmount or 0.0
        invPreviousUninvoicedAmount = inv.invPreviousUninvoicedAmount or 0.0
        invAiAmount = inv.invAiAmount or 0.0
        invPlanName = inv.invPlanName or ""
        invClientName = inv.invClientName or ""
        invNo = inv.invNo or ""
        invPlanPrice = inv.invPlanPrice or 0.0
        invCurrentContacts = inv.invCurrentContacts or 0
        invTotalAmount = inv.invTotalAmount or 0.0
        invPlanId = inv.invPlanId or 0
        invTransationId = inv.invTransationId or ""
        invPayCardNo = inv.invPayCardNo or ""

        businessName = client.cliBusinessName
        if businessName is None or str(businessName) == "null" or str(businessName) == "":
            businessName = "-"

        address = uc_words(tenant.ten_street_address1)

        siteUrl = getattr(settings, 'SITE_URL', '')
        siteUrlAddress = getattr(settings, 'SITE_URL_ADDRESS', '')
        companyNumber = getattr(settings, 'COMPANY_NUMBER', '')

        s = "<html><body>"
        s += "<style type='text/css'> " + \
             ".table { font-size:12px; font-family:Roboto; } " + \
             ".th { background-color:#CCCCCC; font-size:12px; } " + \
             ".padding { padding-top:8px; padding-bottom:8px; } " + \
             ".table_Width { width:1000px; } " + \
             ".text-left { text-align:left; } " + \
             ".text-center { text-align:center; } " + \
             ".text-right { text-align:right; } " + \
             ".td_bg { background-color:#CCCCCC; padding:5px 0px; } " + \
             ".bold { font-weight:bold; } " + \
             ".font-size { font-size:14px; } " + \
             ".border-top { border-top:1px solid #000; } " + \
             ".border-bottom { border-bottom:1px solid #000; }  " + \
             ".border-left { border-left:1px solid #000; } " + \
             ".border-right { border-right:1px solid #000; } " + \
             "</style>"

        s += "<div align='center'><img style='max-width:170px;max-height: 70px;' src='" + str(siteUrl) + "img/logo.png' /></div>"
        s += "<table style='width:1000px; margin-top:30px;' align='center' cellspacing='0' cellpadding='5'>" + \
             "<tr><td colspan='4' class='font-size border-bottom border-top'>" + str(siteUrlAddress) + " • PHONE: " + str(companyNumber) + "</td></tr>" + \
             "<tr><td class='font-size text-right' width='140'><strong>Client Name :</strong></td>" + \
             "<td class='font-size text-left' width='280'>" + str(invClientName) + "</td>" + \
             "<td class='font-size text-right' width='110'><strong>Client Id :</strong></td>" + \
             "<td class='font-size text-left' width='90'>" + str(tenantId) + "</td></tr>" + \
             "<tr><td class='font-size text-right'><strong>Company Name :</strong></td>" + \
             "<td class='font-size text-left'>" + str(businessName) + "</td>" + \
             "<td class='font-size text-right'><strong>Invoice Date :</strong></td>" + \
             "<td class='font-size text-left'>" + display_date(invDate) + "</td></tr>" + \
             "<tr><td class='font-size text-right'><strong>Address :</strong></td>" + \
             "<td class='font-size text-left'>" + str(address) + "</td>" + \
             "<td class='font-size text-right'><strong>Invoice No. :</strong></td>" + \
             "<td class='font-size text-left'>" + str(invNo) + "</td></tr>" + \
             "<tr><td class='font-size text-left'>&nbsp;</td>" + \
             "<td class='font-size text-left'>" + str(uc_words(tenant.ten_city)) + "  " + str(uc_words(tenant.ten_state)) + " " + str(tenant.ten_post_code) + "</td>" + \
             "<td class='font-size text-left'>&nbsp;</td><td class='font-size text-left'>&nbsp;</td></tr>" + \
             "<tr><td class='font-size border-top'>&nbsp;</td><td class='font-size border-top'>&nbsp;</td><td class='font-size border-top'>&nbsp;</td><td class='font-size border-top'>&nbsp;</td></tr>" + \
             "</table>"

        subTotalMonthly = 0.0
        count = 1
        try:
            s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                 "<tr><td class='font-size'>Plan Details</td></tr></table>" + \
                 "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                 "<tr>" + \
                 "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                 "<th width='800' class='text-center td_bg border-left border-bottom border-top th'>Plan Name</th>" + \
                 "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                 "</tr>"

            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                 "<td class='text-left border-left border-bottom'>" + str(invPlanName) + "</td>" + \
                 "<td class='text-right border-left border-bottom border-right'>"
            if invPlanName.lower() == "pay as you grow":
                s += str(countrySetting.cnty_price_symbol) + "0"
                subTotalMonthly += 0.0
            else:
                s += str(countrySetting.cnty_price_symbol) + str(number_format(invPlanPrice, 2))
                subTotalMonthly += invPlanPrice

            s += "</td></tr>"
            count += 1
            s += "<tr><th class='text-right border-left border-bottom bold' colspan='2'>Sub Total</th>" + \
                 "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(subTotalMonthly, 2)) + "</th></tr></table>"
        except Exception as e:
            logger.error("PrintInvoiced Error 1 : " + str(e))

        pipTot = 0.0
        try:
            totalPreviousUninvoiced = 0.0
            previousUninvoiced = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='previous uninvoiced').order_by('tran_id')
            if previousUninvoiced.exists():
                count = 1
                s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                     "<tr><td class='font-size'>Previous Uninvoiced</td></tr></table>" + \
                     "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                     "<tr>" + \
                     "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                     "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                     "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                     "<th width='540' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                     "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                     "</tr>"
                for trans in previousUninvoiced:
                    campName = str(br2nl(trans.tran_campaign_name))
                    totalPreviousUninvoiced += float(trans.tran_total_amount or 0)
                    cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                    if cost > 0:
                        s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                             "<td class='text-center border-left border-bottom'>"
                        try:
                            if trans.tran_campaign_date:
                                s += str(display_date(trans.tran_campaign_date))
                        except Exception:
                            pass
                        s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                             "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                             "<td class='text-right border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2)) + "</td></tr>"
                    count += 1
                    pipTot += cost
                s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                     "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalPreviousUninvoiced, 2)) + "</th></tr></table>"
        except Exception as e:
            logger.error("PrintInvoiced Error 1 : " + str(e))

        subTotal = subTotalMonthly + pipTot
        totalCampaign = 0.0
        totalSurvey = 0.0
        totalAssessment = 0.0
        totalIndividual = 0.0
        totalSms = 0.0
        totalSmsPolling = 0.0
        totalPageTrans = 0.0
        totalSocialMedia = 0.0
        totalSmsConversations = 0.0
        totalBuildIt = 0.0
        totalSmsCalendar = 0.0
        totalShareAppointment = 0.0
        totalAdditionalContacts = 0.0
        total10DLC = 0.0
        totalSmsCalendarReminder = 0.0
        totalAI = 0.0
        totalAIMember = 0.0

        ccTot = 0.0
        csTot = 0.0
        caTot = 0.0
        ciTot = 0.0
        csmTot = 0.0
        csmPollTot = 0.0
        pollNumCost = 0.0
        ptrTot = 0.0
        somTot = 0.0
        cscTot = 0.0
        acTot = 0.0

        totalCalling = 0.0
        callTot = 0.0
        totalWarmup = 0.0
        totalEmailVerification = 0.0

        if invPlanName.lower() == "pay as you grow":
            try:
                s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                     "<tr><td class='font-size'>Current Contacts</td></tr></table>" + \
                     "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                     "<tr>" + \
                     "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                     "<th width='660' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                     "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Contact</th>" + \
                     "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                     "</tr>"
                s += "<tr><td class='text-center border-left border-bottom'>1</td>" + \
                     "<td class='text-left border-left border-bottom'>Contacts</td>" + \
                     "<td class='text-center border-left border-bottom'>" + str(invCurrentContacts) + "</td>" + \
                     "<td class='text-right border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(invTotalAmount, 2)) + "</td></tr>"
                subTotal = float(invTotalAmount)
                finalInvTotalAmount = (float(invTotalAmount) - float(inv10DLCAmount) - float(invPreviousUninvoicedAmount))
                s += "<tr><th class='text-right border-left border-bottom bold' colspan='3'>Sub Total</th>" + \
                     "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(finalInvTotalAmount, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 1 : " + str(e))

        if invCampaignAmount > 0:
            if invPlanId == 1 or invPlanId == 2 or invPlanName.lower() == "free" or invPlanName.lower() == "pay as you go":
                try:
                    campaign = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='campaign').order_by('tran_id')
                    if campaign.exists():
                        count = 1
                        s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                             "<tr><td class='font-size'>Email Campaign</td></tr></table>" + \
                             "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                             "<tr>" + \
                             "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                             "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                             "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                             "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Campaign Info</th>" + \
                             "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Email Sent</th>" + \
                             "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                             "</tr>"
                        for trans in campaign:
                            campName = str(br2nl(trans.tran_campaign_name))
                            if campName == '' or campName is None:
                                campName = CampaignsEmail.objects.filter(camp_id=trans.tran_campaign_id).values_list('camp_name', flat=True).first() or ""

                            totalCampaign += float(trans.tran_total_member or 0)
                            cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))

                            if cost > 0:
                                s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                     "<td class='text-center border-left border-bottom'>"
                                try:
                                    if trans.tran_campaign_date:
                                        s += str(display_date(trans.tran_campaign_date))
                                except Exception:
                                    pass
                                s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                     "<td class='text-left border-left border-bottom'>" + str(campName) + "</td>" + \
                                     "<td class='text-right border-left border-bottom'>"
                                if trans.tran_total_member == 0:
                                    s += "0"
                                else:
                                    if trans.tran_total_member < 0:
                                        s += "Adjustment - Free Account"
                                    else:
                                        s += str(trans.tran_total_member)
                                s += "</td><td class='text-right border-left border-bottom border-right'>"
                                if trans.tran_total_member < 0:
                                    s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                    cost = cost * -1
                                else:
                                    s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                s += "</td></tr>"
                            count += 1
                            ccTot += cost
                        s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                             "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalCampaign) + "</th>" + \
                             "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(ccTot, 2)) + "</th></tr></table>"
                except Exception as e:
                    logger.error("PrintInvoiced Error 2 : " + str(e))

        if invSurveyAmount > 0:
            try:
                survey = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='survey').order_by('tran_id')
                if survey.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Survey Campaign</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Survey Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Participants</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in survey:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalSurvey += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                if trans.tran_total_member < 0:
                                    s += "Adjustment - Free Account"
                                else:
                                    s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        csTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalSurvey) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(csTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 3 : " + str(e))

        if invAssessmentAmount > 0:
            try:
                assessment = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='assessment').order_by('tran_id')
                if assessment.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Assessment</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Assessment Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Participants</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in assessment:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalAssessment += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        caTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalAssessment) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(caTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 3 : " + str(e))

        if invIndividualAmount > 0:
            try:
                customForm = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='customform').order_by('tran_id')
                if customForm.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Custom Form</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Individual Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Participants</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in customForm:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalIndividual += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        ciTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalIndividual) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(ciTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 4 : " + str(e))

        if invSmsAmount > 0:
            try:
                sms = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type__in=['sms', 'sms number']).order_by('tran_id')
                if sms.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>SMS/MMS Campaign</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>SMS/MMS Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>SMS/MMS</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in sms:
                        smsTot = 0.0
                        campName = str(br2nl(trans.tran_campaign_name))
                        if trans.tran_type == "sms":
                            totalSms += float(trans.tran_count_total_sms or 0)
                            smsTot = float(trans.tran_count_total_sms or 0.0)
                        if trans.tran_type == "sms_number":
                            totalSms += float(trans.tran_total_member or 0)
                            smsTot = float(trans.tran_total_member or 0.0)

                        if trans.tran_type == "sms":
                            cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        else:
                            cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))

                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if smsTot == 0.0:
                                s += "0"
                            else:
                                s += "{:.0f}".format(smsTot)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if (trans.tran_total_member or 0) < 0 and trans.tran_type != "sms":
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        csmTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalSms) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(csmTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 5 : " + str(e))

        if invSmsPollAmount > 0:
            try:
                smsPollingNumber = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='sms polling number').order_by('tran_id')
                if smsPollingNumber.exists():
                    count = 1
                    pollNumCost = 0.0
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>SMS Polling Number Purchased/Renewed</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='680' class='text-center td_bg border-left border-bottom border-top th'>Transaction</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in smsPollingNumber:
                        pollNumCost += float(trans.tran_total_amount or 0)
                        campName = str(br2nl(trans.tran_campaign_name))
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2)) + "</td></tr>"
                        count += 1
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='3'>Sub Total</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(pollNumCost, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 6 : " + str(e))

        if invSmsPollAmount > 0:
            try:
                findTranPollFormNo = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='sms polling').values_list('tran_poll_form_no', flat=True).distinct()
                if findTranPollFormNo:
                    count = 1
                    s += "<table class='table' style='width:1000px; margin-top:10px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>SMS Polling</td></tr></table>" + \
                         "<table  class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='60' class='text-center td_bg border-left border-top th'>Item</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-top th'></th>" + \
                         "<th width='240' class='text-center td_bg border-left border-top th'></th>" + \
                         "<th width='140' class='text-center td_bg border-left border-top th'>&nbsp;</th>" + \
                         "<th width='200' class='text-center td_bg border-left border-top th' colspan='2'>Poll</th>" + \
                         "<th width='160' class='text-center td_bg border-left border-top th' colspan='2'>Response</th>" + \
                         "<th width='80' class='text-center td_bg border-left border-right border-top th'>Cost</th>" + \
                         "</tr><tr>" + \
                         "<th width='60' class='text-center td_bg border-left border-bottom border-top th'>#</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='240' class='text-center td_bg border-left border-bottom border-top th'>Poll Name</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>From Number</th>" + \
                         "<th width='100' class='text-center td_bg border-left border-bottom border-top th'>Message</th>" + \
                         "<th width='100' class='text-center td_bg border-left border-bottom border-top th'>Question</th>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Valid</th>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Invalid</th>" + \
                         "<th width='80' class='text-center td_bg border-left border-right border-bottom border-top th'></th>" + \
                         "</tr>"
                    for tranPollFormNo in findTranPollFormNo:
                        smsPolling = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_poll_form_no=tranPollFormNo, tran_type='sms polling').order_by('tran_id')
                        cost = 0.0
                        pollQues = 0
                        respValid = 0
                        respInvalid = 0
                        welcmsg = 0
                        campName = ""
                        tranDate = None
                        for trans in smsPolling:
                            campName = str(br2nl(trans.tran_campaign_name))
                            tranDate = trans.tran_campaign_date
                            spTransLog = SpTransLog.objects.filter(poll_form_no=trans.tran_poll_form_no, poll_to_no=trans.tran_poll_to_no, campaign_id=trans.tran_campaign_id)
                            for splog in spTransLog:
                                cost += float(splog.transAmt or 0)
                                userReply = str(splog.userReply or "")
                                msgContains = str(splog.msgContains or "")
                                questionSend = str(splog.questionSend or "")
                                countTotMsg = 0

                                if (splog.quesId or 0) != 0:
                                    if msgContains:
                                        if len(msgContains) > 160:
                                            countTotMsg = math.ceil(len(msgContains) / 160.0)
                                        else:
                                            countTotMsg = 1

                                    quesId = splog.quesId

                                    if splog.memberSend == "N":
                                        spQuestions = SpQuestions.objects.filter(ques_id=quesId, campaign_id=trans.tran_campaign_id).first()
                                        if spQuestions:
                                            spOptions = SpOptions.objects.filter(ques_id=quesId)
                                            i = 1
                                            validflag = 0
                                            for op in spOptions:
                                                if spQuestions.queTypeId == 1:
                                                    replystr = str(i) + ") " + str(op.optionVal or "")
                                                    replystr2 = str(i) + ")" + str(op.optionVal or "")
                                                    opVal = str(op.optionVal or "").strip().lower()
                                                    uRep = userReply.strip().lower()
                                                    if str(i) == userReply.strip() or opVal == uRep or replystr.strip().lower() == uRep or replystr2.strip().lower() == uRep:
                                                        validflag = 1
                                                        break
                                                elif spQuestions.queTypeId == 2:
                                                    validflag = 1
                                                i += 1
                                            if validflag == 0:
                                                respInvalid += 2
                                            else:
                                                respValid += 1
                                    if questionSend == "Y":
                                        pollQues += countTotMsg
                                elif (splog.quesId or 0) == 0:
                                    if len(msgContains) > 160:
                                        welcmsg += math.ceil(len(msgContains) / 160.0)
                                    else:
                                        welcmsg += 1

                        cost = abs(float(number_format(cost, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if tranDate:
                                    s += str(display_date(tranDate))
                            except Exception:
                                pass
                            s += "</td><td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + str(tranPollFormNo) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>" + str(welcmsg) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>" + str(pollQues) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>" + str(respValid) + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>" + str(respInvalid) + "</td>" + \
                                 "<td class='text-right border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2)) + "</td></tr>"
                        count += 1
                        totalSmsPolling += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='8'>Sub Total</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalSmsPolling, 2)) + "</th></tr></table>"
                    
                    s += "<table class='table' style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td width='200' class='bold'>Poll Message:</td><td width='800'>These are messages sent before poll start and after it finishes.</td></tr>" + \
                         "<tr><td class='bold'>Poll Questions:</td><td>Number of SMS sent to ask questions in a poll.</td></tr>" + \
                         "<tr><td class='bold'>Response Valid:</td><td>Number of SMS response to question that were valid.</td></tr>" + \
                         "<tr><td class='bold'>Response Invalid:</td><td>Number of SMS response to question that were invalid.</td></tr>" + \
                         "</table>"
                csmPollTot = totalSmsPolling + pollNumCost
            except Exception as e:
                logger.error("PrintInvoiced Error 7 : " + str(e))

        if invPageTransAmount > 0:
            try:
                languageTranslation = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='language translation').order_by('tran_id')
                if languageTranslation.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Language Translation</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Language Translation Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Translation</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in languageTranslation:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalPageTrans += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        ptrTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalPageTrans) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(ptrTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 8 : " + str(e))

        if invSocialMediaAmount > 0:
            try:
                socialMediaPosting = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='social media posting').order_by('tran_id')
                if socialMediaPosting.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Social Media Posting</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Social Media Posting Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Accounts Connected</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in socialMediaPosting:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalSocialMedia += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        somTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalSocialMedia) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(somTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 9 : " + str(e))

        if invSMSConversationsAmount > 0:
            try:
                smsConversations = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='sms conversations').order_by('tran_id')
                if smsConversations.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>SMS Conversations</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>SMS Conversations Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Users Added</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in smsConversations:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalSmsConversations += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        cscTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalSmsConversations) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(cscTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 10 : " + str(e))

        if invCallAmount > 0:
            try:
                calling = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='calling').order_by('tran_id')
                if calling.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Calling</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Calling Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Participants / Minutes</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in calling:
                        callingTot = 0.0
                        campName = str(br2nl(trans.tran_campaign_name))
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))

                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if callingTot == 0.0:
                                s += "0"
                            else:
                                s += "{:.0f}".format(callingTot)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if (trans.tran_total_member or 0) < 0 and trans.tran_type != "call":
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        callTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalCalling) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(callTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 11 : " + str(e))

        if invBuildItForMeAmount > 0:
            try:
                buildItForMe = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='builditforme').order_by('tran_id')
                if buildItForMe.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Build It For Me</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Build It For Me Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Participants</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    buildTot = 0.0
                    for trans in buildItForMe:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalBuildIt += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        buildTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalBuildIt) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(buildTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 12 : " + str(e))

        if invSmsCalendarAmount > 0:
            try:
                smsCalendarAppointment = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='sms calendar appointment').order_by('tran_id')
                if smsCalendarAppointment.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>SMS Calendar Appointment</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>SMS Sent</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    scaTot = 0.0
                    for trans in smsCalendarAppointment:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalSmsCalendar += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        scaTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalSmsCalendar) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(scaTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 13 : " + str(e))

        if invShareAppointmentAmount > 0:
            try:
                shareAppointmentLink = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='share appointment link').order_by('tran_id')
                if shareAppointmentLink.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Share Appointment Link</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>SMS/Email Sent</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    saTot = 0.0
                    for trans in shareAppointmentLink:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalShareAppointment += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        saTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalShareAppointment) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(saTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 14 : " + str(e))

        if invAdditionalContactsAmount > 0:
            try:
                additionalContacts = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='additional contacts').order_by('tran_id')
                if additionalContacts.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Additional Contacts</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Contacts</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    for trans in additionalContacts:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalAdditionalContacts += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        acTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalAdditionalContacts) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(acTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 15 : " + str(e))

        if inv10DLCAmount > 0:
            try:
                tenDLC = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='10DLC').order_by('tran_id')
                if tenDLC.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>10DLC Campaign</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='540' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    tenDLCTot = 0.0
                    for trans in tenDLC:
                        campName = str(br2nl(trans.tran_campaign_name))
                        total10DLC += float(trans.tran_total_amount or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2)) + "</td></tr>"
                        count += 1
                        tenDLCTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(total10DLC, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 16 : " + str(e))

        if invWarmupAmount > 0:
            try:
                warmupTrans = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='domain warmup').order_by('tran_id')
                if warmupTrans.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Warmup Email System</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='540' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    wuTot = 0.0
                    for trans in warmupTrans:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalWarmup += float(trans.tran_total_amount or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2)) + "</td></tr>"
                        count += 1
                        wuTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalWarmup, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 17 : " + str(e))

        if invEmailVerificationAmount > 0:
            try:
                emailVerificationTrans = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='email verification').order_by('tran_id')
                if emailVerificationTrans.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>Email Verification</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Verification Emails</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    evTot = 0.0
                    for trans in emailVerificationTrans:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalEmailVerification += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        evTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalEmailVerification) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(evTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 18 : " + str(e))

        if invSmsCalendarReminderAmount > 0:
            try:
                smsCalendarReminder = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='sms calendar reminder').order_by('tran_id')
                if smsCalendarReminder.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>SMS Calendar Reminder</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>SMS Sent</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    scrTot = 0.0
                    for trans in smsCalendarReminder:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalSmsCalendarReminder += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format((trans.tran_total_member or 0) * (trans.tran_member_rate or 0), 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        scrTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalSmsCalendarReminder) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(scrTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 19 : " + str(e))

        if invAiAmount > 0:
            try:
                aiImage = CampaignTransaction.objects.filter(ct_client_id=get_client_id_by_tenant_id(tenantId), tran_invoiced_id=invId, tran_type='ai').order_by('tran_id')
                if aiImage.exists():
                    count = 1
                    s += "<table style='width:1000px; margin-top:10px;' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr><td class='font-size'>AI Image Charges</td></tr></table>" + \
                         "<table class='table_Width table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
                         "<tr>" + \
                         "<th width='80' class='text-center td_bg border-left border-bottom border-top th'>Item #</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Date</th>" + \
                         "<th width='140' class='text-center td_bg border-left border-bottom border-top th'>Transaction Id</th>" + \
                         "<th width='420' class='text-center td_bg border-left border-bottom border-top th'>AI Image Info</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-bottom border-top th'>Generated Image</th>" + \
                         "<th width='120' class='text-center td_bg border-left border-right border-bottom border-top th'>Total Cost</th>" + \
                         "</tr>"
                    aiTot = 0.0
                    for trans in aiImage:
                        campName = str(br2nl(trans.tran_campaign_name))
                        totalAIMember += float(trans.tran_total_member or 0)
                        cost = abs(float(number_format(trans.tran_total_amount or 0, 2)))
                        if cost > 0:
                            s += "<tr><td class='text-center border-left border-bottom'>" + str(count) + "</td>" + \
                                 "<td class='text-center border-left border-bottom'>"
                            try:
                                if trans.tran_campaign_date:
                                    s += str(display_date(trans.tran_campaign_date))
                            except Exception:
                                pass
                            s += "</td><td class='text-center border-left border-bottom'>" + str(trans.tran_id) + "</td>" + \
                                 "<td class='text-left border-left border-bottom'>" + campName + "</td>" + \
                                 "<td class='text-right border-left border-bottom'>"
                            if trans.tran_total_member == 0:
                                s += "0"
                            else:
                                s += str(trans.tran_total_member)
                            s += "</td><td class='text-right border-left border-bottom border-right'>"
                            if trans.tran_total_member < 0:
                                s += "-" + str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                                cost = cost * -1
                            else:
                                s += str(countrySetting.cnty_price_symbol) + str(number_format(cost, 2))
                            s += "</td></tr>"
                        count += 1
                        aiTot += cost
                    s += "<tr><th class='text-right border-left border-bottom bold' colspan='4'>Sub Total</th>" + \
                         "<th class='text-right border-left border-bottom bold'>" + "{:.0f}".format(totalAIMember) + "</th>" + \
                         "<th class='text-right border-left border-right border-bottom bold'>" + str(countrySetting.cnty_price_symbol) + str(number_format(aiTot, 2)) + "</th></tr></table>"
            except Exception as e:
                logger.error("PrintInvoiced Error 20 : " + str(e))

        s += "<table class='table' style='width:1000px; margin-top:40px' align='left' cellspacing='0' cellpadding='5'><tr>" + \
             "<th class='bold td_bg border-left border-bottom border-right border-top th' colspan='2'>Summary</th>" + \
             "</tr>"

        if subTotalMonthly > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Plan Price</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(subTotalMonthly, 2)) + "</th>" + \
                 "</tr>"

        if pipTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Previous Uninvoiced</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(pipTot, 2)) + "</th>" + \
                 "</tr>"

        if ccTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Email Campaign</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(ccTot, 2)) + "</th>" + \
                 "</tr>"

        if csTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Survey Campaign</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(csTot, 2)) + "</th>" + \
                 "</tr>"

        if caTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Assessment</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(caTot, 2)) + "</th>" + \
                 "</tr>"

        if ciTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Custom Form</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(ciTot, 2)) + "</th>" + \
                 "</tr>"

        if csmTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>SMS/MMS Campaign</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(csmTot, 2)) + "</th>" + \
                 "</tr>"

        if csmPollTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>SMS Polling</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(csmPollTot, 2)) + "</th>" + \
                 "</tr>"

        if ptrTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Language Translation</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(ptrTot, 2)) + "</th>" + \
                 "</tr>"

        if somTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Social Media Posting</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(somTot, 2)) + "</th>" + \
                 "</tr>"

        if cscTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>SMS Conversations</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(cscTot, 2)) + "</th>" + \
                 "</tr>"

        if callTot > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Calling</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(callTot, 2)) + "</th>" + \
                 "</tr>"

        if totalBuildIt > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Build It For Me</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalBuildIt, 2)) + "</th>" + \
                 "</tr>"

        if totalSmsCalendar > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Sms Calendar Appointment</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalSmsCalendar, 2)) + "</th>" + \
                 "</tr>"

        if totalShareAppointment > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Share Appointment Link</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalShareAppointment, 2)) + "</th>" + \
                 "</tr>"

        if totalAdditionalContacts > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Additional Contacts</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalAdditionalContacts, 2)) + "</th>" + \
                 "</tr>"

        if total10DLC > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>10DLC Process Charges</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(total10DLC, 2)) + "</th>" + \
                 "</tr>"

        if totalWarmup > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Domain Warmup Service</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalWarmup, 2)) + "</th>" + \
                 "</tr>"

        if totalEmailVerification > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Group Contact Verification Charges</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalEmailVerification, 2)) + "</th>" + \
                 "</tr>"

        if totalSmsCalendarReminder > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>SMS Calender Reminder</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalSmsCalendarReminder, 2)) + "</th>" + \
                 "</tr>"

        if totalAI > 0:
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>AI Image Charges</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(totalAI, 2)) + "</th>" + \
                 "</tr>"

        if invPlanName.lower() != "pay as you grow":
            subTotal += ccTot + csTot + caTot + ciTot + csmTot + csmPollTot + ptrTot + somTot + cscTot + callTot + totalBuildIt + totalSmsCalendar + totalShareAppointment + totalAdditionalContacts + total10DLC + totalWarmup + totalEmailVerification + totalSmsCalendarReminder + ccTot + totalAI

        s += "<tr>" + \
             "<th style='width:830px;' class='text-right bold border-left border-bottom'>Sub Total</th>" + \
             "<th style='width:170px;' class='text-right bold border-left border-bottom border-right'>" + str(countrySetting.cnty_price_symbol) + str(number_format(subTotal, 2)) + "</th>" + \
             "</tr>"

        if tenant.td_membership_type == "Free":
            s += "<tr>" + \
                 "<th class='text-right bold border-left border-bottom'>Adjustment - You have a Free Account.  Enjoy!</th>" + \
                 "<th class='text-right bold border-left border-bottom border-right'>-" + str(countrySetting.cnty_price_symbol) + str(number_format(subTotal, 2)) + "</th>" + \
                 "</tr>"
            invTransationId = "Free"
            invPayCardNo = "Free"
            subTotal = 0.0

        s += "<tr>" + \
             "<th class='text-right bold border-left border-bottom' style='font-size:14px'>Total Due</th>" + \
             "<th class='text-right bold border-left border-bottom border-right' style='font-size:14px'>" + str(countrySetting.cnty_price_symbol) + str(number_format(subTotal, 2)) + "</th>" + \
             "</tr>"
        s += "</table>"

        siteName = getattr(settings, 'SITE_NAME', '')
        siteNameBigCom = getattr(settings, 'SITE_NAME_BIG_COM', '')
        siteNameSmallCom = getattr(settings, 'SITE_NAME_SMALL_COM', '')
        toAdminSupportEmail = getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai')
        siteUrlWWW = getattr(settings, 'SITE_URL_WWW', '')
        siteUrlWWWDisplay = getattr(settings, 'SITE_URL_WWW_DISPLAY', '')
        companyName = getattr(settings, 'COMPANY_NAME', '')
        mainCompanyName = getattr(settings, 'MAIN_COMPANY_NAME', '')
        siteUrlAddressBr = getattr(settings, 'SITE_URL_ADDRESS_BR', '')
        toEmailAdminMember1 = getattr(settings, 'TO_EMAIL_ADMIN_MEMBER_1', 'patel.ritesh.mscit@gmail.com')

        s += "<table class='table' style='width:1000px' align='left' cellspacing='0' cellpadding='5'>" + \
             "<tr><td>&nbsp;</td></tr>" + \
             "<tr><td><strong>Credit Card Transaction ID :</strong> "
        s += str(invTransationId or "")
        s += "</td></tr>" + \
             "<tr><td><strong>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Credit Card Charged :</strong> "
        s += str(countrySetting.cnty_price_symbol) + str(number_format(subTotal, 2))
        s += "</td></tr>" + \
             "<tr><td><strong>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Credit Card : </strong>"
        s += str(invPayCardNo or "")
        s += "</td></tr>" + \
             "<tr><td>&nbsp;</td></tr>" + \
             "<tr><td>Thank you for using " + str(siteName) + " for your marketing! If you have any question or concerns, please contacts us at " + str(toAdminSupportEmail) + " or call " + str(companyNumber) + ".</td></tr>"
        s += "</table>"
        s += "</body></html>"

        fileName = "print-invoiced-" + str(tenantId) + "-" + str(invNo) + ".pdf"
        pdfSaveUrl = getattr(settings, 'PDF_SAVE_DIR', '')
        filePath = os.path.join(pdfSaveUrl, fileName)
        try:
            if os.path.exists(filePath):
                os.remove(filePath)
        except Exception as e:
            logger.error("Error deleting old PDF: " + str(e))

        try:
            with open(filePath, "wb") as result_file:
                pisa_status = pisa.CreatePDF(s, dest=result_file)
                if pisa_status.err:
                    logger.error("PDF generation failed via xhtml2pdf.")
        except Exception as e:
            logger.error("Error creating PDF: " + str(e))
        if sendMail == "sendMail":
            model = {
                "clientName": invClientName,
                "memberId": tenantId,
                "invNo": invNo,
                "cntyPriceSymbol": countrySetting.cnty_price_symbol,
                "subTotal": subTotal,
                "invDate": invDate,
                "siteName": siteName,
                "toAdminSupportEmail": toAdminSupportEmail,
                "siteUrlWWW": siteUrlWWW,
                "siteUrlWWWDisplay": siteUrlWWWDisplay,
                "companyName": companyName,
                "mainCompanyName": mainCompanyName,
                "siteUrlAddress": siteUrlAddress,
                "siteUrlAddressBr": siteUrlAddressBr,
                "companyNumber": companyNumber,
                "siteNameSmallCom": siteNameSmallCom,
                "siteNameBigCom": siteNameBigCom,
                "invStatus": "Adjustment - Free Account" if tenant.td_membership_type == "Free" else "PAID",
                "SITEURL": siteUrl
            }

            mailRequestDTO = MailRequestDTO(
                to=tenant.ten_email,
                file_name=fileName,
                file_path=filePath,
                template_name="invoiced-template.ftl",
                subject="Invoice from " + str(siteNameBigCom)
            )

            response = commonServices.sendEmail(mailRequestDTO, model)

            try:
                invoice = Invoices.objects.get(invTenantId=tenantId, invId=invId)
                rounded_subTotal = float(number_format(subTotal, 2))
                if not response or response.status is False:
                    invoice.invSendMail = "N"
                    invoice.invSubTotal = rounded_subTotal
                    invoice.save(update_fields=["invSendMail", "invSubTotal"])
                else:
                    invoice.invSendMail = "Y"
                    invoice.invSubTotal = rounded_subTotal
                    invoice.save(update_fields=["invSendMail", "invSubTotal"])
            except Exception as e:
                logger.error("Error updating invoice table: " + str(e))

            if toEmailAdminMember1:
                mailRequestDTO.to = toEmailAdminMember1
                commonServices.sendEmail(mailRequestDTO, model)

    except Exception as e:
        logger.error("PrintInvoiced Master Error : " + str(e))

def generate_invoiced(tenantId):
    try:
        tenants = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenantId
                },
                "tenant_details": {
                    "td_authorize_customer_profile_id__isnull": False,
                    "td_authorize_customer_payment_profile_id__isnull": False
                }
            },
            return_type="all"
        )
        for tenant in tenants:
            tblSettings = TblSettings.objects.first()
            assert tblSettings is not None
            billPeriod = int(re.sub(r'[^0-9]', '', tblSettings.bill_period))
            try:
                currentDate = timezone.now().date()
                bYear = currentDate.year
                bMonth = currentDate.month
                bDate = f"{bYear}-{bMonth}-01 00:00:00"
                TenantDetails.objects.filter(
                    tenant__ten_id=tenantId
                ).update(
                    td_bill_date=add_month(convert_date(bDate), billPeriod)
                )
            except Exception as exception:
                logger.error("GenerateInvoiced Error 1 : %s", exception)

            tenantId = tenant.ten_id
            countrySetting = commonServices.country_setting_by_tenant_id(tenantId)

            firstName = tenant.ten_first_name
            lastName = tenant.ten_last_name
            invClientName = firstName + " " + lastName
            email = tenant.ten_email
            invFirst = "no"
            try:
                countInvId = Invoices.objects.filter(invTenantId=tenantId).count()
                if countInvId > 0:
                    invFirst = "no"
                else:
                    invFirst = "yes"
            except Exception as e:
                logger.error("GenerateInvoiced Error 2 : %s", e)

            price = 0.0
            surveyPrice = 0.0
            assessmentPrice = 0.0
            individualPrice = 0.0
            smsPrice = 0.0
            smsPollPrice = 0.0
            pageTransPrice = 0.0
            socialMediaPrice = 0.0
            smsConversationsPrice = 0.0
            shareAppointmentPrice = 0.0
            smsCalendarPrice = 0.0
            smsCalendarReminderPrice = 0.0
            previousUninvoicedPrice = 0.0
            additionalContactsPrice = 0.0
            aiPrice = 0.0
            tenDLCPrice = 0.0
            ps = 0.0
            pc = 0.0
            pa = 0.0
            pi = 0.0
            psm = 0.0
            psmPoll = 0.0
            ptr = 0.0
            psom = 0.0
            psc = 0.0
            callingPrice = 0.0
            pcl = 0.0
            sca = 0.0
            sal = 0.0
            acp = 0.0
            scrp = 0.0
            pip = 0.0
            aip = 0.0

            totalCampaign = 0.0
            totalSurvey = 0.0
            totalAssessment = 0.0
            totalIndividual = 0.0
            totalSms = 0.0
            totalSmsPoll = 0.0
            totalPageTrans = 0.0
            totalSMSConversations = 0.0
            totalCalling = 0.0
            totalSmsCalendar = 0.0
            totalShareAppointment = 0.0
            totalAdditionalContacts = 0.0
            total10DLC = 0.0
            totalWarmup = 0.0
            warmupPrice = 0.0
            totalEmailVerification = 0.0
            emailVerificationPrice = 0.0
            evp = 0.0
            totalSmsCalendarReminder = 0.0
            totalPreviousUninvoiced = 0.0
            totalAI = 0.0

            campaignTransactions = CampaignTransaction.objects.filter(
                ct_client_id=get_client_id_by_tenant_id(tenantId),
                tran_invoiced_status='uninvoiced',
                tran_bill_type=0
            ).order_by('-tran_id')

            for ct in campaignTransactions:
                tenantId = ct.ct_client_id
                if ct.tran_type == "campaign":
                    pc = ct.tran_member_rate
                    totalCampaign += ct.tran_total_member
                    price += (ct.tran_total_member * ct.tran_member_rate)
                elif ct.tran_type == "survey":
                    ps = ct.tran_member_rate
                    totalSurvey += ct.tran_total_member
                    if ct.tran_member_rate > 0:
                        surveyPrice += (ct.tran_total_member * ct.tran_member_rate)
                elif ct.tran_type == "assessment":
                    pa = ct.tran_member_rate
                    totalAssessment += ct.tran_total_member
                    assessmentPrice += (ct.tran_total_member * ct.tran_member_rate)
                elif ct.tran_type == "customform":
                    pi = ct.tran_member_rate
                    totalIndividual += ct.tran_total_member
                    individualPrice += (ct.tran_total_member * ct.tran_member_rate)
                elif ct.tran_type == "sms":
                    totalSms += ct.tran_total_member
                    smsPrice += ct.tran_total_amount
                    psm = ct.tran_member_rate
                elif ct.tran_type == "sms number":
                    totalSms += ct.tran_total_member
                    smsPrice += ct.tran_total_amount
                    psm = ct.tran_member_rate
                elif ct.tran_type == "sms polling":
                    totalSmsPoll += ct.tran_total_member
                    smsPollPrice += ct.tran_total_amount
                    psmPoll = ct.tran_member_rate

                    SpReply.objects.filter(
                        fromNo=ct.tran_poll_form_no,
                        toNo=ct.tran_poll_to_no,
                        smspollingId=ct.tran_campaign_id,
                        tranId=0
                    ).update(
                        tranId=ct.tran_id
                    )

                    SpTransLog.objects.filter(
                        fromNo=ct.tran_poll_form_no,
                        toNo=ct.tran_poll_to_no,
                        smspollingId=ct.tran_campaign_id,
                        tranId=0
                    ).update(
                        tranId=ct.tran_id
                    )

                elif ct.tran_type == "sms polling number":
                    totalSmsPoll += ct.tran_total_member
                    smsPollPrice += ct.tran_total_amount
                    psmPoll = ct.tran_member_rate
                elif ct.tran_type == "language translation":
                    totalPageTrans += ct.tran_total_member
                    pageTransPrice += ct.tran_total_amount
                    ptr = ct.tran_member_rate
                elif ct.tran_type == "sms conversations" or ct.tran_type == "sms conversations number":
                    totalSMSConversations += ct.tran_total_member
                    smsConversationsPrice += ct.tran_total_amount
                    psc = ct.tran_member_rate
                elif ct.tran_type == "calling":
                    totalCalling += ct.tran_total_member
                    callingPrice += ct.tran_total_amount
                    pcl = ct.tran_member_rate
                elif ct.tran_type == "sms calendar appointment":
                    totalSmsCalendar += ct.tran_total_member
                    smsCalendarPrice += ct.tran_total_amount
                    sca = ct.tran_member_rate
                elif ct.tran_type == "share appointment link":
                    totalShareAppointment += ct.tran_total_member
                    shareAppointmentPrice += ct.tran_total_amount
                    sal = ct.tran_member_rate
                elif ct.tran_type == "additional contacts":
                    totalAdditionalContacts += ct.tran_total_member
                    additionalContactsPrice += ct.tran_total_amount
                    acp = ct.tran_member_rate
                elif ct.tran_type == "10DLC":
                    total10DLC += ct.tran_total_member
                    tenDLCPrice += ct.tran_total_amount
                elif ct.tran_type == "domain warmup":
                    totalWarmup += ct.tran_total_member
                    warmupPrice += ct.tran_total_amount
                elif ct.tran_type == "email verification":
                    totalEmailVerification += ct.tran_total_member
                    emailVerificationPrice += ct.tran_total_amount
                    evp = ct.tran_member_rate
                elif ct.tran_type == "sms calendar reminder":
                    totalSmsCalendarReminder += ct.tran_total_member
                    smsCalendarReminderPrice += ct.tran_total_amount
                    scrp = ct.tran_member_rate
                elif ct.tran_type == "previous uninvoiced":
                    totalPreviousUninvoiced += ct.tran_total_member
                    previousUninvoicedPrice += ct.tran_total_amount
                    pip = ct.tran_member_rate
                elif ct.tran_type == "AI":
                    totalAI += ct.tran_total_member
                    aiPrice += ct.tran_total_amount
                    aip = ct.tran_member_rate

            amt = (float(f"{price:.2f}")
                   + float(f"{surveyPrice:.2f}")
                   + float(f"{assessmentPrice:.2f}")
                   + float(f"{individualPrice:.2f}")
                   + float(f"{smsPrice:.2f}")
                   + float(f"{smsPollPrice:.2f}")
                   + float(f"{pageTransPrice:.2f}")
                   + float(f"{socialMediaPrice:.2f}")
                   + float(f"{smsConversationsPrice:.2f}")
                   + float(f"{callingPrice:.2f}")
                   + float(f"{smsCalendarPrice:.2f}")
                   + float(f"{shareAppointmentPrice:.2f}")
                   + float(f"{additionalContactsPrice:.2f}")
                   + float(f"{countrySetting.cnty_plan_price:.2f}")
                   + float(f"{tenDLCPrice:.2f}")
                   + float(f"{warmupPrice:.2f}")
                   + float(f"{emailVerificationPrice:.2f}")
                   + float(f"{smsCalendarReminderPrice:.2f}")
                   + float(f"{previousUninvoicedPrice:.2f}")
                   + float(f"{aiPrice:.2f}"))

            flag = 0
            curContacts = Userlist.objects.filter(
                groupId__gt=0,
                memberId=get_client_id_by_tenant_id(tenantId),
                badEmail__in=['N', 'B', 'D'],
                badPhoneNumber='N'
            ).filter(
                Q(optId__isnull=True) | Q(optId=0),
                Q(status='Subscribed') | Q(smsStatus='Subscribed'),
                groupId__isnull=False
            ).aggregate(
                eCount=Count('emailId')
            )['eCount'] or 0

            plan = Plans.objects.get(
                plan_id=tenant.td_plan_id,
                plan_active='Y'
            )

            if plan.plan_name.lower() == "pay as you grow":
                amt = (
                        Decimal(str(tenDLCPrice))
                        + Decimal(str(previousUninvoicedPrice))
                        + (
                                Decimal(curContacts)
                                * Decimal(str(countrySetting.ctny_contact_per_price))
                        )
                )

                price = 0.0
                surveyPrice = 0.0
                assessmentPrice = 0.0
                individualPrice = 0.0
                smsPrice = 0.0
                smsPollPrice = 0.0
                pageTransPrice = 0.0
                socialMediaPrice = 0.0
                smsConversationsPrice = 0.0
                callingPrice = 0.0
                smsCalendarPrice = 0.0
                shareAppointmentPrice = 0.0
                additionalContactsPrice = 0.0
                warmupPrice = 0.0
                emailVerificationPrice = 0.0
                smsCalendarReminderPrice = 0.0
                aiPrice = 0.0

            elif plan.plan_visibility == "Public" and invFirst == "yes":
                if amt < countrySetting.cnty_first_inv_free_amt:
                    flag = 1

            if flag == 0:
                if amt >= countrySetting.cnty_inv_less_amt_not_charge:
                    invPayCardNo = ""
                    invTransationId = ""
                    errorCode = ""
                    errorMessage = ""
                    if tenant.td_membership_type == "Free":
                        resultCode = "Ok"
                    else:
                        maxInvoicedNo = 0
                        try:
                            maxInvoicedNo = Invoices.objects.filter(
                                invCountryId=tenant.ten_country
                            ).aggregate(
                                max_inv_no=Max('invNo')
                            )['max_inv_no']

                            if maxInvoicedNo is None:
                                maxInvoicedNo = 0
                            else:
                                maxInvoicedNo += 1
                        except Exception:
                            pass

                        resInnerBody = eas_build_it_for_me_views.check_charge_payment_profile(tenantId, float(amt), maxInvoicedNo)
                        resultCode = resInnerBody.get("resultCode")
                        errorCode = resInnerBody.get("errorCode")
                        errorMessage = resInnerBody.get("errorMessage")
                        invPayCardNo = resInnerBody.get("invPayCardNo")
                        invTransationId = resInnerBody.get("invTransationId")

                    if resultCode == "Ok":
                        if tenant.td_membership_type != "Free":
                            affiliateCommissionSchedule = AffiliateCommissionSchedule.objects.filter(aff_c_tenant_id=tenantId,aff_status='Pending').first()
                            if affiliateCommissionSchedule is not None:
                                if affiliateCommissionSchedule.aff_commission_type == 1:
                                    apAmount = 0.0
                                    if amt > 0:
                                        affiliate_program = AffiliateProgram.objects.filter(aff_pid=affiliateCommissionSchedule.aff_cpid).first()
                                        if affiliate_program:
                                            aff_pcommission = affiliate_program.aff_pcommission
                                        else:
                                            aff_pcommission = 0
                                        if countrySetting.cnty_plan_price > 0:
                                            apAmount = (countrySetting.cnty_plan_price * aff_pcommission) / 100
                                        else:
                                            apAmount = (amt * aff_pcommission) / 100

                                    affiliateCommissionSchedule.aff_commission_amount = apAmount

                                affiliateCommissionSchedule.aff_status = "Done"
                                affiliateCommissionSchedule.aff_c_invoice_date = timezone.now()
                                affiliateCommissionSchedule.save()

                        maxInvoicedNo = 1
                        try:
                            maxInvoicedNo = Invoices.objects.filter(
                                invCountryId=tenant.ten_country
                            ).aggregate(
                                max_inv_no=Max('invNo')
                            )['max_inv_no']
                            if maxInvoicedNo is None:
                                maxInvoicedNo = 1
                            else:
                                maxInvoicedNo = int(maxInvoicedNo) + 1
                        except Exception:
                            pass

                        invoice = Invoices()
                        invoice.invNo = maxInvoicedNo
                        invoice.invDate = timezone.now()
                        invoice.invCampaignAmount = price
                        invoice.invSurveyAmount = surveyPrice
                        invoice.invAssessmentAmount = assessmentPrice
                        invoice.invIndividualAmount = individualPrice
                        invoice.invSmsAmount = smsPrice
                        invoice.invSmsPollAmount = smsPollPrice
                        invoice.invPageTransAmount = pageTransPrice
                        invoice.invSocialMediaAmount = socialMediaPrice
                        invoice.invSMSConversationsAmount = smsConversationsPrice
                        invoice.invCallAmount = callingPrice
                        invoice.invShareAppointmentAmount = shareAppointmentPrice
                        invoice.invSmsCalendarAmount = smsCalendarPrice
                        invoice.inv10DLCAmount = tenDLCPrice
                        invoice.invWarmupAmount = warmupPrice
                        invoice.invAdditionalContactsAmount = additionalContactsPrice
                        invoice.invEmailVerificationAmount = emailVerificationPrice
                        invoice.invSmsCalendarReminderAmount = smsCalendarReminderPrice
                        invoice.invPreviousUninvoicedAmount = previousUninvoicedPrice
                        invoice.invAiAmount = aiPrice
                        invoice.invTotalAmount = amt
                        invoice.invTenantId = get_client_id_by_tenant_id(tenantId)
                        invoice.invClientName = invClientName
                        invoice.invCampaignPrice = pc
                        invoice.invSurveyPrice = ps
                        invoice.invAssessmentPrice = pa
                        invoice.invIndividualPrice = pi
                        invoice.invSmsPrice = psm
                        invoice.invSmsPollPrice = psmPoll
                        invoice.invPageTransPrice = ptr
                        invoice.invSocialMediaPrice = psom
                        invoice.invSMSConversationsPrice = psc
                        invoice.invCallPrice = pcl
                        invoice.invShareAppointmentPrice = sal
                        invoice.invSmsCalendarPrice = sca
                        invoice.invAdditionalContactsPrice = acp
                        invoice.invEmailVerificationPrice = evp
                        invoice.invSmsCalendarReminderPrice = scrp
                        invoice.invPreviousUninvoicedPrice = pip
                        invoice.invAiPrice = aip
                        invoice.invPerContactPrice = countrySetting.ctny_contact_per_price
                        invoice.invCountryId = tenant.ten_country
                        invoice.invCurrentContacts = curContacts

                        if tenant.td_membership_type == "Free":
                            invoice.invAdjustmentsAmount = amt
                            invoice.invSubTotal = 0
                            invoice.invTransationId = "Free"
                            invoice.invPayCardNo = "Free"
                            tranInvoicedStatus = "Adjustment - Free Account"
                        else :
                            invoice.invSubTotal = amt
                            invoice.invTransationId = invTransationId
                            invoice.invPayCardNo = invPayCardNo
                            tranInvoicedStatus = "invoiced"

                        invoice.invMonthlyYN = "N"

                        invoice.invPlanId = plan.plan_id
                        if plan.plan_name.lower() == "pay as you grow":
                            invoice.invPlanPrice = 0.0
                        else:
                            invoice.invPlanPrice = countrySetting.cnty_plan_price

                        invoice.invPlanName = plan.plan_name

                        invoice.save()
                        invId = invoice.invId

                        CampaignTransaction.objects.filter(
                            tran_invoiced_status='uninvoiced',
                            tran_bill_type=0,
                            ct_client_id=get_client_id_by_tenant_id(tenantId)
                        ).update(
                            tran_invoiced_id=invId,
                            tran_invoiced_status=tranInvoicedStatus,
                            tran_invoiced_date=now().date()
                        )

                        # Print invoiced code start
                        print_invoiced(invId, tenantId, "sendMail", "cron")
                        # End

                    else:
                        if errorCode == "2":
                            str_error = " General decline (customer should contact bank). This card number appears to be incorrect or may have insufficient funds"
                        elif errorCode == "3":
                            str_error = " Referral to issuer (bank verification needed) Your bank requires additional security"
                        elif errorCode == "4":
                            str_error = " Lost or stolen card (stop retrying) Your bank has this card registered as lost or stolen"
                        elif errorCode == "27":
                            str_error = " AVS mismatch (address mismatch) Your billing address (zip code) appears to be incorrect"
                        elif errorCode == "44":
                            str_error = " CVV mismatch (security code incorrect) Please confirm your Security Code is correct"
                        elif errorCode == "45":
                            str_error = " AVS + CVV mismatch (high fraud risk) Your Address and CVC are not correct. High Security Fraud"
                        elif errorCode == "65":
                            str_error = " CVV failed (too many failed attempts) Too Many Attempts"
                        elif errorCode == "7":
                            str_error = " Credit card expiration date is invalid"
                        elif errorCode == "6" or errorCode == "37":
                            str_error = " The credit card number is invalid"
                        elif errorCode == "165":
                            str_error = " Please confirm your CVV is correct"
                        elif errorCode == "8":
                            str_error = " Credit card has expired"
                            Tenants.objects.filter(ten_id=tenantId).update(ten_status=2)

                            model = {}
                            mailRequestDTO = MailRequestDTO()
                            mailRequestDTO.to = email
                            mailRequestDTO.template_name = "bad-credit-card-template.ftl"
                            mailRequestDTO.subject = settings.SITE_NAME + " Bad Credit Card"
                            model["invClientName"] = invClientName
                            model["error"] = str_error
                            model["cardNumber"] = invPayCardNo
                            model["SITEURL"] = settings.SITE_URL
                            model["siteName"] = settings.SITE_NAME
                            model["toAdminSupportEmail"] = settings.TO_ADMIN_SUPPORT_EMAIL
                            model["siteUrlWWW"] = settings.SITE_URL_WWW
                            model["siteUrlWWWDisplay"] = settings.SITE_URL_WWW_DISPLAY
                            model["companyName"] = settings.COMPANY_NAME
                            model["mainCompanyName"] = settings.MAIN_COMPANY_NAME
                            model["siteUrlAddress"] = settings.SITE_URL_ADDRESS
                            model["siteUrlAddressBr"] = settings.SITE_URL_ADDRESS_BR
                            model["companyNumber"] = settings.COMPANY_NUMBER
                            model["siteNameSmallCom"] = settings.SITE_NAME_SMALL_COM
                            model["siteNameBigCom"] = settings.SITE_NAME_BIG_COM
                            commonServices.sendEmail(mailRequestDTO, model)
                        elif errorCode == "E00039":
                            str_error = "Your CC is used on another account in our system"
                        else:
                            str_error = " " + errorMessage

                        model = {}
                        mailRequestDTO = MailRequestDTO()
                        mailRequestDTO.to = email
                        mailRequestDTO.template_name = "credit-card-template.ftl"
                        mailRequestDTO.subject = "Please update your " + settings.SITE_NAME_BIG_COM + " account to avoid any service interruptions"
                        model["invClientName"] = invClientName
                        model["error"] = str_error
                        model["cardNumber"] = invPayCardNo
                        model["profileUrl"] = settings.SITE_URL + "carddetails"
                        model["SITEURL"] = settings.SITE_URL
                        model["siteName"] = settings.SITE_NAME
                        model["toAdminSupportEmail"] = settings.TO_ADMIN_SUPPORT_EMAIL
                        model["siteUrlWWW"] = settings.SITE_URL_WWW
                        model["siteUrlWWWDisplay"] = settings.SITE_URL_WWW_DISPLAY
                        model["companyName"] = settings.COMPANY_NAME
                        model["mainCompanyName"] = settings.MAIN_COMPANY_NAME
                        model["siteUrlAddress"] = settings.SITE_URL_ADDRESS
                        model["siteUrlAddressBr"] = settings.SITE_URL_ADDRESS_BR
                        model["companyNumber"] = settings.COMPANY_NUMBER
                        model["siteNameSmallCom"] = settings.SITE_NAME_SMALL_COM
                        model["siteNameBigCom"] = settings.SITE_NAME_BIG_COM
                        commonServices.sendEmail(mailRequestDTO, model)
                else:
                    CampaignTransaction.objects.filter(
                        ct_client_id=get_client_id_by_tenant_id(tenantId),
                        tran_invoiced_status='uninvoiced'
                    ).exclude(
                        tran_type__in=['sms number', 'sms polling number', 'sms conversations number']
                    ).delete()
    except Exception as e:
        logger.error("GenerateInvoiced Error : %s", e)

@api_view(['POST'])
def updatePlan(request: Request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
            tenant = Tenants.objects.get(ten_id=tenant_id)
        except TenantDetails.DoesNotExist:
             return api_response(404, "Tenant Not Found", {})
             
        enc_plan_id = request.data.get('encPlanId', '')
        if not enc_plan_id:
             return api_response(500, "Plan ID missing", {})
             
        resBody = {"error": ""}
        try:
            # Decrypting Plan ID
            decrypted_plan_id_str = DecryptString.set_enc_dec_user(enc_plan_id, "display", "Y")
            new_plan_id = int(decrypted_plan_id_str)
            
            try:
                new_plan = Plans.objects.get(plan_id=new_plan_id)
            except Plans.DoesNotExist:
                return api_response(500, "Invalid Plan ID", resBody)
                
            old_plan_id = tenant_details.td_plan_id if tenant_details.td_plan_id else 1
            
            if old_plan_id != new_plan_id:
                try:
                    old_plan = Plans.objects.get(plan_id=old_plan_id)
                    old_is_payg = (
                            old_plan.plan_id == 2 or
                            old_plan.plan_name.lower() == "pay as you go" or
                            old_plan.plan_name.lower() == "pay as you grow"
                    )

                    new_is_payg = (
                            new_plan.plan_id == 2 or
                            new_plan.plan_name.lower() == "pay as you go" or
                            new_plan.plan_name.lower() == "pay as you grow"
                    )

                    if old_is_payg:
                        CampaignTransaction.objects.filter(
                            ct_client_id=get_client_id_by_tenant_id(tenant_id),
                            tran_invoiced_status='uninvoiced'
                        ).exclude(
                            tran_type__in=[
                                'sms number',
                                'sms polling number',
                                'sms conversations number'
                            ]
                        ).delete()

                    if new_is_payg:
                        generate_invoiced(tenant_id)

                except Plans.DoesNotExist:
                    pass

                total_contact_uploaded = commonServices.total_contact_uploaded(tenant_id)

                country_setting = country_setting_by_country_id_and_plan_id(tenant.ten_country, new_plan_id)

                new_is_payg = (new_plan.plan_id == 2 or new_plan.plan_name.lower() == "pay as you go" or new_plan.plan_name.lower() == "pay as you grow")

                if total_contact_uploaded <= country_setting.cnty_contacts_included or new_is_payg:
                    tenant_details.td_plan_id = new_plan_id
                    tenant_details.save()

                    try:
                        TenantPlanDetails.objects.create(plogs_member_id=tenant_id, plogs_plan_id=tenant_details.td_plan_id, plogs_added_date=timezone.now())
                    except Exception:
                        pass
                else:
                    resBody["error"] = "Your Current Contacts Are Greater Then Selected Plan Contacts.\nPlease Select Other Higher Plan."
            else:
                resBody["error"] = "Please Update Your Payment Profile"
        except Exception as e:
            resBody["error"] = "error"
            logging.error(f"UpdatePlan Inner Error : {e}")

        if resBody["error"] == "":
            resBody["msg"] = "Plan Update Successfully"
            return api_response(200, resBody["msg"], resBody)
        elif resBody["error"] != "error":
            return api_response(500, resBody["error"], resBody)
        else:
            return api_response(500, "Error Processing Request", resBody)
            
    except Exception as e:
        logging.error(f"UpdatePlan Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
def uploadWhiteListingLogo(request: Request):
    res_body = dict()
    try:
        data = request.data
        if not data.get('file'):
            return api_response(500, "Request Must Contains File", res_body)
            
        tenant_id = get_final_tenant_id(request=request)
            
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Clients.DoesNotExist:
            return api_response(404, "Client Not Found", res_body)
        
        file_data = data.get('file', '')
        file_type = data.get('fileType', 'image/png')
        
        prefix = f"data:{file_type};base64,"
        file_data = file_data.replace(prefix, "").replace(" ", "")
        
        # Fallback for splitting if prefix didn't match exactly
        if "base64," in file_data:
            file_data = file_data.split("base64,")[1]
            
        decoded_bytes = base64.b64decode(file_data)
        
        # Use FILE_UPLOAD_DIR from settings which maps to Java's FILE_DIRECTORY
        base_dir = getattr(settings, 'FILE_UPLOAD_DIR', getattr(settings, 'FILE_DIRECTORY', os.path.join(settings.BASE_DIR, 'uploads')))
        
        if not base_dir.endswith('/') and not base_dir.endswith('\\'):
            base_dir += '/'
            
        # Match Java nested directory structure: uploads/{tenantId}/images/whitelistinglogo/
        target_dir = os.path.join(base_dir, str(tenant_id), 'images', 'whitelistinglogo')
        os.makedirs(target_dir, exist_ok=True)
        
        file_path = os.path.join(target_dir, 'logo.png')
        
        # Save file and set POSIX permissions (rw-r--r--) equivalent to setFilePermissions
        set_file_permissions(file_path, decoded_bytes)
        
        image_context_path = getattr(settings, 'IMAGE_CONTEXT_PATH', 'https://webapp.salesandmarketing.ai/')
        if not image_context_path.endswith('/'):
            image_context_path += '/'
            
        fileDownloadUri = f"{image_context_path}usercontent/{tenant_id}/images/whitelistinglogo/logo.png"
        res_body["fileDownloadUri"] = fileDownloadUri
        
        client.cliLogo = fileDownloadUri
        client.save()
        
        return api_response(200, "The File Uploaded Successfully", res_body)
    except Exception as e:
        # Match Java's error log format: log.error("UploadWhiteListingLogo Error : " + e);
        logging.error(f"UploadWhiteListingLogo Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

@api_view(['POST'])
def updateWhiteListingDetails(request: Request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Clients.DoesNotExist:
             return api_response(404, "Client Not Found", {})
             
        cli_customer_footer = request.data.get('whiteListingDetails')
        if cli_customer_footer is not None:
            client.cliCustomerFooter = cli_customer_footer
            client.save()
            
        return api_response(200, "WhiteListing Details Updated Successfully", {})
    except Exception as e:
        logging.error(f"UpdateWhiteListingDetails Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getWhiteListingDetails(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Clients.DoesNotExist:
             return api_response(404, "Client Not Found", {})
             
        resBody = {
            "whiteListingLogo": client.cliLogo if client.cliLogo else "",
            "whiteListingDetails": client.cliCustomerFooter if client.cliCustomerFooter else ""
        }
        return api_response(200, "WhiteListing Details Fetched Successfully", resBody)
    except Exception as e:
        logging.error(f"GetWhiteListingDetails Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def checkSmsWhiteFlag(request):
    try:
        return api_response(200, "Check SMS White List Successfully.", {})
    except Exception as e:
        logging.error(f"CheckSmsWhiteFlag Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
def set10DLCStatus(request: Request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            tenant = Tenants.objects.get(ten_id=tenant_id)
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Tenants.DoesNotExist:
             return api_response(404, "Tenant Not Found", {})
             
        status = request.data.get('status', False)
        
        if status:
            client.cli10DlcStatus = "Processing"
        else:
            client.cli10DlcStatus = "No"
            if client.cli10DlcStatus == "No":
                TenDLCRenew.objects.create(
                    rnw_member_id=get_client_id_by_tenant_id(tenant.ten_id),
                    rnw_continue="No",
                    rnw_date=timezone.now().date()
                )
            
        client.save()

        TenDLCLogs.objects.create(
            member_id=get_client_id_by_tenant_id(tenant.ten_id),
            dlc_status=client.cli10DlcStatus,
            dlc_date=timezone.now()
        )
        
        try:
            if status:
                msgBody = "<p>We have got new 10DLC registration.</p>"
                msgBody += f"<p>Tenant Id : {tenant_id}</p>"
                msgBody += "<p>First Name : "
                if tenant.ten_first_name:
                     msgBody += tenant.ten_first_name.title()
                msgBody += "</p>"
                msgBody += "<p>Last Name : "
                if tenant.ten_last_name:
                     msgBody += tenant.ten_last_name.title()
                msgBody += "</p>"

                mail_dto = MailRequestDTO(
                    to=getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai'),
                    subject="Request For 10DLC Approval",
                    template_name="approval-10dlc-template.ftl"
                )
                
                model_data = {
                    "SITEURL": getattr(settings, 'IMAGE_SITE_URL', ''),
                    "msgBody": msgBody,
                    "siteName": getattr(settings, 'SITE_NAME', ''),
                    "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai'),
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
                
                commonServices.sendEmail(mail_dto, model_data)
        except Exception as ee:
            logging.error(f"Set10DLCStatus Email Error : {ee}")
        
        msg = "Set On 10DLC Successfully" if status else "Set Off 10DLC Successfully"
        return api_response(200, msg, {})
    except Exception as e:
        logging.error(f"Set10DLCStatus Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def get10DLCStatus(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            tenant = Tenants.objects.get(ten_id=tenant_id)
            client = Clients.objects.get(cliTenantId=tenant_id)
        except Tenants.DoesNotExist:
             return api_response(404, "Tenant Not Found", {})
             
        country_id = getattr(tenant, 'ten_country', None)
        if country_id:
            country_setting = CountrySetting.objects.filter(cnty_id=country_id).first()
        else:
            country_setting = CountrySetting.objects.first()
            
        ten_dlc_price = "0.00"
        price_symbol = "$"
        if country_setting:
            if country_setting.cnty_10dlc_price is not None:
                 ten_dlc_price = f"{country_setting.cnty_10dlc_price:.2f}"
            price_symbol = country_setting.cnty_price_symbol or "$"
             
        resBody = {
            "tenDLCPrice": ten_dlc_price,
            "priceSymbol": price_symbol,
            "status": client.cli10DlcStatus if client.cli10DlcStatus else "No"
        }
        return api_response(200, "Get 10DLC Successfully", resBody)
    except Exception as e:
        logging.error(f"Get10DLCStatus Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['POST'])
def grabWebsiteLinks(request: Request):
    url = request.data.get('url')
    if not url:
        return api_response(400, "URL is required", {})

    try:
        valid_links = set()
        try:
            url = str(url)
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                tree = html.fromstring(resp.text)
                links = tree.xpath('//a/@href')
                
                # Java logic: String domain = url.split("\\.")[url.split("\\.").length-2];
                parsed_url = urlparse(url)
                netloc = parsed_url.netloc or parsed_url.path.split('/')[0]
                url_parts = netloc.split('.')
                if len(url_parts) >= 2:
                    domain = url_parts[-2]
                else:
                    domain = url_parts[0]
                
                for link in links:
                    if link and link.startswith('http') and domain in link:
                        valid_links.add(link)
        except Exception:
            pass
            
        resBody = {}
        if valid_links:
            resBody["websiteLinks"] = list(valid_links)
        else:
            # Fallback to grabHomePageLinks (async approach via WebContentGrab)
            webContentGrab = WebContentGrab.objects.create(
                type="links",
                request=url,
                is_started=0,
                is_processed=0
            )
            resBody["wcgId"] = webContentGrab.id

        return api_response(200, "Grab Home Page Links", resBody)
    except Exception as e:
        logging.error(f"grabWebsiteLinks Error : {e}")
        
        site_url_www = getattr(settings, 'SITE_URL_WWW', 'salesandmarketing.ai')
        error_msg = ("We can not connect to ##website_name##.  It is not allowing us to gather the information.  "
                     "Please contact your administrator to allow <a href='##siteUrlWWW##'>##siteUrlWWW##</a> to crawl your website "
                     "in order to use this wizard to import your brand logo, images, and colors. \n "
                     "If this is not possible then now worries you can set this up manually.")
        error_msg = error_msg.replace("##website_name##", url).replace("##siteUrlWWW##", site_url_www)
        
        return api_response(500, error_msg, {})

@api_view(['POST'])
def grabHomePageLinks(request: Request):
    try:
        url = request.data.get('url')
        if not url:
            return api_response(400, "URL is required", {})
            
        try:
            url = str(url)
            resp = requests.get(url, timeout=5)
            # basic regex to find hrefs
            hrefs = set(re.findall(r'href=[\'"]?([^\'" >]+)', resp.text))
            
            domain = urlparse(url).netloc
            valid_links = []
            for h in hrefs:
                if h.startswith('http') and domain in h:
                    valid_links.append(h)
                    
            resBody = {"websiteLinks": valid_links[:20]}
        except Exception:
            resBody = {"websiteLinks": []}
            
        return api_response(200, "Grab Home Page Links", resBody)
    except Exception as e:
        logging.error(f"grabHomePageLinks Error : {e}")
        return api_response(500, "Scraping Error", {})

@api_view(['POST'])
def grabWebsiteImages(request: Request):
    urls = request.data.get('urls', [])
    if not urls:
        return api_response(400, "URLs are required", {})

    try:
        valid_images = set()
        
        # Mirroring grabWebsiteImagesNormal logic
        for url in urls:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    tree = html.fromstring(resp.text)
                    valid_images.update(extract_image_urls_from_html(tree, url))
                    valid_images.update(extract_image_urls_from_style_tags(tree, url))
                    valid_images.update(extract_image_urls_from_css_files(tree, url))
                    valid_images.update(extract_image_urls_from_style_attr(tree, url))
            except Exception:
                pass
        
        resBody = {}
        if valid_images:
            resBody["imageUrls"] = list(valid_images)
        else:
            # Fallback to grabWebsiteImages (async approach via WebContentGrab)
            request_str = ",".join(urls)
            webContentGrab = WebContentGrab.objects.create(
                type="images",
                request=request_str,
                is_started=0,
                is_processed=0
            )
            resBody["wcgId"] = webContentGrab.id

        return api_response(200, "Grab Website Images", resBody)
    except Exception as e:
        logging.error(f"grabWebsiteImages Error : {e}")
        
        site_url_www = getattr(settings, 'SITE_URL_WWW', 'salesandmarketing.ai')
        error_msg = ("We can not connect to ##website_name##.  It is not allowing us to gather the information.  "
                     "Please contact your administrator to allow <a href='##siteUrlWWW##'>##siteUrlWWW##</a> to crawl your website "
                     "in order to use this wizard to import your brand logo, images, and colors. \n "
                     "If this is not possible then now worries you can set this up manually.")
        error_msg = error_msg.replace("##website_name##", urls[0]).replace("##siteUrlWWW##", site_url_www)
        
        return api_response(500, error_msg, {})

@api_view(['POST'])
def grabWebsiteColors(request: Request):
    urls = request.data.get('urls', [])
    if not urls:
        return api_response(400, "URLs are required", {})

    try:
        valid_colors = set()
        
        # Mirroring grabWebsiteColorsNormal logic
        for url in urls:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    tree = html.fromstring(resp.text)
                    valid_colors.update(extract_colors_from_html(resp.text))
                    valid_colors.update(extract_colors_from_css_file(tree, resp.text, url))
            except Exception:
                pass
        
        resBody = {}
        if valid_colors:
            resBody["websiteColors"] = list(valid_colors)
        else:
            # Fallback to grabWebsiteColors (async approach via WebContentGrab)
            request_str = ",".join(urls)
            webContentGrab = WebContentGrab.objects.create(
                type="colors",
                request=request_str,
                is_started=0,
                is_processed=0
            )
            resBody["wcgId"] = webContentGrab.id

        return api_response(200, "Grab Website Colors", resBody)
    except Exception as e:
        logging.error(f"grabWebsiteColors Error : {e}")
        
        site_url_www = getattr(settings, 'SITE_URL_WWW', 'salesandmarketing.ai')
        error_msg = ("We can not connect to ##website_name##.  It is not allowing us to gather the information.  "
                     "Please contact your administrator to allow <a href='##siteUrlWWW##'>##siteUrlWWW##</a> to crawl your website "
                     "in order to use this wizard to import your brand logo, images, and colors. \n "
                     "If this is not possible then now worries you can set this up manually.")
        error_msg = error_msg.replace("##website_name##", urls[0]).replace("##siteUrlWWW##", site_url_www)
        
        return api_response(500, error_msg, {})

@api_view(['POST'])
def save10DLCData(request: Request):
    try:
        tenant_id = get_final_tenant_id(request=request)

        TenDLCData.objects.create(
            dat_member_id=get_client_id_by_tenant_id(tenant_id),
            dat_brand_name=request.data.get('datBrandName'),
            dat_campaign_type=request.data.get('datCampaignType'),
            dat_is_active=request.data.get('datIsActive'),
            dat_registration_date=timezone.now().date()
        )
        
        resBody = dict()
        return api_response(200, "10DLC Saved Successfully", resBody)
    except Exception as e:
        logging.error(f"Save10DLCData Error : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def getAll10DLCData(request):
    try:
        tenant_id = get_final_tenant_id(request=request)

        records = TenDLCData.objects.filter(dat_member_id=get_client_id_by_tenant_id(tenant_id)).order_by('-dat_id')
        
        ten_dlc_data = []
        for record in records:
            ten_dlc_data.append({
                "datId": record.dat_id,
                "datMemberId": record.dat_member_id,
                "datBrandName": record.dat_brand_name,
                "datCampaignType": record.dat_campaign_type,
                "datIsActive": record.dat_is_active,
                "datRegistrationDate": record.dat_registration_date.strftime('%m-%d-%Y') if record.dat_registration_date else None
            })
            
        resBody = {
            "tenDLCData": ten_dlc_data
        }
        return api_response(200, "Fetch Data Successfully", resBody)
    except Exception as e:
        logging.error(f"GetAll10DLCData Error : {e}")
        return api_response(500, "Error Processing Request", {})