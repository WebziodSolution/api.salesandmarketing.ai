from django.urls import path
from survey_app.views import survey_category_views, survey_views, survey_report_views

urlpatterns = [
    # Survey Category
    path('surveyCategory/getSurveyCategoryList', survey_category_views.getSurveyCategoryList, name='getSurveyCategoryList'),
    path('surveyCategory/getSurveyCategoryById/<int:qc_id>', survey_category_views.getSurveyCategoryById, name='getSurveyCategoryById'),
    path('surveyCategory/deleteSurveyCategory', survey_category_views.deleteSurveyCategory, name='deleteSurveyCategory'),
    path('surveyCategory/getSurveyCategoryListPages', survey_category_views.getSurveyCategoryListPages, name='getSurveyCategoryListPages'),
    path('surveyCategory/saveSurveyCategory', survey_category_views.saveSurveyCategory, name='saveSurveyCategory'),

    # Survey
    path('survey/getSurveyAllList', survey_views.getSurveyAllList, name='getSurveyAllList'),
    path('survey/getSurveyAllListAuto', survey_views.getSurveyAllListAuto, name='getSurveyAllListAuto'),
    path('survey/saveSurveyData', survey_views.saveSurveyData, name='saveSurveyData'),
    path('survey/deleteSurvey', survey_views.deleteSurvey, name='deleteSurvey'),
    path('survey/getSurveyListPages', survey_views.getSurveyListPages, name='getSurveyListPages'),
    path('survey/getSurveyById/<int:sryId>', survey_views.getSurveyById, name='getSurveyById'),
    path('survey/closeSurvey', survey_views.closeSurvey, name='closeSurvey'),
    path('survey/getSurveyCopy/<int:subMemberId>/<int:sryId>', survey_views.getSurveyCopy, name='getSurveyCopy'),
    path('survey/getPreviewSurveyData', survey_views.getPreviewSurveyData, name='getPreviewSurveyData'),
    path('survey/saveSurveyAnswers', survey_views.saveSurveyAnswers, name='saveSurveyAnswers'),
    path('survey/saveSendSurvey', survey_views.finalSendSurvey, name='finalSendSurvey'),
    path('survey/checkSurveyNameExists', survey_views.checkSurveyNameExists, name='checkSurveyNameExists'),

    # Survey Report
    path('surveyReport/getSurveyReportDemographic', survey_report_views.getSurveyReportDemographic, name='getSurveyReportDemographic'),
    path('surveyReport/getSurveyReportTechnologyUse', survey_report_views.getSurveyReportTechnologyUse, name='getSurveyReportTechnologyUse'),
    path('surveyReport/getSurveyReportQuestions', survey_report_views.getSurveyReportQuestions, name='getSurveyReportQuestions'),
    path('surveyReport/getSurveyReportTextAnswers', survey_report_views.getSurveyReportTextAnswers, name='getSurveyReportTextAnswers'),
    path('surveyReport/getSurveyReportQuestionsComboList', survey_report_views.getSurveyReportQuestionsComboList, name='getSurveyReportQuestionsComboList'),
    path('surveyReport/getSurveyReportAnswersComboList', survey_report_views.getSurveyReportAnswersComboList, name='getSurveyReportAnswersComboList'),
    path('surveyReport/surveyReportDataBrowser', survey_report_views.surveyReportDataBrowser, name='surveyReportDataBrowser'),
    path('surveyReport/getSurveyReportParticipant', survey_report_views.getSurveyReportParticipant, name='getSurveyReportParticipant'),
]
