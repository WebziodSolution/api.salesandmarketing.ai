from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
from common_app.models import SvQuestionCategory, SurveysTemplate
from survey_app.serializers import SvQuestionCategorySerializer, DeleteSurveyCategorySerializer, SvQuestionCategoryResponseSerializer
from django.db.models import Q
from django.core.paginator import Paginator
import logging

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyCategoryList(request):
    final_member_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        if not final_member_id:
             return api_response(400, "Tenant Id Is Required", res_body)


        categories = SvQuestionCategory.objects.filter(
            Q(member_id__isnull=True) | Q(member_id=0) | Q(member_id=get_client_id_by_tenant_id(final_member_id))
        ).order_by('id')
        
        serializer = SvQuestionCategoryResponseSerializer(categories, many=True)
        res_body['surveyCategoryList'] = serializer.data
        return api_response(200, "Fetch Survey Category Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {final_member_id} ] GetSurveyCategoryList Error : {e}")
        # Match Java's empty result on error
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyCategoryById(request, qc_id):
    final_member_id = get_final_tenant_id(request=request)
    res_body = dict()
    try:
        category = SvQuestionCategory.objects.filter(
            Q(member_id__isnull=True) | Q(member_id=0) | Q(member_id=get_client_id_by_tenant_id(final_member_id)),
            id=qc_id
        ).first()
        
        if category:
            serializer = SvQuestionCategoryResponseSerializer(category)
            res_body['surveyCategory'] = serializer.data
        else:
            res_body['surveyCategory'] = None
            
        return api_response(200, "Fetch Survey Category Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {final_member_id} ] GetSurveyCategoryById Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteSurveyCategory(request):
    res_body = {}
    try:
        serializer = DeleteSurveyCategorySerializer(data=request.data)
        if serializer.is_valid():
            ids = serializer.validated_data['id']
            SvQuestionCategory.objects.filter(id__in=ids).delete()
            return api_response(200, "Survey Category Deleted Successfully.", res_body)
        else:
            return api_response(400, "Invalid ID list", res_body)
    except Exception as e:
        logger.error(f"DeleteSurveyCategory Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSurveyCategoryListPages(request):
    final_member_id = get_final_tenant_id(request=request)
    search_key = request.query_params.get('searchKey')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 10))
    
    res_body = {}
    try:
        query = Q(member_id=get_client_id_by_tenant_id(final_member_id)) | Q(member_id=0)
        if search_key:
            query &= Q(cat_name__icontains=search_key)
            
        categories_list = SvQuestionCategory.objects.filter(query).order_by('id')
        paginator = Paginator(categories_list, size)
        
        # Django Paginator is 1-indexed, Java might be 0-indexed
        current_page = paginator.get_page(page + 1)
        
        serializer = SvQuestionCategorySerializer(current_page.object_list, many=True)
        # In Java implementation, memberId is kept for paginated list but subMemberId is null
        for item in serializer.data:
            item['subMemberId'] = None
            
        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['surveyCategoryList'] = serializer.data
        res_body['totalSurveyCategory'] = paginator.count
        
        return api_response(200, "Fetch Survey Category Successfully.", res_body)
    except Exception as e:
        logger.error(f"[ memberId : {final_member_id} ] GetSurveyCategoryListPages Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveSurveyCategory(request):
    final_member_id = get_final_tenant_id(request=request)
    res_body = dict()
    res_body["error"] = ""
    res_body["msg"] = ""
    try:
        data = request.data
        qc_id = data.get('id', 0)
        cat_name = data.get('catName')
        
        if qc_id == 0:
            existing = SvQuestionCategory.objects.filter(cat_name=cat_name, member_id=get_client_id_by_tenant_id(final_member_id)).first()
            if not existing:
                category = SvQuestionCategory.objects.create(
                    cat_name=cat_name,
                    member_id=get_client_id_by_tenant_id(final_member_id)
                )
                res_body['id'] = category.id
                res_body['msg'] = "Add Survey Category Successfully."
            else:
                res_body['msg'] = "Survey Category Name Already In Used."
                res_body['error'] = "error"
        else:
            existing_with_same_name = SvQuestionCategory.objects.filter(cat_name=cat_name, member_id=get_client_id_by_tenant_id(final_member_id)).exclude(id=qc_id).first()
            if not existing_with_same_name:
                category = SvQuestionCategory.objects.filter(id=qc_id, member_id=get_client_id_by_tenant_id(final_member_id)).first()
                if category:
                    old_cat_name = category.cat_name
                    category.cat_name = cat_name
                    category.save()
                    
                    if old_cat_name != cat_name:
                        update_category_name_in_templates(old_cat_name, cat_name, final_member_id)
                        
                    res_body['id'] = category.id
                    res_body['msg'] = "Update Survey Category Successfully."
                else:
                    res_body['msg'] = "Survey Category Not Found."
                    res_body['error'] = "error"
            else:
                res_body['msg'] = "Survey Category Name Already In Used."
                res_body['error'] = "error"
                
        if res_body['error'] == "":
            return api_response(200, res_body['msg'], res_body)
        elif res_body['error'] == "error":
            return api_response(500, "Error Processing Request", res_body)
        else:
            return api_response(500, res_body['msg'], res_body)
            
    except Exception as e:
        logger.error(f"[ memberId : {final_member_id} ] SaveSurveyCategory Error : {e}")
        return api_response(500, "Error Processing Request", res_body)

def update_category_name_in_templates(old_name, new_name, member_id):
    templates = SurveysTemplate.objects.filter(member_id=get_client_id_by_tenant_id(member_id))
    for template in templates:
        changed = False
        if template.st_data:
            # Replicating Java's replaceAll behavior
            new_st_data = template.st_data.replace(f'"{old_name}"', f' "{new_name}"')
            new_st_data = new_st_data.replace(f'\\"{old_name}\\"', f'\\"{new_name}\\"')
            if new_st_data != template.st_data:
                template.st_data = new_st_data
                changed = True
        
        if template.st_html:
            new_st_html = template.st_html.replace(f'"{old_name}"', f' "{new_name}"')
            if new_st_html != template.st_html:
                template.st_html = new_st_html
                changed = True
                
        if template.st_category_page_list:
            new_st_category_page_list = template.st_category_page_list.replace(f'"{old_name}"', f' "{new_name}"')
            if new_st_category_page_list != template.st_category_page_list:
                template.st_category_page_list = new_st_category_page_list
                changed = True
        
        if changed:
            template.save()
