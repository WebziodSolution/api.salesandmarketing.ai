from django.urls import path
from profile_app.views import affiliate_program_views
from profile_app.views import billing_views
from profile_app.views import brand_kit_views
from profile_app.views import contact_us_views
from profile_app.views import domain_email_views
from profile_app.views import domain_views
from profile_app.views import email_signature_views
from profile_app.views import manage_user_views
from profile_app.views import member_views
from profile_app.views import number_forwarding_views
from profile_app.views import plan_views
from profile_app.views import support_api_views
from profile_app.views import todo_views

urlpatterns = [
    path('affiliateProgram/getAffiliateProgramListPage', affiliate_program_views.getAffiliateProgramListPage, name='getAffiliateProgramListPage'),
    path('affiliateProgram/setAgreeAffiliateProgram', affiliate_program_views.setAgreeAffiliateProgram, name='setAgreeAffiliateProgram'),
    path('affiliateProgram/getAffiliateCommissionScheduleListPage', affiliate_program_views.getAffiliateCommissionSchedulePage, name='getAffiliateCommissionSchedulePage'),
    path('billing/getUninvoicedList', billing_views.getUninvoicedList, name='getUninvoicedList'),
    path('billing/getInvoiceList', billing_views.getInvoiceList, name='getInvoiceList'),
    path('billing/getInvoiceById/<str:inv_id>', billing_views.getInvoiceById, name='getInvoiceById'),
    path('billing/printInvoice', billing_views.printInvoice, name='printInvoice'),
    path('billing/getTotalUninvoiced', billing_views.getTotalUninvoiced, name='getTotalUninvoiced'),
    path('billing/removeCreditCard', billing_views.removeCreditCard, name='removeCreditCard'),
    path('billing/deleteAccount', billing_views.deleteAccount, name='deleteAccount'),
    path('billing/checkPassword', billing_views.checkPassword, name='checkPassword'),
    path('billing/paymentBill', billing_views.paymentBill, name='paymentBill'),
    path('brandKit/saveBrandData', brand_kit_views.saveBrandData, name='saveBrandData'),
    path('brandKit/deleteBrandData/<str:brandId>', brand_kit_views.deleteBrandData, name='deleteBrandData'),
    path('brandKit/getBrandData', brand_kit_views.getBrandData, name='getBrandData'),
    path('contactUs/sendContactUs', contact_us_views.sendContactUs, name='sendContactUs'),
    path('domain/getDomainList', domain_views.getDomainList, name='getDomainList'),
    path('domain/saveDomain', domain_views.saveDomain, name='saveDomain'),
    path('domain/deleteDomain/<str:domainId>', domain_views.deleteDomain, name='deleteDomain'),
    path('domain/buyWarmupService', domain_views.buyWarmupService, name='buyWarmupService'),
    path('domain/getDNSProvider', domain_views.getDNSProvider, name='getDNSProvider'),
    path('domain/checkDMARC', domain_views.checkDMARC, name='checkDMARC'),
    path('domain/checkSPF', domain_views.checkSPF, name='checkSPF'),
    path('domain/getESP', domain_views.getESP, name='getESP'),
    path('domain/getBIMI', domain_views.getBIMI, name='getBIMI'),
    path('domain/domainChecker', domain_views.domainChecker, name='domainChecker'),
    path('domainEmail/domainEmail', domain_email_views.getDomainEmailById, name='getDomainEmailById'),
    path('domainEmail/getDomainEmailById/<int:deId>', domain_email_views.getDomainEmailById, name='getDomainEmailById'),
    path('domainEmail/getDomainEmailList/<int:flag>', domain_email_views.getDomainEmailList, name='getDomainEmailList'),
    path('domainEmail/saveDomainEmail', domain_email_views.saveDomainEmail, name='saveDomainEmail'),
    path('domainEmail/addVerifyDomainEmail', domain_email_views.checkDomainEmailExist, name='checkDomainEmailExist'),
    path('domainEmail/deleteDomainEmail/<int:domainEmailId>', domain_email_views.deleteDomainEmail, name='deleteDomainEmail'),
    path('signature/deleteEmailSignature', email_signature_views.deleteEmailSignature, name='deleteEmailSignature'),
    path('signature/getEmailSignatureList', email_signature_views.getEmailSignatureList, name='getEmailSignatureList'),
    path('signature/saveEmailSignature', email_signature_views.saveEmailSignature, name='saveEmailSignature'),
    path('subUser/getUserTypeById/<int:styId>', manage_user_views.getUserTypeById, name='getUserTypeById'),
    path('subUser/getUserType', manage_user_views.getUserType, name='getUserType'),
    path('subUser/saveUsers', manage_user_views.saveSubUser, name='saveSubUser'),
    path('subUser/getAllUser', manage_user_views.getAllUser, name='getAllUser'),
    path('subUser/deleteSubUser/<int:tenant_id>', manage_user_views.deleteSubUser, name='deleteSubUser'),
    path('subUser/getSubUserTypeDetails/<int:sty_id>', manage_user_views.getSubUserTypeEdit, name='getSubUserTypeEdit'),
    path('subUser/getPageActionName', manage_user_views.getPageActionName, name='getPageActionName'),
    path('subUser/getSubaccountPage', manage_user_views.getSubaccountPage, name='getSubaccountPage'),
    path('subUser/getSubaccountPageDetails/<int:pgId>', manage_user_views.getSubaccountPageDetails, name='getSubaccountPageDetails'),
    path('subUser/deleteSubUserType/<int:styId>', manage_user_views.deleteSubUserType, name='deleteSubUserType'),
    path('subUser/saveSubUserType', manage_user_views.saveSubUserType, name='saveSubUserType'),
    path('subUser/getSubUserPhoneList', manage_user_views.getSubUserPhoneList, name='getSubUserPhoneList'),
    path('member/getMemberById', member_views.getTenantById, name='getTenantById'),
    path('member/member', member_views.getTenantById, name='getTenantById'),
    path('member/getMemberByEmail/<str:email>', member_views.getMemberByEmail, name='getMemberByEmail'),
    path('member/updateMemberinfo', member_views.updateMemberInfo, name='updateMemberInfo'),
    path('member/securityquestionstab', member_views.getSecurityQuestionTab, name='getSecurityQuestionTab'),
    path('member/updateSecurityQuestion', member_views.updateSecurityQuestion, name='updateSecurityQuestion'),
    path('member/updateCommunicationPreferences', member_views.updateCommunicationPreferences, name='updateCommunicationPreferences'),
    path('member/updateSmsCvrMyphoneYn', member_views.updateSmsCvrMyphoneYn, name='updateSmsCvrMyphoneYn'),
    path('member/communicationpreferencestab', member_views.getCommunicationPreferencesTab, name='getCommunicationPreferencesTab'),
    path('member/manageappstab', member_views.getManageAppsTab, name='getManageAppsTab'),
    path('member/verifiedOtpOnboarding', member_views.verifiedOtpOnboarding, name='verifiedOtpOnboarding'),
    path('member/uploadFile', member_views.fileUpload, name='fileUpload'),
    path('member/getMemberDetails/<path:tenantEncId>', member_views.getMemberDetails, name='getMemberDetails'),
    path('member/updatePlan', member_views.updatePlan, name='updatePlan'),
    path('member/uploadWhiteListingLogo', member_views.uploadWhiteListingLogo, name='uploadWhiteListingLogo'),
    path('member/updateWhiteListingDetails', member_views.updateWhiteListingDetails, name='updateWhiteListingDetails'),
    path('member/getWhiteListingDetails', member_views.getWhiteListingDetails, name='getWhiteListingDetails'),
    path('member/checkSmsWhiteFlag', member_views.checkSmsWhiteFlag, name='checkSmsWhiteFlag'),
    path('member/set10DLCStatus', member_views.set10DLCStatus, name='set10DLCStatus'),
    path('member/get10DLCStatus', member_views.get10DLCStatus, name='get10DLCStatus'),
    path('member/grabWebsiteLinks', member_views.grabWebsiteLinks, name='grabWebsiteLinks'),
    path('member/grabWebsiteImages', member_views.grabWebsiteImages, name='grabWebsiteImages'),
    path('member/grabWebsiteColors', member_views.grabWebsiteColors, name='grabWebsiteColors'),
    path('member/save10DLCData', member_views.save10DLCData, name='save10DLCData'),
    path('member/getAll10DLCData', member_views.getAll10DLCData, name='getAll10DLCData'),
    path('numberForwarding/numberForwarding', number_forwarding_views.getNumberForwardingList, name='getNumberForwardingList'),
    path('numberForwarding/deleteNumberForwarding', number_forwarding_views.deleteNumberForwarding, name='deleteNumberForwarding'),
    path('numberForwarding/saveNumberForwarding', number_forwarding_views.saveNumberForwarding, name='saveNumberForwarding'),
    path('plan/getPlanById', plan_views.getPlanById, name='getPlanById'),
    path('plan/getPlanListById', plan_views.getPlanListById, name='getPlanListById'),
    path('supportapi/getSupportApiModuleList', support_api_views.getSupportApiModuleList, name='getSupportApiModuleList'),
    path('supportapi/getSupportApiSetting', support_api_views.getSupportApiSetting, name='getSupportApiSetting'),
    path('supportapi/saveAllowApiAccess', support_api_views.saveAllowApiAccess, name='saveAllowApiAccess'),
    path('supportapi/saveAllowApiTo', support_api_views.saveAllowApiTo, name='saveAllowApiTo'),
    path('supportapi/generateAuthKey', support_api_views.generateAuthKey, name='generateAuthKey'),
    path('supportapi/deleteWhiteListingUrls', support_api_views.deleteWhiteListingUrls, name='deleteWhiteListingUrls'),
    path('supportapi/getWhiteListingUrlsList', support_api_views.getWhiteListingUrlsList, name='getWhiteListingUrlsList'),
    path('supportapi/saveWhiteListingUrls', support_api_views.saveWhiteListingUrls, name='saveWhiteListingUrls'),
    # Todos
    path('todos/saveTodo', todo_views.saveTodo, name='saveTodo'),    
    path('todos/getTodoList', todo_views.getTodoList, name='getTodoList'),
    path('todos/getTodoById/<int:todoId>', todo_views.getTodoById, name='getTodoById'),
    path('todos/updateTodoStatus', todo_views.updateTodoStatus, name='updateTodoStatus'),
    path('todos/deleteTodo/<int:todoId>', todo_views.deleteTodo, name='deleteTodoById'),

    # Todo Attachments
    path('todos/uploadAttachment', todo_views.uploadTodoAttachment, name='uploadTodoAttachment'),
    path('todos/getAttachmentList/<int:todoId>', todo_views.getTodoAttachmentList, name='getTodoAttachmentListById'),
    path('todos/getAttachmentById/<int:attachmentId>', todo_views.getTodoAttachmentById, name='getTodoAttachmentById'),
    path('todos/deleteAttachment/<int:attachmentId>', todo_views.deleteTodoAttachment, name='deleteTodoAttachmentById'),

    # Todo Priority
    path('todos/savePriority', todo_views.saveTodoPriority, name='saveTodoPriority'),
    path('todos/getPriorityById/<int:priorityId>', todo_views.getTodoPriorityById, name='getTodoPriorityById'),
    path('todos/getPriorityByTodoId/<int:todoId>', todo_views.getTodoPriorityByTodoId, name='getTodoPriorityByTodoId'),
]


