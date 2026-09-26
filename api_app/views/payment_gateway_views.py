from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from common_app.custom_permissions import WhitelistPermission
from rest_framework import status
from django.conf import settings
from datetime import datetime
import logging
import traceback
from auth_app.models import TenantDetails, Tenants
from common_app.utils import get_final_tenant_id, api_response, country_setting_by_country_id_and_plan_id, upgrade_plan, \
    get_tenants, get_client_id_by_tenant_id
from common_app.services import CommonServices
from authorizenet import apicontractsv1
from authorizenet.apicontrollers import (
    createCustomerProfileController,
    getCustomerProfileController,
    deleteCustomerProfileController,
    updateCustomerPaymentProfileController,
    createTransactionController,
)
from common_app.models import Plans
from django.db import connection
from authorizenet.constants import constants

logger = logging.getLogger(__name__)

def get_total_contact_uploaded(member_id):
    query = """
    SELECT COUNT(tul.UL_EMAIL_ID)
    FROM USER_LIST tul
    JOIN GROUPS grp ON tul.UL_GROUP_ID = grp.GRP_ID
    WHERE tul.UL_GROUP_ID > 0 
      AND tul.UL_CLIENT_ID = %s
      AND (
          (tul.UL_BAD_EMAIL IN ('N', 'B', 'D') OR (tul.UL_BAD_PHONE_NUMBER = 'N' AND LENGTH(tul.UL_PHONE_NUMBER) > 0)) 
          AND (tul.UL_OPT_ID IS NULL OR tul.UL_OPT_ID = 0)
      )
      AND (tul.UL_STATUS = 'Subscribed' OR tul.UL_SMS_STATUS = 'Subscribed') 
      AND tul.UL_TYPE_EMAIL NOT IN ('email', 'pending') 
      AND tul.UL_TYPE_SMS != 'sms'
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, [get_client_id_by_tenant_id(member_id)])
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] TotalContactUploaded Error : {e}")
        return 0

def get_merchant_auth():
    merchantAuth = apicontractsv1.merchantAuthenticationType()
    if settings.ENVSYS == 'prodapi':
        merchantAuth.name = settings.AUTHORIZENET_PRODUCTION_LOGIN_ID
        merchantAuth.transactionKey = settings.AUTHORIZENET_PRODUCTION_TRANSACTION_KEY
    else:
        merchantAuth.name = settings.AUTHORIZENET_LOGIN_ID
        merchantAuth.transactionKey = settings.AUTHORIZENET_TRANSACTION_KEY
    return merchantAuth

def get_environment():
    if settings.ENVSYS == 'prodapi':
        return constants.PRODUCTION
    return constants.SANDBOX

def get_validation_mode():
    if settings.ENVSYS == 'prodapi':
        return apicontractsv1.validationModeEnum.liveMode
    return apicontractsv1.validationModeEnum.testMode


@api_view(['POST'])
@permission_classes([AllowAny])
def createPaymentProfile(request):
    try:
        data = request.data
        tenant_id = data.get('memberId')

        # 1. EXPIRATION DATE VALIDATION
        card_exp = data.get('expMonthYear', '').split('/')
        if len(card_exp) != 2:
            return api_response(500, "Please Confirm The Expiration Date Of Your Credit Card Is Correct And Matches The Format Of MM/YYYY", "Error", sendErrorAs200=True)

        try:
            exp_year = int(card_exp[1]) % 100
            exp_month = int(card_exp[0])
        except ValueError:
            return api_response(500, "Please Confirm The Expiration Date Of Your Credit Card Is Correct And Matches The Format Of MM/YYYY", "Error", sendErrorAs200=True)

        now = datetime.now()
        current_year = now.year % 100
        current_month = now.month # Python month is 1-indexed (1-12)

        if current_year >= exp_year:
            if exp_month <= current_month:
                return api_response(500, "Please Confirm The Expiration Date Of Your Credit Card Is Correct And Matches The Format Of MM/YYYY", "Error", sendErrorAs200=True)

        # Set environment
        # Java: ApiOperationBase.setEnvironment(paymentGatewayConfiguration.environmentModeCheck());
        # Python: already handled via get_environment() in controllers

        # 2. AUTHORIZE.NET OBJECT MAPPING
        merchantAuth = get_merchant_auth()

        creditCard = apicontractsv1.creditCardType()
        creditCard.cardNumber = data.get('cardNumber')
        creditCard.expirationDate = f"{card_exp[1]}-{card_exp[0]}" # Format: YYYY-MM
        creditCard.cardCode = data.get('cardCode')

        payment = apicontractsv1.paymentType()
        payment.creditCard = creditCard

        billTo = apicontractsv1.customerAddressType()
        billTo.firstName = data.get('firstName')
        billTo.lastName = data.get('lastName')
        billTo.company = data.get('company')
        billTo.address = data.get('address')
        billTo.city = data.get('city')
        billTo.state = data.get('state')
        billTo.zip = data.get('postCode')
        billTo.country = data.get('country')
        billTo.phoneNumber = data.get('phone')

        paymentProfile = apicontractsv1.customerPaymentProfileType()
        paymentProfile.customerType = apicontractsv1.customerTypeEnum.individual
        paymentProfile.payment = payment
        paymentProfile.billTo = billTo

        customerProfile = apicontractsv1.customerProfileType()
        customerProfile.email = data.get('email')
        customerProfile.merchantCustomerId = f"{settings.ENVSYS.upper()}-{settings.COMPANY_NAME}-{tenant_id}"
        customerProfile.description = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
        customerProfile.paymentProfiles = [paymentProfile]

        try:
            # 3. EXECUTE REQUEST
            createCustomerProfile = apicontractsv1.createCustomerProfileRequest()
            createCustomerProfile.merchantAuthentication = merchantAuth
            createCustomerProfile.profile = customerProfile
            createCustomerProfile.validationMode = get_validation_mode()

            controller = createCustomerProfileController(createCustomerProfile)
            controller.setenvironment(get_environment())
            controller.execute()
            response = controller.getresponse()
        except Exception as e:
            logger.error(f"createPaymentProfile Error: {e}")
            logger.error(traceback.format_exc())
            response = apicontractsv1.createCustomerProfileRequest()

        # 4. RESPONSE HANDLING
        if response is not None:
            if response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                # --- SUCCESS LOGIC ---
                tenant_instance = TenantDetails.objects.get(tenant__ten_id=tenant_id)
                if tenant_instance:
                    try:
                        customer_profile_id = response.customerProfileId
                        customer_payment_profile_id = response.customerPaymentProfileIdList.numericString[0]

                        tenant_instance.td_authorize_customer_profile_id = str(customer_profile_id)
                        tenant_instance.td_authorize_customer_payment_profile_id = str(customer_payment_profile_id)
                        tenant_instance.td_bill_date = datetime.now()
                        tenant_instance.save()

                        # --- Update plan start ---
                        plan_id = tenant_instance.td_plan_id or 1
                        plan = Plans.objects.filter(plan_id=plan_id).first()
                        if plan and plan.plan_visibility == "Public":
                            auth_cust_id = tenant_instance.td_authorize_customer_profile_id
                            auth_pay_id = tenant_instance.td_authorize_customer_payment_profile_id

                            ten_country = Tenants.objects.get(ten_id=tenant_id).ten_country
                            cnty_setting = country_setting_by_country_id_and_plan_id(int(ten_country or 100), plan_id)
                            included = cnty_setting.cnty_contacts_included if cnty_setting else 0

                            total_uploaded = CommonServices.total_contact_uploaded(tenant_id)
                            if included > 0:
                                if total_uploaded > included:
                                    if auth_cust_id and auth_pay_id:
                                        upgrade_plan(total_uploaded, int(ten_country or 100), tenant_id, plan_id, 0)
                        # --- Update plan end ---

                    except Exception as e:
                        logger.error(f"Not Update Tenant Table : {e}")

                return api_response(200, "Add Credit Card Profile Successfully.", response)
            else:
                # --- FAILURE LOGIC ---
                logger.error(f"Payment Gateway : Failed To Create Customer Profile")
                errMsg = "Failed To Create Customer Profile"
                return api_response(500, "Failed To Create Customer Profile", errMsg,sendErrorAs200=True)
        else:
            # Java: errorResponse = controller.getErrorResponse();
            return api_response(500, "Failed To Get Response", "Null Response",sendErrorAs200=True)
            
    except Exception as e:
        logger.error(f"createPaymentProfile Error: {e}")
        logger.error(traceback.format_exc())
        return api_response(500, "Internal Server Error", str(e),sendErrorAs200=True)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getPaymentProfile(request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        list_data = {"uninvoicedAmount": "0"}
        if final_tenant_id > 0:
            tenant = get_tenants(
                where_conditions={
                    "tenant": {
                        "ten_id": final_tenant_id
                    }
                }
            )

            if not tenant or not tenant.td_authorize_customer_profile_id:
                return api_response(500, "Invalid Customer Profile.", "Invalid Payment Profile",sendErrorAs200=True)
                
            auth_customer_profile_id = tenant.td_authorize_customer_profile_id
            
            merchantAuth = get_merchant_auth()
            try:
                getRequest = apicontractsv1.getCustomerProfileRequest()
                getRequest.merchantAuthentication = merchantAuth
                getRequest.customerProfileId = str(auth_customer_profile_id)
                
                controller = getCustomerProfileController(getRequest)
                controller.setenvironment(get_environment()) 
                controller.execute()
                response = controller.getresponse()
            except Exception as e:
                logger.error(f"Exception during Authorize.Net execution: {str(e)}")
                logger.error(traceback.format_exc())
                response = apicontractsv1.getCustomerProfileRequest()

            
            if response is not None:
                if response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                    if hasattr(response, 'profile') and response.profile is not None:
                        paymentProfiles = getattr(response.profile, 'paymentProfiles', [])
                        for paymentProfile in paymentProfiles:
                            billTo = getattr(paymentProfile, 'billTo', None)
                            payment = getattr(paymentProfile, 'payment', None)
                            card = getattr(payment, 'creditCard', None) if payment is not None else None
                            
                            def to_str(val):
                                if val is None: return ""
                                # Authorize.Net SDK uses PyXB which might return objects for simple types
                                if hasattr(val, 'value'): # PyXB often uses .value() or just str()
                                    return str(val.value()) if val.value() is not None else ""
                                return str(val)

                            list_data["firstName"] = to_str(getattr(billTo, 'firstName', ""))
                            list_data["lastName"] = to_str(getattr(billTo, 'lastName', ""))
                            list_data["company"] = to_str(getattr(billTo, 'company', ""))
                            list_data["address"] = to_str(getattr(billTo, 'address', ""))
                            list_data["city"] = to_str(getattr(billTo, 'city', ""))
                            list_data["state"] = to_str(getattr(billTo, 'state', ""))
                            list_data["postCode"] = to_str(getattr(billTo, 'zip', ""))
                            list_data["country"] = to_str(getattr(billTo, 'country', ""))
                            
                            phone = to_str(getattr(billTo, 'phoneNumber', ""))
                            if phone:
                                phone = phone.replace('-', '')
                            list_data["phone"] = phone
                            
                            list_data["cardNumber"] = to_str(getattr(card, 'cardNumber', ""))
                            list_data["expMonthYear"] = to_str(getattr(card, 'expirationDate', ""))
                            list_data["cardType"] = to_str(getattr(card, 'cardType', ""))
                            
                            total_of_tran_total_amount = CommonServices.total_uninvoiced_amt(final_tenant_id)
                            list_data["uninvoicedAmount"] = str(total_of_tran_total_amount)
                            
                            return api_response(200, "Fetch Payment Profile Successfully.", {"paymentProfile": list_data})
                else:
                    return api_response(500, "Invalid Customer Profile.", response.messages.resultCode,sendErrorAs200=True)

            return api_response(500, "Invalid Customer Profile.", "Invalid Payment Profile",sendErrorAs200=True)
        else:
            return api_response(500, "Invalid Customer Profile.", "Invalid Payment Profile",sendErrorAs200=True)
    except Exception as e:
        logger.error(f"getPaymentProfile Error: {e}")
        logger.error(traceback.format_exc())
        return api_response(500, "Invalid Customer Profile.", str(e),sendErrorAs200=True)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deletePaymentProfile(request):
    try:
        final_tenant_id = get_final_tenant_id(request=request)
        if final_tenant_id > 0:
            final_tenant = TenantDetails.objects.get(tenant__ten_id=final_tenant_id)
            if not final_tenant or not final_tenant.td_authorize_customer_profile_id:
                return api_response(500, "Failed To Delete Customer Profile.", "Failed To Delete Customer Profile.")
                
            auth_customer_profile_id = final_tenant.td_authorize_customer_profile_id

            merchantAuth = get_merchant_auth()
            
            deleteRequest = apicontractsv1.deleteCustomerProfileRequest()
            deleteRequest.merchantAuthentication = merchantAuth
            deleteRequest.customerProfileId = auth_customer_profile_id
            
            controller = deleteCustomerProfileController(deleteRequest)
            controller.setenvironment(get_environment())
            controller.execute()
            
            response = controller.getresponse()
            if response is not None:
                if response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                    try:
                        final_tenant.td_authorize_customer_profile_id = ""
                        final_tenant.td_authorize_customer_payment_profile_id = ""
                        final_tenant.save()
                    except Exception as e:
                        logger.error(f"[ tenantId : {final_tenant_id} ] DeletePaymentProfile Error : {e}")
                    
                    return api_response(200, "Delete Payment Profile Successfully.", {"messages": {"resultCode": response.messages.resultCode}})
                else:
                    logger.error(f"[ tenantId : {final_tenant_id} ] Failed To Delete Customer Profile  Error : {response.messages.resultCode}")
                    return api_response(500, "Failed To Delete Customer Profile.", response.messages.resultCode)
            return api_response(500, "Failed To Delete Customer Profile.", "Failed To Delete Customer Profile.")
        else:
            return api_response(500, "Failed To Delete Customer Profile.", "Failed To Delete Customer Profile.")
    except Exception as e:
        logger.error(f"deletePaymentProfile Error: {e}")
        return api_response(500, "Failed To Delete Customer Profile.", str(e))

@api_view(['POST'])
@permission_classes([AllowAny])
def updatePaymentProfile(request):
    try:
        data = request.data
        tenant_id = data.get('tenantId')
        
        card_exp = data.get('expMonthYear', '').split('/')
        if len(card_exp) != 2:
            return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Please Confirm The Expiration Date Of Your Credit Card Is Correct And Matches The Format Of MM/YYYY", {"status": "Error", "status_code": 500})
            
        exp_month = int(card_exp[0])
        exp_year = int(card_exp[1])
        
        now = datetime.now()
        year = now.year % 100
        month = now.month
        
        if year >= exp_year:
            if exp_month <= month:
                return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Please Confirm The Expiration Date Of Your Credit Card Is Correct And Matches The Format Of MM/YYYY", {"status": "Error", "status_code": 500})

        tenantDetails = TenantDetails.objects.get(tenant__ten_id=tenant_id)
        if not tenantDetails or not tenantDetails.td_authorize_customer_profile_id:
            return api_response(500, "Failed To Update Customer Payment Profile.", "Failed To Update Customer Payment Profile.")
            
        auth_customer_profile_id = tenantDetails.td_authorize_customer_profile_id
        auth_customer_payment_profile_id = tenantDetails.td_authorize_customer_payment_profile_id

        merchantAuth = get_merchant_auth()

        billTo = apicontractsv1.customerAddressType()
        billTo.firstName = data.get('firstName')
        billTo.lastName = data.get('lastName')
        billTo.company = data.get('company')
        billTo.address = data.get('address')
        billTo.city = data.get('city')
        billTo.state = data.get('state')
        billTo.zip = data.get('postCode')
        billTo.country = data.get('country')
        billTo.phoneNumber = data.get('phone')

        creditCard = apicontractsv1.creditCardType()
        creditCard.cardNumber = data.get('cardNumber')
        creditCard.expirationDate = f"{exp_year}-{exp_month:02d}"
        creditCard.cardCode = data.get('cardCode')

        payment = apicontractsv1.paymentType()
        payment.creditCard = creditCard

        customer = apicontractsv1.customerPaymentProfileExType()
        customer.payment = payment
        customer.customerPaymentProfileId = auth_customer_payment_profile_id
        customer.billTo = billTo

        updateRequest = apicontractsv1.updateCustomerPaymentProfileRequest()
        updateRequest.merchantAuthentication = merchantAuth
        updateRequest.customerProfileId = auth_customer_profile_id
        updateRequest.paymentProfile = customer
        updateRequest.validationMode = get_validation_mode()

        controller = updateCustomerPaymentProfileController(updateRequest)
        controller.setenvironment(get_environment())
        controller.execute()

        response = controller.getresponse()

        if response is not None:
            if response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                tenantDetails.td_creditcard_error = None
                tenantDetails.td_creditcard_status = None
                tenantDetails.save()
                return api_response(200, "Update Credit Card Profile Successfully.", {"messages": {"resultCode": response.messages.resultCode}})
            else:
                logger.error(f"Failed To Update Customer Payment Profile: {response}")
                try:
                    err = response.validationDirectResponse.split(',')
                    err_code = err[2] if len(err) > 2 else ""
                    msgs = response.messages.message[0].text if response.messages.message else ""
                    
                    if err_code == "2":
                        errMsg = " General decline (customer should contact bank). This card number appears to be incorrect or may have insufficient funds"
                    elif err_code == "3":
                        errMsg = " Referral to issuer (bank verification needed) Your bank requires additional security"
                    elif err_code == "4":
                        errMsg = " Lost or stolen card (stop retrying) Your bank has this card registered as lost or stolen"
                    elif err_code == "27":
                        errMsg = " AVS mismatch (address mismatch) Your billing address (zip code) appears to be incorrect"
                    elif err_code == "44":
                        errMsg = " CVV mismatch (security code incorrect) Please confirm your Security Code is correct"
                    elif err_code == "45":
                        errMsg = " AVS + CVV mismatch (high fraud risk) Your Address and CVC are not correct. High Security Fraud"
                    elif err_code == "65":
                        errMsg = " CVV failed (too many failed attempts) Too Many Attempts"
                    elif err_code == "7":
                        errMsg = "Credit Card Expiration Date Is Invalid"
                    elif err_code in ["6", "37"]:
                        errMsg = "The Credit Card Number Is Invalid"
                    elif err_code == "165" or msgs == "This Transaction Has Been Declined.":
                        errMsg = "Please Confirm Your CVV Is Correct"
                    elif err_code == "E00039":
                        errMsg = "Your CC is used on another account in our system"
                    else:
                        errMsg = msgs
                except Exception:
                    errMsg = response.messages.message[0].text if response.messages.message else "Failed To Update Customer Payment Profile."
                    
                return api_response(500, errMsg, errMsg)
        return api_response(500, "Failed To Update Customer Payment Profile.", "Failed To Update Customer Payment Profile.")
    except Exception as e:
        logger.error(f"updatePaymentProfile Error: {e}")
        return api_response(500, "Failed To Update Customer Payment Profile.", str(e))

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def chargePaymentProfile(request):
    try:
        data = request.data
        final_tenant_id = get_final_tenant_id(request=request)
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": final_tenant_id
                }
            }
        )
        
        if not tenant or not tenant.td_authorize_customer_profile_id:
            return api_response(500, "Error", "Null Response.")

        auth_customer_profile_id = tenant.td_authorize_customer_profile_id
        auth_customer_payment_profile_id = tenant.td_authorize_customer_payment_profile_id
        
        merchantAuth = get_merchant_auth()
        
        profileToCharge = apicontractsv1.customerProfilePaymentType()
        profileToCharge.customerProfileId = auth_customer_profile_id
        
        paymentProfile = apicontractsv1.paymentProfile()
        paymentProfile.paymentProfileId = auth_customer_payment_profile_id
        profileToCharge.paymentProfile = paymentProfile
        
        now = datetime.now()
        
        orderType = apicontractsv1.orderType()
        orderType.invoiceNumber = f"{settings.COMPANY_NAME}-{data.get('invNo')}"
        orderType.description = f"{settings.COMPANY_NAME} Transaction On Date : {now}"
        
        extendedAmountType = apicontractsv1.extendedAmountType()
        extendedAmountType.amount = 0.00
        extendedAmountType.name = "WA state sales tax"
        extendedAmountType.description = "Washington state sales tax"
        
        txnRequest = apicontractsv1.transactionRequestType()
        txnRequest.transactionType = apicontractsv1.transactionTypeEnum.authCaptureTransaction
        txnRequest.profile = profileToCharge
        txnRequest.amount = round(float(data.get('amt', 0)), 3)
        txnRequest.order = orderType
        txnRequest.tax = extendedAmountType
        txnRequest.taxExempt = False
        
        createRequest = apicontractsv1.createTransactionRequest()
        createRequest.merchantAuthentication = merchantAuth
        createRequest.transactionRequest = txnRequest
        
        controller = createTransactionController(createRequest)
        controller.setenvironment(get_environment())
        controller.execute()
        
        response = controller.getresponse()
        
        resBody = {
            "tenantId": str(data.get('tenantId'))
        }
        
        if response is not None:
            if response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                result = response.transactionResponse
                if hasattr(result, 'messages') and result.messages is not None:
                    resBody["invTransationId"] = result.transId
                    resBody["invPayCardNo"] = result.accountNumber
                    return api_response(200, "Add Charge Successfully.", resBody)
                else:
                    logger.error(f"Error : {response}")
                    return api_response(500, "Error", "Error")
            else:
                logger.error(f"Error : {response}")
                return api_response(500, "Error", "Error")
        else:
            return api_response(500, "Error", "Null Response.")
    except Exception as e:
        logger.error(f"chargePaymentProfile Error: {e}")
        return api_response(500, "Error", str(e))

@api_view(['POST'])
@permission_classes([AllowAny])
def updateBillingDetails(request):
    try:
        data = request.data
        tenant_id = data.get('tenantId')
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )

        if not tenant or not tenant.td_authorize_customer_profile_id:
            return api_response(500, "Failed To Update Customer Payment Profile.", "Failed To Update Customer Payment Profile.")
            
        auth_customer_profile_id = tenant.td_authorize_customer_profile_id
        auth_customer_payment_profile_id = tenant.td_authorize_customer_payment_profile_id

        merchantAuth = get_merchant_auth()

        billTo = apicontractsv1.customerAddressType()
        billTo.firstName = data.get('billingFirstName')
        billTo.lastName = data.get('billingLastName')
        billTo.company = data.get('businessName')
        billTo.address = data.get('billingAddress1')
        billTo.city = data.get('billingCity')
        billTo.state = data.get('billingState')
        billTo.zip = data.get('billingPostCode')
        billTo.country = data.get('billingCountry')
        billTo.phoneNumber = data.get('billingPhone')

        customer = apicontractsv1.customerPaymentProfileExType()
        customer.customerPaymentProfileId = auth_customer_payment_profile_id
        customer.billTo = billTo

        updateRequest = apicontractsv1.updateCustomerPaymentProfileRequest()
        updateRequest.merchantAuthentication = merchantAuth
        updateRequest.customerProfileId = auth_customer_profile_id
        updateRequest.paymentProfile = customer
        updateRequest.validationMode = get_validation_mode()

        controller = updateCustomerPaymentProfileController(updateRequest)
        controller.setenvironment(get_environment())
        controller.execute()

        response = controller.getresponse()

        if response is not None:
            if response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
                return api_response(200, "Update Billing Details Successfully.", {"messages": {"resultCode": response.messages.resultCode}})
            else:
                logger.error(f"Failed To Update Customer Payment Profile : {response}")
                errMsg = response.messages.message[0].text if response.messages.message else "Failed To Update Billing Details"
                return api_response(500, "Failed To Update Billing Details", errMsg)
        
        return api_response(500, "Failed To Update Customer Payment Profile.", "Failed To Update Customer Payment Profile.")
    except Exception as e:
        logger.error(f"updateBillingDetails Error: {e}")
        return api_response(500, "Failed To Update Billing Details", str(e))