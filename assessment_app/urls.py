from django.urls import path
from .views import assessment_category_views, assessment_groups_views, assessment_report_views, assessment_views

urlpatterns = [
    path('assessmentCategory/getAssessmentCategoryList', assessment_category_views.getAssessmentCategoryList, name='getAssessmentCategoryList'),
    path('assessmentCategory/getAssessmentCategoryById/<int:cat_id>', assessment_category_views.getAssessmentCategoryById, name='getAssessmentCategoryById'),
    path('assessmentCategory/deleteAssessmentCategory', assessment_category_views.deleteAssessmentCategory, name='deleteAssessmentCategory'),
    path('assessmentCategory/getAssessmentCategoryListPages', assessment_category_views.getAssessmentCategoryListPages, name='getAssessmentCategoryListPages'),
    path('assessmentCategory/saveAssessmentCategory', assessment_category_views.saveAssessmentCategory, name='saveAssessmentCategory'),
    
    path('assessmentGroups/getAssessmentGroupsList', assessment_groups_views.getAssessmentGroupsList, name='getAssessmentGroupsList'),
    path('assessmentGroups/deleteAssessmentGroups', assessment_groups_views.deleteAssessmentGroups, name='deleteAssessmentGroups'),
    path('assessmentGroups/saveAssessmentGroups', assessment_groups_views.saveAssessmentGroups, name='saveAssessmentGroups'),

    # Assessment Report Endpoints
    path('assessmentReport/getAssessmentReportDemographic', assessment_report_views.AssessmentReportDemographicView.as_view(), name='get_assessment_report_demographic'),
    path('assessmentReport/getAssessmentReportTechnologyUse', assessment_report_views.AssessmentReportTechnologyUseView.as_view(), name='get_assessment_report_technology_use'),
    path('assessmentReport/getSurveyReportQuestions', assessment_report_views.AssessmentReportQuestionsView.as_view(), name='get_survey_report_questions'),
    path('assessmentReport/getAssessmentReportTextAnswers', assessment_report_views.AssessmentReportTextAnswersView.as_view(), name='get_assessment_report_text_answers'),
    path('assessmentReport/getAssessmentReportQuestionsComboList', assessment_report_views.AssessmentReportQuestionsComboListView.as_view(), name='get_assessment_report_questions_combo_list'),
    path('assessmentReport/getAssessmentReportAnswersComboList', assessment_report_views.AssessmentReportAnswersComboListView.as_view(), name='get_assessment_report_answers_combo_list'),
    path('assessmentReport/assessmentReportDataBrowser', assessment_report_views.AssessmentReportDataBrowserView.as_view(), name='assessment_report_data_browser'),
    path('assessmentReport/getAssessmentReportParticipant', assessment_report_views.AssessmentReportParticipantView.as_view(), name='get_assessment_report_participant'),

    # Assessment Endpoints
    path('assessment/getAssessmentAllList', assessment_views.getAssessmentAllList, name='getAssessmentAllList'),
    path('assessment/getAssessmentAllListAuto', assessment_views.getAssessmentAllListAuto, name='getAssessmentAllListAuto'),
    path('assessment/saveAssessmentData', assessment_views.saveAssessmentData, name='saveAssessmentData'),
    path('assessment/deleteAssessment', assessment_views.deleteAssessment, name='deleteAssessment'),
    path('assessment/getAssessmentListPages', assessment_views.getAssessmentListPages, name='getAssessmentListPages'),
    path('assessment/getAssessmentById/<int:assId>', assessment_views.getAssessmentById, name='getAssessmentById'),
    path('assessment/closeAssessment', assessment_views.closeAssessment, name='closeAssessment'),
    path('assessment/getAssessmentCopy/<int:subTenantId>/<int:assId>', assessment_views.getAssessmentCopy, name='getAssessmentCopy'),
    path('assessment/getPreviewAssessmentData', assessment_views.getPreviewAssessmentData, name='getPreviewAssessmentData'),
    path('assessment/saveAssessmentAnswers', assessment_views.saveAssessmentAnswers, name='saveAssessmentAnswers'),
    path('assessment/saveSendAssessment', assessment_views.finalSendAssessment, name='finalSendAssessment'),
    path('assessment/checkAssessmentNameExists', assessment_views.checkAssessmentNameExists, name='checkAssessmentNameExists'),
]
