from django.db import models

class Tenants(models.Model):
    ten_id = models.BigAutoField(db_column="TEN_ID", primary_key=True)
    ten_parent_id = models.BigIntegerField(db_column="TEN_PARENT_ID", null=True, blank=True)
    ten_crm_enabled = models.CharField(db_column="TEN_CRM_ENABLED", max_length=1, null=True, blank=True)
    ten_multi_client_enabled = models.CharField(db_column="TEN_MULTI_CLIENT_ENABLED", max_length=1, null=True, blank=True)
    ten_status = models.IntegerField(db_column="TEN_STATUS", default=0, null=True, blank=True)
    ten_username = models.CharField(db_column="TEN_USERNAME", max_length=25, null=True, blank=True)
    ten_first_name = models.CharField(db_column="TEN_FIRST_NAME", max_length=50, null=True, blank=True)
    ten_last_name = models.CharField(db_column="TEN_LAST_NAME", max_length=50, null=True, blank=True)
    ten_street_address1 = models.CharField(db_column="TEN_STREET_ADDRESS1", max_length=255, null=True, blank=True)
    ten_street_address2 = models.CharField(db_column="TEN_STREET_ADDRESS2", max_length=250, null=True, blank=True)
    ten_city = models.CharField(db_column="TEN_CITY", max_length=255, null=True, blank=True)
    ten_state = models.CharField(db_column="TEN_STATE", max_length=255, null=True, blank=True)
    ten_post_code = models.CharField(db_column="TEN_POST_CODE", max_length=25, null=True, blank=True)
    ten_country = models.CharField(db_column="TEN_COUNTRY", max_length=50, null=True, blank=True)
    ten_phone = models.CharField(db_column="TEN_PHONE", max_length=25, null=True, blank=True)
    ten_cell_phone = models.CharField(db_column="TEN_CELL_PHONE", max_length=25, null=True, blank=True)
    ten_email = models.CharField(db_column="TEN_EMAIL", max_length=25, null=True, blank=True)
    ten_default_language = models.CharField(db_column="TEN_DEFAULT_LANGUAGE", max_length=25, null=True, blank=True)
    ten_date_registered = models.DateTimeField(db_column="TEN_DATE_REGISTERED", null=True, blank=True)
    ten_last_logon = models.DateTimeField(db_column="TEN_LAST_LOGON", null=True, blank=True)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def id(self):
        return self.ten_id

    @property
    def is_active(self):
        # 0 is the active status based on view logic
        return self.ten_status == 0

    class Meta:
        managed = False
        db_table = "TENANTS"


class TenantDetails(models.Model):
    td_id = models.BigAutoField(db_column="TD_ID", primary_key=True)

    tenant = models.OneToOneField(
        Tenants,
        db_column="TD_TENANT_ID",
        to_field="ten_id",
        on_delete=models.DO_NOTHING,
        related_name="details",
        null=True,
        blank=True
    )

    td_membership_type = models.CharField(max_length=25, db_column="TD_MEMBERSHIP_TYPE", null=True, blank=True)
    td_country = models.CharField(max_length=50, db_column="TD_COUNTRY", null=True, blank=True)
    td_password = models.CharField(max_length=255, db_column="TD_PASSWORD", null=True, blank=True)

    td_sec_qus_1 = models.BigIntegerField(db_column="TD_SEC_QUS_1", null=True, blank=True)
    td_sec_ans_1 = models.CharField(max_length=255, db_column="TD_SEC_ANS_1", null=True, blank=True)
    td_sec_qus_2 = models.BigIntegerField(db_column="TD_SEC_QUS_2", null=True, blank=True)
    td_sec_ans_2 = models.CharField(max_length=255, db_column="TD_SEC_ANS_2", null=True, blank=True)
    td_sec_qus_3 = models.BigIntegerField(db_column="TD_SEC_QUS_3", default=0, null=True, blank=True)
    td_sec_ans_3 = models.CharField(max_length=255, db_column="TD_SEC_ANS_3", null=True, blank=True)

    td_opt_in = models.CharField(max_length=1, db_column="TD_OPT_IN", null=True, blank=True)

    td_sub_account_type_id = models.BigIntegerField(db_column="TD_SUB_ACCOUNT_TYPE_ID", default=0, null=True, blank=True)
    td_suba_reg_link_expire = models.DateTimeField(db_column="TD_SUBA_REG_LINK_EXPIRE", null=True, blank=True)

    td_date_registered = models.DateTimeField(db_column="TD_DATE_REGISTERED", null=True, blank=True)

    td_is2fa = models.CharField(max_length=1, db_column="TD_IS2FA", null=True, blank=True)
    td_otp = models.CharField(max_length=255, db_column="TD_OTP", null=True, blank=True)

    td_login_preference = models.CharField(max_length=255, db_column="TD_LOGIN_PREFERENCE", null=True, blank=True)
    td_google_authenticator_secret = models.CharField(max_length=2000, db_column="TD_GOOGLE_AUTHENTICATOR_SECRET", null=True, blank=True)
    td_microsoft_authenticator_secret = models.CharField(max_length=2000, db_column="TD_MICROSOFT_AUTHENTICATOR_SECRET", null=True, blank=True)

    td_registration_step = models.IntegerField(db_column="TD_REGISTRATION_STEP", default=0, null=True, blank=True)

    td_plan_id = models.CharField(max_length=255, db_column="TD_PLAN_ID", null=True, blank=True)
    td_agree_affiliate_program = models.CharField(max_length=1, db_column="TD_AGREE_AFFILIATE_PROGRAM", null=True, blank=True)
    td_newsletter_subscribe = models.CharField(max_length=1, db_column="TD_NEWSLETTER_SUBSCRIBE", null=True, blank=True)

    td_billing_first_name = models.CharField(max_length=255, db_column="TD_BILLING_FIRST_NAME", null=True, blank=True)
    td_billing_last_name = models.CharField(max_length=255, db_column="TD_BILLING_LAST_NAME", null=True, blank=True)
    td_billing_address1 = models.CharField(max_length=250, db_column="TD_BILLING_ADDRESS1", null=True, blank=True)
    td_billing_address2 = models.CharField(max_length=250, db_column="TD_BILLING_ADDRESS2", null=True, blank=True)
    td_billing_city = models.CharField(max_length=255, db_column="TD_BILLING_CITY", null=True, blank=True)
    td_billing_state = models.CharField(max_length=255, db_column="TD_BILLING_STATE", null=True, blank=True)
    td_billing_post_code = models.CharField(max_length=255, db_column="TD_BILLING_POST_CODE", null=True, blank=True)
    td_billing_country = models.CharField(max_length=255, db_column="TD_BILLING_COUNTRY", null=True, blank=True)
    td_billing_phone = models.CharField(max_length=255, db_column="TD_BILLING_PHONE", null=True, blank=True)

    td_enable_api = models.CharField(max_length=2000, db_column="TD_ENABLE_API", default="N", null=True, blank=True)
    td_auth_key = models.CharField(max_length=2000, db_column="TD_AUTH_KEY", null=True, blank=True)
    td_auth_token = models.CharField(max_length=2000, db_column="TD_AUTH_TOKEN", null=True, blank=True)

    td_authorize_customer_profile_id = models.CharField(max_length=255, db_column="TD_AUTHORIZE_CUSTOMER_PROFILE_ID", null=True, blank=True)
    td_authorize_customer_payment_profile_id = models.CharField(max_length=255, db_column="TD_AUTHORIZE_CUSTOMER_PAYMENT_PROFILE_ID", null=True, blank=True)
    td_bill_date = models.DateTimeField(db_column="TD_BILL_DATE", null=True, blank=True)
    td_creditcard_status = models.CharField(max_length=250, db_column="TD_CREDITCARD_STATUS", null=True, blank=True)
    td_creditcard_error = models.CharField(max_length=250, db_column="TD_CREDITCARD_ERROR", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "TENANT_DETAILS"