from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response, country_setting_by_country_id_and_plan_id
from common_app.models import Plans, CountrySetting
from common_app.decrypt_string import DecryptString
import logging

logger = logging.getLogger(__name__)

def remove_decimal(value):
    if not value:
        return value
    splits = str(value).split('.')
    if len(splits) == 1:
        return str(value)
    if splits[1] == "00" or splits[1] == "00000":
        return splits[0]
    return str(value)

@api_view(['GET'])
def getPlanById(request: Request):
    res_body = {}
    try:
        countryId_raw = request.GET.get('countryId')
        planId_enc = request.GET.get('planId')
        
        if not planId_enc:
            return api_response(500, "Error Processing Request", res_body)
            
        try:
            # Java: DecryptString.set_enc_dec_user(planId, "display", "Y")
            planId_dec = DecryptString.set_enc_dec_user(planId_enc, "display", "Y")
            final_plan_id = int(planId_dec)
        except Exception:
            return api_response(500, "Error Processing Request", res_body)
            
        country_id = int(countryId_raw) if countryId_raw else 100

        try:
            plan = Plans.objects.get(plan_id=final_plan_id, plan_active='Y')
        except Plans.DoesNotExist:
            return api_response(500, "Error Processing Request", res_body)

        plan_dto = {
            "planId": DecryptString.set_enc_dec_user(str(plan.plan_id), "", "Y"),
            "planName": plan.plan_name,
            "planActive": plan.plan_active,
            "countrySetting": None
        }

        try:
            country_setting = country_setting_by_country_id_and_plan_id(country_id, final_plan_id)

            if country_setting:
                cs_dto = {
                    "id": country_setting.id,
                    "cntyId": country_setting.cnty_id,
                    "cntyISO2": country_setting.cnty_iso2,
                    "cntyName": country_setting.cnty_name,
                    "cntyPriceSymbol": country_setting.cnty_price_symbol,
                    "cntyPlanPrice": remove_decimal(f"{country_setting.cnty_plan_price:.2f}"),
                    "cntyAssessmentPrice": remove_decimal(f"{country_setting.cnty_assessment_price:.2f}"),
                    "cntySurveyPrice": remove_decimal(f"{country_setting.cnty_survey_price:.2f}"),
                    "cntyIndividualPrice": remove_decimal(f"{country_setting.cnty_individual_price:.2f}"),
                    "cntySocialMediaPrice": remove_decimal(f"{country_setting.cnty_social_media_price:.2f}"),
                    "cntyCampaignPerPrice": remove_decimal(f"{country_setting.cnty_campaign_per_price:.2f}"),
                    "cntySurveyPerPrice": remove_decimal(f"{country_setting.cnty_survey_per_price:.2f}"),
                    "cntyAssessmentPerPrice": remove_decimal(f"{country_setting.cnty_assessment_per_price:.2f}"),
                    "cntyMMSPerPrice": remove_decimal(f"{country_setting.cnty_mms_per_price:.2f}"),
                    "cntySMSPerPrice": remove_decimal(f"{country_setting.cnty_sms_per_price:.2f}"),
                    "cntySMSNumberPerPrice": remove_decimal(f"{country_setting.cnty_sms_number_per_price:.2f}"),
                    "cntyFirstInvFreeAmt": remove_decimal(f"{country_setting.cnty_first_inv_free_amt:.2f}"),
                    "cntyInvLessAmtNotCharge": remove_decimal(f"{country_setting.cnty_inv_less_amt_not_charge:.2f}"),
                    "cntyTranslateCharCharge": remove_decimal(f"{country_setting.cnty_translate_char_charge:.5f}"),
                    "cntySMSConversationsPerPrice": remove_decimal(f"{country_setting.cnty_sms_conversations_per_price:.2f}"),
                    "cntyCallPerMinPrice": remove_decimal(f"{country_setting.cnty_call_per_min_price:.2f}"),
                    "cntyContactsIncluded": country_setting.cnty_contacts_included,
                    "cntyMaxNumberOfEmail": country_setting.cnty_max_number_of_email,
                    "cntyPlanId": country_setting.cnty_plan_id,
                    "cntySupport": country_setting.cnty_support,
                    "cntyMultiUser": country_setting.cnty_multi_user,
                    "cntyAutomation": country_setting.cnty_automation,
                    "cntyWhiteListing": country_setting.cnty_white_listing,
                    "cntyCalendar": country_setting.cnty_calendar,
                    "cntyZoomConferences": country_setting.cnty_zoom_conferences,
                    "cntySocialMedia": country_setting.cnty_social_media,
                    "cntySmsInbox": country_setting.cnty_sms_inbox,
                    "cntyAbTesting": country_setting.cnty_ab_testing,
                    "cntyPlanPopular": country_setting.cnty_plan_popular,
                    "cntyFormResponse": remove_decimal(f"{country_setting.cnty_form_response:.2f}"),
                    "cntyAdditionalContacts": str(country_setting.cnty_additional_contacts),
                    "cntyAdditionalContactsPrice": remove_decimal(f"{country_setting.cnty_additional_contacts_price:.2f}"),
                    "cnty10DLCPrice": remove_decimal(f"{country_setting.cnty_10dlc_price:.2f}"),
                    "cnty10DLCCampaignTypeCharge": remove_decimal(f"{country_setting.cnty_10dlc_campaign_type_charge:.2f}" if country_setting.cnty_10dlc_campaign_type_charge else "0.00"),
                    "cnty10DLCOtherCharge": remove_decimal(f"{country_setting.cnty_10dlc_other_charge:.2f}" if country_setting.cnty_10dlc_other_charge else "0.00"),
                    "cntyWarmupPrice": remove_decimal(f"{country_setting.cnty_warmup_price:.2f}"),
                    "ctnyContactPerPrice": remove_decimal(f"{country_setting.ctny_contact_per_price:.2f}")
                }
                plan_dto["countrySetting"] = cs_dto
        except Exception:
            pass

        res_body["plan"] = plan_dto
        return api_response(200, "Plan Fetched Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetPlanById Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

@api_view(['GET'])
def getPlanListById(request: Request):
    res_body = {}
    try:
        country_id_raw = request.GET.get('countryId')
        private_plan_id_raw = request.GET.get('planId')
        
        country_id = int(country_id_raw) if country_id_raw else 0
        private_plan_id = int(private_plan_id_raw) if private_plan_id_raw else 0

        data = {
            "planId": [], "planName": [], "planPrice": [], "cntyId": [], "cntyISO2": [], "cntyName": [],
            "cntyPriceSymbol": [], "cntyAssessmentPrice": [], "cntySurveyPrice": [], "cntyIndividualPrice": [],
            "cntySocialMediaPrice": [], "cntyCampaignPerPrice": [], "cntySurveyPerPrice": [],
            "cntyAssessmentPerPrice": [], "cntyMMSPerPrice": [], "cntySMSPerPrice": [], "cntySMSNumberPerPrice": [],
            "cntyFirstInvFreeAmt": [], "cntyInvLessAmtNotCharge": [], "cntyTranslateCharCharge": [],
            "cntySMSConversationsPerPrice": [], "cntyCallPerMinPrice": [], "cntyContactsIncluded": [],
            "cntyMaxNumberOfEmail": [], "cntySupport": [], "cntyMultiUser": [], "cntyAutomation": [],
            "cntyWhiteListing": [], "cntyCalendar": [], "cntyZoomConferences": [], "cntySocialMedia": [],
            "cntySmsInbox": [], "cntyAbTesting": [], "cntyPlanPopular": [], "cntyFormResponse": [],
            "cntyAdditionalContacts": [], "cntyAdditionalContactsPrice": [], "cnty10DLCPrice": [],
            "cntyWarmupPrice": [], "ctnyContactPerPrice": []
        }

        try:
            if private_plan_id > 0:
                country_settings = CountrySetting.objects.filter(cnty_plan_id=private_plan_id)
            else:
                country_settings = CountrySetting.objects.filter(cnty_id=country_id)

            for cs in country_settings:
                if private_plan_id > 0:
                    plan = Plans.objects.filter(plan_id=cs.cnty_plan_id, plan_active='Y').first()
                else:
                    plan = Plans.objects.filter(plan_id=cs.cnty_plan_id, plan_active='Y', plan_visibility='Public').first()

                if plan:
                    data["planId"].append(DecryptString.set_enc_dec_user(str(plan.plan_id), "", "Y"))
                    data["planName"].append(plan.plan_name if plan.plan_name is not None else "null")
                    data["planPrice"].append(remove_decimal(f"{cs.cnty_plan_price:.2f}") if cs.cnty_plan_price is not None else "0")
                    data["cntyId"].append(cs.cnty_id)
                    data["cntyISO2"].append(cs.cnty_iso2 if cs.cnty_iso2 is not None else "null")
                    data["cntyName"].append(cs.cnty_name if cs.cnty_name is not None else "null")
                    data["cntyPriceSymbol"].append(cs.cnty_price_symbol if cs.cnty_price_symbol is not None else "null")
                    data["cntyAssessmentPrice"].append(remove_decimal(f"{cs.cnty_assessment_price:.2f}") if cs.cnty_assessment_price is not None else "0")
                    data["cntySurveyPrice"].append(remove_decimal(f"{cs.cnty_survey_price:.2f}") if cs.cnty_survey_price is not None else "0")
                    data["cntyIndividualPrice"].append(remove_decimal(f"{cs.cnty_individual_price:.2f}") if cs.cnty_individual_price is not None else "0")
                    data["cntySocialMediaPrice"].append(remove_decimal(f"{cs.cnty_social_media_price:.2f}") if cs.cnty_social_media_price is not None else "0")
                    data["cntyCampaignPerPrice"].append(remove_decimal(f"{cs.cnty_campaign_per_price:.2f}") if cs.cnty_campaign_per_price is not None else "0")
                    data["cntySurveyPerPrice"].append(remove_decimal(f"{cs.cnty_survey_per_price:.2f}") if cs.cnty_survey_per_price is not None else "0")
                    data["cntyAssessmentPerPrice"].append(remove_decimal(f"{cs.cnty_assessment_per_price:.2f}") if cs.cnty_assessment_per_price is not None else "0")
                    data["cntyMMSPerPrice"].append(remove_decimal(f"{cs.cnty_mms_per_price:.2f}") if cs.cnty_mms_per_price is not None else "0")
                    data["cntySMSPerPrice"].append(remove_decimal(f"{cs.cnty_sms_per_price:.2f}") if cs.cnty_sms_per_price is not None else "0")
                    data["cntySMSNumberPerPrice"].append(remove_decimal(f"{cs.cnty_sms_number_per_price:.2f}") if cs.cnty_sms_number_per_price is not None else "0")
                    data["cntyFirstInvFreeAmt"].append(remove_decimal(f"{cs.cnty_first_inv_free_amt:.2f}") if cs.cnty_first_inv_free_amt is not None else "0")
                    data["cntyInvLessAmtNotCharge"].append(remove_decimal(f"{cs.cnty_inv_less_amt_not_charge:.2f}") if cs.cnty_inv_less_amt_not_charge is not None else "0")
                    data["cntyTranslateCharCharge"].append(remove_decimal(f"{cs.cnty_translate_char_charge:.5f}") if cs.cnty_translate_char_charge is not None else "0")
                    data["cntySMSConversationsPerPrice"].append(remove_decimal(f"{cs.cnty_sms_conversations_per_price:.2f}") if cs.cnty_sms_conversations_per_price is not None else "0")
                    data["cntyCallPerMinPrice"].append(remove_decimal(f"{cs.cnty_call_per_min_price:.2f}") if cs.cnty_call_per_min_price is not None else "0")
                    data["cntyContactsIncluded"].append(str(cs.cnty_contacts_included) if cs.cnty_contacts_included is not None else "0")
                    data["cntyMaxNumberOfEmail"].append(str(cs.cnty_max_number_of_email) if cs.cnty_max_number_of_email is not None else "null")
                    data["cntySupport"].append(cs.cnty_support if cs.cnty_support is not None else "null")
                    data["cntyMultiUser"].append(cs.cnty_multi_user if cs.cnty_multi_user is not None else "null")
                    data["cntyAutomation"].append(cs.cnty_automation if cs.cnty_automation is not None else "null")
                    data["cntyWhiteListing"].append(cs.cnty_white_listing if cs.cnty_white_listing is not None else "null")
                    data["cntyCalendar"].append(cs.cnty_calendar if cs.cnty_calendar is not None else "null")
                    data["cntyZoomConferences"].append(cs.cnty_zoom_conferences if cs.cnty_zoom_conferences is not None else "null")
                    data["cntySocialMedia"].append(cs.cnty_social_media if cs.cnty_social_media is not None else "null")
                    data["cntySmsInbox"].append(cs.cnty_sms_inbox if cs.cnty_sms_inbox is not None else "null")
                    data["cntyAbTesting"].append(cs.cnty_ab_testing if cs.cnty_ab_testing is not None else "null")
                    data["cntyPlanPopular"].append(cs.cnty_plan_popular if cs.cnty_plan_popular is not None else "null")
                    data["cntyFormResponse"].append(remove_decimal(f"{cs.cnty_form_response:.2f}") if cs.cnty_form_response is not None else "0")
                    data["cntyAdditionalContacts"].append(str(cs.cnty_additional_contacts) if cs.cnty_additional_contacts is not None else "0")
                    data["cntyAdditionalContactsPrice"].append(remove_decimal(f"{cs.cnty_additional_contacts_price:.2f}") if cs.cnty_additional_contacts_price is not None else "0")
                    data["cnty10DLCPrice"].append(remove_decimal(f"{cs.cnty_10dlc_price:.2f}") if cs.cnty_10dlc_price is not None else "0")
                    data["cntyWarmupPrice"].append(remove_decimal(f"{cs.cnty_warmup_price:.2f}") if cs.cnty_warmup_price is not None else "0")
                    data["ctnyContactPerPrice"].append(remove_decimal(f"{cs.ctny_contact_per_price:.2f}") if cs.ctny_contact_per_price is not None else "0")

            res_body["data"] = data
            return api_response(200, "Plan List Fetched Successfully.", res_body)
        except Exception:
            return api_response(200, "Plan List Fetched Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetPlanListById Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

