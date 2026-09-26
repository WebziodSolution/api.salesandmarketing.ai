from rest_framework.decorators import api_view
from rest_framework.request import Request
from common_app.utils import api_response, get_final_tenant_id
from auth_app.models import Tenants, TenantDetails
from common_app.models import AffiliateProgram, AffiliateCommissionSchedule
from profile_app.serializers import AffiliateProgramDto, AffiliateCommissionScheduleDto
from common_app.decrypt_string import DecryptString
from django.core.paginator import Paginator
import logging

@api_view(['GET', 'POST'])
def getAffiliateProgramListPage(request: Request):
    try:
        tenant_id = get_final_tenant_id(request=request)

        search_key = request.GET.get('searchKey', '')
        page_number = int(request.GET.get('page', 0))
        page_size = int(request.GET.get('size', 10))

        queryset = AffiliateProgram.objects.all().order_by('-aff_pid')
        
        if search_key:
            queryset = queryset.filter(aff_ptitle__icontains=search_key)

        paginator = Paginator(queryset, page_size)
        
        try:
            page_obj = paginator.page(page_number + 1)
        except Exception:
            page_obj = paginator.page(paginator.num_pages)
            
        content = []
        for program in page_obj:
            ap_date = ""
            if program.aff_pcommission_end_date:
                ap_date = program.aff_pcommission_end_date.strftime("%m/%d/%Y %H:%M:%S")
            ap_code_raw = f"{tenant_id}~{program.aff_pcode}"
            ap_code = DecryptString.set_enc_dec_user(ap_code_raw, "", "Y")
            
            serializer = AffiliateProgramDto(program, context={'apDate': ap_date, 'apCode': ap_code})
            content.append(serializer.data)

        total_affiliate_program = AffiliateProgram.objects.count()

        resBody = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page_obj.number - 1,
            "getSize": page_size,
            "affiliateProgram": content,
            "totalAffiliateProgram": total_affiliate_program
        }
        return api_response(200, "Affiliate Program Fetched Successfully", resBody)
    except Exception as e:
        logging.error(f"GetAffiliateProgramListPage : {e}")
        return api_response(500, "Error Processing Request", {})

@api_view(['GET'])
def setAgreeAffiliateProgram(request):
    try:
        tenant_id = get_final_tenant_id(request=request)
        try:
            tenant_details = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        except TenantDetails.DoesNotExist:
            return api_response(404, "Tenant Not Found", {})

        tenant_details.td_agree_affiliate_program = "Y"
        tenant_details.save()

        resBody = {"error": "", "message": "Affiliate Program Agreement Set Successfully"}
        return api_response(200, "Affiliate Program Agreement Set Successfully", resBody)
    except Exception as e:
        logging.error(f"SetAgreeAffiliateProgram : {e}")
        resBody = {"error": "error"}
        return api_response(500, "Error Processing Request", resBody)

@api_view(['GET'])
def getAffiliateCommissionSchedulePage(request: Request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)

        search_key = request.GET.get('searchKey', '')
        page_number = int(request.GET.get('page', 0))
        page_size = int(request.GET.get('size', 10))
        

        queryset = AffiliateCommissionSchedule.objects.filter(aff_c_tenant_id=final_tenant_id).order_by('-aff_cid')

        if search_key:
            queryset = queryset.filter(aff_title__icontains=search_key)
            
        paginator = Paginator(queryset, page_size)
        try:
            page_obj = paginator.page(page_number + 1)
        except Exception:
            page_obj = paginator.page(paginator.num_pages)
            
        pending_commission = 0.0
        commission = 0.0
        content = []
        for schedule in page_obj:
            if schedule.aff_status == "Pending":
                pending_commission += float(schedule.aff_commission_amount) if schedule.aff_commission_amount else 0.0
            if schedule.aff_status == "Done":
                commission += float(schedule.aff_commission_amount) if schedule.aff_commission_amount else 0.0
                
            invoice_date_str = ""
            if schedule.aff_c_invoice_date:
                invoice_date_str = schedule.aff_c_invoice_date.strftime("%m/%d/%Y %H:%M:%S")
                
            to_tenant_name = ""
            if schedule.aff_c_tenant_id:
                try:
                    tenant = Tenants.objects.get(ten_id=final_tenant_id)
                    fname = tenant.ten_first_name if tenant.ten_first_name else ""
                    lname = tenant.ten_last_name if tenant.ten_last_name else ""
                    to_tenant_name = f"{fname} {lname}".strip()
                except Tenants.DoesNotExist:
                    pass

            serializer = AffiliateCommissionScheduleDto(schedule, context={'invoiceDateStr': invoice_date_str, 'toMemberName': to_tenant_name})
            content.append(serializer.data)

        total_count = AffiliateCommissionSchedule.objects.filter(aff_c_referred_tenant_id=final_tenant_id).count()

        resBody = {
            "getTotalPages": paginator.num_pages,
            "getNumber": page_obj.number - 1,
            "getSize": page_size,
            "affiliateCommissionSchedule": content,
            "pendingCommission": pending_commission,
            "commission": commission,
            "totalAffiliateCommissionSchedule": total_count
        }
        
        return api_response(200, "Affiliate Commission Schedule Fetched Successfully", resBody)
    except Exception as e:
        logging.error(f"GetAffiliateCommissionSchedulePage : {e}")
        return api_response(500, "Error Processing Request", {})

