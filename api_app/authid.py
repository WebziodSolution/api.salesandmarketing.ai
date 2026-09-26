import json
import requests

class AuthId:
    @staticmethod
    def authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl):
        resBody = {
            "error": "",
            "accessToken": "",
            "refreshToken": ""
        }
        try:
            url = f"{authIdBaseUrl}IdentityService/v1/auth/token"
            response = requests.post(url, auth=(authIdExternalId, authIdApiKeyValue))
            if response.status_code == 200:
                data = response.json()
                resBody["accessToken"] = data.get("AccessToken", "")
                resBody["refreshToken"] = data.get("RefreshToken", "")
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdCreateAccount(authIdExternalId, authIdApiKeyValue, userDataDto, authIdAccountNumberStart, accountType, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        resBody["accountNumber"] = ""
        try:
            name = userDataDto.get("username", "")
            email = userDataDto.get("email", "")
            phoneNumber = ""
            if accountType.lower() == "onlyselfie":
                accountNumber = f"{authIdAccountNumberStart}-{accountType}-{userDataDto.get('memberId', '')}"
                name = accountNumber
                email = ""
            else:
                accountNumber = f"{authIdAccountNumberStart}-{userDataDto.get('username', '')}"

            try:
                AuthId.authIdDeleteAccount(authIdExternalId, authIdApiKeyValue, accountNumber, authIdBaseUrl)
            except Exception:
                pass

            url = f"{authIdBaseUrl}Default/AdministrationServiceRest/v1/accounts"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            payload = {
                "AccountNumber": accountNumber,
                "Version": 0,
                "DisplayName": name,
                "CustomDisplayName": name,
                "Description": "",
                "Enabled": True,
                "Custom": True,
                "Email": email,
                "PhoneNumber": phoneNumber
            }
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                resBody["accountNumber"] = data.get("AccountNumber", "")
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdGetAccount(authIdExternalId, authIdApiKeyValue, accountNumber, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        resBody["accountNumber"] = ""
        try:
            url = f"{authIdBaseUrl}Default/AdministrationServiceRest/v1/accounts/{accountNumber}"
            headers = {"Authorization": f"Bearer {resBody.get('accessToken', '')}"}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                if response.text:
                    data = response.json()
                    resBody["accountNumber"] = data.get("AccountNumber", "")
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdGetForeignIDDocument(authIdExternalId, authIdApiKeyValue, accountNumber, authIdDocumentType, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        try:
            url = f"{authIdBaseUrl}Default/AuthorizationServiceRest/v2/operations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            payload = {
                "AccountNumber": accountNumber,
                "Payload": {
                    "DocumentTypes": [authIdDocumentType]
                },
                "Name": "GetForeignIDDocument",
                "Timeout": 3600,
                "TransportType": 0
            }
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                if not response.text:
                    resBody["operationId"] = ""
                    resBody["oneTimeSecret"] = ""
                else:
                    data = response.json()
                    resBody["operationId"] = data.get("OperationId", "")
                    resBody["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdEnrollBioCredential(authIdExternalId, authIdApiKeyValue, accountNumber, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        try:
            url = f"{authIdBaseUrl}Default/AuthorizationServiceRest/v2/operations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            payload = {
                "AccountNumber": accountNumber,
                "Codeword": "",
                "Tag": "",
                "Name": "EnrollBioCredential",
                "Timeout": 3600,
                "TransportType": 0
            }
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                if not response.text:
                    resBody["operationId"] = ""
                    resBody["oneTimeSecret"] = ""
                else:
                    data = response.json()
                    resBody["operationId"] = data.get("OperationId", "")
                    resBody["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdVerifyIdentity(authIdExternalId, authIdApiKeyValue, accountNumber, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        try:
            url = f"{authIdBaseUrl}Default/AuthorizationServiceRest/v2/transactions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            payload = {
                "AccountNumber": accountNumber,
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
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                if not response.text:
                    resBody["transactionId"] = ""
                    resBody["oneTimeSecret"] = ""
                else:
                    data = response.json()
                    resBody["transactionId"] = data.get("TransactionId", "")
                    resBody["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                if response.reason.lower() == "conflict":
                    resBody["error"] = "Biometric not found for this Username Account"
                else:
                    data = response.json() if response.text else {}
                    resBody["error"] = data.get("Message", response.reason)
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdGetProofResults(authIdExternalId, authIdApiKeyValue, authidOperationId, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        resBody["accountNumber"] = ""
        resBody["verified"] = ""
        try:
            url = f"{authIdBaseUrl}Default/AuthorizationServiceRest/v2/operations/{authidOperationId}/result"
            headers = {"Authorization": f"Bearer {resBody.get('accessToken', '')}"}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                if not response.text:
                    resBody["error"] = "error"
                else:
                    data = response.json()
                    verified = data.get("Payload", {}).get("Metadata", {}).get("BiometricVerificationResult", {}).get("Verified", False)
                    resBody["verified"] = verified
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdGetProofResultsAllData(authIdExternalId, authIdApiKeyValue, authidOperationId, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        innerResBody = dict()
        try:
            url = f"{authIdBaseUrl}Default/AuthorizationServiceRest/v2/operations/{authidOperationId}/result"
            headers = {"Authorization": f"Bearer {resBody.get('accessToken', '')}"}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                if not response.text:
                    resBody["error"] = "error"
                else:
                    data = response.json()
                    innerDocument = data.get("Payload", {}).get("Data", {}).get("Document", {})
                    innerResBody["documentType"] = innerDocument.get("Type", "")
                    for item in innerDocument.get("Data", []):
                        innerResBody[item.get("Key")] = item.get("Value")
                    resBody["userInfo"] = json.dumps(innerResBody)
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdDeleteAccount(authIdExternalId, authIdApiKeyValue, accountNumber, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        resBody["msg"] = ""
        try:
            url = f"{authIdBaseUrl}Default/AdministrationServiceRest/v1/accounts/{accountNumber}"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            response = requests.delete(url, headers=headers)
            if response.status_code == 200:
                resBody["msg"] = "done"
                resBody["error"] = ""
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdGetProofTempId(authIdExternalId, authIdApiKeyValue, authidAccountNumber, authidOperationId, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        resBody["accountNumber"] = ""
        resBody["tempId"] = ""
        try:
            url = f"{authIdBaseUrl}Default/AdministrationServiceRest/v1/foreignOperations/documents/{authidOperationId}"
            headers = {"Authorization": f"Bearer {resBody.get('accessToken', '')}"}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                if not response.text:
                    resBody["error"] = "error"
                else:
                    data = response.json()
                    tempId = data.get("TempId", "")
                    resBody = AuthId.authIdSetProofedBiometricCredential(authIdExternalId, authIdApiKeyValue, authidAccountNumber, tempId, authIdBaseUrl)
                    resBody["tempId"] = tempId
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdSetProofedBiometricCredential(authIdExternalId, authIdApiKeyValue, authidAccountNumber, proofTempId, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        try:
            url = f"{authIdBaseUrl}Default/AdministrationServiceRest/v1/accounts/{authidAccountNumber}/proofedBioCredential"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            payload = {"TempId": proofTempId}
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdGetForeignBiometry(authIdExternalId, authIdApiKeyValue, accountNumber, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        try:
            url = f"{authIdBaseUrl}Default/AuthorizationServiceRest/v2/operations"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            payload = {
                "AccountNumber": accountNumber,
                "Codeword": "",
                "Tag": "",
                "Name": "GetForeignBiometry",
                "Timeout": 3600,
                "TransportType": 0
            }
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                if not response.text:
                    resBody["operationId"] = ""
                    resBody["oneTimeSecret"] = ""
                else:
                    data = response.json()
                    resBody["operationId"] = data.get("OperationId", "")
                    resBody["oneTimeSecret"] = data.get("OneTimeSecret", "")
            else:
                resBody["error"] = response.reason
        except Exception as e:
            resBody["error"] = str(e)
        return resBody

    @staticmethod
    def authIdOnlySelfieVerifyIdentity(authIdExternalId, authIdApiKeyValue, authIdBaseUrl):
        resBody = AuthId.authIdToken(authIdExternalId, authIdApiKeyValue, authIdBaseUrl)
        try:
            image_url = "https://webapp.salesandmarketing.ai/img/innovative-products.jpg"
            image_response = requests.get(image_url)
            file_content = image_response.content

            url = "https://id.authid.ai/search/identify"
            headers = {
                "accept": "text/plain",
                "Authorization": f"Bearer {resBody.get('accessToken', '')}"
            }
            files = {
                "image": ("logo.jpg", file_content, "image/jpeg")
            }
            data_payload = {
                "threshold": "84"
            }
            response = requests.post(url, headers=headers, files=files, data=data_payload)
            if response.status_code == 200:
                data = response.json()
                resBody["id"] = data.get("id", "")
            else:
                data = response.json() if response.text else {}
                resBody["error"] = data.get("Message", response.reason)
        except Exception as e:
            resBody["error"] = str(e)
        return resBody
