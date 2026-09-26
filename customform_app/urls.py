from django.urls import path
from customform_app.views import custom_form_views

urlpatterns = [
    path('getCustomFormLinkList', custom_form_views.getCustomFormLinkList, name='getCustomFormLinkList'),
    path('getCustomFormLinkListAuto', custom_form_views.getCustomFormLinkListAuto, name='getCustomFormLinkListAuto'),
    path('getCustomFormList/<int:cfFormStatus>', custom_form_views.getCustomFormList, name='getCustomFormList'),
    path('getCustomFormDataById/<int:cfId>', custom_form_views.getCustomFormDataById, name='getCustomFormDataById'),
    path('saveCustomFormData', custom_form_views.saveCustomForm, name='saveCustomForm'),
    path('deleteCustomForm/<int:cfId>', custom_form_views.deleteCustomForm, name='deleteCustomForm'),
    path('getCustomFormCopy/<int:subMemberId>/<int:cfId>', custom_form_views.getCustomFormCopy, name='getCustomFormCopy'),
    path('getPreviewCustomFormData', custom_form_views.getPreviewCustomFormData, name='getPreviewCustomFormData'),
    path('saveCustomFormAnswers', custom_form_views.saveCustomFormAnswers, name='saveCustomFormAnswers'),
    path('getCustomFormListPages', custom_form_views.getCustomFormListPages, name='getCustomFormListPages'),
    path('getCustomFormReport', custom_form_views.getCustomFormReport, name='getCustomFormReport'),
    path('deleteCustomFormAnswers', custom_form_views.deleteCustomFormAnswers, name='deleteCustomFormAnswers'),
    path('getCustomFormAllDataReport', custom_form_views.getCustomFormAllDataReport, name='getCustomFormAllDataReport'),
    path('checkCustomFormNameExists', custom_form_views.checkCustomFormNameExists, name='checkCustomFormNameExists'),
    path('reportExportFormToGroup', custom_form_views.reportExportFormToGroup, name='reportExportFormToGroup'),
    path('grabCustomFormPdfData', custom_form_views.grabCustomFormPdfData, name='grabCustomFormPdfData'),
]
