from rest_framework.permissions import BasePermission
from common_app.utils import get_final_tenant_id, get_client_id_by_tenant_id
from profile_app.models import SupportApiPermission, SupportApi, WhiteListingUrls
from django.conf import settings

class WhitelistPermission(BasePermission):
    """
    Extracted from Java's JwtRequestFilter.java
    Requires JWT token and authentication unless the request_uri contains one of these whitelist paths.
    """
    WHITELISTED_PATHS = [
        "/contact/addInviteByUrlContact", "/group/getInviteByUrlData", "/domainEmail/saveDomainEmail",
        "/auth/resetPassword", "/auth/forgotPassword", "/auth/forgotPasswordVerify", "/auth/token",
        "/auth/changePlan", "/auth/cancelRegistration", "/auth/checkLogin", "/lookupdata", "/language",
        "/country", "/securityQuestion", "/countryToState/", "/usercontent/", "/sendingEmail", "/v3/api-docs",
        "/auth/registration", "/auth/checkRegistrationLink", "/auth/resendActivationEmail",
        "/auth/processActivation", "/auth/verifiedOtp", "/favicon.ico", "swagger-ui", "/swagger-ui/index.html",
        "/v2/api-docs", "/smsInbox/conversationsReplyUrl", "/calling/callingReply", "/googleDrive/googleSignIn",
        "/smsPolling/smsPollingReplyUrl", "/smsCampaign/smsCampaignReplyUrl", "/dropbox/dropboxSignIn",
        "/facebook/facebookLogin", "/onedrive/onedriveSignIn", "/linkedin/linkedinLogin", "/twitter/twitterLogin",
        "/customForm/getPreviewCustomFormData", "/customForm/saveCustomFormAnswers",
        "/googleCalendar/googleCalendarSignIn", "/outlookCalendar/outlookCalendarSignIn", "/auth/checkEmail/",
        "/auth/checkUsername", "/auth/verifyEmail", "/survey/saveSurveyAnswers", "/survey/getPreviewSurveyData",
        "/assessment/saveAssessmentAnswers", "/assessment/getPreviewAssessmentData", "/validatePhoneFormat/",
        "/calendar/getTimeZoneList", "/calendarAppointment/freeSlotList", "/member/getMemberDetails/",
        "/calendarAppointment/saveAppointment", "/calendarAppointmentEventType/getEventTypeAllList/",
        "/calendarAppointment/getAvailabilitySlotsList/", "/smsCampaign/smsStatusUrl", "/smsCampaign/smsStatusReplyUrl",
        "/emailCampaign/campaignLinkClick", "/emailCampaign/openEmail", "/auth/generateAuthKey/",
        "/shopify/shopifyLogin", "/zoom/zoomLogin", "/unsubscribe", "/mypages/getPreview",
        "/mypages/getFreeTemplateTags", "/mypages/getFreeTemplateList", "/smsReplyUrl", "/getPriceList",
        "/calendarAppointment/smsStatusUrlSendAppointmentLink", "/calendarAppointment/smsStatusUrlSendSmsCalendarAppointment",
        "/smsPolling/smsStatusUrl", "/smsCampaign/smsLinkClick", "/auth/checkActiveSubaccount",
        "/auth/activeSubaccount", "/plan/getPlanById", "/plan/getPlanListById", "/auth/sendOtpOnboarding",
        "/member/verifiedOtpOnboarding", "/contactImport/optOut", "/contactImport/optOutDetails",
        "/contactImport/optInDetails", "/contactImport/optIn", "/contactImport/smsStatusUrlSendSmsOptIn",
        "/contact/getContact/", "/member/grabWebsiteLinks", "/member/grabWebsiteImages",
        "/member/grabWebsiteColors", "/member/saveWebsiteColor", "/easDrive/importImageFromUrl",
        "/zeroBounceReturnUrl", "/calendar/smsStatusUrlSendSmsCalendarReminder", "/auth/sendOtpAuthenticationCode/",
        "/polling/grabImages", "/polling/grabColors", "/polling/grabLinks", "/emailCampaign/viewInBrowser",
        "/amply/amplyReply", "/authenticator/generate", "/authenticator/verify", "/contact/checkOptin",
        "/auth/onboarding/", "/health/" , "/easDrive/deleteFoldersAndFiles"
    ]

    def has_permission(self, request, view):
        request_uri = request.META.get('PATH_INFO', '')
        
        # Check against the java JwtRequestFilter exact logic using string contains
        for path in self.WHITELISTED_PATHS:
            if path in request_uri:
                return True
                
        # If not in whitelist, enforce normal REST auth using JWT user session object
        if request.user and request.user.is_authenticated:
            # If authenticated via SupportApiAuthentication (secretKey/authToken headers present)
            # Perform additional Support API permission checks as in Java logic
            if 'secretKey' in request.headers and 'authToken' in request.headers:
                member_id = get_final_tenant_id(request=request)
                
                # 1. Whitelisting URL Check (Origin/Referer)
                origin = request.headers.get('Origin')
                # Java: if envsys=api reqUrl=scheme://serverName else reqUrl=Origin
                if settings.ENVSYS == "api":
                    # request.get_host() includes server name and port
                    req_url = f"{request.scheme}://{request.get_host().split(':')[0]}"
                else:
                    req_url = origin or ""
                
                # Tool Check (Postman, etc.)
                user_agent = request.headers.get('User-Agent', '')
                if any(tool in user_agent for tool in ["PostmanRuntime", "Oracle API Gateway", "Zapier"]):
                    count = 1
                else:
                    count = WhiteListingUrls.objects.filter(memberId=get_client_id_by_tenant_id(member_id), url=req_url).count()
                
                if count == 0:
                    return False # Invalid Whitelisting URL
                    
                # 2. Support API Permission Check
                # Extract tempRequestUrl matching Java's split logic
                parts = request_uri.split('/') # Leading slash creates empty string at index 0
                if settings.ENVSYS == "api":
                    if len(parts) > 2:
                        temp_request_url = "/" + parts[1] + "/" + parts[2]
                    else:
                        temp_request_url = request_uri
                else:
                    if len(parts) > 3:
                        temp_request_url = "/" + parts[2] + "/" + parts[3]
                    else:
                        temp_request_url = request_uri
                
                permissions = SupportApiPermission.objects.filter(perMemberId=get_client_id_by_tenant_id(member_id))
                for perm in permissions:
                    if SupportApi.objects.filter(apiMdId=perm.perMdId, apiUrl=temp_request_url).exists():
                        return True
                
                return False # Not Permitted To Access This API
                
            return True
            
        return False

