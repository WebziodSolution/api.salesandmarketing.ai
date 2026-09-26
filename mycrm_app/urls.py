from django.urls import path
from mycrm_app.views import (
    calendar_appointment_views,
    calendar_appointment_event_type_views,
    calendar_views,
    calling_views,
    contact_views,
    contact_history_views,
    contact_import_views,
    sms_inbox_views,
    group_views,
    group_segment_views,
)

urlpatterns = [
    # Contact History
    path('contactHistory/getSendEmails/<int:emailId>', contact_history_views.get_send_emails),
    path('contactHistory/getOutgoingSMS/<int:emailId>', contact_history_views.get_outgoing_sms),
    path('contactHistory/getIncomingSMS/<int:emailId>', contact_history_views.get_incoming_sms),
    path('contactHistory/getSMSPolling/<int:emailId>', contact_history_views.get_sms_polling),
    path('contactHistory/getCalling', contact_history_views.get_calling),
    path('contactHistory/getConversations', contact_history_views.get_conversations),

    # Calling
    path('calling/sendCalling', calling_views.send_calling),
    path('calling/callingReply', calling_views.calling_reply),
    path('calling/callingStop', calling_views.calling_stop),

    # Calendar Appointment
    path('calendarAppointment/getAvailabilitySlotsList/<path:tenId>', calendar_appointment_views.get_availability_slots_list),
    path('calendarAppointment/saveAvailabilitySlots', calendar_appointment_views.save_availability_slots),
    path('calendarAppointment/freeSlotList', calendar_appointment_views.free_slot_list),
    path('calendarAppointment/saveAppointment', calendar_appointment_views.save_appointment),
    path('calendarAppointment/sendEmailAppointmentLink', calendar_appointment_views.send_email_appointment_link),
    path('calendarAppointment/sendSmsAppointmentLink', calendar_appointment_views.send_sms_appointment_link),
    path('calendarAppointment/smsStatusUrlSendAppointmentLink', calendar_appointment_views.sms_status_url_send_appointment_link),
    path('calendarAppointment/smsStatusUrlSendSmsCalendarAppointment', calendar_appointment_views.sms_status_url_send_sms_calendar_appointment),

    # Calendar Appointment Event Type
    path('calendarAppointmentEventType/getEventTypeList', calendar_appointment_event_type_views.get_event_type_list),
    path('calendarAppointmentEventType/getEventType/<int:aetId>', calendar_appointment_event_type_views.get_event_type),
    path('calendarAppointmentEventType/deleteEventType', calendar_appointment_event_type_views.delete_event_type),
    path('calendarAppointmentEventType/saveEventType', calendar_appointment_event_type_views.save_event_type),
    path('calendarAppointmentEventType/getEventTypeAllList/<path:memId>', calendar_appointment_event_type_views.get_event_type_all_list),

    # Calendar
    path('calendar/getTimeZoneList', calendar_views.get_time_zone_list),
    path('calendar/getCalendarAuthentication', calendar_views.get_calendar_authentication),
    path('calendar/saveMemberTimeZone', calendar_views.save_client_time_zone),
    path('calendar/saveWebConference', calendar_views.save_web_conference),
    path('calendar/saveEmailNotification', calendar_views.save_email_notification),
    path('calendar/saveSmsNotification', calendar_views.save_sms_notification),
    path('calendar/getEventList', calendar_views.get_event_list),
    path('calendar/getEvent/<int:calId>', calendar_views.get_event),  # Fixed: added /{id} path variable
    path('calendar/getSync', calendar_views.get_sync),
    path('calendar/deleteEvent', calendar_views.delete_event),
    path('calendar/saveEvent', calendar_views.save_event),
    path('calendar/saveReminder', calendar_views.save_reminder),
    path('calendar/smsStatusUrlSendSmsCalendarReminder', calendar_views.sms_status_url_send_sms_calendar_reminder),
    path('calendar/saveDefaultCalendar', calendar_views.save_default_calendar),

    # Contact
    path('contact', contact_views.contact_root), # Handles POST and PUT /contact
    path('contact/addContact', contact_views.add_contact),
    path('contact/updateContact/<int:email_id>', contact_views.update_contact),
    path('contact/deleteContact/<int:email_id>', contact_views.delete_contact),
    path('contact/deleteBulkContact', contact_views.delete_bulk_contact),
    path('contact/getContact/<int:email_id>', contact_views.get_contact),
    path('contact/getDownloadContactFile/<int:groupId>', contact_views.get_download_contact_file),
    path('contact/moveContactExistingGroup/<int:newGroupId>/<str:selectionType>', contact_views.move_contact_existing_group),
    path('contact/copyContactNewGroup/<int:oldGroupId>/<str:selectionType>', contact_views.copy_contact_new_group),
    path('contact/getBadEmail', contact_views.get_bad_email),
    path('contact/getBadSms', contact_views.get_bad_sms),
    path('contact/getUnsubscribedContactList', contact_views.get_unsubscribed_contact_list),
    path('contact/removeDuplicateContact/<int:groupId>', contact_views.remove_duplicate_contact),
    path('contact/getDuplicateContactList/<int:groupId>/', contact_views.get_duplicate_contact_list),
    path('contact/countTotalGroupContact/<int:memberId>/<int:groupId>', contact_views.count_total_group_contact),
    path('contact/countTotalGroupContactOnlyEmail/<int:memberId>/<int:groupId>', contact_views.count_total_group_contact_only_email),
    path('contact/countTotalBadEmail/<int:memberId>', contact_views.count_total_bad_email),
    path('contact/countTotalBadSms/<int:memberId>', contact_views.count_total_bad_sms),
    path('contact/countTotalUnsubscribedEmailContact/<int:memberId>', contact_views.count_total_unsubscribed_email_contact),
    path('contact/countTotalDuplicateEmailOrSMSContact/<int:memberId>/<int:groupId>', contact_views.count_total_duplicate_email_or_sms_contact),
    path('contact/getTotalContact', contact_views.get_total_contact),
    path('contact/getContactList/<int:groupId>', contact_views.get_contact_list),
    path('contact/getFullView/<int:groupId>/<int:segmentId>', contact_views.get_full_view),
    path('contact/findUserByGroup/<int:groupId>/<int:memberId>', contact_views.find_user_by_group),
    path('contact/findSmsPollingUserByGroup/<int:groupId>/<int:memberId>', contact_views.find_sms_polling_user_by_group),
    path('contact/countTotalSmsPollingGroupContact/<int:memberId>/<int:groupId>', contact_views.count_total_sms_polling_group_contact),
    path('contact/findLimitContactList/<int:memberId>/<int:limit>', contact_views.find_limit_contact_list),
    path('contact/findDuplicateUserByGroup/<int:groupId>/<int:memberId>', contact_views.find_duplicate_user_by_group),
    path('contact/findUnsubscribedSms/<int:memberId>', contact_views.find_unsubscribed_sms),
    path('contact/countTotalUnsubscribedSmsContact/<int:memberId>', contact_views.count_total_unsubscribed_sms_contact),
    path('contact/getSmsPollingContactList/<int:groupId>', contact_views.get_sms_polling_contact_list),
    path('contact/addInviteByUrlContact', contact_views.add_invite_by_url_contact),
    path('contact/getDownloadNotGroupContactFile/<str:filterData>', contact_views.get_download_not_group_contact_file),
    path('contact/getContactNumberList/<str:searchName>', contact_views.get_contact_number_list),
    # path('contact/getContactEmailList', contact_views.get_contact_email_list),
    path('contact/getContactEmailList/<str:searchName>', contact_views.get_contact_email_list),
    path('contact/getUnsubscribedSmsContactList', contact_views.get_unsubscribed_sms_contact_list),
    path('contact/sendEmailToContact', contact_views.send_email_to_contact),
    path('contact/checkOptin', contact_views.check_optin),

    # Contact Import
    path('contactImport', contact_import_views.import_contact),
    path('contactImport/headerFieldMapping', contact_import_views.get_header_field_mapping),
    path('contactImport/selectHeaders', contact_import_views.get_selected_headers),
    path('contactImport/addTempCronContact', contact_import_views.add_temp_cron_contact),
    path('contactImport/updateImportContact', contact_import_views.update_import_contact),
    path('contactImport/cancelUpload', contact_import_views.cancel_upload),
    path('contactImport/optOutDetails', contact_import_views.opt_out_details),
    path('contactImport/optInDetails', contact_import_views.opt_in_details),
    path('contactImport/optOut', contact_import_views.opt_out),
    path('contactImport/optIn', contact_import_views.opt_in),
    path('contactImport/sendSubscribeLink', contact_import_views.send_subscribe_link),
    path('contactImport/emailVerificationGroup', contact_import_views.email_verification_group),
    path('contactImport/smsStatusUrlSendSmsOptIn', contact_import_views.sms_status_url_send_sms_opt_in),
    path('contactImport/contactImportFile', contact_import_views.contact_import_file),

    # SMS Inbox
    path('smsInbox/getAllReplyCount', sms_inbox_views.get_all_reply_count),
    path('smsInbox/getSMSCampaignPhoneNumberList', sms_inbox_views.get_sms_campaign_phone_number_list),
    path('smsInbox/getSMSCampaignList/<str:phoneNumber>', sms_inbox_views.get_sms_campaign_list),
    path('smsInbox/getSMSCampaignDetailList/<str:phoneNumber>/<int:crEmailId>/<int:crSmsId>', sms_inbox_views.get_sms_campaign_detail_list),
    path('smsInbox/getConversationsList', sms_inbox_views.get_conversations_list),
    path('smsInbox/getConversationsClosedList', sms_inbox_views.get_conversations_closed_list),
    path('smsInbox/getConversationsContactList/<str:searchName>', sms_inbox_views.get_conversations_contact_list),
    path('smsInbox/currentConversationsDetailList', sms_inbox_views.current_conversations_detail_list),
    path('smsInbox/sendConversations', sms_inbox_views.send_conversations),
    path('smsInbox/closedConversations', sms_inbox_views.closed_conversations),
    path('smsInbox/buyNumber', sms_inbox_views.buy_number),
    path('smsInbox/checkInboxForConversation/<str:clientNumber>', sms_inbox_views.check_inbox_for_conversation),
    path('smsInbox/deleteSmsConversationsNumber/<int:tenantId>', sms_inbox_views.delete_sms_conversations_number),
    path('smsInbox/changeSmsConversationsNumber', sms_inbox_views.change_sms_conversations_number),
    path('smsInbox/setConversationNumber', sms_inbox_views.set_conversation_number),
    path('smsInbox/campaignCloseConversation', sms_inbox_views.campaign_close_conversation),
    path('smsInbox/smsStatusUrl', sms_inbox_views.sms_status_url),
    path('smsInbox/checkDefaultConversationsNumber', sms_inbox_views.check_default_conversations_number),
    path('smsInbox/checkConversationsNumberStatus', sms_inbox_views.check_conversations_number_status),
    path('smsInbox/getConversationsNumber', sms_inbox_views.get_conversations_number),

    # Group
    path('group/getGroupList', group_views.getGroupList),
    path('group/getGroupListWithCheckDuplicate', group_views.getGroupListWithCheckDuplicate),
    path('group/getGroupById/<int:groupId>', group_views.getGroupById),
    path('group/saveGroup', group_views.saveGroup),
    path('group/deleteBulkGroup', group_views.deleteBulkGroup),
    path('group/getGroupUDFList/<int:groupId>', group_views.getUDFlist),
    path('group/getGroupUDFValueList/<int:groupId>/<str:groupUDF>', group_views.getGroupUDFValueList),  # NEW
    path('group/getGroupContactHeader/<int:groupId>', group_views.getGroupContactHeader),  # NEW
    path('group/getGroupContactHeaderKey/<int:groupId>', group_views.getGroupContactHeaderKey),  # NEW
    path('group/inviteByUrl', group_views.inviteByUrl),  # NEW
    path('group/getInviteByUrlData', group_views.getInviteByUrlData),  # NEW
    path('group/getGroupUDF/<int:groupId>', group_views.getGroupUDF),
    path('group/getGroupUDFAuto/<int:groupId>', group_views.getGroupUDFAuto),
    path('group/getGroupFirstRecords/<int:groupId>', group_views.getGroupFirstRecords),  # NEW
    path('group/getGroupSmsTotalCount', group_views.getGroupSmsTotalCount),  # NEW
    path('group/getGroupListCombo', group_views.getGroupListCombo),
    path('group/sendOptInGroup', group_views.sendOptInGroup),
    path('group/getGroupContactCount/<int:groupId>', group_views.getGroupContactCount),  # NEW
    path('group/getGroupFieldsList/<int:groupId>', group_views.getGroupFieldsList),


    # Group Segment
    path('groupSegment/addSegment', group_segment_views.addSegment),
    path('groupSegment/updateSegment/<int:segmentId>', group_segment_views.updateSegment),
    path('groupSegment/getSegment/<int:segmentId>', group_segment_views.getSegment),
    path('groupSegment/getSegmentList/<int:groupId>', group_segment_views.getSegmentList),
    path('groupSegment/deleteBulkSegment', group_segment_views.deleteBulkSegment),
    path('groupSegment/getSegmentContactList/<int:groupId>/<int:segmentId>', group_segment_views.getSegmentContactList),
]
