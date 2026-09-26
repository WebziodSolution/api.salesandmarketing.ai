from django.urls import path
from common_app.views import common_views
from common_app.views import polling_views
from common_app.views import telnyx_views

urlpatterns = [


    path('health/', common_views.health_check, name='health_check'),
    # CommonController routes
    path('lookupdata', common_views.lookupdata, name='lookupdata'),
    path('sendingEmail', common_views.sendingEmail, name='sendingEmail'),
    path('displayLanguage', common_views.displayLanguage, name='displayLanguage'),
    path('language', common_views.language, name='language'),
    path('country', common_views.country, name='country'),
    path('countryToState/<int:countryId>', common_views.countryToState, name='countryToState'),
    path('securityQuestion', common_views.securityQuestion, name='securityQuestion'),
    path('getRemoteAddress', common_views.getRemoteAddress, name='getRemoteAddress'),
    path('countryToStateName/<str:countryName>', common_views.countryToStateName, name='countryToStateName'),
    path('getCountryName/<int:countryId>', common_views.getCountryName, name='getCountryName'),
    path('getCountryId/<str:countryName>', common_views.getCountryId, name='getCountryId'),
    path('getGroupFirstRecords/<int:groupId>', common_views.getGroupFirstRecords, name='getGroupFirstRecords'),
    path('checkAuthorized', common_views.checkAuthorized, name='checkAuthorized'),
    path('validatePhoneFormat/<int:countryId>/<str:phoneNumber>', common_views.validatePhoneFormat, name='validatePhoneFormat'),
    path('unsubscribe', common_views.unsubscribe, name='unsubscribe'),
    path('smsReplyUrl', common_views.smsReplyUrl, name='smsReplyUrl'),
    path('getPriceList', common_views.getPriceList, name='getPriceList'),
    path('zeroBounceReturnUrl', common_views.zeroBounceReturnUrl, name='zeroBounceReturnUrl'),

    # PollingController routes mapped without prefix here
    path('polling/grabImages', polling_views.grabImages, name='grabImages'),
    path('polling/grabColors', polling_views.grabColors, name='grabColors'),
    path('polling/grabLinks', polling_views.grabLinks, name='grabLinks'),
    path('polling/grabAnalyticsCsv', polling_views.grabAnalyticsCsv, name='grabAnalyticsCsv'),
    path('polling/grabCustomFormPdfData', polling_views.grabCustomFormPdfData, name='grabCustomFormPdfData'),

    # TelnyxController routes
    path('searchForBuyNumber', telnyx_views.searchForBuyNumber, name='searchForBuyNumber'),
    path('sendsms', telnyx_views.sendSms, name='sendSms'),
    path('createSIP', telnyx_views.createSIP, name='createSIP'),
]
