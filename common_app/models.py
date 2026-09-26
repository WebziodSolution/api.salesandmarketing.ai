from django.db import models
import datetime

class Language(models.Model):
    lg_id = models.BigAutoField(db_column='LG_ID', primary_key=True)
    lg_dis_order = models.BigIntegerField(db_column='LG_DIS_ORDER', null=True, blank=True)
    lg_long_name = models.CharField(db_column='LG_LONG_NAME', max_length=255, null=True, blank=True)
    lg_name = models.CharField(db_column='LG_NAME', max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'LANGUAGES'
        managed = False


class SecurityQuestion(models.Model):
    sec_id = models.BigAutoField(db_column='SEC_ID', primary_key=True)
    sec_question = models.CharField(db_column='SEC_QUESTION', max_length=255)

    class Meta:
        db_table = 'SECURITY_QUESTIONS'
        managed = False


class NumberCallForwarding(models.Model):
    cfnId = models.BigAutoField(db_column='CFN_ID', primary_key=True)
    cfnTwilioNumber = models.CharField(db_column='CFN_PHONE_NUMBER', max_length=255, null=True, blank=True)
    cfnTwilioPhoneSid = models.CharField(db_column='CFN_PHONE_SID', max_length=255, null=True, blank=True)
    cfnForwardingCountryCode = models.CharField(db_column='CFN_FORWARDING_COUNTRY_CODE', max_length=255, null=True, blank=True)
    cfnForwardingNumber = models.CharField(db_column='CFN_FORWARDING_NUMBER', max_length=255, null=True, blank=True)
    cfnMemberId = models.BigIntegerField(db_column='CFN_CLIENT_ID', default=0)
    cfnDateTime = models.DateTimeField(db_column='CFN_DATE_TIME', null=True, blank=True)
    cfnEmbedding = models.JSONField(null=True, blank=True, db_column='CFN_EMBEDDING')

    class Meta:
        db_table = 'CALL_FORWARDING_NUMBER'
        managed = False


class Country(models.Model):
    country_id = models.AutoField(db_column='COUNTRY_ID', primary_key=True)
    cnt_code = models.CharField(db_column='CNT_CODE', max_length=255, null=True, blank=True)
    cnt_name = models.CharField(db_column='CNTNAME', max_length=80)
    iso2 = models.CharField(db_column='ISO2', max_length=2, null=True, blank=True)
    long_name = models.CharField(db_column='LONG_NAME', max_length=80)
    oid = models.IntegerField(db_column='OID', null=True, blank=True)
    phone_min_length = models.IntegerField(db_column='PHONE_MIN_LENGTH', default=0)
    phone_max_length = models.IntegerField(db_column='PHONE_MAX_LENGTH', default=0)
    embedding = models.JSONField(null=True, blank=True, db_column='EMBEDDING')

    class Meta:
        db_table = 'COUNTRY'
        managed = False


class CountryToState(models.Model):
    country_to_state_id = models.BigAutoField(primary_key=True)
    fk_country_id = models.BigIntegerField()
    state_capital = models.CharField(max_length=100, null=True, blank=True)
    state_long = models.CharField(max_length=100, null=True, blank=True)
    state_short = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        db_table = 'country_to_state'
        managed = False

class CountrySetting(models.Model):
    id = models.AutoField(db_column='ID', primary_key=True)
    cnty_id = models.BigIntegerField(db_column='CNTY_ID', null=True, blank=True)
    cnty_iso2 = models.CharField(db_column='CNTY_ISO2', max_length=255, null=True, blank=True)
    cnty_name = models.CharField(db_column='CNTY_NAME', max_length=255, null=True, blank=True)
    cnty_price_symbol = models.CharField(db_column='CNTY_PRICE_SYMBOL', max_length=255, null=True, blank=True)
    cnty_assessment_price = models.FloatField(db_column='CNTY_ASSESSMENT_PRICE', null=True, blank=True)
    cnty_survey_price = models.FloatField(db_column='CNTY_SURVEY_PRICE', null=True, blank=True)
    cnty_individual_price = models.FloatField(db_column='CNTY_INDIVIDUAL_PRICE', null=True, blank=True)
    cnty_social_media_price = models.FloatField(db_column='CNTY_SOCIALMEDIA_PRICE', null=True, blank=True)
    cnty_campaign_per_price = models.FloatField(db_column='CNTY_CAMPAIGN_PER_PRICE', null=True, blank=True)
    cnty_survey_per_price = models.FloatField(db_column='CNTY_SURVEY_PER_PRICE', null=True, blank=True)
    cnty_assessment_per_price = models.FloatField(db_column='CNTY_ASSESSMENT_PER_PRICE', null=True, blank=True)
    cnty_mms_per_price = models.FloatField(db_column='CNTY_MMS_PER_PRICE', null=True, blank=True)
    cnty_sms_per_price = models.FloatField(db_column='CNTY_SMS_PER_PRICE', null=True, blank=True)
    cnty_sms_number_per_price = models.FloatField(db_column='CNTY_SMS_NUMBER_PER_PRICE', null=True, blank=True)
    cnty_first_inv_free_amt = models.FloatField(db_column='CNTY_FIRST_INV_FREE_AMT', null=True, blank=True)
    cnty_inv_less_amt_not_charge = models.FloatField(db_column='CNTY_INV_LESS_AMT_NOT_CHARGE', null=True, blank=True)
    cnty_translate_char_charge = models.FloatField(db_column='CNTY_TRANSLATE_CHAR_CHARGE', null=True, blank=True)
    cnty_sms_conversations_per_price = models.FloatField(db_column='CNTY_SMS_CONVERSATIONS_PER_PRICE', null=True, blank=True)
    cnty_call_per_min_price = models.FloatField(db_column='CNTY_CALL_PERM_IN_PRICE', null=True, blank=True)

    cnty_contacts_included = models.BigIntegerField(db_column='CNTY_CONTACTS_INCLUDED', null=True, blank=True)
    cnty_max_number_of_email = models.BigIntegerField(db_column='CNTY_MAX_NUMBER_OF_EMAIL', null=True, blank=True)
    cnty_plan_id = models.BigIntegerField(db_column='CNTY_PLAN_ID', null=True, blank=True)
    cnty_plan_price = models.FloatField(db_column='CNTY_PLAN_PRICE', null=True, blank=True)

    cnty_support = models.CharField(db_column='CNTY_SUPPORT', max_length=250, null=True, blank=True)
    cnty_multi_user = models.CharField(db_column='CNTY_MULTI_USER', max_length=1, null=True, blank=True)
    cnty_automation = models.CharField(db_column='CNTY_AUTOMATION', max_length=1, null=True, blank=True)
    cnty_white_listing = models.CharField(db_column='CNTY_WHITE_LISTING', max_length=1, null=True, blank=True)
    cnty_calendar = models.CharField(db_column='CNTY_CALENDAR', max_length=1, null=True, blank=True)
    cnty_zoom_conferences = models.CharField(db_column='CNTY_ZOOM_CONFERENCES', max_length=1, null=True, blank=True)
    cnty_social_media = models.CharField(db_column='CNTY_SOCIAL_MEDIA', max_length=1, null=True, blank=True)
    cnty_sms_inbox = models.CharField(db_column='CNTY_SMS_INBOX', max_length=1, null=True, blank=True)
    cnty_ab_testing = models.CharField(db_column='CNTY_AB_TESTING', max_length=1, null=True, blank=True)
    cnty_plan_popular = models.CharField(db_column='CNTY_PLAN_POPULAR', max_length=1, null=True, blank=True)
    cnty_plan_display_order = models.IntegerField(db_column='CNTY_PLAN_DISPLAY_ORDER', null=True, blank=True)

    cnty_form_response = models.FloatField(db_column='CNTY_FORM_RESPONSE', null=True, blank=True)
    cnty_additional_contacts = models.IntegerField(db_column='CNTY_ADDITIONAL_CONTACTS', null=True, blank=True)
    cnty_additional_contacts_price = models.FloatField(db_column='CNTY_ADDITIONAL_CONTACTS_PRICE', null=True, blank=True)

    cnty_10dlc_price = models.FloatField(db_column='CNTY_10DLC_PRICE', null=True, blank=True)
    cnty_10dlc_campaign_type_charge = models.FloatField(db_column='CNTY_10DLC_CAMPAIGN_TYPE_CHARGE', null=True, blank=True)
    cnty_10dlc_other_charge = models.FloatField(db_column='CNTY_10DLC_OTHER_CHARGE', null=True, blank=True)
    cnty_warmup_price = models.FloatField(db_column='CNTY_WARMUP_PRICE', null=True, blank=True)
    ctny_ai_generated_image = models.FloatField(db_column='CTNY_AI_GENERATED_IMAGE', null=True, blank=True)
    ctny_ai_edited_image = models.FloatField(db_column='CTNY_AI_EDITED_IMAGE', null=True, blank=True)
    ctny_contact_per_price = models.FloatField(db_column='CTNY_CONTACT_PER_PRICE', null=True, blank=True)

    class Meta:
        db_table = 'COUNTRY_SETTING'
        managed = False

class BrandKits(models.Model):
    brand_id = models.AutoField(db_column='BRAND_ID', primary_key=True)
    brand_client_id = models.BigIntegerField(db_column='BRAND_CLIENT_ID')
    brand_name = models.CharField(max_length=250, null=True, blank=True, db_column='BRAND_NAME')
    brand_website = models.CharField(max_length=250, null=True, blank=True, db_column='BRAND_WEBSITE')
    brand_logo = models.TextField(null=True, blank=True, db_column='BRAND_LOGO')
    brand_colors = models.TextField(null=True, blank=True, db_column='BRAND_COLORS')
    brand_fonts = models.TextField(null=True, blank=True, db_column='BRAND_FONTS')
    brand_created_date = models.DateTimeField(null=True, blank=True, db_column='BRAND_CREATED_DATE')
    brand_updated_date = models.DateTimeField(null=True, blank=True, db_column='BRAND_UPDATED_DATE')

    class Meta:
        db_table = 'BRAND_KITS'
        managed = False


class Plans(models.Model):
    plan_id = models.AutoField(primary_key=True, db_column='PLAN_ID')
    plan_name = models.CharField(max_length=255, null=True, blank=True, db_column='PLAN_NAME')
    plan_active = models.CharField(max_length=1, null=True, blank=True, db_column='PLAN_ACTIVE')
    plan_visibility = models.CharField(max_length=255, null=True, blank=True, db_column='PLAN_VISIBILITY')
    plan_added_date = models.DateTimeField(null=True, blank=True, db_column='PLAN_ADDED_DATE')
    plan_pm_id_list = models.CharField(max_length=255, null=True, blank=True, db_column='PLAN_PM_ID_LIST')

    class Meta:
        db_table = 'PLANS'
        managed = False

class TenantPlanDetails(models.Model):
    tpd_id = models.BigAutoField(primary_key=True, db_column='TPD_ID')
    tpd_client_id = models.BigIntegerField(db_column='TPD_CLIENT_ID', null=True, blank=True)
    tpd_plan_id = models.BigIntegerField(db_column='TPD_PLAN_ID', null=True, blank=True)
    tpd_additional_contacts = models.IntegerField(db_column='TPF_ADDITIONAL_CONTACTS', null=True, blank=True)
    tpd_added_date = models.DateTimeField(db_column='TPD_ADDED_DATE', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'TENANT_PLAN_DETAILS'


class PlanModule(models.Model):
    pm_id = models.AutoField(db_column='PM_ID', primary_key=True)
    pm_title = models.CharField(db_column='PM_TITLE', max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'PLAN_MODULES'
        managed = False


class SubaccountPage(models.Model):
    sp_id = models.AutoField(db_column='SP_ID', primary_key=True)
    sp_name = models.CharField(db_column='SP_NAME', max_length=255, null=True, blank=True)
    sp_menu_name = models.CharField(db_column='SP_MENU_NAME', max_length=255, null=True, blank=True)
    sp_module_name = models.CharField(db_column='SP_MODULE_NAME', max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'SUBACCOUNT_PAGE'
        managed = False


class WebContentGrab(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='WCG_ID')
    type = models.CharField(max_length=255, db_column='WCG_TYPE', null=True, blank=True)
    request = models.TextField(db_column='WCG_REQUEST', null=True, blank=True)
    is_started = models.IntegerField(db_column='WCG_IS_STARTED', default=0)
    is_processed = models.IntegerField(db_column='WCG_IS_PROCESSED', default=0)
    response = models.TextField(db_column='WCG_RESPONSE', null=True, blank=True)
    error = models.CharField(max_length=250, db_column='WCG_ERROR', null=True, blank=True)
    created_date = models.DateTimeField(db_column='WCG_CREATED_DATE', auto_now_add=True)

    class Meta:
        db_table = 'WEB_CONTENT_GRAB'
        managed = False

class AnalyticsCsv(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='AC_ID')
    member_id = models.BigIntegerField(db_column='AC_CLIENT_ID', null=True, blank=True)
    campaign_id = models.CharField(max_length=255, db_column='AC_CAMPAIGN_ID', null=True, blank=True)
    is_started = models.IntegerField(db_column='AC_IS_STARTED', default=0)
    is_processed = models.IntegerField(db_column='AC_IS_PROCESSED', default=0)
    percent_complete = models.IntegerField(db_column='AC_PERCENT_COMPLETE', default=0)
    csv_url = models.TextField(db_column='AC_CSV_URL', null=True, blank=True)
    created_date = models.DateTimeField(db_column='AC_CREATED_DATE', auto_now_add=True)

    class Meta:
        db_table = 'ANALYTICS_CSV'
        managed = False

class CustomFormReportPdf(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='RFP_ID')
    member_id = models.BigIntegerField(db_column='RFP_CLIENT_ID', null=True, blank=True)
    custom_form_id = models.BigIntegerField(db_column='RFP_CUSTOM_FORM_ID', null=True, blank=True)
    ans_ids = models.CharField(max_length=2000, db_column='RFP_ANS_IDS', null=True, blank=True)
    is_started = models.IntegerField(db_column='RFP_IS_STARTED', default=0)
    is_processed = models.IntegerField(db_column='RFP_IS_PROCESSED', default=0)
    zip_url = models.CharField(max_length=2000, db_column='RFP_ZIP_URL', null=True, blank=True)
    created_date = models.DateTimeField(db_column='RFP_CREATED_DATE', auto_now_add=True)
    rfpEmbedding = models.JSONField(null=True, blank=True, db_column='RFP_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_REPORT_PDF'
        managed = False

class SubaccountPagePermission(models.Model):
    spp_id = models.AutoField(db_column='SPP_ID', primary_key=True)
    spp_pg_id = models.BigIntegerField(db_column='SPP_PG_ID', null=True, blank=True)
    spp_action_name = models.CharField(db_column='SPP_ACTION_NAME', max_length=255, null=True, blank=True)
    spp_sub_id = models.BigIntegerField(db_column='SPP_SUB_ID', null=True, blank=True)
    spp_client_id = models.BigIntegerField(db_column='SPP_CLIENT_ID', null=True, blank=True)

    class Meta:
        db_table = 'SUBACCOUNT_PAGE_PERMISSION'
        managed = False

class TenDLCLogs(models.Model):
    dlc_id = models.BigAutoField(primary_key=True, db_column='TDL_ID')
    member_id = models.BigIntegerField(db_column='TDL_CLIENT_ID', null=True, blank=True)
    dlc_status = models.CharField(max_length=255, db_column='TDL_STATUS', null=True, blank=True)
    dlc_date = models.DateTimeField(db_column='TDL_DATE', null=True, blank=True)
    tdl_embedding = models.JSONField(null=True, blank=True, db_column='TDL_EMBEDDING')

    class Meta:
        db_table = 'TEN_DLC_LOGS'
        managed = False


class TenDLCRenew(models.Model):
    rnw_id = models.BigAutoField(primary_key=True, db_column='TDR_ID')
    rnw_member_id = models.BigIntegerField(db_column='TDR_CLIENT_ID', null=True, blank=True)
    rnw_continue = models.CharField(max_length=255, db_column='TDR_CONTINUE', null=True, blank=True)
    rnw_date = models.DateField(db_column='TDR_DATE', null=True, blank=True)

    class Meta:
        db_table = 'TEN_DLC_RENEW'
        managed = False


class TenDLCData(models.Model):
    dat_id = models.BigAutoField(primary_key=True, db_column='TDC_ID')
    dat_member_id = models.BigIntegerField(db_column='TDC_CLIENT_ID', null=True, blank=True)
    dat_brand_name = models.CharField(max_length=255, db_column='TDC_BRAND_NAME', null=True, blank=True)
    dat_campaign_type = models.CharField(max_length=255, db_column='TDC_CAMPAIGN_TYPE', null=True, blank=True)
    dat_is_active = models.CharField(max_length=255, db_column='TDC_IS_ACTIVE', null=True, blank=True)
    dat_registration_date = models.DateField(db_column='TDC_REGISTRATION_DATE', null=True, blank=True)
    tdc_embedding = models.JSONField(null=True, blank=True, db_column='TDC_EMBEDDING')

    class Meta:
        db_table = 'TEN_DLC_DATA'
        managed = False


class AffiliateProgram(models.Model):
    aff_pid = models.BigAutoField(primary_key=True, db_column='AFF_PID')
    aff_ptitle = models.CharField(max_length=255, db_column='AFF_PTITLE', null=True, blank=True)
    aff_pcode = models.CharField(max_length=255, db_column='AFF_PCODE', null=True, blank=True)
    aff_pcommission_type = models.IntegerField(db_column='AFF_PCOMMISSION_TYPE', default=1)
    aff_pcommission = models.DecimalField(max_digits=10, decimal_places=2, db_column='AFF_PCOMMISSION', null=True, blank=True)
    aff_pdiscount = models.DecimalField(max_digits=10, decimal_places=2, db_column='AFF_PDISCOUNT', null=True, blank=True)
    aff_pcommission_end_date = models.DateTimeField(db_column='AFF_PCOMMISSION_END_DATE', null=True, blank=True)
    aff_pdiscount_end_date = models.DateTimeField(db_column='AFF_PDISCOUNT_END_DATE', null=True, blank=True)
    aff_pwaive_setup_fees = models.CharField(max_length=255, db_column='AFF_PWAIVE_SETUP_FEES', null=True, blank=True)
    aff_pis_active = models.CharField(max_length=255, db_column='AFF_PIS_ACTIVE', default='N', null=True, blank=True)
    aff_pis_public = models.CharField(max_length=255, db_column='AFF_PIS_PUBLIC', default='N', null=True, blank=True)

    class Meta:
        db_table = 'AFFILIATE_PROGRAM'
        managed = False


class AffiliateCommissionSchedule(models.Model):
    aff_cid = models.BigAutoField(primary_key=True, db_column='AFF_CID')
    aff_cpid = models.BigIntegerField(db_column='AFF_CPID', default=0, null=True, blank=True)
    aff_c_tenant_id = models.BigIntegerField(db_column='AFF_C_TENANT_ID', default=0, null=True, blank=True)
    aff_c_referred_tenant_id = models.BigIntegerField(db_column='AFF_C_REFERRED_TENANT_ID', default=0, null=True, blank=True)
    aff_c_invoice_id = models.BigIntegerField(db_column='AFF_C_INVOICE_ID', null=True, blank=True)
    aff_c_invoice_date = models.DateTimeField(db_column='AFF_C_INVOICE_DATE', null=True, blank=True)
    aff_commission_amount = models.FloatField(db_column='AFF_COMMISSION_AMOUNT', null=True, blank=True)
    aff_amount_paid = models.FloatField(db_column='AFF_AMOUNT_PAID', null=True, blank=True)
    aff_date_paid = models.DateTimeField(db_column='AFF_DATE_PAID', null=True, blank=True)
    aff_title = models.CharField(max_length=255, db_column='AFF_TITLE', null=True, blank=True)
    aff_commission_type = models.IntegerField(db_column='AFF_COMMISSION_TYPE', default=1, null=True, blank=True)
    aff_plan_id = models.BigIntegerField(db_column='AFF_PLAN_ID', default=0, null=True, blank=True)
    aff_status = models.CharField(max_length=255, db_column='AFF_STATUS', null=True, blank=True)

    class Meta:
        db_table = 'AFFILIATE_COMMISSION_SCHEDULE'
        managed = False


class CampaignTransaction(models.Model):
    tran_id = models.BigAutoField(primary_key=True, db_column='CT_TRANS_ID')
    tran_campaign_id = models.BigIntegerField(db_column='CT_TRAN_CAMPAIGN_ID', null=True, blank=True)
    tran_campaign_name = models.CharField(max_length=255, db_column='CT_TRAN_CAMPAIGN_NAME', null=True, blank=True)
    tran_campaign_date = models.DateField(db_column='CT_TRAN_CAMPAIGN_DATE', null=True, blank=True)
    tran_total_member = models.BigIntegerField(db_column='CT_TRAN_TOTAL_MEMBER', null=True, blank=True)
    tran_type = models.CharField(max_length=255, db_column='CT_TRAN_TYPE', null=True, blank=True)
    tran_invoiced_id = models.BigIntegerField(db_column='CT_TRAN_INVOICED_ID', null=True, blank=True)
    tran_invoiced_status = models.CharField(max_length=255, db_column='CT_TRAN_INVOICED_STATUS', null=True, blank=True)
    tran_invoiced_date = models.DateField(db_column='CT_TRAN_INVOICED_DATE', null=True, blank=True)
    ct_client_id = models.BigIntegerField(db_column='CT_CLIENT_ID', null=True, blank=True)
    tran_bill_type = models.CharField(max_length=255, db_column='CT_TRAN_BILL_TYPE', default='0', null=True, blank=True)
    tran_total_amount = models.FloatField(db_column='CT_TRAN_TOTAL_AMOUNT', null=True, blank=True)
    tran_member_rate = models.FloatField(db_column='CT_TRAN_MEMBER_RATE', null=True, blank=True)
    tran_count_total_sms = models.BigIntegerField(db_column='CT_TRAN_COUNT_TOTAL_SMS', null=True, blank=True)
    tran_poll_form_no = models.CharField(max_length=255, db_column='CT_TRAN_POLL_FORM_NO', null=True, blank=True)
    tran_poll_to_no = models.CharField(max_length=255, db_column='CT_TRAN_POLL_TO_NO', null=True, blank=True)
    sub_member_id = models.BigIntegerField(db_column='SUB_MEMBER_ID', default=0, null=True, blank=True)
    ct_embedding = models.JSONField(null=True, blank=True, db_column='CT_TRANS_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_BILLING'
        managed = False

class EasBuildItForMe(models.Model):
    bfmId = models.AutoField(primary_key=True, db_column='IFM_ID')
    memberId = models.BigIntegerField(db_column='IFM_CLIENT_ID')
    bfmProjectName = models.CharField(max_length=255, db_column='IFM_PROJECT_NAME', null=True, blank=True)
    bfmWebsite = models.CharField(max_length=255, db_column='IFM_WEBSITE', null=True, blank=True)
    bfmYourBusiness = models.CharField(max_length=255, db_column='IFM_YOUR_BUSINESS', null=True, blank=True)
    bfmPlatformInMind = models.CharField(max_length=255, db_column='IFM_PLATFORM_IN_MIND', null=True, blank=True)
    bfmEmailPackId = models.IntegerField(db_column='IFM_EMAIL_PACK_ID', null=True, blank=True)
    bfmEmailPackAmount = models.CharField(max_length=255, db_column='IFM_EMAIL_PACK_AMOUNT', null=True, blank=True)
    bfmPublishStatus = models.IntegerField(db_column='IIM_PUBLISH_STATUS', null=True, blank=True)
    bfmInvoicedId = models.CharField(max_length=255, db_column='IFM_INVOICED_ID', null=True, blank=True)
    bfmCreatedate = models.DateField(db_column='IFM_CREATE_DATE', null=True, blank=True)
    bfmMpId = models.BigIntegerField(db_column='IFM_MP_ID', null=True, blank=True)
    bfmDesignerName = models.CharField(max_length=255, db_column='IFM_DESIGNER_NAME', null=True, blank=True)
    bfmDesignerEmail = models.CharField(max_length=255, db_column='IFM_DESIGNER_EMAIL', null=True, blank=True)
    bfmAboutYourCompany = models.TextField(db_column='IFM_ABOUT_YOUR_COMPANY', null=True, blank=True)
    bfmMainGoalWithEt = models.TextField(db_column='IFM_MAIN_GOAL_WITH_ET', null=True, blank=True)
    bfmWantIncluded = models.TextField(db_column='IFM_WANT_INCLUDED', null=True, blank=True)
    bfmCommunicateToTeam = models.TextField(db_column='IFM_COMMUNICATE_TO_TEAM', null=True, blank=True)
    bfmNotWantIncluded = models.TextField(db_column='IFM_NOT_WANT_INCLUDED', null=True, blank=True)
    bfmAttachmentFile = models.TextField(db_column='IFM_ATTACHMENT_FILE', null=True, blank=True)

    class Meta:
        db_table = 'BUILD_IT_FOR_ME'
        managed = False


class EasBuildItForMePackage(models.Model):
    bfmpId = models.AutoField(primary_key=True, db_column='FMP_ID')
    bfmpLable = models.CharField(max_length=255, db_column='FMP_LABEL', null=True, blank=True)
    bfmpAmount = models.CharField(max_length=255, db_column='FMP_AMOUNT', null=True, blank=True)
    bfmpActive = models.CharField(max_length=1, db_column='FMP_ACTIVE', null=True, blank=True)
    bfmpText = models.TextField(db_column='FMP_TEXT', null=True, blank=True)

    class Meta:
        db_table = 'BUILD_IT_FOR_ME_PACKAGES'
        managed = False


class EasBuildItForMePackData(models.Model):
    bfmpdId = models.BigAutoField(primary_key=True, db_column='MPD_ID')
    bfmpdBfmId = models.BigIntegerField(db_column='MPD_BFM_ID', null=True, blank=True)
    bfmpdMpId = models.BigIntegerField(db_column='MPD_MP_ID', null=True, blank=True)
    bfmpdMpName = models.CharField(max_length=255, db_column='MPD_NAME', null=True, blank=True)
    bfmpdMpStatus = models.IntegerField(db_column='MPD_STATUS', null=True, blank=True)
    bfmpdDate = models.DateTimeField(db_column='MLT_TYPE', null=True, blank=True)

    class Meta:
        db_table = 'BUILD_IT_FOR_ME_PACKAGE_DETAILS'
        managed = False


class EasBuildItForMeLog(models.Model):
    blogId = models.BigAutoField(primary_key=True, db_column='FML_ID')
    blogBfmId = models.BigIntegerField(db_column='FML_BFM_ID', null=True, blank=True)
    blogBfmProjectName = models.CharField(max_length=255, db_column='FML_PROJECT_NAME', null=True, blank=True)
    blogBfmpdId = models.BigIntegerField(db_column='FML_BFMPD_ID', null=True, blank=True)
    blogAction = models.CharField(max_length=255, db_column='FML_BLOGT_ID', null=True, blank=True)
    blogBlogtId = models.BigIntegerField(db_column='BLOG_BLOGT_ID', null=True, blank=True)
    blogDate = models.DateTimeField(db_column='FML_DATE', null=True, blank=True)
    blogNotes = models.TextField(db_column='FML_NOTES', null=True, blank=True)

    class Meta:
        db_table = 'BUILD_IT_FOR_ME_LOG'
        managed = False


class EasBuildItForMeLogType(models.Model):
    blogtId = models.BigAutoField(primary_key=True, db_column='MLT_ID')
    blogtType = models.CharField(max_length=255, db_column='MLT_TYPE')

    class Meta:
        db_table = 'BUILD_IT_FOR_ME_LOG_TYPE'
        managed = False


class MyPages(models.Model):
    mpId = models.BigAutoField(primary_key=True, db_column='MP_ID')
    mpName = models.CharField(max_length=255, db_column='MP_NAME', null=True, blank=True)
    mpTags = models.TextField(db_column='MP_TAGS', null=True, blank=True)
    mpType = models.IntegerField(db_column='MP_TYPE', null=True, blank=True)
    mpStage = models.IntegerField(db_column='MP_STAGE', null=True, blank=True)
    mpGroupId = models.BigIntegerField(db_column='MP_GROUP_ID', null=True, blank=True)
    mpClientId = models.BigIntegerField(db_column='MP_CLIENT_ID', null=True, blank=True)
    mpTemplateLanguage = models.CharField(max_length=255, db_column='MP_TEMPLATE_LANGUAGE', null=True, blank=True)
    mpTemplateConvertLangList = models.TextField(db_column='MP_TEMPLATE_CONVERT_LANG_LIST', null=True, blank=True)
    mpAllowConvertLang = models.CharField(max_length=3, db_column='MP_ALLOW_CONVERT_LANG', default="N")
    mpBuilditPublish = models.CharField(max_length=1, db_column='MP_BUILDIT_PUBLISH', default="Y")
    mpPublicUrl = models.CharField(max_length=1, db_column='MP_PUBLIC_URL', default="N")
    mpDetails = models.TextField(db_column='MP_DETAILS', null=True, blank=True)
    mpEmbedding = models.JSONField(null=True, blank=True, db_column='MP_EMBEDDING')

    class Meta:
        db_table = 'MYPAGES'
        managed = False


class Invoices(models.Model):
    invId = models.BigAutoField(primary_key=True, db_column='INV_ID')
    invNo = models.BigIntegerField(db_column='INV_NO', default=0)
    invAdjustmentsAmount = models.FloatField(db_column='INV_ADJUSTMENTS_AMOUNT', default=0)
    invAssessmentAmount = models.FloatField(db_column='INV_ASSESSMENT_AMOUNT', default=0)
    invAssessmentPrice = models.FloatField(db_column='INV_ASSESSMENT_PRICE', default=0)
    invBuildItForMeAmount = models.FloatField(db_column='INV_BUILD_IT_FOR_ME_AMOUNT', default=0)
    invBuildItForMePrice = models.FloatField(db_column='INV_BUILD_IT_FOR_ME_PRICE', default=0)
    invCallAmount = models.FloatField(db_column='INV_CALL_AMOUNT', default=0)
    invCallPrice = models.FloatField(db_column='INV_CALL_PRICE', default=0)
    invCampaignAmount = models.FloatField(db_column='INV_CAMPAIGN_AMOUNT', default=0)
    invCampaignPrice = models.FloatField(db_column='INV_CAMPAIGN_PRICE', default=0)
    invClientName = models.CharField(max_length=255, db_column='INV_CLIENT_NAME', null=True, blank=True)
    invCountryId = models.BigIntegerField(db_column='INV_COUNTRY_ID', default=100)
    invCurrentContacts = models.BigIntegerField(db_column='INV_CURRENT_CONTACTS', default=0)
    invDate = models.DateField(db_column='INV_DATE', null=True, blank=True)
    invIndividualAmount = models.FloatField(db_column='INV_INDIVIDUAL_AMOUNT', default=0)
    invIndividualPrice = models.FloatField(db_column='INV_INDIVIDUAL_PRICE', default=0)
    invMonthlyEmailAmount = models.FloatField(db_column='INV_MONTHLY_EMAIL_AMOUNT', default=0)
    invMonthlyIndividualAmount = models.FloatField(db_column='INV_MONTHLY_INDIVIDUAL_AMOUNT', default=0)
    invMonthlySmsAmount = models.FloatField(db_column='INV_MONTHLY_SMS_AMOUNT', default=0)
    invMonthlySocialMediaAmount = models.FloatField(db_column='INV_MONTHLY_SOCIAL_MEDIA_AMOUNT', default=0)
    invMonthlySurveyAmount = models.FloatField(db_column='INV_MONTHLY_SURVEY_AMOUNT', default=0)
    invMonthlyYN = models.CharField(max_length=1, db_column='INV_MONTHLY_YN', default="N")
    invPageTransAmount = models.FloatField(db_column='INV_PAGE_TRANS_AMOUNT', default=0)
    invPageTransPrice = models.FloatField(db_column='INV_PAGE_TRANS_PRICE', default=0)
    invPayCardNo = models.CharField(max_length=255, db_column='INV_PAY_CARDNO', null=True, blank=True)
    invSendMail = models.CharField(max_length=1, db_column='INV_SEND_MAIL', null=True, blank=True)
    invSmsAmount = models.FloatField(db_column='INV_SMS_AMOUNT', default=0)
    invSMSConversationsAmount = models.FloatField(db_column='INV_SMS_CONVERSATIONS_AMOUNT', default=0)
    invSMSConversationsPrice = models.FloatField(db_column='INV_SMS_CONVERSATIONS_PRICE', default=0)
    invSmsPollAmount = models.FloatField(db_column='INV_SMS_POLL_AMOUNT', default=0)
    invSmsPollPrice = models.FloatField(db_column='INV_SMS_POLL_PRICE', default=0)
    invSmsPrice = models.FloatField(db_column='INV_SMS_PRICE', default=0)
    invSocialMediaAmount = models.FloatField(db_column='INV_SOCIAL_MEDIA_AMOUNT', default=0)
    invSocialMediaPrice = models.FloatField(db_column='INV_SOCIAL_MEDIA_PRICE', default=0)
    invSubTotal = models.FloatField(db_column='INV_SUBTOTAL', default=0)
    invSurveyAmount = models.FloatField(db_column='INV_SURVEY_AMOUNT', default=0)
    invSurveyPrice = models.FloatField(db_column='INV_SURVEY_PRICE', default=0)
    invTotalAmount = models.FloatField(db_column='INV_TOTAL_AMOUNT', default=0)
    invTransationId = models.CharField(max_length=500, db_column='INV_TRANSATION_ID', null=True, blank=True)
    invTenantId = models.BigIntegerField(db_column='INV_CLIENT_ID', default=0)
    invPlanId = models.BigIntegerField(db_column='INV_PLAN_ID', default=0)
    invPlanName = models.CharField(max_length=255, db_column='INV_PLAN_NAME', null=True, blank=True)
    invPlanPrice = models.FloatField(db_column='INV_PLAN_PRICE', default=0)
    invShareAppointmentAmount = models.FloatField(db_column='INV_SHARE_APPOINTMENT_AMOUNT', default=0)
    invSmsCalendarAmount = models.FloatField(db_column='INV_SMS_CALENDAR_AMOUNT', default=0)
    invShareAppointmentPrice = models.FloatField(db_column='INV_SHARE_APPOINTMENT_PRICE', default=0)
    invSmsCalendarPrice = models.FloatField(db_column='INV_SMS_CALENDAR_PRICE', default=0)
    invAdditionalContactsAmount = models.FloatField(db_column='INV_ADDITIONAL_CONTACTS_AMOUNT', default=0)
    invAdditionalContactsPrice = models.FloatField(db_column='INV_ADDITIONAL_CONTACTS_PRICE', default=0)
    inv10DLCAmount = models.FloatField(db_column='INV_10DLC_AMOUNT', default=0)
    invWarmupAmount = models.FloatField(db_column='INV_WARMUP_AMOUNT', default=0)
    invEmailVerificationAmount = models.FloatField(db_column='INV_EMAIL_VERIFICATION_AMOUNT', default=0)
    invEmailVerificationPrice = models.FloatField(db_column='INV_EMAIL_VERIFICATION_PRICE', default=0)
    invSmsCalendarReminderAmount = models.FloatField(db_column='INV_SMS_CALENDAR_REMINDER_AMOUNT', default=0)
    invSmsCalendarReminderPrice = models.FloatField(db_column='INV_SMS_CALENDAR_REMINDER_PRICE', default=0)
    invPreviousUninvoicedAmount = models.FloatField(db_column='INV_PREVIOUS_UNINVOICED_AMOUNT', default=0)
    invPreviousUninvoicedPrice = models.FloatField(db_column='INV_PREVIOUS_UNINVOICED_PRICE', default=0)
    invAiAmount = models.FloatField(db_column='INV_AI_AMOUNT', default=0)
    invAiPrice = models.FloatField(db_column='INV_AI_PRICE', default=0)
    invPerContactPrice = models.FloatField(db_column='INV_PER_CONTACT_PRICE', default=0)

    class Meta:
        db_table = 'INVOICES'
        managed = False

class CustomForm(models.Model):
    cfId = models.BigAutoField(primary_key=True, db_column='CF_ID')
    memberId = models.BigIntegerField(db_column='CF_CLIENT_ID')
    cfFormName = models.CharField(max_length=255, db_column='CF_FORM_NAME')
    cfFormMetaKeyWord = models.CharField(max_length=2000, db_column='CF_FORM_META_KEY_WORD', null=True, blank=True)
    cfFormMetaDescription = models.CharField(max_length=2000, db_column='CF_FORM_META_DESCRIPTION', null=True, blank=True)
    cfFormData = models.TextField(db_column='CF_FORM_DATA', null=True, blank=True)
    cfFormStatus = models.IntegerField(db_column='CF_FORM_STATUS', null=True, blank=True)
    cfCreateDate = models.DateField(db_column='CF_CREATE_DATE', null=True, blank=True)
    cfUpdateDate = models.DateField(db_column='CF_UPDATE_DATE', null=True, blank=True)
    cfSendNotificationEmail = models.CharField(max_length=255, db_column='CF_SEND_NOTIFICATION_EMAIL', null=True, blank=True)
    cfFormHtml = models.TextField(db_column='CF_FORM_HTML', null=True, blank=True)
    cfSendNotificationConfirmation = models.CharField(max_length=1, db_column='CF_SEND_NOTIFICATION_CONFIRMATION', default='N')
    cfFormType = models.CharField(max_length=255, db_column='CF_FORM_TYPE', null=True, blank=True)
    cfFormToGroupYN = models.CharField(max_length=3, db_column='CF_FORM_TO_GROUP_YN', default='No')
    cfGroupId = models.BigIntegerField(db_column='CF_GROUP_ID', default=0)
    cfMapping = models.TextField(db_column='CF_MAPPING', null=True, blank=True)
    cfEmbedding = models.JSONField(null=True, blank=True, db_column='CF_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM'
        managed = False


class CustomFormPages(models.Model):
    pageId = models.BigAutoField(primary_key=True, db_column='CFP_ID')
    pageCfId = models.BigIntegerField(db_column='CFP_CF_ID', default=0)
    pageNumber = models.BigIntegerField(db_column='CFP_NUMBER', default=0)
    pageType = models.CharField(max_length=25, db_column='CFP_TYPE', null=True, blank=True)
    cfpEmbedding = models.JSONField(null=True, blank=True, db_column='CFP_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_PAGES'
        managed = False


class CustomFormQuestions(models.Model):
    queId = models.BigAutoField(primary_key=True, db_column='CFQ_CFP_ID')
    quePageId = models.BigIntegerField(db_column='CFQ_PAGE_ID', default=0)
    queType = models.CharField(max_length=25, db_column='CFQ_TYPE', null=True, blank=True)
    queQuestion = models.CharField(max_length=2000, db_column='CFQ_QUESTION', null=True, blank=True)
    queDisplayOrder = models.BigIntegerField(db_column='CFQ_DISPLAY_ORDER', default=0)
    cfqEmbedding = models.JSONField(null=True, blank=True, db_column='CFQ_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_QUESTIONS'
        managed = False


class CustomFormOptions(models.Model):
    optId = models.BigAutoField(primary_key=True, db_column='CFO_ID')
    optQueId = models.BigIntegerField(db_column='CFO_QUE_ID', default=0)
    optValue = models.CharField(max_length=250, db_column='CFO_VALUE', null=True, blank=True)
    optDescription = models.CharField(max_length=2000, db_column='CFO_DESCRIPTION', null=True, blank=True)
    optDisplayOrder = models.BigIntegerField(db_column='CFO_DISPLAY_ORDER', default=0)
    optHasCommnets = models.IntegerField(db_column='CFO_HAS_COMMENTS', null=True, blank=True)
    cfoEmbedding = models.JSONField(null=True, blank=True, db_column='CFO_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_OPTIONS'
        managed = False


class CustomFormOptionsColumns(models.Model):
    optId = models.BigAutoField(primary_key=True, db_column='FOC_ID')
    optQueId = models.BigIntegerField(db_column='FOC_QUE_ID', default=0)
    optValue = models.CharField(max_length=2000, db_column='FOC_VALUE', null=True, blank=True)
    optDisplayOrder = models.BigIntegerField(db_column='FOC_DISPLAY_ORDER', default=0)
    focEmbedding = models.JSONField(null=True, blank=True, db_column='FOC_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_OPTIONS_COLUMNS'
        managed = False


class CustomFormStatistics(models.Model):
    stId = models.BigAutoField(primary_key=True, db_column='CFS_ID')
    stCfId = models.BigIntegerField(db_column='CFS_CF_ID', default=0)
    stQueComplete = models.BigIntegerField(db_column='CFS_QUE_COMPLETE', default=0)
    stIsComplete = models.BigIntegerField(db_column='CFS_IS_COMPLETE', default=0)
    stSessionId = models.CharField(max_length=255, db_column='CFS_SESSION_ID', null=True, blank=True)
    stIpAddress = models.CharField(max_length=255, db_column='CFS_IP_ADDRESS', null=True, blank=True)
    stDate = models.DateTimeField(db_column='CFS_DATE')
    stCity = models.CharField(max_length=255, db_column='CFS_CITY', null=True, blank=True)
    stState = models.CharField(max_length=255, db_column='CFS_STATE', null=True, blank=True)
    stCountry = models.CharField(max_length=255, db_column='CFS_COUNTRY', null=True, blank=True)
    stTechnology = models.CharField(max_length=255, db_column='CFS_TECHNOLOGY', null=True, blank=True)
    stSources = models.CharField(max_length=255, db_column='CFS_SOURCES', null=True, blank=True)
    cfsEmbedding = models.JSONField(null=True, blank=True, db_column='CFS_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_STATISTICS'
        managed = False


class CustomFormAnswers(models.Model):
    ansId = models.BigAutoField(primary_key=True, db_column='CFA_ANS_ID')
    ansStId = models.BigIntegerField(db_column='CFA_ANS_ST_ID', default=0)
    ansPageId = models.BigIntegerField(db_column='CFA_ANS_PAGE_ID', default=0)
    ansQueId = models.BigIntegerField(db_column='CFA_ANS_QUE_ID', default=0)
    ansAnswers = models.TextField(db_column='CFA_ANS_ANSWERS', null=True, blank=True)
    ansComments = models.TextField(db_column='CFA_ANS_COMMENTS', null=True, blank=True)
    cfaEmbedding = models.JSONField(null=True, blank=True, db_column='CFA_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_ANSWERS'
        managed = False


class CustomFormToGroups(models.Model):
    ftgId = models.BigAutoField(primary_key=True, db_column='FTG_ID')
    ftgCfId = models.BigIntegerField(db_column='FTG_CF_ID', default=0)
    ftgField = models.CharField(max_length=250, db_column='FTG_FIELD', null=True, blank=True)
    ftgValue = models.BigIntegerField(db_column='FTG_VALUE', default=0)
    ftgGroupId = models.BigIntegerField(db_column='FTG_GROUP_ID', default=0)
    ftgEmbedding = models.JSONField(null=True, blank=True, db_column='FTG_EMBEDDING')

    class Meta:
        db_table = 'CUSTOM_FORM_TO_GROUPS'
        managed = False


class Surveys(models.Model):
    sryId = models.BigAutoField(primary_key=True, db_column='SUR_ID')
    sryName = models.CharField(max_length=255, null=True, blank=True, db_column='SUR_NAME')
    sryDescription = models.CharField(max_length=250, null=True, blank=True, db_column='SUR_DESCRIPTION')
    sryData = models.TextField(null=True, blank=True, db_column='SUR_DATA')
    sryStCategoryPageList = models.TextField(null=True, blank=True, db_column='SUR_CATEGORY_PAGE_LIST')
    sryCountryList = models.TextField(null=True, blank=True, db_column='SUR_COUNTRY_LIST')
    sryStatus = models.IntegerField(default=0, db_column='SUR_STATUS')
    sryStId = models.BigIntegerField(null=True, blank=True, db_column='SUR_ST_ID')
    sryStTotalQuestions = models.IntegerField(default=0, db_column='SUR_TOTAL_QUESTIONS')
    memberId = models.BigIntegerField(null=True, blank=True, db_column='SUR_CLIENT_ID')
    sryCreatedDate = models.DateField(db_column='SUR_CREATED_DATE', null=True, blank=True)
    sryUpdateDate = models.DateField(db_column='SUR_UPDATE_DATE', null=True, blank=True)
    surEmbedding = models.JSONField(db_column='SUR_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'SURVEYS'
        managed = False

class Userlist(models.Model):
    emailId = models.BigAutoField(db_column='UL_EMAIL_ID', primary_key=True)
    memberId = models.BigIntegerField(db_column='UL_CLIENT_ID', null=True, blank=True)
    firstName = models.CharField(db_column='UL_FIRST_NAME', max_length=250, null=True, blank=True)
    lastName = models.CharField(db_column='UL_LAST_NAME', max_length=250, null=True, blank=True)
    email = models.CharField(db_column='UL_EMAIL', max_length=500, null=True, blank=True)
    udf1 = models.CharField(db_column='UL_UDF1', max_length=250, null=True, blank=True)
    udf2 = models.CharField(db_column='UL_UDF2', max_length=250, null=True, blank=True)
    udf3 = models.CharField(db_column='UL_UDF3', max_length=250, null=True, blank=True)
    udf4 = models.CharField(db_column='UL_UDF4', max_length=250, null=True, blank=True)
    udf5 = models.CharField(db_column='UL_UDF5', max_length=250, null=True, blank=True)
    udf6 = models.CharField(db_column='UL_UDF6', max_length=250, null=True, blank=True)
    udf7 = models.CharField(db_column='UL_UDF7', max_length=250, null=True, blank=True)
    udf8 = models.CharField(db_column='UL_UDF8', max_length=250, null=True, blank=True)
    udf9 = models.CharField(db_column='UL_UDF9', max_length=250, null=True, blank=True)
    udf10 = models.CharField(db_column='UL_UDF10', max_length=250, null=True, blank=True)
    status = models.CharField(db_column='UL_STATUS', max_length=250, null=True, blank=True)
    badEmail = models.CharField(db_column='UL_BAD_EMAIL', max_length=1, null=True, blank=True)
    optId = models.IntegerField(db_column='UL_OPT_ID', null=True, blank=True)
    bounceReason = models.CharField(db_column='UL_BOUNCE_REASON', max_length=500, null=True, blank=True)
    tempCronId = models.BigIntegerField(db_column='UL_TEMP_CRON_ID', null=True, blank=True)
    smsStatus = models.CharField(db_column='UL_SMS_STATUS', max_length=255, null=True, blank=True)
    smsSid = models.CharField(db_column='UL_SMS_ID', max_length=255, null=True, blank=True)
    streetAddress1 = models.CharField(db_column='UL_STREET_ADDRESS1', max_length=250, null=True, blank=True)
    streetAddress2 = models.CharField(db_column='UL_STREET_ADDRESS2', max_length=250, null=True, blank=True)
    fullName = models.CharField(db_column='UL_FULL_NAME', max_length=500, null=True, blank=True)
    phone = models.CharField(db_column='UL_PHONE', max_length=255, null=True, blank=True)
    city = models.CharField(db_column='UL_CITY', max_length=255, null=True, blank=True)
    stateProvRegion = models.CharField(db_column='UL_STATE_PROV_REGION', max_length=255, null=True, blank=True)
    zipPostalCode = models.CharField(db_column='UL_ZIP_POSTAL_CODE', max_length=255, null=True, blank=True)
    country = models.CharField(db_column='UL_COUNTRY', max_length=255, null=True, blank=True)
    birthday = models.CharField(db_column='UL_BIRTHDAY', max_length=255, null=True, blank=True)
    gender = models.CharField(db_column='UL_GENDER', max_length=255, null=True, blank=True)
    tags = models.CharField(db_column='UL_TAGS', max_length=250, null=True, blank=True)
    phoneNumber = models.CharField(db_column='UL_PHONE_NUMBER', max_length=255, null=True, blank=True)
    emailDomain = models.CharField(db_column='UL_EMAIL_DOMAIN', max_length=50, null=True, blank=True)
    badPhoneNumber = models.CharField(db_column='UL_BAD_PHONE_NUMBER', max_length=1, null=True, blank=True)
    usDefaultLanguage = models.CharField(db_column='UL_US_DEFAULT_LANGUAGE', max_length=255, null=True, blank=True)
    isEmailValidate = models.CharField(db_column='UL_IS_EMAIL_VALIDATE', max_length=255, null=True, blank=True)
    dateRegistered = models.DateTimeField(db_column='UL_DATE_REGISTERED', auto_now_add=True)
    optDate = models.DateTimeField(db_column='UL_OPT_DATE', null=True, blank=True)
    optBackInDate = models.DateTimeField(db_column='UL_OPT_BACK_IN_DATE', null=True, blank=True)
    optOutDate = models.DateTimeField(db_column='UL_OPT_OUT_DATE', null=True, blank=True)
    dateAdded = models.DateTimeField(db_column='UL_DATE_ADDED', auto_now_add=True)
    dateLastModified = models.DateTimeField(db_column='UL_DATE_LAST_MODIFIED', auto_now=True)
    groupId = models.BigIntegerField(db_column='UL_GROUP_ID', default=0)
    typeEmail = models.CharField(db_column='UL_TYPE_EMAIL', max_length=255, null=True, blank=True)
    typeSms = models.CharField(db_column='UL_TYPE_SMS', max_length=255, null=True, blank=True)
    sendToEmailVerification = models.CharField(db_column='UL_SEND_TO_EMAIL_VERIFICATION', max_length=255, default='No')
    smtpHost = models.CharField(db_column='UL_SMTP_HOST', max_length=255, null=True, blank=True)
    emailVerificationStatus = models.CharField(db_column='UL_EMAIL_VERIFICATION_STATUS', max_length=255, null=True, blank=True)
    evId = models.BigIntegerField(db_column='UL_EV_ID', null=True, blank=True)
    ulEmbedding = models.JSONField(null=True, blank=True, db_column='UL_EMBEDDING')

    class Meta:
        db_table = 'USER_LIST'
        managed = False

class SpSmsPolling(models.Model):
    iId = models.BigAutoField(primary_key=True, db_column='PS_ID')
    iUserId = models.BigIntegerField(db_column='PS_CLIENT_ID', null=True, blank=True)
    vHeading = models.CharField(max_length=255, db_column='PS_VHEADING', null=True, blank=True)
    tDetail = models.CharField(max_length=250, db_column='PS_TDETAIL', null=True, blank=True)
    noOfQuestions = models.IntegerField(db_column='PS_NO_OF_QUESTIONS', default=0)
    rndHash = models.CharField(max_length=16, db_column='PS_RND_HASH', null=True, blank=True)
    iSPStatus = models.IntegerField(db_column='PS_ISP_STATUS', default=0)
    tWelcomeMsg = models.CharField(max_length=250, db_column='PS_TWELCOME_MSG', null=True, blank=True)
    tCompleteMsg = models.CharField(max_length=250, db_column='PS_TCOMPLETE_MSG', null=True, blank=True)
    tFinalMsg = models.CharField(max_length=250, db_column='PS_TFINAL_MSG', null=True, blank=True)
    dPublishDate = models.DateField(db_column='PS_DPUBLISH_DATE', null=True, blank=True)
    groupList = models.CharField(max_length=250, db_column='PS_GROUP_LIST', null=True, blank=True)
    isSend = models.CharField(max_length=1, db_column='PS_IS_SEND', default='N')
    isProcessed = models.CharField(max_length=1, db_column='PS_IS_PROCESSED', default='N')
    questionFlowJson = models.TextField(db_column='PS_QUESTION_FLOW_JSON', null=True, blank=True)
    pnId = models.BigIntegerField(db_column='PS_PN_ID', null=True, blank=True)
    psEmbedding = models.JSONField(db_column='PS_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'POLLING_SMS'
        managed = False

class SpQuestions(models.Model):
    queId = models.BigAutoField(primary_key=True, db_column='PSQ_ID')
    iSmspollingId = models.BigIntegerField(db_column='PSQ_PS_ID', null=True, blank=True)
    queTypeId = models.BigIntegerField(db_column='PSQ_TYPE_ID', null=True, blank=True)
    question = models.CharField(max_length=2000, db_column='PSQ_QUESTION', null=True, blank=True)
    noOfOptions = models.IntegerField(db_column='PSQ_NO_OF_OPTIONS', null=True, blank=True)
    queOrder = models.IntegerField(db_column='PSQ_QUE_ORDER', default=0)
    disOrder = models.BigIntegerField(db_column='PSQ_DISORDER', null=True, blank=True)
    ddQue = models.IntegerField(db_column='PSQ_DD_QUE', default=0)
    catId = models.IntegerField(db_column='PSQ_CAT_ID', null=True, blank=True)

    class Meta:
        db_table = 'POLLING_SMS_QUESTIONS'
        managed = False

class SpOptions(models.Model):
    optId = models.BigAutoField(primary_key=True, db_column='PSA_ID')
    optTypeId = models.BigIntegerField(db_column='PSA_TYPE_ID', null=True, blank=True)
    queId = models.BigIntegerField(db_column='PSA_QUE_ID', null=True, blank=True)
    optionVal = models.CharField(max_length=250, db_column='PSA_ANSWER', null=True, blank=True)
    optOrder = models.IntegerField(db_column='PSA_OPT_ORDER', default=0)
    ansAnalysis = models.CharField(max_length=250, db_column='PSA_ANALYSIS', null=True, blank=True)
    condQue = models.IntegerField(db_column='PSA_COND_QUE', null=True, blank=True)
    regReq = models.IntegerField(db_column='PSA_REG_REQ', null=True, blank=True)
    psaEmbedding = models.JSONField(null=True, blank=True, db_column='PSA_EMBEDDING')

    class Meta:
        db_table = 'POLLING_SMS_ANSWERS'
        managed = False

class SpReply(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='PSR_ID')
    smsPollingId = models.BigIntegerField(db_column='PSR_SP_ID', null=True, blank=True)
    quesId = models.IntegerField(db_column='PSR_QUE_ID', null=True, blank=True)
    question = models.CharField(max_length=2000, db_column='PSR_QUESTION', null=True, blank=True)
    ansId = models.IntegerField(db_column='PSR_ANS_ID', null=True, blank=True)
    ansVal = models.CharField(max_length=255, db_column='PSR_ANSWER', null=True, blank=True)
    userReply = models.TextField(db_column='PSR_USER_REPLY', null=True, blank=True)
    fromNo = models.CharField(max_length=255, db_column='PSR_FROM_NO', null=True, blank=True)
    toNo = models.CharField(max_length=255, db_column='PSR_TO_NO', null=True, blank=True)
    sid = models.CharField(max_length=255, db_column='PSR_SID', null=True, blank=True)
    sendDate = models.DateTimeField(db_column='PSR_SEND_DATE', null=True, blank=True)
    replyDate = models.DateTimeField(db_column='PSR_REPLY_YDATE', null=True, blank=True)
    fromCountry = models.CharField(max_length=255, db_column='PSR_FROM_COUNTRY', null=True, blank=True)
    fromState = models.CharField(max_length=255, db_column='PSR_FROM_STATE', null=True, blank=True)
    fromCity = models.CharField(max_length=255, db_column='PSR_FROM_CITY', null=True, blank=True)
    fromZip = models.CharField(max_length=255, db_column='PSR_FROM_ZIP', null=True, blank=True)
    tranId = models.BigIntegerField(db_column='PSR_CT_TRANS_ID', default=0)
    psaEmbedding = models.JSONField(null=True, blank=True, db_column='PSR_EMBEDDING')

    class Meta:
        db_table = 'POLLING_SMS_RESPONSES'
        managed = False

class PollingSmsTemp(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='PST_ID')
    iSmspollingId = models.BigIntegerField(db_column='PST_SMS_POLL_ID', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='PST_CLIENT_ID', null=True, blank=True)
    emailId = models.BigIntegerField(db_column='PST_EMAIL_ID', null=True, blank=True)
    is_send = models.CharField(max_length=1, db_column='PST_IS_SENT', default='N')
    pstEmbedding = models.JSONField(null=True, blank=True, db_column='PST_EMBEDDING')

    class Meta:
        db_table = 'POLLING_SMS_DRAFT'
        managed = False

class SpQuestionCategory(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='SQC_ID')
    catName = models.CharField(max_length=255, db_column='SQC_CAT_NAME', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='SQC_CLIENT_ID', null=True, blank=True)

    class Meta:
        db_table = 'POLLING_SMS_QUESTION_CATEGORY'
        managed = False

class SpCountry(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='PSD_ID')
    iSmsPollingId = models.BigIntegerField(db_column='PSD_PS_ID', null=True, blank=True)
    country = models.CharField(max_length=255, db_column='PSD_COUNTRY', null=True, blank=True)
    psdEmbedding = models.JSONField(null=True, blank=True, db_column='PSD_EMBEDDING')

    class Meta:
        db_table = 'POLLING_SMS_COUNTRY'
        managed = False

class PollingSmsSend(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='PSS_ID')
    iSmspollingId = models.BigIntegerField(db_column='PSS_SMS_POLL_ID', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='PSS_CLIENT_ID', null=True, blank=True)
    emailId = models.BigIntegerField(db_column='PSS_CONTACT_ID', null=True, blank=True)
    sId = models.CharField(max_length=255, db_column='PSS_SID', null=True, blank=True)
    smsStatus = models.CharField(max_length=255, db_column='PSS_SMS_STATUS', null=True, blank=True)
    errorMessage = models.CharField(max_length=255, db_column='PSS_ERROR_MESSAGE', null=True, blank=True)
    errorCode = models.CharField(max_length=255, db_column='PSS_ERROR_CODE', null=True, blank=True)
    fromContact = models.CharField(max_length=255, db_column='PSS_FROM_CONTACT', null=True, blank=True)
    toContact = models.CharField(max_length=255, db_column='PSS_TO_CONTACT', null=True, blank=True)
    smsSendDate = models.DateTimeField(db_column='PSS_SEND_DATE', null=True, blank=True)
    isSend = models.CharField(max_length=1, db_column='PSS_IS_SENT', default='N')
    pssEmbedding = models.JSONField(null=True, blank=True, db_column='PSS_EMBEDDING')

    class Meta:
        db_table = 'POLLING_SMS_SENT'
        managed = False

class SpTransLog(models.Model):
    id = models.BigAutoField(primary_key=True, db_column='PSR_ID')
    smspollingId = models.BigIntegerField(db_column='PSR_PS_ID', null=True, blank=True)
    psrTenantId = models.BigIntegerField(db_column='PSR_CLIENT_ID', null=True, blank=True)
    quesId = models.BigIntegerField(db_column='PSR_QUES_ID', null=True, blank=True)
    question = models.TextField(db_column='PSR_QUESTION', null=True, blank=True)
    userReply = models.TextField(db_column='PSR_USER_REPLY', null=True, blank=True)
    fromNo = models.CharField(max_length=255, db_column='PSR_FROM_NO', null=True, blank=True)
    toNo = models.CharField(max_length=255, db_column='PSR_TO_NO', null=True, blank=True)
    smsDate = models.DateTimeField(db_column='PSR_SMS_DATE', null=True, blank=True)
    transRate = models.FloatField(db_column='PSR_TRANS_RATE', null=True, blank=True)
    transAmt = models.FloatField(db_column='PSR_TRANS_AMT', null=True, blank=True)
    memberSend = models.CharField(max_length=1, db_column='PSR_MEMBER_SEND', null=True, blank=True)
    fromCountry = models.CharField(max_length=255, db_column='PSR_FROM_COUNTRY', null=True, blank=True)
    fromState = models.CharField(max_length=255, db_column='PSR_FROM_STATE', null=True, blank=True)
    fromCity = models.CharField(max_length=255, db_column='PSR_FROM_CITY', null=True, blank=True)
    fromZip = models.CharField(max_length=255, db_column='PSR_FROM_ZIP', null=True, blank=True)
    tranId = models.BigIntegerField(db_column='PSR_CT_TRANS_ID', default=0)
    msgContains = models.CharField(max_length=2000, db_column='PSR_MSG_CONTAINS', null=True, blank=True)
    questionSend = models.CharField(max_length=1, db_column='PSR_QUESTION_SEND', null=True, blank=True)
    psaEmbedding = models.JSONField(null=True, blank=True, db_column='PSA_EMBEDDING')

    class Meta:
        db_table = 'POLLING_SMS_REPORTING'
        managed = False

Contact = Userlist


class CampaignsEmail(models.Model):
    campId = models.BigAutoField(db_column='CE_ID', primary_key=True)
    byAutoManual = models.CharField(db_column='CE_BY_AUTO_MANUAL', max_length=10, null=True, blank=True)
    byMeasure = models.CharField(db_column='CE_BY_MEASURE', max_length=10, null=True, blank=True)
    byNumber = models.IntegerField(db_column='CE_BY_NUMBER', null=True, blank=True)
    byType = models.CharField(db_column='CE_BY_TYPE', max_length=10, null=True, blank=True)
    campDetail = models.TextField(db_column='CE_DETAIL')
    campDetailB = models.TextField(db_column='CE_DETAIL_B', null=True, blank=True)
    campMainType = models.IntegerField(db_column='CE_MAIN_TYPE', null=True, blank=True)
    campName = models.CharField(db_column='CE_CAMP_NAME', max_length=250)
    campStatus = models.IntegerField(db_column='CE_STATUS', null=True, blank=True)
    campType = models.IntegerField(db_column='CE_CAMP_TYPE')
    fromAdd = models.CharField(db_column='CE_FROM_ADD', max_length=255)
    fromName = models.CharField(db_column='CE_FROM_NAME', max_length=255, null=True, blank=True)
    fromNameB = models.CharField(db_column='CE_FROM_NAME_B', max_length=255, null=True, blank=True)
    groupList = models.CharField(db_column='CE_GROUP_LIST', max_length=2000)
    incrementalUpdates = models.CharField(db_column='CE_INCREMENTAL_UPDATES', max_length=10, null=True, blank=True)
    mailType = models.CharField(db_column='CE_MAIL_TYPE', max_length=255, null=True, blank=True)
    mypageId = models.BigIntegerField(db_column='CE_MY_PAGE_ID', null=True, blank=True)
    mypageIdB = models.BigIntegerField(db_column='CE_MY_PAGE_ID_B', null=True, blank=True)
    remainGroupPer = models.IntegerField(db_column='CE_REMAIN_GROUP_PER', null=True, blank=True)
    replyToAdd = models.CharField(db_column='CE_REPLY_TO_ADD', max_length=255)
    resultTie = models.CharField(db_column='CE_RESULT_TIE', max_length=10, null=True, blank=True)
    scheduleType = models.IntegerField(db_column='CE_SCHEDULE_TYPE', null=True, blank=True)
    scheduleTypeB = models.IntegerField(db_column='CE_SCHEDULE_TYPE_B', null=True, blank=True)
    segId = models.BigIntegerField(db_column='CE_SEGID', null=True, blank=True)
    selectGroupPer = models.IntegerField(db_column='CE_SELECT_GROUP_PER', null=True, blank=True)
    sendDate = models.DateTimeField(db_column='CE_SEND_DATE')
    sendOnDate = models.DateTimeField(db_column='CE_SEND_ON_DATE', null=True, blank=True)
    sendOnDateB = models.DateTimeField(db_column='CE_SEND_ON_DATE_B', null=True, blank=True)
    sendOnTime = models.DurationField(db_column='CE_SEND_ON_TIME', null=True, blank=True)
    sendOnTimeB = models.DurationField(db_column='CT_TRAN_CAMPAIGN_NAME', null=True, blank=True)
    subject = models.CharField(db_column='CE_SUBJECT', max_length=255)
    subjectB = models.CharField(db_column='CE_SUBJECT_B', max_length=255, null=True, blank=True)
    testingType = models.IntegerField(db_column='CE_TESTING_TYPE', null=True, blank=True)
    tries = models.IntegerField(db_column='CE_TRIES', null=True, blank=True)
    triesCount = models.IntegerField(db_column='CE_TRIES_COUNT', null=True, blank=True)
    ceClientId = models.BigIntegerField(db_column='CE_CLIENT_ID', null=True, blank=True)
    archiveYn = models.CharField(db_column='CE_ARCHIVE_YN', max_length=1, default='N')

    class Meta:
        db_table = 'CAMPAIGN_EMAILS'
        managed = False


class CampaignsSms(models.Model):
    smsId = models.BigAutoField(db_column='CS_ID', primary_key=True)
    groupList = models.CharField(db_column='CS_GROUPLIST', max_length=255)
    readyToSms = models.CharField(db_column='CS_READY_TO_SMS', max_length=1, default='N')
    scheduleType = models.IntegerField(db_column='CS_SCHEDULE_TYPE', null=True, blank=True)
    segId = models.BigIntegerField(db_column='CS_SEG_ID', null=True, blank=True)
    sendDate = models.DateTimeField(db_column='CS_SEND_DATE', null=True, blank=True)
    sendOnDate = models.DateTimeField(db_column='CS_SEND_ON_DATE', null=True, blank=True)
    sendOnTime = models.DurationField(db_column='CS_SEND_ON_TIME', null=True, blank=True)
    smsDetail = models.TextField(db_column='CS_CAMP_DETAIL', null=True, blank=True)
    smsName = models.CharField(db_column='CS_NAME', max_length=255)
    smsStatus = models.IntegerField(db_column='CS_STATUS', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='CS_CLIENT_ID', null=True, blank=True)
    chkOptOut = models.IntegerField(db_column='CS_CHK_OPT_OUT', null=True, blank=True)
    optOutMsg = models.CharField(db_column='CS_OPT_OUT_MSG', max_length=255, null=True, blank=True)
    smsOpenClose = models.CharField(db_column='CS_OPEN_CLOSE', max_length=255, null=True, blank=True)
    smsCloseDate = models.DateTimeField(db_column='CS_CLOSE_DATE', null=True, blank=True)
    pnId = models.IntegerField(db_column='CS_PN_ID', null=True, blank=True)
    csEmbedding = models.JSONField(db_column='CS_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'CAMPAIGN_SMS'
        managed = False



class Calendar(models.Model):
    calId = models.BigAutoField(db_column='CAL_ID', primary_key=True)
    calTitle = models.CharField(db_column='CAL_TITLE', max_length=255, null=True, blank=True)
    calDescription = models.TextField(db_column='CAL_DESCRIPTION', null=True, blank=True)
    calStartDateTime = models.DateTimeField(db_column='CAL_START_DATE_TIME', null=True, blank=True)
    calEndDateTime = models.DateTimeField(db_column='CAL_END_DATE_TIME', null=True, blank=True)
    calCreatedDateTime = models.DateTimeField(db_column='CAL_CREATED_DATE_TIME', null=True, blank=True)
    calUpdatedDateTime = models.DateTimeField(db_column='CAL_UPDATED_DATE_TIME', null=True, blank=True)
    calAllDay = models.CharField(db_column='CAL_ALL_DAY', max_length=255, default='false')
    calMemberId = models.BigIntegerField(db_column='CAL_CLIENT_ID', default=0)
    calTimeZone = models.CharField(db_column='CAL_TIME_ZONE', max_length=255, null=True, blank=True)
    calAttendees = models.CharField(db_column='CAL_ATTENDEES', max_length=2000, null=True, blank=True)
    calAetId = models.BigIntegerField(db_column='CAL_AET_ID', default=0)
    calNotification = models.CharField(db_column='CAL_NOTIFICATION', max_length=1, default='N')
    calNumbers = models.CharField(db_column='CAL_NUMBERS', max_length=250, null=True, blank=True)
    calType = models.CharField(db_column='CAL_TYPE', max_length=255, null=True, blank=True)
    calEventReminder = models.CharField(db_column='CAL_EVENT_REMINDER', max_length=255, default='event')
    calReminderSubject = models.CharField(db_column='CAL_REMINDER_SUBJECT', max_length=255, null=True, blank=True)
    calReminderType = models.CharField(db_column='CAL_REMINDER_TYPE', max_length=255, null=True, blank=True)
    calMyPageId = models.BigIntegerField(db_column='CAL_MYPAGE_ID', default=0)
    calSmsSstId = models.BigIntegerField(db_column='CAL_SMS_SST_ID', default=0)
    calScheduleDateTime = models.DateTimeField(db_column='CAL_SCHEDULE_DATE_TIME', null=True, blank=True)
    calParentId = models.BigIntegerField(db_column='CAL_PARENT_ID', default=0)
    calRepeatEvery = models.IntegerField(db_column='CAL_REPEAT_EVERY', default=0)
    calRepeatType = models.CharField(db_column='CAL_REPEAT_TYPE', max_length=255, null=True, blank=True)
    calRepeatEveryType = models.CharField(db_column='CAL_REPEAT_EVERY_TYPE', max_length=255, null=True, blank=True)
    calRepeatDayName = models.CharField(db_column='CAL_REPEAT_DAY_NAME', max_length=255, null=True, blank=True)
    calRepeatEndDate = models.DateTimeField(db_column='CAL_REPEAT_END_DATE', null=True, blank=True)
    calRepeatDate = models.DateTimeField(db_column='CAL_REPEAT_DATE', null=True, blank=True)
    calRepeatSelectedOption = models.IntegerField(db_column='CAL_REPEAT_SELECTED_OPTION', default=0)

    class Meta:
        db_table = 'CALENDAR'
        managed = False


class CampaignsSendEmail(models.Model):
    id = models.BigAutoField(db_column='CES_ID', primary_key=True)
    campId = models.BigIntegerField(db_column='CES_CAMP_ID', null=True, blank=True)
    campSendId = models.BigIntegerField(db_column='CES_SEND_ID', default=0)
    memberId = models.BigIntegerField(db_column='CES_CLIENT_ID', null=True, blank=True)
    email = models.CharField(db_column='CES_EMAIL', max_length=500, null=True, blank=True)
    emailId = models.BigIntegerField(db_column='CES_EMAIL_ID', null=True, blank=True)
    isSend = models.CharField(db_column='CES_IS_SEND', max_length=1, default='N')
    isRead = models.CharField(db_column='CES_IS_READ', max_length=1, null=True, blank=True)
    isBounced = models.CharField(db_column='CES_IS_BOUNCED', max_length=1, null=True, blank=True)
    isUnsubscribed = models.CharField(db_column='CES_IS_UNSUBSCRIBED', max_length=1, null=True, blank=True)
    firstName = models.CharField(db_column='CES_FIRST_NAME', max_length=255, null=True, blank=True)
    lastName = models.CharField(db_column='CES_LAST_NAME', max_length=255, null=True, blank=True)
    emailDomain = models.CharField(db_column='CES_EMAIL_DOMAIN', max_length=50, null=True, blank=True)
    csDefaultLanguage = models.CharField(db_column='CES_CS_DEFAULT_LANGUAGE', max_length=50, default='en')
    smtpServerHost = models.CharField(db_column='CES_SMTP_SERVER_HOST', max_length=50, null=True, blank=True)
    isProcessed = models.CharField(db_column='CES_IS_PROCESSED', max_length=1, default='N')
    emailQId = models.CharField(db_column='CES_EMAIL_Q_ID', max_length=255, null=True, blank=True)
    emailStatus = models.CharField(db_column='CES_EMAIL_STATUS', max_length=255, null=True, blank=True)
    cronStatus = models.CharField(db_column='CES_CRON_STATUS', max_length=255, default='active')
    splitGroup = models.CharField(db_column='CES_SPLIT_GROUP', max_length=1, null=True, blank=True)
    groupWinner = models.CharField(db_column='CES_GROUP_WINNER', max_length=1, null=True, blank=True)
    msgPriority = models.IntegerField(db_column='CES_MSG_PRIORITY', default=0)
    cesEmbedding = models.JSONField(null=True, blank=True, db_column='CES_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_EMAIL_SENT'
        managed = False


class CampaignSmsReply(models.Model):
    crId = models.BigAutoField(db_column='CSR_ID', primary_key=True)
    crEmailId = models.BigIntegerField(db_column='CSR_EMAIL_ID', null=True, blank=True)
    crSid = models.CharField(db_column='CSR_SID', max_length=255, null=True, blank=True)
    crMemberId = models.BigIntegerField(db_column='CSR_CLIENT_ID', null=True, blank=True)
    crSmsId = models.BigIntegerField(db_column='CSR_CS_ID', null=True, blank=True)
    crReply = models.TextField(db_column='CSR_REPLY', null=True, blank=True)
    crReplyNo = models.CharField(db_column='CSR_REPLY_NO', max_length=50, null=True, blank=True)
    crSmsSid = models.CharField(db_column='CSR_SMS_SID', max_length=255, null=True, blank=True)
    crSmsStatus = models.CharField(db_column='CSR_SMS_STATUS', max_length=50, null=True, blank=True)
    crSmsErrorMessage = models.CharField(db_column='CSR_SMS_ERROR_MESSAGE', max_length=255, null=True, blank=True)
    crSmsErrorCode = models.CharField(db_column='CSR_SMS_ERROR_CODE', max_length=50, null=True, blank=True)
    crSmsFromNo = models.CharField(db_column='CSR_SMS_FROM_NO', max_length=50, null=True, blank=True)
    crSmsToNo = models.CharField(db_column='CSR_SMS_TO_NO', max_length=50, null=True, blank=True)
    crDate = models.DateTimeField(db_column='CSR_DATE', null=True, blank=True)
    crRead = models.CharField(db_column='CSR_READ', max_length=1, default='N', null=True, blank=True)
    csrEmbedding = models.JSONField(db_column='CSR_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'CAMPAIGN_SMS_REPLY'
        managed = False



class SurveysStatistics(models.Model):
    ssId = models.BigAutoField(db_column='SS_ID', primary_key=True)
    ssSryId = models.BigIntegerField(db_column='SS_SUR_ID', default=0)
    ssSqueComplete = models.BigIntegerField(db_column='SS_SQUE_COMPLETE', default=0)
    ssIsComplete = models.BigIntegerField(db_column='SS_IS_COMPLETE', default=0)
    ssSessionId = models.CharField(db_column='SS_SESSION_ID', max_length=255, null=True, blank=True)
    ssIpAddress = models.CharField(db_column='SS_IP_ADDRESS', max_length=255, null=True, blank=True)
    ssDate = models.DateTimeField(db_column='SS_DATE')
    ssCity = models.CharField(db_column='SS_CITY', max_length=255, null=True, blank=True)
    ssState = models.CharField(db_column='SS_STATE', max_length=255, null=True, blank=True)
    ssCountry = models.CharField(db_column='SS_COUNTRY', max_length=255, null=True, blank=True)
    ssTechnology = models.CharField(db_column='SS_TECHNOLOGY', max_length=255, null=True, blank=True)
    ssSources = models.CharField(db_column='SS_SOURCES', max_length=255, null=True, blank=True)
    ssEmbedding = models.JSONField(db_column='SS_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'SURVEYS_STATISTICS'
        managed = False

class SurveysPages(models.Model):
    spgId = models.BigAutoField(db_column='SP_ID', primary_key=True)
    spgSryId = models.BigIntegerField(db_column='SP_SUR_ID', default=0)
    spgNumber = models.BigIntegerField(db_column='SP_TYPE', default=0)
    spgType = models.CharField(db_column='SPG_TYPE', max_length=250, null=True, blank=True)
    spEmbedding = models.JSONField(null=True, blank=True, db_column='SP_EMBEDDING')

    class Meta:
        db_table = 'SURVEYS_PAGES'
        managed = False


class SurveysQuestions(models.Model):
    squeId = models.BigAutoField(db_column='SQ_ID', primary_key=True)
    squeSpgId = models.BigIntegerField(db_column='SQ_PAGE_ID', default=0)
    squeType = models.CharField(db_column='SQ_TYPE', max_length=250, null=True, blank=True)
    squeQuestion = models.CharField(db_column='SQ_QUESTION', max_length=2000, null=True, blank=True)
    squeDisplayOrder = models.BigIntegerField(db_column='SQ_DISPLAY_ORDER', default=0)
    squeCatId = models.BigIntegerField(db_column='SQ_CAT_ID', default=0)
    sqEmbedding = models.JSONField(null=True, blank=True, db_column='SQ_EMBEDDING')

    class Meta:
        db_table = 'SURVEYS_QUESTIONS'
        managed = False


class SurveysOptions(models.Model):
    soptId = models.BigAutoField(db_column='SQD_ID', primary_key=True)
    soptSqueId = models.BigIntegerField(db_column='SQD_QUES_ID', default=0)
    soptValue = models.CharField(db_column='SQD_VALUE', max_length=250, null=True, blank=True)
    soptDescription = models.CharField(db_column='SQD_DESCRIPTION', max_length=250, null=True, blank=True)
    soptDisplayOrder = models.BigIntegerField(db_column='SQD_DISPLAY_ORDER', default=0)
    soptHasComments = models.IntegerField(db_column='SQD_HAS_COMMENTS', default=0)
    sqdEmbedding = models.JSONField(null=True, blank=True, db_column='SOPT_EMBEDDING')

    class Meta:
        db_table = 'SURVEYS_QUESTION_DETAILS'
        managed = False


class SurveysOptionsColumns(models.Model):
    soptId = models.BigAutoField(db_column='SOC_ID', primary_key=True)
    soptSqueId = models.BigIntegerField(db_column='SOC_QUE_ID', default=0)
    soptValue = models.CharField(db_column='SOC_VALUE', max_length=250, null=True, blank=True)
    soptDisplayOrder = models.BigIntegerField(db_column='SOC_DISPLAY_ORDER', default=0)
    socEmbedding = models.JSONField(null=True, blank=True, db_column='SOC_EMBEDDING')

    class Meta:
        db_table = 'SURVEYS_OPTIONS_COLUMNS'
        managed = False


class SurveysAnswers(models.Model):
    sansId = models.BigAutoField(db_column='SA_ID', primary_key=True)
    sansSsId = models.BigIntegerField(db_column='SA_SS_ID', default=0)
    sansSpgId = models.BigIntegerField(db_column='SA_PAGE_ID', default=0)
    sansSqueId = models.BigIntegerField(db_column='SA_QUES_ID', default=0)
    sansAnswers = models.CharField(db_column='SA_ANSWERS', max_length=2000, null=True, blank=True)
    sansComments = models.CharField(db_column='SA_COMMENTS', max_length=2000, null=True, blank=True)
    saEmbedding = models.JSONField(null=True, blank=True, db_column='SA_EMBEDDING')

    class Meta:
        db_table = 'SURVEYS_ANSWERS'
        managed = False

class Groups(models.Model):
    grpId = models.BigAutoField(db_column='GRP_ID', primary_key=True)
    grpGroupName = models.CharField(db_column='GRP_GROUP_NAME', max_length=75)
    grpDateRegistered = models.DateTimeField(db_column='GRP_DATE_REGISTERED', auto_now_add=True)
    grpClientId = models.BigIntegerField(db_column='GRP_CLIENT_ID', null=True, blank=True)
    grpLockGroup = models.CharField(db_column='GRP_LOCK_GROUP', max_length=1, default='N')
    grpSegmentYn = models.CharField(db_column='GRP_SEGMENT_YN', max_length=1, default='N')
    grpDuplicateRecordsYn = models.CharField(db_column='GRP_DUPLICATE_RECORDS_YN', max_length=1, default='N')
    grpTypeEmail = models.CharField(db_column='GRP_TYPE_EMAIL', max_length=255, default='unverified')
    grpTotalMember = models.BigIntegerField(db_column='GRP_TOTAL_MEMBER', default=0)
    grpEmbedding = models.JSONField(null=True, blank=True, db_column='GRP_EMBEDDING')

    class Meta:
        db_table = 'GROUPS'
        managed = False

class SvQuestionCategory(models.Model):
    id = models.BigAutoField(db_column='SQC_ID', primary_key=True)
    cat_name = models.CharField(db_column='SQC_CAT_NAME', max_length=255, null=True, blank=True)
    member_id = models.BigIntegerField(db_column='SQC_CLIENT_ID', null=True, blank=True)

    class Meta:
        db_table = 'SURVEY_QUESTION_CATEGORIES'
        managed = False

class SurveysTemplate(models.Model):
    st_id = models.BigAutoField(db_column='ST_ID', primary_key=True)
    member_id = models.BigIntegerField(db_column='ST_CLIENT_ID', null=True, blank=True)
    st_name = models.CharField(db_column='ST_NAME', max_length=255, null=True, blank=True)
    st_data = models.TextField(db_column='ST_DATA', null=True, blank=True)
    st_status = models.IntegerField(db_column='ST_STATUS')
    st_create_date = models.DateField(db_column='ST_CREATE_DATE', null=True, blank=True)
    st_update_date = models.DateField(db_column='ST_UPDATE_DATE', null=True, blank=True)
    st_html = models.TextField(db_column='ST_HTML', null=True, blank=True)
    st_logic_flow = models.TextField(db_column='ST_LOGIC_FLOW', null=True, blank=True)
    st_category_page_list = models.TextField(db_column='ST_CATEGORY_PAGE_LIST', null=True, blank=True)
    st_total_questions = models.IntegerField(db_column='ST_TOTAL_QUESTIONS', default=0)
    st_description = models.CharField(db_column='ST_DESCRIPTION', max_length=2000, null=True, blank=True)
    st_type = models.IntegerField(db_column='ST_TYPE', default=0)
    st_survey_about = models.CharField(db_column='ST_SURVEY_ABOUT', max_length=500, null=True, blank=True)
    st_survey_goal = models.CharField(db_column='ST_SURVEY_GOAL', max_length=500, null=True, blank=True)
    st_survey_goal_description = models.CharField(db_column='ST_SURVEY_GOAL_DESCRIPTION', max_length=500, null=True, blank=True)
    st_no_of_question = models.IntegerField(db_column='ST_NO_OF_QUESTION', default=0)
    st_survey_type = models.CharField(db_column='ST_SURVEY_TYPE', max_length=255, null=True, blank=True)
    st_embedding = models.JSONField(null=True, blank=True, db_column='ST_EMBEDDING')

    class Meta:
        db_table = 'SURVEYS_TEMPLATE'
        managed = False


class CampaignsEmailSend(models.Model):
    id = models.BigAutoField(db_column='CEQ_ID', primary_key=True)
    member_id = models.BigIntegerField(db_column='CEQ_CLIENT_ID', null=True, blank=True)
    camp_type = models.IntegerField(db_column='CEQ_CAMP_TYPE', default=0, null=True, blank=True)
    is_proccessed_by_loadbalancer = models.IntegerField(db_column='CEQ_IS_PROCCESSED_BY_LOADBALANCER', default=0, null=True, blank=True)
    from_name = models.CharField(db_column='CEQ_FROM_NAME', max_length=255, null=True, blank=True)
    from_add = models.CharField(db_column='CEQ_FROM_ADD', max_length=255, null=True, blank=True)
    reply_to_add = models.CharField(db_column='CEQ_REPLY_TO_ADD', max_length=255, null=True, blank=True)
    subject = models.CharField(db_column='CEQ_SUBJECT', max_length=255, null=True, blank=True)
    send_date = models.DateTimeField(db_column='CEQ_SEND_DATE', null=True, blank=True)
    readytomail = models.CharField(db_column='CEQ_READY_TO_MAIL', max_length=1, default='N', null=True, blank=True)
    camp_id = models.BigIntegerField(db_column='CEQ_CAMP_ID', null=True, blank=True)
    last_opened = models.DateTimeField(db_column='CEQ_LAST_OPENED', null=True, blank=True)
    email_start_time = models.DateTimeField(db_column='CEQ_EMAIL_START_TIME', null=True, blank=True)
    email_end_time = models.DateTimeField(db_column='CEQ_EMAIL_END_TIME', null=True, blank=True)
    email_server_ip = models.CharField(db_column='CEQ_EMAIL_SERVER_IP', max_length=255, null=True, blank=True)
    sendondate = models.DateTimeField(db_column='CEQ_SEND_ON_DATE', null=True, blank=True)
    sendontime = models.DurationField(db_column='CEQ_SEND_ON_TIME', null=True, blank=True)
    mail_type = models.CharField(db_column='CEQ_MAIL_TYPE', max_length=255, default='Newsletter', null=True, blank=True)
    mypageid = models.BigIntegerField(db_column='CEQ_MY_PAGE_ID', null=True, blank=True)
    camp_main_type = models.IntegerField(db_column='CEQ_CAMP_MAIN_TYPE', null=True, blank=True)
    testing_type = models.IntegerField(db_column='CEQ_TESTING_TYPE', null=True, blank=True)
    selectgroupper = models.IntegerField(db_column='CEQ_SELECT_GROUP_PER', null=True, blank=True)
    remaingroupper = models.IntegerField(db_column='CEQ_REMAIN_GROUP_PER', null=True, blank=True)
    mypageidb = models.BigIntegerField(db_column='CEQ_MY_PAGE_ID_B', null=True, blank=True)
    from_name_b = models.CharField(db_column='CEQ_FROM_NAME_B', max_length=255, null=True, blank=True)
    subjectb = models.CharField(db_column='CEQ_SUBJECT_B', max_length=255, null=True, blank=True)
    scheduletypeb = models.IntegerField(db_column='CEQ_SCHEDULE_TYPE_B', null=True, blank=True)
    sendondateb = models.DateTimeField(db_column='CEQ_SEND_ON_DATE_B', null=True, blank=True)
    sendontimeb = models.DurationField(db_column='CEQ_SEND_ON_TIME_B', null=True, blank=True)
    byautomanual = models.CharField(db_column='CEQ_BY_AUTO_MANUAL', max_length=10, null=True, blank=True)
    bytype = models.CharField(db_column='CEQ_BY_TYPE', max_length=10, null=True, blank=True)
    bynumber = models.IntegerField(db_column='CEQ_BY_NUMBER', null=True, blank=True)
    bymeasure = models.CharField(db_column='CEQ_BY_MEASURE', max_length=10, null=True, blank=True)
    result_tie = models.CharField(db_column='CEQ_RESULT_TIE', max_length=10, null=True, blank=True)
    incremental_updates = models.CharField(db_column='CEQ_INCREMENTAL_UPDATES', max_length=10, null=True, blank=True)
    tries = models.IntegerField(db_column='CEQ_TRIES', null=True, blank=True)
    tries_count = models.IntegerField(db_column='CEQ_TRIES_COUNT', null=True, blank=True)
    is_completed_ab = models.CharField(db_column='CEQ_IS_COMPLETED_AB', max_length=1, null=True, blank=True)
    archive_yn = models.CharField(db_column='CEQ_ARCHIVE_YN', max_length=1, default='N', null=True, blank=True)
    total_queued = models.IntegerField(db_column='CEQ_TOTAL_QUEUED', default=0, null=True, blank=True)
    total_queued_b = models.IntegerField(db_column='CEQ_TOTAL_QUEUED_B', default=0, null=True, blank=True)
    total_queued_o = models.IntegerField(db_column='CEQ_TOTAL_QUEUED_O', default=0, null=True, blank=True)
    retry_send_date_time = models.DateTimeField(db_column='CEQ_RETRY_SEND_DATE_TIME', null=True, blank=True)
    max_bounce_email = models.IntegerField(db_column='CEQ_MAX_BOUNCE_EMAIL', default=0, null=True, blank=True)
    retry_send_count = models.IntegerField(db_column='CEQ_RETRY_SEND_COUNT', default=0, null=True, blank=True)
    throttling = models.CharField(db_column='CEQ_THROTTLING', max_length=1, null=True, blank=True)
    throttling_type = models.CharField(db_column='CEQ_THROTTLING_TYPE', max_length=500, null=True, blank=True)
    throttling_value = models.IntegerField(db_column='CEQ_THROTTLING_VALUE', null=True, blank=True)
    throttling_next_date = models.DateTimeField(db_column='CEQ_THROTTLING_NEXT_DATE', null=True, blank=True)
    camp_name = models.TextField(db_column='CEQ_CAMP_NAME', null=True, blank=True)
    grouplist = models.TextField(db_column='CEQ_GROUPLIST', null=True, blank=True)
    camp_detail = models.TextField(db_column='CEQ_CAMP_DETAIL', null=True, blank=True)
    camp_detail_b = models.TextField(db_column='CEQ_CAMP_DETAIL_B', null=True, blank=True)
    unsubscribe_uid = models.TextField(db_column='CEQ_UNSUBSCRIBE_UID', null=True, blank=True)
    stop_status = models.TextField(db_column='CEQ_STOP_STATUS', null=True, blank=True)
    ceq_trans_embedding = models.JSONField(null=True, blank=True, db_column='CEQ_TRANS_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_EMAIL_QUEUED'
        managed = False

class Domains(models.Model):
    domId = models.BigAutoField(db_column='DOM_ID', primary_key=True)
    domClientId = models.IntegerField(db_column='DOM_CLIENT_ID', null=True, blank=True)
    domDomain = models.CharField(db_column='DOM_DOMAIN', max_length=255, null=True, blank=True)
    domStatus = models.IntegerField(db_column='DOM_STATUS', null=True, blank=True)
    domCreateDate = models.DateTimeField(db_column='DOM_CREATE_DATE', auto_now_add=True)
    domDkim = models.CharField(db_column='DOM_DKIM', max_length=1, default='N')
    domSpf = models.CharField(db_column='DOM_SPF', max_length=1, default='N')
    domDmarc = models.CharField(db_column='DOM_DMARC', max_length=1, default='N')
    domBimi = models.CharField(db_column='DOM_BIMI', max_length=1, default='N')
    domEsp = models.CharField(db_column='DOM_ESP', max_length=255, null=True, blank=True)
    domDsp = models.CharField(db_column='DOM_DSP', max_length=255, null=True, blank=True)
    domDomainReputation = models.CharField(db_column='DOM_DOMAIN_REPUTATION', max_length=255, null=True, blank=True)
    domDomainCapacity = models.BigIntegerField(db_column='DOM_DOMAIN_CAPACITY', default=1000)
    domDomainCapacityUsed = models.BigIntegerField(db_column='DOM_DOMAIN_CAPACITY_USED', default=0)
    domEmbedding = models.JSONField(null=True, blank=True, db_column='DOM_EMBEDDING')

    class Meta:
        db_table = 'DOMAINS'
        managed = False

class TempSendEmailCampaigns(models.Model):
    id = models.BigAutoField(db_column='SEC_ID', primary_key=True)
    campId = models.BigIntegerField(db_column='SEC_CAMP_ID', null=True, blank=True)
    sqlString = models.TextField(db_column='SEC_SQL_STRING', null=True, blank=True)
    campMainType = models.IntegerField(db_column='SEC_CAMP_MAIN_TYPE')
    totA = models.FloatField(db_column='SEC_TOT_A')
    totB = models.FloatField(db_column='SEC_TOT_B')
    campSendId = models.BigIntegerField(db_column='SEC_CAMP_SEND_ID', default=0)
    msgPriority = models.IntegerField(db_column='SEC_MSG_PRIORITY')
    languageName = models.CharField(db_column='MP_TEMPLATE_LANGUAGE', max_length=250, null=True, blank=True)
    mpTemplateLanguage = models.CharField(db_column='SEC_MP_TEMPLATE_LANGUAGE', max_length=255, null=True, blank=True)
    isProcessedStart = models.CharField(db_column='SEC_IS_PROCESSED_START', max_length=1, default='N')
    isProcessedEnd = models.CharField(db_column='SEC_IS_PROCESSED_END', max_length=1, default='N')
    memberId = models.BigIntegerField(db_column='SEC_CLIENT_ID', null=True, blank=True)

    class Meta:
        db_table = 'TEMP_SEND_EMAIL_CAMPAIGNS'
        managed = False

class TranslateTemplateSend(models.Model):
    ttId = models.BigAutoField(db_column='TTS_ID', primary_key=True)
    ttMyPageId = models.BigIntegerField(db_column='TTS_MY_PAGE_ID', null=True, blank=True)
    ttMemberId = models.BigIntegerField(db_column='TTS_CLIENT_ID', null=True, blank=True)
    ttCampDetailSend = models.TextField(db_column='TTS_CAMP_DETAIL_SEND', null=True, blank=True)
    ttMasterCopy = models.CharField(db_column='TTS_MASTER_COPY', max_length=255, null=True, blank=True)
    ttTemplateLanguage = models.CharField(db_column='TTS_TEMPLATE_LANGUAGE', max_length=255, null=True, blank=True)
    ttPublishDate = models.DateTimeField(db_column='TTS_PUBLISH_DATE', null=True, blank=True)
    ttApiError = models.CharField(db_column='TTS_API_ERROR', max_length=250, null=True, blank=True)
    ttNodeId = models.BigIntegerField(db_column='TTS_NODE_ID', default=0)
    ttCampSendId = models.BigIntegerField(db_column='TTS_CAMP_SEND_ID', null=True, blank=True)

    class Meta:
        db_table = 'TRANSLATE_TEMPLATE_SEND'
        managed = False


class CampaignLinks(models.Model):
    id = models.BigAutoField(db_column='CL_ID', primary_key=True)
    campId = models.BigIntegerField(db_column='CL_CAMP_ID', null=True, blank=True)
    campLink = models.TextField(db_column='CL_LINK', null=True, blank=True)
    linkCount = models.IntegerField(db_column='CL_LINK_COUNT', default=0)
    splitGroup = models.CharField(db_column='CL_SPLIT_GROUP', max_length=1, null=True, blank=True)
    nodeId = models.BigIntegerField(db_column='CL_NODE_ID', null=True, blank=True)
    automationEmailNodeDetails = models.CharField(db_column='CL_AUTOMATION_EMAIL_NODE_DETAILS', max_length=2000, null=True, blank=True)
    clEmbedding = models.JSONField(null=True, blank=True, db_column='CL_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_LINKS'
        managed = False


class CampaignLinkClick(models.Model):
    id = models.BigAutoField(db_column='ID', primary_key=True)
    userId = models.BigIntegerField(db_column='USER_ID', null=True, blank=True)
    linkId = models.IntegerField(db_column='LINK_ID', null=True, blank=True)
    linkCount = models.IntegerField(db_column='LINK_COUNT', null=True, blank=True)
    city = models.CharField(db_column='CITY', max_length=255, null=True, blank=True)
    clickDate = models.DateTimeField(db_column='CLICK_DATE', null=True, blank=True)
    sources = models.CharField(db_column='SOURCES', max_length=255, null=True, blank=True)
    sourceDetails = models.CharField(db_column='SOURCE_DETAILS', max_length=2000, null=True, blank=True)

    class Meta:
        db_table = 'TEMP_CAMP_LINK_CLICK'
        managed = False


class CampaignSubscriber(models.Model):
    id = models.BigAutoField(db_column='CER_ID', primary_key=True)
    campId = models.BigIntegerField(db_column='CER_CAMP_ID', null=True, blank=True)
    subId = models.BigIntegerField(db_column='CER_CONTACT_ID', null=True, blank=True)
    totalOpen = models.BigIntegerField(db_column='CER_TOTAL_OPEN', null=True, blank=True)
    lastOpened = models.DateTimeField(db_column='CER_LAST_OPENED', null=True, blank=True)
    cerEmbedding = models.JSONField(null=True, blank=True, db_column='CER_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_EMAIL_REPORTING'
        managed = False


class SmtpServer(models.Model):
    id = models.AutoField(db_column='SS_ID', primary_key=True)
    serverName = models.CharField(db_column='SS_SERVER_NAME', max_length=45, null=True, blank=True)
    serverStatus = models.CharField(db_column='SS_SERVER_STATUS', max_length=255, null=True, blank=True)
    serverDomain = models.CharField(db_column='SS_SERVER_DOMAIN', max_length=255, null=True, blank=True)
    capacityHr = models.BigIntegerField(db_column='SS_CAPACITY_HR', null=True, blank=True)
    capacityDay = models.BigIntegerField(db_column='SS_CAPACITY_DAY', null=True, blank=True)
    weightHr = models.BigIntegerField(db_column='SS_WEIGHT_HR', null=True, blank=True)
    weightDay = models.BigIntegerField(db_column='SS_WEIGHT_DAY', null=True, blank=True)
    reactiveTime = models.DateTimeField(db_column='SS_REACTIVE_TIME', null=True, blank=True)
    activeDate = models.DateTimeField(db_column='SS_ACTIVE_DATE', null=True, blank=True)
    location = models.CharField(db_column='SS_LOCATION', max_length=255, null=True, blank=True)
    country = models.CharField(db_column='SS_COUNTRY', max_length=255, null=True, blank=True)
    threads = models.IntegerField(db_column='SS_THREADS', null=True, blank=True)
    mps = models.FloatField(db_column='SS_MPS', null=True, blank=True)
    isActive = models.IntegerField(db_column='SS_IS_ACTIVE', default=0)
    pctFailure10Min = models.FloatField(db_column='SS_PCT_FAILURE_10MIN', null=True, blank=True)
    currentFailureRate = models.FloatField(db_column='SS_CURRENT_FAILURE_RATE', null=True, blank=True)
    isDedicatedIp = models.CharField(db_column='SS_IS_DEDICATED_IP', max_length=1, null=True, blank=True)
    memberId = models.BigIntegerField(db_column='SS_CLIENT_ID', null=True, blank=True)

    class Meta:
        db_table = 'SMTP_SERVERS'
        managed = False



class GroupSegment(models.Model):
    segId = models.BigAutoField(db_column='SEG_ID', primary_key=True)
    segName = models.CharField(db_column='SEG_NAME', max_length=255, null=True, blank=True)
    groupId = models.BigIntegerField(db_column='SEG_GROUP_ID', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='SEG_CLIENT_ID', null=True, blank=True)
    segQuery = models.CharField(db_column='SEG_QUERY', max_length=2000, null=True, blank=True)
    segDateAdded = models.DateTimeField(db_column='SEGADDEDDATE')
    segEmbedding = models.JSONField(null=True, blank=True, db_column='SEG_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'SEGMENTS'

class GroupSegmentField(models.Model):
    segfId = models.BigAutoField(db_column='SF_ID', primary_key=True)
    segId = models.BigIntegerField(db_column='SF_SEG_ID')
    segFieldName = models.CharField(db_column='SF_FEILDS_NAME', max_length=255, null=True, blank=True)
    segFieldOperator = models.CharField(db_column='SF_OPERATOR', max_length=255, null=True, blank=True)
    segFieldValue = models.CharField(db_column='SF_FIELDS_VALUE', max_length=255, null=True, blank=True)
    segConditions = models.CharField(db_column='SF_CONDITIONS', max_length=255, null=True, blank=True)
    segDisplayOrder = models.BigIntegerField(db_column='SF_DISPLAY_ORDER', null=True, blank=True)
    segEmbedding = models.JSONField(null=True, blank=True, db_column='SEG_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'SEGMENT_FIELDS'

class Udf(models.Model):
    id = models.BigAutoField(db_column='UDF_ID', primary_key=True)
    tblUdfcol = models.CharField(db_column='UDF_UDFCOL', max_length=45, null=True, blank=True)
    udf = models.CharField(db_column='UDF_UDF', max_length=255)
    udfLabel = models.IntegerField(db_column='UDF_UDF_LABEL')
    groupId = models.BigIntegerField(db_column='UDF_GROUP_ID')

    class Meta:
        managed = False
        db_table = 'UDFS'

class TranslateTemplate(models.Model):
    ttId = models.BigAutoField(db_column='TT_ID', primary_key=True)
    ttMyPageId = models.BigIntegerField(db_column='TT_MY_PAGE_ID', null=True, blank=True)
    ttClientId = models.BigIntegerField(db_column='TT_CLIENT_ID', null=True, blank=True)
    ttMasterCopy = models.CharField(db_column='TT_MASTER_COPY', max_length=255, null=True, blank=True)
    ttTemplateLanguage = models.CharField(db_column='TT_TEMPLATE_LANGUAGE', max_length=255, null=True, blank=True)
    ttPublishDate = models.DateTimeField(db_column='TT_PUBLISH_DATE', null=True, blank=True)
    ttCampDetail = models.TextField(db_column='TT_CAMP_DETAIL', null=True, blank=True)
    ttCampDetailSend = models.TextField(db_column='TT_CAMP_DETAIL_SEND', null=True, blank=True)
    ttApiError = models.CharField(db_column='TT_API_ERROR', max_length=250, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'TRANSLATE_TEMPLATE'

class FreeTemplate(models.Model):
    ftId = models.BigAutoField(db_column='FT_ID', primary_key=True)
    ftName = models.CharField(db_column='FT_NAME', max_length=255, null=True, blank=True)
    ftFolderName = models.CharField(db_column='FT_FOLDERNAME', max_length=255, null=True, blank=True)
    ftStage = models.IntegerField(db_column='FT_STAGE', default=0)
    ftCatId = models.BigIntegerField(db_column='FT_CAT_ID', null=True, blank=True)
    ftTags = models.CharField(db_column='FT_TAGS', max_length=250, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'FREE_TEMPLATE'

class CatTemplate(models.Model):
    ctemId = models.BigAutoField(db_column='CT_ID', primary_key=True)
    ctemName = models.CharField(db_column='CT_NAME', max_length=255, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'CAT_TEMPLATE'

class SmsTemplates(models.Model):
    stId = models.BigAutoField(db_column='ST_ID', primary_key=True)
    stClientId = models.BigIntegerField(db_column='ST_CLIENT_ID', null=True, blank=True)
    stName = models.CharField(db_column='ST_NAME', max_length=255, null=True, blank=True)
    stDetails = models.TextField(db_column='ST_DETAILS', null=True, blank=True)
    stDate = models.DateTimeField(db_column='ST_DATE', null=True, blank=True)
    stEmbedding = models.JSONField(null=True, blank=True, db_column='ST_EMBEDDING')

    class Meta:
        managed = False
        db_table = 'SMS_TEMPLATES'

class CampaignSmsDetails(models.Model):
    sdId = models.BigAutoField(db_column='CSD_ID', primary_key=True)
    smsId = models.BigIntegerField(db_column='CSD_CS_ID', null=True, blank=True)
    sdDetail = models.TextField(db_column='CSD_DETAIL', null=True, blank=True)
    sdType = models.CharField(db_column='CSD_TYPE', max_length=255, null=True, blank=True)
    sdDisplayOrder = models.BigIntegerField(db_column='CSD_DISPLAY_ORDER', null=True, blank=True)
    csdEmbedding = models.JSONField(null=True, blank=True, db_column='CSD_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_SMS_DETAILS'
        managed = False


class SmsLinks(models.Model):
    id = models.BigAutoField(db_column='ID', primary_key=True)
    smsId = models.BigIntegerField(db_column='SMS_ID', null=True, blank=True)
    smsLink = models.CharField(db_column='SMS_LINK', max_length=250, null=True, blank=True)
    smsOrgLink = models.CharField(db_column='SMS_ORG_LINK', max_length=250, null=True, blank=True)
    linkCount = models.IntegerField(db_column='LINK_COUNT', default=0)

    class Meta:
        db_table = 'TBL_SMS_LINKS'
        managed = False


class SmsLinkTrace(models.Model):
    id = models.BigAutoField(db_column='ID', primary_key=True)
    smsLinkId = models.BigIntegerField(db_column='SMS_LINK_ID', null=True, blank=True)
    linkArray = models.TextField(db_column='LINK_ARRAY', null=True, blank=True)

    class Meta:
        db_table = 'TBL_SMS_LINK_TRACE'
        managed = False


class CampaignsSmsSend(models.Model):
    id = models.BigAutoField(db_column='CSS_ID', primary_key=True)
    groupList = models.CharField(db_column='CSS_GROUP_LIST', max_length=255)
    isProcessed = models.CharField(db_column='CSS_IS_PROCESSED', max_length=1, null=True, blank=True)
    isSend = models.CharField(db_column='CSS_IS_SEND', max_length=1, null=True, blank=True)
    readyToSms = models.CharField(max_length=1,db_column="CSS_READY_TO_SMS")
    scheduleType = models.IntegerField(db_column='CSS_SCHEDULE_TYPE', null=True, blank=True)
    sendDate = models.DateTimeField(db_column='CSS_SEND_DATE')
    sendOnDate = models.DateTimeField(db_column='CSS_SEND_ON_DATE', null=True, blank=True)
    sendOnTime = models.DurationField(db_column='CSS_SEND_ON_TIME', null=True, blank=True)
    smsEndTime = models.DateTimeField(db_column='CSS_SMS_END_TIME', null=True, blank=True)
    smsId = models.IntegerField(db_column='CSS_CS_ID', null=True, blank=True)
    smsName = models.CharField(db_column='CSS_SMS_NAME', max_length=250)
    smsStartTime = models.DateTimeField(db_column='CSS_SMS_START_TIME', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='CSS_CLIENT_ID', null=True, blank=True)
    chkOptOut = models.IntegerField(db_column='CSS_CHK_OPT_OUT', null=True, blank=True)
    optOutMsg = models.CharField(db_column='CSS_OPT_OUT_MSG', max_length=500, null=True, blank=True)
    cssEmbedding = models.JSONField(null=True, blank=True, db_column='CSS_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_SMS_SENT'
        managed = False


class CampaignSendSms(models.Model):
    id = models.BigAutoField(db_column='CSQ_ID', primary_key=True)
    smsId = models.BigIntegerField(db_column='CSQ_CSS_ID', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='CSQ_CLIENT_ID', null=True, blank=True)
    emailId = models.BigIntegerField(db_column='CSQ_EMAIL_ID', null=True, blank=True)
    isSend = models.CharField(db_column='CSQ_IS_SEND', max_length=1, default='N')
    sid = models.CharField(db_column='CSQ_SID', max_length=255, null=True, blank=True)
    smsStatus = models.CharField(db_column='CSQ_SMS_STATUS', max_length=255, null=True, blank=True)
    errorMessage = models.CharField(db_column='CSQ_ERROR_MESSAGE', max_length=255, null=True, blank=True)
    errorCode = models.CharField(db_column='CSQ_ERROR_CODE', max_length=255, null=True, blank=True)
    fromContact = models.CharField(db_column='CSQ_FROM_CONTACT', max_length=255, null=True, blank=True)
    toContact = models.CharField(db_column='CSQ_TO_CONTACT', max_length=255, null=True, blank=True)
    smsDetail = models.TextField(db_column='CSQ_SMS_DETAIL', null=True, blank=True)
    smsSendDate = models.DateTimeField(db_column='CSQ_SMS_SEND_DATE', null=True, blank=True)
    cssdId = models.BigIntegerField(db_column='CSQ_CSD_ID', null=True, blank=True)
    cssdType = models.CharField(max_length=255, null=True, blank=True,db_column="CSQ_CSS_TYPE")
    smsSegment = models.BigIntegerField(db_column='CSQ_SMS_SEGMENT', default=0)
    optOutMsg = models.CharField(db_column='CSQ_OPT_OUT_MSG', max_length=2000, null=True, blank=True)
    csqIdEmbedding = models.JSONField(null=True, blank=True, db_column='CSQ_ID_EMBEDDING')

    class Meta:
        db_table = 'CAMPAIGN_SMS_QUEUED'
        managed = False


class CampaignSendSmsTemp(models.Model):
    id = models.BigAutoField(db_column='CSD_ID', primary_key=True)
    emailId = models.BigIntegerField(db_column='CSD_EMAIL_ID', null=True, blank=True)
    isSend = models.CharField(db_column='CSD_IS_SEND', max_length=1)
    memberId = models.BigIntegerField(db_column='CSD_CLIENT_ID', null=True, blank=True)
    smsId = models.BigIntegerField(db_column='CSD_CS_ID', null=True, blank=True)

    class Meta:
        db_table = 'CAMPAIGN_SMS_DRAFT'
        managed = False

class PhoneNumbers(models.Model):
    pnId = models.BigAutoField(db_column='PN_ID', primary_key=True)
    phClientId = models.BigIntegerField(db_column='PH_CLIENT_ID')
    phPhoneNumber = models.CharField(db_column='PH_PHONE_NUMBER', max_length=15, null=True, blank=True)
    phSid = models.CharField(db_column='PH_SID', max_length=100, null=True, blank=True)
    phHowUsed = models.CharField(db_column='PH_HOW_USED', max_length=25, null=True, blank=True)
    phDatePurchased = models.DateTimeField(db_column='PH_DATE_PURCHASED', null=True, blank=True)
    phDateRenew = models.DateTimeField(db_column='PH_DATE_RENEW', null=True, blank=True)
    phPhoneNumberClosed = models.CharField(db_column='PH_PHONE_NUMBER_CLOSED', max_length=1, null=True, blank=True)
    phError = models.CharField(db_column='PH_ERROR', max_length=2000, null=True, blank=True)

    class Meta:
        db_table = 'PHONE_NUMBERS'
        managed = False

class SmsConversations(models.Model):
    cvsId = models.BigAutoField(db_column='SC_ID', primary_key=True)
    cvsMemberId = models.BigIntegerField(db_column='SC_CLIENT_ID', null=True, blank=True)
    cvsMemberNumber = models.CharField(db_column='SC_CONTACT_NUMBER', max_length=255, null=True, blank=True)
    cvsTwilioNumber = models.CharField(db_column='SC_PHONE_NUMBER', max_length=255, null=True, blank=True)
    cvsTitle = models.CharField(db_column='CVS_TITLE', max_length=255, null=True, blank=True)
    cvsConversationsSid = models.CharField(db_column='SC_CONVERSATIONS_SID', max_length=255, null=True, blank=True)
    cvsFriendlyName = models.CharField(db_column='SC_FRIENDLY_NAME', max_length=255, null=True, blank=True)
    cvsDate = models.DateTimeField(db_column='SC_DATE', null=True, blank=True)
    cvsClosed = models.CharField(db_column='SC_CLOSED', max_length=1, default='N')
    cvsClosedDate = models.DateTimeField(db_column='SC_CLOSED_DATE', null=True, blank=True)
    aldEmbedding = models.JSONField(null=True, blank=True, db_column='ALD_EMBEDDING')

    class Meta:
        db_table = 'SMS_CONVERSATIONS'
        managed = False


class SmsConversationsDetails(models.Model):
    cvsdId = models.BigAutoField(db_column='SCD_ID', primary_key=True)
    cvsdCvsId = models.BigIntegerField(db_column='SCD_SD_ID', null=True, blank=True)
    cvsdMessage = models.TextField(db_column='SCD_MESSAGE', null=True, blank=True)
    cvsdClientId = models.BigIntegerField(db_column='SCD_CLIENT_ID', null=True, blank=True)
    cvsdClientNumber = models.CharField(db_column='SCD_CLIENT_NUMBER', max_length=255, null=True, blank=True)
    cvsdParticipantSid = models.CharField(db_column='SCD_PARTICIPANT_SID', max_length=255, null=True, blank=True)
    cvsdSid = models.CharField(db_column='SCD_SID', max_length=255, null=True, blank=True)
    cvsdSender = models.CharField(db_column='SCD_SENDER', max_length=1, null=True, blank=True)
    cvsdDate = models.DateTimeField(db_column='SCD_DATE', null=True, blank=True)
    cvsdRead = models.CharField(db_column='SCD_IS_READ', max_length=1, default='N', null=True, blank=True)
    scdEmbedding = models.JSONField(null=True, blank=True, db_column='SCD_EMBEDDING')

    class Meta:
        db_table = 'SMS_CONVERSATION_DETAILS'
        managed = False


class OracleIntervalTimeField(models.Field):
    """
    Mimics Java's IntervalToSqlTimeConverter perfectly.
    Accepts "HH:MM:SS" (e.g. "10:00:00") and stores it as "0 10:00:00" in Oracle.
    Reads "+00 10:00:00.000000" from Oracle and returns "10:00:00" to Django.
    """
    
    def get_internal_type(self):
        # Tricks Django into letting us pass our custom string directly to the DB
        return "CharField"

    def db_type(self, connection):
        # Tells the database what column type to expect
        return "INTERVAL DAY TO SECOND"

    def get_prep_value(self, value):
        # Method 1: Python -> Database (Equivalent to convertToDatabaseColumn)
        if value is None:
            return None
        
        # If the request sends "10:00:00", we MUST artificially add the "0 " 
        # to prevent ORA-01867, exactly like your Java code did.
        if isinstance(value, str):
            clean_val = value.strip()
            # Prevent double-prefixing if it's already there
            if not clean_val.startswith("0 ") and not clean_val.startswith("+"):
                return f"0 {clean_val}"
            return clean_val
        
        return value

    def from_db_value(self, value, expression, connection):
        # Method 2: Database -> Python (Equivalent to convertToEntityAttribute)
        if value is None:
            return None
        
        # If oracledb translates the DB interval to a Python timedelta natively
        if isinstance(value, datetime.timedelta):
            # Calculate time, completely ignoring days
            seconds = value.seconds
            h, remainder = divmod(seconds, 3600)
            m, s = divmod(remainder, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        # If it comes as a raw string like "+00 10:00:00.000000"
        if isinstance(value, str):
            clean_str = value.replace('+', '').strip()
            parts = clean_str.split(' ')
            time_part = parts[1] if len(parts) > 1 else parts[0]
            if '.' in time_part:
                time_part = time_part.split('.')[0]
            return time_part
            
        return value

    def to_python(self, value):
        # Ensures the app layer consistently works with "HH:MM:SS" strings
        if value is None:
            return None
            
        if isinstance(value, datetime.timedelta):
            seconds = value.seconds
            h, remainder = divmod(seconds, 3600)
            m, s = divmod(remainder, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"
        
        if isinstance(value, str):
            clean_str = value.replace('+', '').strip()
            parts = clean_str.split(' ')
            time_part = parts[1] if len(parts) > 1 else parts[0]
            if '.' in time_part:
                time_part = time_part.split('.')[0]
            return time_part
            
        return value

class CalendarAppointmentAvailabilitySlots(models.Model):
    aasId = models.BigAutoField(db_column='AAS_ID', primary_key=True)
    aasDayName = models.CharField(db_column='AAS_DAY_NAME', max_length=255, null=True, blank=True)
    aasStartTime = OracleIntervalTimeField(db_column='AAS_START_TIME', null=True, blank=True)
    aasEndTime = OracleIntervalTimeField(db_column='AAS_END_TIME', null=True, blank=True)
    aasMemberId = models.BigIntegerField(db_column='AAS_CLIENT_ID', default=0)
    aasAvailableYN = models.CharField(db_column='AAS_AVAILABLE_YN', max_length=1, default='Y')
    aasCreatedDate = models.DateTimeField(db_column='AAS_CREATED_DATE', null=True, blank=True)
    aasEmbedding = models.JSONField(null=True, blank=True, db_column='AAS_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_APPOINTMENT_AVAILABILITY_SLOTS'
        managed = False


class CalendarAppointmentEventType(models.Model):
    aetId = models.BigAutoField(db_column='AET_ID', primary_key=True)
    aetTitle = models.CharField(db_column='AET_TITLE', max_length=255, null=True, blank=True)
    aetDescription = models.TextField(db_column='AET_DESCRIPTION', null=True, blank=True)
    aetDurationMinutes = models.BigIntegerField(db_column='AET_DURATION_MINUTES', null=True, blank=True)
    aetDurationHours = models.BigIntegerField(db_column='AET_DURATION_HOURS', null=True, blank=True)
    aetMemberId = models.BigIntegerField(db_column='AET_CLIENT_ID', default=0)
    aetDateTime = models.DateTimeField(db_column='AET_DATE_TIME', null=True, blank=True)
    aetEmbedding = models.JSONField(null=True, blank=True, db_column='AET_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_APPOINTMENT_EVENT_TYPE'
        managed = False


class CalendarAppointmentSms(models.Model):
    casId = models.BigAutoField(db_column='CAS_ID', primary_key=True)
    casMessage = models.CharField(db_column='CAS_MESSAGE', max_length=2000, null=True, blank=True)
    casFromNumber = models.CharField(db_column='CAS_FROM_NUMBER', max_length=255, null=True, blank=True)
    casTotalMember = models.BigIntegerField(db_column='CAS_TOTAL_MEMBER', null=True, blank=True)
    casMemberId = models.BigIntegerField(db_column='CAS_CLIENT_ID', null=True, blank=True)
    casDateTime = models.DateTimeField(db_column='CAS_DATE_TIME', null=True, blank=True)
    casCalId = models.BigIntegerField(db_column='CAS_CAL_ID', default=0)
    casEmbedding = models.JSONField(null=True, blank=True, db_column='CAS_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_APPOINTMENT_SMS'
        managed = False


class CalendarAppointmentSmsDetails(models.Model):
    casdId = models.BigAutoField(db_column='ASD_ID', primary_key=True)
    casdCasId = models.BigIntegerField(db_column='ASD_CAS_ID', null=True, blank=True)
    casdToNumber = models.CharField(db_column='ASD_TO_NUMBER', max_length=255, null=True, blank=True)
    casdStatus = models.CharField(db_column='ASD_STATUS', max_length=255, null=True, blank=True)
    casdErrorCode = models.CharField(db_column='ASD_ERROR_CODE', max_length=255, null=True, blank=True)
    casdErrorMessage = models.CharField(db_column='ASD_ERROR_MESSAGE', max_length=250, null=True, blank=True)
    casdSid = models.CharField(db_column='ASD_SID', max_length=255, null=True, blank=True)
    asdEmbedding = models.JSONField(null=True, blank=True, db_column='ASD_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_APPOINTMENT_SMS_DETAILS'
        managed = False


class CalendarNotification(models.Model):
    calnId = models.BigAutoField(db_column='CN_ID', primary_key=True)
    calnCalId = models.BigIntegerField(db_column='CN_CAL_ID', null=True, blank=True)
    calnMinutes = models.BigIntegerField(db_column='CN_MINUTES', null=True, blank=True)
    calnCreatedDateTime = models.DateTimeField(db_column='CN_CREATED_DATE_TIME', null=True, blank=True)
    calnSendDateTime = models.DateTimeField(db_column='CALN_SEND_DATE_TIME', null=True, blank=True)
    calnNotification = models.CharField(db_column='CN_NOTIFICATION', max_length=1, default='N')
    cnEmbedding = models.JSONField(null=True, blank=True, db_column='CN_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_NOTIFICATION'
        managed = False


class ShareAppointmentLink(models.Model):
    salId = models.BigAutoField(db_column='SAL_ID', primary_key=True)
    salMessage = models.CharField(db_column='SAL_MESSAGE', max_length=250, null=True, blank=True)
    salFromNumber = models.CharField(db_column='SAL_FROM_NUMBER', max_length=255, null=True, blank=True)
    salTotalMember = models.BigIntegerField(db_column='SAL_TOTAL_MEMBER', null=True, blank=True)
    salMemberId = models.BigIntegerField(db_column='SAL_CLIENT_ID', null=True, blank=True)
    salDateTime = models.DateTimeField(db_column='SAL_DATE_TIME', null=True, blank=True)
    salEmbedding = models.JSONField(null=True, blank=True, db_column='SAL_EMBEDDING')

    class Meta:
        db_table = 'SHARE_APPOINTMENT_LINKS'
        managed = False


class ShareAppointmentLinkDetails(models.Model):
    saldId = models.BigAutoField(db_column='ALD_ID', primary_key=True)
    saldSalId = models.BigIntegerField(db_column='ALD_SAL_ID', null=True, blank=True)
    saldToNumber = models.CharField(db_column='ALD_TO_NUMBER', max_length=255, null=True, blank=True)
    saldStatus = models.CharField(db_column='ALD_STATUS', max_length=255, null=True, blank=True)
    saldErrorCode = models.CharField(db_column='ALD_ERROR_CODE', max_length=255, null=True, blank=True)
    saldErrorMessage = models.CharField(db_column='ALD_ERROR_MESSAGE', max_length=250, null=True, blank=True)
    saldSid = models.CharField(db_column='ALD_SID', max_length=255, null=True, blank=True)
    aldEmbedding = models.JSONField(null=True, blank=True, db_column='ALD_EMBEDDING')

    class Meta:
        db_table = 'SHARE_APPOINTMENT_LINK_DETAILS'
        managed = False


class CalendarDetails(models.Model):
    caldId = models.BigAutoField(db_column='CD_ID', primary_key=True)
    caldCalId = models.BigIntegerField(db_column='CD_CAL_ID', null=True, blank=True)
    caldType = models.CharField(db_column='CD_TYPE', max_length=255, null=True, blank=True)
    caldSycId = models.CharField(db_column='CD_SYC_ID', max_length=255, null=True, blank=True)
    cdEmbedding = models.JSONField(null=True, blank=True, db_column='CD_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_DETAILS'
        managed = False


class TimeZoneList(models.Model):
    tmzId = models.BigAutoField(db_column='TZL_ID', primary_key=True)
    tmzTitle = models.CharField(db_column='TZL_TITLE', max_length=255)
    tmzValue = models.CharField(db_column='TZL_VALUE', max_length=255)

    class Meta:
        db_table = 'TIME_ZONE_LIST'
        managed = False


class CalendarNotificationReminder(models.Model):
    calnId = models.BigAutoField(db_column='CNR_ID', primary_key=True)
    calnCalId = models.BigIntegerField(db_column='CNR_CAL_ID', null=True, blank=True)
    calnCreatedDateTime = models.DateTimeField(db_column='CNR_CREATED_DATE_TIME', null=True, blank=True)
    calnSendDateTime = models.DateTimeField(db_column='CNR_SEND_DATE_TIME', null=True, blank=True)
    calnNotification = models.CharField(db_column='CNR_NOTIFICATION', max_length=1, default='N')
    calnReminderType = models.CharField(db_column='CALN_REMINDER_TYPE', max_length=255, null=True, blank=True)
    cnrEmbedding = models.JSONField(null=True, blank=True, db_column='CNR_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_NOTIFICATION_REMINDER'
        managed = False


class CalendarReminderSmsDetails(models.Model):
    crsdId = models.BigAutoField(db_column='RSD_ID', primary_key=True)
    crsdCrsId = models.BigIntegerField(db_column='RSD_CRS_ID', null=True, blank=True)
    crsdToNumber = models.CharField(db_column='RSD_TO_NUMBER', max_length=255, null=True, blank=True)
    crsdStatus = models.CharField(db_column='RSD_STATUS', max_length=255, null=True, blank=True)
    crsdErrorCode = models.CharField(db_column='RSD_ERROR_CODE', max_length=255, null=True, blank=True)
    crsdErrorMessage = models.CharField(db_column='RSD_ERROR_MESSAGE', max_length=250, null=True, blank=True)
    crsdSid = models.CharField(db_column='RSD_SID', max_length=255, null=True, blank=True)
    rsdEmbedding = models.JSONField(null=True, blank=True, db_column='RSD_EMBEDDING')

    class Meta:
        db_table = 'CALENDAR_REMINDER_SMS_DETAILS'
        managed = False

class CalendarSetup(models.Model):
    csId = models.BigAutoField(db_column='CS_ID', primary_key=True)
    csClientId = models.BigIntegerField(db_column='CS_CLIENT_ID')
    csCalendarType = models.CharField(db_column='CS_CALENDAR_TYPE', max_length=25, null=True, blank=True)
    csCalendarName = models.CharField(db_column='CS_CALENDAR_NAME', max_length=25, null=True, blank=True)
    csAccessToken = models.TextField(db_column='CS_ACCESS_TOKEN', null=True, blank=True)
    csRefreshToken = models.TextField(db_column='CS_REFRESH_TOKEN', null=True, blank=True)
    csRefreshTime = models.CharField(db_column='CS_REFRESH_TIME', max_length=250, null=True, blank=True)
    csWebConferenceUrl = models.CharField(db_column='CS_WEB_CONFERENCE_URL', max_length=100, null=True, blank=True)
    csDefaultCalendar = models.CharField(db_column='CS_DEFAULT_CALENDAR', max_length=1, null=True, blank=True)
    csEmailNotification = models.CharField(db_column='CS_EMAIL_NOTIFICATION', max_length=250, null=True, blank=True)
    csSmsNotification = models.CharField(db_column='CS_SMS_NOTIFICATION', max_length=1, null=True, blank=True)
    csEmail = models.CharField(db_column='CS_EMAIL', max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'CALENDAR_SETUP'
        managed = False

class CallingParent(models.Model):
    cp_id = models.BigAutoField(primary_key=True, db_column='CP_ID')
    cp_twilio_no = models.CharField(max_length=255, db_column='CP_PHONE_NO', null=True, blank=True)
    cp_member_id = models.BigIntegerField(db_column='CP_CLIENT_ID', null=True, blank=True)
    cp_member_phone_no = models.CharField(max_length=255, db_column='CP_CLIENT_PHONE_NO', null=True, blank=True)
    cp_start_time = models.DateTimeField(db_column='CP_START_TIME', null=True, blank=True)
    cp_end_time = models.DateTimeField(db_column='CP_END_TIME', null=True, blank=True)
    cp_duration = models.FloatField(db_column='CP_DURATION', default=0.0)
    cp_sid = models.CharField(max_length=255, db_column='CP_SID', null=True, blank=True)
    cp_token = models.CharField(max_length=2000, db_column='CP_TOKEN', null=True, blank=True)
    cp_call_stop = models.CharField(max_length=1, db_column='CP_CALL_STOP', default='N')
    cp_date = models.DateTimeField(db_column='CP_DATE', null=True, blank=True)
    cp_embedding = models.JSONField(null=True, blank=True, db_column='CP_EMBEDDING')

    class Meta:
        db_table = 'CALLING_PARENT'
        managed = False


class CallingChild(models.Model):
    cc_id = models.BigAutoField(primary_key=True, db_column='CC_ID')
    cc_cp_id = models.BigIntegerField(db_column='CC_CP_ID', null=True, blank=True)
    cc_client_id = models.BigIntegerField(db_column='CC_CLIENT_ID', null=True, blank=True)
    cc_client_phone_no = models.CharField(max_length=255, db_column='CC_CLIENT_PHONE_NO', null=True, blank=True)
    cc_sid = models.CharField(max_length=255, db_column='CC_SID', null=True, blank=True)
    cc_start_time = models.DateTimeField(db_column='CC_START_TIME', null=True, blank=True)
    cc_end_time = models.DateTimeField(db_column='CC_END_TIME', null=True, blank=True)
    cc_duration = models.FloatField(db_column='CC_DURATION', default=0.0)
    cc_embedding = models.JSONField(null=True, blank=True, db_column='CC_EMBEDDING')

    class Meta:
        db_table = 'CALLING_CHILD'
        managed = False


class CallingIncoming(models.Model):
    cin_id = models.BigAutoField(primary_key=True, db_column='CI_ID')
    cin_session_id = models.CharField(max_length=255, db_column='CI_SESSION_ID', null=True, blank=True)
    cin_from = models.CharField(max_length=255, db_column='CI_FROM', null=True, blank=True)
    cin_to = models.CharField(max_length=255, db_column='CI_TO', null=True, blank=True)
    cin_start_time = models.DateTimeField(db_column='CI_START_TIME', null=True, blank=True)
    cin_end_time = models.DateTimeField(db_column='CI_END_TIME', null=True, blank=True)
    cin_duration = models.FloatField(db_column='CI_DURATION', default=0.0)
    cin_member_id = models.BigIntegerField(db_column='CI_CLIENT_ID', default=0)
    cin_call_stop = models.CharField(max_length=1, db_column='CI_CALL_STOP', default='N')
    cin_date = models.DateTimeField(db_column='CI_DATE', null=True, blank=True)
    ci_embedding = models.JSONField(null=True, blank=True, db_column='CI_EMBEDDING')

    class Meta:
        db_table = 'CALLING_INCOMING'
        managed = False


class ContactSendSmsLogs(models.Model):
    id = models.BigAutoField(db_column='SSL_ID', primary_key=True)
    member_id = models.BigIntegerField(db_column='SSL_CLIENT_ID', null=True, blank=True)
    email_id = models.BigIntegerField(db_column='SSL_EMAIL_ID', null=True, blank=True)
    sid = models.CharField(db_column='SSL_SID', max_length=255, null=True, blank=True)
    sms_status = models.CharField(db_column='SSL_SMS_STATUS', max_length=255, null=True, blank=True)
    error_message = models.CharField(db_column='SSL_ERROR_MESSAGE', max_length=500, null=True, blank=True)
    error_code = models.CharField(db_column='ERROR_CODE', max_length=255, null=True, blank=True)
    from_contact = models.CharField(db_column='SSL_FROM_CONTACT', max_length=255, null=True, blank=True)
    to_contact = models.CharField(db_column='SSL_TO_CONTACT', max_length=255, null=True, blank=True)
    sms_detail = models.CharField(db_column='SSL_SMS_DETAIL', max_length=4000, null=True, blank=True)
    sms_send_date = models.DateTimeField(db_column='SSL_SMS_SEND_DATE', null=True, blank=True)
    group_id = models.BigIntegerField(db_column='SSL_GROUP_ID', null=True, blank=True)
    ssl_embedding = models.JSONField(null=True, blank=True, db_column='SSL_EMBEDDING')

    class Meta:
        db_table = 'CONTACT_SMS_LOG'
        managed = False


class MyCrmSendEmail(models.Model):
    send_id = models.BigAutoField(db_column='SM_ID', primary_key=True)
    send_subject = models.CharField(db_column='SM_SEND_SUBJECT', max_length=255, null=True, blank=True)
    send_from_name = models.CharField(db_column='SM_SEND_FROM_NAME', max_length=255, null=True, blank=True)
    send_from_email = models.CharField(db_column='SM_SEND_FROM_EMAIL', max_length=255, null=True, blank=True)
    send_reply_to_email = models.CharField(db_column='SM_SEND_REPLY_TO_EMAIL', max_length=255, null=True, blank=True)
    send_to_email = models.CharField(db_column='SM_SEND_TO_EMAIL', max_length=255, null=True, blank=True)
    send_email_details = models.TextField(db_column='SM_SEND_EMAIL_DETAILS', null=True, blank=True)
    send_member_id = models.BigIntegerField(db_column='SM_CLIENT_ID', null=True, blank=True)

    class Meta:
        db_table = 'MYCRM_SEND_EMAIL'
        managed = False


class AutomationLinkClickEmail(models.Model):
    sendId = models.BigAutoField(primary_key=True, db_column='LCE_ID')
    sendSubject = models.CharField(max_length=255, null=True, blank=True, db_column='LCE_SUBJECT')
    sendFromName = models.CharField(max_length=255, null=True, blank=True, db_column='LCE_FROM_NAME')
    sendFromEmail = models.CharField(max_length=255, null=True, blank=True, db_column='LCE_FROM_EMAIL')
    sendReplyToEmail = models.CharField(max_length=255, null=True, blank=True, db_column='LCE_REPLY_TO_EMAIL')
    sendToEmail = models.CharField(max_length=255, null=True, blank=True, db_column='LCE_TO_EMAIL')
    sendEmailDetails = models.TextField(null=True, blank=True, db_column='LCE_EMAIL_DETAILS')
    sendMemberId = models.BigIntegerField(null=True, blank=True, db_column='LCE_CLIENT_ID')
    sendLinkId = models.BigIntegerField(null=True, blank=True, db_column='LCE_LINK_ID')
    sendNodeId = models.BigIntegerField(null=True, blank=True, db_column='LCE_NODE_ID')
    sendAutomationId = models.BigIntegerField(null=True, blank=True, db_column='LCE_AUT_ID')
    sendDateTime = models.DateTimeField(null=True, blank=True, db_column='LCE_SEND_DATE_TIME')
    lceEmbedding = models.JSONField(null=True, blank=True, db_column='LCE_EMBEDDING')

    class Meta:
        db_table = 'AUTOMATION_LINK_CLICK_EMAIL'
        managed = False


class UnsubscribeLogs(models.Model):
    id = models.BigAutoField(db_column='UL_ID', primary_key=True)
    member_id = models.BigIntegerField(db_column='UL_CLIENT_ID', default=0)
    email = models.CharField(db_column='UL_EMAIL', max_length=255, null=True, blank=True)
    campaign_id = models.BigIntegerField(db_column='UL_CAMPAIGN_ID', null=True, blank=True)
    created_date = models.DateTimeField(db_column='UL_CREATED_DATE', null=True, blank=True)

    class Meta:
        db_table = 'UNSUBSCRIBE_LOGS'
        managed = False


class AutomationSmsReplyLog(models.Model):
    log_id = models.BigAutoField(primary_key=True, db_column='SRL_ID')
    log_sms_id = models.BigIntegerField(db_column='SRL_SMS_ID', default=0)
    log_to_number = models.CharField(db_column='SRL_TO_NUMBER', max_length=255, null=True, blank=True)
    log_from_number = models.CharField(db_column='SRL_FROM_NUMBER', max_length=255, null=True, blank=True)
    log_status = models.CharField(db_column='LOG_STATUS', max_length=255, null=True, blank=True)
    log_sid = models.CharField(db_column='LOG_SID', max_length=255, null=True, blank=True)
    log_error_message = models.CharField(db_column='SRL_ERROR_MESSAGE', max_length=255, null=True, blank=True)
    log_error_code = models.CharField(db_column='SRL_ERROR_CODE', max_length=255, null=True, blank=True)
    log_member_id = models.BigIntegerField(db_column='SRL_CLIENT_ID', default=0)
    log_created_date = models.DateTimeField(db_column='SRL_CREATED_DATE', auto_now_add=True)
    log_receive_reply = models.CharField(db_column='SRL_RECEIVE_REPLY', max_length=2000, null=True, blank=True)
    log_send_reply_details = models.CharField(db_column='SRL_SEND_REPLY_DETAILS', max_length=2000, null=True, blank=True)
    srl_embedding = models.JSONField(null=True, blank=True, db_column='SRL_EMBEDDING')

    class Meta:
        db_table = 'AUTOMATION_SMS_REPLY_LOG'
        managed = False


class TempUserlist(models.Model):
    emailId = models.BigAutoField(db_column='TUL_EMAIL_ID', primary_key=True)
    birthday = models.CharField(db_column='TUL_BIRTHDAY', max_length=255, null=True, blank=True)
    city = models.CharField(db_column='TUL_CITY', max_length=255, null=True, blank=True)
    country = models.CharField(db_column='TUL_COUNTRY', max_length=255, null=True, blank=True)
    dateAdded = models.CharField(db_column='TUL_DATE_ADDED', max_length=255, null=True, blank=True)
    dateLastModified = models.CharField(db_column='TUL_DATE_LAST_MODIFIED', max_length=255, null=True, blank=True)
    email = models.CharField(db_column='TUL_EMAIL', max_length=255)
    firstName = models.CharField(db_column='TUL_FIRST_NAME', max_length=250, null=True, blank=True)
    gender = models.CharField(db_column='TUL_GENDER', max_length=255, null=True, blank=True)
    lastName = models.CharField(db_column='TUL_LAST_NAME', max_length=250, null=True, blank=True)
    optDate = models.CharField(db_column='TUL_OPT_DATE', max_length=255, null=True, blank=True)
    phoneNumber = models.CharField(db_column='TUL_PHONE_NUMBER', max_length=255, null=True, blank=True)
    stateProvRegion = models.CharField(db_column='TUL_STATE_PROV_REGION', max_length=255, null=True, blank=True)
    status = models.CharField(db_column='TUL_STATUS', max_length=255, null=True, blank=True)
    streetAddress1 = models.TextField(db_column='TUL_STREET_ADDRESS1', null=True, blank=True)
    streetAddress2 = models.TextField(db_column='TUL_STREET_ADDRESS2', null=True, blank=True)
    fullName = models.CharField(db_column='TUL_FULL_NAME', max_length=255, null=True, blank=True)
    phone = models.CharField(db_column='TUL_CELL_PHONE', max_length=255, null=True, blank=True)
    tags = models.CharField(db_column='TUL_TAGS', max_length=250, null=True, blank=True)
    transId = models.CharField(db_column='TUL_TRANS_ID', max_length=500, null=True, blank=True)
    udf1 = models.CharField(db_column='TUL_UDF1', max_length=250, null=True, blank=True)
    udf10 = models.CharField(db_column='TUL_UDF10', max_length=250, null=True, blank=True)
    udf2 = models.CharField(db_column='TUL_UDF2', max_length=250, null=True, blank=True)
    udf3 = models.CharField(db_column='TUL_UDF3', max_length=250, null=True, blank=True)
    udf4 = models.CharField(db_column='TUL_UDF4', max_length=250, null=True, blank=True)
    udf5 = models.CharField(db_column='TUL_UDF5', max_length=250, null=True, blank=True)
    udf6 = models.CharField(db_column='TUL_UDF6', max_length=250, null=True, blank=True)
    udf7 = models.CharField(db_column='TUL_UDF7', max_length=250, null=True, blank=True)
    udf8 = models.CharField(db_column='TUL_UDF8', max_length=250, null=True, blank=True)
    udf9 = models.CharField(db_column='TUL_UDF9', max_length=250, null=True, blank=True)
    zipPostalCode = models.CharField(db_column='TUL_ZIP_POSTAL_CODE', max_length=255, null=True, blank=True)
    memberId = models.BigIntegerField(db_column='TUL_CLIENT_ID', null=True, blank=True)
    usDefaultLanguage = models.CharField(db_column='TUL_US_DEFAULT_LANGUAGE', max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'TEMP_USER_LIST'
        managed = False


class TempCronUserListTotal(models.Model):
    cronId = models.BigAutoField(db_column='CRON_ID', primary_key=True)
    cronMemberId = models.BigIntegerField(db_column='CRON_CLIENT_ID')
    cronGroupId = models.BigIntegerField(db_column='CRON_GROUP_ID')
    cronStartId = models.BigIntegerField(db_column='CRON_START_ID')
    cronEndId = models.BigIntegerField(db_column='CRON_END_ID')
    cronProcess = models.CharField(db_column='CRON_PROCESS', max_length=1, null=True, blank=True)
    cronProcessFinished = models.CharField(db_column='CRON_PROCESS_FINISHED', max_length=1, null=True, blank=True)
    cronOptInMessage = models.CharField(db_column='CRON_OPT_IN_MESSAGE', max_length=250, null=True, blank=True)
    transId = models.CharField(db_column='CRON_TRANS_ID', max_length=255, null=True, blank=True)
    cronCheckDuplicateYN = models.CharField(db_column='CRON_CHECK_DUPLICATE_YN', max_length=1, default='N')
    cronOptInYN = models.CharField(db_column='CRON_OPT_IN_YN', max_length=1, default='N')
    cronEmailVerification = models.CharField(db_column='CRON_EMAIL_VERIFICATION', max_length=1, default='N')
    swapColumns = models.CharField(db_column='CRON_SWAP_COLUMNS', max_length=2000, null=True, blank=True)
    blankFieldsList = models.CharField(db_column='CRON_BLANK_FIELDS_LIST', max_length=250, null=True, blank=True)
    moveList = models.TextField(db_column='CRON_MOVE_LIST', null=True, blank=True)

    class Meta:
        db_table = 'TEMP_CRON_CONTACTS_TOTAL'
        managed = False


class EmailVerification(models.Model):
    evId = models.BigAutoField(db_column='EV_ID', primary_key=True)
    evFileName = models.CharField(db_column='EV_FILE_NAME', max_length=255, null=True, blank=True)
    evFileId = models.CharField(db_column='EV_FILE_ID', max_length=255, null=True, blank=True)
    evFileStatus = models.CharField(db_column='EV_FILE_STATUS', max_length=255, null=True, blank=True)
    evTotalRecords = models.IntegerField(db_column='EV_TOTAL_RECORDS')
    evFileUpload = models.CharField(db_column='EV_FILE_UPLOAD', max_length=1)
    evFileUploadError = models.CharField(db_column='EV_FILE_UPLOAD_ERROR', max_length=250, null=True, blank=True)
    evFileDownload = models.CharField(db_column='EV_FILE_DOWNLOAD', max_length=1)
    evFileDownloadError = models.TextField(db_column='EV_FILE_DOWNLOAD_ERROR', null=True, blank=True)
    evBounceRate = models.FloatField(db_column='EV_BOUNCE_RATE')
    evGroupId = models.BigIntegerField(db_column='EV_GROUP_ID', null=True, blank=True)
    evMemberId = models.BigIntegerField(db_column='EV_CLIENT_ID', null=True, blank=True)
    evDateTime = models.DateTimeField(db_column='EV_DATE_TIME', null=True, blank=True)
    evOptInYN = models.CharField(db_column='EV_OPTIN_YN', max_length=1, default='N')
    evStep = models.BigIntegerField(db_column='EV_STEP', default=1)

    class Meta:
        db_table = 'EMAIL_VERIFICATION'
        managed = False

class RegistrationSteps(models.Model):
    rl_id = models.BigAutoField(primary_key=True, db_column='RL_ID')
    rl_username = models.CharField(max_length=255, db_column='RL_USERNAME', null=True, blank=True)
    rl_email = models.CharField(max_length=255, db_column='RL_EMAIL', null=True, blank=True)
    rl_first_name = models.CharField(max_length=255, db_column='RL_FIRST_NAME', null=True, blank=True)
    rl_last_name = models.CharField(max_length=255, db_column='RL_LAST_NAME', null=True, blank=True)
    rl_cell = models.CharField(max_length=255, db_column='RL_CELL', null=True, blank=True)
    rl_step = models.IntegerField(db_column='RL_STEP', default=0, null=True, blank=True)
    rl_status = models.CharField(max_length=255, db_column='RL_STATUS', null=True, blank=True)
    rl_created_date = models.DateTimeField(db_column='RL_CREATED_DATE', null=True, blank=True)

    class Meta:
        db_table = 'REGISTRATION_STEPS'
        managed = False

class DomainEmails(models.Model):
    de_id = models.BigAutoField(primary_key=True, db_column='DE_ID')
    de_client_id = models.IntegerField(db_column='DE_CLIENT_ID', null=True, blank=True)
    de_did = models.IntegerField(db_column='DE_DID', null=True, blank=True)
    de_email = models.CharField(max_length=255, db_column='DE_EMAIL', null=True, blank=True)
    de_create_date = models.DateTimeField(db_column='DE_CREATE_DATE', null=True, blank=True)
    de_embedding = models.JSONField(null=True, blank=True, db_column='DE_EMBEDDING')

    class Meta:
        db_table = 'DOMAIN_EMAILS'
        managed = False

class Zoom(models.Model):
    zmId = models.BigAutoField(db_column='zm_id', primary_key=True)
    zmType = models.IntegerField(db_column='zm_type', null=True, blank=True)
    zmStartTime = models.DateTimeField(db_column='zm_start_time', null=True, blank=True)
    zmJoinUrl = models.CharField(db_column='zm_join_url', max_length=2000, null=True, blank=True)
    zmPassword = models.CharField(db_column='zm_password', max_length=255, null=True, blank=True)
    zmMemberId = models.BigIntegerField(db_column='zm_member_id', null=True, blank=True)
    zmDate = models.DateTimeField(db_column='zm_date', null=True, blank=True)
    subMemberId = models.BigIntegerField(db_column='sub_member_id', default=0)

    class Meta:
        db_table = 'tbl_zoom'
        managed = False

class ZoomDetails(models.Model):
    zmdId = models.BigAutoField(db_column='zmd_id', primary_key=True)
    zmdZmId = models.BigIntegerField(db_column='zmd_zm_id', null=True, blank=True)
    zmdClientId = models.BigIntegerField(db_column='zmd_client_id', null=True, blank=True)

    class Meta:
        db_table = 'tbl_zoom_details'
        managed = False


class EiSocialMedia(models.Model):
    smId = models.BigAutoField(db_column='SP_ID', primary_key=True)
    publishDateTime = models.DateTimeField(db_column='SP_PUBLISH_DATETIME', null=True, blank=True)
    publishStatus = models.IntegerField(db_column='SP_PUBLISH_STATUS', null=True, blank=True)
    publishType = models.CharField(db_column='SP_PUBLISH_TYPE', max_length=50, null=True, blank=True)
    smFacebookPost = models.TextField(db_column='SP_FACEBOOK_POST', null=True, blank=True)
    smLinkedinPost = models.TextField(db_column='SP_LINKEDIN_POST', null=True, blank=True)
    smName = models.TextField(db_column='SP_NAME')
    smPostImage = models.TextField(db_column='SP_POST_IMAGE', null=True, blank=True)
    smPostVideoFacebook = models.TextField(db_column='SP_POST_VIDEO_FACEBOOK', null=True, blank=True)
    smPostVideoTwitter = models.TextField(db_column='SP_POST_VIDEO_TWITTER', null=True, blank=True)
    smPostVideoLinkedin = models.TextField(db_column='SP_POST_VIDEO_LINKEDIN', null=True, blank=True)
    smTwitterPost = models.TextField(db_column='SP_TWITTER_POST', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='SP_CLIENT_ID', null=True, blank=True)
    spEmbedding = models.JSONField(null=True, blank=True, db_column='SP_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_POSTINGS'
        managed = False


class EiSocialMediaPublish(models.Model):
    smpId = models.BigAutoField(db_column='SP_ID', primary_key=True)
    memberId = models.BigIntegerField(db_column='SP_CLIENT_ID', null=True, blank=True)
    smId = models.BigIntegerField(db_column='SP_POST_ID', null=True, blank=True)
    smpPublishFor = models.CharField(db_column='SP_PUBLISH_FOR', max_length=50, null=True, blank=True)
    smpPublishData = models.TextField(db_column='SP_PUBLISH_DATA', null=True, blank=True)
    smpPublishLink = models.CharField(db_column='SP_PUBLISH_LINK', max_length=2000, null=True, blank=True)
    smpPublishImage = models.TextField(db_column='SP_PUBLISH_IMAGE', null=True, blank=True)
    smpPublishVideoFacebook = models.TextField(db_column='SP_PUBLISH_VIDEO_FACEBOOK', null=True, blank=True)
    smpPublishVideoTwitter = models.TextField(db_column='SP_PUBLISH_VIDEO_TWITTER', null=True, blank=True)
    smpPublishVideoLinkedin = models.TextField(db_column='SP_PUBLISH_VIDEO_LINKEDIN', null=True, blank=True)
    smpResponse = models.TextField(db_column='SP_RESPONSE', null=True, blank=True)
    smpStatus = models.IntegerField(db_column='SP_PUBLISH_STATUS', default=0)
    smpPublishDateTime = models.DateTimeField(db_column='SP_PUBLISH_DATETIME', null=True, blank=True)
    smpScheduleDateTime = models.DateTimeField(db_column='SP_SCHEDULE_DATETIME', null=True, blank=True)
    linkdinIds = models.TextField(db_column='SP_LINKDIN_IDS', null=True, blank=True)
    hasVideo = models.CharField(db_column='SP_HAS_VIDEO', max_length=1, default='N')
    isProcessed = models.CharField(db_column='SP_IS_PROCESSED', max_length=1, default='N')
    spEmbedding = models.JSONField(null=True, blank=True, db_column='SP_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_PUBLISH'
        managed = False

class EiSocialMediaFacebookReport(models.Model):
    sfrId = models.BigAutoField(db_column='SFR_ID', primary_key=True)
    memberId = models.BigIntegerField(db_column='SFR_CLIENT_ID', null=True, blank=True)
    sfrSmpId = models.BigIntegerField(db_column='SFR_SP_ID', null=True, blank=True)
    sfrPageId = models.CharField(db_column='SFR_PAGE_ID', max_length=50, null=True, blank=True)
    sfrDate = models.DateField(db_column='SFR_DATE', null=True, blank=True)
    sfrPeopleReached = models.IntegerField(db_column='SFR_PEOPLE_REACHED', null=True, blank=True)
    sfrEngagements = models.IntegerField(db_column='SFR_ENGAGEMENTS', null=True, blank=True)
    sfrTotalReactions = models.IntegerField(db_column='SFR_TOTAL_REACTIONS', null=True, blank=True)
    sfrTotalComments = models.IntegerField(db_column='SFR_TOTAL_COMMENTS', null=True, blank=True)
    sfrEmbedding = models.JSONField(null=True, blank=True, db_column='SFR_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_FACEBOOK_REPORT'
        managed = False


class EiSocialMediaTwitterReport(models.Model):
    stwrId = models.BigAutoField(db_column='STR_ID', primary_key=True)
    memberId = models.BigIntegerField(db_column='STR_CLIENT_ID', null=True, blank=True)
    stwrSmpId = models.BigIntegerField(db_column='STR_SP_ID', null=True, blank=True)
    stwrDate = models.DateField(db_column='STR_DATE', null=True, blank=True)
    stwrTotalRetweets = models.IntegerField(db_column='STR_TOTAL_RETWEETS', null=True, blank=True)
    stwrTotalLikes = models.IntegerField(db_column='STR_TOTAL_LIKES', null=True, blank=True)
    strEmbedding = models.JSONField(null=True, blank=True, db_column='STR_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_TWITTER_REPORT'
        managed = False


class EiSocialMediaLinkedinReport(models.Model):
    slrId = models.BigAutoField(db_column='SLR_ID', primary_key=True)
    memberId = models.BigIntegerField(db_column='SLR_CLIENT_ID', null=True, blank=True)
    slrSmpId = models.BigIntegerField(db_column='SLR_SP_ID', null=True, blank=True)
    slrDate = models.DateField(db_column='SLR_DATE', null=True, blank=True)
    slrTotalReactions = models.IntegerField(db_column='SLR_TOTAL_REACTIONS', null=True, blank=True)
    slrTotalComments = models.IntegerField(db_column='SLR_TOTAL_COMMENTS', null=True, blank=True)
    slrPageId = models.CharField(db_column='SLR_PAGE_ID', max_length=100, null=True, blank=True)
    slrEmbedding = models.JSONField(null=True, blank=True, db_column='SLR_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_LINKEDIN_REPORT'
        managed = False


class EiSocialMediaFacebookReaction(models.Model):
    sfraId = models.BigAutoField(db_column='SFR_ID', primary_key=True)
    sfraSfrId = models.BigIntegerField(db_column='SFR_SFR_ID', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='SFR_CLIENT_ID', null=True, blank=True)
    sfraLikesCares = models.IntegerField(db_column='SFR_LIKES_CARES', null=True, blank=True)
    sfraLoves = models.IntegerField(db_column='SFR_LOVES', null=True, blank=True)
    sfraHahas = models.IntegerField(db_column='SFR_HAHAS', null=True, blank=True)
    sfraWows = models.IntegerField(db_column='SFR_WOWS', null=True, blank=True)
    sfraSads = models.IntegerField(db_column='SFR_SADS', null=True, blank=True)
    sfraAngries = models.IntegerField(db_column='SFR_ANGRIES', null=True, blank=True)
    sfrEmbedding = models.JSONField(null=True, blank=True, db_column='SFR_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_FACEBOOK_REACTION'
        managed = False


class EiSocialMediaLinkedinReaction(models.Model):
    slraId = models.BigAutoField(db_column='SLR_ID', primary_key=True)
    slraSlrId = models.BigIntegerField(db_column='SLR_SLR_ID', null=True, blank=True)
    memberId = models.BigIntegerField(db_column='SLR_CLIENT_ID', null=True, blank=True)
    slraLikes = models.IntegerField(db_column='SLR_LIKES', null=True, blank=True)
    slraCelebrates = models.IntegerField(db_column='SLR_CELEBRATES', null=True, blank=True)
    slraSupports = models.IntegerField(db_column='SLR_SUPPORTS', null=True, blank=True)
    slraLoves = models.IntegerField(db_column='SLR_LOVES', null=True, blank=True)
    slraInsightfuls = models.IntegerField(db_column='SLR_INSIGHTFULS', null=True, blank=True)
    slraCuriouses = models.IntegerField(db_column='SLR_CURIOUSES', null=True, blank=True)
    slrEmbedding = models.JSONField(null=True, blank=True, db_column='SLR_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_LINKEDIN_REACTION'
        managed = False


class EiSocialMediaComment(models.Model):
    scId = models.BigAutoField(db_column='SC_ID', primary_key=True)
    scParentId = models.BigIntegerField(db_column='SC_PARENT_ID', null=True, blank=True)
    scSocialMediaName = models.CharField(db_column='SC_SOCIALMEDIA_NAME', max_length=50, null=True, blank=True)
    scUser = models.CharField(db_column='SC_USER', max_length=100, null=True, blank=True)
    scComment = models.CharField(db_column='SC_COMMENT', max_length=2000, null=True, blank=True)
    scEmbedding = models.JSONField(null=True, blank=True, db_column='SC_EMBEDDING')

    class Meta:
        db_table = 'SOCIALMEDIA_COMMENT'
        managed = False

class ClientWebsitesAnalytics(models.Model):
    cwa_id = models.BigAutoField(primary_key=True, db_column='CWA_ID')
    cwa_client_id = models.BigIntegerField(null=True, blank=True, db_column='CWA_CLIENT_ID')
    cwa_website_url = models.CharField(max_length=250, db_column='CWA_WEBSITE_URL')
    cwa_analytics_web_id = models.CharField(max_length=250, db_column='CWA_ANALYTICS_WEB_ID')
    cwa_generation_date = models.DateTimeField(null=True, blank=True, db_column='CWA_GENERATION_DATE')
    cwa_embedding = models.JSONField(null=True, blank=True, db_column='CWA_EMBEDDING')
    class Meta:
        db_table = 'CLIENT_WEBSITES_ANALYTICS'
        managed = False

class DeleteAccount(models.Model):
    daId = models.BigAutoField(db_column='DA_ID', primary_key=True)
    daAccountId = models.BigIntegerField(db_column='DA_ACCOUNT_ID', null=True, blank=True)
    daAccountName = models.CharField(db_column='DA_ACCOUNT_NAME', max_length=255, null=True, blank=True)
    daEmail = models.CharField(db_column='DA_EMAIL', max_length=255, null=True, blank=True)
    daIpAddress = models.CharField(db_column='DA_IP_ADDRESS', max_length=255, null=True, blank=True)
    daDateTime = models.CharField(db_column='DA_DATE_TIME', max_length=255, null=True, blank=True)
    daLeavingDetails = models.CharField(db_column='DA_LEAVING_DETAILS', max_length=2000, null=True, blank=True)
    daACN = models.TextField(db_column='DA_ACN', null=True, blank=True)

    class Meta:
        db_table = 'DELETE_ACCOUNT'
        managed = False

class TblSettings(models.Model):
    id = models.BigAutoField(primary_key=True)
    admin_name = models.CharField(max_length=255, null=True, blank=True)
    admin_email = models.CharField(max_length=255, null=True, blank=True)
    facebook_link = models.CharField(max_length=255, null=True, blank=True)
    twitter_link = models.CharField(max_length=255, null=True, blank=True)
    gplus_link = models.CharField(max_length=255, null=True, blank=True)
    linkin_link = models.CharField(max_length=255, null=True, blank=True)
    site_on_off = models.CharField(max_length=255, null=True, blank=True)
    logo_name = models.CharField(max_length=255, null=True, blank=True)
    logo_system_name = models.CharField(max_length=255, null=True, blank=True)
    payment_switch = models.CharField(max_length=50, null=True, blank=True)
    bill_period = models.CharField(max_length=255, null=True, blank=True)
    assessmentprice = models.FloatField(null=True, blank=True)
    surveyprice = models.FloatField(null=True, blank=True)
    individualprice = models.FloatField(null=True, blank=True)
    email_bounce_rate = models.IntegerField(default=6, null=True, blank=True)
    throttling_count_days = models.IntegerField(default=0, null=True, blank=True)
    throttling_domain_capacity = models.IntegerField(default=0, null=True, blank=True)
    throttling_last_total_campaigns = models.IntegerField(default=0, null=True, blank=True)
    throttling_bounce_rate_percentage = models.IntegerField(default=0, null=True, blank=True)
    throttling_increase_domain_capacity_percentage = models.IntegerField(default=0, null=True, blank=True)

    class Meta:
        db_table = 'TENANT_SETTINGS'
        managed = False

class Clients(models.Model):
    cliId = models.BigAutoField(db_column='CLI_ID', primary_key=True)
    cliTenantId = models.BigIntegerField(db_column='CLI_TENANT_ID')
    cliName = models.CharField(db_column='CLI_NAME', max_length=50, null=True, blank=True)
    cliType = models.CharField(db_column='CLI_TYPE', max_length=25, null=True, blank=True)
    cliAudience = models.CharField(db_column='CLI_AUDIENCE', max_length=25, null=True, blank=True)
    cliWebsite = models.CharField(db_column='CLI_WEBSITE', max_length=100, null=True, blank=True)
    cliWebsiteColors = models.CharField(db_column='CLI_WEBSITE_COLORS', max_length=2000, null=True, blank=True)
    cliLogo = models.CharField(db_column='CLI_LOGO', max_length=500, null=True, blank=True)
    cliCustomerFooter = models.CharField(db_column='CLI_CUSTOMER_FOOTER', max_length=500, null=True, blank=True)
    cliLinkedin = models.CharField(db_column='CLI_LINKEDIN', max_length=100, null=True, blank=True)
    cliRevenue = models.DecimalField(db_column='CLI_REVENUE', max_digits=10, decimal_places=2, null=True, blank=True)
    cliNumEmployees = models.DecimalField(db_column='CLI_NUM_EMPLOYEES', max_digits=10, decimal_places=2, null=True, blank=True)
    cliStockTicker = models.CharField(db_column='CLI_STOCK_TICKER', max_length=25, null=True, blank=True)
    cli10DlcStatus = models.CharField(db_column='CLI_10DLC_STATUS', max_length=25, null=True, blank=True)
    cliSipFriendlyName = models.CharField(db_column='CLI_SIP_FRIENDLY_NAME', max_length=255, null=True, blank=True)
    cliSmsAccountSid = models.CharField(db_column='CLI_SMS_ACCOUNT_SID', max_length=255, null=True, blank=True)
    cliSipConnectionId = models.CharField(db_column='CLI_SIP_CONNECTION_ID', max_length=255, null=True, blank=True)
    cliSipUsername = models.CharField(db_column='CLI_SIP_USERNAME', max_length=255, null=True, blank=True)
    cliSipPassword = models.CharField(db_column='CLI_SIP_PASSWORD', max_length=255, null=True, blank=True)
    cliBusinessName = models.CharField(db_column='CLI_BUSINESS_NAME', max_length=100, null=True, blank=True)
    cliProfileImageUrl = models.CharField(db_column='CLI_PROFILE_IMAGE_URL', max_length=255, null=True, blank=True)
    cliTimeZone = models.CharField(db_column='CLI_TIME_ZONE', max_length=255, null=True, blank=True)
    cliSubAccountTypeId = models.BigIntegerField(db_column='CLI_SUB_ACCOUNT_TYPE_ID', default=0)
    cliSmsForwardMyphoneYn = models.CharField(db_column='CLI_SMS_FORWARD_MYPHONE_YN', max_length=1, default='Y')
    cliFbId = models.CharField(db_column='CLI_FB_ID', max_length=255, null=True, blank=True)
    cliFbAccessToken = models.CharField(db_column='CLI_FB_ACCESS_TOKEN', max_length=2000, null=True, blank=True)
    cliTwOauthtoken = models.CharField(db_column='CLI_TW_OAUTHTOKEN', max_length=2000, null=True, blank=True)
    cliTwOauthtokenSecret = models.CharField(db_column='CLI_TW_OAUTHTOKEN_SECRET', max_length=2000, null=True, blank=True)
    cliLinAuthToken = models.CharField(db_column='CLI_LIN_AUTH_TOKEN', max_length=2000, null=True, blank=True)
    cliLinExpiresAt = models.CharField(db_column='CLI_LIN_EXPIRES_AT', max_length=255, null=True, blank=True)
    cliZoomToken = models.CharField(db_column='CLI_ZOOM_TOKEN', max_length=2000, null=True, blank=True)
    # Oracle VECTOR(768, FLOAT32)
    cliEmbedding = models.JSONField(db_column='CLI_EMBEDDING', null=True, blank=True)

    class Meta:
        db_table = 'CLIENTS'
        managed = False
