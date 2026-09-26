from rest_framework import serializers
from profile_app.models import SubaccountType, Todos, TodoAttachments, TodosPriority

class SubaccountTypeDtoSerializer(serializers.ModelSerializer):
    styCreatedDate = serializers.DateTimeField(required=False, format="%m-%d-%Y %H:%M:%S")

    class Meta:
        model = SubaccountType
        fields = ['styId', 'styMemberId', 'styName', 'styCreatedDate']

class AffiliateProgramDto(serializers.ModelSerializer):
    apDate = serializers.CharField(required=False, allow_null=True)
    apCode = serializers.CharField(required=False, allow_null=True)

    class Meta:
        from common_app.models import AffiliateProgram
        model = AffiliateProgram
        fields = '__all__'

    def to_representation(self, instance):
        return {
            "affPId": instance.aff_pid,
            "affPTitle": instance.aff_ptitle,
            "affPCommission": float(instance.aff_pcommission) if instance.aff_pcommission else 0.0,
            "affPCommissionType": instance.aff_pcommission_type,
            "affPCode": self.context.get('apCode', ''),
            "affPIsActive": instance.aff_pis_active,
            "affPCommissionEndDate": self.context.get('apDate', '')
        }

class AffiliateCommissionScheduleDto(serializers.ModelSerializer):
    toMemberName = serializers.CharField(required=False, allow_null=True)
    invoiceDateStr = serializers.CharField(required=False, allow_null=True)

    class Meta:
        from common_app.models import AffiliateCommissionSchedule
        model = AffiliateCommissionSchedule
        fields = '__all__'

    def to_representation(self, instance):
        return {
            "affCId": instance.aff_cid,
            "affCPId": instance.aff_cpid,
            "affCMemberId": instance.aff_c_tenant_id,
            "affCReferredMemberId": instance.aff_c_referred_tenant_id,
            "affCInvoiceId": instance.aff_c_invoice_id,
            "affCInvoiceDate": self.context.get('invoiceDateStr', ''),
            "affCommissionAmount": instance.aff_commission_amount if instance.aff_commission_amount else 0.0,
            "affAmountPaid": instance.aff_amount_paid if instance.aff_amount_paid else None,
            "affDatePaid": instance.aff_date_paid.strftime("%m/%d/%Y %H:%M:%S") if instance.aff_date_paid else None,
            "affTitle": instance.aff_title,
            "affCommissionType": instance.aff_commission_type,
            "affPlanId": instance.aff_plan_id,
            "affStatus": instance.aff_status,
            "toMemberName": self.context.get('toMemberName', '')
        }


class TodoAttachmentSerializer(serializers.ModelSerializer):
    tenId = serializers.IntegerField(source='tenant_id', read_only=True)
    todoId = serializers.IntegerField(source='todo_id', read_only=True)
    fileName = serializers.CharField(source='file_name', read_only=True)
    filePath = serializers.CharField(source='file_path', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = TodoAttachments
        fields = ['id', 'tenId', 'todoId', 'fileName', 'filePath', 'createdAt']

    def to_representation(self, instance):
        created_at_val = instance.created_at
        created_at_str = created_at_val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at_val, 'strftime') else (str(created_at_val) if created_at_val else None)
        return {
            "id": instance.id,
            "tenId": instance.tenant_id,
            "todoId": instance.todo_id,
            "fileName": instance.file_name,
            "filePath": instance.file_path or '',
            "createdAt": created_at_str
        }



class TodoSerializer(serializers.ModelSerializer):
    tenId = serializers.IntegerField(source='tenant_id', read_only=True)
    dueDate = serializers.DateField(source='due_date', format="%Y-%m-%d", read_only=True)
    isToday = serializers.BooleanField(source='is_today', required=False, allow_null=True)
    type = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    priorityIndex = serializers.SerializerMethodField(read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M:%S", read_only=True)
    attachments = TodoAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Todos
        fields = ['id', 'tenId', 'task', 'description', 'dueDate', 'status', 'isToday', 'type', 'priorityIndex', 'createdAt', 'attachments']

    def get_priorityIndex(self, instance):
        if hasattr(instance, 'priority_records'):
            pr = instance.priority_records.first()
            return pr.priority_index if pr else None
        return None

    def to_representation(self, instance):
        attachments_qs = instance.attachments.all() if hasattr(instance, 'attachments') else []
        attachments_data = [
            TodoAttachmentSerializer(att).to_representation(att)
            for att in attachments_qs
        ]
        due_date_val = instance.due_date
        due_date_str = due_date_val.strftime("%Y-%m-%d") if hasattr(due_date_val, 'strftime') else (str(due_date_val) if due_date_val else None)
        created_at_val = instance.created_at
        created_at_str = created_at_val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at_val, 'strftime') else (str(created_at_val) if created_at_val else None)

        priority_rec = instance.priority_records.first() if hasattr(instance, 'priority_records') else None
        priority_index = priority_rec.priority_index if priority_rec else None

        return {
            "id": instance.id,
            "tenId": instance.tenant_id,
            "task": instance.task,
            "description": instance.description or "",
            "dueDate": due_date_str,
            "status": instance.status,
            "isToday": bool(instance.is_today) if instance.is_today is not None else False,
            "type": instance.type or "",
            "priorityIndex": priority_index,
            "createdAt": created_at_str,
            "attachments": attachments_data
        }


class TodoPrioritySerializer(serializers.ModelSerializer):
    tenId = serializers.IntegerField(source='tenant_id', read_only=True)
    todoId = serializers.IntegerField(source='todo_id', read_only=True)
    priorityIndex = serializers.IntegerField(source='priority_index')

    class Meta:
        model = TodosPriority
        fields = ['id', 'tenId', 'todoId', 'priorityIndex']

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "tenId": instance.tenant_id,
            "todoId": instance.todo_id,
            "priorityIndex": instance.priority_index
        }


TodosSerializer = TodoSerializer
TodoAttachmentsSerializer = TodoAttachmentSerializer
TodosPrioritySerializer = TodoPrioritySerializer
