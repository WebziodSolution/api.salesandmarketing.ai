from django.urls import path, include
from socialmediacampaigns_app.views import facebook_views, linkedin_views, twitter_views, socialmediacampaigns_views, socialmediacampaign_report_views

urlpatterns = [
    # Facebook Endpoints
    path('facebook/facebookLogin', facebook_views.facebookLogin),
    path('facebook/facebookOauth', facebook_views.facebookOauth),
    path('facebook/getFacebookUserData', facebook_views.getFacebookUserData),
    path('facebook/setFacebookPost', facebook_views.setFacebookPost),
    path('facebook/setFacebookImagePost', facebook_views.setFacebookImagePost),
    path('facebook/facebookLogout', facebook_views.facebookLogout),

    # LinkedIn Endpoints
    path('linkedin/linkedinLogin', linkedin_views.linkedinLogin),
    path('linkedin/linkedInOauth', linkedin_views.linkedInOauth),
    path('linkedin/linkedinUserData', linkedin_views.getLinkedinUserData),
    path('linkedin/linkedinPagesData', linkedin_views.getLinkedinPagesData),
    path('linkedin/linkedinSetPost', linkedin_views.setLinkedinPost),
    path('linkedin/linkedinImagePost', linkedin_views.setLinkedinImagePost),
    path('linkedin/linkedinLogout', linkedin_views.linkedinLogout),

    # Twitter Endpoints
    path('twitter/twitterLogin', twitter_views.twitterLogin),
    path('twitter/twitterOauth', twitter_views.twitterOauth),
    path('twitter/getTwitterUserData', twitter_views.getTwitterUserData),
    path('twitter/setTwitterPost', twitter_views.setTwitterPost),
    path('twitter/setTwitterImagePost', twitter_views.setTwitterImagePost),
    path('twitter/twitterLogout', twitter_views.twitterLogout),

    # Social Media Campaign Endpoints
    path('socialMediaCampaign/', include([
        path('getSocialMediaCampaignList', socialmediacampaigns_views.getSocialMediaCampaignList),
        path('deleteSocialMediaPost', socialmediacampaigns_views.deleteSocialMediaPost),
        path('saveAsDraft', socialmediacampaigns_views.saveAsDraft),
        path('saveSchedule', socialmediacampaigns_views.saveSchedule),
        path('editSocialMediaPostSchedule', socialmediacampaigns_views.editSocialMediaPostSchedule),
        path('postNow', socialmediacampaigns_views.postNow),
        path('getSocialMediaCampaign', socialmediacampaigns_views.getSocialMediaCampaign),
        path('getSocialMediaAuthData', socialmediacampaigns_views.getSocialMediaAuthData),
        path('getLinkPreview', socialmediacampaigns_views.getLinkPreview),
        path('uploadImage', socialmediacampaigns_views.uploadImage),
        path('uploadVideo', socialmediacampaigns_views.uploadVideo),
        path('removeImage/<int:smId>/<str:imageName>', socialmediacampaigns_views.removeImage),
        path('getSocialMediaAuthentication', socialmediacampaigns_views.getSocialMediaAuthentication),
    ])),

    # Social Media Campaign Report Endpoints
    path('socialMediaCampaignReport/', include([
        path('getSocialMediaCampaignReportListPage', socialmediacampaign_report_views.getSocialMediaCampaignReportListPage),
        path('getReportFacebookPageDetails', socialmediacampaign_report_views.getReportFacebookPageDetails),
        path('reportFacebookPostDetails', socialmediacampaign_report_views.reportFacebookPostDetails),
        path('reportFacebookPostReactions', socialmediacampaign_report_views.reportFacebookPostReactions),
        path('reportFacebookPostComments', socialmediacampaign_report_views.reportFacebookPostComments),
        path('getReportTwitterTweetsDetails', socialmediacampaign_report_views.getReportTwitterTweetsDetails),
        path('getReportLinkedinWallDetails', socialmediacampaign_report_views.getReportLinkedinWallDetails),
        path('getReportLinkedinPageList', socialmediacampaign_report_views.getReportLinkedinPageList),
        path('getReportLinkedinPageDetails', socialmediacampaign_report_views.getReportLinkedinPageDetails),
        path('getReportLinkedinReactionReport', socialmediacampaign_report_views.getReportLinkedinReactionReport),
        path('getReportLinkedinCommentsReport', socialmediacampaign_report_views.getReportLinkedinCommentsReport),
    ])),
]
