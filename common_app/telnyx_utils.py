"""
Telnyx utility functions -- Python port of TelnyxSmsFunction.java
"""
import time
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def _telnyx_headers():
    api_key = getattr(settings, 'TELNYX_API_KEY', '')
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }


def _telnyx_base_url():
    return getattr(settings, 'TELNYX_BASE_URL', 'https://api.telnyx.com/v2/')


def send_sms_telnyx(mobile_no, telnyx_number, sms_type, sms_details, sms_count, opt_out_msg, sms_status_url, telnyx_base_url=None, telnyx_api_key=None):
    """
    Python port of TelnyxSmsFunction.sendSms
    Sends an SMS or MMS message via Telnyx.
    Returns dict with keys: msgError, msgErrorCode, msgId, msgStatus.
    """
    result = {"msgError": "", "msgErrorCode": "", "msgId": "", "msgStatus": ""}
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    if sms_type == "image":
        try:
            payload = {
                "from": telnyx_number,
                "to": mobile_no,
                "text": "",
                "type": "MMS",
                "media_urls": [sms_details],
                "webhook_url": sms_status_url,
            }
            response = requests.post(f"{base_url}messages", json=payload, headers=headers)
            data = response.json()
            if "data" in data:
                result["msgId"] = data["data"].get("id", "")
                to_list = data["data"].get("to", [])
                if to_list:
                    result["msgStatus"] = to_list[0].get("status", "")
            elif "errors" in data:
                result["msgError"] = data["errors"][0].get("detail", "")
                result["msgErrorCode"] = data["errors"][0].get("code", "")
            time.sleep(0.015)
        except Exception as e:
            logger.error(f"SendSms Error 1 : {e}")
    else:
        if sms_type != "onlytext" and sms_count == "last":
            if opt_out_msg:
                sms_details = sms_details + "\n" + opt_out_msg
        try:
            payload = {
                "from": telnyx_number,
                "to": mobile_no,
                "text": sms_details,
                "webhook_url": sms_status_url,
            }
            response = requests.post(f"{base_url}messages", json=payload, headers=headers)
            data = response.json()
            if "data" in data:
                result["msgId"] = data["data"].get("id", "")
                to_list = data["data"].get("to", [])
                if to_list:
                    result["msgStatus"] = to_list[0].get("status", "")
            elif "errors" in data:
                result["msgError"] = data["errors"][0].get("detail", "")
                result["msgErrorCode"] = data["errors"][0].get("code", "")
        except Exception as e:
            logger.error(f"SendSms Error 2 : {e}")

    # For image/last: send opt-out as a separate text
    if sms_count == "last" and sms_type == "image" and opt_out_msg:
        try:
            payload = {
                "from": telnyx_number,
                "to": mobile_no,
                "text": opt_out_msg,
                "webhook_url": sms_status_url,
            }
            response = requests.post(f"{base_url}messages", json=payload, headers=headers)
            data = response.json()
            if "data" in data:
                result["msgId"] = data["data"].get("id", "")
                to_list = data["data"].get("to", [])
                if to_list:
                    result["msgStatus"] = to_list[0].get("status", "")
        except Exception as e:
            logger.error(f"SendSms Error 3 : {e}")

    return result


def telnyx_sub_account(sms_reply_url, cli_sip_friendly_name, ph_phone_number, cli_sms_account_sid, telnyx_base_url=None, telnyx_api_key=None, cli_sip_connection_id=None, site_url_backend=None, telnyx_outbound_voice_profile_id=None):
    """
    Python port of TelnyxSmsFunction.telnyxSubAccount
    Creates or retrieves a Telnyx messaging profile (sub account), orders a number, and assigns it.
    """
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    outbound_profile_id = telnyx_outbound_voice_profile_id or getattr(settings, 'TELNYX_OUTBOUND_VOICE_PROFILE_ID', '')
    backend_url = site_url_backend or getattr(settings, 'SITE_URL_BACKEND', '')

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    result = {
        "error": "",
        "cliSmsAccountSid": "",
        "cliSipFriendlyName": cli_sip_friendly_name,
        "telnyxUserName": cli_sip_friendly_name,
        "telnyxPassword": cli_sip_friendly_name,
        "phPhoneNumber": "",
        "cliSipConnectionId": "",
    }

    telnyx_user_name = cli_sip_friendly_name
    telnyx_password = cli_sip_friendly_name

    # 1. Create or use existing messaging profile
    if cli_sms_account_sid:
        result["cliSmsAccountSid"] = cli_sms_account_sid
    else:
        try:
            payload = {
                "enabled": True,
                "name": cli_sip_friendly_name,
                "webhook_url": sms_reply_url,
                "whitelisted_destinations": ["US"],
            }
            resp = requests.post(f"{base_url}messaging_profiles", json=payload, headers=headers)
            data = resp.json()
            cli_sms_account_sid = data.get("data", {}).get("id", "")
            result["cliSmsAccountSid"] = cli_sms_account_sid
        except Exception as e:
            logger.error(f"TelnyxSubAccount Sub account error : {e}")
            result["error"] = "Oops !! there is some problem while creating account."

    # 2. Create or use existing SIP connection
    if cli_sip_connection_id:
        result["cliSipConnectionId"] = cli_sip_connection_id
    else:
        cli_sip_connection_id = create_sip(base_url, api_key, outbound_profile_id, telnyx_user_name, telnyx_password, backend_url)
        result["cliSipConnectionId"] = cli_sip_connection_id

    if not cli_sms_account_sid:
        result["error"] = "Oops !! there is some problem while creating account."
        return result

    # 3. Order the phone number
    try:
        payload = {"phone_numbers": [{"phone_number": ph_phone_number}]}
        requests.post(f"{base_url}number_orders", json=payload, headers=headers)
    except Exception as e:
        logger.error(f"TelnyxSubAccount Incoming phone number error 1 : {e}")
        result["error"] = "Oops !! there is some problem while assigning phone number."

    # 4. Find the phone_number SId
    ph_sid = ""
    try:
        resp = requests.get(f"{base_url}phone_numbers", headers=headers)
        data = resp.json()
        for item in data.get("data", []):
            if item.get("phone_number") == ph_phone_number:
                ph_sid = item.get("id", "")
                break
    except Exception as e:
        logger.error(f"TelnyxSubAccount Get SubAccountPhoneSId error 2 : {e}")

    if ph_sid:
        result["phPhoneNumber"] = ph_phone_number
        result["phSid"] = ph_sid
        try:
            time.sleep(3)
            assign_to_number(cli_sms_account_sid, ph_sid, base_url, api_key, cli_sip_connection_id)
        except Exception as e:
            logger.error(f"TelnyxSubAccount Assign number error 3 : {e}")
            result["error"] = "Oops !! there is some problem while assigning phone number."
    else:
        result["error"] = "Oops !! there is some problem while assigning phone number."

    return result

def assign_to_number(cli_sms_account_sid, ph_sid, telnyx_base_url=None, telnyx_api_key=None, cli_sip_connection_id=None):
    """
    Python port of TelnyxSmsFunction.assignToNumber
    """
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    try:
        # Assign messaging profile
        requests.patch(
            f"{base_url}phone_numbers/{ph_sid}/messaging",
            json={"messaging_profile_id": cli_sms_account_sid},
            headers=headers
        )
        # Assign SIP connection
        if cli_sip_connection_id:
            requests.patch(
                f"{base_url}phone_numbers/{ph_sid}",
                json={"connection_id": cli_sip_connection_id},
                headers=headers
            )
    except Exception as e:
        logger.error(f"AssignToNumber Assign number error : {e}")


def delete_telnyx_number(ph_sid, telnyx_base_url=None, telnyx_api_key=None):
    """
    Python port of TelnyxSmsFunction.deleteTelnyxNumber
    Returns 1 on success.
    """
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    try:
        resp = requests.delete(f"{base_url}phone_numbers/{ph_sid}", headers=headers)
        if resp.status_code == 200:
            return 1
        return 0
    except Exception as e:
        logger.error(f"Delete Telnyx Number Error : {e}")
        return 0

def change_telnyx_number(cli_sip_friendly_name, ph_phone_number, cli_sms_account_sid, ph_sid, telnyx_base_url=None, telnyx_api_key=None, cli_sip_connection_id=None):
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    result = {
        "error": "",
        "cliSipFriendlyName": cli_sip_friendly_name,
        "cliSmsAccountSid": cli_sms_account_sid,
        "phSid": ph_sid,
    }

    try:
        delete_telnyx_number(ph_sid, base_url, api_key)
    except Exception as e:
        logger.error(f"Delete telnyx number Error : {e}")

    if cli_sms_account_sid:
        # Order the new phone number
        try:
            payload = {"phone_numbers": [{"phone_number": ph_phone_number}]}
            requests.post(f"{base_url}number_orders", json=payload, headers=headers)
        except Exception as e:
            logger.error(f"Incoming phone number error : {e}")
            result["error"] = "Oops !! there is some problem while assigning phone number."

        # Find the new phone_number SId
        new_sub_account_phone_s_id = ""
        try:
            resp = requests.get(f"{base_url}phone_numbers", headers=headers)
            data = resp.json()
            for item in data.get("data", []):
                if item.get("phone_number") == ph_phone_number:
                    new_sub_account_phone_s_id = item.get("id", "")
                    break
        except Exception as e:
            logger.error(f"Get SubAccountPhoneSId error : {e}")

        if new_sub_account_phone_s_id:
            result["phPhoneNumber"] = ph_phone_number
            result["phSid"] = new_sub_account_phone_s_id
            try:
                time.sleep(3)
                assign_to_number(cli_sms_account_sid, new_sub_account_phone_s_id, base_url, api_key, cli_sip_connection_id)
            except Exception as e:
                logger.error(f"Assign number error : {e}")
                result["error"] = "Oops !! there is some problem while assigning phone number."
        else:
            result["error"] = "Oops !! there is some problem while assigning phone number."

    return result

def check_assign_to_number(cli_sms_account_sid, ph_sid, telnyx_base_url=None, telnyx_api_key=None, cli_sip_connection_id=None):
    """
    Python port of TelnyxSmsFunction.checkAssignToNumber
    Returns "Yes" if the number is provisioned, "No" otherwise.
    """
    number_assign = "No"
    if not ph_sid:
        return number_assign
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    try:
        resp = requests.get(f"{base_url}phone_numbers/{ph_sid}", headers=headers)
        data = resp.json()
        if "data" in data:
            mp_id = str(data["data"].get("messaging_profile_id", ""))
            if len(mp_id) < 5:
                assign_to_number(cli_sms_account_sid, ph_sid, base_url, api_key, cli_sip_connection_id)
                number_assign = "No"
            else:
                number_assign = "Yes"
    except Exception as e:
        logger.error(f"Check Assign To Number Error : {e}")
    return number_assign


def create_sip(telnyx_base_url=None, telnyx_api_key=None, telnyx_outbound_voice_profile_id=None, telnyx_user_name="", telnyx_password="", site_url_backend=""):
    """
    Python port of TelnyxSmsFunction.createSIP
    """
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    outbound_profile_id = telnyx_outbound_voice_profile_id or getattr(settings, 'TELNYX_OUTBOUND_VOICE_PROFILE_ID', '')
    backend_url = site_url_backend or getattr(settings, 'SITE_URL_BACKEND', '')
    # Remove blanks
    un = (telnyx_user_name or "").replace(" ", "")
    pw = (telnyx_password or "").replace(" ", "")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "active": True,
        "user_name": un,
        "password": pw,
        "connection_name": un,
        "webhook_event_url": f"{backend_url}calling/callingReply",
        "sip_uri_calling_preference": "unrestricted",
        "inbound": {
            "dnis_number_format": "sip_username",
            "codecs": ["G722", "G711U", "G711A", "G729", "OPUS", "H.264", "VP8", "AMR-WB"],
            "isup_headers_enabled": True
        },
        "outbound": {
            "outbound_voice_profile_id": outbound_profile_id
        }
    }
    try:
        resp = requests.post(f"{base_url}credential_connections", json=payload, headers=headers)
        data = resp.json()
        if "data" in data:
            return data["data"].get("id", "")
    except Exception as e:
        logger.error(f"CreateSIP Error : {e}")
    return ""


def telnyx_call_forwarding(ph_sid, forwarding_number, call_forwarding_enabled, telnyx_base_url=None, telnyx_api_key=None):
    """
    Python port of TelnyxSmsFunction.callForwarding
    """
    base_url = telnyx_base_url or _telnyx_base_url()
    api_key = telnyx_api_key or getattr(settings, 'TELNYX_API_KEY', '')
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "call_forwarding": {
            "call_forwarding_enabled": call_forwarding_enabled,
            "forwards_to": forwarding_number,
            "forwarding_type": "on-failure"
        }
    }
    try:
        resp = requests.patch(f"{base_url}phone_numbers/{ph_sid}/voice", json=payload, headers=headers)
        if resp.status_code in [200, 201, 202, 204]:
            json_response = resp.json()
            if 'data' in json_response and 'id' in json_response['data']:
                return json_response['data']['id']
    except Exception as e:
        logger.error(f"CallForwarding Error : {e}")
    return ""


def get_token(cp_id, telnyx_api_key, telnyx_connection_id, telnyx_base_url):
    """
    Python port of TelnyxCallingFunction.getToken
    """
    result = {"error": "", "callingToken": ""}
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {telnyx_api_key}"
        }
        payload = {"connection_id": telnyx_connection_id}
        response = requests.post(f"{telnyx_base_url}telephony_credentials", json=payload, headers=headers)
        data = response.json()
        if "data" in data:
            cred_id = data["data"].get("id")
            token_response = requests.post(f"{telnyx_base_url}telephony_credentials/{cred_id}/token", headers=headers)
            result["callingToken"] = token_response.text
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Telnyx GetToken Error : {e}")
    return result

def check_active_telnyx_number(phone_sid):
    # import requests as req
    try:
        base_url = getattr(settings, 'TELNYX_BASE_URL', 'https://api.telnyx.com/v2/')
        api_key = getattr(settings, 'TELNYX_API_KEY', '')
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        resp = requests.get(f"{base_url}phone_numbers/{phone_sid}", headers=headers)
        if resp.status_code == 200:
            return "Active"
        return "Inactive"
    except Exception:
        return "Inactive"
