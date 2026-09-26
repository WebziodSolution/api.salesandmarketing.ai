from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.db import connection
from common_app.decrypt_string import DecryptString
import logging
import random
import re
import json
import traceback
from django.utils import timezone
from django.db.models import Q, OuterRef, Subquery
from authorizenet import apicontractsv1
from authorizenet.apicontrollers import getCustomerProfileController
from common_app.models import (Userlist, EmailVerification, ContactSendSmsLogs, UnsubscribeLogs, CampaignsEmailSend, CampaignsSendEmail, CountrySetting, Udf, TranslateTemplate, MyCrmSendEmail, AutomationLinkClickEmail, CampaignTransaction, Country, CampaignSendSms, CampaignSmsReply, SmsConversations, SmsConversationsDetails, SpReply, MyPages, Groups, NumberCallForwarding, CountryToState, Language, SecurityQuestion, Plans, AutomationSmsReplyLog, CampaignsSmsSend, SpQuestions, SpOptions, SpSmsPolling, SpTransLog, Clients, PhoneNumbers, CampaignsSms)
from automation_app.models import Automation, AutomationSmsDetails, AutomationCampaignNode
import base64
from bs4 import BeautifulSoup
from common_app import telnyx_utils
from auth_app.models import Tenants
from common_app.utils import cron_send_campaign_content_remove, nl2br, strip_slashes, country_setting_by_country_id_and_plan_id, check_duplicate_records, check_total_member, clean_me_number, get_tenants, get_phone_numbers_first, get_client_id_by_tenant_id, get_tenant_id_by_client_id
from django.db.models.functions import Length
from authorizenet.constants import constants

logger = logging.getLogger(__name__)

class MailRequestDTO:
    def __init__(self, to=None, subject=None, template_name=None, file_name=None, file_path=None):
        self.to = to
        self.subject = subject
        self.template_name = template_name
        self.file_name = file_name
        self.file_path = file_path

class MailResponseDTO:
    def __init__(self, message=None, status=None):
        self.message = message
        self.status = status

class CommonServices:
    @staticmethod
    def sendEmail(mailRequestDTO, model):
        try:
            # Render Django HTML corresponding to the requested template name
            template_name = mailRequestDTO.template_name.replace('.ftl', '.html')

            # The 'model' dict corresponds directly to Java's Map<String, Object> model
            html_content = render_to_string(template_name, model)

            # Extract plain text fallback (strip HTML tags)
            # Since html_content now contains real tags (due to |safe in template), this will work.
            text_content = re.sub('<[^<]+>', '', html_content)

            sender = getattr(settings, 'DEFAULT_FROM_EMAIL', 'support@salesandmarketing.ai')
            subject = mailRequestDTO.subject
            recipient = mailRequestDTO.to

            # Build and Send
            msg = EmailMultiAlternatives(subject, text_content, sender, [recipient])
            msg.attach_alternative(html_content, "text/html")
            
            # Attach file if provided
            if mailRequestDTO.file_name and mailRequestDTO.file_path:
                try:
                    with open(mailRequestDTO.file_path, 'rb') as f:
                        msg.attach(mailRequestDTO.file_name, f.read(), 'application/octet-stream')
                except Exception as attach_e:
                    logger.error(f"Error attaching file to email: {attach_e}")
                    
            msg.send()

            return MailResponseDTO(message="Email Sent Successfully", status=True)

        except Exception as e:
            logger.exception(f"Error sending email: {str(e)}")
            return MailResponseDTO(message=str(e), status=False)

    @staticmethod
    def country_setting_by_tenant_id(tenant_id):
        if tenant_id and tenant_id > 0:
            try:
                tenant = get_tenants(
                    where_conditions={
                        "tenant": {
                            "ten_id": tenant_id
                        }
                    }
                )
                country_id = "100" if tenant.ten_country is None or tenant.ten_country == "" or tenant.ten_country == "0" else tenant.ten_country
                plan_id = 1 if tenant.td_plan_id is None or tenant.td_plan_id == "" or tenant.td_plan_id == "0" else tenant.td_plan_id
                return country_setting_by_country_id_and_plan_id(int(country_id), plan_id)
            except Exception as e:
                logger.error(f"Error in country_setting_by_tenant_id for tenant {tenant_id}: {e}")
        return None

    @staticmethod
    def saveCampaignTransaction(tranCampaignId, tranCampaignName, tranTotalMember, tranType,
                                tranInvoicedId, tranInvoicedStatus, tranInvoicedDate, memberId,
                                tranBillType, tranTotalAmount, tranMemberRate, tranCountTotalSms,
                                tranPollFormNo, tranPollToNo, subMemberId):
        """Save a new campaign transaction matching Java implementation exactly"""
        try:
            ct = CampaignTransaction()
            ct.tran_campaign_id = tranCampaignId
            ct.tran_campaign_name = tranCampaignName
            ct.tran_campaign_date = timezone.now()
            ct.tran_total_member = tranTotalMember
            ct.tran_type = tranType
            ct.tran_invoiced_id = tranInvoicedId
            ct.tran_invoiced_status = tranInvoicedStatus
            ct.tran_invoiced_date = tranInvoicedDate
            ct.ct_client_id = memberId
            ct.tran_bill_type = tranBillType
            ct.tran_total_amount = tranTotalAmount
            ct.tran_member_rate = tranMemberRate
            ct.tran_count_total_sms = tranCountTotalSms
            ct.tran_poll_form_no = tranPollFormNo
            ct.tran_poll_to_no = tranPollToNo
            ct.save()
        except Exception as e:
            logger.error(f"SaveCampaignTransaction Error: {e}")

    # ========== NEW SERVICE METHODS ==========

    @staticmethod
    def generate_otp():
        """
        Generate a 6-digit One-Time Password
        Mirrors Java's: CommonServices.generateOneTimePassword()
        """
        return ''.join(random.choices('0123456789', k=6))

    @staticmethod
    def get_country_id(country_name):
        """
        Get country ID by country name
        Mirrors Java's: CommonServices.getCountryId(String countryName)
        """
        try:
            country = Country.objects.get(cnt_name=country_name)
            return country.country_id
        except Country.DoesNotExist:
            return 0
        except Exception as e:
            logger.error(f"Error in get_country_id: {e}")
            return 0

    @staticmethod
    def get_country_name(country_id):
        """
        Get country name by country ID
        Mirrors Java's: CommonServices.getCountryName(Long countryId)
        """
        try:
            country = Country.objects.get(country_id=country_id)
            return country.cnt_name
        except Country.DoesNotExist:
            return ""
        except Exception as e:
            logger.error(f"Error in get_country_name: {e}")
            return ""

    @staticmethod
    def validate_phone_format(country_id, phone_number):
        """
        Validate phone number format for given country
        Mirrors Java's: CommonServices.validatePhoneFormat(Long countryId, String phoneNumber)
        """
        try:
            country = Country.objects.get(country_id=country_id)
            # Remove all non-digit characters
            cleaned_phone = ''.join(filter(str.isdigit, str(phone_number)))

            # Check length constraints
            if (len(cleaned_phone) == country.phone_min_length or
                len(cleaned_phone) == country.phone_max_length):
                return True
            return False
        except Country.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Phone format validation error: {e}")
            return False

    @staticmethod
    def find_group_first_records(tenant_id, group_id):
        """
        Get first contact record from a group
        Mirrors Java's: CommonServices.findGroupFirstRecords(Long memberId, Long groupId)
        """
        
        try:
            contact = (
                Userlist.objects
                .annotate(phoneNumber_len=Length('phoneNumber'))
                .filter(
                    groupId=group_id,
                    memberId=get_client_id_by_tenant_id(tenant_id)
                )
                .filter(
                    Q(badEmail__in=['N', 'B', 'D']) |
                    (
                            Q(badPhoneNumber='N') &
                            Q(phoneNumber_len__gt=0)
                    )
                )
                .filter(
                    Q(status='Subscribed') |
                    (
                            Q(status='Unsubscribed') &
                            (
                                    Q(smsStatus='Subscribed') |
                                    Q(smsStatus__isnull=True)
                            )
                    )
                )
                .filter(
                    Q(optId__isnull=True) |
                    Q(optId=0)
                )
                .filter(
                    Q(email__isnull=False) |
                    Q(phoneNumber__isnull=False)
                )
                .order_by('firstName')
                .first()
            )

            tenant = Tenants.objects.get(ten_id=tenant_id)
            if contact:
                return {
                    'First_Name': contact.firstName or '',
                    'Last_Name': contact.lastName or '',
                    'Email': contact.email or '',
                    'Contact_No': contact.phoneNumber or '',
                    'Your_First_Name': tenant.ten_first_name or '',
                    'Your_Last_Name': tenant.ten_last_name or '',
                    'Client_First_Name': contact.firstName or '',
                    'Client_Last_Name': contact.lastName or '',
                    'Street_Address1': contact.streetAddress1 or '',
                    'Street_Address2': contact.streetAddress2 or '',
                    'City': contact.city or '',
                    'State': contact.stateProvRegion or '',
                    'Country': contact.country or ''
                }
            logger.info(f"No contacts found for member {tenant_id} in group {group_id}")
            return {}
        except Exception as e:
            logger.error(f"Error finding group first records: {e}")
            return {}

    @staticmethod
    def find_tenant_record(tenant_id):
        """
        Get member record with all details
        Mirrors Java's: CommonServices.findMemberRecord(Long memberId)
        """
        try:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": tenant_id
                    }
                }
            )
            if tenant is None:
                return None
            return {
                'tenantId': tenant.ten_id,
                'tenEmail': tenant.ten_email,
                'tenCountry': tenant.ten_country,
                'tdPlanId': tenant.td_plan_id,
                'tenFirstName': getattr(tenant, 'ten_first_name', ''),
                'tenLastName': getattr(tenant, 'ten_last_name', '')
            }
        except Exception as e:
            logger.error(f"Error finding member record: {e}")
            return None

    @staticmethod
    def check_authorized(tenant_id):
        """
        Check if member has payment authorization IDs set up in database.
        """
        try:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": tenant_id
                    }
                }
            )
            if tenant is None:
                return False
            has_auth_profile = (
                hasattr(tenant, 'td_authorize_customer_profile_id') and
                getattr(tenant, 'td_authorize_customer_profile_id') and
                hasattr(tenant, 'td_authorize_customer_payment_profile_id') and
                getattr(tenant, 'td_authorize_customer_payment_profile_id')
            )
            return has_auth_profile
        except Exception:
            return False

    @staticmethod
    def check_payment_profile_exists(tenant_id):
        """
        Verify with Authorize.net if the customer profile actually exists.
        Mirrors Java's: paymentGatewayService.checkPaymentProfileExists
        """
        try:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": tenant_id
                    }
                }
            )
            if not tenant.td_authorize_customer_profile_id or not tenant.td_authorize_customer_payment_profile_id:
                return "noprofile"

            # Decrypt IDs (structural parity with Java)
            auth_customer_profile_id = tenant.td_authorize_customer_profile_id

            # Setup merchant authentication
            merchantAuth = apicontractsv1.merchantAuthenticationType()
            if settings.ENVSYS == 'prodapi':
                merchantAuth.name = settings.AUTHORIZENET_PRODUCTION_LOGIN_ID
                merchantAuth.transactionKey = settings.AUTHORIZENET_PRODUCTION_TRANSACTION_KEY
            else:
                merchantAuth.name = settings.AUTHORIZENET_LOGIN_ID
                merchantAuth.transactionKey = settings.AUTHORIZENET_TRANSACTION_KEY

            # Setup request
            getRequest = apicontractsv1.getCustomerProfileRequest()
            getRequest.merchantAuthentication = merchantAuth
            getRequest.customerProfileId = auth_customer_profile_id

            # Execute
            controller = getCustomerProfileController(getRequest)
            if settings.ENVSYS == 'prodapi':
                controller.setenvironment(constants.PRODUCTION)
            else:
                controller.setenvironment(constants.SANDBOX)
            
            controller.execute()
            response = controller.getresponse()

            if response is not None and response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                return "ok"
            else:
                return response.messages.message[0].text if response and response.messages.message else "Error verifying profile"

        except Exception as e:
            logger.error(f"Error checking payment profile existence: {e}")
            return "Error verifying profile"

    @staticmethod
    def total_contact_uploaded(member_id):
        """
        Count total contacts uploaded by member (active/subscribed)
        Mirrors Java's: CommonServices.totalContactUploaded(Long memberId)
        """
        
        try:
            return Userlist.objects.filter(
                Q(memberId=get_client_id_by_tenant_id(member_id)),
                Q(status='Subscribed'),
                Q(badEmail__in=['N', 'B', 'D']),
                Q(optId=0) | Q(optId__isnull=True)
            ).count()
        except Exception as e:
            logger.error(f"Error in total_contact_uploaded: {e}")
            return 0

    @staticmethod
    def unsubscribe(unsubscribe_dto):
        """
        Process unsubscribe request
        Mirrors Java's: CommonServices.unsubscribe(UnsubscribeDto unsubscribeDto)
        """
        res_body = {
            "error": "",
            "msg": ""
        }
        try:
            ui_encoded = unsubscribe_dto.get('ui', '')
            ci_encoded = unsubscribe_dto.get('ci', '')
            m_encoded = unsubscribe_dto.get('m', '')

            def decode_param(val):
                if not val:
                    raise ValueError("Empty param")
                val += '=' * (-len(val) % 4)
                return base64.urlsafe_b64decode(val.encode('utf-8')).decode('utf-8')

            ui = int(decode_param(ui_encoded))
            ci = int(decode_param(ci_encoded))
            m = int(decode_param(m_encoded))

            userlist = Userlist.objects.get(memberId=get_client_id_by_tenant_id(m), emailId=ui)
            first_name = userlist.firstName or ""
            last_name = userlist.lastName or ""
            email = ""
            if userlist.email:
                email = userlist.email

            if userlist.status == "Unsubscribed":
                res_body["msg"] = "You Have Already Unsubscribed"
            else:
                campaigns_email_send = None
                try:
                    campaigns_email_send = CampaignsEmailSend.objects.get(id=ci)
                    userlist.status = "Unsubscribed"
                    userlist.optId = campaigns_email_send.camp_id
                    userlist.optDate = timezone.now()
                    userlist.save()
                except Exception:
                    pass

                # Add UnsubscribeLogs
                try:
                    unsubscribe_log = UnsubscribeLogs()
                    unsubscribe_log.member_id = get_client_id_by_tenant_id(m)
                    unsubscribe_log.email = email
                    if campaigns_email_send is None:
                        unsubscribe_log.campaign_id = 0
                    else:
                        unsubscribe_log.campaign_id = int(campaigns_email_send.camp_id)
                    unsubscribe_log.created_date = timezone.now()
                    unsubscribe_log.save()
                except Exception:
                    pass

                CampaignsSendEmail.objects.filter(emailId=ui, campSendId=ci).update(isUnsubscribed='Y')

                res_body["msg"] = "Unsubscribed Successfully"

                tenant = get_tenants(
                    where_conditions={
                        "tenant": {
                            "ten_id": m
                        }
                    }
                )
                ten_first_name = ""
                ten_last_name = ""
                ten_email = ""

                if tenant.first_name:
                    ten_first_name = DecryptString.set_enc_dec_user(tenant.first_name, "display", "Y")
                if tenant.last_name:
                    ten_last_name = DecryptString.set_enc_dec_user(tenant.last_name, "display", "Y")
                if tenant.email:
                    ten_email = DecryptString.set_enc_dec_user(tenant.email, "display", "Y")

                count = 1
                optout_reason = ""
                if unsubscribe_dto.get('manyEmail') == 1:
                    optout_reason += f"<div>{count}. Too many emails</div>"
                    count += 1
                if unsubscribe_dto.get('notRel') == 1:
                    optout_reason += f"<div>{count}. Not relevant to what I want</div>"
                    count += 1
                if unsubscribe_dto.get('perEmail') == 1:
                    optout_reason += f"<div>{count}. I never registered with this company or gave them permission to use my email address</div>"
                    count += 1
                if unsubscribe_dto.get('longerEmail') == 1:
                    optout_reason += f"<div>{count}. I just no longer want to receive emails from this company</div>"
                    count += 1
                if unsubscribe_dto.get('other') == 1:
                    optout_reason += f"<div>{count}. {unsubscribe_dto.get('otherMsg', '')}</div>"
                    count += 1

                if userlist.email and unsubscribe_dto.get('outType') == "removeThisList":
                    Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant.ten_id), groupId=userlist.groupId, email=userlist.email).update(
                        status="Unsubscribed",
                        optOutDate=timezone.now()
                    )
                    CommonServices.checkDuplicateRecords(userlist.groupId, tenant.ten_id)
                    CommonServices.checkTotalMember(userlist.groupId, tenant.ten_id)

                if userlist.email and unsubscribe_dto.get('outType') == "removeAllList":
                    Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant.ten_id), email=userlist.email).update(
                        status="Unsubscribed",
                        optOutDate=timezone.now()
                    )
                    group_ids = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant.ten_id), email=userlist.email).values_list('groupId', flat=True).distinct()
                    for gid in group_ids:
                        CommonServices.checkDuplicateRecords(gid, tenant.ten_id)
                        CommonServices.checkTotalMember(gid, tenant.ten_id)

                model = {
                    "memFirstName": ten_first_name,
                    "memLastName": ten_last_name,
                    "firstName": first_name,
                    "lastName": last_name,
                    "email": email,
                    "optoutReason": optout_reason,
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
                    "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', '')
                }

                mail_request_dto = MailRequestDTO(
                    to=ten_email,
                    subject="Tenant Opted Out of Your Contact List",
                    template_name="opted-out-template.html"
                )
                try:
                    CommonServices.sendEmail(mail_request_dto, model)
                except Exception:
                    pass

                to_email_admin_1 = getattr(settings, 'TO_EMAIL_ADMIN_MEMBER_1', None)
                if to_email_admin_1:
                    mail_request_dto.to = to_email_admin_1
                    try:
                        CommonServices.sendEmail(mail_request_dto, model)
                    except Exception:
                        pass

                try:
                    CommonServices.send_optout_details_email(userlist)
                except Exception:
                    pass

        except Exception as exp:
            logger.error(f"Unsubscribe Error : {exp}")
            res_body["error"] = "error"
        return res_body

    @staticmethod
    def sms_reply_url(request_data):
        """
        
        Handle SMS reply webhook from Telnyx
        Mirrors Java's: CommonServices.smsReplyUrl(HttpServletRequest request)
        Lines: 802-1020

        Processes incoming SMS replies and routes them to appropriate handlers
        based on source (campaign SMS, conversations, or SMS polling).
        """

        try:
            # Handle both dict and JSON object inputs
            if isinstance(request_data, str):
                response = json.loads(request_data)
            else:
                response = request_data

            if not response:
                logger.warning("Empty SMS reply data received")
                return

            # Parse Telnyx webhook payload
            try:
                data = response.get('data', {})
                json_object = data.get('payload', {})

                user_reply = json_object.get('text', '').strip()
                mes_id = json_object.get('id', '')
                messaging_profile_id = json_object.get('messaging_profile_id', '')

                from_obj = json_object.get('from', {})
                to_no = from_obj.get('phone_number', '')

                to_array = json_object.get('to', [])
                if to_array:
                    to_obj = to_array[0]
                    from_no = to_obj.get('phone_number', '')
                else:
                    from_no = ''

            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"SmsReplyUrl Error parsing payload: {e}")
                return

            # Step 1: Determine member and flag (source type)
            ten_id = 0
            flag_check = 0  # 0=polling, 1=campaign SMS, 2=conversations

            try:
                client = Clients.objects.filter(cliSmsAccountSid=messaging_profile_id).first()
                if client is None:
                    logger.error(f"SmsReplyUrl Error 1: Tenant not found with sub_account_sid={messaging_profile_id}")
                ten_id = getattr(client,"cliTenantId", 0)

                # Check if this is a campaign SMS or conversations number
                phone_number = get_phone_numbers_first(ten_id, "CAMPAIGN")
                chat_phone_number = get_phone_numbers_first(ten_id, "CHAT")
                if getattr(phone_number,"phPhoneNumber") and getattr(phone_number,"phPhoneNumber") == from_no:
                    flag_check = 1
                elif getattr(chat_phone_number,"phPhoneNumber") and getattr(chat_phone_number,"phPhoneNumber") == from_no:
                    flag_check = 2

            except Exception as e:
                logger.error(f"SmsReplyUrl Error 1: {e}")

            # Step 2: If not found in member, check campaign SMS numbers
            if flag_check == 0:
                try:
                    pn = PhoneNumbers.objects.filter(
                        phClientId=get_client_id_by_tenant_id(ten_id),
                        phPhoneNumber=from_no
                    ).values_list('pnId', flat=True).first()

                    if pn:
                        flag_check = 1
                except Exception as e:
                    logger.error(f"SmsReplyUrl Error 2: {e}")
                    flag_check = 0

            # Step 3: Check automation rules
            auto_sms_yes = False
            if user_reply:
                try:
                    auto_sms_yes = CommonServices.sms_automation_reply(to_no, from_no, user_reply)
                except Exception as e:
                    logger.error(f"AutomationSms SmsReplyUrl Error 1: {e}")

            # Step 4: Process reply if not handled by automation
            if not auto_sms_yes and user_reply:
                # Handle unsubscribe/stop keywords
                try:
                    if user_reply.lower().strip() in ['unsubscribe', 'stop']:
                        temp_to_no = '+' + (to_no.replace('+', '').replace('-', '').replace(' ', ''))
                        temp_from_no = '+' + (from_no.replace('+', '').replace('-', '').replace(' ', ''))

                        try:
                            contact_log = ContactSendSmsLogs.objects.filter(
                                toPhoneNumber=temp_to_no,
                                fromPhoneNumber=temp_from_no
                            ).first()

                            if contact_log:
                                contact = Userlist.objects.get(
                                    memberId=contact_log.member_id,
                                    emailId=contact_log.email_id
                                )
                                # Update contact as unsubscribed
                                Userlist.objects.filter(
                                    memberId=contact.memberId,
                                    phoneNumber__endswith=contact.phoneNumber[-10:] if contact.phoneNumber else ''
                                ).update(smsStatus='Unsubscribed', optOutDate=timezone.now())
                        except (Userlist.DoesNotExist, ContactSendSmsLogs.DoesNotExist):
                            pass
                except Exception as e:
                    logger.error(f"Unsubscribe handling error: {e}")

                # Process based on source type
                reply_msg = "Type Start to or Stop to Opt-Out. Contact support@salesandmarketing.ai if you have any more questions"

                if to_no and from_no:
                    if flag_check == 1:
                        # Campaign SMS reply
                        if user_reply.lower().strip() == 'help':
                            CommonServices._handle_campaign_help_reply(
                                to_no, from_no, reply_msg, ten_id
                            )
                        else:
                            CommonServices.sms_campaign_reply(to_no, from_no, user_reply)

                    elif flag_check == 2:
                        # Conversations reply
                        if user_reply.lower().strip() == 'help':
                            CommonServices._handle_conversations_help_reply(
                                to_no, from_no, reply_msg, mes_id, ten_id
                            )
                        else:
                            CommonServices.conversations_reply(to_no, from_no, user_reply, mes_id)

                    else:
                        # SMS Polling reply
                        if user_reply.lower().strip() == 'help':
                            CommonServices._handle_polling_help_reply(
                                to_no, from_no, reply_msg
                            )
                        else:
                            CommonServices.sms_polling_reply(to_no, from_no, user_reply, '', '', '', '')

        except Exception as e:
            logger.error(f"SmsReplyUrl Error: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")

    @staticmethod
    def _handle_campaign_help_reply(to_no, from_no, reply_msg, mem_id):
        """Handle help request for campaign SMS"""
        try:
            campaign_sms = CampaignSendSms.objects.filter(
                toContact=to_no,
                fromContact=from_no
            ).first()

            if not campaign_sms:
                return

            sms_id = campaign_sms.smsId
            member_id = campaign_sms.memberId
            email_id = campaign_sms.emailId
            sid = campaign_sms.sid

            pn_id = CampaignsSms.objects.filter(smsId=sms_id).values_list('pnId', flat=True).first()
            pn = PhoneNumbers.objects.filter(
                phClientId=member_id,
                pnId=pn_id
            ).values_list('phPhoneNumber', flat=True).first()

            phone_number = pn or from_no

            # Send help response via Telnyx
            try:
                msg_result = telnyx_utils.send_sms_telnyx(
                    to_no, phone_number, 'text', reply_msg, 1, None,
                    getattr(settings, 'SMS_STATUS_REPLY_URL', ''),
                    getattr(settings, 'TELNYX_BASE_URL', None),
                    getattr(settings, 'TELNYX_API_KEY', None)
                )

                msg_sid = msg_result.get('msgId', '')
                msg_status = msg_result.get('msgStatus', '')
                msg_error = msg_result.get('msgError', '')
                msg_error_code = msg_result.get('msgErrorCode', '')
            except Exception as e:
                logger.error(f"Error sending help SMS: {e}")
                msg_sid = ''
                msg_status = ''
                msg_error = str(e)
                msg_error_code = ''

            # Save reply record
            campaign_sms_reply = CampaignSmsReply(
                crEmailId=email_id,
                crSid=sid,
                crMemberId=member_id,
                crReply=reply_msg,
                crReplyNo=to_no,
                crSmsId=sms_id,
                crSmsSid=msg_sid,
                crSmsStatus=msg_status,
                crSmsErrorMessage=msg_error,
                crSmsErrorCode=msg_error_code,
                crSmsFromNo=phone_number,
                crSmsToNo=to_no,
                crDate=timezone.now()
            )
            campaign_sms_reply.save()

            # Update transaction for billing
            try:
                transaction = CampaignTransaction.objects.get(
                    tranMemberId=member_id,
                    tranCampaignId=sms_id
                )
                transaction.tran_total_amount = transaction.tran_total_amount + transaction.tran_member_rate
                transaction.tran_count_total_sms = transaction.tran_count_total_sms + 1
                transaction.save()
            except CampaignTransaction.DoesNotExist:
                pass

        except Exception as e:
            logger.error(f"Campaign help reply error: {e}")

    @staticmethod
    def _handle_conversations_help_reply(to_no, from_no, reply_msg, mes_id, mem_id):
        """Handle help request for conversations"""
        try:
            # Clean phone numbers
            client_number = '+' + (to_no.replace('+', '').replace('-', '').replace(' ', ''))
            twilio_number = '+' + (from_no.replace('+', '').replace('-', '').replace(' ', ''))

            conversation_qs = SmsConversations.objects.filter(
                cvsId=OuterRef('cvsdCvsId'),
                cvsTwilioNumber=twilio_number
            )

            conversation = (
                SmsConversationsDetails.objects
                .filter(cvsdClientNumber=client_number)
                .annotate(
                    cvsdId=Subquery(conversation_qs.values('cvsId')[:1]),
                    cvsdClientNumber=Subquery(conversation_qs.values('cvsMemberNumber')[:1]),
                    cvsdClientId=Subquery(conversation_qs.values('cvsMemberId')[:1])
                )
                .exclude(cvsdId__isnull=True)
                .order_by('-cvsdId')
                .values(
                    'cvsdId',
                    'cvsdClientNumber',
                    'cvsdClientId'
                )[:1]
            )

            if not conversation:
                return

            conversation = conversation[0]
            cvs_id = conversation['cvsdId']
            cvs_tenant_id = conversation['cvsdClientId']
            cvsd_client_id = conversation['cvsdClientId']


            # Get member for Telnyx number
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": get_tenant_id_by_client_id(cvs_tenant_id)
                    }
                }
            )
            chat_phone_number = get_phone_numbers_first(tenant.ten_id, "CHAT")

            # Send help response via Telnyx
            try:
                telnyx_utils.send_sms_telnyx(
                    client_number, chat_phone_number.phPhoneNumber, 'text', reply_msg, 1, None,
                    getattr(settings, 'CONVERSATIONS_STATUS_URL', ''),
                    getattr(settings, 'TELNYX_BASE_URL', None),
                    getattr(settings, 'TELNYX_API_KEY', None)
                )
            except Exception as e:
                logger.error(f"Error sending conversation help SMS: {e}")

            # Save reply in conversation details
            try:
                conversation_detail = SmsConversationsDetails(
                    cvsdCvsId=cvs_id,
                    cvsdMessage=reply_msg,
                    cvsdClientId=cvsd_client_id,
                    cvsdClientNumber=client_number,
                    cvsdSid=mes_id,
                    cvsdSender='c',
                    cvsdDate=timezone.now()
                )
                conversation_detail.save()
            except Exception as e:
                logger.error(f"Error saving conversation detail: {e}")

            # Update transaction for billing
            try:
                transaction = CampaignTransaction.objects.get(
                    tranMemberId=cvs_tenant_id,
                    tranCampaignId=cvs_id
                )
                transaction.tran_total_amount = transaction.tran_total_amount + transaction.tran_member_rate
                transaction.tran_count_total_sms = transaction.tran_count_total_sms + 1
                transaction.save()
            except CampaignTransaction.DoesNotExist:
                pass

        except Exception as e:
            logger.error(f"Conversations help reply error: {e}")

    @staticmethod
    def _handle_polling_help_reply(to_no, from_no, reply_msg):
        """Handle help request for SMS polling"""
        try:
            to_no_formatted = '+' + (to_no.replace('+', '').replace('-', '').replace(' ', ''))
            from_no_formatted = '+' + (from_no.replace('+', '').replace('-', '').replace(' ', ''))

            sp_reply = SpReply.objects.filter(
                toNo=to_no_formatted,
                fromNo=from_no_formatted
            ).first()

            if sp_reply:
                # Send help SMS via Telnyx
                try:
                    telnyx_utils.send_sms_telnyx(
                        to_no_formatted, from_no_formatted, 'text', reply_msg, 1, None,
                        getattr(settings, 'SMS_POLLING_STATUS_URL', ''),
                        getattr(settings, 'TELNYX_BASE_URL', None),
                        getattr(settings, 'TELNYX_API_KEY', None)
                    )
                except Exception as e:
                    logger.error(f"Error sending polling help SMS: {e}")

        except Exception as e:
            logger.error(f"Polling help reply error: {e}")

    @staticmethod
    def update_campaign_transaction(campaign_transaction):
        """
        Update existing campaign transaction
        Mirrors Java's: CommonServices.updateCampaignTransaction(CampaignTransaction campaignTransaction)
        """
        try:
            tran_id = campaign_transaction.get('tran_id') if isinstance(campaign_transaction, dict) else campaign_transaction.tran_campaign_id

            ct = CampaignTransaction.objects.get(tran_campaign_id=tran_id)

            # Update fields from campaign_transaction
            if isinstance(campaign_transaction, dict):
                for field, value in campaign_transaction.items():
                    if hasattr(ct, field):
                        setattr(ct, field, value)
            else:
                for field in dir(campaign_transaction):
                    if not field.startswith('_') and hasattr(ct, field):
                        setattr(ct, field, getattr(campaign_transaction, field))

            ct.save()
        except CampaignTransaction.DoesNotExist:
            logger.error(f"Transaction not found")
        except Exception as e:
            logger.error(f"Error updating campaign transaction: {e}")

    @staticmethod
    def zero_bounce_return_url(request_data):
        """
        Handle ZeroBounce email validation webhook
        Mirrors Java's: CommonServices.zeroBounceReturnUrl(HttpServletRequest request)
        """
        # , EmailVerification
        try:
            # Extract ZeroBounce response data
            file_id = request_data.get('file_id')
            emailVerification = EmailVerification.objects.get(evFileId=file_id)
            if emailVerification is not None:
                emailVerification.evFileStatus = "Complete"
                emailVerification.save()
            return {'status': True, 'message': 'ZeroBounce validation processed successfully'}

        except Exception as e:
            logger.error(f"Error processing ZeroBounce response: {e}")
            return {'status': False, 'message': str(e)}

    @staticmethod
    def email_verification_rate(pending_email_count, member_id):
        """
        Calculate email verification rate for member
        Mirrors Java's: CommonServices.emailVerificationRate(int pendingEmailCount, Long memberId)
        """
        

        try:
            total_emails = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id)).count()
            if total_emails == 0:
                return 0.0
            verification_rate = (total_emails - pending_email_count) / total_emails
            return round(verification_rate, 2)
        except Exception as e:
            logger.error(f"Error calculating email verification rate: {e}")
            return 0.0

    @staticmethod
    def send_optout_details_email(userlist):
        try:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": userlist.memberId
                    }
                }
            )
            client = Clients.objects.get(cliId=userlist.memberId)
            tenant_name = ""
            if tenant.ten_first_name:
                tenant_name = tenant.ten_first_name

            if tenant.ten_last_name:
                tenant_name += " " + tenant.ten_last_name

            cli_business_name = ""
            if client.cliBusinessName:
                cli_business_name = client.cliBusinessName

            country_setting = CommonServices.country_setting_by_tenant_id(userlist.memberId)
            
            firstName = userlist.firstName or ""
            lastName = userlist.lastName or ""
            email = ""
            if userlist.email:
                email = userlist.email
            
            udf1 = userlist.udf1 or ""
            udf2 = userlist.udf2 or ""
            udf3 = userlist.udf3 or ""
            udf4 = userlist.udf4 or ""
            udf5 = userlist.udf5 or ""
            udf6 = userlist.udf6 or ""
            udf7 = userlist.udf7 or ""
            udf8 = userlist.udf8 or ""
            udf9 = userlist.udf9 or ""
            udf10 = userlist.udf10 or ""

            udf_array = list(Udf.objects.filter(groupId=userlist.groupId).values_list('udf', flat=True))

            my_page = MyPages.objects.filter(mpClientId=userlist.memberId, mpName='Opt Out').first()
            camp_detail_temp = my_page.mpDetails if my_page else ""

            if camp_detail_temp:
                camp_detail_temp = camp_detail_temp.replace('\u200c', '').replace('\u200b', '')
                camp_detail_temp = camp_detail_temp.replace('\xe2\x80\x8c', '').replace('\xe2\x80\x8b', '')
                camp_detail_temp = camp_detail_temp.replace("447px", "5px")
                camp_detail_temp = camp_detail_temp.replace('height="100%"', "")
                camp_detail_temp = re.sub(r"<style.*?>.*?</style>", "", camp_detail_temp, flags=re.DOTALL | re.IGNORECASE)
                camp_detail_temp = re.sub(r"<!--RT3S-->.*?<!--RT3E-->", "", camp_detail_temp, flags=re.DOTALL | re.IGNORECASE)

                if cli_business_name:
                    camp_detail_temp = re.sub(r"(?i)##business_name##", cli_business_name.strip(), camp_detail_temp)
                else:
                    camp_detail_temp = re.sub(r"(?i)##business_name##", tenant_name.strip(), camp_detail_temp)

                if firstName:
                    camp_detail_temp = re.sub(r"(?i)##first_name##", firstName.strip(), camp_detail_temp)
                if lastName:
                    camp_detail_temp = re.sub(r"(?i)##last_name##", lastName.strip(), camp_detail_temp)
                if email:
                    camp_detail_temp = re.sub(r"(?i)##email##", email.strip(), camp_detail_temp)

                client_phone_number = ""
                if userlist.phoneNumber:
                    client_phone_number = userlist.phoneNumber
                elif userlist.phone:
                    client_phone_number = userlist.phone

                if client_phone_number:
                    clean_phone = client_phone_number.replace(" ", "").strip()
                    camp_detail_temp = re.sub(r"(?i)##contact_no##", clean_phone, camp_detail_temp)

                udfs = [udf1, udf2, udf3, udf4, udf5, udf6, udf7, udf8, udf9, udf10]
                for i, udf_name in enumerate(udf_array):
                    search_val = f"##{udf_name}##"
                    replace_val = ""
                    if i < len(udfs):
                        val = udfs[i]
                        if val and val != "":
                            replace_val = val.strip()
                    camp_detail_temp = camp_detail_temp.replace(search_val, replace_val)

                soup = BeautifulSoup(camp_detail_temp, "html.parser")
                for div in soup.select("div.removeClass"):
                    div.decompose()
                camp_detail_temp = str(soup)
                camp_detail_temp = cron_send_campaign_content_remove(camp_detail_temp)

                camp_detail_temp = camp_detail_temp.replace("</body></html>", "")
                camp_detail_temp += "<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:\'Myriad Pro\',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
                camp_detail_temp += "<div style='padding-top:2px'>"

                site_url = getattr(settings, 'SITE_URL', '')
                site_url_www = getattr(settings, 'SITE_URL_WWW', '')
                site_url_address = getattr(settings, 'SITE_URL_ADDRESS', '')

                cnty_white_listing = getattr(country_setting, 'cnty_white_listing', '') or ''
                cli_logo = client.cliLogo
                cli_customer_footer = client.cliCustomerFooter

                if cnty_white_listing.lower() == 'y' and cli_logo:
                    camp_detail_temp += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
                else:
                    camp_detail_temp += f'<a style="color:#00599A;margin: 0px auto;" href="{site_url_www}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{site_url}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'

                camp_detail_temp += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"

                if cnty_white_listing.lower() == 'y' and cli_customer_footer:
                    if cli_customer_footer:
                        camp_detail_temp += nl2br(cli_customer_footer)
                    else:
                        camp_detail_temp += site_url_address
                else:
                    camp_detail_temp += site_url_address

                link_v = DecryptString.set_enc_dec_user(str(userlist.memberId), "", "Y")
                link_w = DecryptString.set_enc_dec_user(str(userlist.groupId), "", "Y")
                link_y = DecryptString.set_enc_dec_user(str(userlist.emailId), "", "Y")
                link = f"{site_url}subscribelink?v={link_v}&w={link_w}&y={link_y}"

                raw_str = f"{userlist.groupId}~{userlist.memberId}~0~{userlist.emailId}"
                enc_str = DecryptString.set_enc_dec_user(raw_str, "", "Y")
                update_contact_link = f"{site_url}inviteurl?q={enc_str}"

                camp_detail_temp += "</div></div>"
                camp_detail_temp += f"</div></div><div align='center' style='color:#4285F4;font-size:12px;'><a href='{link}' style='color:#4285F4'>Subscribe</a> | <a href='{update_contact_link}' style='color:#4285F4'>Update Contact Information</a></div></body></html>"

                name_list = cli_business_name if cli_business_name else tenant_name
                subject = f"Opt-Out From {name_list} Contact List"

                mail_request = MailRequestDTO(
                    to=email.lower(),
                    subject=subject,
                    template_name="optout-template.html"
                )

                model = {
                    "SITEURL": site_url,
                    "msgBody": strip_slashes(camp_detail_temp),
                    "siteName": getattr(settings, 'SITE_NAME', ''),
                    "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', ''),
                    "siteUrlWWW": site_url_www,
                    "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', ''),
                    "companyName": getattr(settings, 'COMPANY_NAME', ''),
                    "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', ''),
                    "siteUrlAddress": site_url_address,
                    "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', ''),
                    "companyNumber": getattr(settings, 'COMPANY_NUMBER', ''),
                    "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', ''),
                    "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', '')
                }

                CommonServices.sendEmail(mail_request, model)

        except Exception as e:
            logger.error(f"Error sending opt-out email: {e}")

    @staticmethod
    def total_contact_count(group_id, member_id):
        """
        Count total active contacts in a group
        Mirrors Java's: CommonServices.totalContactCount(Long groupId, Long memberId)
        """
        try:
            return Userlist.objects.filter(
                Q(groupId=group_id),
                Q(memberId=get_client_id_by_tenant_id(member_id)),
                Q(status='Subscribed'),
                Q(badEmail__in=['N', 'B', 'D']),
                Q(optId=0) | Q(optId__isnull=True)
            ).count()
        except Exception as e:
            logger.error(f"Error in total_contact_count: {e}")
            return 0

    @staticmethod
    def total_duplicate_count(group_id, member_id):
        """
        Get duplicate records flag from Group table
        Mirrors Java's: CommonServices.totalDuplicateCount(Long groupId, Long memberId)
        """
        try:
            group = Groups.objects.get(grpId=group_id, grpClientId=get_client_id_by_tenant_id(member_id))
            return group.grpDuplicateRecordsYn
        except Exception as e:
            logger.error(f"Error in total_duplicate_count: {e}")
            return 'N'

    @staticmethod
    def total_sms_count(group_id, member_id):
        """
        Count total active SMS contacts in a group
        Mirrors Java's: CommonServices.totalSmsCount(Long groupId, Long memberId)
        """
        try:
            return Userlist.objects.filter(
                Q(groupId=group_id),
                Q(memberId=get_client_id_by_tenant_id(member_id)),
                Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True),
                Q(badPhoneNumber='N'),
                Q(optId=0) | Q(optId__isnull=True)
            ).count()
        except Exception as e:
            logger.error(f"Error in total_sms_count: {e}")
            return 0

    @staticmethod
    def check_duplicate_records(group_id, member_id):
        """
        Check and flag duplicate contacts in a group
        Mirrors Java's: CommonServices.checkDuplicateRecords(Long groupId, Long memberId)
        """
        

        try:
            contacts = Userlist.objects.filter(groupId=group_id, memberId=get_client_id_by_tenant_id(member_id))
            email_counts = {}

            for contact in contacts:
                if contact.email:
                    email_counts[contact.email] = email_counts.get(contact.email, 0) + 1

            duplicate_count = sum(1 for count in email_counts.values() if count > 1)
            return duplicate_count
        except Exception as e:
            logger.error(f"Error checking duplicates: {e}")
            return 0

    @staticmethod
    def check_type_email(group_id, member_id):
        """
        Validate email types in group
        Mirrors Java's: CommonServices.checkTypeEmail(Long groupId, Long memberId)
        """
        

        try:
            contacts = Userlist.objects.filter(groupId=group_id, memberId=get_client_id_by_tenant_id(member_id))
            invalid_count = 0

            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

            for contact in contacts:
                if contact.email and not re.match(email_pattern, contact.email):
                    invalid_count += 1

            return invalid_count
        except Exception as e:
            logger.error(f"Error validating email types: {e}")
            return 0

    @staticmethod
    def check_total_member(group_id, member_id):
        """
        Verify total member count in group matches plan limits
        Mirrors Java's: CommonServices.checkTotalMember(Long groupId, Long memberId)
        """
        

        try:
            contact_count = Userlist.objects.filter(
                groupId=group_id,
                memberId=get_client_id_by_tenant_id(member_id)
            ).count()

            country_setting = CommonServices.country_setting_by_tenant_id(member_id)
            if country_setting:
                max_contacts = getattr(country_setting, 'cnty_contacts_included', 0)
                return contact_count <= max_contacts
            return True
        except Exception as e:
            logger.error(f"Error checking total members: {e}")
            return True

    @staticmethod
    def save_number_call_forwarding(cfn_id, twilio_number, country_code, forwarding_number, member_id, twilio_phone_sid):
        """
        Save call forwarding number configuration
        Mirrors Java's: CommonServices.saveNumberCallForwarding(...)
        """
        try:
            if cfn_id:
                call_forward = NumberCallForwarding.objects.get(cfnId=cfn_id)
            else:
                call_forward = NumberCallForwarding()

            call_forward.cfnTwilioNumber = twilio_number
            call_forward.cfnForwardingCountryCode = country_code
            call_forward.cfnForwardingNumber = forwarding_number
            call_forward.cfnMemberId = get_client_id_by_tenant_id(member_id)
            call_forward.cfnTwilioPhoneSid = twilio_phone_sid
            call_forward.cfnDateTime = timezone.now()

            call_forward.save()
            return call_forward.cfnId
        except Exception as e:
            logger.error(f"Error saving call forwarding: {e}")
            return 0

    @staticmethod
    def delete_number_call_forwarding(twilio_phone_sid, member_id):
        """
        Delete call forwarding number
        Mirrors Java's: CommonServices.deleteNumberCallForwarding(...)
        """
        try:
            NumberCallForwarding.objects.filter(
                cfnTwilioPhoneSid=twilio_phone_sid,
                cfnMemberId=get_client_id_by_tenant_id(member_id)
            ).delete()
        except Exception as e:
            logger.error(f"Error deleting call forwarding: {e}")

    @staticmethod
    def send_whoops_error(error_msg_dto):
        """
        Send error notification email to admin
        Mirrors Java's: CommonServices.sendWhoopsError(ErrorMsgDto errorMsgDto)
        """
        try:
            admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@example.com')
            mail_request = MailRequestDTO(
                to=admin_email,
                subject=f"Error: {error_msg_dto.get('error_type', 'Unknown')}",
                template_name="error_notification.ftl"
            )
            model = {
                "errorMessage": error_msg_dto.get('message', ''),
                "stackTrace": error_msg_dto.get('stack_trace', ''),
                "userId": error_msg_dto.get('user_id', '')
            }
            CommonServices.sendEmail(mail_request, model)
        except Exception as e:
            logger.error(f"Error sending error notification: {e}")

    @staticmethod
    def send_email_to_contact(tenant_id, send_email_to_contact_dto):
        res_body = {"error": ""}
        try:
            data = send_email_to_contact_dto
            email_id = data.get('emailId')
            my_page_id = data.get('myPageId')
            subject = data.get('subject')
            from_name = data.get('fromName')
            from_address = data.get('fromAddress', '').strip().lower()
            send_link_id = data.get('sendLinkId')
            send_automation_id = data.get('sendAutomationId')
            send_node_id = data.get('sendNodeId')

            userlist = Userlist.objects.get(memberId=get_client_id_by_tenant_id(tenant_id), emailId=email_id)
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": get_tenant_id_by_client_id(userlist.memberId)
                    }
                }
            )
            client = Clients.objects.get(cliTenantId=tenant_id)

            tenant_name = ""
            if tenant.ten_first_name:
                tenant_name = tenant.ten_first_name

            if tenant.ten_last_name:
                tenant_name += " " + tenant.ten_last_name

            cli_business_name = ""
            if client.cliBusinessName:
                cli_business_name = client.cliBusinessName

            cli_logo = client.cliLogo
            cli_customer_footer = client.cliCustomerFooter

            country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(userlist.memberId))
            cnty_white_listing = getattr(country_setting, 'cnty_white_listing', 'N') or 'N'

            first_name = userlist.firstName
            last_name = userlist.lastName
            email = userlist.email

            udf_values = [
                userlist.udf1, userlist.udf2, userlist.udf3, userlist.udf4, userlist.udf5,
                userlist.udf6, userlist.udf7, userlist.udf8, userlist.udf9, userlist.udf10
            ]

            udf_array = list(Udf.objects.filter(groupId=userlist.groupId).values_list('udf', flat=True))

            camp_detail_temp = ""
            try:
                translate_template = TranslateTemplate.objects.filter(
                    ttMyPageId=my_page_id,
                    ttTemplateLanguage=userlist.usDefaultLanguage
                ).order_by('-ttId').first()

                if not translate_template:
                    translate_template = TranslateTemplate.objects.filter(
                        ttMyPageId=my_page_id,
                        ttMasterCopy='Y'
                    ).order_by('-ttId').first()

                if translate_template:
                    camp_detail_temp = translate_template.ttCampDetailSend or ""
            except Exception:
                pass

            # Text cleaning mirroring Java regex
            camp_detail_temp = camp_detail_temp.replace("\u200c", "").replace("\u200b", "")
            camp_detail_temp = camp_detail_temp.replace("447px", "5px")
            camp_detail_temp = camp_detail_temp.replace('height="100%"', "")

            camp_detail_temp = camp_detail_temp.replace("<style", "~~STARTTAG~~")
            camp_detail_temp = camp_detail_temp.replace("</style>", "~~STARTTAGEND~~")
            camp_detail_temp = re.sub(r"~~STARTTAG~~[\s\S]+?~~STARTTAGEND~~", "", camp_detail_temp)
            camp_detail_temp = re.sub(r"<!--RT3S-->[\s\S]+?<!--RT3E-->", "", camp_detail_temp)

            # Placeholder replacement
            if cli_business_name:
                camp_detail_temp = re.sub(r"(?i)##business_name##", cli_business_name.strip(), camp_detail_temp)
            else:
                camp_detail_temp = re.sub(r"(?i)##business_name##", tenant_name.strip(), camp_detail_temp)

            if first_name:
                camp_detail_temp = re.sub(r"(?i)##first_name##", first_name.strip(), camp_detail_temp)

            if last_name:
                camp_detail_temp = re.sub(r"(?i)##last_name##", last_name.strip(), camp_detail_temp)

            if email:
                camp_detail_temp = re.sub(r"(?i)##email##", email.strip(), camp_detail_temp)

            client_phone_number = userlist.phoneNumber or ""
            if client_phone_number:
                camp_detail_temp = re.sub(r"(?i)##contact_no##", client_phone_number.replace(" ", "").strip(),
                                          camp_detail_temp)

            for i, udf_name in enumerate(udf_array):
                search_val = f"##{udf_name}##"
                replace_val = ""
                if i < len(udf_values) and udf_values[i]:
                    replace_val = udf_values[i].strip()
                camp_detail_temp = camp_detail_temp.replace(search_val, replace_val)

            # Jsoup equivalent using BeautifulSoup
            doc = BeautifulSoup(camp_detail_temp, "html.parser")
            for div in doc.select("div.removeClass"):
                div.decompose()
            camp_detail_temp = str(doc)

            camp_detail_temp = cron_send_campaign_content_remove(camp_detail_temp)
            camp_detail_temp = camp_detail_temp.replace("</body></html>", "")

            # Footer generation
            site_url = getattr(settings, 'SITE_URL', '')
            site_url_www = getattr(settings, 'SITE_URL_WWW', '')
            site_url_address = getattr(settings, 'SITE_URL_ADDRESS', '')

            footer_html = "<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:'Myriad Pro',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
            footer_html += "<div style='padding-top:2px'>"

            if cnty_white_listing.lower() == 'y' and cli_logo:
                footer_html += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
            else:
                footer_html += f'<a style="color:#00599A;margin: 0px auto;" href="{site_url_www}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{site_url}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:100%" border="0"></a>'

            footer_html += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"

            if cnty_white_listing.lower() == 'y' and cli_customer_footer:
                footer_html += nl2br(cli_customer_footer)
            else:
                footer_html += site_url_address

            # Tracking and Unsubscribe links
            q_str = DecryptString.set_enc_dec_user(f"{userlist.groupId}~{userlist.memberId}~0~{userlist.emailId}", "",
                                                   "Y")
            update_contact_link = f"{site_url}inviteurl?q={q_str}"

            user_id_b64 = base64.b64encode(str(email_id).encode('utf-8')).decode('utf-8')
            email_b64 = base64.b64encode(email.encode('utf-8')).decode('utf-8')
            member_id_b64 = base64.b64encode(str(tenant_id).encode('utf-8')).decode('utf-8')

            footer_html += "</div></div></div></div>"

            view_in_browser_link = f"{site_url}viewinbrowser?mpId={DecryptString.set_enc_dec_user(str(my_page_id), '', 'Y')}&ui={user_id_b64}&ci=0"
            unsubscribe_link = f"{site_url}unsubscribe?ui={user_id_b64}&ci=0&e={email_b64}&m={member_id_b64}"
            change_lang_link = f"{site_url}viewtemplate?mpId={DecryptString.set_enc_dec_user(str(my_page_id), '', 'Y')}"

            footer_html += f"<div align='center' style='color:#4285F4;font-size:12px;font-family:Arial, Helvetica Neue, Helvetica, sans-serif;'><a href='{view_in_browser_link}' style='color:#4285F4'>View In Browser</a> | <a href='{unsubscribe_link}' style='color:#4285F4'>Unsubscribe</a> | <a href='{change_lang_link}' style='color:#4285F4'>Change Language</a> | <a href='{update_contact_link}' style='color:#4285F4'>Update Contact Information</a></div>"
            footer_html += "</body></html>"

            camp_detail_temp += footer_html

            # Save to MyCrmSendEmail
            my_crm_send_email = MyCrmSendEmail(
                send_subject=subject,
                send_from_name=from_name,
                send_from_email=from_address,
                send_reply_to_email=from_address,
                send_to_email=email.lower(),
                send_email_details=strip_slashes(camp_detail_temp),
                send_member_id=get_client_id_by_tenant_id(tenant_id)
            )
            my_crm_send_email.save()

            # Save to AutomationLinkClickEmail if sendLinkId exists
            if send_link_id and int(send_link_id) > 0:
                automation_id = AutomationCampaignNode.objects.filter(acnId=send_link_id).values('acnAutId').first()
                automation_email = AutomationLinkClickEmail(
                    sendSubject=subject,
                    sendFromName=from_name,
                    sendFromEmail=from_address,
                    sendReplyToEmail=from_address,
                    sendToEmail=email.lower(),
                    sendEmailDetails=strip_slashes(camp_detail_temp),
                    sendMemberId=get_client_id_by_tenant_id(tenant_id),
                    sendLinkId=send_link_id,
                    sendAutomationId=automation_id,
                    sendNodeId=send_node_id,
                    sendDateTime=timezone.now()
                )
                automation_email.save()

        except Exception as e:
            logger.exception(e)
            logger.error(f"[ tenantId : {tenant_id} ] send_email_to_contact Error : {e}")
            res_body["error"] = "error"
        return res_body


    @staticmethod
    def send_optin_details_sms(userlist, automation_sms_reply_log):
        """
        Send SMS opt-in confirmation with template personalization
        Mirrors Java's: CommonServicesImpl.sendOptInDetailsSms(Userlist userlist, AutomationSmsReplyLog automationSmsReplyLog)
        Lines: 2513-2727

        Process:
        1. Fetch member details and decrypt names
        2. Build contact information (first/last name, email, phone, UDFs)
        3. Fetch SMS opt-in template
        4. Replace all placeholders with contact details
        5. Calculate SMS charges and create transaction
        6. Send SMS via Telnyx
        7. Update AutomationSmsReplyLog or create ContactSendSmsLogs
        """
        try:
            if not userlist or not userlist.phoneNumber:
                logger.warning("Invalid userlist or missing phone number")
                return False

            # Step 1: Get member details for name personalization
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": get_tenant_id_by_client_id(userlist.memberId)
                    }
                }
            )
            client = Clients.objects.get(cliId=userlist.memberId)
            if tenant is None:
                logger.error(f"Tenant not found for tenant_id: {userlist.memberId}")
                return False

            # Step 2: Build member name (for greeting)
            tenant_name = ""
            if tenant.ten_first_name:
                tenant_name = tenant.ten_first_name or ""

            if tenant.ten_last_name:
                if tenant_name:
                    tenant_name += " " + tenant.ten_last_name
                else:
                    tenant_name = tenant.ten_last_name or ""

            # Step 3: Build business name
            cli_business_name = ""
            if client.cliBusinessName:
                cli_business_name = client.cliBusinessName or ""

            # Step 4: Get contact details
            first_name = userlist.firstName or ""
            last_name = userlist.lastName or ""
            email = ""
            if userlist.email:
                email = userlist.email or ""

            mobile_number = userlist.phoneNumber or ""

            # Step 5: Get all UDF values
            udf_values = [
                userlist.udf1 or "",
                userlist.udf2 or "",
                userlist.udf3 or "",
                userlist.udf4 or "",
                userlist.udf5 or "",
                userlist.udf6 or "",
                userlist.udf7 or "",
                userlist.udf8 or "",
                userlist.udf9 or "",
                userlist.udf10 or ""
            ]

            # Escape single quotes in UDFs (Java pattern: udf.replaceAll("'", "\'"))
            udf_values = [udf.replace("'", "\\'") if udf else "" for udf in udf_values]

            # Step 6: Fetch SMS opt-in template
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT ST_DETAILS FROM SMS_TEMPLATES WHERE ST_CLIENT_ID = %s AND ST_NAME = 'Opt In' LIMIT 1",
                    [userlist.memberId]
                )
                row = cursor.fetchone()
                sms_details = row[0] if row else ""
                sms_details = str(sms_details)

            if not sms_details:
                logger.warning(f"No opt-in SMS template found for member {userlist.memberId}")
                return False

            # Step 7: Replace placeholders in SMS template (case-insensitive)

            # Replace business name or member name
            if cli_business_name:
                sms_details = re.sub(r'(?i)##Business Name##', cli_business_name, sms_details)
            elif tenant_name:
                sms_details = re.sub(r'(?i)##Business Name##', tenant_name, sms_details)
            else:
                sms_details = re.sub(r'(?i)##Business Name##', '', sms_details)

            # Replace first name
            if first_name:
                sms_details = re.sub(r'(?i)##First Name##', first_name, sms_details)
            else:
                sms_details = re.sub(r'(?i)##First Name##', '', sms_details)

            # Replace last name
            if last_name:
                sms_details = re.sub(r'(?i)##Last Name##', last_name, sms_details)
            else:
                sms_details = re.sub(r'(?i)##Last Name##', '', sms_details)

            # Replace email
            if email:
                sms_details = re.sub(r'(?i)##Email##', email, sms_details)
            else:
                sms_details = re.sub(r'(?i)##Email##', '', sms_details)

            # Replace mobile number (case-sensitive for ##Mobile Number##, case-insensitive for ##Contact No##)
            if mobile_number:
                sms_details = sms_details.replace('##Mobile Number##', mobile_number)
                sms_details = sms_details.replace('##Contact No##', mobile_number)
                sms_details = re.sub(r'(?i)##Mobile Number##', mobile_number, sms_details)
                sms_details = re.sub(r'(?i)##Contact No##', mobile_number, sms_details)
            else:
                sms_details = re.sub(r'(?i)##Mobile Number##', '', sms_details)
                sms_details = re.sub(r'(?i)##Contact No##', '', sms_details)

            # Step 8: Replace UDF placeholders
            # First, get list of UDF labels for this group
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT UDF_UDF_LABEL FROM UDFS WHERE UDF_GROUP_ID = %s ORDER BY UDF_UDF_LABEL",
                        [userlist.groupId]
                    )
                    udf_labels = [row[0] for row in cursor.fetchall()]

                for idx, label in enumerate(udf_labels[:10]):  # Max 10 UDFs
                    if idx < len(udf_values):
                        udf_value = udf_values[idx]
                        if udf_value:
                            pattern = re.compile(f'##{re.escape(label)}##', re.IGNORECASE)
                            sms_details = pattern.sub(str(udf_value), sms_details)
                        else:
                            pattern = re.compile(f'##{re.escape(label)}##', re.IGNORECASE)
                            sms_details = pattern.sub('', sms_details)
            except Exception as e:
                logger.warning(f"Error processing UDFs: {e}")

            # Step 9: Handle country and phone number formatting
            if not userlist.country or userlist.country.strip() == "":
                userlist.country = "United States"

            try:
                country = Country.objects.get(long_name=userlist.country)
            except Country.DoesNotExist:
                logger.warning(f"Country not found: {userlist.country}")
                return False

            # Get client phone number (last N digits based on country's phone_max_length)
            client_phone_number = ""
            if userlist.phoneNumber and userlist.phoneNumber.strip():
                # Take last N digits where N = country's phone_max_length
                client_phone_number = userlist.phoneNumber[-country.phone_max_length:] if country.phone_max_length > 0 else userlist.phoneNumber
            elif userlist.phone and userlist.phone.strip():
                client_phone_number = userlist.phone[-country.phone_max_length:] if country.phone_max_length > 0 else userlist.phone

            # Step 10: Check if we can send SMS
            phone_number = get_phone_numbers_first(tenant.ten_id, "CAMPAIGN")
            if not ((phone_number.phPhoneNumber and phone_number.phPhoneNumber.strip() and
                    client_phone_number and client_phone_number.strip()) or automation_sms_reply_log):
                logger.warning("Cannot send opt-in SMS: missing Telnyx number or client phone")
                return False

            # Prepend country code
            client_phone_number = (country.cnt_code or "") + client_phone_number

            try:
                # Step 11: Create update contact link
                link_string = f"{userlist.groupId}~{userlist.memberId}~0~{userlist.emailId}"
                encrypted_link = DecryptString.set_enc_dec_user(link_string, "", "Y")
                site_url = getattr(settings, 'SITE_URL', 'https://www.salesandmarketing.ai/')
                update_contact_link = f"{site_url}inviteurl?q={encrypted_link}"

                sms_details = re.sub(r'(?i)##Link##', update_contact_link, sms_details)

                # Step 12: Calculate SMS charges and create transaction
                country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(userlist.memberId))
                sms_rate = getattr(country_setting, 'cnty_sms_per_price', 0)

                if sms_rate > 0:
                    # SMS count: ceil(message_length / 160)
                    sms_count = (len(sms_details) + 159) // 160  # Ceiling division
                    total_amount = sms_rate * sms_count

                    # Create transaction
                    if automation_sms_reply_log:
                        CommonServices.saveCampaignTransaction(
                            None,
                            "Opt In SMS Charges",
                            1,
                            'sms',
                            None,
                            'uninvoiced',
                            None,
                            userlist.memberId,
                            '0',
                            total_amount,
                            sms_rate,
                            sms_count,
                            automation_sms_reply_log.log_from_number,
                            automation_sms_reply_log.log_to_number,
                            0
                        )
                    else:
                        CommonServices.saveCampaignTransaction(
                            None,
                            "Opt In SMS Charges",
                            1,
                            'sms',
                            None,
                            'uninvoiced',
                            None,
                            userlist.memberId,
                            '0',
                            total_amount,
                            sms_rate,
                            sms_count,
                            phone_number.phPhoneNumber,
                            client_phone_number,
                            0
                        )

                # Step 13: Send SMS via Telnyx
                if automation_sms_reply_log:
                    msg_response = telnyx_utils.send_sms_telnyx(
                        automation_sms_reply_log.log_to_number,
                        automation_sms_reply_log.log_from_number,
                        'text',
                        sms_details,
                        'first',
                        '',
                        getattr(settings, 'SMS_STATUS_URL_SEND_SMS_OPT_IN', ''),
                        getattr(settings, 'TELNYX_BASE_URL', None),
                        getattr(settings, 'TELNYX_API_KEY', None)
                    )

                    # Update AutomationSmsReplyLog with response details
                    automation_sms_reply_log.log_status = msg_response.get('msgStatus', '')
                    automation_sms_reply_log.log_sid = msg_response.get('msgId', '')
                    automation_sms_reply_log.log_error_message = msg_response.get('msgError', '')
                    automation_sms_reply_log.log_error_code = msg_response.get('msgErrorCode', '')
                    automation_sms_reply_log.log_send_reply_details = sms_details
                    automation_sms_reply_log.save()

                else:
                    msg_response = telnyx_utils.send_sms_telnyx(
                        client_phone_number,
                        phone_number.phPhoneNumber,
                        'text',
                        sms_details,
                        'first',
                        '',
                        getattr(settings, 'SMS_STATUS_URL_SEND_SMS_OPT_IN', ''),
                        getattr(settings, 'TELNYX_BASE_URL', None),
                        getattr(settings, 'TELNYX_API_KEY', None)
                    )

                    # Create ContactSendSmsLogs record
                    try:
                        ContactSendSmsLogs.objects.create(
                            member_id=userlist.memberId,
                            email_id=userlist.emailId,
                            sid=msg_response.get('msgId', ''),
                            sms_status=msg_response.get('msgStatus', ''),
                            error_code=msg_response.get('msgErrorCode', ''),
                            from_contact=phone_number.phPhoneNumber,
                            to_contact=client_phone_number,
                            sms_detail=sms_details,
                            group_id=userlist.groupId,
                            sms_send_date=timezone.now()
                        )
                    except Exception as e:
                        logger.error(f"Error creating ContactSendSmsLogs: {e}")

                logger.info(f"Opt-in SMS sent successfully to {client_phone_number}")
                return True

            except Exception as e:
                logger.error(f"Error sending opt-in SMS: {e}")
                return False

        except Exception as e:
            logger.error(f"SendOptInDetailsSms Error: {e}")
            return False

    @staticmethod
    def send_optin_details_email(userlist):
        """
        Send opt-in confirmation email.
        Mirrors Java's ContactServiceImpl.sendOptInDetailsEmail logic.
        """
        try:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": userlist.memberId
                    }
                }
            )
            client = Clients.objects.get(cliId=userlist.memberId)
            tenant_name = ""
            if tenant.ten_first_name:
                tenant_name = tenant.ten_first_name
            if tenant.ten_last_name:
                tenant_name += " " + tenant.ten_last_name

            cli_business_name = ""
            if client.cliBusinessName:
                cli_business_name = client.cliBusinessName

            # Fetch Opt In template from MyPage
            try:
                mypage = MyPages.objects.filter(mpClientId=userlist.memberId, mpName='Opt In').first()
                if not mypage or not mypage.mpDetails:
                    logger.warning(f"No Opt In template found for member {userlist.memberId}")
                    return False
                content = mypage.mpDetails
            except Exception as e:
                logger.error(f"Error fetching MyPage for opt-in: {e}")
                return False

            # Sanitization (parity with Java regex)
            content = content.replace("\u200c", "").replace("\u200b", "")
            content = content.replace("447px", "5px")
            # Remove <style> tags content
            content = re.sub(r'<style[\s\S]+?</style>', '', content, flags=re.IGNORECASE)
            # Remove RT3 tags
            content = re.sub(r'<!--RT3S-->[\s\S]+?<!--RT3E-->', '', content)

            # Replacements
            b_name = cli_business_name if cli_business_name else tenant_name
            content = re.sub(r'##business_name##', b_name, content, flags=re.IGNORECASE)
            content = re.sub(r'##first_name##', userlist.firstName or "", content, flags=re.IGNORECASE)
            content = re.sub(r'##last_name##', userlist.lastName or "", content, flags=re.IGNORECASE)
            
            email_display = userlist.email if userlist.email else ""
            content = re.sub(r'##email##', email_display, content, flags=re.IGNORECASE)

            phone_display = userlist.phoneNumber or userlist.phone or ""
            content = re.sub(r'##contact_no##', phone_display.replace(" ", ""), content, flags=re.IGNORECASE)

            # UDF Replacements
            udfs = Udf.objects.filter(groupId=userlist.groupId).values_list('udf', flat=True)
            for i, udf_label in enumerate(udfs):
                if i >= 10: break
                search_val = f"##{udf_label}##"
                udf_val = getattr(userlist, f'udf{i+1}', "") or ""
                content = content.replace(search_val, udf_val)

            # Jsoup equivalent using BeautifulSoup
            doc = BeautifulSoup(content, "html.parser")
            for div in doc.select("div.removeClass"):
                div.decompose()
            content = str(doc)

            # Wrap and send
            subject = f"Opt In - {b_name}"
            mail_request = MailRequestDTO(to=email_display, subject=subject, template_name="generic_content.html")
            # We use a generic template that just renders {{ content|safe }}
            return CommonServices.sendEmail(mail_request, {"content": content})

        except Exception as e:
            logger.error(f"Error in send_optin_details_email: {e}")
            return False

    @staticmethod
    def findGroupEmailCount(member_id, group_id):        
        return Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            groupId=group_id
        ).exclude(Q(email__isnull=True) | Q(email='')).count()

    @staticmethod
    def findEmailCount(member_id, email_ids):
        return Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            emailId__in=email_ids
        ).exclude(Q(email__isnull=True) | Q(email='')).count()

    @staticmethod
    def findGroupSmsCount(member_id, group_id):
        return Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            groupId=group_id
        ).exclude(Q(phoneNumber__isnull=True) | Q(phoneNumber='')).count()

    @staticmethod
    def findSmsCount(member_id, email_ids):
        return Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            emailId__in=email_ids
        ).exclude(Q(phoneNumber__isnull=True) | Q(phoneNumber='')).count()

    @staticmethod
    def updateOptInEmail(member_id, group_id):
        Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            groupId=group_id
        ).exclude(Q(email__isnull=True) | Q(email='')).update(
            typeEmail='email',
            emailVerificationStatus='done',
            optDate=timezone.now()
        )

    @staticmethod
    def updateOptInEmailOnlyIds(member_id, email_ids):
        Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            emailId__in=email_ids
        ).exclude(Q(email__isnull=True) | Q(email='')).update(
            typeEmail='email',
            emailVerificationStatus='done',
            optDate=timezone.now()
        )

    @staticmethod
    def updateOptInSms(member_id, group_id):
        Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            groupId=group_id
        ).exclude(Q(phoneNumber__isnull=True) | Q(phoneNumber='')).update(
            typeSms='sms',
            emailVerificationStatus='done',
            optDate=timezone.now()
        )

    @staticmethod
    def updateOptInSmsOnlyIds(member_id, email_ids):
        Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(member_id),
            emailId__in=email_ids
        ).exclude(Q(phoneNumber__isnull=True) | Q(phoneNumber='')).update(
            typeSms='sms',
            emailVerificationStatus='done',
            optDate=timezone.now()
        )

    @staticmethod
    def checkDuplicateRecords(group_id, tenant_id):
        check_duplicate_records(group_id, tenant_id)

    @staticmethod
    def checkTotalMember(group_id, tenant_id):
        check_total_member(group_id, tenant_id)

    @staticmethod
    def get_country_to_states(country_id):
        """
        Get all states for a country
        Mirrors Java's: CommonServices.getCountryToStates(Long countryId)
        """
        try:
            return CountryToState.objects.filter(fk_country_id=country_id)
        except Exception as e:
            logger.error(f"Error in get_country_to_states: {e}")
            return []

    @staticmethod
    def get_all_language():
        """Get all languages"""
        try:
            return Language.objects.all()
        except Exception as e:
            logger.error(f"Error in get_all_language: {e}")
            return []

    @staticmethod
    def get_all_security_question_list():
        """Get all security questions"""
        try:
            return SecurityQuestion.objects.all()
        except Exception as e:
            logger.error(f"Error in get_all_security_question_list: {e}")
            return []

    @staticmethod
    def get_all_country():
        """Get all countries"""
        try:
            return Country.objects.all()
        except Exception as e:
            logger.error(f"Error in get_all_country: {e}")
            return []

    @staticmethod
    def get_all_country_to_states():
        """Get all country to state mappings"""
        try:
            return CountryToState.objects.all()
        except Exception as e:
            logger.error(f"Error in get_all_country_to_states: {e}")
            return []

    @staticmethod
    def total_uninvoiced_amt(tenant_id):
        """
        Calculate total uninvoiced amount for member
        Mirrors Java's: CommonServices.totalUninvoicedAmt(Long memberId)
        """
        try:
            amt = 0
            previous_uninvoiced_price = 0
            trans_types = ["sms", "sms number", "sms polling", "sms polling number", "language translation"]

            campaign_transactions = CampaignTransaction.objects.filter(
                ct_client_id=get_client_id_by_tenant_id(tenant_id),
                tran_invoiced_status='uninvoiced',
                tran_bill_type=0
            )

            for ct in campaign_transactions:
                tran_type = (ct.tran_type or "").lower()
                if tran_type == "previous uninvoiced":
                    previous_uninvoiced_price += (ct.tran_total_amount or 0)

                if tran_type in trans_types:
                    amt += (ct.tran_total_amount or 0)
                else:
                    amt += ((ct.tran_total_member or 0) * (ct.tran_member_rate or 0))

            try:
                tenant = get_tenants(
                    where_conditions={
                        "tenant": {
                            "ten_id": tenant_id
                        }
                    }
                )
                country_id = tenant.ten_country or "100"
                plan_id = tenant.td_plan_id or 1

                try:
                    country_setting = CountrySetting.objects.get(cnty_id=int(country_id), cnty_plan_id=plan_id)
                except CountrySetting.DoesNotExist:
                    country_setting = CountrySetting.objects.filter(cnty_id=100, cnty_plan_id=2).first()

                
                cur_contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id)).count()

                plan = Plans.objects.get(plan_id=plan_id)
                if plan.plan_name.lower() == "pay as you grow":
                    if country_setting :
                        ctny_contact_per_price = country_setting.ctny_contact_per_price
                    else:
                        ctny_contact_per_price = 0
                    amt = previous_uninvoiced_price + (cur_contacts * ctny_contact_per_price)
            except Exception:
                pass

            return amt
        except Exception as e:
            logger.error(f"Error in total_uninvoiced_amt: {e}")
            return 0

    # ===== SMS Reply Helper Methods =====

    @staticmethod
    def sms_automation_reply(to_no, from_no, user_reply):
        """
        Check if automation rules handle the SMS reply
        Mirrors Java's: CommonServicesImpl.smsAutomationReply(String toNo, String fromNo, String userReply)
        Lines: 1022-1133

        Implements flag mechanism:
        - flag=0: No matching automation found
        - flag=1: Automation found and rule matched
        - flag=2: New contact was created (triggers opt-in logic)
        """
        try:
            if not user_reply or not from_no:
                return False

            # Step 1: Normalize user reply (collapse whitespace, trim, lowercase)
            # Pattern: userReply.replaceAll("\\s+", " ").trim().toLowerCase();
            user_reply_normalized = ' '.join(user_reply.split()).strip().lower()

            # Step 2: Clean phone number and prepend "+"
            # Pattern: tempFromNo = "+" + CommonFunction.cleanMeNumber(fromNo);
            temp_from_no = "+" + clean_me_number(from_no)

            # Step 3: Find automation by SMS from number
            automation = Automation.objects.filter(autSmsFromNumber=temp_from_no).first()

            if not automation:
                return False

            flag = 0

            # Step 4: Check for duplicate replies (logCount > 1)
            # Java: automationSmsReplyLogRepository.findCount(automation.getSmsGroupId(), toNo, fromNo, automation.getAmId());
            log_count = AutomationSmsReplyLog.objects.filter(
                log_sms_id=automation.autId,
                log_to_number=to_no,
                log_from_number=from_no
            ).count()

            if log_count > 1:
                return True  # Exit early if already replied multiple times

            # Step 5: Find matching automation SMS details and process
            auto_details = AutomationSmsDetails.objects.filter(detSmsId=automation.autId)

            for asd in auto_details:
                # Check if received reply matches expected reply (case-insensitive)
                expected_reply = (asd.detReceiveReply or '').strip().lower()
                expected_reply = ' '.join(expected_reply.split())  # Collapse whitespace

                if expected_reply and user_reply_normalized == expected_reply:
                    try:
                        # Initialize flag if first match
                        if flag == 0:
                            flag = 1

                            # Check if contact exists
                            contact_count = Userlist.objects.filter(
                                phoneNumber=to_no,
                                memberId=automation.autClientId,
                                groupId=automation.autGroupId
                            ).count()

                            if contact_count == 0:
                                flag = 2

                                # Create new contact with all fields (matching Java implementation)
                                Userlist.objects.create(
                                    memberId=get_tenant_id_by_client_id(automation.autClientId),
                                    groupId=automation.autGroupId,
                                    firstName="",
                                    lastName="",
                                    fullName="",
                                    email="",
                                    phoneNumber=to_no,
                                    status="Subscribed",
                                    smsStatus="Subscribed",
                                    dateAdded=timezone.now(),
                                    typeSms="done",
                                    typeEmail="done",
                                    badEmail="N",
                                    badPhoneNumber="N",
                                    country="United States"
                                )

                    except Exception as e:
                        logger.error(f"Error in automation contact creation: {e}")

                    # Step 6: Send SMS reply using Telnyx
                    msg_response = telnyx_utils.send_sms_telnyx(
                        to_no,
                        from_no,
                        'text',
                        asd.detSendReplyDetails.strip() if asd.detSendReplyDetails else '',
                        'first',  # sms_count parameter
                        None,  # opt_out_msg
                        getattr(settings, 'SMS_STATUS_REPLY_URL', ''),
                        getattr(settings, 'TELNYX_BASE_URL', None),
                        getattr(settings, 'TELNYX_API_KEY', None)
                    )

                    # Step 7: Log automation SMS reply with full details (status, sid, error codes)
                    try:
                        AutomationSmsReplyLog.objects.create(
                            log_sms_id=automation.autId,
                            log_to_number=to_no,
                            log_from_number=from_no,
                            log_status=msg_response.get('msgStatus', ''),
                            log_sid=msg_response.get('msgId', ''),
                            log_error_message=msg_response.get('msgError', ''),
                            log_error_code=msg_response.get('msgErrorCode', ''),
                            log_member_id=automation.autClientId,
                            log_receive_reply=user_reply_normalized,
                            log_send_reply_details=asd.detSendReplyDetails
                            # log_created_date will be automatically set by Django's auto_now_add=True
                        )
                    except Exception as e:
                        logger.error(f"Error logging automation SMS reply: {e}")

                    # Step 8: Create transaction for SMS reply
                    try:
                        country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(automation.autClientId))
                        sms_reply_text = asd.detSendReplyDetails.strip() if asd.detSendReplyDetails else ''
                        sms_count = max(1, (len(sms_reply_text) + 159) // 160)
                        sms_rate = getattr(country_setting, 'cnty_sms_per_price', 0)

                        if sms_rate > 0:
                            total_amount = sms_rate * sms_count

                            CommonServices.saveCampaignTransaction(
                                None,
                                automation.autName,
                                1,
                                'sms conversations',
                                None,
                                'uninvoiced',
                                None,
                                automation.autClientId,
                                '0',
                                total_amount,
                                sms_rate,
                                sms_count,
                                from_no,
                                to_no,
                                0
                            )
                    except Exception as e:
                        logger.error(f"Error creating automation transaction: {e}")

            # Step 9: Handle opt-in logic (when smsOptinYn='Y' and flag=2)
            if automation.autSmsOptInYn == "Y" and flag == 2:
                try:
                    # Fetch the newly created contact
                    userlist = Userlist.objects.get(
                        phoneNumber=to_no,
                        memberId=automation.autClientId,
                        groupId=automation.autGroupId
                    )

                    # Create automation SMS reply log for opt-in
                    automation_sms_reply_log = AutomationSmsReplyLog.objects.create(
                        log_sms_id=automation.autId,
                        log_to_number=to_no,
                        log_from_number=from_no,
                        log_member_id=automation.autClientId,
                        # log_created_date will be automatically set by Django's auto_now_add=True
                    )

                    # Send opt-in SMS if user reply is not empty
                    if user_reply and user_reply.strip():
                        CommonServices.send_optin_details_sms(userlist, automation_sms_reply_log)

                except Exception as ex:
                    logger.error(f"Automation SMS Opt-In Reply Error: {ex}")

            # Return True if any rule was matched (flag > 0), False otherwise
            return flag > 0

        except Exception as e:
            logger.error(f"Error in sms_automation_reply: {e}")
            return False

    @staticmethod
    def sms_campaign_reply(to_no, from_no, user_reply):
        try:
            clean_to = to_no.replace('+', '').replace('-', '').replace(' ', '')[-10:]
            clean_from = from_no.replace('+', '').replace('-', '').replace(' ', '')[-10:]

            campaign_sms = CampaignSendSms.objects.filter(
                toContact__endswith=clean_to,
                fromContact__endswith=clean_from
            ).first()

            if not campaign_sms:
                return

            sms_id = campaign_sms.smsId
            tenant_id = campaign_sms.memberId
            email_id = campaign_sms.emailId
            sid = campaign_sms.sid
            campaign_sms_send = CampaignsSmsSend.objects.filter(
                id=sms_id
            ).first()
            if campaign_sms_send:
                sms_id = campaign_sms_send.smsId
                Heading = campaign_sms_send.smsName
            else:
                sms_id = 0
                Heading = ""
            # Check keywords
            norm_reply = user_reply.lower().strip()
            stop_kw = ['stop', 'stopall', 'stop all', 'unsubscribe', 'cancel', 'end', 'quit']

            if norm_reply in stop_kw:
                Userlist.objects.filter(
                    memberId=tenant_id,
                    phoneNumber__endswith=clean_to
                ).update(smsStatus='Unsubscribed', optOutDate=timezone.now())
            elif norm_reply in ['start', 'unstop']:
                Userlist.objects.filter(
                    memberId=tenant_id,
                    phoneNumber__endswith=clean_to
                ).update(smsStatus='Subscribed')

            # Get settings
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": get_tenant_id_by_client_id(tenant_id)
                    }
                }
            )
            client = Clients.objects.get(cliId=tenant_id)
            country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(tenant_id))
            sms_rate = getattr(country_setting, 'cnty_sms_per_price', 0)
            if tenant is None:
                tenant = None
                sms_rate = 0

            sms_cnt = max(1, (len(user_reply) + 159) // 160)

            # Send copy if enabled
            if tenant and getattr(client, 'cliSmsForwardMyphoneYn', None) == 'Y' and getattr(tenant, 'ten_phone', None):
                try:
                    telnyx_utils.send_sms_telnyx(
                        getattr(tenant, 'ten_phone'), from_no, 'text',
                        f"[Reply from {to_no}]: {user_reply}", 1, None,
                        getattr(settings, 'SMS_STATUS_REPLY_URL', ''),
                        getattr(settings, 'TELNYX_BASE_URL', None),
                        getattr(settings, 'TELNYX_API_KEY', None)
                    )
                    sms_cnt += 1
                except Exception as e:
                    logger.error(f"Error sending copy: {e}")

            # Save reply
            try:
                campaign_sms_reply = CampaignSmsReply(
                    crEmailId=email_id,
                    crSid=sid,
                    crMemberId=tenant_id,
                    crReply=user_reply,
                    crReplyNo=to_no,
                    crSmsId=sms_id,
                    crSmsSid=None,
                    crSmsStatus='received',
                    crSmsFromNo=from_no,
                    crSmsToNo=to_no,
                    crDate=timezone.now()
                )
                campaign_sms_reply.save()
            except Exception as e:
                logger.error(f"Error saving reply: {e}")

            # Update/create transaction
            try:
                transaction = CampaignTransaction.objects.get(
                    member_id=tenant_id,
                    tran_campaign_id=sms_id,
                    tran_type='sms',
                    tran_invoiced_status='uninvoiced'
                )
                transaction.tran_total_amount = (transaction.tran_total_amount or 0.0) + (sms_cnt * (transaction.tran_member_rate or sms_rate))
                transaction.tran_count_total_sms = (transaction.tran_count_total_sms or 0) + sms_cnt
                transaction.save()
            except CampaignTransaction.DoesNotExist:
                total_amount = sms_cnt * sms_rate
                CommonServices.saveCampaignTransaction(
                    sms_id,                      # 1: tranCampaignId
                    Heading,                     # 2: tranCampaignName
                    1,                           # 3: tranTotalMember
                    "sms",                       # 4: tranType
                    None,                        # 5: tranInvoicedId
                    "uninvoiced",                # 6: tranInvoicedStatus
                    None,                        # 7: tranInvoicedDate
                    tenant_id,                   # 8: memberId
                    "0",                         # 9: tranBillType
                    total_amount,                # 10: tranTotalAmount
                    sms_rate,                    # 11: tranMemberRate
                    sms_cnt,                     # 12: tranCountTotalSms
                    None,                        # 13: tranPollFormNo
                    None,                        # 14: tranPollToNo
                    0                # 15: subMemberId
                )
            except Exception as e:
                logger.error(f"Error in sms_campaign_reply transaction: {e}")

        except Exception as e:
            logger.error(f"Error in sms_campaign_reply: {e}")

    @staticmethod
    def conversations_reply(to_no, from_no, user_reply, mes_id):
        """
        Process conversations reply
        Mirrors Java's: CommonServices.conversationsReply(String toNo, String fromNo, String userReply, String mesId)
        Lines: 1320-1474
        """
        try:
            client_number = '+' + (to_no.replace('+', '').replace('-', '').replace(' ', ''))
            twilio_number = '+' + (from_no.replace('+', '').replace('-', '').replace(' ', ''))

            conversation_qs = SmsConversations.objects.filter(
                cvsId=OuterRef('cvsdCvsId'),
                cvsTwilioNumber=twilio_number
            )

            conversation = (
                SmsConversationsDetails.objects
                .filter(cvsdClientNumber=client_number)
                .annotate(
                    cvsdId=Subquery(conversation_qs.values('cvsId')[:1]),
                    cvsdClientNumber=Subquery(conversation_qs.values('cvsMemberNumber')[:1]),
                    cvsdClientId=Subquery(conversation_qs.values('cvsMemberId')[:1]),
                )
                .exclude(cvsdId__isnull=True)
                .order_by('-cvsdId')
                .values(
                    'cvsdId',
                    'cvsdClientNumber',
                    'cvsdClientId'
                )[:1]
            )

            if not conversation:
                return

            conversation = conversation[0]

            cvs_id = conversation['cvsdId']
            cvs_tenant_id = conversation['cvsdClientId']
            cvsd_client_id = conversation['cvsdClientId']

            # Check keywords
            norm_reply = user_reply.lower().strip()
            if norm_reply in ['stop', 'stopall', 'stop all', 'unsubscribe']:
                Userlist.objects.filter(
                    memberId=cvs_tenant_id,
                    phoneNumber__endswith=client_number[-10:]
                ).update(smsStatus='Unsubscribed', optOutDate=timezone.now())
            elif norm_reply in ['start', 'unstop']:
                Userlist.objects.filter(
                    memberId=cvs_tenant_id,
                    phoneNumber__endswith=client_number[-10:]
                ).update(smsStatus='Subscribed')

            # Get settings
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": get_tenant_id_by_client_id(cvs_tenant_id)
                    }
                }
            )
            client = Clients.objects.get(cliId=cvs_tenant_id)
            country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(cvs_tenant_id))
            sms_rate = getattr(country_setting, 'cnty_sms_conversations_per_price', 0)
            if tenant is None:
                tenant = None
                sms_rate = 0

            sms_cnt = max(1, (len(user_reply) + 159) // 160)

            # Send copy if enabled
            if tenant and getattr(client, 'cliSmsForwardMyphoneYn', None) == 'Y' and getattr(tenant, 'ten_phone', None):
                try:
                    telnyx_utils.send_sms_telnyx(
                        getattr(tenant, 'ten_phone'), twilio_number, 'text',
                        f"[Conv from {client_number}]: {user_reply}", 1, None,
                        getattr(settings, 'CONVERSATIONS_STATUS_URL', ''),
                        getattr(settings, 'TELNYX_BASE_URL', None),
                        getattr(settings, 'TELNYX_API_KEY', None)
                    )
                    sms_cnt += 1
                except Exception as e:
                    logger.error(f"Error sending copy: {e}")

            # Save detail
            try:
                SmsConversationsDetails.objects.create(
                    cvsdCvsId=cvs_id,
                    cvsdMessage=user_reply,
                    cvsdClientId=cvsd_client_id,
                    cvsdClientNumber=client_number,
                    cvsdSid=mes_id,
                    cvsdSender='c',
                    cvsdDate=timezone.now()
                )
            except Exception as e:
                logger.error(f"Error saving detail: {e}")

            # Update/create transaction
            try:
                transaction = CampaignTransaction.objects.get(
                    member_id=cvs_tenant_id,
                    tran_campaign_id=cvs_id,
                    tran_type='sms conversations',
                    tran_invoiced_status='uninvoiced'
                )
                transaction.tran_total_amount = (transaction.tran_total_amount or 0.0) + (sms_cnt * (transaction.tran_member_rate or sms_rate))
                transaction.tran_count_total_sms = (transaction.tran_count_total_sms or 0) + sms_cnt
                transaction.save()
            except CampaignTransaction.DoesNotExist:
                total_amount = sms_cnt * sms_rate
                CommonServices.saveCampaignTransaction(
                    cvs_id,                      # 1: tranCampaignId
                    "",                          # 2: tranCampaignName
                    1,                           # 3: tranTotalMember
                    "sms conversations",         # 4: tranType
                    None,                        # 5: tranInvoicedId
                    "uninvoiced",                # 6: tranInvoicedStatus
                    None,                        # 7: tranInvoicedDate
                    cvs_tenant_id,               # 8: memberId
                    "0",                         # 9: tranBillType
                    total_amount,                # 10: tranTotalAmount
                    sms_rate,                    # 11: tranMemberRate
                    sms_cnt,                     # 12: tranCountTotalSms
                    None,                        # 13: tranPollFormNo
                    None,                        # 14: tranPollToNo
                    0                # 15: subMemberId
                )
            except Exception as e:
                logger.error(f"Error in conversations_reply transaction: {e}")

        except Exception as e:
            logger.error(f"Error in conversations_reply: {e}")

    @staticmethod
    def sms_polling_reply(to_no, from_no, user_reply, from_country, from_state, from_city, from_zip):
        """
        Process SMS polling reply
        Mirrors Java's: CommonServices.smsPollingReply(String toNo, String fromNo, String userReply, String fromCountry, String fromState, String fromCity, String fromZip)
        Lines: 1476-1656
        """
        try:
            to_fmt = '+' + (to_no.replace('+', '').replace('-', '').replace(' ', ''))
            from_fmt = '+' + (from_no.replace('+', '').replace('-', '').replace(' ', ''))

            sp_reply = SpReply.objects.filter(toNo=to_fmt, fromNo=from_fmt).first()
            if not sp_reply:
                return

            sms_polling_id = sp_reply.smsPollingId
            ques_id = sp_reply.quesId
            question = sp_reply.question or ''

            # Get polling details
            sp_polling = SpSmsPolling.objects.get(iId=sms_polling_id)
            member_id = sp_polling.iUserId

            # Log transaction
            CommonServices.sms_polling_trans_log(
                sms_polling_id, member_id, ques_id, question, user_reply,
                from_fmt, to_fmt, 'N', from_country, from_state,
                from_city, from_zip, '', 'N', 0
            )

            # Update transaction table
            CommonServices.sms_polling_trans_table(
                sms_polling_id, user_reply, sp_polling.vHeading or '',
                to_fmt, from_fmt, member_id, 0
            )

            # Validate and save
            try:
                question_obj = SpQuestions.objects.get(queId=ques_id)
                ques_type = question_obj.queTypeId or 1

                if ques_type in [1, 2]:
                    valid_options = SpOptions.objects.filter(
                        queId=ques_id
                    ).values_list('optionVal', flat=True)

                    if user_reply not in valid_options:
                        error_msg = "Invalid answer. Please try again."
                        try:
                            telnyx_utils.send_sms_telnyx(
                                to_fmt, from_fmt, 'text', error_msg, 1, None,
                                getattr(settings, 'SMS_POLLING_STATUS_URL', ''),
                                getattr(settings, 'TELNYX_BASE_URL', None),
                                getattr(settings, 'TELNYX_API_KEY', None)
                            )
                        except Exception as e:
                            logger.error(f"Error sending error msg: {e}")
                        return

                # Save reply
                sp_reply.userReply = user_reply
                sp_reply.replyDate = timezone.now()
                sp_reply.save()

                # Send completion
                try:
                    telnyx_utils.send_sms_telnyx(
                        to_fmt, from_fmt, 'text', "Thank you for your response!", 1, None,
                        getattr(settings, 'SMS_POLLING_STATUS_URL', ''),
                        getattr(settings, 'TELNYX_BASE_URL', None),
                        getattr(settings, 'TELNYX_API_KEY', None)
                    )
                except Exception as e:
                    logger.error(f"Error sending completion: {e}")

            except Exception as e:
                logger.error(f"Error processing answer: {e}")

        except Exception as e:
            logger.error(f"Error in sms_polling_reply: {e}")

    @staticmethod
    def sms_polling_trans_log(sms_polling_id, member_id, ques_id, question, user_reply,
                              from_no, to_no, member_send, from_country, from_state,
                              from_city, from_zip, msg_contains, question_send, sub_member_id):
        """
        Log SMS polling transaction
        Mirrors Java's: CommonServices.smsPollingTransLog(...)
        Lines: 1699-1734
        """
        try:
            country_setting = CommonServices.country_setting_by_tenant_id(member_id)
            msg_len = len(msg_contains or '')
            sms_cnt = max(1, (msg_len + 159) // 160)
            sms_rate = getattr(country_setting, 'cnty_sms_per_price', 0)
            trans_amt = sms_cnt * sms_rate
            SpTransLog.objects.create(
                smspollingId=sms_polling_id,
                psrTenantId=get_client_id_by_tenant_id(member_id),
                quesId=int(ques_id),
                question=question,
                userReply=user_reply,
                fromNo=from_no,
                toNo=to_no,
                transRate=sms_rate,
                transAmt=trans_amt,
                memberSend=member_send,
                smsDate=timezone.now(),
                fromCountry=from_country,
                fromState=from_state,
                fromCity=from_city,
                fromZip=from_zip,
                msgContains=msg_contains,
                questionSend=question_send,
                tranId=0
            )

        except Exception as e:
            logger.error(f"Error logging polling transaction: {e}")

    @staticmethod
    def sms_polling_trans_table(sms_polling_id, message, campaign_name, to_contact,
                                from_contact, member_id, sub_member_id):
        """
        Update SMS polling transaction table for billing
        Mirrors Java's: CommonServices.smsPollingTransTable(...)
        Lines: 1658-1697
        """
        try:
            sms_cnt = max(1, (len(message) + 159) // 160)
            country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(member_id))
            sms_rate = getattr(country_setting, 'cnty_sms_per_price', 0)
            trans_amt = sms_cnt * sms_rate

            try:
                transaction = CampaignTransaction.objects.get(
                    tran_campaign_id=sms_polling_id,
                    tran_poll_form_no=from_contact,
                    tran_poll_to_no=to_contact
                )
                transaction.tran_total_amount = (transaction.tran_total_amount or 0.0) + trans_amt
                transaction.tran_count_total_sms = (transaction.tran_count_total_sms or 0) + sms_cnt
                transaction.save()
            except CampaignTransaction.DoesNotExist:
                CommonServices.saveCampaignTransaction(
                    sms_polling_id,
                    f"SMS Polling: {campaign_name}",
                    1,
                    'sms polling',
                    None,
                    'uninvoiced',
                    None,
                    member_id,
                    '0',
                    trans_amt,
                    sms_rate,
                    sms_cnt,
                    from_contact,
                    to_contact,
                    sub_member_id
                )

        except Exception as e:
            logger.error(f"Error updating polling transaction: {e}")

# Singleton export mimicking autowired usage
commonServices = CommonServices()
