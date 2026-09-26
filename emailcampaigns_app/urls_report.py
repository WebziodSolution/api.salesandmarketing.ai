from django.urls import path
from .views import email_campaigns_report_views as report_views

urlpatterns = [
    path('getEmailCampaignsReportListPage', report_views.getEmailCampaignsReportListPage, name='getEmailCampaignsReportListPage'),
    path('getEmailCampaignsReportDashboard', report_views.getEmailCampaignsReportDashboard, name='getEmailCampaignsReportDashboard'),
    path('getEmailCampaignsReportProductLinks', report_views.getEmailCampaignsReportProductLinks, name='getEmailCampaignsReportProductLinks'),
    path('getEmailCampaignsReportProductLinksClickUser', report_views.getEmailCampaignsReportProductLinksClickUser, name='getEmailCampaignsReportProductLinksClickUser'),
    path('getEmailCampaignsReportMembersListPage', report_views.getEmailCampaignsReportMembersListPage, name='getEmailCampaignsReportMembersListPage'),
    path('getEmailCampaignsReportMemberClick', report_views.getEmailCampaignsReportMemberClick, name='getEmailCampaignsReportMemberClick'),
    path('getEmailCampaignsReportSources', report_views.getEmailCampaignsReportSources, name='getEmailCampaignsReportSources'),
    path('getCampaignsReportPrint', report_views.getCampaignsReportPrint, name='getCampaignsReportPrint'),
    path('getEmailCampaignsReportMembersList', report_views.getEmailCampaignsReportMembersList, name='getEmailCampaignsReportMembersList'),
    path('getBouncedEmailReportList', report_views.getBouncedEmailReportList, name='getBouncedEmailReportList'),
    path('getEmailCampaignsMemberOpenListPage', report_views.getEmailCampaignsMemberOpenListPage, name='getEmailCampaignsMemberOpenListPage'),
    path('getEmailCampaignsMemberOpenList', report_views.getEmailCampaignsMemberOpenList, name='getEmailCampaignsMemberOpenList'),
]
