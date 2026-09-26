from django.http import JsonResponse
from django.db import connections
from django.db.utils import OperationalError
from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.models import Language, SecurityQuestion, Country, CountryToState, CountrySetting
from common_app.serializers import LanguageDto, SecurityQuestionDto, CountryDto, CountryToStateDto
from common_app.utils import api_response, get_final_tenant_id
import logging
from common_app.services import CommonServices, MailRequestDTO
import traceback
from django.conf import settings

logger = logging.getLogger(__name__)

@api_view(['GET'])
def health_check(request):
    health_status = {"status": "healthy", "database": "up"}

    # Optional: Verify Database Connection
    try:
        db_conn = connections['default']
        db_conn.cursor()
    except OperationalError:
        health_status["status"] = "unhealthy"
        health_status["database"] = "down"
        return JsonResponse(health_status, status=503)

    return JsonResponse(health_status, status=200)

@api_view(['GET'])
def lookupdata(request):
    language_dto = LanguageDto(Language.objects.all(), many=True).data
    security_question_dto = SecurityQuestionDto(SecurityQuestion.objects.all(), many=True).data
    country_dto = CountryDto(Country.objects.all(), many=True).data
    state_dto = CountryToStateDto(CountryToState.objects.all(), many=True).data

    res_body = {
        "language": language_dto,
        "securityQuestion": security_question_dto,
        "country": country_dto,
        "state": state_dto
    }
    return api_response(200, "Fetch Data Successfully.", res_body)

@api_view(['POST'])
def sendingEmail(request: Request):
    """
    FIX #1: Implement real email sending
    Mirrors Java's: CommonController.sendEmail()
    """
    try:
        # Extract request data
        mail_request_data = request.data
        if not mail_request_data.get('to') or not mail_request_data.get('subject'):
            return api_response(400, "Missing required fields (to, subject)", {})

        # Create mail request object
        mail_request = MailRequestDTO(
            to=mail_request_data.get('to'),
            subject=mail_request_data.get('subject'),
            template_name=mail_request_data.get('template_name', 'default.ftl')
        )

        # Add site URL to model
        model = {
            "url": getattr(settings, 'SITE_URL', 'https://salesandmarketing.ai')
        }

        # Send email via service
        response = CommonServices.sendEmail(mail_request, model)

        return api_response(
            200 if response.status else 500,
            response.message,
            {"status": response.status}
        )
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return api_response(500, f"Error sending email: {str(e)}", {})

@api_view(['GET'])
def displayLanguage(request):
    languages = Language.objects.all()
    res_body = {
        "language": {lg.lg_name: lg.lg_long_name for lg in languages if lg.lg_name and lg.lg_long_name}
    }
    return api_response(200, "Fetch Language Successfully.", res_body)

@api_view(['GET'])
def language(request):
    language_dto = LanguageDto(Language.objects.all(), many=True).data
    res_body = {"language": language_dto}
    return api_response(200, "Fetch Language Successfully.", res_body)

@api_view(['GET'])
def country(request):
    country_dto = CountryDto(Country.objects.all(), many=True).data
    res_body = {"country": country_dto}
    return api_response(200, "Fetch Country Successfully.", res_body)

@api_view(['GET'])
def countryToState(request, countryId):
    state_dto = CountryToStateDto(CountryToState.objects.filter(fk_country_id=countryId), many=True).data
    res_body = {"state": state_dto}
    return api_response(200, "Fetch State Successfully.", res_body)

@api_view(['GET'])
def securityQuestion(request):
    security_question_dto = SecurityQuestionDto(SecurityQuestion.objects.all(), many=True).data
    res_body = {"securityQuestion": security_question_dto}
    return api_response(200, "Fetch Security Question Successfully.", res_body)

@api_view(['GET'])
def getRemoteAddress(request: Request):
    remote_address = request.META.get('REMOTE_ADDR')
    res_body = {"remoteAddress": remote_address}
    return api_response(200, "Fetch Remote Address Successfully.", res_body)

@api_view(['GET'])
def countryToStateName(request, countryName):
    """
    FIX #7: Use service method for country lookup
    Mirrors Java's: CommonController.countryToStateName()
    """
    try:
        # Use service method to get country ID
        country_id = CommonServices.get_country_id(countryName)

        if country_id > 0:
            state_dto = CountryToStateDto(
                CountryToState.objects.filter(fk_country_id=country_id),
                many=True
            ).data
            res_body = {"state": state_dto}
            return api_response(200, "Fetch State Successfully.", res_body)

        return api_response(500, "Invalid Country Name.", {})
    except Exception as e:
        logger.error(f"Error in countryToStateName: {e}")
        return api_response(500, "Error fetching states", {})

@api_view(['GET'])
def getCountryName(request, countryId):
    """
    FIX #5: Use service method instead of direct ORM query
    Mirrors Java's: CommonController.getCountryName()
    """
    try:
        # Use service method instead of direct ORM
        country_name = CommonServices.get_country_name(countryId)
        res_body = {"countryName": country_name}
        return api_response(200, "Fetch Country Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetCountryName Error: {e}")
        res_body = {"countryName": ""}
        return api_response(200, "Fetch Country Successfully.", res_body)

@api_view(['GET'])
def getCountryId(request, countryName):
    """
    FIX #6: Use service method instead of direct ORM query
    Mirrors Java's: CommonController.getCountryId()
    """
    try:
        # Use service method
        country_id = CommonServices.get_country_id(countryName)
        res_body = {"countryId": country_id}
        return api_response(200, "Fetch Country Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetCountryId Error: {e}")
        res_body = {"countryId": 0}
        return api_response(200, "Fetch Country Successfully.", res_body)

@api_view(['GET'])
def getGroupFirstRecords(request, groupId):
    """
    FIX #2: Add member ID extraction and service call
    Mirrors Java's: CommonController.getGroupFirstRecords()
    """
    try:
        # Extract member ID from JWT token in request
        member_id = get_final_tenant_id(request=request)

        if not member_id or member_id == 0:
            return api_response(401, "Authentication required", {})

        # Call service method to get group first records
        result = CommonServices.find_group_first_records(member_id, groupId)

        if result:
            return api_response(200, "Fetched First Record Successfully.", result)
        else:
            return api_response(404, "No records found", {})
    except Exception as e:
        logger.error(f"Error in getGroupFirstRecords: {e}")
        return api_response(500, "Error fetching group records", {})

@api_view(['GET'])
def checkAuthorized(request):
    try:
        member_id = get_final_tenant_id(request=request)

        if not member_id or member_id == 0:
            return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", "",sendErrorAs200=True)

        is_authorized = CommonServices.check_authorized(member_id)

        if is_authorized:
            return api_response(200, "Successfully.", "")
        else:
            return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", "",sendErrorAs200=True)
    except Exception as e:
        logger.error(f"checkAuthorized error: {e}")
        return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", "",sendErrorAs200=True)

@api_view(['GET'])
def validatePhoneFormat(request, countryId, phoneNumber):
    """
    FIX #8: Use service method instead of direct ORM query
    Mirrors Java's: CommonController.validatePhoneFormat()
    """
    try:
        # Use service method
        is_valid = CommonServices.validate_phone_format(countryId, phoneNumber)

        if is_valid:
            return api_response(200, "Successfully.", "")
        else:
            return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", "")
    except Exception as e:
        logger.error(f"validatePhoneFormat error: {e}")
        return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", "")

@api_view(['POST'])
def unsubscribe(request: Request):
    """
    Mirrors Java's: CommonController.unsubscribe()
    """
    try:
        unsubscribe_dto = request.data
        res_body = CommonServices.unsubscribe(unsubscribe_dto)

        if res_body.get("error") == "":
            return api_response(200, str(res_body.get("msg", "")), res_body)
        else:
            return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", "")
    except Exception as e:
        logger.error(f"Unsubscribe Error : {e}")
        return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", "")

@api_view(['POST'])
def smsReplyUrl(request: Request):
    try:
        CommonServices.sms_reply_url(request.data)
        return api_response(200, "Sms Reply.", {})
    except Exception as e:
        logger.error(f"SmsReplyUrl Error: {e}")
        return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", {})

@api_view(['GET'])
def getPriceList(request):
    try:
        country_setting = CountrySetting.objects.first()
        res_body = {
            "cntyCampaignPerPrice": country_setting.cnty_campaign_per_price if country_setting else 0.0,
            "cntySMSPerPrice": country_setting.cnty_sms_per_price if country_setting else 0.0,
            "cntySurveyPerPrice": country_setting.cnty_survey_per_price if country_setting else 0.0,
            "cntyIndividualPrice": country_setting.cnty_individual_price if country_setting else 0.0
        }
        return api_response(200, "Fetch Price Successfully.", res_body)
    except Exception:
        return api_response(500, "Whoops! An Expected Error Has Occurred", {})

@api_view(['POST'])
def zeroBounceReturnUrl(request: Request):
    """
    FIX #4: Add service call and error notification
    Mirrors Java's: CommonController.zeroBounceReturnUrl()
    """
    try:
        # Call service to process ZeroBounce response
        CommonServices.zero_bounce_return_url(request.data)

        return api_response(200, "ZeroBounceReturnUrl Reply.", {})

    except Exception as e:
        logger.error(f"ZeroBounceReturnUrl Error: {e}")

        # Send error notification email
        try:
            member_id = get_final_tenant_id(request=request)
            error_msg_dto = {
                'member_id': member_id,
                'error_type': 'ZeroBounceReturnUrl',
                'message': str(e),
                'stack_trace': traceback.format_exc()
            }
            CommonServices.send_whoops_error(error_msg_dto)
        except Exception as inner_e:
            logger.error(f"Failed to send error notification: {inner_e}")

        return api_response(500, "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It.", {})
