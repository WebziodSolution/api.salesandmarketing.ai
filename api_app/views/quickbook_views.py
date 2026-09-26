import os
import json
import random
import requests
import logging
from datetime import datetime
from django.conf import settings
from requests.auth import HTTPBasicAuth
from rest_framework.views import APIView
from common_app.custom_permissions import WhitelistPermission
from auth_app.authentication import MemberJWTAuthentication
from common_app.models import TempUserlist
from common_app.utils import get_final_tenant_id, api_response, get_tenants

logger = logging.getLogger(__name__)

class QuickbookBaseView(APIView):
    authentication_classes = [MemberJWTAuthentication]
    permission_classes = [WhitelistPermission]

    @staticmethod
    def get_final_id(request):
        return get_final_tenant_id(request=request)

    @staticmethod
    def get_user_identifier(tenant):
        return f"{tenant.ten_first_name}_{tenant.ten_last_name}_{tenant.ten_id}"

    def get_token_path(self, tenant):
        user_id = self.get_user_identifier(tenant)
        return os.path.join(settings.QUICKBOOKS_TOKEN_DIR, f"{user_id}.json")

    def save_auth_data(self, tenant, data):
        path = self.get_token_path(tenant)
        # Load existing data if any to preserve fields
        existing_data = self.get_auth_data(tenant)
        existing_data.update(data)
        
        if not os.path.exists(settings.QUICKBOOKS_TOKEN_DIR):
            os.makedirs(settings.QUICKBOOKS_TOKEN_DIR)
            
        with open(path, 'w') as f:
            json.dump(existing_data, f)

    def get_auth_data(self, tenant):
        path = self.get_token_path(tenant)
        if os.path.exists(path):
            with open(path, 'r') as f:
                try:
                    return json.load(f)
                except:
                    return {}
        return {}

class ConnectToQuickbooksView(QuickbookBaseView):
    authentication_classes = [MemberJWTAuthentication]
    permission_classes = [WhitelistPermission]
    def get(self, request):
        tenant_id = self.get_final_id(request)
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        
        # Generate CSRF token
        csrf_token = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))
        
        # Store CSRF in file
        self.save_auth_data(tenant, {'csrf_token': csrf_token})
        
        # Scope for Accounting
        scope = "com.intuit.quickbooks.accounting"
        
        # Build Authorization URL
        auth_url = (
            f"https://appcenter.intuit.com/connect/oauth2"
            f"?client_id={settings.QUICKBOOKS_CLIENT_ID}"
            f"&response_type=code"
            f"&scope={scope}"
            f"&redirect_uri={settings.QUICKBOOKS_REDIRECT_URI}"
            f"&state={csrf_token}"
        )
        
        return api_response(200, "Redirect Url.", {"url": auth_url})

class OAuth2RedirectView(QuickbookBaseView):
    def get(self, request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        realm_id = request.query_params.get('realmId')

        tenant_id = self.get_final_id(request)
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        
        auth_data = self.get_auth_data(tenant)
        if not auth_data or auth_data.get('csrf_token') != state:
            return api_response(500, "Invalid state parameter or authentication state not found.", {})
            
        # Exchange code for tokens
        token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        payload = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.QUICKBOOKS_REDIRECT_URI
        }
        
        try:
            response = requests.post(token_url, auth=HTTPBasicAuth(settings.QUICKBOOKS_CLIENT_ID, settings.QUICKBOOKS_CLIENT_SECRET), data=payload)
            if response.status_code != 200:
                logger.error(f"Quickbooks token exchange failed: {response.text}")
                return api_response(500, "Failed to exchange tokens.", {})
                
            token_data = response.json()
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            
            # Update Auth Data in file
            self.save_auth_data(tenant, {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'realm_id': realm_id,
                'auth_code': code,
                'last_updated': datetime.now().isoformat()
            })
            
            # Fetch Company Info (Customers)
            import_service = QuickbookImportService(tenant_id, realm_id, access_token)
            resp_data = import_service.import_customers()
            
            return api_response(200, "Contact Import Successfully.", resp_data)
            
        except Exception as e:
            logger.error(f"Quickbooks OAuth callback error: {str(e)}")
            return api_response(500, "Internal Server Error", {"error": str(e)})

class QuickbookImportService:
    def __init__(self, tenant_id, realm_id, access_token):
        self.tenant_id = tenant_id
        self.realm_id = realm_id
        self.access_token = access_token
        self.api_host = settings.QUICKBOOKS_API_HOST
        
        self.key_value_fields = {
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
            "tags": "Tags",
            "jobTitle": "Job Title"
        }

    def import_customers(self):
        url = f"{self.api_host}/v3/company/{self.realm_id}/query"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/text'
        }
        query = "select * from Customer"
        
        response = requests.post(url, headers=headers, data=query)
        if response.status_code != 200:
            logger.error(f"Quickbooks query failed: {response.text}")
            raise Exception("Failed to fetch customers from Quickbooks")
            
        data = response.json()
        query_result = data.get('QueryResponse', {})
        customers = query_result.get('Customer', [])
        
        return self.process_customers(customers)

    def process_customers(self, customers):
        tran_id = str(random.randint(10000, 20000))
        
        for customer in customers:
            try:
                email_addr = customer.get('PrimaryEmailAddr', {}).get('Address', '')
                primary_phone = customer.get('PrimaryPhone', {}).get('FreeFormNumber', '')
                mobile_phone = customer.get('Mobile', {}).get('FreeFormNumber', '')
                alt_phone = customer.get('AlternatePhone', {}).get('FreeFormNumber', '')
                
                # Check if we have any contact info
                if email_addr or primary_phone or mobile_phone or alt_phone:
                    temp_user = TempUserlist()
                    temp_user.memberId = self.tenant_id
                    temp_user.transId = tran_id
                    temp_user.firstName = customer.get('GivenName', '')
                    temp_user.lastName = customer.get('FamilyName', '')
                    temp_user.email = email_addr.lower() if email_addr else ""
                    
                    phone = primary_phone or mobile_phone or alt_phone or ""
                    temp_user.phoneNumber = phone
                    
                    bill_addr = customer.get('BillAddr', {})
                    address_parts = []
                    for i in range(1, 6):
                        line = bill_addr.get(f'Line{i}')
                        if line:
                            address_parts.append(line)
                    
                    temp_user.streetAddress1 = ", ".join(address_parts)
                    temp_user.city = bill_addr.get('City', '')
                    temp_user.country = bill_addr.get('Country', '')
                    temp_user.zipPostalCode = bill_addr.get('PostalCode', '')
                        
                    temp_user.tags = bill_addr.get('Tag', '')
                        
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    temp_user.dateAdded = now_str
                    temp_user.dateLastModified = now_str
                    temp_user.status = 'active'
                    temp_user.save()
                    
            except Exception as e:
                logger.error(f"Error processing customer: {str(e)}")
                continue
                
        # Calculate statistics
        email_ids = TempUserlist.objects.filter(memberId=self.tenant_id, transId=tran_id).values_list('emailId', flat=True)
        if email_ids:
            min_id = min(email_ids)
            max_id = max(email_ids)
        else:
            min_id = 0
            max_id = 0
            
        total_record = len(email_ids)
        invalid_emails = 0 
        
        # Display body
        user_list = TempUserlist.objects.filter(memberId=self.tenant_id, transId=tran_id)
        body = []
        for u in user_list:
            body.append({
                "emailId": u.emailId,
                "firstName": u.firstName,
                "lastName": u.lastName,
                "email": u.email,
                "phoneNumber": u.phoneNumber,
                "address": u.streetAddress1,
                "city": u.city,
                "country": u.country,
                "zipPostalCode": u.zipPostalCode,
                "tags": u.tags,
            })
            
        return {
            "cronStartId": min_id,
            "cronEndId": max_id,
            "totalRecord": total_record,
            "invalidEmails": invalid_emails,
            "transId": tran_id,
            "body": body,
            "dataTableHeaders": self.key_value_fields
        }
