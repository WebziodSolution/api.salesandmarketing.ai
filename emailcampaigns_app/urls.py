from django.urls import path
from emailcampaigns_app.views import email_campaigns_views

urlpatterns = [
    # email_campaigns_views
    path('getCampaignListAutomation', email_campaigns_views.get_campaign_list_automation, name='getCampaignListAutomation'),
    path('getCampaignInfo/<int:campId>/<int:campSendId>', email_campaigns_views.get_campaign_info, name='getCampaignInfo'),
    path('getCampaignList', email_campaigns_views.get_campaign_list, name='getCampaignList'),
    path('editCampaignSchedule', email_campaigns_views.edit_campaign_schedule, name='editCampaignSchedule'),
    path('deleteCampaign', email_campaigns_views.delete_campaign, name='deleteCampaign'),
    path('pauseCampaign', email_campaigns_views.pause_campaign, name='pauseCampaign'),
    path('restartCampaign', email_campaigns_views.restart_campaign, name='restartCampaign'),
    path('resendAllCampaign', email_campaigns_views.resend_all_campaign, name='resendAllCampaign'),
    path('resendCampaignNotOpened', email_campaigns_views.resend_campaign_not_open, name='resendCampaignNotOpened'),
    path('saveResendCampaign', email_campaigns_views.save_resend_campaign, name='saveResendCampaign'),
    path('sendCampaign', email_campaigns_views.send_campaign, name='sendCampaign'),
    path('saveSendCampaign', email_campaigns_views.save_send_campaign, name='saveSendCampaign'),
    path('getCampaignExists/<str:campName>', email_campaigns_views.get_campaign_exists, name='getCampaignExists'),
    path('sendEmailPreview', email_campaigns_views.send_email_preview, name='sendEmailPreview'),
    path('checkSpam', email_campaigns_views.check_spam, name='checkSpam'),
    path('campaignLinkClick', email_campaigns_views.campaign_link_click, name='campaignLinkClick'),
    path('openEmail', email_campaigns_views.open_email, name='openEmail'),
    path('getCampaignById', email_campaigns_views.get_campaign_by_id, name='getCampaignById'),
    path('throttlingValidation', email_campaigns_views.throttling_validation, name='throttlingValidation'),
    path('sendEmail', email_campaigns_views.send_email, name='sendEmail'),
    path('viewInBrowser', email_campaigns_views.view_in_browser, name='viewInBrowser'),
    
    # Reporting Endpoints
    path('getEmailCampaignsReportListPage', email_campaigns_views.get_email_campaigns_report_list_page, name='getEmailCampaignsReportListPage'),
    path('getCampaignsReportListMembers', email_campaigns_views.get_email_campaigns_report_members_list_page, name='getCampaignsReportListMembers'),
    path('getCampaignsListBouncedEmail', email_campaigns_views.get_campaigns_list_bounced_email, name='getCampaignsListBouncedEmail'),
    path('getCampaignsReportPrint', email_campaigns_views.get_campaigns_report_print, name='getCampaignsReportPrint'),
    path('getEmailCampaignsReportDashboard', email_campaigns_views.get_email_campaigns_report_dashboard, name='getEmailCampaignsReportDashboard'),
    path('getEmailCampaignsReportProductLinks', email_campaigns_views.get_email_campaigns_report_product_links, name='getEmailCampaignsReportProductLinks'),
    path('productLinksClickUser', email_campaigns_views.get_email_campaigns_report_product_links_click_user, name='productLinksClickUser'),
    path('getEmailCampaignsReportMemberClick', email_campaigns_views.get_email_campaigns_report_member_click, name='getEmailCampaignsReportMemberClick'),
    path('getEmailCampaignsReportMemberClickDetail', email_campaigns_views.get_email_campaigns_report_member_click_detail, name='getEmailCampaignsReportMemberClickDetail'),
    path('getEmailCampaignsMemberOpenListPage', email_campaigns_views.get_email_campaigns_member_open_list_page, name='getEmailCampaignsMemberOpenListPage'),
    path('getEmailCampaignsReportSourceLinks', email_campaigns_views.get_email_campaigns_report_sources, name='getEmailCampaignsReportSourceLinks'),
]
