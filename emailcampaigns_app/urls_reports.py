from django.urls import path
from emailcampaigns_app.views import email_campaigns_ab_testing_report_views

urlpatterns = [
    path('getEmailCampaignsReportDashboardAB', email_campaigns_ab_testing_report_views.getEmailCampaignsReportDashboardAB, name='getEmailCampaignsReportDashboardAB'),
    path('getEmailCampaignsReportProductLinksAB', email_campaigns_ab_testing_report_views.getEmailCampaignsReportProductLinksAB, name='getEmailCampaignsReportProductLinksAB'),
    path('getEmailCampaignsReportMembersListPageAB', email_campaigns_ab_testing_report_views.getEmailCampaignsReportMembersListPageAB, name='getEmailCampaignsReportMembersListPageAB'),
    path('getEmailCampaignsReportMembersBListPageAB', email_campaigns_ab_testing_report_views.getEmailCampaignsReportMembersBListPageAB, name='getEmailCampaignsReportMembersBListPageAB'),
    path('getEmailCampaignsReportMembersOListPageAB', email_campaigns_ab_testing_report_views.getEmailCampaignsReportMembersOListPageAB, name='getEmailCampaignsReportMembersOListPageAB'),
    path('getEmailCampaignsReportSourcesAB', email_campaigns_ab_testing_report_views.getEmailCampaignsReportSourcesAB, name='getEmailCampaignsReportSourcesAB'),
    path('getCampaignsReportPrintAB', email_campaigns_ab_testing_report_views.getCampaignsReportPrintAB, name='getCampaignsReportPrintAB'),
    path('setChooseWinner', email_campaigns_ab_testing_report_views.setChooseWinner, name='setChooseWinner'),
    path('getEmailCampaignsReportMembersListAB', email_campaigns_ab_testing_report_views.getEmailCampaignsReportMembersListAB, name='getEmailCampaignsReportMembersListAB'),
    path('getEmailCampaignsMemberOpenListPageAB', email_campaigns_ab_testing_report_views.getEmailCampaignsMemberOpenListPageAB, name='getEmailCampaignsMemberOpenListPageAB'),
]
