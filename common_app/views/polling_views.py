from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response
from common_app.models import WebContentGrab, AnalyticsCsv, CustomFormReportPdf

@api_view(['GET'])
def grabImages(request: Request):
    wcg_id = request.GET.get('wcgId')
    if not wcg_id:
        return api_response(500, "Missing wcgId parameter", {})
    try:
        wcg = WebContentGrab.objects.get(id=wcg_id)
        res_body = dict()
        res_body["error"] = ""
        if wcg.response:
            res_body["status"] = True
            res_body["imageUrls"] = wcg.response.split(",") if wcg.response else []
            return api_response(200, "Images Grabbed Successfully", res_body)
        elif wcg.error:
            res_body["status"] = True
            res_body["error"] = wcg.error
            return api_response(500, wcg.error, res_body)
        else:
            res_body["status"] = False
            return api_response(200, "Still Processing", res_body)
    except WebContentGrab.DoesNotExist:
        return api_response(500, "Invalid ID", {"status": False, "error": ""})
    except Exception as e:
        return api_response(500, "An Error Occurred", {"status": False, "error": str(e)})

@api_view(['GET'])
def grabColors(request: Request):
    wcg_id = request.GET.get('wcgId')
    if not wcg_id:
        return api_response(500, "Missing wcgId parameter", {})
    try:
        wcg = WebContentGrab.objects.get(id=wcg_id)
        res_body = dict()
        res_body["error"] = ""
        if wcg.response:
            res_body["status"] = True
            res_body["websiteColors"] = wcg.response.split(",") if wcg.response else []
            return api_response(200, "Colors Grabbed Successfully", res_body)
        elif wcg.error:
            res_body["status"] = True
            res_body["error"] = wcg.error
            return api_response(500, wcg.error, res_body)
        else:
            res_body["status"] = False
            return api_response(200, "Still Processing", res_body)
    except WebContentGrab.DoesNotExist:
        return api_response(500, "Invalid ID", {"status": False, "error": ""})
    except Exception as e:
        return api_response(500, "An Error Occurred", {"status": False, "error": str(e)})

@api_view(['GET'])
def grabLinks(request: Request):
    wcg_id = request.GET.get('wcgId')
    if not wcg_id:
        return api_response(500, "Missing wcgId parameter", {})
    try:
        wcg = WebContentGrab.objects.get(id=wcg_id)
        res_body = dict()
        res_body["error"] = ""
        if wcg.response:
            res_body["status"] = True
            res_body["websiteLinks"] = wcg.response.split(",") if wcg.response else []
            return api_response(200, "Links Grabbed Successfully", res_body)
        elif wcg.error:
            res_body["status"] = True
            res_body["error"] = wcg.error
            return api_response(500, wcg.error, res_body)
        else:
            res_body["status"] = False
            return api_response(200, "Still Processing", res_body)
    except WebContentGrab.DoesNotExist:
        return api_response(500, "Invalid ID", {"status": False, "error": ""})
    except Exception as e:
        return api_response(500, "An Error Occurred", {"status": False, "error": str(e)})

@api_view(['POST'])
def grabAnalyticsCsv(request: Request):
    camp_id = request.POST.get('campId') or request.GET.get('campId')
    try:
        analytics_csv = AnalyticsCsv.objects.filter(campaign_id=camp_id).first()
        if not analytics_csv:
            return api_response(200, "Analytics CSV Grabbed Successfully", {"status": "not_started"})
        elif analytics_csv.is_processed == 0:
            return api_response(200, "Analytics CSV Grabbed Successfully", {"status": "in_progress"})
        else:
            return api_response(200, "Analytics CSV Grabbed Successfully", {"status": "completed", "csvUrl": analytics_csv.csv_url})
    except Exception as e:
        return api_response(500, "An Error Occurred", {"status": "error", "error": str(e)})

@api_view(['POST'])
def grabCustomFormPdfData(request: Request):
    cf_id = request.POST.get('cfId') or request.GET.get('cfId')
    try:
        custom_form_pdf = CustomFormReportPdf.objects.filter(custom_form_id=cf_id).first()
        if not custom_form_pdf:
            return api_response(200, "Custom From PDF Grabbed Successfully", {"status": "not_started"})
        elif custom_form_pdf.is_processed == 0:
            return api_response(200, "Custom From PDF Grabbed Successfully", {"status": "in_progress"})
        else:
            return api_response(200, "Custom From PDF Grabbed Successfully", {"status": "completed", "zipUrl": custom_form_pdf.zip_url})
    except Exception as e:
        return api_response(500, "An Error Occurred", {"status": "error", "error": str(e)})
