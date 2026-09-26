from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from django.conf import settings
from django.db import models, transaction
from common_app.models import (
    EasBuildItForMe, EasBuildItForMePackage, EasBuildItForMePackData,
    EasBuildItForMeLog, EasBuildItForMeLogType, MyPages, Invoices
)
from common_app.utils import api_response, get_final_tenant_id, set_file_permissions, get_tenants, \
    get_client_id_by_tenant_id
from common_app.decrypt_string import DecryptString
from common_app.services import commonServices, MailRequestDTO
import os
import base64
from datetime import datetime
import logging
from django.db.models import Max
from api_app.views.payment_gateway_views import get_merchant_auth, get_environment
from authorizenet import apicontractsv1
from authorizenet.apicontrollers import createTransactionController
from django.utils import timezone

logger = logging.getLogger(__name__)

# Constants
ERROR_MSG = "Something went wrong. Please try again later."

def eas_build_it_for_me_to_dto(obj):
    return {
        "bfmId": obj.bfmId,
        "memberId": obj.memberId,
        "bfmProjectName": obj.bfmProjectName,
        "bfmWebsite": obj.bfmWebsite,
        "bfmYourBusiness": obj.bfmYourBusiness,
        "bfmAboutYourCompany": obj.bfmAboutYourCompany,
        "bfmMainGoalWithEt": obj.bfmMainGoalWithEt,
        "bfmWantIncluded": obj.bfmWantIncluded,
        "bfmCommunicateToTeam": obj.bfmCommunicateToTeam,
        "bfmNotWantIncluded": obj.bfmNotWantIncluded,
        "bfmAttachmentFile": obj.bfmAttachmentFile,
        "bfmEmailPackId": obj.bfmEmailPackId,
        "bfmEmailPackAmount": obj.bfmEmailPackAmount,
        "bfmPublishStatus": "DRAFT" if obj.bfmPublishStatus == 0 else "PAID" if obj.bfmPublishStatus == 1 else "ASSIGNED" if obj.bfmPublishStatus == 2 else "APPROVAL" if obj.bfmPublishStatus == 3 else "PUBLISHED" if obj.bfmPublishStatus == 4 else str(obj.bfmPublishStatus),
        "bfmPublishStatusId": obj.bfmPublishStatus,
        "bfmInvoicedId": obj.bfmInvoicedId,
        "bfmCreatedate": obj.bfmCreatedate.strftime("%m/%d/%Y") if obj.bfmCreatedate else None,
        "bfmMpId": obj.bfmMpId,
        "bfmDesignerName": obj.bfmDesignerName,
        "bfmDesignerEmail": obj.bfmDesignerEmail
    }

def my_page_to_dto(obj):
    return {
        "mpId": obj.mpId,
        "mpName": obj.mpName,
        "mpTags": obj.mpTags,
        "mpType": obj.mpType,
        "mpStage": obj.mpStage,
        "groupId": obj.mpGroupId,
        "memberId": obj.mpClientId,
        "mpTemplateLanguage": obj.mpTemplateLanguage,
        "mpTemplateConvertLangList": obj.mpTemplateConvertLangList,
        "mpAllowConvertLang": obj.mpAllowConvertLang,
        "mpBuilditPublish": obj.mpBuilditPublish,
        "mpPublicUrl": obj.mpPublicUrl
    }

def log_to_dto(obj):
    return {
        "blogId": obj.blogId,
        "blogBfmId": obj.blogBfmId,
        "blogBfmProjectName": obj.blogBfmProjectName,
        "blogBfmpdId": obj.blogBfmpdId,
        "blogAction": obj.blogAction,
        "blogBlogtId": obj.blogBlogtId,
        "blogDate": obj.blogDate.strftime("%m/%d/%Y") if obj.blogDate else None,
        "blogNotes": obj.blogNotes
    }

def check_charge_payment_profile(tenant_id, amt, inv_no):
    res_body = {
        "invTransationId": "",
        "invPayCardNo": "",
        "errorCode": "",
        "errorMessage": "",
        "resultCode": "error"
    }
    
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        if not tenant or not tenant.td_authorize_customer_profile_id:
            return res_body

        auth_customer_profile_id = tenant.td_authorize_customer_profile_id
        auth_customer_payment_profile_id = tenant.td_authorize_customer_payment_profile_id
        
        merchant_auth = get_merchant_auth()
        
        profile_to_charge = apicontractsv1.customerProfilePaymentType()
        profile_to_charge.customerProfileId = auth_customer_profile_id
        
        payment_profile = apicontractsv1.paymentProfile()
        payment_profile.paymentProfileId = auth_customer_payment_profile_id
        profile_to_charge.paymentProfile = payment_profile
        
        order_type = apicontractsv1.orderType()
        order_type.invoiceNumber = f"{settings.COMPANY_NAME}-{inv_no}"
        order_type.description = f"{settings.COMPANY_NAME} Transaction On Date : {datetime.now()}"
        
        txn_request = apicontractsv1.transactionRequestType()
        txn_request.transactionType = apicontractsv1.transactionTypeEnum.authCaptureTransaction
        txn_request.profile = profile_to_charge
        txn_request.amount = round(float(amt), 3)
        txn_request.order = order_type
        
        create_request = apicontractsv1.createTransactionRequest()
        create_request.merchantAuthentication = merchant_auth
        create_request.transactionRequest = txn_request
        
        controller = createTransactionController(create_request)
        controller.setenvironment(get_environment())
        controller.execute()
        
        response = controller.getresponse()
        
        if response is not None:
            if response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                result = response.transactionResponse
                if hasattr(result, 'messages') and result.messages is not None:
                    res_body["invTransationId"] = result.transId
                    res_body["invPayCardNo"] = result.accountNumber
                    res_body["resultCode"] = "Ok"
                else:
                    if hasattr(result, 'errors') and result.errors is not None:
                        res_body["errorCode"] = result.errors.error[0].errorCode
                        res_body["errorMessage"] = result.errors.error[0].errorText
            else:
                if hasattr(response, 'transactionResponse') and hasattr(response.transactionResponse, 'errors') and response.transactionResponse.errors:
                    res_body["errorCode"] = response.transactionResponse.errors.error[0].errorCode
                    res_body["errorMessage"] = response.transactionResponse.errors.error[0].errorText
    except Exception as e:
        logger.error(f"[ tenantId : {tenant_id} ] check_charge_payment_profile Error : {str(e)}")
        
    return res_body

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getListOrder(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        orders = EasBuildItForMe.objects.filter(memberId=get_client_id_by_tenant_id(final_tenant_id))
        list_dto = [eas_build_it_for_me_to_dto(obj) for obj in orders]

        return api_response(200, "Fetch Order List Successfully.", {"buildItForMe": list_dto})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetListOrder Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getRequestForApprovalTags(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        tags_column = MyPages.objects.filter(
            mpClientId=get_client_id_by_tenant_id(final_tenant_id),
            mpStage=1,
            mpBuilditPublish='C'
        ).exclude(mpTags__isnull=True).exclude(mpTags='').values_list('mpTags', flat=True)

        tags = []
        if tags_column:
            tag_string = ",".join(tags_column).replace(" ", "").lower()
            tags_list = tag_string.split(",")
            tags = sorted(list(set(filter(None, tags_list))))

        return api_response(200, "Fetch Tags Successfully.", {"requestForApprovalTags": tags})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetRequestForApprovalTags Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getListRequestForApproval(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        list_objs = MyPages.objects.filter(
            mpClientId=get_client_id_by_tenant_id(final_tenant_id),
            mpStage=1,
            mpBuilditPublish='C'
        ).order_by('mpName')

        list_dto = []
        for obj in list_objs:
            temp = my_page_to_dto(obj)
            bfm_id = EasBuildItForMePackData.objects.filter(bfmpdMpId=obj.mpId).values_list('bfmpdBfmId', flat=True).first()
            temp['bfMpdBfmId'] = bfm_id
            temp['encMpId'] = DecryptString.set_enc_dec_user(str(obj.mpId), "", "Y")
            list_dto.append(temp)

        return api_response(200, "Fetch Request For Approval List Successfully.", {"requestForApproval": list_dto})
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] GetListRequestForApproval Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getOrderDetails(request, bfmId):
    try:
        eas_build_it_for_me = EasBuildItForMe.objects.filter(bfmId=bfmId).first()
        if not eas_build_it_for_me:
            return api_response(404, "Order Not Found", {})
            
        dto = eas_build_it_for_me_to_dto(eas_build_it_for_me)
        
        package = EasBuildItForMePackage.objects.filter(bfmpId=eas_build_it_for_me.bfmEmailPackId).first()
        if package:
            dto['packLabel'] = package.bfmpLable
        else:
            dto['packLabel'] = None
            
        temp_id = 0
        bfmpd_ids = EasBuildItForMePackData.objects.filter(bfmpdBfmId=bfmId).values_list('bfmpdId', flat=True)
        if bfmpd_ids:
            temp_id = bfmpd_ids[0]
            
        logs = EasBuildItForMeLog.objects.filter(
            blogBfmId=bfmId,
            blogBlogtId__isnull=False
        ).filter(
            models.Q(blogBfmpdId=temp_id) | models.Q(blogBfmpdId=0)
        ).exclude(blogBlogtId__in=[3, 5])
        
        logs_dto = []
        for log_obj in logs:
            log_dto = log_to_dto(log_obj)
            log_type = EasBuildItForMeLogType.objects.filter(blogtId=log_obj.blogBlogtId).values_list('blogtType', flat=True).first()
            log_dto['blogType'] = log_type if log_type else ""
            logs_dto.append(log_dto)
            
        dto['logs'] = logs_dto
        
        return api_response(200, "Fetch Order Details Successfully.", {"orderDetails": dto})
    except Exception as e:
        logger.error(f"GetOrderDetails Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def approveRequest(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        data = request.data
        mp_id = data.get('mpId')
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": final_tenant_id
                }
            }
        )
        with transaction.atomic():
            pack_data_list = EasBuildItForMePackData.objects.filter(bfmpdMpId=mp_id)
            for pack_data in pack_data_list:
                pack_data.bfmpdMpStatus = 7
                pack_data.save()

            my_page = MyPages.objects.filter(mpId=mp_id).first()
            if my_page:
                my_page.mpStage = 2
                my_page.mpBuilditPublish = "Y"
                my_page.save()

            if pack_data_list:
                bfm_id = pack_data_list[0].bfmpdBfmId
                eas_build_it_for_me = EasBuildItForMe.objects.filter(bfmId=bfm_id).first()
                if eas_build_it_for_me:
                    eas_build_it_for_me.bfmPublishStatus = 4
                    eas_build_it_for_me.save()

                    log = EasBuildItForMeLog()
                    log.blogBfmId = bfm_id
                    log.blogBfmProjectName = eas_build_it_for_me.bfmProjectName
                    log.blogBfmpdId = pack_data_list[0].bfmpdId
                    log.blogBlogtId = 7
                    log.blogDate = datetime.now()
                    log.save()
            res_body = dict()
            res_body["msg"] = "Successfully Published To My Pages"
            user_notified_via_mail = False

            try:
                if tenant:
                    full_name = f"{tenant.ten_first_name} {tenant.ten_last_name}".strip()
                    to_email = tenant.ten_email
                else:
                    full_name = ""
                    to_email = ""

                mail_dto = MailRequestDTO(
                    to=to_email,
                    subject=f"Your template is ready on {settings.SITE_NAME_SMALL_COM}",
                    template_name="approve-template.ftl"
                )

                model = {
                    "FULLNAME": full_name,
                    "SITEURL": settings.SITEURL,
                    "siteName": settings.SITE_NAME,
                    "toAdminSupportEmail": settings.TO_ADMIN_SUPPORT_EMAIL,
                    "siteUrlWWW": settings.SITE_URL_WWW,
                    "siteUrlWWWDisplay": settings.SITE_URL_WWW_DISPLAY,
                    "companyName": settings.COMPANY_NAME,
                    "mainCompanyName": settings.MAIN_COMPANY_NAME,
                    "siteUrlAddress": settings.SITE_URL_ADDRESS,
                    "siteUrlAddressBr": settings.SITE_URL_ADDRESS_BR,
                    "companyNumber": settings.COMPANY_NUMBER,
                    "siteNameSmallCom": settings.SITE_NAME_SMALL_COM,
                    "siteNameBigCom": settings.SITE_NAME_BIG_COM
                }

                resp = commonServices.sendEmail(mail_dto, model)
                user_notified_via_mail = resp.status

                # Admin emails
                if settings.TO_EMAIL_ADMIN_MEMBER_1:
                    mail_dto.to = settings.TO_EMAIL_ADMIN_MEMBER_1
                    commonServices.sendEmail(mail_dto, model)
                if settings.TO_EMAIL_ADMIN_MEMBER_2:
                    mail_dto.to = settings.TO_EMAIL_ADMIN_MEMBER_2
                    commonServices.sendEmail(mail_dto, model)

            except Exception as ex:
                res_body["errorWhileNotify"] = str(ex)

            res_body["userNotifiedViaMail"] = user_notified_via_mail
            return api_response(200, "Successfully Published To My Pages", res_body)

    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] ApproveRequest Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def rejectRequest(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        data = request.data
        mp_id = data.get('mpId')
        note = data.get('note', '')

        with transaction.atomic():
            pack_data_list = EasBuildItForMePackData.objects.filter(bfmpdMpId=mp_id)
            for pack_data in pack_data_list:
                pack_data.bfmpdMpStatus = 6
                pack_data.save()

            my_page = MyPages.objects.filter(mpId=mp_id).first()
            if my_page:
                my_page.mpStage = 1
                my_page.mpBuilditPublish = "N"
                my_page.save()

            if pack_data_list:
                bfm_id = pack_data_list[0].bfmpdBfmId
                eas_build_it_for_me = EasBuildItForMe.objects.filter(bfmId=bfm_id).first()
                if eas_build_it_for_me:
                    eas_build_it_for_me.bfmPublishStatus = 2
                    eas_build_it_for_me.save()

                    log = EasBuildItForMeLog()
                    log.blogBfmId = bfm_id
                    log.blogBfmProjectName = eas_build_it_for_me.bfmProjectName
                    log.blogBfmpdId = pack_data_list[0].bfmpdId
                    log.blogBlogtId = 6
                    log.blogNotes = note
                    log.blogDate = datetime.now()
                    log.save()
                    res_body = dict()
                    res_body["msg"] = "Request Rejected Successfully"
                    designer_notified_via_mail = False

                    try:
                        designer_name = eas_build_it_for_me.bfmDesignerName if eas_build_it_for_me.bfmDesignerName else "Designer"
                        mail_dto = MailRequestDTO(
                            to=eas_build_it_for_me.bfmDesignerEmail,
                            subject="Customer template needs approval",
                            template_name="reject-template.ftl"
                        )

                        model = {
                            "DESIGNERNAME": designer_name,
                            "TEMPLATENAME": eas_build_it_for_me.bfmDesignerName,
                            "SITEURL": settings.SITEURL,
                            "siteName": settings.SITE_NAME,
                            "toAdminSupportEmail": settings.TO_ADMIN_SUPPORT_EMAIL,
                            "siteUrlWWW": settings.SITE_URL_WWW,
                            "siteUrlWWWDisplay": settings.SITE_URL_WWW_DISPLAY,
                            "companyName": settings.COMPANY_NAME,
                            "mainCompanyName": settings.MAIN_COMPANY_NAME,
                            "siteUrlAddress": settings.SITE_URL_ADDRESS,
                            "siteUrlAddressBr": settings.SITE_URL_ADDRESS_BR,
                            "companyNumber": settings.COMPANY_NUMBER,
                            "siteNameSmallCom": settings.SITE_NAME_SMALL_COM,
                            "siteNameBigCom": settings.SITE_NAME_BIG_COM
                        }

                        resp = commonServices.sendEmail(mail_dto, model)
                        designer_notified_via_mail = resp.status

                        if settings.TO_EMAIL_ADMIN_MEMBER_1:
                            mail_dto.to = settings.TO_EMAIL_ADMIN_MEMBER_1
                            commonServices.sendEmail(mail_dto, model)
                        if settings.TO_EMAIL_ADMIN_MEMBER_2:
                            mail_dto.to = settings.TO_EMAIL_ADMIN_MEMBER_2
                            commonServices.sendEmail(mail_dto, model)
                    except Exception as ex:
                        res_body["errorWhileNotify"] = str(ex)

                    res_body["designerNotifiedViaMail"] = designer_notified_via_mail
                    return api_response(200, "Request Rejected Successfully", res_body)

            return api_response(404, "Pack Data Not Found", {})

    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] RejectRequest Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteOrder(request, bfmId):
    try:
        EasBuildItForMe.objects.filter(bfmId=bfmId).delete()
        return api_response(200, "Build It For Me Deleted Successfully", {})
    except Exception as e:
        logger.error(f"DeleteOrder Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def uploadFile(request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        data = request.data
        
        file_base64 = data.get('file', '')
        file_type = data.get('fileType', '')
        file_name = data.get('fileName', '')
        
        if not file_base64:
            return api_response(500, "Request Must Contains File", {})
            
        base_dir = os.path.join(settings.EAS_DRIVE_PATH, str(final_tenant_id))
        images_dir = os.path.join(base_dir, "images")
        bfm_dir = os.path.join(images_dir, "builditforme")
        
        for d in [base_dir, images_dir, bfm_dir]:
            if not os.path.exists(d):
                os.makedirs(d)
                
        # Remove data uri prefix if present
        if f"data:{file_type};base64," in file_base64:
            file_base64 = file_base64.replace(f"data:{file_type};base64,", "")
        file_base64 = file_base64.replace(" ", "")
        
        decoded_bytes = base64.b64decode(file_base64)
        file_path = os.path.join(bfm_dir, file_name)
        
        set_file_permissions(file_path, decoded_bytes)
        
        file_download_uri = f"{settings.IMAGE_SITE_URL}easdrive/{final_tenant_id}/images/builditforme/{file_name}"
        
        return api_response(200, "The File Uploaded Successfully", {"fileDownloadUri": file_download_uri})
    except Exception as e:
        logger.error(f"FileUpload Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def removeFile(request, bfmId, fileName):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        file_path = os.path.join(settings.EAS_DRIVE_PATH, str(final_tenant_id), "images", "builditforme", fileName)
        res_body = {}

        if os.path.exists(file_path):
            os.remove(file_path)
            if bfmId > 0:
                order = EasBuildItForMe.objects.filter(bfmId=bfmId).first()
                if order and order.bfmAttachmentFile:
                    files = order.bfmAttachmentFile.split(",")
                    if fileName in files:
                        files.remove(fileName)
                        order.bfmAttachmentFile = ",".join(files)
                        order.save()
                        res_body[fileName] = "Deleted"
                    else:
                        res_body[fileName] = "Not Found In Records"
            else:
                res_body[fileName] = "Deleted"
        else:
            res_body[fileName] = "File Not Found On Server"

        return api_response(200, "The File Deleted Successfully", res_body)
    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] RemoveFile Error : {str(e)}")
        return api_response(500, "Order Not Found", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveOrder(request):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        data = request.data

        bfm_id = data.get('bfmId', 0)
        pack_id = data.get('bfmEmailPackId')

        package = EasBuildItForMePackage.objects.filter(bfmpId=pack_id).first()
        if not package:
            return api_response(200, "Email Package Not Found", {})

        with transaction.atomic():
            if bfm_id > 0:
                order = EasBuildItForMe.objects.get(bfmId=bfm_id)
            else:
                order = EasBuildItForMe()
                order.bfmCreatedate = datetime.now()

            order.memberId = final_tenant_id
            order.bfmProjectName = data.get('bfmProjectName')
            order.bfmWebsite = data.get('bfmWebsite')
            order.bfmYourBusiness = data.get('bfmYourBusiness')
            order.bfmAboutYourCompany = data.get('bfmAboutYourCompany')
            order.bfmMainGoalWithEt = data.get('bfmMainGoalWithEt')
            order.bfmWantIncluded = data.get('bfmWantIncluded')
            order.bfmCommunicateToTeam = data.get('bfmCommunicateToTeam')
            order.bfmNotWantIncluded = data.get('bfmNotWantIncluded')
            attachment_file = data.get('bfmAttachmentFile', '')
            if attachment_file:
                order.bfmAttachmentFile = attachment_file.strip(',')
            order.bfmEmailPackId = pack_id
            order.bfmEmailPackAmount = str(package.bfmpAmount)
            order.bfmPublishStatus = 0
            order.save()

            msg = "Update Order Successfully" if bfm_id > 0 else "New Order Placed Successfully"
            return api_response(200, msg, {"bfmId": order.bfmId, "message": ""})

    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] SaveOrder Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def placeOrder(request, bfmId):
    final_tenant_id = get_final_tenant_id(request=request)
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": final_tenant_id
                }
            }
        )

        eas_build_it_for_me = EasBuildItForMe.objects.filter(bfmId=bfmId).first()
        if not eas_build_it_for_me:
            return api_response(404, "Order Not Found", {})

        amt = eas_build_it_for_me.bfmEmailPackAmount
        if tenant is not None:
            inv_client_name = f"{tenant.ten_first_name} {tenant.ten_last_name}"
            ten_country = tenant.ten_country
            ten_membership_type = tenant.td_membership_type
        else:
            inv_client_name = ""
            ten_country = 0
            ten_membership_type = ""

        max_inv_no = Invoices.objects.filter(invCountryId=ten_country).aggregate(Max('invNo'))['invNo__max']
        max_inv_no = (max_inv_no or 0) + 1

        # Payment processing
        res_inner_body = {}
        if ten_membership_type == "Free":
            result_code = "Ok"
            inv_transaction_id = ""
            inv_pay_card_no = ""
        else:
            res_inner_body = check_charge_payment_profile(final_tenant_id, amt, max_inv_no)
            result_code = res_inner_body.get('resultCode', 'error')
            inv_transaction_id = res_inner_body.get('invTransationId', '')
            inv_pay_card_no = res_inner_body.get('invPayCardNo', '')

        if result_code == "Ok":
            with transaction.atomic():
                log = EasBuildItForMeLog()
                log.blogBfmId = bfmId
                log.blogBfmProjectName = eas_build_it_for_me.bfmProjectName
                log.blogBfmpdId = 0
                log.blogBlogtId = 1
                log.blogDate = datetime.now()
                log.save()

                invoice = Invoices()
                invoice.invNo = max_inv_no
                invoice.invDate = datetime.now()
                invoice.invBuildItForMeAmount = float(amt)
                invoice.invTotalAmount = float(amt)
                invoice.invTenantId = get_client_id_by_tenant_id(final_tenant_id)
                invoice.invClientName = inv_client_name
                invoice.invBuildItForMePrice = float(amt)
                invoice.invPayCardNo = inv_pay_card_no
                invoice.invTransationId = inv_transaction_id
                if ten_membership_type == "Free":
                    invoice.invAdjustmentsAmount = float(amt)
                invoice.save()

                tran_status = "Adjustment - Free Account" if ten_membership_type == "Free" else "invoiced"

                commonServices.saveCampaignTransaction(
                    bfmId, "Build It For Me", 1, "builditforme",
                    invoice.invId, tran_status, timezone.now(),
                    get_client_id_by_tenant_id(final_tenant_id), "0", float(amt), float(amt),
                    0, None, None, 0
                )

                eas_build_it_for_me.bfmPublishStatus = 1
                eas_build_it_for_me.bfmInvoicedId = invoice.invId
                eas_build_it_for_me.save()

                # Email notification
                try:
                    mail_dto = MailRequestDTO(
                        to=settings.TO_ADMIN_SUPPORT_EMAIL,
                        subject="New Order Placed",
                        template_name="new-order-template.ftl"
                    )
                    model = {
                        "FULLNAME": inv_client_name,
                        "PROJECTNAME": eas_build_it_for_me.bfmProjectName,
                        "SITEURL": settings.SITEURL,
                        "siteName": settings.SITE_NAME
                    }
                    commonServices.sendEmail(mail_dto, model)
                except Exception:
                    pass

            return api_response(200, "Order Placed Successfully", {"resultCode": "Ok", "message": ""})
        else:
            return api_response(500, res_inner_body.get('errorMessage', "Payment Failed"), {"resultCode": "error", "message": ""})

    except Exception as e:
        logger.error(f"[ tenantId : {final_tenant_id} ] PlaceOrder Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getListPackage(request):
    try:
        packages = EasBuildItForMePackage.objects.filter(bfmpActive='Y')
        list_dto = []
        for p in packages:
            list_dto.append({
                "bfmpId": p.bfmpId,
                "bfmpLable": p.bfmpLable,
                "bfmpAmount": str(p.bfmpAmount)
            })
        return api_response(200, "Fetch Package List Successfully.", {"packageList": list_dto})
    except Exception as e:
        logger.error(f"GetListPackage Error : {str(e)}")
        return api_response(500, ERROR_MSG, {})
