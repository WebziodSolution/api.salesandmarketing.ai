import requests
from django.conf import settings

class AuthIdHelper:
    @staticmethod
    def auth_id_token():
        """
        Retrieves AuthId access and refresh tokens.
        Mirrors AuthId.authIdToken in Java.
        """
        auth_id_external_id = settings.AUTHID_EXTERNAL_ID
        auth_id_api_key_value = settings.AUTHID_API_KEY_VALUE
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = {
            "error": "",
            "accessToken": "",
            "refreshToken": ""
        }
        
        try:
            url = f"{auth_id_base_url}IdentityService/v1/auth/token"
            response = requests.post(url, auth=(auth_id_external_id, auth_id_api_key_value))
            
            if response.status_code == 200:
                data = response.json()
                res_body["accessToken"] = data.get("AccessToken", "")
                res_body["refreshToken"] = data.get("RefreshToken", "")
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_create_account(user_data, account_type):
        """
        Creates an AuthId account.
        Mirrors AuthId.authIdCreateAccount in Java.
        user_data is expected to have member_id, username, and email.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        auth_id_account_number_start = settings.AUTHID_ACCOUNT_NUMBER_START
        
        res_body = AuthIdHelper.auth_id_token()
        res_body["accountNumber"] = ""
        
        if res_body.get("error"):
            return res_body
            
        try:
            username = user_data.get("username", "")
            email = user_data.get("email", "")
            member_id = user_data.get("member_id", "")
            phone_number = ""

            if account_type.lower() == "onlyselfie":
                account_number = f"{auth_id_account_number_start}-{account_type}-{member_id}"
                name = account_number
                email = ""
            else:
                account_number = f"{auth_id_account_number_start}-{username}"
                name = username
            
            # Attempt to delete existing account first, mirroring Java logic
            try:
                AuthIdHelper.auth_id_delete_account(account_number)
            except:
                pass
                
            url = f"{auth_id_base_url}Default/AdministrationServiceRest/v1/accounts"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            body = {
                "AccountNumber": account_number,
                "Version": 0,
                "DisplayName": name,
                "CustomDisplayName": name,
                "Description": "",
                "Enabled": True,
                "Custom": True,
                "Email": email,
                "PhoneNumber": phone_number
            }
            
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                data = response.json()
                res_body["accountNumber"] = data.get("AccountNumber", "")
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_get_account(account_number):
        """
        Retrieves AuthId account details.
        Mirrors AuthId.authIdGetAccount in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        res_body["accountNumber"] = ""
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AdministrationServiceRest/v1/accounts/{account_number}"
            headers = {
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    res_body["accountNumber"] = ""
                else:
                    res_body["accountNumber"] = data.get("AccountNumber", "")
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_get_foreign_id_document(account_number, document_type):
        """
        Starts a foreign ID document operation.
        Mirrors AuthId.authIdGetForeignIDDocument in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AuthorizationServiceRest/v2/operations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            body = {
                "AccountNumber": account_number,
                "Payload": {
                    "DocumentTypes": [document_type]
                },
                "Name": "GetForeignIDDocument",
                "Timeout": 3600,
                "TransportType": 0
            }
            
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                data = response.json()
                res_body["operationId"] = data.get("OperationId", "")
                res_body["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_enroll_bio_credential(account_number):
        """
        Starts a biometric credential enrollment operation.
        Mirrors AuthId.authIdEnrollBioCredential in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AuthorizationServiceRest/v2/operations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            body = {
                "AccountNumber": account_number,
                "Codeword": "",
                "Tag": "",
                "Name": "EnrollBioCredential",
                "Timeout": 3600,
                "TransportType": 0
            }
            
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                data = response.json()
                res_body["operationId"] = data.get("OperationId", "")
                res_body["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_verify_identity(account_number):
        """
        Starts an identity verification transaction.
        Mirrors AuthId.authIdVerifyIdentity in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AuthorizationServiceRest/v2/transactions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            body = {
                "AccountNumber": account_number,
                "ConfirmationPolicy": {
                    "TransportType": 0,
                    "CredentialType": 1,
                    "BioPolicy": {
                        "CheckLiveness": "true"
                    }
                },
                "Name": "Verify_Identity",
                "Timeout": 3600
            }
            
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                data = response.json()
                res_body["transactionId"] = data.get("TransactionId", "")
                res_body["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                if response.status_code == 409: # Conflict
                    res_body["error"] = "Biometric not found for this Username Account"
                else:
                    try:
                        data = response.json()
                        res_body["error"] = data.get("Message", response.reason or str(response.status_code))
                    except:
                        res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_get_proof_results(operation_id):
        """
        Retrieves the results of a proof operation.
        Mirrors AuthId.authIdGetProofResults in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        res_body["accountNumber"] = ""
        res_body["verified"] = ""
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AuthorizationServiceRest/v2/operations/{operation_id}/result"
            headers = {
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    res_body["error"] = "error"
                else:
                    payload = data.get("Payload", {})
                    metadata = payload.get("Metadata", {})
                    biometric_result = metadata.get("BiometricVerificationResult", {})
                    res_body["verified"] = biometric_result.get("Verified", "")
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_get_proof_results_all_data(operation_id):
        """
        Retrieves all data from a proof operation result.
        Mirrors AuthId.authIdGetProofResultsAllData in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        authidtoken = AuthIdHelper.auth_id_token()
        res_body = dict()
        res_body["error"] = authidtoken.get("error")
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AuthorizationServiceRest/v2/operations/{operation_id}/result"
            headers = {
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    res_body["error"] = "error"
                else:
                    payload = data.get("Payload", {})
                    inner_data = payload.get("Data", {})
                    document = inner_data.get("Document", {})
                    data_array = document.get("Data", [])

                    inner_res_body = dict()
                    inner_res_body["documentType"] = document.get("Type", "")
                    for item in data_array:
                        key = item.get("Key")
                        value = item.get("Value")
                        if key:
                            inner_res_body[key] = value
                    res_body["userInfo"] = inner_res_body
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_delete_account(account_number):
        """
        Deletes an AuthId account.
        Mirrors AuthId.authIdDeleteAccount in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        res_body["msg"] = ""
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AdministrationServiceRest/v1/accounts/{account_number}"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            response = requests.delete(url, headers=headers)
            
            if response.status_code == 200:
                res_body["msg"] = "done"
                res_body["error"] = ""
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_get_proof_temp_id(account_number, operation_id):
        """
        Retrieves a temporary ID for a proof operation and sets it as the biometric credential.
        Mirrors AuthId.authIdGetProofTempId in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        res_body["accountNumber"] = ""
        res_body["tempId"] = ""
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AdministrationServiceRest/v1/foreignOperations/documents/{operation_id}"
            headers = {
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    res_body["error"] = "error"
                else:
                    temp_id = data.get("TempId", "")
                    res_body = AuthIdHelper.auth_id_set_proofed_biometric_credential(account_number, temp_id)
                    res_body["tempId"] = temp_id
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_set_proofed_biometric_credential(account_number, temp_id):
        """
        Sets a proofed biometric credential for an account.
        Mirrors AuthId.authIdSetProofedBiometricCredential in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AdministrationServiceRest/v1/accounts/{account_number}/proofedBioCredential"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            body = {"TempId": temp_id}
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code != 200:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_get_foreign_biometry(account_number):
        """
        Starts a foreign biometry operation.
        Mirrors AuthId.authIdGetForeignBiometry in Java.
        """
        auth_id_base_url = settings.AUTHID_BASE_URL
        
        res_body = AuthIdHelper.auth_id_token()
        
        if res_body.get("error"):
            return res_body
            
        try:
            url = f"{auth_id_base_url}Default/AuthorizationServiceRest/v2/operations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            body = {
                "AccountNumber": account_number,
                "Codeword": "",
                "Tag": "",
                "Name": "GetForeignBiometry",
                "Timeout": 3600,
                "TransportType": 0
            }
            
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 200:
                data = response.json()
                res_body["operationId"] = data.get("OperationId", "")
                res_body["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body

    @staticmethod
    def auth_id_only_selfie_verify_identity():
        """
        Identity verification using only a selfie (specific implementation).
        Mirrors AuthId.authIdOnlySelfieVerifyIdentity in Java.
        """
        res_body = AuthIdHelper.auth_id_token()
        
        if res_body.get("error"):
            return res_body
            
        try:
            # Replicating the Java call to a public image
            image_url = "https://webapp.salesandmarketing.ai/img/innovative-products.jpg"
            image_response = requests.get(image_url)
            file_content = image_response.content
            
            url = "https://id.authid.ai/search/identify"
            headers = {
                "Authorization": f"Bearer {res_body['accessToken']}"
            }
            files = {
                "image": ("logo.jpg", file_content, "image/jpeg")
            }
            data = {
                "threshold": "84"
            }
            
            response = requests.post(url, headers=headers, files=files, data=data)
            
            if response.status_code == 200:
                data = response.json()
                res_body["id"] = data.get("id", "")
            else:
                try:
                    data = response.json()
                    res_body["error"] = data.get("Message", response.reason or str(response.status_code))
                except:
                    res_body["error"] = response.reason or str(response.status_code)
        except Exception as e:
            res_body["error"] = str(e)
            
        return res_body
