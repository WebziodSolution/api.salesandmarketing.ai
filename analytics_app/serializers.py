from rest_framework import serializers

class AnalyticsDateFilterSerializer(serializers.Serializer):
    websiteId = serializers.CharField(required=False)
    dateFilterType = serializers.CharField(required=False)
    startDate = serializers.DateField(format="%m/%d/%Y", input_formats=["%m/%d/%Y"], required=False, allow_null=True)
    endDate = serializers.DateField(format="%m/%d/%Y", input_formats=["%m/%d/%Y"], required=False, allow_null=True)
    timeStamp = serializers.IntegerField(required=False, allow_null=True)
    callCount = serializers.IntegerField(required=False, allow_null=True)
    countryFilter = serializers.CharField(required=False, allow_null=True)
    domainFilter = serializers.CharField(required=False, allow_null=True)
    userFilter = serializers.CharField(required=False, allow_null=True)

class AnalyticsDeviceUserCampaignSerializer(serializers.Serializer):
    websiteId = serializers.CharField(required=True)
    filterType = serializers.CharField(required=True)
    dateFilterType = serializers.CharField(required=True)
    startDate = serializers.DateField(format="%m/%d/%Y", input_formats=["%m/%d/%Y"], required=False, allow_null=True)
    endDate = serializers.DateField(format="%m/%d/%Y", input_formats=["%m/%d/%Y"], required=False, allow_null=True)

class AnalyticsLogDataSerializer(serializers.Serializer):
    id = serializers.CharField(required=True)
    websiteId = serializers.CharField(required=True)
    logDataBy = serializers.CharField(required=True)
    dateFilterType = serializers.CharField(required=True)
    startDate = serializers.DateField(format="%m/%d/%Y", input_formats=["%m/%d/%Y"], required=False, allow_null=True)
    endDate = serializers.DateField(format="%m/%d/%Y", input_formats=["%m/%d/%Y"], required=False, allow_null=True)

class AnalyticsEmailCampaignOpenMemberLinkSerializer(serializers.Serializer):
    emailId = serializers.IntegerField(required=True)
    campId = serializers.CharField(required=True)
