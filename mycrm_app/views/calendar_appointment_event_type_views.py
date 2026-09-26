import logging
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.core.paginator import Paginator
from common_app.models import CalendarAppointmentEventType
from common_app.utils import api_response, get_final_tenant_id, get_client_id_by_tenant_id
from common_app.decrypt_string import DecryptString
from mycrm_app.serializers import (CalendarAppointmentEventTypeSerializer, DeleteCalendarAppointmentEventTypeDtoSerializer)

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_event_type_list(request):
    res_body = dict()
    try:
        member_id = get_final_tenant_id(request=request)
        search_key = request.GET.get('searchKey')
        page = int(request.GET.get('page', 0))
        size = int(request.GET.get('size', 10))
        
        queryset = CalendarAppointmentEventType.objects.filter(aetMemberId=get_client_id_by_tenant_id(member_id))
        if search_key:
            queryset = queryset.filter(aetTitle__icontains=search_key)
        
        queryset = queryset.order_by('-aetId')
        paginator = Paginator(queryset, size)
        page_obj = paginator.get_page(page + 1)
        
        serializer = CalendarAppointmentEventTypeSerializer(page_obj.object_list, many=True)
        event_type_lists = []
        for event_type in serializer.data:
            new_event_type = dict(event_type)
            if new_event_type['aetDurationHours']:
                new_event_type['aetDurationHours'] = new_event_type['aetDurationHours'] if new_event_type['aetDurationHours'] > 9 else f"0{new_event_type['aetDurationHours']}"
            event_type_lists.append(new_event_type)

        res_body['getTotalPages'] = paginator.num_pages
        res_body['getNumber'] = page
        res_body['getSize'] = size
        res_body['eventTypeList'] = event_type_lists
        res_body['totalEventType'] = paginator.count
        
        return api_response(200, "Fetch Event Type Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetEventTypeList Error : {e}")
        return api_response(500, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_event_type(request, aetId):
    res_body = dict()
    try:
        member_id = get_final_tenant_id(request=request)
        event_type = CalendarAppointmentEventType.objects.get(aetMemberId=get_client_id_by_tenant_id(member_id), aetId=aetId)
        serializer = CalendarAppointmentEventTypeSerializer(event_type)
        res_body['eventTypeList'] = serializer.data
        return api_response(200, "Fetch Event Type Successfully.", res_body)
    except Exception as e:
        logger.error(f"GetEventType Error : {e}")
        return api_response(500, "Internal Server Error", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def delete_event_type(request):
    res_body = dict()
    try:
        serializer = DeleteCalendarAppointmentEventTypeDtoSerializer(data=request.data)
        if serializer.is_valid():
            aet_ids = serializer.validated_data['aetId']
            CalendarAppointmentEventType.objects.filter(aetId__in=aet_ids).delete()
            return api_response(200, "Event Type Deleted Successfully.", res_body)
        else:
            return api_response(400, "Bad Request", res_body)
    except Exception as e:
        logger.error(f"DeleteEvent Error : {e}")
        return api_response(500, "Internal Server Error", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def save_event_type(request):
    res_body = {"error": ""}
    try:
        member_id = get_final_tenant_id(request=request)
        data = request.data
        aet_id = data.get('aetId', 0)
        
        if aet_id == 0:
            event_type = CalendarAppointmentEventType(
                aetTitle=data.get('aetTitle'),
                aetDescription=data.get('aetDescription'),
                aetDurationMinutes=data.get('aetDurationMinutes'),
                aetDurationHours=data.get('aetDurationHours'),
                aetMemberId=get_client_id_by_tenant_id(member_id),
                aetDateTime=timezone.now()
            )
            success_msg = "Add Event Type Successfully"
        else:
            event_type = CalendarAppointmentEventType.objects.get(aetId=aet_id)
            event_type.aetTitle = data.get('aetTitle')
            event_type.aetDescription = data.get('aetDescription')
            event_type.aetDurationMinutes = data.get('aetDurationMinutes')
            event_type.aetDurationHours = data.get('aetDurationHours')
            event_type.aetDateTime = timezone.now()
            success_msg = "Update Event Type Successfully"
        
        event_type.save()
        return api_response(200, success_msg, res_body)
    except Exception as e:
        res_body['error'] = "error"
        logger.error(f"SaveEventType Error : {e}")
        return api_response(500, "Internal Server Error", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_event_type_all_list(request, memId):
    res_body = dict()
    try:
        member_id_str = DecryptString.set_enc_dec_user(memId, "display", "Y")
        if not (member_id_str and str(member_id_str).isdigit()) and memId.endswith('/'):
            member_id_str = DecryptString.set_enc_dec_user(memId.rstrip('/'), "display", "Y")
        if member_id_str and str(member_id_str).isdigit():
            member_id = int(member_id_str)
            event_types = CalendarAppointmentEventType.objects.filter(aetMemberId=get_client_id_by_tenant_id(member_id)).order_by('aetTitle')
            serializer = CalendarAppointmentEventTypeSerializer(event_types, many=True)
            res_body['eventTypeList'] = serializer.data
            return api_response(200, "Fetch Event Type Successfully.", res_body)
        else:
            return api_response(400, "Invalid ID")
    except Exception as e:
        logger.error(f"GetEventTypeAllList Error : {e}")
        return api_response(500, "Internal Server Error", res_body)
