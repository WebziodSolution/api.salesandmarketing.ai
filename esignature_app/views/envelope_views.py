import logging
import uuid
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.utils import api_response, get_final_member_id

from esignature_app.models import Envelope, EnvelopeDocument, EnvelopeRecipient, EnvelopeField
from esignature_app.serializers import (
    EnvelopeDtoSerializer,
    EnvelopeSerializer
)

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def createEnvelope(request):
    """
    POST /envelope/create
    Replicates EnvelopeServiceImpl.createEnvelope
    """
    final_member_id = get_final_member_id(request=request)
    res_body = {"error": "", "message": ""}
    
    if not final_member_id:
        res_body["error"] = "Member Id Is Required"
        return api_response(500, "Error Processing Request", res_body)

    dto_serializer = EnvelopeDtoSerializer(data=request.data)
    if not dto_serializer.is_valid():
        res_body["error"] = f"Invalid payload structure: {dto_serializer.errors}"
        return api_response(400, "Invalid payload structure", res_body)

    try:
        dto = dto_serializer.validated_data
        envelope_details = dto['envelopeDetails']
        email_content = dto['emailContent']

        with transaction.atomic():
            # 1. Save Envelope
            envelope = Envelope.objects.create(
                env_title=envelope_details['title'],
                env_description=envelope_details.get('description'),
                env_type=envelope_details['type'],
                env_status="DRAFT", # Initial status
                email_subject=email_content['subject'],
                email_message=email_content.get('message'),
                member_id=final_member_id,
                env_uuid=str(uuid.uuid4())
            )

            # 2. Save Recipients
            recipients = dto.get('recipients', [])
            for i, r_dto in enumerate(recipients):
                EnvelopeRecipient.objects.create(
                    envelope=envelope,
                    name=r_dto['name'],
                    email=r_dto['email'],
                    action=r_dto['action'],
                    routing_order=i + 1,
                    status="CREATED",
                    color=r_dto.get('color'),
                    access_code=r_dto.get('access_code'),
                    private_message=r_dto.get('private_message'),
                    recipient_token=str(uuid.uuid4())
                )

            # 3. Save Documents and Fields
            documents = dto.get('documents', [])
            for doc_dto in documents:
                document = EnvelopeDocument.objects.create(
                    envelope=envelope,
                    file_name=doc_dto['fileName'],
                    file_index=doc_dto['fileIndex'],
                    file_url=doc_dto['url']
                )

                # 4. Save Fields
                fields = doc_dto.get('fields', [])
                for f_dto in fields:
                    EnvelopeField.objects.create(
                        document=document,
                        recipient_index=f_dto['recipientIndex'],
                        field_type=f_dto['type'],
                        page_number=f_dto['pageNumber'],
                        x=f_dto['x'],
                        y=f_dto['y'],
                        width=f_dto['width'],
                        height=f_dto['height'],
                        required=f_dto['required'],
                        value=f_dto.get('value')
                    )

            res_body = {
                "envelopeId": envelope.env_id,
                "envelopeUuid": envelope.env_uuid,
                "message": "Envelope created successfully",
                "error": ""
            }
            return api_response(200, "Envelope Created Successfully.", res_body)

    except Exception as e:
        logger.error(f"CreateEnvelope Error : {e}", exc_info=True)
        res_body = {
            "error": f"Internal server error: {str(e)}"
        }
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEnvelopes(request):
    """
    GET /envelope/list
    Replicates EnvelopeServiceImpl.getAllEnvelopes
    """
    final_member_id = get_final_member_id(request=request)
    res_body = {
        "content": [],
        "totalPages": 0,
        "totalElements": 0,
        "error": ""
    }

    if not final_member_id:
        res_body["error"] = "Member Id Is Required"
        return api_response(500, "Error Processing Request", res_body)

    try:
        page = int(request.query_params.get('page', 0))
        size = int(request.query_params.get('size', 10))
        search = request.query_params.get('search')

        # Django Paginator is 1-indexed, Spring Boot page is 0-indexed
        page_number = page + 1

        query = Q(member_id=final_member_id)
        if search:
            query &= (Q(env_title__icontains=search) | Q(env_description__icontains=search))

        envelopes_qs = Envelope.objects.filter(query).prefetch_related(
            'recipients',
            'documents__fields'
        ).order_by('env_id')

        paginator = Paginator(envelopes_qs, size)

        # Handle out of bounds pages gracefully like Spring Data JPA Page behaviour
        try:
            page_obj = paginator.page(page_number)
            content_list = page_obj.object_list
        except Exception:
            content_list = []

        serializer = EnvelopeSerializer(content_list, many=True)

        res_body = {
            "content": serializer.data,
            "totalPages": paginator.num_pages,
            "totalElements": paginator.count,
            "error": ""
        }
        return api_response(200, "Envelopes Fetched Successfully.", res_body)

    except Exception as e:
        logger.error(f"GetEnvelopes Error : {e}", exc_info=True)
        res_body["error"] = str(e)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getEnvelopeById(request, id):
    """
    GET /envelope/{id}
    Replicates EnvelopeServiceImpl.getEnvelopeById
    """
    res_body = {"error": ""}
    try:
        try:
            envelope = Envelope.objects.prefetch_related(
                'recipients',
                'documents__fields'
            ).get(env_id=id)
        except Envelope.DoesNotExist:
            res_body["error"] = "Not Found"
            return api_response(500, "Not Found", res_body)

        serializer = EnvelopeSerializer(envelope)
        res_body = {
            "envelope": serializer.data,
            "error": ""
        }
        return api_response(200, "Envelope Fetched Successfully.", res_body)

    except Exception as e:
        logger.error(f"GetEnvelopeById Error : {e}", exc_info=True)
        res_body["error"] = str(e)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def deleteEnvelopes(request):
    """
    POST /envelope/delete
    Replicates EnvelopeServiceImpl.deleteEnvelopes
    """
    final_member_id = get_final_member_id(request=request)
    res_body = {"error": "", "message": ""}

    if not final_member_id:
        res_body["error"] = "Member Id Is Required"
        return api_response(500, "Error Processing Request", res_body)

    ids = request.data.get('ids')
    if ids is None or not isinstance(ids, list) or len(ids) == 0:
        res_body["error"] = "No IDs provided"
        return api_response(400, "No IDs provided", res_body)

    try:
        with transaction.atomic():
            Envelope.objects.filter(member_id=final_member_id, env_id__in=ids).delete()

        res_body = {
            "error": "",
            "message": "Deleted successfully"
        }
        return api_response(200, "Envelopes Deleted Successfully.", res_body)

    except Exception as e:
        logger.error(f"DeleteEnvelopes Error : {e}", exc_info=True)
        res_body = {
            "error": str(e)
        }
        return api_response(500, "Error Processing Request", res_body)
