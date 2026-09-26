from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from assessment_app.models import AssessmentGroups, Assessments
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
from django.utils import timezone

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getAssessmentGroupsList(request):
    res_body = dict()
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        groups = AssessmentGroups.objects.filter(agClientId=get_client_id_by_tenant_id(final_tenant_id)).order_by('agId')
        
        group_list = []
        for gp in groups:
            group_list.append({
                "groupId": gp.agId,
                "groupName": gp.agGroupName,
            })
            
        res_body["assessmentGroupsList"] = group_list
        return api_response(200, "Fetch Assessment Groups Successfully.", res_body)
    except Exception:
        return api_response(500, "Error occurred", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteAssessmentGroups(request):
    res_body = {"error": ""}
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        group_ids = request.data.get('groupId', [])
        for g_id in group_ids:
            ass_count = Assessments.objects.filter(assClientId=get_client_id_by_tenant_id(final_tenant_id), assGroupId=g_id).count()
            if ass_count > 0:
                res_body["error"] = "This Group Is Not Deleted Because There Are Assessment Available."
                return api_response(500, res_body["error"], res_body)
            else:
                AssessmentGroups.objects.filter(agId=g_id, agClientId=get_client_id_by_tenant_id(final_tenant_id)).delete()
                
        return api_response(200, "Assessment Group Deleted Successfully.", res_body)
    except Exception:
        res_body["error"] = "Data Not Found"
        return api_response(500, res_body["error"], res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveAssessmentGroups(request):
    res_body = dict()
    res_body["error"] = ""
    res_body["msg"] = ""
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        
        data = request.data
        group_id = data.get('groupId', 0)
        group_name = data.get('groupName', '')
        
        if group_id == 0:
            existing = AssessmentGroups.objects.filter(agGroupName=group_name, agClientId=get_client_id_by_tenant_id(final_tenant_id)).first()
            if existing:
                res_body["msg"] = "Assessment Group Name Already In Used."
                res_body["error"] = "error"
                return api_response(500, res_body["msg"], res_body)
            
            new_group = AssessmentGroups.objects.create(
                agGroupName=group_name,
                agClientId=get_client_id_by_tenant_id(final_tenant_id),
                agDateRegistered=timezone.now()
            )
            res_body["groupId"] = new_group.agId
            res_body["msg"] = "Add Assessment Group Successfully."
            return api_response(200, res_body["msg"], res_body)
        else:
            existing_other = AssessmentGroups.objects.filter(agGroupName=group_name, agClientId=get_client_id_by_tenant_id(final_tenant_id)).exclude(agId=group_id).first()
            if existing_other:
                res_body["msg"] = "Assessment Group Name Already In Used."
                res_body["error"] = "error"
                return api_response(500, res_body["msg"], res_body)
                
            group = AssessmentGroups.objects.get(agId=group_id, agClientId=get_client_id_by_tenant_id(final_tenant_id))
            group.agGroupName = group_name
            group.agDateRegistered = timezone.now()
            group.save()
            
            res_body["groupId"] = group.agId
            res_body["msg"] = "Update Assessment Group Successfully."
            return api_response(200, res_body["msg"], res_body)
            
    except Exception:
        res_body["error"] = "invalid"
        return api_response(500, "Error occurred", res_body)
