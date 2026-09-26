import base64
import logging
import os
import shutil
from datetime import datetime, date
from django.conf import settings
from django.db import connection, models
from django.db.models import Q, F
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response, get_final_tenant_id, set_file_permissions
from profile_app.models import Todos, TodoAttachments, TodosPriority
from profile_app.serializers import TodoSerializer, TodoAttachmentSerializer, TodoPrioritySerializer


logger = logging.getLogger(__name__)


def _parse_due_date(date_val):
    if not date_val:
        return None
    if isinstance(date_val, (datetime, date)):
        return date_val
    date_str = str(date_val).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    try:
        # Fallback to dateutil if available or ISO format split
        return datetime.fromisoformat(date_str).date()
    except Exception:
        return None


@api_view(['POST'])
def saveTodo(request: Request):
    """
    Create or update a Todo item.
    TEN_ID is retrieved via get_final_tenant_id(request=request).
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        data = request.data
        todo_id = data.get('id') or data.get('todoId') or 0
        task = data.get('task')
        description = data.get('description', '')
        due_date_raw = data.get('dueDate') or data.get('due_date')
        status = data.get('status', 'Not Started')

        if not task:
            return api_response(400, "Task is required", res_body)

        if len(str(task)) > 50:
            return api_response(400, "Task cannot exceed 50 characters", res_body)

        if not due_date_raw:
            return api_response(400, "Due Date is required", res_body)

        due_date = _parse_due_date(due_date_raw)
        if not due_date:
            return api_response(400, "Invalid Due Date format. Use YYYY-MM-DD", res_body)

        is_today_raw = data.get('isToday') if 'isToday' in data else data.get('is_today')
        type_val = data.get('type')

        if todo_id and int(todo_id) > 0:
            todo = Todos.objects.filter(id=int(todo_id), tenant_id=tenant_id).first()
            if not todo:
                return api_response(404, "Todo Not Found", res_body)

            todo.task = task
            if description is not None:
                todo.description = description
            todo.due_date = due_date
            if status:
                todo.status = status
            if is_today_raw is not None:
                if isinstance(is_today_raw, str):
                    todo.is_today = is_today_raw.strip().lower() in ('true', '1', 't', 'y', 'yes')
                else:
                    todo.is_today = bool(is_today_raw)
            if 'type' in data:
                todo.type = type_val
            todo.save()
            msg = "Todo Updated Successfully"
        else:
            is_today = False
            if is_today_raw is not None:
                if isinstance(is_today_raw, str):
                    is_today = is_today_raw.strip().lower() in ('true', '1', 't', 'y', 'yes')
                else:
                    is_today = bool(is_today_raw)

            todo = Todos(
                tenant_id=tenant_id,
                task=task,
                description=description,
                due_date=due_date,
                status=status or 'Not Started',
                is_today=is_today,
                type=type_val or '',
                created_at=timezone.now()
            )
            todo.save()
            msg = "Todo Created Successfully"

        res_body['todo'] = TodoSerializer(todo).data
        return api_response(200, msg, res_body)

    except Exception as e:
        logger.error(f"SaveTodo Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
def getTodoList(request: Request):
    """
    Get list of todos for the authenticated tenant.
    Supports optional filtering by status, isToday, and search keyword.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        todos_qs = Todos.objects.filter(tenant_id=tenant_id).prefetch_related('attachments', 'priority_records')

        status = request.GET.get('status')
        if status:
            todos_qs = todos_qs.filter(status__iexact=status)

        is_today_filter = request.GET.get('isToday') if 'isToday' in request.GET else request.GET.get('is_today')
        is_today_bool = False
        if is_today_filter is not None and is_today_filter != '':
            is_today_bool = str(is_today_filter).strip().lower() in ('true', '1', 't', 'y', 'yes')
            todos_qs = todos_qs.filter(is_today=is_today_bool)

        search = request.GET.get('search')
        if search:
            todos_qs = todos_qs.filter(
                Q(task__icontains=search) | Q(description__icontains=search)
            )

        if is_today_bool:
            # Order by PRIORITY_INDEX (e.g. 1, 2, 4...)
            todos_qs = todos_qs.order_by(F('priority_records__priority_index').asc(nulls_last=True), '-id')
        else:
            todos_qs = todos_qs.order_by('-id')

        todos_data = TodoSerializer(todos_qs, many=True).data
        res_body['todos'] = todos_data
        return api_response(200, "Fetch Todos Successfully", res_body)


    except Exception as e:
        logger.error(f"GetTodoList Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)



@api_view(['GET'])
def getTodoById(request: Request, todoId=None):
    """
    Get a single todo by ID. Supports ID from path parameter or query string.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        target_id = todoId or request.GET.get('todoId') or request.GET.get('id')
        if not target_id:
            return api_response(400, "Todo ID is required", res_body)

        todo = Todos.objects.filter(id=int(target_id), tenant_id=tenant_id).prefetch_related('attachments', 'priority_records').first()
        if not todo:
            return api_response(404, "Todo Not Found", res_body)

        res_body['todo'] = TodoSerializer(todo).data
        return api_response(200, "Fetch Todo Successfully", res_body)

    except Exception as e:
        logger.error(f"GetTodoById Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['POST', 'PUT'])
def updateTodoStatus(request: Request):
    """
    Quick status update for a Todo.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        data = request.data
        todo_id = data.get('todoId') or data.get('id')
        status = data.get('status')

        if not todo_id:
            return api_response(400, "Todo ID is required", res_body)

        if not status:
            return api_response(400, "Status is required", res_body)

        todo = Todos.objects.filter(id=int(todo_id), tenant_id=tenant_id).first()
        if not todo:
            return api_response(404, "Todo Not Found", res_body)

        todo.status = status
        todo.save()

        res_body['todo'] = TodoSerializer(todo).data
        return api_response(200, "Todo Status Updated Successfully", res_body)

    except Exception as e:
        logger.error(f"UpdateTodoStatus Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['DELETE', 'POST'])
def deleteTodo(request: Request, todoId=None):
    """
    Delete a todo and its associated attachments (both files on disk and DB records).
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        target_id = todoId or request.data.get('todoId') or request.data.get('id') or request.GET.get('todoId')
        if not target_id:
            return api_response(400, "Todo ID is required", res_body)

        todo = Todos.objects.filter(id=int(target_id), tenant_id=tenant_id).first()
        if not todo:
            return api_response(404, "Todo Not Found", res_body)

        # Remove attachments directory on disk if it exists
        base_dir = getattr(settings, 'FILE_UPLOAD_DIR', getattr(settings, 'FILE_DIRECTORY', os.path.join(settings.BASE_DIR, 'uploads')))
        todo_attachments_dir = os.path.join(base_dir, str(tenant_id), 'todos', str(todo.id))
        if os.path.exists(todo_attachments_dir):
            try:
                shutil.rmtree(todo_attachments_dir)
            except Exception as ex:
                logger.warning(f"Could not remove attachments directory {todo_attachments_dir}: {ex}")

        # Delete attachment records
        TodoAttachments.objects.filter(todo_id=todo.id, tenant_id=tenant_id).delete()
        # Delete todo
        todo.delete()

        return api_response(200, "Todo Deleted Successfully", res_body)

    except Exception as e:
        logger.error(f"DeleteTodo Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['POST'])
def uploadTodoAttachment(request: Request):
    """
    Upload one or multiple file attachments for a Todo.
    Supports:
    - Multiple files in multipart form-data via 'file', 'files', 'attachment', or 'attachments' keys
    - Base64 encoded file(s) in JSON via 'file' or 'files'
    Path stored into TODOS_ATTACHMENTS table is:
    {image_context_path}usercontent/{tenant_id}/todos/{todo_id}/attachments/{todo_attachment_id}/{file_name}
    """
    tenant_id = 0
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        data = request.data
        todo_id = data.get('todoId') or data.get('todo_id')
        if not todo_id:
            return api_response(400, "Todo ID is required", res_body)

        todo = Todos.objects.filter(id=int(todo_id), tenant_id=tenant_id).first()
        if not todo:
            return api_response(404, "Todo Not Found", res_body)

        # Collect files to upload
        file_items = []

        # 1. Check multipart files in request.FILES
        for key in ('file', 'files', 'attachment', 'attachments'):
            if key in request.FILES:
                file_items.extend(request.FILES.getlist(key))

        # 2. If no multipart files found, check data (for JSON / base64 payloads)
        if not file_items:
            raw_files = data.get('files') or data.get('attachments')
            if raw_files:
                if isinstance(raw_files, list):
                    for item in raw_files:
                        if isinstance(item, dict):
                            file_items.append(item)
                        elif isinstance(item, str):
                            file_items.append({'file': item})
                elif isinstance(raw_files, (dict, str)):
                    file_items.append(raw_files if isinstance(raw_files, dict) else {'file': raw_files})
            else:
                raw_file = data.get('file')
                if raw_file:
                    if isinstance(raw_file, list):
                        for item in raw_file:
                            file_items.append(item if isinstance(item, dict) else {'file': item})
                    elif isinstance(raw_file, dict):
                        file_items.append(raw_file)
                    elif isinstance(raw_file, str):
                        file_items.append({
                            'file': raw_file,
                            'fileName': data.get('fileName') or data.get('file_name'),
                            'fileType': data.get('fileType') or data.get('file_type')
                        })

        if not file_items:
            return api_response(500, "Request Must Contains File", res_body)

        # Base upload directory and image context path
        base_dir = getattr(settings, 'FILE_UPLOAD_DIR', getattr(settings, 'FILE_DIRECTORY', os.path.join(settings.BASE_DIR, 'uploads')))
        if not base_dir.endswith('/') and not base_dir.endswith('\\'):
            base_dir += '/'

        image_context_path = getattr(settings, 'IMAGE_CONTEXT_PATH', 'https://webapp.salesandmarketing.ai/')
        if not image_context_path.endswith('/'):
            image_context_path += '/'

        saved_attachments = []

        for item in file_items:
            if hasattr(item, 'read'):
                # UploadedFile from request.FILES
                decoded_bytes = item.read()
                file_name = getattr(item, 'name', 'attachment.bin')
            elif isinstance(item, dict):
                # Dict containing base64 string
                file_str = item.get('file', '')
                file_type = item.get('fileType') or item.get('file_type', 'application/octet-stream')
                prefix = f"data:{file_type};base64,"
                file_str = file_str.replace(prefix, "").replace(" ", "")
                if "base64," in file_str:
                    file_str = file_str.split("base64,")[1]
                decoded_bytes = base64.b64decode(file_str)
                file_name = item.get('fileName') or item.get('file_name') or 'attachment.png'
            else:
                continue

            file_name = os.path.basename(str(file_name))[:50]

            # Allocate todo_attachment_id using sequence
            todo_attachment_id = None
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT TODOS_ATTACHMENTS_SEQ.NEXTVAL FROM DUAL")
                    row = cursor.fetchone()
                    if row:
                        todo_attachment_id = row[0]
            except Exception:
                pass

            if not todo_attachment_id:
                max_id = TodoAttachments.objects.all().aggregate(models.Max('id'))['id__max'] or 0
                todo_attachment_id = max_id + 1

            # Disk target directory: uploads/{tenant_id}/todos/{todo_id}/attachments/{todo_attachment_id}/
            target_dir = os.path.join(base_dir, str(tenant_id), 'todos', str(todo_id), 'attachments', str(todo_attachment_id))
            os.makedirs(target_dir, exist_ok=True)

            disk_file_path = os.path.join(target_dir, file_name)
            set_file_permissions(disk_file_path, decoded_bytes)

            file_upload_path = f"{image_context_path}usercontent/{tenant_id}/todos/{todo_id}/attachments/{todo_attachment_id}/{file_name}"

            # Save to TODOS_ATTACHMENTS table
            attachment = TodoAttachments(
                id=todo_attachment_id,
                tenant_id=tenant_id,
                todo_id=int(todo_id),
                file_name=file_name,
                file_path=file_upload_path,
                created_at=timezone.now()
            )
            attachment.save()

            saved_attachments.append(TodoAttachmentSerializer(attachment).data)

        if not saved_attachments:
            return api_response(500, "Failed to process files", res_body)

        res_body["attachments"] = saved_attachments
        if len(saved_attachments) == 1:
            res_body["filePath"] = saved_attachments[0]["filePath"]
            res_body["attachment"] = saved_attachments[0]
        else:
            res_body["filePath"] = [att["filePath"] for att in saved_attachments]
            res_body["attachment"] = saved_attachments[0]

        message = "The Files Uploaded Successfully" if len(saved_attachments) > 1 else "The File Uploaded Successfully"
        return api_response(200, message, res_body)



    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] UploadTodoAttachment Error : {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
def getTodoAttachmentList(request: Request, todoId=None):
    """
    Get list of attachments for a specific todo.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        target_todo_id = todoId or request.GET.get('todoId')
        if not target_todo_id:
            return api_response(400, "Todo ID is required", res_body)

        attachments = TodoAttachments.objects.filter(
            todo_id=int(target_todo_id),
            tenant_id=tenant_id
        ).order_by('-id')

        res_body['attachments'] = TodoAttachmentSerializer(attachments, many=True).data
        return api_response(200, "Fetch Attachments Successfully", res_body)

    except Exception as e:
        logger.error(f"GetTodoAttachmentList Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
def getTodoAttachmentById(request: Request, attachmentId=None):
    """
    Get a single attachment by ID.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        target_id = attachmentId or request.GET.get('attachmentId') or request.GET.get('id')
        if not target_id:
            return api_response(400, "Attachment ID is required", res_body)

        attachment = TodoAttachments.objects.filter(
            id=int(target_id),
            tenant_id=tenant_id
        ).first()

        if not attachment:
            return api_response(404, "Attachment Not Found", res_body)

        res_body['attachment'] = TodoAttachmentSerializer(attachment).data
        return api_response(200, "Fetch Attachment Successfully", res_body)

    except Exception as e:
        logger.error(f"GetTodoAttachmentById Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['DELETE', 'POST'])
def deleteTodoAttachment(request: Request, attachmentId=None):
    """
    Delete a todo attachment record and its file from disk.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        target_id = attachmentId or request.data.get('attachmentId') or request.data.get('id') or request.GET.get('attachmentId')
        if not target_id:
            return api_response(400, "Attachment ID is required", res_body)

        attachment = TodoAttachments.objects.filter(
            id=int(target_id),
            tenant_id=tenant_id
        ).first()

        if not attachment:
            return api_response(404, "Attachment Not Found", res_body)

        # Remove attachment directory on disk
        base_dir = getattr(settings, 'FILE_UPLOAD_DIR', getattr(settings, 'FILE_DIRECTORY', os.path.join(settings.BASE_DIR, 'uploads')))
        target_dir = os.path.join(base_dir, str(tenant_id), 'todos', str(attachment.todo_id), 'attachments', str(attachment.id))
        if os.path.exists(target_dir):
            try:
                shutil.rmtree(target_dir)
            except Exception as ex:
                logger.warning(f"Could not remove attachment folder {target_dir}: {ex}")

        attachment.delete()
        return api_response(200, "Attachment Deleted Successfully", res_body)

    except Exception as e:
        logger.error(f"DeleteTodoAttachment Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


# =========================================================================
# TODOS PRIORITY CRUD
# =========================================================================

@api_view(['POST'])
def saveTodoPriority(request: Request):
    """
    Create or update priority for one or multiple todos.
    Supports single item:
      { "todoId": 1, "priorityIndex": 1 }
    or bulk list:
      [ { "todoId": 1, "priorityIndex": 1 }, { "todoId": 2, "priorityIndex": 2 } ]
    or wrapped:
      { "priorities": [ ... ] }
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        data = request.data
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if 'priorities' in data and isinstance(data['priorities'], list):
                items = data['priorities']
            else:
                items = [data]

        if not items:
            return api_response(400, "Priority data is required", res_body)

        saved_priorities = []
        for item in items:
            todo_id = item.get('todoId') or item.get('todo_id')
            priority_index = item.get('priorityIndex') if 'priorityIndex' in item else item.get('priority_index')

            if not todo_id:
                continue

            todo = Todos.objects.filter(id=int(todo_id), tenant_id=tenant_id).first()
            if not todo:
                continue

            if priority_index is None:
                continue

            priority_obj = TodosPriority.objects.filter(todo_id=todo.id, tenant_id=tenant_id).first()
            if priority_obj:
                priority_obj.priority_index = int(priority_index)
                priority_obj.save()
            else:
                priority_obj = TodosPriority(
                    tenant_id=tenant_id,
                    todo_id=todo.id,
                    priority_index=int(priority_index)
                )
                priority_obj.save()

            saved_priorities.append(TodoPrioritySerializer(priority_obj).data)

        if not saved_priorities:
            return api_response(400, "Invalid Todo ID or priority index", res_body)

        res_body['priorities'] = saved_priorities
        if len(saved_priorities) == 1:
            res_body['priority'] = saved_priorities[0]

        return api_response(200, "Todo Priority Saved Successfully", res_body)

    except Exception as e:
        logger.error(f"SaveTodoPriority Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
def getTodoPriorityById(request: Request, priorityId=None):
    """
    Get a single priority record by its ID.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        target_id = priorityId or request.GET.get('priorityId') or request.GET.get('id')
        if not target_id:
            return api_response(400, "Priority ID is required", res_body)

        priority = TodosPriority.objects.filter(id=int(target_id), tenant_id=tenant_id).first()
        if not priority:
            return api_response(404, "Priority Not Found", res_body)

        res_body['priority'] = TodoPrioritySerializer(priority).data
        return api_response(200, "Fetch Priority Successfully", res_body)

    except Exception as e:
        logger.error(f"GetTodoPriorityById Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


@api_view(['GET'])
def getTodoPriorityByTodoId(request: Request, todoId=None):
    """
    Get the priority record for a specific todo.
    """
    res_body = dict()
    try:
        tenant_id = get_final_tenant_id(request=request)
        if not tenant_id:
            return api_response(401, "Tenant ID not found", res_body)

        target_todo_id = todoId or request.GET.get('todoId')
        if not target_todo_id:
            return api_response(400, "Todo ID is required", res_body)

        priority = TodosPriority.objects.filter(todo_id=int(target_todo_id), tenant_id=tenant_id).first()
        if not priority:
            return api_response(404, "Priority Not Found", res_body)

        res_body['priority'] = TodoPrioritySerializer(priority).data
        return api_response(200, "Fetch Priority Successfully", res_body)

    except Exception as e:
        logger.error(f"GetTodoPriorityByTodoId Error: {e}", exc_info=True)
        return api_response(500, "Error Processing Request", res_body)


