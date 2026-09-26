from django.urls import path
from analytics_app.views import analytics_website_tracking_views, analytics_event_views

urlpatterns = [
    # Analytics Website Tracking
    path('analyticsTracking/getAllAnalyticsWebsites', analytics_website_tracking_views.getAllAnalyticsWebsites, name='getAllAnalyticsWebsites'),
    path('analyticsTracking/saveAnalyticsWebsite', analytics_website_tracking_views.saveAnalyticsWebsite, name='saveAnalyticsWebsite'),
    path('analyticsTracking/deleteAnalyticsWebsite', analytics_website_tracking_views.deleteAnalyticsWebsite, name='deleteAnalyticsWebsite'),
    
    # Analytics Events
    path('analytics/getDashBoardComboList', analytics_event_views.getDashBoardComboList, name='getDashBoardComboList'),
    path('analytics/getDevicesUsersCampaigns', analytics_event_views.getDevicesUsersCampaigns, name='getDevicesUsersCampaigns'),
    path('analytics/getSessionPageLogData', analytics_event_views.getSessionPageLogData, name='getSessionPageLogData'),
    path('analytics/getDashboardData', analytics_event_views.getDashboardData, name='getDashboardData'),
    path('analytics/getMinuteActiveUsers', analytics_event_views.getMinuteActiveUsers, name='getMinuteActiveUsers'),
    path('analytics/getPageLogData', analytics_event_views.getPageLogData, name='getPageLogData'),
    path('analytics/getCountryLogData', analytics_event_views.getCountryLogData, name='getCountryLogData'),
    path('analytics/getEmailCampaignOpenMemberLink', analytics_event_views.getEmailCampaignOpenMemberLink, name='getEmailCampaignOpenMemberLink'),
    path('analytics/getEmailCampaignOpenMemberLinkCSV', analytics_event_views.getEmailCampaignOpenMemberLinkCSV, name='getEmailCampaignOpenMemberLinkCSV'),
    path('analytics/grabAnalyticsCsvData', analytics_event_views.grabAnalyticsCsvData, name='grabAnalyticsCsvData'),
]
