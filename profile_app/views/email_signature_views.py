import logging
from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response, get_client_id_by_tenant_id
from profile_app.models import EmailSignature
from django.utils import timezone
from common_app.utils import get_final_tenant_id

@api_view(['DELETE', 'POST'])
def deleteEmailSignature(request: Request):
    resBody = dict()
    try:
        data = request.data
        sign_ids = data.get('signId', [])
        
        if sign_ids:
            for sign_id in sign_ids:
                signature_exists = EmailSignature.objects.filter(signId=sign_id).exists()
                if signature_exists:
                    EmailSignature.objects.filter(signId=sign_id).delete()
                    
        return api_response(200, "Email Signature Deleted Successfully.", resBody)
    except Exception as e:
        logging.error(f"DeleteEmailSignature Error : {e}")
        return api_response(500, "Error Processing Request", resBody)

@api_view(['GET'])
def getEmailSignatureList(request):
    resBody = dict()
    final_member_id = get_final_tenant_id(request=request)
    try:
        email_signatures = EmailSignature.objects.filter(signMemberId=get_client_id_by_tenant_id(final_member_id))

        sig_list = []
        for sig in email_signatures:
            sig_list.append({
                "signId": sig.signId,
                "signTitle": sig.signTitle,
                "signDescription": sig.signDescription,
                "signDateTime": sig.signDateTime.strftime("%m/%d/%Y %H:%M:%S.") if sig.signDateTime else None,
                "signMemberId": sig.signMemberId
            })

        resBody["emailSignature"] = sig_list
        return api_response(200, "Fetch Email Signature Successfully.", resBody)
    except Exception as e:
        logging.error(f"[ MemberId : {final_member_id} ] GetEmailSignatureList Error : {e}")
        return api_response(500, "Error Processing Request", resBody)

@api_view(['POST'])
def saveEmailSignature(request: Request):
    resBody = dict()
    final_member_id = get_final_tenant_id(request=request)
    try:
        data = request.data
        sign_id = data.get('signId', 0)
        sign_title = data.get('signTitle')
        sign_description = data.get('signDescription')

        resBody["error"] = ""

        try:
            if sign_id == 0:
                email_signature = EmailSignature()
            else:
                email_signature = EmailSignature.objects.filter(signId=sign_id).first()
                if not email_signature:
                    email_signature = EmailSignature()

            email_signature.signTitle = sign_title
            email_signature.signDescription = sign_description
            email_signature.signMemberId = get_client_id_by_tenant_id(final_member_id)
            email_signature.signDateTime = timezone.now()
            email_signature.save()
        except Exception:
            resBody["error"] = "Invalid Data"
            return api_response(500, "Invalid Data", resBody)

        return api_response(200, "Email Signature Added Successfully", resBody)

    except Exception as e:
        logging.error(f"[ MemberId : {final_member_id} ] SaveEmailSignature Error : {e}")
        return api_response(500, "Error Processing Request", resBody)