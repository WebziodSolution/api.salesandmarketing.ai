"""
SMS Campaigns Database Queries
All queries are native Oracle SQL to match Java implementation exactly
"""
import logging
from django.db import connection

from common_app.utils import get_client_id_by_tenant_id

logger = logging.getLogger(__name__)

class SmsCampaignQueries:
    """All complex database queries for SMS campaigns"""

    @staticmethod
    def get_contact_list_for_campaign(group_id, tenant_id, cursor=None):
        """
        Get contact list (emailIds) for campaign
        Filters for opted-in contacts with valid phone numbers
        Java: final_save_sms_campaign logic

        Args:
            group_id: Target group ID
            tenant_id: Tenant ID
            cursor: Database cursor (optional, creates new if not provided)

        Returns:
            List of email IDs (contact IDs)
        """
        try:
            if cursor is None:
                cursor = connection.cursor()
            query = """
                SELECT UL_EMAIL_ID
                FROM USER_LIST
                WHERE UL_GROUP_ID = %s
                  AND UL_CLIENT_ID = %s
                  AND (UL_SMS_STATUS='Subscribed' or UL_SMS_STATUS is null)
                  AND UL_BAD_PHONE_NUMBER = 'N'
                  AND (UL_OPT_ID is null or UL_OPT_ID=0)
                  AND (UL_PHONE_NUMBER is not null)
                ORDER BY UL_FIRST_NAME
            """

            cursor.execute(query, [group_id, get_client_id_by_tenant_id(tenant_id)])
            results = cursor.fetchall()
            return [row[0] for row in results]
        except Exception as e:
            logger.error(f"Error getting contact list: {e}")
            return []

    @staticmethod
    def get_segment_contact_list(seg_id, cursor=None):
        """
        Get contact list from segment definition
        Java: GroupSegment query logic

        Args:
            seg_id: Segment ID
            cursor: Database cursor (optional)

        Returns:
            List of email IDs (contact IDs)
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            # First get the segment query
            query = """
                SELECT SEG_QUERY
                FROM SEGMENTS
                WHERE SEG_ID = %s
            """

            cursor.execute(query, [seg_id])
            result = cursor.fetchone()

            if not result:
                return []

            seg_query = result[0]

            # Replace SELECT * with SELECT tul.Email_Id
            seg_query = seg_query.replace("select *", "SELECT tul.Email_Id")
            seg_query = seg_query.replace("SELECT *", "SELECT tul.Email_Id")

            # Add phone number filter if not present
            if "phoneNumber" not in seg_query:
                seg_query = seg_query.replace(
                    "WHERE",
                    "WHERE ( tul.phoneNumber is not null and tul.phoneNumber!='' ) and "
                )

            cursor.execute(seg_query)
            results = cursor.fetchall()
            return [row[0] for row in results]
        except Exception as e:
            logger.error(f"Error getting segment contact list: {e}")
            return []

    @staticmethod
    def get_campaign_details_by_sms_id(sms_id, cursor=None):
        """
        Get all campaign details for SMS campaign, ordered by display order
        Java: CampaignsSmsDetailsRepository.getCampaignSmsDetailsAll()

        Args:
            sms_id: SMS campaign ID
            cursor: Database cursor (optional)

        Returns:
            List of CampaignSmsDetails objects with details
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                SELECT CSD_ID, CSD_CS_ID, CSD_DETAIL, CSD_TYPE, CSD_DISPLAY_ORDER
                FROM CAMPAIGN_SMS_DETAILS
                WHERE CSD_CS_ID = %s
                ORDER BY CSD_DISPLAY_ORDER ASC
            """

            cursor.execute(query, [sms_id])
            results = cursor.fetchall()

            details = []
            for row in results:
                sd_detail = row[2]
                if hasattr(sd_detail, 'read'):
                    sd_detail = sd_detail.read()
                
                details.append({
                    'sdId': row[0],
                    'smsId': row[1],
                    'sdDetail': sd_detail,
                    'sdType': row[3],
                    'sdDisplayOrder': row[4]
                })
            return details
        except Exception as e:
            logger.error(f"Error getting campaign details: {e}")
            return []

    @staticmethod
    def get_campaign_send_record(sms_id, cursor=None):
        """
        Get latest CampaignsSmsSend record for SMS campaign
        Java: CampaignsSmsSendRepository.findSmsId()

        Args:
            sms_id: SMS campaign ID
            cursor: Database cursor (optional)

        Returns:
            Dict with send record details or None
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                SELECT CSS_ID, CSS_SEND_ON_DATE
                FROM CAMPAIGN_SMS_SENT
                WHERE CSS_CS_ID = %s
                ORDER BY CSS_ID DESC
                FETCH FIRST 1 ROWS ONLY
            """

            cursor.execute(query, [sms_id])
            result = cursor.fetchone()

            if result:
                return {
                    'id': result[0],
                    'sendOnDate': result[1]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting campaign send record: {e}")
            return None

    @staticmethod
    def get_temp_send_records_count(sms_id, cursor=None):
        """
        Get count of temporary send records for SMS campaign
        Used to determine number of recipients

        Args:
            sms_id: SMS campaign ID
            cursor: Database cursor (optional)

        Returns:
            Count of records
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                SELECT COUNT(*)
                FROM CAMPAIGN_SMS_DRAFT
                WHERE CSD_CS_ID = %s AND CSD_IS_SEND = 'N'
            """

            cursor.execute(query, [sms_id])
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting temp send records count: {e}")
            return 0

    @staticmethod
    def update_campaign_schedule_date(sms_id, send_on_date, cursor=None):
        """
        Update campaign scheduled send date and time
        Java: CampaignsSmsRepository.updateCampaignSms()

        Args:
            sms_id: SMS campaign ID
            send_on_date: Date in "YYYY-MM-DD HH24:MI:SS" format
            cursor: Database cursor (optional)

        Returns:
            Number of rows updated
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                UPDATE CAMPAIGN_SMS
                SET CS_SEND_ON_DATE = TO_TIMESTAMP(%s, 'YYYY-MM-DD HH24:MI:SS'),
                    CS_SEND_ON_TIME = TO_DSINTERVAL('0 ' || TO_CHAR(TO_TIMESTAMP(%s, 'YYYY-MM-DD HH24:MI:SS'), 'HH24:MI:SS'))
                WHERE CS_ID = %s
            """

            cursor.execute(query, [send_on_date, send_on_date, sms_id])
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error updating campaign schedule: {e}")
            return 0

    @staticmethod
    def update_campaign_send_schedule_date(schedule_id, send_on_date, cursor=None):
        """
        Update campaign send record scheduled send date and time
        Java: CampaignsSmsSendRepository.updateCampaignsSmsSend()

        Args:
            schedule_id: CampaignsSmsSend ID
            send_on_date: Date in "YYYY-MM-DD HH24:MI:SS" format
            cursor: Database cursor (optional)

        Returns:
            Number of rows updated
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                UPDATE CAMPAIGN_SMS_SENT
                SET CSS_SEND_ON_DATE = TO_TIMESTAMP(%s, 'YYYY-MM-DD HH24:MI:SS'),
                    CSS_SEND_ON_TIME = TO_DSINTERVAL('0 ' || TO_CHAR(TO_TIMESTAMP(%s, 'YYYY-MM-DD HH24:MI:SS'), 'HH24:MI:SS'))
                WHERE CSS_ID = %s
            """

            cursor.execute(query, [send_on_date, send_on_date, schedule_id])
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error updating campaign send schedule: {e}")
            return 0

    @staticmethod
    def get_sent_sms_count(sms_id, cursor=None):
        """
        Get count of SMS messages sent for campaign
        Java: CampaignSendSmsRepository.totalCount()

        Args:
            sms_id: SMS campaign ID
            cursor: Database cursor (optional)

        Returns:
            Count of sent SMS
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                SELECT COUNT(*)
                FROM CAMPAIGN_SMS_QUEUED
                WHERE CSQ_CSS_ID = %s AND CSQ_IS_SEND = 'Y'
            """

            cursor.execute(query, [sms_id])
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting sent SMS count: {e}")
            return 0

    @staticmethod
    def get_delivered_sms_count(sms_id, cursor=None):
        """
        Get count of delivered SMS messages
        Java: CampaignSendSmsRepository status tracking

        Args:
            sms_id: SMS campaign ID
            cursor: Database cursor (optional)

        Returns:
            Count of delivered SMS
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                SELECT COUNT(*)
                FROM CAMPAIGN_SMS_QUEUED
                WHERE CSQ_CSS_ID = %s AND CSQ_SMS_STATUS = 'delivered'
            """

            cursor.execute(query, [sms_id])
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting delivered SMS count: {e}")
            return 0

    @staticmethod
    def get_failed_sms_count(sms_id, cursor=None):
        """
        Get count of failed SMS messages

        Args:
            sms_id: SMS campaign ID
            cursor: Database cursor (optional)

        Returns:
            Count of failed SMS
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                SELECT COUNT(*)
                FROM CAMPAIGN_SMS_QUEUED
                WHERE CSQ_CSS_ID = %s AND CSQ_SMS_STATUS IN ('failed', 'bounced', 'undelivered')
            """

            cursor.execute(query, [sms_id])
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting failed SMS count: {e}")
            return 0

    @staticmethod
    def get_sms_sent_list(sms_id, page_no=0, page_size=10, cursor=None):
        """
        Get paginated list of sent SMS for campaign
        Java: Report endpoint logic

        Args:
            sms_id: SMS campaign ID
            page_no: Page number (0-based)
            page_size: Records per page
            cursor: Database cursor (optional)

        Returns:
            List of sent SMS records
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            offset = page_no * page_size

            query = """
                SELECT
                    css.CSQ_ID, css.CSQ_CSS_ID, css.CSQ_CLIENT_ID, css.CSQ_EMAIL_ID,
                    css.CSQ_IS_SEND, css.CSQ_SID, css.CSQ_SMS_STATUS, css.CSQ_FROM_CONTACT,
                    css.CSQ_TO_CONTACT, css.CSQ_SMS_SEND_DATE, tul.UL_FIRST_NAME, tul.UL_LAST_NAME,
                    tul.UL_EMAIL
                FROM CAMPAIGN_SMS_QUEUED css
                LEFT JOIN USER_LIST tul ON tul.UL_EMAIL_ID = css.CSQ_EMAIL_ID
                WHERE css.CSQ_CSS_ID = %s
                ORDER BY css.CSQ_ID DESC
                OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """

            cursor.execute(query, [sms_id, offset, page_size])
            results = cursor.fetchall()

            sent_list = []
            for row in results:
                sent_list.append({
                    'id': row[0],
                    'smsId': row[1],
                    'memberId': row[2],
                    'emailId': row[3],
                    'isSend': row[4],
                    'sid': row[5],
                    'smsStatus': row[6],
                    'fromContact': row[7],
                    'toContact': row[8],
                    'smsSendDate': row[9],
                    'firstName': row[10],
                    'lastName': row[11],
                    'email': row[12]
                })
            return sent_list
        except Exception as e:
            logger.error(f"Error getting SMS sent list: {e}")
            return []

    @staticmethod
    def get_sms_from_number_list(sms_id, cursor=None):
        """
        Get list of phone numbers used to send SMS for campaign
        Java: CampaignSendSmsRepository.findFromContactList()

        Args:
            sms_id: SMS campaign ID
            cursor: Database cursor (optional)

        Returns:
            List of unique phone numbers
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                SELECT DISTINCT replace(CSQ_FROM_CONTACT, '+', '') AS fromContact
                FROM CAMPAIGN_SMS_QUEUED
                WHERE CSQ_CSS_ID = %s AND CSQ_FROM_CONTACT IS NOT NULL
                ORDER BY CSQ_FROM_CONTACT
            """

            cursor.execute(query, [sms_id])
            results = cursor.fetchall()
            return [row[0] for row in results]
        except Exception as e:
            logger.error(f"Error getting SMS from numbers: {e}")
            return []

    @staticmethod
    def get_campaign_transaction_list(tenant_id, page_no=0, page_size=10, cursor=None):
        """
        Get paginated list of SMS campaign transactions for member
        Java: CampaignTransactionRepository logic

        Args:
            tenant_id: Tenant ID
            page_no: Page number (0-based)
            page_size: Records per page
            cursor: Database cursor (optional)

        Returns:
            Tuple: (transaction_list, total_count)
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            # Get total count
            count_query = """
                SELECT COUNT(*)
                FROM CAMPAIGN_BILLING
                WHERE CT_CLIENT_ID = %s AND CT_TRAN_TYPE = 'sms'
            """
            cursor.execute(count_query, [get_client_id_by_tenant_id(tenant_id)])
            total_count = cursor.fetchone()[0]

            # Get paginated results
            offset = page_no * page_size
            query = """
                SELECT
                    CT_TRANS_ID, CT_TRAN_CAMPAIGN_ID, CT_TRAN_CAMPAIGN_NAME, CT_TRAN_TOTAL_MEMBER,
                    CT_TRAN_TYPE, CT_TRAN_BILL_TYPE, CT_TRAN_TOTAL_AMOUNT, CT_TRAN_MEMBER_RATE,
                    CT_TRAN_COUNT_TOTAL_SMS, CT_TRAN_INVOICED_STATUS, CT_TRAN_DATE
                FROM CAMPAIGN_BILLING
                WHERE CT_CLIENT_ID = %s AND CT_TRAN_TYPE = 'sms'
                ORDER BY CT_TRANS_ID DESC
                OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """

            cursor.execute(query, [get_client_id_by_tenant_id(tenant_id), offset, page_size])
            results = cursor.fetchall()

            transactions = []
            for row in results:
                transactions.append({
                    'tranId': row[0],
                    'tranCampaignId': row[1],
                    'tranCampaignName': row[2],
                    'tranTotalMember': row[3],
                    'tranType': row[4],
                    'tranBillType': row[5],
                    'tranTotalAmount': float(row[6]),
                    'tranMemberRate': float(row[7]),
                    'tranCountTotalSms': row[8],
                    'tranInvoicedStatus': row[9],
                    'tranDate': row[10]
                })

            return transactions, total_count
        except Exception as e:
            logger.error(f"Error getting campaign transaction list: {e}")
            return [], 0

    @staticmethod
    def check_campaign_name_exists(tenant_id, sms_name, exclude_sms_id=None, cursor=None):
        """
        Check if campaign name already exists for member
        Java: CampaignsSmsRepository.findByNameAndMemberId()

        Args:
            tenant_id: Tenant ID
            sms_name: Campaign name to check
            exclude_sms_id: SMS ID to exclude from check (for edit operation)
            cursor: Database cursor (optional)

        Returns:
            Boolean - True if exists
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            if exclude_sms_id:
                query = """
                    SELECT COUNT(*)
                    FROM CAMPAIGN_SMS
                    WHERE CS_CLIENT_ID = %s AND CS_NAME = %s AND CS_ID != %s
                """
                cursor.execute(query, [get_client_id_by_tenant_id(tenant_id), sms_name, exclude_sms_id])
            else:
                query = """
                    SELECT COUNT(*)
                    FROM CAMPAIGN_SMS
                    WHERE CS_CLIENT_ID = %s AND CS_NAME = %s
                """
                cursor.execute(query, [get_client_id_by_tenant_id(tenant_id), sms_name])

            result = cursor.fetchone()
            return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"Error checking campaign name: {e}")
            return False

    @staticmethod
    def update_campaign_open_status(sms_id, pn_id, cursor=None):
        """
        Set campaign status to 'open'
        Java: CampaignsSmsRepository.updateData()
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = "UPDATE CAMPAIGN_SMS SET CS_OPEN_CLOSE = 'open', CS_PN_ID = %s WHERE CS_ID = %s"
            cursor.execute(query, [pn_id, sms_id])
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error updating campaign open status: {e}")
            return 0

    @staticmethod
    def insert_campaign_send_record(sms_id, cursor=None):
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                INSERT INTO CAMPAIGN_SMS_SENT 
                (CSS_CLIENT_ID, CSS_SMS_NAME, CSS_GROUP_LIST, CSS_SEND_DATE, 
                 CSS_CS_ID, CSS_SEND_ON_DATE, CSS_SEND_ON_TIME, CSS_SCHEDULE_TYPE, CSS_IS_SEND, CSS_CHK_OPT_OUT, CSS_OPT_OUT_MSG)
                SELECT 
                    CS_CLIENT_ID, CS_NAME, CS_GROUPLIST, CS_SEND_DATE, 
                    CS_ID, CS_SEND_ON_DATE, CS_SEND_ON_TIME, CS_SCHEDULE_TYPE, NULL, CS_CHK_OPT_OUT, CS_OPT_OUT_MSG 
                FROM CAMPAIGN_SMS 
                WHERE CS_ID = %s
            """
            cursor.execute(query, [sms_id])
            
            # Get the generated ID (Oracle uses sequence/identity)
            # Java: campaignsSmsSendRepository.getId(smsId)
            cursor.execute("SELECT CSS_ID FROM CAMPAIGN_SMS_SENT WHERE CSS_CS_ID = %s ORDER BY CSS_ID DESC FETCH FIRST 1 ROWS ONLY", [sms_id])
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error inserting campaign send record: {e}")
            return None

    @staticmethod
    def get_sms_links_id(cid, new_link, old_link, cursor=None):
        """
        Check if SMS link already exists for the send record
        Java: smsLinksRepository.findSmsLinks(cid, match.get(i), matchOrg.get(i))
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = "SELECT ID FROM TBL_SMS_LINKS WHERE SMS_ID = %s AND SMS_LINK = %s AND SMS_ORG_LINK = %s"
            cursor.execute(query, [cid, new_link, old_link])
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error checking sms links: {e}")
            return None

    @staticmethod
    def update_campaign_sms_send_member(cid, cursor=None):
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                UPDATE CAMPAIGN_SMS_SENT 
                SET CSS_IS_SEND = NULL, CSS_READY_TO_SMS = 'Y'
                WHERE CSS_ID = %s
            """
            cursor.execute(query, [cid])
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error updating campaign sms send member: {e}")
            return 0
    @staticmethod
    def close_campaign_master(sms_id, cursor=None):
        """
        Mark campaign as closed
        Java: CampaignsSmsServiceImpl line 2071-2073
        """
        try:
            if cursor is None:
                cursor = connection.cursor()

            query = """
                UPDATE CAMPAIGN_SMS 
                SET CS_OPEN_CLOSE = 'close',
                    CS_CLOSE_DATE = CURRENT_TIMESTAMP
                WHERE CS_ID = %s
            """
            cursor.execute(query, [sms_id])
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error closing campaign master: {e}")
            return 0

    @staticmethod
    def check_temp_send_exists(sms_id, cursor=None):
        """
        Check if any unsent temporary records exist for the campaign
        Java: campaignSendSmsTempRepository.findSmsIdIsSend(smsId)
        """
        try:
            if cursor is None:
                cursor = connection.cursor()
            query = "SELECT CSD_ID FROM CAMPAIGN_SMS_DRAFT WHERE CSD_CS_ID = %s AND CSD_IS_SEND = 'N' FETCH FIRST 1 ROWS ONLY"
            cursor.execute(query, [sms_id])
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking temp send records: {e}")
            return False

    @staticmethod
    def update_sms_detail_text(sd_id, new_text, cursor=None):
        """
        Update the text of a campaign detail record
        Java: campaignsSmsDetailsRepository.save(smsDetails)
        """
        try:
            if cursor is None:
                cursor = connection.cursor()
            query = "UPDATE CAMPAIGN_SMS_DETAILS SET CSD_DETAIL = %s WHERE CSD_ID = %s"
            cursor.execute(query, [new_text, sd_id])
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error updating sms detail text: {e}")
            return 0

    @staticmethod
    def insert_sms_link(cid, tiny_url, original_url, cursor=None):
        """
        Insert a new SMS link tracking record
        Java: smsLinksRepository.save(smsLinks)
        """
        try:
            if cursor is None:
                cursor = connection.cursor()
            query = """
                INSERT INTO TBL_SMS_LINKS (SMS_ID, SMS_LINK, SMS_ORG_LINK, LINK_COUNT)
                VALUES (%s, %s, %s, 0)
            """
            cursor.execute(query, [cid, tiny_url, original_url])
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error inserting sms link: {e}")
            return 0