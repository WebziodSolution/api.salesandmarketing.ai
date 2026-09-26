from rest_framework import serializers
from esignature_app.models import Envelope, EnvelopeDocument, EnvelopeRecipient, EnvelopeField

# ==========================================
# 1. Output Serializers (Database -> Response)
# ==========================================

class EnvelopeFieldSerializer(serializers.ModelSerializer):
    fieldId = serializers.IntegerField(source='field_id', read_only=True)
    recipientIndex = serializers.IntegerField(source='recipient_index', required=False, allow_null=True)
    fieldType = serializers.CharField(source='field_type', required=False, allow_null=True)
    pageNumber = serializers.IntegerField(source='page_number', required=False, allow_null=True)
    # x, y, width, height, required, value automatically serialize
    
    class Meta:
        model = EnvelopeField
        fields = ['fieldId', 'recipientIndex', 'fieldType', 'pageNumber', 'x', 'y', 'width', 'height', 'required', 'value']


class EnvelopeDocumentSerializer(serializers.ModelSerializer):
    docId = serializers.IntegerField(source='doc_id', read_only=True)
    fileName = serializers.CharField(source='file_name', required=False, allow_null=True)
    fileIndex = serializers.IntegerField(source='file_index', required=False, allow_null=True)
    fileUrl = serializers.CharField(source='file_url', required=False, allow_null=True)
    fields = EnvelopeFieldSerializer(many=True, read_only=True)
    
    class Meta:
        model = EnvelopeDocument
        fields = ['docId', 'fileName', 'fileIndex', 'fileUrl', 'fields']


class EnvelopeRecipientSerializer(serializers.ModelSerializer):
    recipientId = serializers.IntegerField(source='recipient_id', read_only=True)
    recipientToken = serializers.CharField(source='recipient_token', required=False, allow_null=True)
    routingOrder = serializers.IntegerField(source='routing_order', required=False, allow_null=True)
    actionTime = serializers.CharField(source='action_time', required=False, allow_null=True)
    accessCode = serializers.CharField(source='access_code', required=False, allow_null=True)
    privateMessage = serializers.CharField(source='private_message', required=False, allow_null=True)
    ipAddress = serializers.CharField(source='ip_address', required=False, allow_null=True)
    # name, email, action, status, color, country, state, city automatically serialize
    
    class Meta:
        model = EnvelopeRecipient
        fields = [
            'recipientId', 'name', 'email', 'action', 'routingOrder', 'status', 'color', 
            'recipientToken', 'country', 'state', 'city', 'ipAddress', 'actionTime', 
            'accessCode', 'privateMessage'
        ]


class EnvelopeSerializer(serializers.ModelSerializer):
    envId = serializers.IntegerField(source='env_id', read_only=True)
    envTitle = serializers.CharField(source='env_title', required=False, allow_null=True)
    envDescription = serializers.CharField(source='env_description', required=False, allow_null=True)
    envType = serializers.CharField(source='env_type', required=False, allow_null=True)
    envStatus = serializers.CharField(source='env_status', required=False, allow_null=True)
    emailSubject = serializers.CharField(source='email_subject', required=False, allow_null=True)
    emailMessage = serializers.CharField(source='email_message', required=False, allow_null=True)
    memberId = serializers.IntegerField(source='member_id', required=False, allow_null=True)
    envelopeUuid = serializers.CharField(source='envelope_uuid', required=False, allow_null=True)
    createdDate = serializers.DateTimeField(source='created_date', required=False, allow_null=True)
    updatedDate = serializers.DateTimeField(source='updated_date', required=False, allow_null=True)
    recipients = EnvelopeRecipientSerializer(many=True, read_only=True)
    documents = EnvelopeDocumentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Envelope
        fields = [
            'envId', 'envTitle', 'envDescription', 'envType', 'envStatus', 
            'emailSubject', 'emailMessage', 'memberId', 'envelopeUuid', 
            'createdDate', 'updatedDate', 'recipients', 'documents'
        ]


# ==========================================
# 2. Input Serializers (Request -> DTO)
# ==========================================

class EnvelopeDetailsSerializer(serializers.Serializer):
    title = serializers.CharField(required=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    type = serializers.CharField(required=True)


class RecipientDtoSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    action = serializers.CharField(required=True)
    color = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    accessCode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    privateMessage = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class EmailContentSerializer(serializers.Serializer):
    subject = serializers.CharField(required=True)
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class FieldDtoSerializer(serializers.Serializer):
    type = serializers.CharField(required=True)
    pageNumber = serializers.IntegerField(required=True)
    recipientIndex = serializers.IntegerField(required=True)
    x = serializers.FloatField(required=True)
    y = serializers.FloatField(required=True)
    width = serializers.FloatField(required=True)
    height = serializers.FloatField(required=True)
    required = serializers.BooleanField(required=True)
    value = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class DocumentDtoSerializer(serializers.Serializer):
    fileName = serializers.CharField(required=True)
    fileIndex = serializers.IntegerField(required=True)
    url = serializers.CharField(required=True)
    fields = FieldDtoSerializer(many=True, required=False)


class EnvelopeDtoSerializer(serializers.Serializer):
    envelopeDetails = EnvelopeDetailsSerializer(required=True)
    recipients = RecipientDtoSerializer(many=True, required=False)
    emailContent = EmailContentSerializer(required=True)
    documents = DocumentDtoSerializer(many=True, required=False)


# ==========================================
# 3. Recipient Request Serializers
# ==========================================

class ValidateAccessCodeSerializer(serializers.Serializer):
    accessCode = serializers.CharField(required=True)


class UpdateRecipientStatusSerializer(serializers.Serializer):
    status = serializers.CharField(required=True)
    country = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    state = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    city = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    ipAddress = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    actionTime = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class FieldSubmissionSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    value = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class SubmitSignedDocumentSerializer(serializers.Serializer):
    country = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    state = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    city = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    ipAddress = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    actionTime = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    fields = FieldSubmissionSerializer(many=True, required=False)


class AdoptSignatureSerializer(serializers.Serializer):
    signatureId = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    type = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    image = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    name = serializers.CharField(required=False, allow_null=True, allow_blank=True)

