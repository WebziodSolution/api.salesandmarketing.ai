from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from assessment_app.models import AssessmentQuestionCategory, AssessmentsTemplate
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
from django.core.paginator import Paginator

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentCategoryList(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        categories = AssessmentQuestionCategory.objects.filter(
            Q(aqcClientId=get_client_id_by_tenant_id(final_tenant_id)) | Q(aqcClientId=0) | Q(aqcClientId__isnull=True)
        ).order_by('aqcId')
        
        category_list = []
        for cat in categories:
            category_list.append({
                "id": cat.aqcId,
                "catName": cat.aqcCatName,
                "memberId": None
            })
            
        res_body["assessmentCategoryList"] = category_list
        return api_response(200, "Fetch Assessment Category Successfully.", res_body)
    except Exception:
        return api_response(500, "Error occurred", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentCategoryById(request, cat_id):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        cat = AssessmentQuestionCategory.objects.filter(
            Q(aqcId=cat_id) & (Q(aqcClientId=get_client_id_by_tenant_id(final_tenant_id)) | Q(aqcClientId=0) | Q(aqcClientId__isnull=True))
        ).first()
        
        if cat:
            data = {
                "id": cat.aqcId,
                "catName": cat.aqcCatName,
                "memberId": None
            }
            res_body["assessmentCategory"] = data
        else:
            res_body["assessmentCategory"] = None
            
        return api_response(200, "Fetch Assessment Category Successfully.", res_body)
    except Exception:
        return api_response(500, "Error occurred", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteAssessmentCategory(request):
    res_body = {}
    try:
        aqcIds = request.data.get('id', [])
        for cat_id in aqcIds:
            AssessmentQuestionCategory.objects.filter(aqcId=cat_id).delete()
            
        return api_response(200, "Assessment Category Deleted Successfully.", res_body)
    except Exception:
        return api_response(500, "Error occurred", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentCategoryListPages(request):
    res_body = {}
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        search_key = request.GET.get('searchKey', '')
        page_no = int(request.GET.get('page', 0))
        page_size = int(request.GET.get('size', 10))
        
        base_query = Q(aqcClientId=get_client_id_by_tenant_id(final_tenant_id)) | Q(aqcClientId=0)
        if search_key:
            base_query &= Q(aqcCatName__icontains=search_key)
            
        categories = AssessmentQuestionCategory.objects.filter(base_query).order_by('aqcId')
        paginator = Paginator(categories, page_size)
        page_obj = paginator.get_page(page_no + 1)
        
        category_list = []
        for cat in page_obj:
            category_list.append({
                "id": cat.aqcId,
                "catName": cat.aqcCatName,
                "memberId": cat.aqcClientId
            })
            
        res_body["getTotalPages"] = paginator.num_pages
        res_body["getNumber"] = page_no
        res_body["getSize"] = page_size
        res_body["assessmentCategoryList"] = category_list
        
        total_count = AssessmentQuestionCategory.objects.filter(Q(aqcClientId=get_client_id_by_tenant_id(final_tenant_id)) | Q(aqcClientId=0)).count()
        res_body["totalAssessmentCategory"] = total_count
        
        return api_response(200, "Fetch Assessment Category Successfully.", res_body)
    except Exception:
        return api_response(500, "Error occurred", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveAssessmentCategory(request):
    res_body = dict()
    res_body["error"] = ""
    res_body["msg"] = ""
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        data = request.data
        cat_id = data.get('id', 0)
        cat_name = data.get('catName', '')
        
        if cat_id == 0:
            existing = AssessmentQuestionCategory.objects.filter(aqcCatName=cat_name, aqcClientId=get_client_id_by_tenant_id(final_tenant_id)).first()
            if existing:
                res_body["msg"] = "Assessment Category Name Already In Used."
                res_body["error"] = "error"
                return api_response(500, res_body["msg"], res_body)
            
            new_cat = AssessmentQuestionCategory.objects.create(
                aqcCatName=cat_name,
                aqcClientId=get_client_id_by_tenant_id(final_tenant_id)
            )
            res_body["id"] = new_cat.aqcId
            res_body["msg"] = "Add Assessment Category Successfully."
            return api_response(200, res_body["msg"], res_body)
        else:
            existing_other = AssessmentQuestionCategory.objects.filter(aqcCatName=cat_name, aqcClientId=get_client_id_by_tenant_id(final_tenant_id)).exclude(aqcId=cat_id).first()
            if existing_other:
                res_body["msg"] = "Assessment Category Name Already In Used."
                res_body["error"] = "error"
                return api_response(500, res_body["msg"], res_body)
            
            cat = AssessmentQuestionCategory.objects.get(aqcId=cat_id)
            old_name = cat.aqcCatName
            cat.aqcCatName = cat_name
            cat.save()
            
            if old_name != cat_name:
                update_category_name_in_templates(old_name, cat_name, final_tenant_id)
                
            res_body["id"] = cat.aqcId
            res_body["msg"] = "Update Assessment Category Successfully."
            return api_response(200, res_body["msg"], res_body)
            
    except Exception:
        res_body["error"] = "Invalid data"
        return api_response(500, "Error occurred", res_body)

def update_category_name_in_templates(old_name, new_name, tenant_id):
    templates = AssessmentsTemplate.objects.filter(at_client_id=get_client_id_by_tenant_id(tenant_id))
    for t in templates:
        changed = False
        # atData
        if t.at_data:
            orig = t.at_data
            t.at_data = t.at_data.replace(f'"{old_name}"', f'"{new_name}"')
            t.at_data = t.at_data.replace(f'\\"{old_name}\\"', f'\\"{new_name}\\"')
            if orig != t.at_data:
                changed = True
        
        # atHtml
        if t.at_html:
            orig = t.at_html
            t.at_html = t.at_html.replace(f'"{old_name}"', f'"{new_name}"')
            if orig != t.at_html:
                changed = True
            
        # atCategoryPageList
        if t.at_category_page_list:
            orig = t.at_category_page_list
            t.at_category_page_list = t.at_category_page_list.replace(f'"{old_name}"', f'"{new_name}"')
            if orig != t.at_category_page_list:
                changed = True
            
        # atAnalysis
        if t.at_analysis:
            orig = t.at_analysis
            t.at_analysis = t.at_analysis.replace(f'"{old_name}"', f'"{new_name}"')
            if orig != t.at_analysis:
                changed = True
            
        if changed:
            t.save()