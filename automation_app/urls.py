from django.urls import path
from .views import automation_views, automation_sms_views

urlpatterns = [
    # Automation Controller paths
    path('automation/createAutomation', automation_views.createAutomation, name='createAutomation'),
    path('automation/deleteAutomation', automation_views.deleteAutomation, name='deleteAutomation'),
    path('automation/getAutomationList', automation_views.getAutomationList, name='getAutomationList'),
    path('automation/getAutomationById/<int:amId>', automation_views.getAutomationById, name='getAutomationById'),
    path('automation/getAutomationReportById/<int:amId>', automation_views.getAutomationReportById, name='getAutomationReportById'),
    path('automation/getAutomationReportDashboard/<int:amId>', automation_views.getAutomationReportDashboard, name='getAutomationReportDashboard'),
    path('automation/getAutomationMyPageLinkList', automation_views.getAutomationMyPageLinkList, name='getAutomationMyPageLinkList'),
    path('automation/stopAutomationById', automation_views.stopAutomationById, name='stopAutomationById'),
    path('automation/startAutomationById', automation_views.startAutomationById, name='startAutomationById'),
    path('automation/copyAutomationById', automation_views.copyAutomationById, name='copyAutomationById'),
    path('automation/getAutomationBouncedReportList', automation_views.getAutomationBouncedReportList, name='getAutomationBouncedReportList'),
    path('automation/getAutomationReportProductLinks', automation_views.getAutomationReportProductLinks, name='getAutomationReportProductLinks'),
    path('automation/getAutomationReportMembersListPage', automation_views.getAutomationReportMembersListPage, name='getAutomationReportMembersListPage'),
    path('automation/getAutomationReportSources', automation_views.getAutomationReportSources, name='getAutomationReportSources'),
    path('automation/getAutomationReportProductLinksClickUser', automation_views.getAutomationReportProductLinksClickUser, name='getAutomationReportProductLinksClickUser'),
    path('automation/getAutomationReportMemberClick', automation_views.getAutomationReportMemberClick, name='getAutomationReportMemberClick'),
    path('automation/getAutomationReportMembersList', automation_views.getAutomationReportMembersList, name='getAutomationReportMembersList'),
    path('automation/getAutomationSmsReportById', automation_views.getAutomationSmsReportById, name='getAutomationSmsReportById'),
    path('automation/automationSmsCloseById', automation_views.automationSmsCloseById, name='automationSmsCloseById'),
    
    # Automation SMS Controller paths
    path('automationSms/getBuyAllNumberList', automation_sms_views.getBuyAllNumberList, name='getBuyAllNumberList'),
]
