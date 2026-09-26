import requests
from django.conf import settings

class ZeroBounceHelper:
    @staticmethod
    def validate(email):
        """
        Validates an email using ZeroBounce API.
        Mirrors the logic in ZeroBounce.java.
        """
        zero_bounce_base_url = settings.ZERO_BOUNCE_BASE_URL
        zero_bounce_api_key = settings.ZERO_BOUNCE_API_KEY
        
        res_body = {
            "status": False,
            "error": ""
        }
        
        try:
            # Replicating the URL structure from Java:
            # zeroBounceBaseUrl + "validate?api_key=" + zeroBounceApiKey + "&email=" + email
            url = f"{zero_bounce_base_url}validate"
            params = {
                "api_key": zero_bounce_api_key,
                "email": email
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    res_body["status"] = False
                else:
                    # Java: if(data.getString("status").equals("valid"))
                    email_status = data.get("status", "").lower()
                    if email_status == "valid":
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
