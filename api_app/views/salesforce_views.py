from rest_framework.decorators import api_view
from django.conf import settings
from common_app.utils import api_response, get_final_tenant_id
from common_app.models import TempUserlist
import urllib.parse
import requests
import time
import random
import logging
from datetime import datetime
from rest_framework.request import Request
from django.db.models import Min, Max, Count

logger = logging.getLogger(__name__)

KEY_VALUE_FIELDS = {
    "firstName": "First Name",
    "lastName": "Last Name",
    "email": "Email",
    "phoneNumber": "Mobile Number",
    "address": "Address",
    "city": "City",
    "country": "Country",
    "zipPostalCode": "Zip Code",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "notes": "Notes",
}

def random_generation():
    r = random.Random(time.time() * 1000)
    return (1 + r.randint(0, 1)) * 10000 + r.randint(0, 9999)

@api_view(['GET', 'POST'])
def connectToSalesforce(request):
    res_body = {}
    url = f"{settings.SALESFORCE_LOGIN_URI}/services/oauth2/authorize?response_type=code&client_id={settings.SALESFORCE_CLIENT_ID}&redirect_uri={urllib.parse.quote(settings.SALESFORCE_REDIRECT)}"
    res_body["url"] = url
    return api_response(200, "Redirect Url.", res_body)

@api_view(['GET', 'POST'])
def callBackFromOAuth(request: Request):
    final_tenant_id = get_final_tenant_id(request=request)
    auth_code = request.query_params.get('code')

    try:
        res_body = dict()
        # Token Exchange
        token_url = f"{settings.SALESFORCE_LOGIN_URI}/services/oauth2/token"
        params = {
            "code": auth_code,
            "grant_type": "authorization_code",
            "client_id": settings.SALESFORCE_CLIENT_ID,
            "client_secret": settings.SALESFORCE_CLIENT_SECRET,
            "redirect_uri": settings.SALESFORCE_REDIRECT
        }

        response = requests.post(token_url, params=params)
        token_data = response.json()

        instance_url = token_data.get("instance_url")
        access_token = token_data.get("access_token")

        res_body["instance_url"] = instance_url
        res_body["access_token"] = access_token

        if instance_url and access_token:
            populate_response(final_tenant_id, res_body)

        return api_response(200, "Contact Import Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {final_tenant_id} ] CallBackFromOAuth Error : {e}")
        return api_response(500, "Error Processing Request", "")

def format_date_per_rule_9(date_val):
    if not date_val:
        return None
    if isinstance(date_val, str):
        try:
            date_val = datetime.strptime(date_val, "%Y-%m-%d %H:%M:%S")
        except:
            return date_val
    # Rule 9: MM-dd-yyyy MM-dd-yyyy HH:mm:ss.
    return date_val.strftime("%m-%d-%Y %m-%d-%Y %H:%M:%S.")

def populate_response(tenant_id, res_body):
    instance_url = res_body.get("instance_url")
    access_token = res_body.get("access_token")
    
    if instance_url and access_token:
        sql_query = "Select Id,FirstName,LastName,Email,Phone,Birthdate,MailingStreet,Fax,MobilePhone,HomePhone,MailingCity,MailingState,MailingCountry,MailingPostalCode,MailingLatitude,MailingLongitude,Description from Contact"
        
        query_url = f"{instance_url}/services/data/v51.0/query?q={urllib.parse.quote(sql_query)}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(query_url, headers=headers)
        contact_data = response.json()
        
        if "records" in contact_data:
            records = contact_data["records"]
            tran_id = str(random_generation())
            
            for contact in records:
                temp_user = TempUserlist()
                temp_user.transId = tran_id
                temp_user.firstName = str(contact.get("FirstName") or "")
                temp_user.lastName = str(contact.get("LastName") or "")
                temp_user.memberId = tenant_id
                
                email = contact.get("Email")
                if email and str(email).lower() != "null":
                    temp_user.email = str(email).lower()
                else:
                    temp_user.email = ""
                
                phone_number = ""
                if contact.get("MobilePhone") and str(contact.get("MobilePhone")).lower() != "null":
                    phone_number = contact.get("MobilePhone")
                elif contact.get("HomePhone") and str(contact.get("HomePhone")).lower() != "null":
                    phone_number = contact.get("HomePhone")
                elif contact.get("Phone") and str(contact.get("Phone")).lower() != "null":
                    phone_number = contact.get("Phone")
                
                temp_user.phoneNumber = str(phone_number or "")
                
                if contact.get("MailingStreet") and str(contact.get("MailingStreet")).lower() != "null":
                    temp_user.streetAddress1 = str(contact.get("MailingStreet"))
                if contact.get("MailingCity") and str(contact.get("MailingCity")).lower() != "null":
                    temp_user.city = str(contact.get("MailingCity"))
                if contact.get("MailingCountry") and str(contact.get("MailingCountry")).lower() != "null":
                    temp_user.country = str(contact.get("MailingCountry"))
                if contact.get("MailingPostalCode") and str(contact.get("MailingPostalCode")).lower() != "null":
                    temp_user.zipPostalCode = str(contact.get("MailingPostalCode"))
                
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                temp_user.dateAdded = now_str
                temp_user.dateLastModified = now_str
                temp_user.save()
            
            # Summary attributes
            email_stats = TempUserlist.objects.filter(memberId=tenant_id, transId=tran_id).aggregate(
                min_id=Min('emailId'), max_id=Max('emailId'), total=Count('emailId')
            )
            
            res_body["cronStartId"] = email_stats['min_id']
            res_body["cronEndId"] = email_stats['max_id']
            res_body["totalRecord"] = email_stats['total']
            
            # invalidEmails logic: typically checking for empty or invalid format
            invalid_emails_count = TempUserlist.objects.filter(memberId=tenant_id, transId=tran_id).filter(email="").count()
            res_body["invalidEmails"] = invalid_emails_count
            
            res_body["transId"] = tran_id
            
            # body: displayUserlist(id, tranId)
            users = TempUserlist.objects.filter(memberId=tenant_id, transId=tran_id)
            user_list_data = []
            for u in users:
                user_list_data.append({
                    "emailId": u.emailId,
                    "firstName": u.firstName,
                    "lastName": u.lastName,
                    "email": u.email,
                    "phoneNumber": u.phoneNumber,
                    "streetAddress1": u.streetAddress1,
                    "city": u.city,
                    "country": u.country,
                    "zipPostalCode": u.zipPostalCode,
                    "dateAdded": format_date_per_rule_9(u.dateAdded),
                    "dateLastModified": format_date_per_rule_9(u.dateLastModified)
                })
            res_body["body"] = user_list_data
            res_body["dataTableHeaders"] = KEY_VALUE_FIELDS
