import os
import io
import json
import logging
import base64
import uuid
import tempfile
import shutil
from django.conf import settings
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.utils import api_response

from esignature_app.models import Envelope, EnvelopeDocument, EnvelopeRecipient, EnvelopeField, RecipientSignature
from esignature_app.serializers import (
    EnvelopeRecipientSerializer,
    EnvelopeSerializer,
    EnvelopeDocumentSerializer,
    ValidateAccessCodeSerializer,
    UpdateRecipientStatusSerializer,
    SubmitSignedDocumentSerializer,
    AdoptSignatureSerializer
)

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)


def draw_text(can, text, x, y, width, height):
    """
    Draws text onto the PDF overlay canvas at specified coordinates.
    Emulates PdfServiceImpl.drawText logic.
    """
    font_size = max(6.0, min(14.0, height * 0.7))
    can.setFont("Helvetica", font_size)
    text_y = y + (height / 2.0) - (font_size / 3.0)
    can.drawString(x + 2.0, text_y, str(text))


def burn_fields_onto_pdf(envelope):
    """
    Burns/stamps field values, checkboxes, radio selections, and signatures onto the PDF document.
    Emulates PdfServiceImpl.burnFieldsOntoPdf.
    """
    member_id = envelope.member_id
    if not member_id:
        logger.error(f"Envelope {envelope.env_id} has no member_id")
        return

    eas_drive_path = getattr(settings, 'EAS_DRIVE_PATH', '')
    if not eas_drive_path:
        logger.error("EAS_DRIVE_PATH not configured in settings")
        return

    for doc in envelope.documents.all():
        pdf_path = os.path.join(eas_drive_path, str(member_id), "images", "envelopes", doc.file_name)
        pdf_path = os.path.normpath(pdf_path)
        
        if not os.path.exists(pdf_path):
            logger.error(f"PDF file not found: {pdf_path}")
            continue

        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
        except Exception as e:
            logger.error(f"Failed to read PDF: {pdf_path}, error: {e}", exc_info=True)
            continue

        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()
            num_pages = len(reader.pages)
        except Exception as e:
            logger.error(f"Failed to parse PDF: {pdf_path}, error: {e}", exc_info=True)
            continue

        fields = list(doc.fields.all())
        if not fields:
            continue

        for page_idx in range(num_pages):
            page_number = page_idx + 1
            page = reader.pages[page_idx]
            
            page_fields = [f for f in fields if f.page_number == page_number]
            if not page_fields:
                writer.add_page(page)
                continue

            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            # Generate ReportLab overlay page
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))

            for field in page_fields:
                if not field.value:
                    continue
                
                abs_x = float(field.x or 0.0) * page_width
                abs_y_top = float(field.y or 0.0) * page_height
                abs_width = float(field.width or 0.0) * page_width
                abs_height = float(field.height or 0.0) * page_height
                abs_y_bottom = page_height - abs_y_top - abs_height

                field_type = field.field_type or ""
                raw_value = field.value
                signature_image = None

                if raw_value.startswith("{"):
                    try:
                        data_map = json.loads(raw_value)
                        if data_map.get("type") == "image":
                            signature_image = data_map.get("value")
                        elif data_map.get("type") == "text":
                            raw_value = data_map.get("value") or ""
                    except Exception as e:
                        logger.error(f"Failed to parse field JSON: {e}")
                elif raw_value.startswith("data:image"):
                    signature_image = raw_value

                if field_type.lower() in ("signature", "initial"):
                    if raw_value.startswith("{"):
                        try:
                            data_map = json.loads(raw_value)
                            if data_map.get("type") == "image":
                                signature_image = data_map.get("value")
                            elif data_map.get("type") == "text":
                                signature_image = None
                                raw_value = data_map.get("value") or ""
                        except:
                            pass

                    if signature_image and signature_image.startswith("data:image"):
                        try:
                            if "," in signature_image:
                                encoded = signature_image.split(",", 1)[1]
                            else:
                                encoded = signature_image
                            img_bytes = base64.b64decode(encoded)
                            img_io = io.BytesIO(img_bytes)
                            img_reader = ImageReader(img_io)
                            can.drawImage(img_reader, abs_x, abs_y_bottom, width=abs_width, height=abs_height, mask='auto')
                        except Exception as e:
                            logger.error(f"Failed to add image for field {field.field_id}: {e}", exc_info=True)
                            draw_text(can, raw_value, abs_x, abs_y_bottom, abs_width, abs_height)
                    else:
                        draw_text(can, raw_value, abs_x, abs_y_bottom, abs_width, abs_height)

                elif field_type.lower() == "checkbox":
                    if raw_value.lower() == "true":
                        draw_text(can, "X", abs_x, abs_y_bottom, abs_width, abs_height)
                elif field_type.lower() == "radio":
                    if raw_value.lower() == "true":
                        draw_text(can, "O", abs_x, abs_y_bottom, abs_width, abs_height)
                else:
                    draw_text(can, raw_value, abs_x, abs_y_bottom, abs_width, abs_height)

            can.save()
            packet.seek(0)

            # Apply overlay
            try:
                overlay_reader = PdfReader(packet)
                if len(overlay_reader.pages) > 0:
                    page.merge_page(overlay_reader.pages[0])
            except Exception as e:
                logger.error(f"Failed to merge overlay page: {e}", exc_info=True)

            writer.add_page(page)

        # Write safely using temp file
        temp_fd, temp_path = tempfile.mkstemp()
        try:
            with os.fdopen(temp_fd, 'wb') as temp_file:
                writer.write(temp_file)
            shutil.move(temp_path, pdf_path)
            logger.info(f"Successfully burned fields onto PDF: {pdf_path}")
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            logger.error(f"Failed to save stamped PDF to {pdf_path}: {e}", exc_info=True)


def check_and_complete_envelope(envelope):
    """
    Checks if all recipients of the envelope have signed and updates status.
    Emulates RecipientServiceImpl.checkAndCompleteEnvelope.
    """
    recipients = envelope.recipients.all()
    all_signed = all(
        r.status == "SIGNED" or r.action == "RECEIVES_COPY"
        for r in recipients
    )

    if all_signed:
        envelope.env_status = "COMPLETED"
        envelope.save()

        try:
            burn_fields_onto_pdf(envelope)
        except Exception as e:
            logger.error(f"Failed to burn PDF fields: {e}", exc_info=True)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def validateRecipientToken(request, token):
    """
    GET /recipient/validate/{token}
    Replicates RecipientController.validateRecipientToken
    """
    res_body = {"error": ""}
    try:
        try:
            recipient = EnvelopeRecipient.objects.select_related('envelope').get(recipient_token=token)
        except EnvelopeRecipient.DoesNotExist:
            res_body["error"] = "Invalid or expired token"
            return api_response(404, "Invalid or expired token", res_body)

        envelope = recipient.envelope
        requires_access_code = bool(recipient.access_code and recipient.access_code.strip())

        if requires_access_code:
            res_body["requiresAccessCode"] = True
            res_body["recipient"] = EnvelopeRecipientSerializer(recipient).data
        else:
            res_body["requiresAccessCode"] = False
            res_body["recipient"] = EnvelopeRecipientSerializer(recipient).data
            res_body["envelope"] = EnvelopeSerializer(envelope).data
            res_body["documents"] = EnvelopeDocumentSerializer(envelope.documents.all(), many=True).data

        res_body["error"] = ""
        return api_response(200, "Token Validated Successfully", res_body)

    except Exception as e:
        logger.error(f"validateRecipientToken Error: {e}", exc_info=True)
        res_body["error"] = "Internal server error"
        return api_response(500, "Error Processing Request", res_body)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def validateAccessCode(request, token):
    """
    POST /recipient/validate-access-code/{token}
    Replicates RecipientController.validateAccessCode
    """
    res_body = {"error": ""}
    
    serializer = ValidateAccessCodeSerializer(data=request.data)
    if not serializer.is_valid():
        res_body["error"] = f"Invalid payload structure: {serializer.errors}"
        return api_response(400, "Invalid payload structure", res_body)

    access_code = serializer.validated_data["accessCode"]

    try:
        try:
            recipient = EnvelopeRecipient.objects.select_related('envelope').get(recipient_token=token)
        except EnvelopeRecipient.DoesNotExist:
            res_body["error"] = "Invalid or expired token"
            return api_response(404, "Invalid or expired token", res_body)

        if recipient.access_code == access_code:
            envelope = recipient.envelope
            res_body["recipient"] = EnvelopeRecipientSerializer(recipient).data
            res_body["envelope"] = EnvelopeSerializer(envelope).data
            res_body["documents"] = EnvelopeDocumentSerializer(envelope.documents.all(), many=True).data
            res_body["error"] = ""
            return api_response(200, "Access Code Validated Successfully", res_body)
        else:
            res_body["error"] = "Invalid access code"
            return api_response(400, "Invalid access code", res_body)

    except Exception as e:
        logger.error(f"validateAccessCode Error: {e}", exc_info=True)
        res_body["error"] = "Internal server error"
        return api_response(500, "Error Processing Request", res_body)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def updateStatus(request, token):
    """
    POST /recipient/status/{token}
    Replicates RecipientController.updateStatus
    """
    res_body = {"error": ""}
    
    serializer = UpdateRecipientStatusSerializer(data=request.data)
    if not serializer.is_valid():
        res_body["error"] = f"Invalid payload structure: {serializer.errors}"
        return api_response(400, "Invalid payload structure", res_body)

    data = serializer.validated_data

    try:
        try:
            recipient = EnvelopeRecipient.objects.get(recipient_token=token)
        except EnvelopeRecipient.DoesNotExist:
            res_body["error"] = "Invalid token"
            return api_response(400, "Invalid token", res_body)

        recipient.status = data["status"]

        if "country" in data and data["country"] is not None:
            recipient.country = data["country"]
        if "state" in data and data["state"] is not None:
            recipient.state = data["state"]
        if "city" in data and data["city"] is not None:
            recipient.city = data["city"]
        if "ipAddress" in data and data["ipAddress"] is not None:
            recipient.ip_address = data["ipAddress"]
        if "actionTime" in data and data["actionTime"] is not None:
            recipient.action_time = data["actionTime"]

        recipient.save()

        res_body["message"] = "Status updated successfully"
        res_body["error"] = ""
        return api_response(200, "Status Updated Successfully", res_body)

    except Exception as e:
        logger.error(f"updateStatus Error: {e}", exc_info=True)
        res_body["error"] = "Internal server error"
        return api_response(500, "Error Processing Request", res_body)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def submitSignedDocument(request, token):
    """
    POST /recipient/sign/{token}
    Replicates RecipientController.submitSignedDocument
    """
    res_body = {"error": ""}
    
    serializer = SubmitSignedDocumentSerializer(data=request.data)
    if not serializer.is_valid():
        res_body["error"] = f"Invalid payload structure: {serializer.errors}"
        return api_response(400, "Invalid payload structure", res_body)

    data = serializer.validated_data

    try:
        try:
            recipient = EnvelopeRecipient.objects.select_related('envelope').get(recipient_token=token)
        except EnvelopeRecipient.DoesNotExist:
            res_body["error"] = "Invalid token"
            return api_response(400, "Invalid token", res_body)

        with transaction.atomic():
            recipient.status = "SIGNED"

            if "country" in data and data["country"] is not None:
                recipient.country = data["country"]
            if "state" in data and data["state"] is not None:
                recipient.state = data["state"]
            if "city" in data and data["city"] is not None:
                recipient.city = data["city"]
            if "ipAddress" in data and data["ipAddress"] is not None:
                recipient.ip_address = data["ipAddress"]
            if "actionTime" in data and data["actionTime"] is not None:
                recipient.action_time = data["actionTime"]

            recipient.save()

            fields_data = data.get("fields", [])
            if fields_data:
                for f_data in fields_data:
                    field_id = f_data["id"]
                    value = f_data.get("value")

                    try:
                        field = EnvelopeField.objects.get(field_id=field_id)
                    except EnvelopeField.DoesNotExist:
                        continue

                    field.value = value
                    field.save()

                    if value and value.startswith("{"):
                        try:
                            val_map = json.loads(value)
                            if val_map.get("signatureId"):
                                signature_id = val_map["signatureId"]
                                img_data = val_map.get("value", "")
                                signer_name = val_map.get("signerName", recipient.name)

                                RecipientSignature.objects.create(
                                    member_id=recipient.envelope.member_id,
                                    env_id=recipient.envelope.env_id,
                                    recipient_id=recipient.recipient_id,
                                    signature_uuid=signature_id,
                                    signature_type="UNKNOWN",
                                    signature_image=img_data,
                                    signer_name=signer_name
                                )
                        except Exception as ex:
                            logger.error(f"Failed to parse field JSON for signature extraction: {ex}")

            check_and_complete_envelope(recipient.envelope)

        res_body["message"] = "Document submitted successfully"
        res_body["error"] = ""
        return api_response(200, "Document Submitted Successfully", res_body)

    except Exception as e:
        logger.error(f"submitSignedDocument Error: {e}", exc_info=True)
        res_body["error"] = "Internal server error"
        return api_response(500, "Error Processing Request", res_body)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def adoptSignature(request, token):
    """
    POST /recipient/signature/adopt/{token}
    Replicates RecipientController.adoptSignature
    """
    res_body = {"error": ""}
    
    serializer = AdoptSignatureSerializer(data=request.data)
    if not serializer.is_valid():
        res_body["error"] = f"Invalid payload structure: {serializer.errors}"
        return api_response(400, "Invalid payload structure", res_body)

    data = serializer.validated_data

    try:
        try:
            recipient = EnvelopeRecipient.objects.select_related('envelope').get(recipient_token=token)
        except EnvelopeRecipient.DoesNotExist:
            res_body["error"] = "Invalid token"
            return api_response(400, "Invalid token", res_body)

        signature_id = data.get("signatureId")
        if not signature_id:
            signature_id = str(uuid.uuid4())

        signature_type = data.get("type") or "UNKNOWN"
        signature_image = data.get("image") or ""
        signer_name = data.get("name") or recipient.name

        RecipientSignature.objects.create(
            member_id=recipient.envelope.member_id,
            env_id=recipient.envelope.env_id,
            recipient_id=recipient.recipient_id,
            signature_uuid=signature_id,
            signature_type=signature_type,
            signature_image=signature_image,
            signer_name=signer_name
        )

        res_body["signatureId"] = signature_id
        res_body["signerName"] = signer_name
        res_body["message"] = "Signature adopted successfully"
        res_body["error"] = ""
        return api_response(200, "Signature Adopted Successfully", res_body)

    except Exception as e:
        logger.error(f"adoptSignature Error: {e}", exc_info=True)
        res_body["error"] = "Internal server error"
        return api_response(500, "Error Processing Request", res_body)
