from django.urls import path
from smspolling_app.views import sms_polling_views, sms_polling_report_views

urlpatterns = [
    # SMS Polling
    path('smsPolling/getSmsPollingList', sms_polling_views.getSmsPollingList, name='getSmsPollingList'),
    path('smsPolling/deleteSmsPolling', sms_polling_views.deleteSmsPolling, name='deleteSmsPolling'),
    path('smsPolling/closeSmsPolling', sms_polling_views.closeSmsPolling, name='closeSmsPolling'),
    path('smsPolling/getSmsPolling/<str:rndHash>', sms_polling_views.getSmsPolling, name='getSmsPolling'),
    path('smsPolling/saveSmsInfo', sms_polling_views.saveSmsInfo, name='saveSmsInfo'),
    path('smsPolling/saveMemberList', sms_polling_views.saveMemberList, name='saveMemberList'),
    path('smsPolling/addSmsPollingCategory', sms_polling_views.addSmsPollingCategory, name='addSmsPollingCategory'),
    path('smsPolling/getSmsPollingCategoryList', sms_polling_views.getSmsPollingCategoryList, name='getSmsPollingCategoryList'),
    path('smsPolling/deleteSmsPollingQuestion', sms_polling_views.deleteSmsPollingQuestion, name='deleteSmsPollingQuestion'),
    path('smsPolling/saveSmsPollingQuestion', sms_polling_views.saveSmsPollingQuestion, name='saveSmsPollingQuestion'),
    path('smsPolling/getDuplicateSmsPolling/<int:subMemberId>/<str:rndHash>', sms_polling_views.getDuplicateSmsPolling, name='getDuplicateSmsPolling'),
    path('smsPolling/saveFinalizeQuestionOrder', sms_polling_views.saveFinalizeQuestionOrder, name='saveFinalizeQuestionOrder'),
    path('smsPolling/clearQuestionLogicFlow', sms_polling_views.clearQuestionLogicFlow, name='clearQuestionLogicFlow'),
    path('smsPolling/saveQuestionLogicFlow', sms_polling_views.saveQuestionLogicFlow, name='saveQuestionLogicFlow'),
    path('smsPolling/saveDemographicLocation', sms_polling_views.saveDemographicLocation, name='saveDemographicLocation'),
    path('smsPolling/saveAndConfirm', sms_polling_views.saveAndConfirm, name='saveAndConfirm'),
    path('smsPolling/publishAndConfirm', sms_polling_views.publishAndConfirm, name='publishAndConfirm'),
    path('smsPolling/finalPublishAndConfirm', sms_polling_views.finalPublishAndConfirm, name='finalPublishAndConfirm'),
    path('smsPolling/buyNumberForSmsPolling', sms_polling_views.buyNumberForSmsPolling, name='buyNumberForSmsPolling'),
    path('smsPolling/getSmsPollingPhoneList', sms_polling_views.getSmsPollingPhoneList, name='getSmsPollingPhoneList'),
    path('smsPolling/deleteSmsPollingNumber/<int:iId>', sms_polling_views.deleteSmsPollingNumber, name='deleteSmsPollingNumber'),
    path('smsPolling/smsStatusUrl', sms_polling_views.smsStatusUrl, name='smsStatusUrl'),
    path('smsPolling/countTotalSmsPollingWithOutDraft', sms_polling_views.countTotalSmsPollingWithOutDraft, name='countTotalSmsPollingWithOutDraft'),
    path('smsPolling/findLimitSmsPollingListWithOutDraft', sms_polling_views.findLimitSmsPollingListWithOutDraft, name='findLimitSmsPollingListWithOutDraft'),
    path('smsPolling/getTotalResponsesCount', sms_polling_views.getTotalResponsesCount, name='getTotalResponsesCount'),

    # SMS Polling Reports
    path('smsPollingReport/getSmsPollingReportDemographic', sms_polling_report_views.getSmsPollingReportDemographic, name='getSmsPollingReportDemographic'),
    path('smsPollingReport/getSmsPollingReportQuestions', sms_polling_report_views.getSmsPollingReportQuestions, name='getSmsPollingReportQuestions'),
    path('smsPollingReport/getSmsPollingReportTextAnswers', sms_polling_report_views.getSmsPollingReportTextAnswers, name='getSmsPollingReportTextAnswers'),
    path('smsPollingReport/getSmsPollingReportQuestionsComboList', sms_polling_report_views.getSmsPollingReportQuestionsComboList, name='getSmsPollingReportQuestionsComboList'),
    path('smsPollingReport/getSmsPollingReportAnswersComboList', sms_polling_report_views.getSmsPollingReportAnswersComboList, name='getSmsPollingReportAnswersComboList'),
    path('smsPollingReport/smsPollingReportDataBrowser', sms_polling_report_views.smsPollingReportDataBrowser, name='smsPollingReportDataBrowser'),
    path('smsPollingReport/getSmsPollingReportParticipate', sms_polling_report_views.getSmsPollingReportParticipate, name='getSmsPollingReportParticipate'),
]
