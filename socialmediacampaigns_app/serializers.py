from rest_framework import serializers
from common_app.models import EiSocialMedia

class FacebookPostDtoSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    imageList = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )
    postLink = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    editFSmpResponse = serializers.DictField(required=False, allow_null=True)

class LinkedinPostDtoSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    image = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    postLink = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sendTo = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    editLSmpResponse = serializers.CharField(required=False, allow_blank=True, allow_null=True)

class TwitterPostDtoSerializer(serializers.Serializer):
    message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    imageList = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)

class DeleteSocialMediaPostDtoSerializer(serializers.Serializer):
    smId = serializers.ListField(child=serializers.IntegerField())

class UploadFileOrPicDtoSerializer(serializers.Serializer):
    file = serializers.CharField(allow_null=True, required=False)
    fileType = serializers.CharField(max_length=50, allow_null=True, required=False)
    fileName = serializers.CharField(max_length=255, allow_null=True, required=False)
    fileData = serializers.CharField(allow_null=True, required=False)
    uploadId = serializers.CharField(max_length=255, allow_null=True, required=False)
    chunkIndex = serializers.IntegerField(required=False)
    totalChunks = serializers.IntegerField(required=False)

class EiSocialMediaDtoSerializer(serializers.ModelSerializer):
    status = serializers.CharField(max_length=50, allow_null=True, required=False)
    smpScheduleDateTime = serializers.CharField(max_length=100, allow_null=True, required=False)
    facebookPostLink = serializers.CharField(max_length=2000, allow_null=True, required=False)
    twitterPostLink = serializers.CharField(max_length=2000, allow_null=True, required=False)
    linkedinPostLink = serializers.CharField(max_length=2000, allow_null=True, required=False)
    linkedinSendTo = serializers.CharField(max_length=2000, allow_null=True, required=False)

    class Meta:
        model = EiSocialMedia
        fields = '__all__'