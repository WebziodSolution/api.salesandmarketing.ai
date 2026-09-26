from django.db import models

class Envelope(models.Model):
    env_id = models.BigAutoField(primary_key=True)
    env_title = models.CharField(max_length=255, null=True, blank=True)
    env_description = models.TextField(null=True, blank=True)
    env_type = models.CharField(max_length=255, null=True, blank=True)
    env_status = models.CharField(max_length=255, null=True, blank=True) # DRAFT, SENT, COMPLETED, VOIDED
    email_subject = models.CharField(max_length=255, null=True, blank=True)
    email_message = models.TextField(null=True, blank=True)
    member_id = models.BigIntegerField(null=True, blank=True)
    env_uuid = models.CharField(max_length=255, null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_date = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'tbl_envelope'
        managed = False


class EnvelopeRecipient(models.Model):
    recipient_id = models.BigAutoField(primary_key=True)
    envelope = models.ForeignKey(Envelope, on_delete=models.CASCADE, db_column='env_id', related_name='recipients')
    name = models.CharField(db_column='recipient_name', max_length=255, null=True, blank=True)
    email = models.CharField(db_column='recipient_email', max_length=255, null=True, blank=True)
    action = models.CharField(db_column='recipient_action', max_length=255, null=True, blank=True)
    routing_order = models.IntegerField(db_column='routing_order', null=True, blank=True)
    status = models.CharField(db_column='recipient_status', max_length=255, null=True, blank=True)
    color = models.CharField(max_length=255, null=True, blank=True)
    recipient_token = models.TextField(db_column='recipient_token', null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.CharField(db_column='ip_address', max_length=255, null=True, blank=True)
    action_time = models.CharField(db_column='action_time', max_length=255, null=True, blank=True)
    access_code = models.CharField(db_column='access_code', max_length=255, null=True, blank=True)
    private_message = models.TextField(db_column='private_message', null=True, blank=True)

    class Meta:
        db_table = 'tbl_envelope_recipient'
        managed = False


class EnvelopeDocument(models.Model):
    doc_id = models.BigAutoField(primary_key=True)
    envelope = models.ForeignKey(Envelope, on_delete=models.CASCADE, db_column='env_id', related_name='documents')
    file_name = models.CharField(db_column='file_name', max_length=255, null=True, blank=True)
    file_index = models.IntegerField(db_column='file_index', null=True, blank=True)
    file_url = models.TextField(db_column='file_url', null=True, blank=True)

    class Meta:
        db_table = 'tbl_envelope_document'
        managed = False


class EnvelopeField(models.Model):
    field_id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(EnvelopeDocument, on_delete=models.CASCADE, db_column='doc_id', related_name='fields')
    recipient_index = models.IntegerField(db_column='recipient_index', null=True, blank=True)
    field_type = models.CharField(db_column='field_type', max_length=255, null=True, blank=True)
    page_number = models.IntegerField(db_column='page_number', null=True, blank=True)
    x = models.FloatField(db_column='pos_x', null=True, blank=True)
    y = models.FloatField(db_column='pos_y', null=True, blank=True)
    width = models.FloatField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    required = models.BooleanField(null=True, blank=True)
    value = models.TextField(db_column='field_value', null=True, blank=True)

    class Meta:
        db_table = 'tbl_envelope_field'
        managed = False


class RecipientSignature(models.Model):
    signature_id = models.BigAutoField(primary_key=True)
    member_id = models.BigIntegerField(db_column='member_id')
    env_id = models.BigIntegerField(db_column='env_id')
    recipient_id = models.BigIntegerField(db_column='recipient_id')
    signature_uuid = models.CharField(db_column='signature_uuid', max_length=255)
    signature_type = models.CharField(db_column='signature_type', max_length=255, null=True, blank=True)
    signature_image = models.TextField(db_column='signature_image', null=True, blank=True)
    signer_name = models.CharField(db_column='signer_name', max_length=255)
    created_date = models.DateTimeField(db_column='created_date', auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'tbl_recipient_signature'
        managed = False

