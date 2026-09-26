from django.db import models
from auth_app.models import Tenants


class SubaccountType(models.Model):
    styId = models.AutoField(primary_key=True, db_column='SUB_ID')
    styMemberId = models.IntegerField(null=True, blank=True, db_column='SUB_CLIENT_ID')
    styName = models.CharField(max_length=255, null=True, blank=True, db_column='SUB_NAME')
    styCreatedDate = models.DateTimeField(null=True, blank=True, db_column='SUB_CREATED_DATE')
    subEmbedding = models.JSONField(null=True, blank=True, db_column='SUB_EMBEDDING')

    class Meta:
        db_table = 'SUBACCOUNTS'
        managed = False

class PageActionName(models.Model):
    acId = models.AutoField(primary_key=True, db_column='AM_ID')
    acName = models.CharField(max_length=255, null=True, blank=True, db_column='AM_NAME')

    class Meta:
        db_table = 'PAGE_ACTION_NAME'
        managed = False

class SubaccountPageDetails(models.Model):
    pgdId = models.AutoField(primary_key=True, db_column='SPD_ID')
    pgdPgId = models.IntegerField(null=True, blank=True, db_column='SPD_SP_ID')
    pgdActionName = models.CharField(max_length=255, null=True, blank=True, db_column='SPD_ACTION_NAME')

    class Meta:
        db_table = 'SUBACCOUNT_PAGE_DETAILS'
        managed = False

class WarmupLog(models.Model):
    warmId = models.AutoField(primary_key=True, db_column='WL_ID')
    warmDomain = models.CharField(max_length=255, null=True, blank=True, db_column='WL_DOMAIN')
    warmEmail = models.CharField(max_length=255, null=True, blank=True, db_column='WL_EMAIL')
    warmStartDate = models.DateTimeField(null=True, blank=True, db_column='WL_START_DATE')
    warmEndDate = models.DateTimeField(null=True, blank=True, db_column='WL_END_DATE')
    warmPrice = models.FloatField(null=True, blank=True, db_column='WL_PRICE')
    memberId = models.IntegerField(null=True, blank=True, db_column='WL_CLIENT_ID')

    class Meta:
        db_table = 'WARMUP_LOG'
        managed = False

class EmailSignature(models.Model):
    signId = models.AutoField(primary_key=True, db_column='SIGN_ID')
    signTitle = models.CharField(max_length=255, null=True, blank=True, db_column='SIGN_TITLE')
    signDescription = models.CharField(max_length=2000, null=True, blank=True, db_column='SIGN_DESCRIPTION')
    signDateTime = models.DateTimeField(auto_now_add=True, null=True, blank=True, db_column='SIGN_DATE_TIME')
    signMemberId = models.BigIntegerField(default=0, db_column='SIGN_MEMBER_ID')

    class Meta:
        db_table = 'EMAIL_SIGNATURE'
        managed = False

class SupportApiModule(models.Model):
    mdId = models.AutoField(primary_key=True, db_column='SAM_ID')
    mdName = models.CharField(max_length=255, null=True, blank=True, db_column='SAM_NAME')

    class Meta:
        db_table = 'SUPPORT_API_MODULE'
        managed = False

class SupportApiPermission(models.Model):
    perId = models.AutoField(primary_key=True, db_column='SAM_ID')
    perMdId = models.IntegerField(null=True, blank=True, db_column='SAP_MOD_ID')
    perMemberId = models.IntegerField(null=True, blank=True, db_column='SAP_CLIENT_ID')

    class Meta:
        db_table = 'SUPPORT_API_PERMISSION'
        managed = False

class WhiteListingUrls(models.Model):
    id = models.AutoField(primary_key=True, db_column='WL_ID')
    memberId = models.IntegerField(default=0, db_column='WL_CLIENT_ID')
    url = models.CharField(max_length=250, null=True, blank=True, db_column='WL_URL')
    createdDate = models.DateTimeField(null=True, blank=True, db_column='WL_CREATED_DATE')

    class Meta:
        db_table = 'WHITELISTING_URLS'
        managed = False

class SupportApi(models.Model):
    apiId = models.AutoField(primary_key=True, db_column='api_id')
    apiMdId = models.IntegerField(null=True, blank=True, db_column='api_md_id')
    apiUrl = models.CharField(max_length=255, null=True, blank=True, db_column='api_url')

    class Meta:
        db_table = 'support_api'
        managed = False


class Todos(models.Model):
    id = models.AutoField(primary_key=True, db_column='ID')
    tenant = models.ForeignKey(
        Tenants,
        on_delete=models.DO_NOTHING,
        db_column='TEN_ID',
        related_name='todos'
    )
    task = models.CharField(max_length=50, db_column='TASK')
    description = models.TextField(null=True, blank=True, db_column='DESCRIPTION')
    due_date = models.DateField(db_column='DUE_DATE')
    status = models.CharField(max_length=25, default='Not Started', db_column='STATUS')
    is_today = models.BooleanField(default=False, null=True, blank=True, db_column='IS_TODAY')
    type = models.CharField(max_length=50, null=True, blank=True, db_column='TYPE')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CREATED_AT')


    @property
    def ten_id(self):
        return self.tenant_id

    @ten_id.setter
    def ten_id(self, value):
        self.tenant_id = value

    def save(self, *args, **kwargs):
        if not self.id:
            from django.db import connection
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT TODOS_SEQ.NEXTVAL FROM DUAL")
                    row = cursor.fetchone()
                    if row:
                        self.id = row[0]
            except Exception:
                pass
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'TODOS'
        managed = False


Todo = Todos


class TodoAttachments(models.Model):
    id = models.AutoField(primary_key=True, db_column='ID')
    tenant = models.ForeignKey(
        Tenants,
        on_delete=models.DO_NOTHING,
        db_column='TEN_ID',
        related_name='todo_attachments'
    )
    todo = models.ForeignKey(
        Todos,
        on_delete=models.DO_NOTHING,
        db_column='TODO_ID',
        related_name='attachments'
    )
    file_name = models.CharField(max_length=50, db_column='FILE_NAME')
    file_path = models.TextField(null=True, blank=True, db_column='FILE_PATH')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CREATED_AT')

    @property
    def ten_id(self):
        return self.tenant_id

    @ten_id.setter
    def ten_id(self, value):
        self.tenant_id = value

    def save(self, *args, **kwargs):
        if not self.id:
            from django.db import connection
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT TODOS_ATTACHMENTS_SEQ.NEXTVAL FROM DUAL")
                    row = cursor.fetchone()
                    if row:
                        self.id = row[0]
            except Exception:
                pass
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'TODOS_ATTACHMENTS'
        managed = False


TodoAttachment = TodoAttachments


class TodosPriority(models.Model):
    id = models.AutoField(primary_key=True, db_column='ID')
    tenant = models.ForeignKey(
        Tenants,
        on_delete=models.CASCADE,
        db_column='TEN_ID',
        related_name='todo_priorities'
    )
    todo = models.ForeignKey(
        Todos,
        on_delete=models.CASCADE,
        db_column='TODO_ID',
        related_name='priority_records'
    )
    priority_index = models.IntegerField(db_column='PRIORITY_INDEX')

    @property
    def ten_id(self):
        return self.tenant_id

    @ten_id.setter
    def ten_id(self, value):
        self.tenant_id = value

    def save(self, *args, **kwargs):
        if not self.id:
            from django.db import connection
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT TODOS_PRIORITY_SEQ.NEXTVAL FROM DUAL")
                    row = cursor.fetchone()
                    if row:
                        self.id = row[0]
            except Exception:
                pass
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'TODOS_PRIORITY'
        managed = False


TodoPriority = TodosPriority


