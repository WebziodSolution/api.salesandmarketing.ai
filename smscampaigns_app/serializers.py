from rest_framework import serializers

class SaveSendSmsCampaignDetailsDtoSerializer(serializers.Serializer):
    """Nested DTO for SMS campaign details/segments"""
    rowDisplayOrder = serializers.IntegerField()
    smsType = serializers.CharField(max_length=255)
    smsDetail = serializers.CharField()

class SaveSendSmsCampaignDtoSerializer(serializers.Serializer):
    """Main DTO for saving/sending SMS campaigns - matches Java SaveSendSmsCampaignDto"""
    memberId = serializers.IntegerField(required=False, allow_null=True)
    subMemberId = serializers.IntegerField(required=False, allow_null=True, default=0)
    smsId = serializers.IntegerField(required=False, allow_null=True)
    smsName = serializers.CharField(max_length=255)
    scheduleType = serializers.IntegerField()
    sendOnDate = serializers.CharField(required=False, allow_null=True, help_text="Format: YYYY-MM-DD HH:MM:SS with timezone")
    groupList = serializers.IntegerField()  # Long in Java, single group ID
    segId = serializers.IntegerField(required=False, allow_null=True, default=0)
    sendSaveValue = serializers.IntegerField(required=False, allow_null=True)
    smsCampaignDetails = SaveSendSmsCampaignDetailsDtoSerializer(many=True, required=False, default=list)
    chkOptOut = serializers.IntegerField(required=False, allow_null=True, default=0)
    optOutMsg = serializers.CharField(max_length=2000, required=False, allow_null=True, allow_blank=True)
    scmNumberPhoneSid = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    scmId = serializers.IntegerField(required=False, allow_null=True)
    isClosedConversations = serializers.CharField(max_length=1, required=False, allow_blank=True)
    convertTinyUrlYN = serializers.CharField(max_length=1, default='Y')
    timeZone = serializers.CharField(max_length=255, required=False, allow_null=True)

class CampaignsSmsPreviewDtoSerializer(serializers.Serializer):
    """Preview SMS content before sending"""
    smsType = serializers.CharField(max_length=255, required=False, allow_blank=True)
    smsDetail = serializers.CharField()
    chkOptOut = serializers.IntegerField(required=False, allow_null=True, default=0)
    optOutMsg = serializers.CharField(max_length=2000, required=False, allow_null=True, allow_blank=True)
    convertTinyUrlYN = serializers.CharField(max_length=1, required=False, default='Y')

class EditSmsCampaignScheduleDtoSerializer(serializers.Serializer):
    """Edit scheduled send date for campaign"""
    memberId = serializers.IntegerField(required=False, allow_null=True)
    subMemberId = serializers.IntegerField(required=False, allow_null=True)
    smsId = serializers.IntegerField()
    sendOnDate = serializers.CharField(help_text="Format: YYYY-MM-DD HH:MM:SS")
    scheduleId = serializers.IntegerField(required=False, allow_null=True)
    timeZone = serializers.CharField(max_length=255, required=False, allow_null=True)

class DeleteSmsCampaignDtoSerializer(serializers.Serializer):
    """Delete one or multiple SMS campaigns"""
    smsId = serializers.ListField(child=serializers.IntegerField())
    conversationsTwilioNumber = serializers.CharField(required=False, allow_null=True, allow_blank=True)