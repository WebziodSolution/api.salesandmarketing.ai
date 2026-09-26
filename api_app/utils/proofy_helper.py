import requests
from django.conf import settings

class ProofyHelper:
    @staticmethod
    def validate(email):
        """
        Validates an email using Proofy API.
        Mirrors the logic in Proofy.java.
        """
        proofy_base_url = settings.PROOFY_BASE_URL
        proofy_api_key = settings.PROOFY_API_KEY
        
        res_body = {
            "status": False,
            "error": ""
        }
        
        try:
            # Replicating the URL structure from Java:
            # proofyBaseUrl + "verify/single?api_key=" + proofyApiKey + "&email=" + email
            url = f"{proofy_base_url}verify/single"
            params = {
                "api_key": proofy_api_key,
                "email": email
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    res_body["status"] = False
                else:
                    # Java: String emailStatus = data.getString("status");
                    # The Java code accesses a field named "status" inside the JSON response body
                    email_status = data.get("status", "").lower()
                    
                    # Java: if(emailStatus.equalsIgnoreCase("deliverable") || emailStatus.equalsIgnoreCase("risky") || emailStatus.equalsIgnoreCase("valid"))
                    valid_statuses = ["deliverable", "risky", "valid"]
                    if email_status in valid_statuses:
                        res_body["status"] = True
                    else:
                        res_body["status"] = False
            else:
                # Java: resBody.put("error", response.getStatusText());
                res_body["error"] = response.reason if hasattr(response, 'reason') else str(response.status_code)
                
        except Exception as e:
            # Java: resBody.put("error", e.getMessage());
            res_body["error"] = str(e)
            
        return res_body
