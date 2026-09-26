from django.db import models

class Automation(models.Model):
    autId = models.BigAutoField(db_column='AUT_ID', primary_key=True)
    autClientId = models.BigIntegerField(db_column='AUT_CLIENT_ID', null=True, blank=True)
    autStartCondition = models.CharField(db_column='AUT_START_CONDITION', max_length=255, null=True, blank=True)
    autName = models.CharField(db_column='AUT_NAME', max_length=255, null=True, blank=True)
    autDescription = models.CharField(db_column='AUT_DESCRIPTION', max_length=255, null=True, blank=True)
    autEmailTemplateId = models.IntegerField(db_column='AUT_EMAIL_TEMPLATE_ID', null=True, blank=True)
    autGroupId = models.IntegerField(db_column='AUT_GROUP_ID', null=True, blank=True)
    autSendDateTime = models.DateTimeField(db_column='AUT_SEND_DATETIME', null=True, blank=True)
    autStartDateTime = models.DateTimeField(db_column='AUT_START_DATETIME', null=True, blank=True)
    autJsonData = models.TextField(db_column='AUT_JSON_DATA', null=True, blank=True)
    autStartAction = models.CharField(db_column='AUT_START_ACTION', max_length=255, null=True, blank=True)
    autSaveStatus = models.CharField(db_column='AUT_SAVE_STATUS', max_length=255, null=True, blank=True)
    autEstimatedCompletionDateTime = models.DateTimeField(db_column='AUT_ESTIMATED_COMPLETION_DATETIME', null=True, blank=True)
    autAutomationCampaignStatus = models.CharField(db_column='AUT_AUTOMATION_CAMPAIGN_STATUS', max_length=255, null=True, blank=True)
    autSmsFromNumber = models.CharField(db_column='AUT_SMS_FROM_NUMBER', max_length=255, null=True, blank=True)
    autSmsFromNumberSid = models.CharField(db_column='AUT_SMS_FROM_NUMBER_SID', max_length=255, null=True, blank=True)
    autSmsGroupId = models.BigIntegerField(db_column='AUT_SMS_GROUP_ID', default=0)
    autSmsOptInYn = models.CharField(db_column='AUT_SMS_OPTIN_YN', max_length=1, default='N')
    autEmbedding = models.JSONField(null=True, blank=True, db_column='AUT_EMBEDDING')

    class Meta:
        db_table = 'AUTOMATION'
        managed = False

class AutomationCampaignMaster(models.Model):
    id = models.BigAutoField(db_column='ACM_ID', primary_key=True)
    amId = models.BigIntegerField(db_column='ACM_AUT_ID')
    memberId = models.BigIntegerField(db_column='ACM_CLIENT_ID')
    campName = models.CharField(db_column='ACM_CAMP_NAME', max_length=250, null=True, blank=True)
    campDetail = models.TextField(db_column='ACM_CAMP_DETAIL', null=True, blank=True)
    campType = models.IntegerField(db_column='ACM_CAMP_TYPE')
    campGroupId = models.IntegerField(db_column='ACM_CAMP_GROUP_ID')
    formName = models.CharField(db_column='ACM_FROM_NAME', max_length=255, null=True, blank=True)
    formAdd = models.CharField(db_column='ACM_FROM_ADDRESS', max_length=255)
    replyToAdd = models.CharField(db_column='ACM_REPLY_TO_ADDRESS', max_length=255)
    subject = models.CharField(db_column='ACM_SUBJECT', max_length=255)
    sendDate = models.DateTimeField(db_column='ACM_SEND_DATE')
    templateName = models.CharField(db_column='ACM_TEMPLATE_NAME', max_length=255)
    myPageId = models.BigIntegerField(db_column='ACM_MYPAGE_ID', null=True, blank=True)
    readyToSend = models.IntegerField(db_column='ACM_READY_TO_SEND', null=True, blank=True)
    isSend = models.IntegerField(db_column='ACM_IS_SEND', null=True, blank=True)
    isProcessed = models.IntegerField(db_column='ACM_IS_PROCESSED', null=True, blank=True)
    sendOnDate = models.DateTimeField(db_column='ACM_SEND_ON_DATE', null=True, blank=True)
    sendOnTime = models.DurationField(db_column='ACM_SEND_ON_TIME', null=True, blank=True)
    mailType = models.CharField(db_column='ACM_MAIL_TYPE', max_length=255, null=True, blank=True)
    acmEmbedding = models.JSONField(null=True, blank=True, db_column='ACM_EMBEDDING')

    class Meta:
        db_table = 'AUTOMATION_CAMPAIGN_MASTER'
        managed = False

class AutomationCampaignNode(models.Model):
    acnId = models.BigAutoField(db_column='ACN_ID', primary_key=True)
    acnAutId = models.BigIntegerField(db_column='ACN_AUT_ID')
    acnMasterId = models.BigIntegerField(db_column='ACN_MASTER_ID')
    acnNodeId = models.TextField(db_column='ACN_NODE_ID', null=True, blank=True)
    acnNodeType = models.TextField(db_column='ACN_NODE_TYPE', null=True, blank=True)
    acnNodeDetail = models.TextField(db_column='ACN_NODE_DETAIL', null=True, blank=True)
    acnSourceId = models.CharField(db_column='ACN_SOURCE_ID', max_length=255, null=True, blank=True)
    acnIsProcessed = models.CharField(db_column='ACN_IS_PROCESSED', max_length=1, default='N')
    acnIsSend = models.CharField(db_column='ACN_IS_SEND', max_length=1, default='N')
    acnStartDateTime = models.DateTimeField(db_column='ACN_START_DATE_TIME', null=True, blank=True)
    acnEndDateTime = models.DateTimeField(db_column='ACN_END_DATE_TIME', null=True, blank=True)
    acnSourceHandle = models.CharField(db_column='ACN_SOURCE_HANDLE', max_length=255, null=True, blank=True)
    acnSendId = models.BigIntegerField(db_column='ACN_SEND_ID', default=0)
    acnEmbedding = models.JSONField(null=True, blank=True, db_column='ACN_EMBEDDING')

    class Meta:
        db_table = 'AUTOMATION_CAMP_NODE'
        managed = False

class AutomationSmsDetails(models.Model):
    detId = models.BigAutoField(db_column='ASD_DET_ID', primary_key=True)
    detSmsId = models.BigIntegerField(db_column='ASD_SMS_ID', default=0)
    detReceiveReply = models.CharField(db_column='ASD_RECEIVE_REPLY', max_length=2000, null=True, blank=True)
    detSendReplyDetails = models.CharField(db_column='ASD_SEND_REPLY_DETAILS', max_length=2000, null=True, blank=True)
    asdEmbedding = models.JSONField(null=True, blank=True, db_column='ASD_EMBEDDING')

    class Meta:
        db_table = 'AUTOMATION_SMS_DETAILS'
        managed = False

class AutomationSendContact(models.Model):
    id = models.BigAutoField(db_column='ASC_ID', primary_key=True)
    automationId = models.BigIntegerField(db_column='ASC_AUT_ID')
    automationMasterSendId = models.BigIntegerField(db_column='ASC_MASTER_SEND_ID', default=0)
    memberId = models.BigIntegerField(db_column='ASC_CLIENT_ID')
    email = models.CharField(db_column='ASC_EMAIL', max_length=500, null=True, blank=True)
    emailId = models.BigIntegerField(db_column='ASC_EMAIL_ID', null=True, blank=True)
    isSend = models.CharField(db_column='ASC_IS_SEND', max_length=1, default='N')
    isRead = models.CharField(db_column='ASC_IS_READ', max_length=1, null=True, blank=True)
    isBounced = models.CharField(db_column='ASC_IS_BOUNCED', max_length=1, null=True, blank=True)
    isUnsubscribed = models.CharField(db_column='ASC_IS_UNSUBSCRIBED', max_length=1, null=True, blank=True)
    firstName = models.CharField(db_column='ASC_FIRST_NAME', max_length=255, null=True, blank=True)
    lastName = models.CharField(db_column='ASC_LAST_NAME', max_length=255, null=True, blank=True)
    emailDomain = models.CharField(db_column='ASC_EMAIL_DOMAIN', max_length=45, null=True, blank=True)
    csDefaultLanguage = models.CharField(db_column='ASC_CS_DEFAULT_LANGUAGE', max_length=255, default='en')
    smtpServerHost = models.CharField(db_column='ASC_SMTP_SERVER_HOST', max_length=1, null=True, blank=True)
    isProcessed = models.CharField(db_column='ASC_IS_PROCESSED', max_length=1, default='N')
    emailQId = models.CharField(db_column='ASC_EMAIL_Q_ID', max_length=255, null=True, blank=True)
    emailStatus = models.CharField(db_column='ASC_EMAIL_STATUS', max_length=255, null=True, blank=True)
    cronStatus = models.CharField(db_column='ASC_CRON_STATUS', max_length=255, default='active')
    splitGroup = models.CharField(db_column='ASC_SPLIT_GROUP', max_length=1, null=True, blank=True)
    groupWinner = models.CharField(db_column='LCE_LINK_ID', max_length=1, null=True, blank=True)
    msgPriority = models.IntegerField(db_column='ASC_MSG_PRIORITY', default=0)
    campSendId = models.BigIntegerField(db_column='ASC_CAMP_SEND_ID', default=0)
    sid = models.CharField(db_column='ASC_SID', max_length=255, null=True, blank=True)
    smsStatus = models.CharField(db_column='ASC_SMS_STATUS', max_length=255, null=True, blank=True)
    errorMessage = models.CharField(db_column='ASC_SMS_ERROR_MESSAGE', max_length=255, null=True, blank=True)
    errorCode = models.CharField(db_column='ASC_ERROR_CODE', max_length=255, null=True, blank=True)
    fromContact = models.CharField(db_column='ASC_FROM_CONTACT', max_length=255, null=True, blank=True)
    toContact = models.CharField(db_column='ASC_TO_CONTACT', max_length=255, null=True, blank=True)
    smsSendDate = models.DateTimeField(db_column='ASC_SEND_DATE', null=True, blank=True)
    smsDetails = models.CharField(db_column='ASC_SMS_DETAILS', max_length=2000, null=True, blank=True)
    ascEmbedding = models.JSONField(null=True, blank=True, db_column='ASC_EMBEDDING')

    class Meta:
        db_table = 'AUTOMATION_SEND_CONTACT'
        managed = False