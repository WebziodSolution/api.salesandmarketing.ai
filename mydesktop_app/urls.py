from django.urls import path
from mydesktop_app.views import assessment_template_views, my_pages_views, sms_template_views, survey_template_views

urlpatterns = [
    # Assessment Template endpoints
    path('assessmentTemplate/getAssessmentTemplateList/<int:atStatus>', assessment_template_views.getAssessmentTemplateList, name='getAssessmentTemplateList'),
    path('assessmentTemplate/saveAssessmentTemplate', assessment_template_views.saveAssessmentTemplate, name='saveAssessmentTemplate'),
    path('assessmentTemplate/getAssessmentTemplateById/<int:at_id>', assessment_template_views.getAssessmentTemplateById, name='getAssessmentTemplateById'),
    path('assessmentTemplate/deleteAssessmentTemplate/<int:at_id>', assessment_template_views.deleteAssessmentTemplate, name='deleteAssessmentTemplate'),
    path('assessmentTemplate/getAssessmentTemplateOnlyDataById/<int:at_id>', assessment_template_views.getAssessmentTemplateOnlyDataById, name='getAssessmentTemplateOnlyDataById'),
    path('assessmentTemplate/getAssessmentTemplateCopy/<int:subMemberId>/<int:atId>', assessment_template_views.getAssessmentTemplateCopy, name='getAssessmentTemplateCopy'),

    # MyPages endpoints
    path('mypages/getMyPagesTags/<int:mpStageId>', my_pages_views.listMyPageTags, name='listMyPageTags'),
    path('mypages/getMyPagesList/<int:mpStageId>', my_pages_views.listMyPage, name='listMyPage'),
    path('mypages/saveForLater', my_pages_views.saveForLater, name='saveForLater'),
    path('mypages/publish', my_pages_views.publish, name='publish'),
    path('mypages/autoSave', my_pages_views.autoSave, name='autoSave'),
    path('mypages/getGroupLanguageList', my_pages_views.getGroupLanguageList, name='getGroupLanguageList'),
    path('mypages/deleteMyPage/<int:mpId>', my_pages_views.deleteMyPage, name='deleteMyPage'),
    path('mypages/getMyPageClone/<int:subTenantId>/<int:mpId>', my_pages_views.getMyPageClone, name='getMyPageClone'),
    path('mypages/getMyPageById/<int:mpId>', my_pages_views.getMyPageById, name='getMyPageById'),
    path('mypages/getFreeTemplateTags', my_pages_views.getFreeTemplateTags, name='getFreeTemplateTags'),
    path('mypages/getFreeTemplateList', my_pages_views.getFreeTemplateList, name='getFreeTemplateList'),
    path('mypages/getPreview', my_pages_views.getPreview, name='getPreview'),
    path('mypages/getPreviewFreeTemplate/<str:ftFolderName>', my_pages_views.getPreviewFreeTemplate, name='getPreviewFreeTemplate'),
    path('mypages/sendMyPageEmailPreview', my_pages_views.sendMyPageEmailPreview, name='sendMyPageEmailPreview'),


    # SmsTemplate endpoints
    path('smsTemplate/getSmsTemplateSelect', sms_template_views.getSmsTemplateSelect, name='getSmsTemplateSelect'),
    path('smsTemplate/getSmsTemplateDetails/<int:sstId>/<int:emailId>', sms_template_views.getSmsTemplateDetails, name='getSmsTemplateDetails'),
    path('smsTemplate/deleteSmsTemplate/<int:sstId>', sms_template_views.deleteSmsTemplate, name='deleteSmsTemplate'),
    path('smsTemplate/getSmsTemplate/<int:sstId>', sms_template_views.getSmsTemplate, name='getSmsTemplate'),
    path('smsTemplate/getSmsTemplateList', sms_template_views.getSmsTemplateList, name='getSmsTemplateList'),
    path('smsTemplate/saveSmsTemplate', sms_template_views.saveSmsTemplate, name='saveSmsTemplate'),

    # Survey Template endpoints
    path('surveyTemplate/getSurveyTemplateList/<int:stStatus>', survey_template_views.listSurveyTemplate, name='getSurveyTemplateList'),
    path('surveyTemplate/saveSurveyTemplate', survey_template_views.saveSurveyTemplate, name='saveSurveyTemplate'),
    path('surveyTemplate/getSurveyTemplateById/<int:stId>', survey_template_views.getSurveyTemplateById, name='getSurveyTemplateById'),
    path('surveyTemplate/deleteSurveyTemplate/<int:stId>', survey_template_views.deleteSurveyTemplate, name='deleteSurveyTemplate'),
    path('surveyTemplate/getSurveyTemplateOnlyDataById/<int:stId>', survey_template_views.getSurveyTemplateOnlyDataById, name='getSurveyTemplateOnlyDataById'),
    path('surveyTemplate/getSurveyTemplateCopy/<int:subMemberId>/<int:stId>', survey_template_views.getSurveyTemplateCopy, name='getSurveyTemplateCopy'),

]
