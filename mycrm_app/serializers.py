from rest_framework import serializers
from common_app.models import (CalendarAppointmentAvailabilitySlots, CalendarAppointmentEventType, TimeZoneList, TempUserlist, GroupSegment, GroupSegmentField, Udf)
from common_app.utils import display_date_time

class CalendarAppointmentAvailabilitySlotsSerializer(serializers.ModelSerializer):
    aasCreatedDate = serializers.SerializerMethodField()
    aasStartTime = serializers.SerializerMethodField()
    aasEndTime = serializers.SerializerMethodField()

    class Meta:
        model = CalendarAppointmentAvailabilitySlots
        fields = '__all__'

    def get_aasCreatedDate(self, obj):
        return display_date_time(obj.aasCreatedDate)

    def get_aasStartTime(self, obj):
        return display_date_time(obj.aasStartTime)

    def get_aasEndTime(self, obj):
        return display_date_time(obj.aasEndTime)

class CalendarAppointmentEventTypeSerializer(serializers.ModelSerializer):
    aetDateTime = serializers.SerializerMethodField()

    class Meta:
        model = CalendarAppointmentEventType
        fields = '__all__'
    
    def get_aetDateTime(self, obj):
        return display_date_time(obj.aetDateTime)

class CalendarDtoSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    description = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    start = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    end = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calMemberId = serializers.IntegerField(required=False, allow_null=True)
    allDay = serializers.BooleanField(required=False, allow_null=True)
    calTimeZone = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calAttendees = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    slotMember = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calAetId = serializers.IntegerField(required=False, allow_null=True)
    slotTimeMinus = serializers.IntegerField(required=False, default=0)
    contactList = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    displayStart = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    displayEnd = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calType = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    currentDateYN = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    memTimeZone = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    # These fields caused your specific error:
    calEventReminder = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calReminderSubject = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calReminderType = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    calMyPageId = serializers.IntegerField(required=False, allow_null=True)
    calSmsSstId = serializers.IntegerField(required=False, allow_null=True)
    calScheduleDateTime = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calParentId = serializers.IntegerField(required=False, allow_null=True)
    calRepeatEvery = serializers.IntegerField(required=False, default=0)
    
    # These fields caused your specific error:
    calRepeatType = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calRepeatEveryType = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calRepeatDayName = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    calRepeatEndDate = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calRepeatDate = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calRepeatSelectedOption = serializers.IntegerField(required=False, default=0)
    editAll = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    cladTypeList = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)

class SendContactListSerializer(serializers.Serializer):
    emailId = serializers.IntegerField(required=False)
    clientEmail = serializers.EmailField(required=False)
    clientNumber = serializers.CharField(required=False)

class DeleteCalendarAppointmentEventTypeDtoSerializer(serializers.Serializer):
    aetId = serializers.ListField(child=serializers.IntegerField())

class DeleteEventDtoSerializer(serializers.Serializer):
    calId = serializers.IntegerField(required=False, allow_null=True)
    googleCalendar = serializers.BooleanField(required=False, default=False)
    outlookCalendar = serializers.BooleanField(required=False, default=False)
    calParentId = serializers.IntegerField(required=False, allow_null=True)
    deleteAll = serializers.CharField(required=False, allow_null=True)

class SaveTenantTimeZoneDtoSerializer(serializers.Serializer):
    timeZone = serializers.CharField(required=False, allow_null=True)

class SaveTenantWebConferenceDtoSerializer(serializers.Serializer):
    webConference = serializers.CharField(required=False, allow_null=True)

class SaveTenantEmailNotificationDtoSerializer(serializers.Serializer):
    emailNotification = serializers.CharField(required=False, allow_null=True)

class SaveTenantSmsNotificationDtoSerializer(serializers.Serializer):
    smsNotification = serializers.CharField(required=False, allow_null=True)

class TimeZoneListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeZoneList
        fields = ['tmzId','tmzTitle','tmzValue']

class CallingHistoryDtoSerializer(serializers.Serializer):
    emailId = serializers.IntegerField()
    firstName = serializers.CharField(required=False, allow_null=True)
    LastName = serializers.CharField(required=False, allow_null=True)
    cpDate = serializers.CharField(required=False, allow_null=True)
    ccDuration = serializers.FloatField(required=False, allow_null=True)

class ConversationsHistoryDtoSerializer(serializers.Serializer):
    contactEmailId = serializers.IntegerField(required=False, allow_null=True)
    contactFirstName = serializers.CharField(required=False, allow_null=True)
    contactLastName = serializers.CharField(required=False, allow_null=True)
    contactPhoneNumber = serializers.CharField(required=False, allow_null=True)
    contactCountryCallCode = serializers.CharField(required=False, allow_null=True)
    memPhone = serializers.CharField(required=False, allow_null=True)
    memCountryCallCode = serializers.CharField(required=False, allow_null=True)
    memFirstName = serializers.CharField(required=False, allow_null=True)
    memLastName = serializers.CharField(required=False, allow_null=True)
    cvsdDate = serializers.CharField(required=False, allow_null=True)
    cvsdMessage = serializers.CharField(required=False, allow_null=True)
    cvsdId = serializers.IntegerField(required=False, allow_null=True)
    cvsdSender = serializers.CharField(required=False, allow_null=True)
    cvsdClientId = serializers.IntegerField(required=False, allow_null=True)
    cvsdCvsId = serializers.IntegerField(required=False, allow_null=True)
    checkConversationsRows = serializers.IntegerField(required=False, default=0)
    chatColor = serializers.CharField(required=False, allow_null=True)

class ImportContactDtoSerializer(serializers.Serializer):
    format = serializers.CharField()
    path = serializers.CharField()
    memberId = serializers.IntegerField()
    transId = serializers.CharField(required=False, allow_null=True)
    columnHeaders = serializers.DictField(child=serializers.CharField(), required=False, allow_null=True)

class HeaderFileMappingDtoSerializer(serializers.Serializer):
    path = serializers.CharField(required=False, allow_null=True)
    groupId = serializers.IntegerField()
    columnHeaders = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    quickbook = serializers.CharField(required=False, allow_null=True)
    salesforce = serializers.CharField(required=False, allow_null=True)
    transId = serializers.CharField(required=False, allow_null=True)

class UpdateImportContactSerializer(serializers.Serializer):
    emailId = serializers.IntegerField()
    key = serializers.CharField()
    value = serializers.CharField(allow_blank=True)

class OptOutDtoSerializer(serializers.Serializer):
    encMemberId = serializers.CharField()
    encGroupId = serializers.CharField()
    email = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    phoneNumber = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    optOutType = serializers.CharField()
    encEmailId = serializers.CharField(required=False, allow_null=True, allow_blank=True)

class OptOutDetailsDtoSerializer(serializers.Serializer):
    encMemberId = serializers.CharField()
    encGroupId = serializers.CharField()
    encEmailId = serializers.CharField()
    clientName = serializers.CharField(required=False, allow_null=True)
    clientEmail = serializers.CharField(required=False, allow_null=True)
    clientPhoneNumber = serializers.CharField(required=False, allow_null=True)
    memberName = serializers.CharField(required=False, allow_null=True)
    groupName = serializers.CharField(required=False, allow_null=True)
    whiteListingLogo = serializers.CharField(required=False, allow_null=True)
    businessName = serializers.CharField(required=False, allow_null=True)

class OptInDtoSerializer(serializers.Serializer):
    encMemberId = serializers.CharField()
    email = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    phoneNumber = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    groupList = serializers.ListField(child=serializers.IntegerField())

class SendSubscribeLinkDtoSerializer(serializers.Serializer):
    groupId = serializers.IntegerField()
    emailId = serializers.IntegerField()

class EmailVerificationGroupDtoSerializer(serializers.Serializer):
    groupId = serializers.IntegerField()

class TempUserlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = TempUserlist
        fields = '__all__'

class UdfSerializer(serializers.ModelSerializer):
    class Meta:
        model = Udf
        fields = '__all__'

class GroupSegmentFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupSegmentField
        fields = '__all__'

class GroupSegmentSerializer(serializers.ModelSerializer):
    groupSegmentFieldDtos = serializers.SerializerMethodField()
    segAddedDate = serializers.SerializerMethodField()

    class Meta:
        model = GroupSegment
        fields = [
            'segId', 'segName', 'groupId', 'memberId', 
            'segAddedDate', 'groupSegmentFieldDtos'
        ]

    def get_groupSegmentFieldDtos(self, obj):
        from common_app.models import GroupSegmentField
        fields = GroupSegmentField.objects.filter(segId=obj.segId).order_by('segDisplayOrder')
        return GroupSegmentFieldSerializer(fields, many=True).data

    def get_segAddedDate(self, obj):
        from common_app.utils import display_date
        return display_date(obj.segDateAdded)

class BulkDeleteGroupSegmentSerializer(serializers.Serializer):
    segIds = serializers.ListField(child=serializers.IntegerField())

class UploadFileOrPicDtoSerializer(serializers.Serializer):
    file = serializers.CharField()
    fileType = serializers.CharField()
    fileName = serializers.CharField()
    uploadId = serializers.CharField(required=False, allow_null=True)
    totalChunks = serializers.IntegerField(required=False, default=0)

class InviteByUrlDtoSerializer(serializers.Serializer):
    q = serializers.CharField()

class SendOptInGroupDtoSerializer(serializers.Serializer):
    groupId = serializers.IntegerField()
    optInType = serializers.CharField()
    emailIds = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)