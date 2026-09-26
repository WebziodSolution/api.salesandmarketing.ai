import logging
import requests
from datetime import datetime
import pytz
from django.conf import settings
from common_app.models import (
    CampaignSendSms, SmsConversations
)

logger = logging.getLogger(__name__)

class TelnyxSmsService:
    """Telnyx SMS sending and management service"""

    def __init__(self):
        self.api_key = getattr(settings, 'TELNYX_API_KEY', '')
        self.base_url = getattr(settings, 'TELNYX_BASE_URL', 'https://api.telnyx.com/v2')
        self.outbound_profile_id = getattr(settings, 'TELNYX_OUTBOUND_VOICE_PROFILE_ID', '')
        self.webhook_url = getattr(settings, 'TELNYX_SMS_STATUS_WEBHOOK_URL', '')

    def send_sms(self, from_number, to_number, message_body, sms_id=None, email_id=None):
        """
        Send single SMS message via Telnyx

        Args:
            from_number: Sender phone number (Telnyx DID)
            to_number: Recipient phone number
            message_body: SMS message text
            sms_id: Campaign SMS ID (optional)
            email_id: Recipient email/contact ID (optional)

        Returns:
            Dict with send result: {sid, status, error}
        """
        try:
            if not self.api_key:
                logger.error("Telnyx API key not configured")
                return {"status": "error", "error": "API key not configured", "sid": None}

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "to": to_number,
                "from": from_number,
                "text": message_body,
                "webhook_url": self.webhook_url
            }

            response = requests.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                result = response.json()
                message_data = result.get('data', {})
                sid = message_data.get('id')

                # Record in database
                if sms_id and email_id:
                    try:
                        CampaignSendSms.objects.create(
                            smsId=sms_id,
                            emailId=email_id,
                            isSend='Y',
                            sid=sid,
                            smsStatus='sent',
                            fromContact=from_number,
                            toContact=to_number,
                            smsDetail=message_body,
                            smsSendDate=datetime.now(pytz.UTC)
                        )
                    except Exception as e:
                        logger.warning(f"Error recording SMS: {e}")

                return {
                    "status": "success",
                    "sid": sid,
                    "error": None
                }
            else:
                error_msg = response.text
                logger.error(f"Telnyx API error: {response.status_code} - {error_msg}")
                return {
                    "status": "error",
                    "error": f"Telnyx API error: {response.status_code}",
                    "sid": None
                }
        except requests.Timeout:
            logger.error("Telnyx API request timeout")
            return {"status": "error", "error": "Request timeout", "sid": None}
        except Exception as e:
            logger.error(f"Error sending SMS via Telnyx: {e}")
            return {"status": "error", "error": str(e), "sid": None}

    def purchase_number(self, country_code="+1", area_code=None):
        """
        Purchase new SMS phone number from Telnyx

        Args:
            country_code: Country code (default +1 for US)
            area_code: Area code (optional)

        Returns:
            Dict with phone number and SID
        """
        try:
            if not self.api_key:
                logger.error("Telnyx API key not configured")
                return {"status": "error", "error": "API key not configured"}

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "country_code": country_code,
                "messaging_profile_id": self.outbound_profile_id
            }

            if area_code:
                payload["area_code"] = area_code

            response = requests.post(
                f"{self.base_url}/available_phone_numbers",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                result = response.json()
                number_data = result.get('data', {})

                return {
                    "status": "success",
                    "phone_number": number_data.get('phone_number'),
                    "phone_sid": number_data.get('id'),
                    "error": None
                }
            else:
                logger.error(f"Telnyx number purchase error: {response.status_code}")
                return {
                    "status": "error",
                    "error": f"Failed to purchase number: {response.status_code}"
                }
        except Exception as e:
            logger.error(f"Error purchasing phone number: {e}")
            return {"status": "error", "error": str(e)}

    def release_number(self, phone_number):
        """
        Release (delete) a phone number

        Args:
            phone_number: Phone number to release

        Returns:
            Bool indicating success
        """
        try:
            if not self.api_key:
                logger.error("Telnyx API key not configured")
                return False

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            response = requests.delete(
                f"{self.base_url}/phone_numbers/{phone_number}",
                headers=headers,
                timeout=10
            )

            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Error releasing phone number: {e}")
            return False

    def process_delivery_webhook(self, webhook_data):
        """
        Process SMS delivery status webhook from Telnyx

        Args:
            webhook_data: Webhook payload from Telnyx

        Returns:
            Bool indicating success
        """
        try:
            # Extract delivery status from webhook
            message_id = webhook_data.get('data', {}).get('id')
            status = webhook_data.get('data', {}).get('dlr', {}).get('status')

            if message_id and status:
                # Update SMS record
                try:
                    sms = CampaignSendSms.objects.get(sid=message_id)
                    sms.smsStatus = status  # delivered, failed, undelivered, etc.
                    sms.save()
                    logger.info(f"Updated SMS {message_id} status to {status}")
                except CampaignSendSms.DoesNotExist:
                    logger.warning(f"SMS with SID {message_id} not found")

            return True
        except Exception as e:
            logger.error(f"Error processing delivery webhook: {e}")
            return False

    def process_inbound_sms_webhook(self, webhook_data):
        """
        Process inbound SMS (reply) webhook from Telnyx

        Args:
            webhook_data: Webhook payload from Telnyx

        Returns:
            Bool indicating success
        """
        try:
            # Extract inbound SMS data
            from_number = webhook_data.get('data', {}).get('from', {}).get('phone_number')
            to_number = webhook_data.get('data', {}).get('to', {}).get('phone_number')
            message_body = webhook_data.get('data', {}).get('text')
            received_date = webhook_data.get('data', {}).get('received_at')

            # Store inbound SMS
            if from_number and to_number and message_body:
                try:
                    SmsConversations.objects.create(
                        contactNumber=from_number,
                        fromNumber=to_number,
                        toNumber=from_number,
                        messageContent=message_body,
                        messageType='inbound',
                        status='active',
                        receivedDate=received_date or datetime.now(pytz.UTC)
                    )
                    logger.info(f"Recorded inbound SMS from {from_number}")
                except Exception as e:
                    logger.warning(f"Error recording inbound SMS: {e}")

            return True
        except Exception as e:
            logger.error(f"Error processing inbound SMS webhook: {e}")
            return False

    def batch_send_sms(self, from_number, recipients_list, message_body, sms_id=None):
        """
        Send SMS to multiple recipients

        Args:
            from_number: Sender number
            recipients_list: List of {emailId, toNumber} dicts
            message_body: SMS message text
            sms_id: Campaign SMS ID

        Returns:
            Dict with overall status and per-recipient results
        """
        results = dict()
        results["total"] = len(recipients_list)
        results["successful"] = 0
        results["failed"] = 0
        results["recipients"] = []

        for recipient in recipients_list:
            email_id = recipient.get('emailId')
            to_number = recipient.get('toNumber')

            result = self.send_sms(from_number, to_number, message_body, sms_id, email_id)

            recipient_result = {
                "emailId": email_id,
                "toNumber": to_number,
                "status": result.get("status"),
                "sid": result.get("sid")
            }

            results["recipients"].append(recipient_result)

            if result.get("status") == "success":
                results["successful"] += 1
            else:
                results["failed"] += 1

        return results


class TelnyxSubAccountService:
    """Manage sub-account resources in Telnyx"""

    def __init__(self):
        self.api_key = getattr(settings, 'TELNYX_API_KEY', '')
        self.base_url = getattr(settings, 'TELNYX_BASE_URL', 'https://api.telnyx.com/v2')

    def create_sub_account(self, account_name):
        """
        Create a sub-account in Telnyx

        Args:
            account_name: Name for the sub-account

        Returns:
            Dict with sub-account ID and details
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "name": account_name,
                "billing_group_id": getattr(settings, 'TELNYX_BILLING_GROUP_ID', '')
            }

            response = requests.post(
                f"{self.base_url}/sub_accounts",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                result = response.json()
                return {
                    "status": "success",
                    "sub_account_id": result.get('data', {}).get('id'),
                    "error": None
                }
            else:
                logger.error(f"Sub-account creation error: {response.status_code}")
                return {"status": "error", "error": f"Error: {response.status_code}"}
        except Exception as e:
            logger.error(f"Error creating sub-account: {e}")
            return {"status": "error", "error": str(e)}

    def get_sub_account_details(self, sub_account_id):
        """
        Get sub-account details

        Args:
            sub_account_id: Telnyx sub-account ID

        Returns:
            Dict with account details
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }

            response = requests.get(
                f"{self.base_url}/sub_accounts/{sub_account_id}",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                return {
                    "status": "success",
                    "data": response.json().get('data', {})
                }
            else:
                return {"status": "error", "error": f"Error: {response.status_code}"}
        except Exception as e:
            logger.error(f"Error getting sub-account details: {e}")
            return {"status": "error", "error": str(e)}
