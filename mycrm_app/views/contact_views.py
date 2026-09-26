import csv
import math
import os
import logging
from datetime import datetime, date
from django.http import HttpResponse
from django.conf import settings
from django.db.models import Q, Count, Min, QuerySet
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from common_app.decrypt_string import DecryptString
from common_app.models import (Userlist, Groups, Udf, GroupSegment, UnsubscribeLogs, Country, Plans)
from common_app.utils import (api_response, get_final_tenant_id, check_duplicate_records, check_type_email,
                              check_total_member, db_date, clean_me_number, last_characters, upgrade_plan, get_tenants,
                              get_client_id_by_tenant_id)
from common_app.services import CommonServices
from common_app.recaptcha_service import reCaptchaService
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)

ACTIVE_CONTACT_FILTER = (
    Q(badEmail__in=['N', 'B', 'D']) | (Q(badPhoneNumber='N') & Q(phoneNumber__isnull=False))
) & (
    (Q(status='Subscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
    (Q(status='Unsubscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
    (Q(status='Subscribed') & Q(smsStatus='Unsubscribed'))
) & (Q(optId__isnull=True) | Q(optId=0))

def format_date_parity(date_val):
    """Formats a date object or string to MM/dd/yyyy for parity."""
    if not date_val:
        return None

    if isinstance(date_val, (datetime, date)):
        return date_val.strftime('%m/%d/%Y')

    if isinstance(date_val, str):
        try:
            dt = datetime.strptime(date_val[:10], '%Y-%m-%d')
            return dt.strftime('%m/%d/%Y')
        except ValueError:
            return date_val

    return str(date_val)

def format_contact_dict(c, duplicate_emails=None, duplicate_phones=None):
    # Decrypt sensitive fields
    first_name = c.firstName if c.firstName else ""
    last_name = c.lastName if c.lastName else ""
    email_raw = c.email if c.email else ""
    
    # Calculate duplicateRecords logic matching Java ContactServiceImpl.java:1242-1254 (if duplicates provided)
    is_duplicate = "N"
    if duplicate_emails is not None and email_raw and email_raw in duplicate_emails:
        is_duplicate = "Y"
    if is_duplicate == "N" and duplicate_phones is not None and c.phoneNumber and c.phoneNumber in duplicate_phones:
        is_duplicate = "Y"

    type_email = c.typeEmail or "done"
    if type_email == "pending":
        type_email = "email"

    country_code = None
    if c.country:
        try:
            # Inline import or local lookup to avoid circularity if needed
            country_obj = Country.objects.filter(cnt_name__iexact=c.country).first()
            if country_obj:
                country_code = country_obj.cnt_code
        except Exception:
            pass

    # Ordered EXACTLY as in UserlistDto.java (Step 1161/1029)
    res = {
        "emailId": c.emailId,
        "memberId": c.memberId,
        "firstName": first_name or None,
        "lastName": last_name or None,
        "birthday": format_date_parity(c.birthday) if c.birthday else None,
        "email": email_raw or "",
        "country": c.country or "",
        "phoneNumber": c.phoneNumber or "",
        "groupId": c.groupId,
        "streetAddress1": c.streetAddress1 or None,
        "badEmail": c.badEmail or "N",
        "badPhoneNumber": c.badPhoneNumber or "N",
        "bounceReason": c.bounceReason or None,
        "city": c.city or None,
        "emailDomain": email_raw.split('@')[1] if email_raw and '@' in email_raw else None,
        "gender": c.gender or None,
        "isEmailValidate": getattr(c, 'isEmailValidate', "N"),
        "optId": getattr(c, 'optId', None),
        "smsSid": getattr(c, 'smsSid', None),
        "smsStatus": c.smsStatus or "Subscribed",
        "stateProvRegion": c.stateProvRegion or None,
        "status": c.status or "Subscribed",
        "streetAddress2": c.streetAddress2 or None,
        "fullName": f"{first_name} {last_name}".strip() or None,
        "phone": None,
        "tags": getattr(c, 'tags', None),
        "tempCronId": getattr(c, 'tempCronId', None),
        "udf1": getattr(c, 'udf1', None),
        "udf10": getattr(c, 'udf10', None),
        "udf2": getattr(c, 'udf2', None),
        "udf3": getattr(c, 'udf3', None),
        "udf4": getattr(c, 'udf4', None),
        "udf5": getattr(c, 'udf5', None),
        "udf6": getattr(c, 'udf6', None),
        "udf7": getattr(c, 'udf7', None),
        "udf8": getattr(c, 'udf8', None),
        "udf9": getattr(c, 'udf9', None),
        "usDefaultLanguage": c.usDefaultLanguage or "en",
        "zipPostalCode": c.zipPostalCode or None,
        "duplicateRecords": is_duplicate,
        "reCaptchaToken": None,
        "dateRegistered": format_date_parity(c.dateRegistered),
        "optDate": format_date_parity(getattr(c, 'optDate', None)),
        "optBackInDate": format_date_parity(getattr(c, 'optBackInDate', None)),
        "optOutDate": format_date_parity(getattr(c, 'optOutDate', None)),
        "dateAdded": format_date_parity(getattr(c, 'dateAdded', None)),
        "dateLastModified": format_date_parity(getattr(c, 'dateLastModified', None)),
        "udfs": None,
        "countryCode": country_code,
        "encEmailId": str(DecryptString.set_enc_dec_user(c.emailId, "", "Y")),
        "typeEmail": type_email,
        "typeSms": c.typeSms or "done",
        "sendToEmailVerification": getattr(c, 'sendToEmailVerification', "No"),
        "DEBUG_MARKER": "20260328_REDO_V2"
    }
    return res

def format_bad_email_dict(c):
    group_name = ""
    try:
        group = Groups.objects.filter(grpId=c.groupId).first()
        if group:
            group_name = group.grpGroupName
    except:
        pass

    # Ordered exactly as in BadEmailAndUnsubscribedDto.java
    return {
        "emailId": c.emailId,
        "firstName": c.firstName if c.firstName else None,
        "lastName": c.lastName if c.lastName else None,
        "email": c.email if c.email else "",
        "badEmail": c.badEmail or "N",
        "phoneNumber": c.phoneNumber or "",
        "optId": getattr(c, 'optId', None),
        "optDate": format_date_parity(getattr(c, 'optDate', None)),
        "groupId": c.groupId,
        "groupName": group_name,
        "bounceReason": c.bounceReason or None,
        "sendToEmailVerification": getattr(c, 'sendToEmailVerification', "No")
    }

def get_contact_header_dict(g_id):
    """Matches GroupServiceImpl.java contactHeaderKey/Value."""
    base_headers = {
        "firstName": "First Name", "lastName": "Last Name", "fullName": "Full Name",
        "email": "Email", "phoneNumber": "Mobile", "phone": "Phone",
        "usDefaultLanguage": "Language", "streetAddress1": "Street Address1",
        "streetAddress2": "Street Address2", "city": "City", "stateProvRegion": "State",
        "zipPostalCode": "Zip Code", "country": "Country", "birthday": "Birthday",
        "gender": "Gender", "emailDomain": "Email Domain", "dateRegistered": "Registered Date",
        "status": "Status", "smsStatus": "SMS Status", "optDate": "Opt Date",
        "optBackInDate": "Opt Back In Date", "optOutDate": "Opt Out Date", "tags": "Tags"
    }
    udfs = Udf.objects.filter(groupId=g_id)
    for udf in udfs:
        base_headers[f"udf{udf.udfLabel}"] = udf.udf
    return base_headers

def get_contact_header_key_list(g_id):
    """Matches GroupServiceImpl.java contactHeaderKey."""
    return list(get_contact_header_dict(g_id).keys())

def _create_and_update_user_list(data, tenant_id, sub_tenant_id=0):
    """Private helper mirroring ContactServiceImpl.createAndUpdateUserList logic."""
    res_body = dict()
    res_body['error'] = ""
    try:
        email = data.get('email', '')
        email_id = int(data.get('emailId', 0))
        group_id = int(data.get('groupId', 0))
        
        if not data.get('country'):
            data['country'] = "United States"
            
        if UnsubscribeLogs.objects.filter(member_id=get_client_id_by_tenant_id(tenant_id), email=email).exists():
            res_body["error"] = "This Email Address Is Unsubscribed From Your Contact List"
            return res_body

        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        
        if email_id == 0:
            # Plan validation logic (mirrors Java createAndUpdateUserList block)
            plan_id = tenant.td_plan_id or 1
            try:
                plan = Plans.objects.get(plan_id=plan_id)
                if plan.plan_visibility == "Public":
                    if tenant.td_authorize_customer_profile_id and tenant.td_authorize_customer_payment_profile_id:
                        country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
                        total_uploaded = CommonServices.total_contact_uploaded(tenant_id)
                        limit = country_setting.cnty_contacts_included if country_setting else 0
                        
                        total_uploaded += 1
                        if total_uploaded > limit:
                            # Find next plan
                            next_plan = Plans.objects.filter(plan_id__gt=plan_id, plan_visibility="Public").order_by('plan_id').first()
                            if next_plan:
                                upgrade_plan(total_uploaded, int(tenant.ten_country or 100), tenant_id, next_plan.plan_id,
                                                 sub_tenant_id)
            except Exception as e:
                logger.error(f"Plan validation error: {e}")

        # Encryption parity
        birthday = data.get('birthday', '')
        encrypted_birthday = db_date(birthday) if birthday else ""
        encrypted_email = email if email else ""
        email_domain = email.split('@')[1] if email and '@' in email else ""

        if email_id > 0:
            contact = Userlist.objects.get(emailId=email_id)
        else:
            contact = Userlist()
            contact.memberId = get_client_id_by_tenant_id(tenant_id)
            contact.dateRegistered = timezone.now()
            contact.dateAdded = timezone.now()
            contact.typeEmail = "unverified" if email else "done"
            contact.typeSms = "done"

        contact.groupId = group_id
        
        # Mapping all standard fields from request DTO
        fields = [
            'firstName', 'lastName', 'phoneNumber', 'phone', 'country', 'status', 'smsStatus',
            'streetAddress1', 'streetAddress2', 'city', 'stateProvRegion', 'zipPostalCode',
            'gender', 'tags', 'fullName', 'usDefaultLanguage',
            'bounceReason', 'optId', 'smsSid',
            'tempCronId', 'badEmail', 'badPhoneNumber'
        ]

        for field in fields:
            if field in data:
                setattr(contact, field, data[field])
            elif email_id == 0:
                if field in ['status', 'smsStatus']: setattr(contact, field, 'Subscribed')
                elif field in ['badEmail', 'badPhoneNumber']: setattr(contact, field, 'N')
                elif field == 'usDefaultLanguage': setattr(contact, field, 'en')

        contact.email = encrypted_email
        contact.emailDomain = email_domain
        contact.birthday = encrypted_birthday
        contact.dateLastModified = timezone.now()
        contact.isEmailValidate = 'Y' if email else 'N'
        
        for i in range(1, 11):
            f_name = f'udf{i}'
            if f_name in data: setattr(contact, f_name, data[f_name])

        contact.save()

        # Update stats
        check_duplicate_records(group_id, get_client_id_by_tenant_id(tenant_id))
        check_type_email(group_id, get_client_id_by_tenant_id(tenant_id))
        check_total_member(group_id, get_client_id_by_tenant_id(tenant_id))

        # Opt-in logic (exactly mirroring Java)
        if data.get('optInType'):
            opt_type = data.get('optInType')
            if opt_type in ['email', 'both'] and contact.email:
                CommonServices.send_optin_details_email(contact)
            if opt_type in ['sms', 'both'] and contact.phoneNumber:
                # Passing None as reply log to use default opt-in message
                CommonServices.send_optin_details_sms(contact, None)

        res_body["userlist"] = format_contact_dict(contact)
        return res_body
    except Exception as e:
        logger.error(f"Error in _create_and_update_user_list: {e}")
        res_body["error"] = str(e)
        return res_body

@api_view(['POST', 'PUT'])
@permission_classes([WhitelistPermission])
def contact_root(request):
    """Unified endpoint for root /contact POST/PUT."""
    if request.method == 'POST':
        return add_contact(request)
    elif request.method == 'PUT':
        email_id = request.data.get('emailId')
        return update_contact(request, email_id=email_id)
    return api_response(405, "Method not allowed")


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def add_contact(request):
    """POST /addContact"""
    member_id = get_final_tenant_id(request=request)
    data = request.data.copy()
    if not data.get('email') and not data.get('phoneNumber'):
        return api_response(500, "Please Enter Email Address / Mobile Number")
    data['emailId'] = 0
    result = _create_and_update_user_list(data, member_id)
    if result.get('error'):
        return api_response(500, result['error'], result)
    return api_response(200, "Contact Added", result)

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def update_contact(request, email_id):
    """PUT /updateContact/{id}"""
    member_id = get_final_tenant_id(request=request)
    data = request.data.copy()
    data['emailId'] = email_id
    if not data.get('email') and not data.get('phoneNumber'):
        return api_response(500, "Please Enter Email Address / Mobile Number")
    result = _create_and_update_user_list(data, member_id)
    if result.get('error'):
        return api_response(500, result['error'])
    
    # UDF list population logic from Java updateContact
    udfs_data = data.get('udfs')
    if isinstance(udfs_data, list):
        seen = set()
        for u in udfs_data:
            lbl = u.get('udf')
            gid = data.get('groupId')
            if lbl and gid and lbl not in seen:
                seen.add(lbl)
                if not Udf.objects.filter(groupId=gid, udf=lbl).exists():
                    Udf.objects.create(groupId=gid, udf=lbl, udfLabel=u.get('udfLabel', lbl))

    return api_response(200, "Contact Updated Successfully.", result.get('userlist'))

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def delete_contact(request, email_id):
    """DELETE /deleteContact/{id}"""
    try:
        member_id = get_final_tenant_id(request=request)
        contact = Userlist.objects.get(emailId=email_id, memberId=get_client_id_by_tenant_id(member_id))
        gid = contact.groupId
        contact.delete()
        check_duplicate_records(gid, get_client_id_by_tenant_id(member_id))
        check_type_email(gid, get_client_id_by_tenant_id(member_id))
        check_total_member(gid, get_client_id_by_tenant_id(member_id))
        return api_response(200, "Contact Deleted Successfully.", {})
    except Userlist.DoesNotExist:
        return api_response(500, "Something went wrong. Please try again later.")

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def delete_bulk_contact(request):
    """DELETE /deleteBulkContact"""
    member_id = get_final_tenant_id(request=request)
    email_ids = request.data.get('emailIds', [])
    if not email_ids:
        return api_response(400, "emailIds list is required")
    contacts = Userlist.objects.filter(emailId__in=email_ids, memberId=get_client_id_by_tenant_id(member_id))
    gids = set(contacts.values_list('groupId', flat=True))
    contacts.delete()
    for gid in gids:
        check_duplicate_records(gid, get_client_id_by_tenant_id(member_id))
        check_type_email(gid, get_client_id_by_tenant_id(member_id))
        check_total_member(gid, get_client_id_by_tenant_id(member_id))
    return api_response(200, "Contact Deleted Successfully.", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_contact(request, email_id):
    """GET /getContact/{id} mirroring findUser."""
    try:
        contact = Userlist.objects.get(emailId=email_id)
        return api_response(200, "Contact Fetched Successfully.", format_contact_dict(contact))
    except Userlist.DoesNotExist:
        return api_response(404, "Contact Not Found")
    except Exception as e:
        return api_response(500, "Exception While Fetching Contact", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_total_contact(request):
    """GET /getTotalContact"""
    member_id = get_final_tenant_id(request=request)
    return api_response(200, "Total Contact Fetched Successfully.", CommonServices.total_contact_count(0,member_id))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_contact_list(request, groupId):
    """GET /getContactList/{groupId} mirroring findUserByGroup."""
    member_id = get_final_tenant_id(request=request)
    search_key = request.query_params.get('searchKey', '')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 25))
    
    # Grouping logic for duplicate detection matching Java repo/service
    dup_emails = set(Userlist.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(member_id), status='Subscribed', badEmail__in=['N', 'B', 'D'], optId__isnull=True)
                     .exclude(email__isnull=True).exclude(email='')
                     .values('email').annotate(cnt=Count('email')).filter(cnt__gt=1)
                     .values_list('email', flat=True))
    
    dup_phones = set(Userlist.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(member_id), badPhoneNumber='N', optId__isnull=True)
                     .filter(Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))
                     .exclude(phoneNumber__isnull=True).exclude(phoneNumber='')
                     .values('phoneNumber').annotate(cnt=Count('phoneNumber')).filter(cnt__gt=1)
                     .values_list('phoneNumber', flat=True))

    # Base queryset with ACTIVE_CONTACT_FILTER
    base_qs = Userlist.objects.filter(ACTIVE_CONTACT_FILTER, memberId=get_client_id_by_tenant_id(member_id), groupId=groupId)
    
    qs = base_qs
    if search_key:
        enc_search = search_key
        qs = qs.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=enc_search))
    
    # Dynamic sorting
    sort_param = request.query_params.get('sort', 'firstName,asc')
    field, direction = sort_param.split(',') if ',' in sort_param else (sort_param, 'asc')
    if direction.lower() == 'desc':
        field = f'-{field}'
    
    total_elements = qs.count()
    contacts = qs.order_by(field)[page*size : (page+1)*size]
    
    return api_response(200, "Contact Fetched Successfully.", {
        "contactHeader": get_contact_header_dict(groupId),
        "getNumber": page,
        "totalContact": total_elements,
        "getSize": size,
        "contact": [format_contact_dict(c, duplicate_emails=dup_emails, duplicate_phones=dup_phones) for c in contacts],
        "getTotalPages": math.ceil(total_elements / size) if size > 0 else 0,
        "contactHeaderKey": get_contact_header_key_list(groupId)
    })

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def find_user_by_group(request, groupId, memberId):
    """GET /findUserByGroup/{groupId}/{memberId} mirroring repository findContactsByGroupId."""
    contacts = Userlist.objects.filter(ACTIVE_CONTACT_FILTER, memberId=get_client_id_by_tenant_id(memberId), groupId=groupId).order_by('firstName')
    return api_response(200, "Success", [format_contact_dict(c) for c in contacts])

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def find_duplicate_user_by_group(request, groupId, memberId):
    """GET /findDuplicateUserByGroup/{groupId}/{memberId}."""
    search_key = request.query_params.get('searchKey', '')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 25))
    
    # Ported duplicate identification logic
    email_dupes = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId), groupId=groupId, status='Subscribed', badEmail__in=['N','B','D']).exclude(email__isnull=True).exclude(email='').values('email').annotate(c=Count('emailId')).filter(c__gt=1)
    phone_dupes = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId), groupId=groupId, badPhoneNumber='N').exclude(phoneNumber__isnull=True).exclude(phoneNumber='').values('phoneNumber').annotate(c=Count('emailId')).filter(c__gt=1)
    
    dup_emails = [d['email'] for d in email_dupes]
    dup_phones = [d['phoneNumber'] for d in phone_dupes]
    
    qs = Userlist.objects.filter(ACTIVE_CONTACT_FILTER, memberId=get_client_id_by_tenant_id(memberId), groupId=groupId).filter(Q(email__in=dup_emails) | Q(phoneNumber__in=dup_phones))
    
    if search_key:
        enc_search = search_key
        qs = qs.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=enc_search))
        
    total_elements = qs.count()
    contacts = qs.order_by('firstName')[page*size : (page+1)*size]
    
    return api_response(200, "Success", {
        "contact": [format_contact_dict(c) for c in contacts],
        "totalContact": total_elements,
        "getTotalPages": math.ceil(total_elements / size) if size > 0 else 0,
        "getNumber": page,
        "getSize": size
    })

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_duplicate_contact_list(request, groupId):
    """GET /getDuplicateContactList/{groupId}/ mirroring findDuplicateUserByGroup."""
    member_id = get_final_tenant_id(request=request)
    search_key = request.query_params.get('searchKey', '')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 25))
    
    # Pre-calculate duplicate sets for the group (Java GroupServiceImpl.java/ContactServiceImpl.java)
    dup_emails = set(Userlist.objects.filter(groupId=groupId, memberId=member_id, status='Subscribed', badEmail__in=['N', 'B', 'D'], optId__isnull=True)
                     .exclude(email__isnull=True).exclude(email='')
                     .values('email').annotate(cnt=Count('email')).filter(cnt__gt=1)
                     .values_list('email', flat=True))
    
    dup_phones = set(Userlist.objects.filter(groupId=groupId, memberId=member_id, badPhoneNumber='N', optId__isnull=True)
                     .filter(Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))
                     .exclude(phoneNumber__isnull=True).exclude(phoneNumber='')
                     .values('phoneNumber').annotate(cnt=Count('phoneNumber')).filter(cnt__gt=1)
                     .values_list('phoneNumber', flat=True))

    # Base queryset for duplicates
    base_qs = Userlist.objects.filter(groupId=groupId, memberId=member_id, optId__isnull=True).filter(
        Q(email__in=dup_emails) | Q(phoneNumber__in=dup_phones)
    ).filter(
        (Q(badEmail__in=['N', 'B', 'D']) & Q(status='Subscribed')) |
        (Q(badPhoneNumber='N') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True)))
    )
    
    qs = base_qs
    if search_key:
        enc_search = search_key
        qs = qs.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=enc_search))
        
    # Dynamic sorting
    sort_param = request.query_params.get('sort', 'firstName,asc')
    field, direction = sort_param.split(',') if ',' in sort_param else (sort_param, 'asc')
    if direction.lower() == 'desc':
        field = f'-{field}'
        
    total_elements = qs.count()
    contacts = qs.order_by(field)[page*size : (page+1)*size]
    
    return api_response(200, "Duplicate Contact Fetched Successfully.", {
        "contactHeader": get_contact_header_dict(groupId),
        "getNumber": page,
        "totalContact": total_elements,
        "getSize": size,
        "contact": [format_contact_dict(c, duplicate_emails=dup_emails, duplicate_phones=dup_phones) for c in contacts],
        "getTotalPages": math.ceil(total_elements / size) if size > 0 else 0,
        "contactHeaderKey": get_contact_header_key_list(groupId)
    })

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def remove_duplicate_contact(request, groupId):
    """DELETE /removeDuplicateContact/{groupId}."""
    member_id = get_final_tenant_id(request=request)
    
    # Identification logic (ported from Java deleteDuplicateContacts)
    email_dupes = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=groupId).exclude(email__isnull=True).exclude(email='').values('email').annotate(c=Count('emailId')).filter(c__gt=1)
    deleted_count = 0
    for dup in email_dupes:
        ids = list(Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=groupId, email=dup['email']).order_by('emailId').values_list('emailId', flat=True))
        if len(ids) > 1:
            deleted, _ = Userlist.objects.filter(emailId__in=ids[1:]).delete()
            deleted_count += deleted

    phone_dupes = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=groupId).exclude(phoneNumber__isnull=True).exclude(phoneNumber='').values('phoneNumber').annotate(c=Count('emailId')).filter(c__gt=1)
    for dup in phone_dupes:
        ids = list(Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=groupId, phoneNumber=dup['phoneNumber']).order_by('emailId').values_list('emailId', flat=True))
        if len(ids) > 1:
            deleted, _ = Userlist.objects.filter(emailId__in=ids[1:]).delete()
            deleted_count += deleted

    if deleted_count > 0:
        check_duplicate_records(groupId, get_client_id_by_tenant_id(member_id))
        check_type_email(groupId, get_client_id_by_tenant_id(member_id))
        check_total_member(groupId, get_client_id_by_tenant_id(member_id))

    return api_response(200, "Duplicate Contacts Deleted Successfully.", {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_full_view(request, groupId, segmentId):
    """GET /getFullView/{groupId}/{segmentId}."""
    member_id = get_final_tenant_id(request=request)
    try:
        if segmentId > 0:
            segment = GroupSegment.objects.get(segId=segmentId, memberId=get_client_id_by_tenant_id(member_id))
            # Use raw query for complex segment logic
            contacts = Userlist.objects.raw(segment.segQuery)
        else:
            contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=groupId).order_by('firstName')
            
        return api_response(200, "Contact Fetched Successfully", {
            "contact": [format_contact_dict(c) for c in contacts],
            "contactHeaderKey": get_contact_header_key_list(groupId),
            "contactHeader": get_contact_header_dict(groupId)
        })
    except Exception as e:
        logger.error(f"GetFullView Error: {e}")
        return api_response(500, "Something went wrong. Please try again later.", {})

def _get_paginated_status_list(request, base_filter, msg):
    """Helper for status-based lists (bad emails, unsubscribed, etc.) matches BadEmailAndUnsubscribedDto."""
    member_id = get_final_tenant_id(request=request)
    search_key = request.query_params.get('searchKey', '')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 25))
    
    qs = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id)).filter(base_filter)
    if search_key:
        enc_search = search_key
        qs = qs.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=enc_search))
        
    # Dynamic sorting
    sort_param = request.query_params.get('sort', 'firstName,asc')
    field, direction = sort_param.split(',') if ',' in sort_param else (sort_param, 'asc')
    if direction.lower() == 'desc':
        field = f'-{field}'
        
    total_elements = qs.count()
    contacts = qs.order_by(field)[page*size : (page+1)*size]
    
    return api_response(200, msg, {
        "contact": [format_bad_email_dict(c) for c in contacts],
        "getTotalPages": math.ceil(total_elements / size) if size > 0 else 0,
        "getNumber": page,
        "getSize": size,
        "totalContact": total_elements
    })

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_bad_email(request):
    """GET /getBadEmail mirroring findBadEmail."""
    return _get_paginated_status_list(request, Q(badEmail__in=['Y', 'B']), "Bad Email Contact Fetched Successfully.")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_bad_sms(request):
    """GET /getBadSms mirroring findBadSms."""
    return _get_paginated_status_list(request, Q(badPhoneNumber='Y'), "Bad SMS Contact Fetched Successfully.")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_unsubscribed_contact_list(request):
    """GET /getUnsubscribedContactList mirroring findUnsubscribed."""
    return _get_paginated_status_list(request, Q(status='Unsubscribed'), "Unsubscribed Contact Fetched Successfully.")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_unsubscribed_sms_contact_list(request):
    """GET /getUnsubscribedSmsContactList mirroring findUnsubscribedSms."""
    return _get_paginated_status_list(request, Q(smsStatus='Unsubscribed'), "Unsubscribed Contact Fetched Successfully.")

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def move_contact_existing_group(request, newGroupId, selectionType):
    """PUT /moveContactExistingGroup/{newGroupId}/{selectionType} mirroring updateUserGroups."""
    member_id = get_final_tenant_id(request=request)
    data = request.data # Expects list of UsergroupDto
    if not data or not isinstance(data, list):
        return api_response(400, "Request body must be a list of UsergroupDto")
    
    old_gid = data[0].get('groupId')
    if selectionType == "all":
        qs = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=old_gid)
    else:
        ids = [item.get('emailId') for item in data if item.get('emailId')]
        qs = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), emailId__in=ids)
    
    qs.update(groupId=newGroupId)
    
    # Stats update for both groups
    for gid in {old_gid, newGroupId}:
        if gid:
            check_duplicate_records(gid, get_client_id_by_tenant_id(member_id))
            check_type_email(gid, get_client_id_by_tenant_id(member_id))
            check_total_member(gid, get_client_id_by_tenant_id(member_id))
            
    return api_response(200, "Contact Updated Successfully.", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def copy_contact_new_group(request, oldGroupId, selectionType):
    """POST /copyContactNewGroup/{oldGroupId}/{selectionType} mirroring copiedUser."""
    member_id = get_final_tenant_id(request=request)
    data = request.data # NewGroupCopyDto
    gn = data.get('groupName')
    if not gn: return api_response(400, "groupName is required")
    if Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id), grpGroupName=gn).exists():
        return api_response(500, "Group Name Already Exist")
    
    orig = Groups.objects.get(grpId=oldGroupId)
    ng = Groups.objects.create(grpGroupName=gn, grpClientId=get_client_id_by_tenant_id(member_id), grpLockGroup=orig.grpLockGroup, grpSegmentYn='N')
    
    # Copy UDFs
    udfs = Udf.objects.filter(groupId=oldGroupId)
    Udf.objects.bulk_create([Udf(groupId=ng.grpId, udf=u.udf, udfLabel=u.udfLabel) for u in udfs if u.udf])
    
    # Copy Contacts
    if selectionType == "all":
        contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=oldGroupId)
    else:
        ids = data.get('emailIds', [])
        contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), emailId__in=ids)
        
    new_objs = []
    for c in contacts:
        c.pk = None
        c.groupId = ng.grpId
        c.dateAdded = timezone.now()
        new_objs.append(c)
    
    if new_objs: Userlist.objects.bulk_create(new_objs)
    
    for gid in {oldGroupId, ng.grpId}:
        check_duplicate_records(gid, get_client_id_by_tenant_id(member_id))
        check_type_email(gid, get_client_id_by_tenant_id(member_id))
        check_total_member(gid, get_client_id_by_tenant_id(member_id))
        
    return api_response(200, "Contact Copied Successfully.", {"contact": "Contact Copied Successfully."})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_sms_polling_contact_list(request, groupId):
    """GET /getSmsPollingContactList/{groupId}."""
    member_id = get_final_tenant_id(request=request)
    search_key = request.query_params.get('searchKey', '')
    page = int(request.query_params.get('page', 0))
    size = int(request.query_params.get('size', 25))
    
    # Dynamic sorting
    sort_param = request.query_params.get('sort', 'firstName,asc')
    field, direction = sort_param.split(',') if ',' in sort_param else (sort_param, 'asc')
    if direction.lower() == 'desc':
        field = f'-{field}'

    # Calculate group-wide duplicate sets (Java GroupServiceImpl.java/ContactServiceImpl.java)
    dup_emails = set(Userlist.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(member_id), status='Subscribed', badEmail__in=['N', 'B', 'D'], optId__isnull=True)
                     .exclude(email__isnull=True).exclude(email='')
                     .values('email').annotate(cnt=Count('email')).filter(cnt__gt=1)
                     .values_list('email', flat=True))
    
    dup_phones = set(Userlist.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(member_id), badPhoneNumber='N', optId__isnull=True)
                     .filter(Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))
                     .exclude(phoneNumber__isnull=True).exclude(phoneNumber='')
                     .values('phoneNumber').annotate(cnt=Count('phoneNumber')).filter(cnt__gt=1)
                     .values_list('phoneNumber', flat=True))

    # Base queryset matching findPageSmsPollingContactsByGroupId (line 57 Repository)
    base_qs = Userlist.objects.filter(
        groupId=groupId, memberId=get_client_id_by_tenant_id(member_id), optId__isnull=True
    ).exclude(
        typeEmail__in=['email', 'pending']
    ).exclude(
        typeSms='sms'
    ).filter(
        (Q(badEmail__in=['N', 'B', 'D']) | (Q(badPhoneNumber='N') & Q(phoneNumber__isnull=False) & ~Q(phoneNumber='')))
    ).filter(
        (Q(status='Subscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
        (Q(status='Unsubscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
        (Q(status='Subscribed') & Q(smsStatus='Unsubscribed'))
    )

    qs = base_qs
    if search_key:
        enc_search = search_key
        qs = qs.filter(Q(firstName__icontains=search_key) | Q(lastName__icontains=search_key) | Q(email__icontains=enc_search))
    
    total_elements = qs.count()
    contacts = qs.order_by(field)[page*size : (page+1)*size]
    
    return api_response(200, "Contact Fetched Successfully.", {
        "contactHeader": get_contact_header_dict(groupId),
        "getNumber": page,
        "totalContact": total_elements,
        "getSize": size,
        "contact": [format_contact_dict(c, duplicate_emails=dup_emails, duplicate_phones=dup_phones) for c in contacts],
        "getTotalPages": math.ceil(total_elements / size) if size > 0 else 0,
        "contactHeaderKey": get_contact_header_key_list(groupId)
    })

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_contact_number_list(request, searchName):
    """GET /getContactNumberList/{searchName} mirroring ContactServiceImpl.java."""
    tenant_id = get_final_tenant_id(request=request)
    search_contact_list = []
    res_body = {"contactList": search_contact_list}
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        country_tenant = Country.objects.filter(country_id=tenant.ten_country).first()
        ten_call_code = country_tenant.cnt_code if country_tenant else ""
        tenant_phone = ""
        
        if tenant.ten_phone:
            phone = tenant.ten_phone
            tenant_phone = clean_me_number(phone)
            if country_tenant:
                tenant_phone = last_characters(tenant_phone, country_tenant.phone_max_length)
            tenant_phone = f"{ten_call_code}{tenant_phone}"

        # Fetch contacts - mirroring findContactNumberList (searching numbers, with group by)
        qs = Userlist.objects.filter(
            memberId=get_client_id_by_tenant_id(tenant_id),
            phoneNumber__isnull=False,
            phoneNumber__icontains=searchName
        ).values(
            'firstName', 'lastName', 'phoneNumber', 'country'
        ).annotate(emailId=Min('emailId')).values_list(
            'emailId', 'firstName', 'lastName', 'phoneNumber', 'country'
        )[:50]
        
        for c_id, f_name, l_name, phone_num, country_name in qs:
            first_name = f_name or ""
            last_name = l_name or ""
            phone_num = phone_num or ""
            country_name = country_name or ""
            
            country_client = Country.objects.filter(cnt_name__iexact=country_name).first()
            client_code = country_client.cnt_code if country_client else "+1"
            client_phone_number = ""
            
            if phone_num:
                client_phone_number = clean_me_number(phone_num)
                if country_client:
                    client_phone_number = last_characters(client_phone_number, country_client.phone_max_length)
                else:
                    client_phone_number = last_characters(client_phone_number, 10)
                client_phone_number = f"{client_code}{client_phone_number}"
                
            full_name = f"{first_name} {last_name}".strip()
            search_contact_list.append({
                "emailId": str(c_id),
                "value": full_name,
                "label": f"{full_name} ({client_phone_number})",
                "memberNumber": tenant_phone,
                "clientNumber": client_phone_number
            })
            
        res_body["contactList"] = search_contact_list
        return api_response(200, "Contact List Fetched Successfully", res_body)

    except Exception as e:
        logger.error(f"[ memberId : {tenant_id} ] GetContactNumberList Error: {e}")
        return api_response(500, "Exception While Fetching Contact", {"error": str(e)})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_contact_email_list(request, searchName):
    """GET /getContactEmailList/{searchName} mirroring ContactServiceImpl.java."""
    tenant_id = get_final_tenant_id(request=request)
    search_contact_list = []
    res_body = {"contactList": search_contact_list}
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        country_tenant = Country.objects.filter(country_id=tenant.ten_country).first()
        ten_call_code = country_tenant.cnt_code if country_tenant else ""
        tenant_phone = ""
        
        if tenant.ten_phone:
            phone = tenant.ten_phone
            tenant_phone = clean_me_number(phone)
            if country_tenant:
                tenant_phone = last_characters(tenant_phone, country_tenant.phone_max_length)
            tenant_phone = f"{ten_call_code}{tenant_phone}"

        temp_list = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), email__isnull=False).values(
            'firstName', 'lastName', 'email', 'country'
        ).annotate(emailId=Min('emailId')).values_list(
            'emailId', 'firstName', 'lastName', 'email', 'country'
        )
        
        for c_id, f_name, l_name, enc_email, country_name in temp_list:
            first_name = f_name or ""
            last_name = l_name or ""
            email = enc_email if enc_email else ""
            
            if searchName in email:
                search_contact_list.append({
                    "emailId": str(c_id),
                    "value": f"{first_name} {last_name}".strip(),
                    "label": f"{first_name} {last_name} ({email})".strip(),
                    "memberNumber": tenant_phone,
                    "clientEmail": email
                })
        
        res_body["contactList"] = search_contact_list
        return api_response(200, "Contact List Fetched Successfully", res_body)

    except Exception as e:
        logger.error(f"[ memberId : {tenant_id} ] GetContactEmailList Error: {e}")
        return api_response(500, "Exception While Fetching Contact", {"error": str(e)})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def check_optin(request):
    """POST /checkOptin."""
    data = request.data
    fn, ln, email = data.get('firstName'), data.get('lastName'), data.get('email')
    if not all([fn, ln, email]) or "@" not in email:
        return api_response(500, "Something went wrong. Please check your field values.")
    return api_response(200, f"You are successfully optin with {email}.")

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_download_contact_file(request, groupId):
    """GET /getDownloadContactFile/{groupId} mirroring downloadContacts."""
    member_id = get_final_tenant_id(request=request)
    try:
        contacts = Userlist.objects.filter(ACTIVE_CONTACT_FILTER, memberId=get_client_id_by_tenant_id(member_id), groupId=groupId).order_by('firstName')
        group = get_object_or_404(Groups, grpId=groupId)
        file_name = f"{group.grpGroupName}.csv"
        # Ensure directory exists in media root or similar
        dir_path = settings.CSV_DOWNLOAD_DIR
        print(f"Directory Path: {dir_path}")
        if not os.path.exists(dir_path): os.makedirs(dir_path)
        file_path = os.path.join(dir_path, file_name)
        headerMap = ["First_Name", "Last_Name", "Email", "Phone", "Mobile Number", "Gender", "Birthday", "Street_Address1", "Street_Address2", "City", "State", "Zip","Country", "Language"]

        list1 = [ "firstName", "lastName", "email", "phone", "phoneNumber", "gender", "birthday", "streetAddress1", "streetAddress2", "city", "stateProvRegion", "zipPostalCode", "country", "usDefaultLanguage"]

        udfList = Udf.objects.filter(groupId=groupId)
        i=1
        for udf in udfList:
            headerMap.append(udf.udf)
            list1.append(f"udf{i}")
            i=i+1
        # headers = get_contact_header_key_list(groupId)
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headerMap)
            writer.writeheader()
            for c in contacts:
                # Format each row to match matching DTO fields
                row = format_contact_dict(c)
                # writer.writerow({k: row.get(k) for k in list1})
                # Filter row to only include keys in header
                writer.writerow({headerMap[i]: row.get(list1[i]) for i in range(len(headerMap))})
                
        return api_response(200, "Export Contact Successfully.", {"filePath": f"{settings.SITE_URL}csv_download/{file_name}"})
    except Exception as e:
        logger.error(f"Download Error: {e}")
        return api_response(500, "Something went wrong.")


@permission_classes([WhitelistPermission])
def get_download_not_group_contact_file(request, filterData):
    """GET /getDownloadNotGroupContactFile/{filter}."""
    member_id = get_final_tenant_id(request=request)
    try:
        qs = QuerySet(model=Userlist)
        # filter can be 'badEmail', 'badSms', 'unsubscribed'
        if filterData in ['badEmail', 'badSms', 'unsubscribed', 'unsubscribedEmail', 'unsubscribedSms']:
            if filterData == 'badEmail': qs = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), badEmail__in=['Y', 'B'])
            elif filterData == 'badSms': qs = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), badPhoneNumber='Y')
            elif filterData in ['unsubscribed', 'unsubscribedEmail']: qs = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), status='Unsubscribed')
            elif filterData == 'unsubscribedSms': qs = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), smsStatus='Unsubscribed')
        else: return api_response(400, "Invalid filter")
        
        file_name = f"export_csv_{member_id}.csv"
        dir_path = settings.CSV_DOWNLOAD_DIR
        print(f"Directory Path: {dir_path}")
        if not os.path.exists(dir_path): os.makedirs(dir_path)
        file_path = os.path.join(dir_path, file_name)
        
        # Use a default header for non-group exports (firstName, lastName, email, phone)
        headers = ["firstName", "lastName", "email", "phoneNumber", "status", "smsStatus"]
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for c in qs.order_by('firstName'):
                row = format_contact_dict(c)
                writer.writerow({k: row.get(k) for k in headers})
                
        return api_response(200, "Export Contact Successfully.", {"filePath": f"{settings.SITE_URL}csv_download/{file_name}"})
    except Exception as e:
        logger.error(f"Download Not Group Error: {e}")
        return api_response(500, "Something went wrong.")

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def add_invite_by_url_contact(request):
    """POST /addInviteByUrlContact."""
    # reCAPTCHA verification (from query param or body to match Java's hybrid Params/Body)
    rc_token = request.query_params.get('recaptchaResponse') or request.data.get('recaptchaResponse') or request.data.get('reCaptchaToken')
    if rc_token:
        rc_res = reCaptchaService.verify(rc_token)
        if not rc_res.isSuccess():
            return api_response(500, "You Are Robot.")
    elif not settings.DEBUG: # In production, reCAPTCHA is mandatory
        return api_response(500, "Please select reCaptcha.")
        
    data = request.data.copy()
    if not data.get('email') and not data.get('phoneNumber'):
        return api_response(500, "Please Enter Email Address / Mobile Number")
        
    # Invitations usually don't have memberId in request but logic needs one
    # If memberId is 0 or missing, it might use a default or extract from context
    member_id = data.get('memberId', 0)
    result = _create_and_update_user_list(data, member_id)
    if result.get('error'):
        return api_response(500, result['error'])
    return api_response(200, "Contact Added", result)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_group_contact(request, memberId, groupId):
    """GET /countTotalGroupContact/{memberId}/{groupId} mirroring findContactsCountByGroupId."""
    count = Userlist.objects.filter(ACTIVE_CONTACT_FILTER, memberId=get_client_id_by_tenant_id(memberId), groupId=groupId).count()
    return HttpResponse(str(count))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_group_contact_only_email(request, memberId, groupId):
    """GET /countTotalGroupContactOnlyEmail/{memberId}/{groupId}."""
    count = Userlist.objects.filter(ACTIVE_CONTACT_FILTER, memberId=get_client_id_by_tenant_id(memberId), groupId=groupId).exclude(email__isnull=True).exclude(email='').count()
    return HttpResponse(str(count))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_bad_email(request, memberId):
    """GET /countTotalBadEmail/{memberId}."""
    count = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId), badEmail__in=['Y', 'B']).count()
    return HttpResponse(str(count))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_bad_sms(request, memberId):
    """GET /countTotalBadSms/{memberId}."""
    count = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId), badPhoneNumber='Y').count()
    return HttpResponse(str(count))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_unsubscribed_email_contact(request, memberId):
    """GET /countTotalUnsubscribedEmailContact/{memberId}."""
    count = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId), status='Unsubscribed').count()
    return HttpResponse(str(count))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_duplicate_email_or_sms_contact(request, memberId, groupId):
    """GET /countTotalDuplicateEmailOrSmsContact/{memberId}/{groupId}."""
    dup_emails = Userlist.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(memberId), status='Subscribed', badEmail__in=['N','B','D']).values('email').annotate(c=Count('emailId')).filter(c__gt=1)
    dup_phones = Userlist.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(memberId), badPhoneNumber='N').values('phoneNumber').annotate(c=Count('emailId')).filter(c__gt=1)
    e_list = [d['email'] for d in dup_emails if d['email']]
    p_list = [d['phoneNumber'] for d in dup_phones if d['phoneNumber']]
    count = Userlist.objects.filter(ACTIVE_CONTACT_FILTER, memberId=get_client_id_by_tenant_id(memberId), groupId=groupId).filter(Q(email__in=e_list) | Q(phoneNumber__in=p_list)).count()
    return HttpResponse(str(count))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def find_sms_polling_user_by_group(request, groupId, memberId):
    """GET /findSmsPollingUserByGroup/{groupId}/{memberId}."""
    contacts = Userlist.objects.filter(
        groupId=groupId, memberId=get_client_id_by_tenant_id(memberId), optId__isnull=True
    ).exclude(
        typeEmail__in=['email', 'pending']
    ).exclude(
        typeSms='sms'
    ).filter(
        (Q(badEmail__in=['N', 'B', 'D']) | (Q(badPhoneNumber='N') & Q(phoneNumber__isnull=False) & ~Q(phoneNumber='')))
    ).filter(
        (Q(status='Subscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
        (Q(status='Unsubscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
        (Q(status='Subscribed') & Q(smsStatus='Unsubscribed'))
    ).order_by('firstName')
    return api_response(200, "Success", [format_contact_dict(c) for c in contacts])

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_sms_polling_group_contact(request, memberId, groupId):
    """GET /countTotalSmsPollingGroupContact/{memberId}/{groupId}."""
    count = Userlist.objects.filter(
        groupId=groupId, memberId=get_client_id_by_tenant_id(memberId), optId__isnull=True
    ).exclude(
        typeEmail__in=['email', 'pending']
    ).exclude(
        typeSms='sms'
    ).filter(
        (Q(badEmail__in=['N', 'B', 'D']) | (Q(badPhoneNumber='N') & Q(phoneNumber__isnull=False) & ~Q(phoneNumber='')))
    ).filter(
        (Q(status='Subscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
        (Q(status='Unsubscribed') & (Q(smsStatus='Subscribed') | Q(smsStatus__isnull=True))) |
        (Q(status='Subscribed') & Q(smsStatus='Unsubscribed'))
    ).count()
    return HttpResponse(str(count))

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def find_limit_contact_list(request, memberId, limit):
    """GET /findLimitContactList/{memberId}/{limit}."""
    contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId)).order_by('-dateRegistered')[:limit]
    return api_response(200, "Success", [format_contact_dict(c) for c in contacts])

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def find_unsubscribed_sms(request, memberId):
    """GET /findUnsubscribedSms/{memberId}."""
    contacts = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId), smsStatus='Unsubscribed').order_by('firstName')
    return api_response(200, "Success", [format_contact_dict(c) for c in contacts])

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def count_total_unsubscribed_sms_contact(request, memberId):
    """GET /countTotalUnsubscribedSmsContact/{memberId}."""
    count = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(memberId), smsStatus='Unsubscribed').count()
    return HttpResponse(str(count))

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_email_to_contact(request):
    res_body = {"error": ""}
    member_id = 0
    try:
        member_id = get_final_tenant_id(request=request)
        res_body = CommonServices.send_email_to_contact(member_id, request.data)
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] send_email_to_contact Error : {e}")
        res_body["error"] = "error"
    return api_response(200, "Email Sent Successfully." if not res_body["error"] else "Error", res_body)
