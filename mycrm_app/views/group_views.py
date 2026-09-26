from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from common_app.models import Groups, Udf, Userlist, GroupSegment, GroupSegmentField, TempCronUserListTotal, Clients
from common_app.custom_permissions import WhitelistPermission
from common_app.utils import get_final_tenant_id, api_response, get_client_id_by_tenant_id, get_tenant_id_by_client_id
from common_app.decrypt_string import DecryptString
from common_app.services import CommonServices
from mycrm_app.serializers import (UdfSerializer, SendOptInGroupDtoSerializer, InviteByUrlDtoSerializer)
from django.db import connection
from django.utils import timezone
from mycrm_app.views.group_segment_views import clean_oracle_sql
from django.db.models import Q
import re

import logging
logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupList(request):
    """
    Get a list of groups associated with a specific member.
    Matches Java GroupController.getGroupList
    """
    member_id = get_final_tenant_id(request=request)
    # Java GroupRepository.findAllData(memberId) orders by groupName
    groups = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id)).order_by('grpGroupName')
    
    res_body = {
        "group": [{"groupId": group.grpId, "groupName": group.grpGroupName} for group in groups],
        "totalContact": CommonServices.total_contact_uploaded(member_id)
    }
    return api_response(200, "Group Fetched Successfully.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupListWithCheckDuplicate(request):
    """
    Get a list of groups with duplicate check.
    Matches Java GroupController.getGroupListWithCheckDuplicate
    """
    member_id = get_final_tenant_id(request=request)
    
    # Matches Java GroupRepository.findAllData(memberId) orders by groupName
    groups = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id)).order_by('grpGroupName')
    
    final_list = []
    for gp in groups:
        # Serializer handles mapping of Group entity to GroupDto structure
        data = {
            "groupId": gp.grpId,
            "dateRegistered": gp.grpDateRegistered.strftime("%m/%d/%Y") if gp.grpDateRegistered else None,
            "groupName": gp.grpGroupName,
            "memberId": member_id,
            "duplicateRecords": gp.grpDuplicateRecordsYn,
            "encGroupId": DecryptString.set_enc_dec_user(str(gp.grpId), "", "Y"),
            "typeEmail": gp.grpTypeEmail,
            "lockGroup": gp.grpLockGroup,
            "segmentYN": gp.grpSegmentYn,
            "totalMember": gp.grpTotalMember,
        }
        
        try:
            cron_entry = TempCronUserListTotal.objects.filter(
                cronMemberId=get_client_id_by_tenant_id(member_id),
                cronGroupId=gp.grpId,
                cronProcessFinished='N'
            ).only('cronId').first()
            
            data['cronId'] = cron_entry.cronId if cron_entry else 0
        except Exception as e:
            logger.error(f"[ memberId : {member_id} ] GetGroupList Error : {e}")
            data['cronId'] = 0
            
        final_list.append(data)
        
    res_body = {
        "group": final_list
    }
    return api_response(200, "Group Fetched Successfully.", res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def saveGroup(request):
    """
    Save or update a group, including UDFs.
    Matches Java GroupController.saveGroup (lines 122-181)
    and GroupServiceImpl.saveGroup (lines 197-216).
    """
    member_id = get_final_tenant_id(request=request)
    data = request.data.copy()
    data['memberId'] = member_id
    
    group_id = data.get('groupId')
    if group_id is None:
        group_id = 0
    else:
        group_id = int(group_id)
    
    group_name = data.get('groupName')
    
    try:
        # 1. Check if group name already exists for this member
        query = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id), grpGroupName=group_name)
        if group_id != 0:
            query = query.exclude(grpId=group_id)
        
        if query.exists():
            return api_response(304, "Group Name Already In Used.", {})

        # 2. Save or Update Group (Preservation logic matches GroupServiceImpl.saveGroup)
        if group_id == 0:
            group_saved = Groups(
                grpGroupName = data.get('groupName'),
                grpDateRegistered = timezone.now(),
                grpClientId = get_client_id_by_tenant_id(data.get('memberId')),
                grpLockGroup = 'N',
                grpSegmentYn = 'N',
                grpDuplicateRecordsYn = 'N',
                grpTypeEmail = 'unverified',
                grpTotalMember = 0
            )
            group_saved.save()
            success_msg = "Add Group Successfully."
        else:
            # Update group - preserve existing fields
            group_saved = get_object_or_404(Groups, grpId=group_id, grpClientId=get_client_id_by_tenant_id(member_id))
            group_saved.grpGroupName = data.get('groupName')
            group_saved.save()
            success_msg = "Update Group Successfully."

        # 3. Handle UDFs (Matches GroupController.saveGroup logic lines 146-165)
        new_group_id = group_saved.grpId
        if new_group_id > 0:
            udfs_data = data.get('udfs', [])
            if udfs_data:
                # Java uses distinct() on the list of DTOs
                seen_names = set()
                unique_udfs_data = []
                for u in udfs_data:
                    u_name = u.get('udf', '')
                    if u_name and u_name not in seen_names:
                        seen_names.add(u_name)
                        unique_udfs_data.append(u)
                
                i = 1
                for udf_dto in unique_udfs_data:
                    udf_name = udf_dto.get('udf', '').strip()
                    if udf_name:
                        # checkUdfExits(newGroupDto.getGroupId(), udf.getUdf())
                        exists = Udf.objects.filter(groupId=new_group_id, udf=udf_name).exists()
                        if not exists:
                            Udf.objects.create(
                                groupId=new_group_id,
                                udf=udf_name,
                                udfLabel=i
                            )
                        i += 1
            
            # Response matches Java logic based on request groupId
            return api_response(200, success_msg, {})
        else:
            return api_response(500, "Internal Server Error", {})
            
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] SaveGroup Error : {e}")
        return api_response(500, "Internal Server Error", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def chkDuplicateGroupName(request):
    """
    Check if a group with a specific name exists for a given member.
    """
    member_id = get_final_tenant_id(request=request)
    group_name = request.data.get('groupName')
    group_id = int(request.data.get('groupId', 0))
    
    if not group_name:
        return api_response(400, "Group name is required", {"exists": False})
    
    query = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id), grpGroupName=group_name)
    if group_id != 0:
        query = query.exclude(grpId=group_id)
        
    exists = query.exists()
    return api_response(200, "Status Fetched Successfully", exists)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getUDFlist(request, groupId):
    """
    Find a list of User Defined Fields (UDFs) associated with the specified group.
    """
    udf_keys = ["UL_FIRST_NAME", "UL_LAST_NAME", "UL_FULL_NAME", "UL_EMAIL", "UL_PHONE_NUMBER", "UL_PHONE", "UL_STREET_ADDRESS1", "UL_STREET_ADDRESS2", "UL_CITY", "UL_STATE_PROV_REGION", "UL_ZIP_POSTAL_CODE", "UL_GENDER", "UL_TAGS"]
    udf_values = ["First Name", "Last Name", "Full Name", "Email", "Mobile Number", "Phone", "Street Address1", "Street Address2", "City", "State", "Zip Code", "Gender", "Tags"]
    
    udf_list = []
    for key, value in zip(udf_keys, udf_values):
        udf_list.append({"key": key, "value": value})
        
    # Custom UDFs
    custom_udfs = Udf.objects.filter(groupId=groupId)
    for udf in custom_udfs:
        udf_list.append({
            "key": f"UL_UDF{udf.udfLabel}",
            "value": udf.udf
        })
        
    return api_response(200, "UDF List Fetched Successfully.", udf_list)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupById(request, groupId):
    """
    Retrieve a specific group by ID.
    """
    member_id = get_final_tenant_id(request=request)
    group = get_object_or_404(Groups, grpId=groupId, grpClientId=get_client_id_by_tenant_id(member_id))
    res_body = {
        "groupId": group.grpId,
        "groupName": group.grpGroupName,
        "memberId": get_tenant_id_by_client_id(group.grpClientId),
        "lockGroup": group.grpLockGroup,
        "segmentYn": group.grpSegmentYn,
        "duplicateRecordsYn": group.grpDuplicateRecordsYn,
        "typeEmail": group.grpTypeEmail,
        "totalMember": group.grpTotalMember,
        "dateRegistered": group.grpDateRegistered.strftime("%m/%d/%Y") if group.grpDateRegistered else None
    }
    return api_response(200, "Group Fetched Successfully.", res_body)

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteBulkGroup(request):
    """
    Delete multiple groups for a specific member.
    Matches Java GroupController.deleteBulkGroup
    """
    member_id = get_final_tenant_id(request=request)
    # Field name 'groupIds' matches BulkDeleteGroup DTO
    group_ids = request.data.get('groupIds', [])
    
    if not group_ids:
        return api_response(400, "No group IDs provided")

    try:
        # Synchronization with GroupServiceImpl.deleteBulkGroup logic
        
        # 1. Delete contacts (matches contactRepository.deleteAllByMemberIdAndGroupIdIn)
        Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId__in=group_ids).delete()
        
        # 2. Delete segment fields
        seg_ids = list(GroupSegment.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId__in=group_ids).values_list('segId', flat=True))
        GroupSegmentField.objects.filter(segId__in=seg_ids).delete()
        
        # 3. Delete segments
        GroupSegment.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId__in=group_ids).delete()
        
        # 4. Delete UDFs
        Udf.objects.filter(groupId__in=group_ids).delete()
        
        # 5. Delete groups (matches groupRepository.deleteAllByMemberIdAndGroupIdIn)
        Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id), grpId__in=group_ids).delete()
        
        return api_response(200, "Group Deleted Successfully.", {})
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] DeleteBulkGroup Error : {e}")
        return api_response(500, "Group Delete Failed", False)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupListCombo(request):
    """
    Retrieve a list of group names and IDs for combo box.
    Matches Java GroupController.getGroupListCombo
    """
    member_id = get_final_tenant_id(request=request)
    # Java uses GroupRepository.findAllData(memberId)
    groups = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id)).order_by('grpGroupName')
    res_body = {
        "group": [{"groupId": group.grpId, "groupName": group.grpGroupName} for group in groups],
        "totalContact": CommonServices.total_contact_uploaded(member_id)
    }
    return api_response(200, "Group Fetched Successfully.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupUDF(request, groupId):
    """
    GET /getGroupUDF/{groupId}
    """
    udfs = Udf.objects.filter(groupId=groupId)
    serializer = UdfSerializer(udfs, many=True)
    return api_response(200, "UDF Fetched Successfully.", {
        "groupId": groupId,
        "udfs": serializer.data
    })

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupUDFAuto(request: Request, groupId):
    """
    GET /getGroupUDFAuto/{groupId}
    """
    return getGroupUDF(request._request, groupId)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sendOptInGroup(request):
    """
    Django implementation of GroupController.sendOptInGroup
    """
    member_id = get_final_tenant_id(request=request)
    serializer = SendOptInGroupDtoSerializer(data=request.data)
    
    if not serializer.is_valid():
        return api_response(400, "Validation Error", serializer.errors)
        
    group_id = serializer.validated_data['groupId']
    opt_in_type = serializer.validated_data['optInType']
    email_ids = serializer.validated_data.get('emailIds', [])
    
    res_map = {}
    email_cnt = 0
    sms_cnt = 0
    
    # 1. Count contacts based on optInType
    # 1. Count contacts based on optInType
    if opt_in_type == "email" or opt_in_type == "both":
        if group_id > 0:
            email_cnt = CommonServices.findGroupEmailCount(member_id, group_id)
            if email_cnt == 0:
                res_map["error"] = "Email Address Is Blank For Group Contact(s)."
            else:
                res_map["msg"] = "Opt-In Message Is Sent To Group Contact(s)."
                CommonServices.updateOptInEmail(member_id, group_id)
                CommonServices.checkDuplicateRecords(group_id, member_id)
                CommonServices.checkTotalMember(group_id, member_id)
        else:
            if email_ids:
                email_cnt = CommonServices.findEmailCount(member_id, email_ids)
                if email_cnt == 0:
                    res_map["error"] = "Email Address Is Blank For Selected Contact(s)."
                else:
                    res_map["msg"] = "Opt-In Message Is Sent To Selected Contact(s)."
                    CommonServices.updateOptInEmailOnlyIds(member_id, email_ids)

    if opt_in_type == "sms" or opt_in_type == "both":
        if group_id > 0:
            sms_cnt = CommonServices.findGroupSmsCount(member_id, group_id)
            if sms_cnt == 0:
                res_map["error"] = "Mobile Number Is Blank For Selected Contact(s)."
            else:
                res_map["msg"] = "Opt-In Message Is Sent To Selected Contact(s)"
                CommonServices.updateOptInSms(member_id, group_id)
        else:
            if email_ids:
                sms_cnt = CommonServices.findSmsCount(member_id, email_ids)
                if sms_cnt == 0:
                    res_map["error"] = "Mobile Number Is Blank For Selected Contact(s)."
                else:
                    res_map["msg"] = "Opt-In Message Is Sent To Selected Contact(s)."
                    CommonServices.updateOptInSmsOnlyIds(member_id, email_ids)

    if opt_in_type == "both":
        if email_cnt == 0 and sms_cnt == 0:
            res_map["msg"] = ""
            if group_id > 0:
                res_map["error"] = "Email And Mobile Number Are Blank For Group Contact(s)."
            else:
                res_map["error"] = "Email And Mobile Number Are Blank For Selected Contact(s)."
        else:
            res_map["error"] = ""
            if group_id > 0:
                res_map["msg"] = "Opt-In Message Is Sent To Group Contact(s)."
            else:
                res_map["msg"] = "Opt-In Message Is Sent To Selected Contact(s)."

    return api_response(200, res_map.get("msg", "success") or res_map.get("error", "success"), res_map)


# --- Java-parity contact header helpers (matches GroupServiceImpl) ---

CONTACT_HEADER_KEYS = [
    "firstName", "lastName", "fullName", "email", "phoneNumber", "phone",
    "usDefaultLanguage", "streetAddress1", "streetAddress2", "city",
    "stateProvRegion", "zipPostalCode", "country", "birthday", "gender",
    "emailDomain", "dateRegistered", "status", "smsStatus", "optDate",
    "optBackInDate", "optOutDate", "tags"
]

CONTACT_HEADER_VALUES = [
    "First Name", "Last Name", "Full Name", "Email", "Mobile", "Phone",
    "Language", "Street Address1", "Street Address2", "City", "State",
    "Zip Code", "Country", "Birthday", "Gender", "Email Domain",
    "Registered Date", "Status", "SMS Status", "Opt Date",
    "Opt Back In Date", "Opt Out Date", "Tags"
]


def _find_contact_header_key_list(group_id):
    keys = list(CONTACT_HEADER_KEYS)
    udf_list = Udf.objects.filter(groupId=group_id)
    for udf in udf_list:
        keys.append(f"udf{udf.udfLabel}")
    return keys


def _find_contact_header_list(group_id):
    res_body = {}
    for i in range(len(CONTACT_HEADER_KEYS)):
        res_body[CONTACT_HEADER_KEYS[i]] = CONTACT_HEADER_VALUES[i]
    udf_list = Udf.objects.filter(groupId=group_id)
    for udf in udf_list:
        res_body[f"udf{udf.udfLabel}"] = udf.udf
    return res_body


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupUDFValueList(request, groupId, groupUDF):
    """
    GET /group/getGroupUDFValueList/{groupId}/{groupUDF}
    Find the distinct values of a specific UDF for contacts in a group.
    """
    member_id = get_final_tenant_id(request=request)
    
    contacts = Userlist.objects.filter(
        Q(groupId=groupId),
        Q(memberId=get_client_id_by_tenant_id(member_id)),
        Q(status='Subscribed'),
        Q(badEmail__in=['N', 'B', 'D']),
        Q(optId=0) | Q(optId__isnull=True)
    )

    # Map groupUDF to the model field (matching Java GroupServiceImpl.findUDFlistValue)
    UDF_FIELD_MAP = {
        "UL_FIRST_NAME": "firstName",
        "UL_LAST_NAME": "lastName",
        "UL_FULL_NAME": "fullName",
        "UL_EMAIL": "emailDomain",
        "UL_PHONE_NUMBER": "phoneNumber",
        "UL_PHONE": "phone",
        "UL_STREET_ADDRESS1": "streetAddress1",
        "UL_STREET_ADDRESS2": "streetAddress2",
        "UL_CITY": "city",
        "UL_STATE_PROV_REGION": "stateProvRegion",
        "UL_ZIP_POSTAL_CODE": "zipPostalCode",
        "UL_GENDER": "gender",
        "UL_TAGS": "tags",
    }

    udf_values = set()
    field_name = UDF_FIELD_MAP.get(groupUDF)

    if field_name:
        for c in contacts:
            val = getattr(c, field_name, None)
            if val is not None and str(val).strip() != '':
                udf_values.add(str(val))
    else:
        # Handle custom UDFs (udf1-udf10)
        for c in contacts:
            val = getattr(c, groupUDF, None)
            if val is not None and str(val).strip() != '':
                udf_values.add(str(val))

    return api_response(200, "UDF List Value Fetched Successfully.", sorted(list(udf_values)))


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupContactHeader(request, groupId):
    """
    GET /group/getGroupContactHeader/{groupId}
    """
    return api_response(200, "Header List Fetched Successfully.", _find_contact_header_list(groupId))


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupContactHeaderKey(request, groupId):
    """
    GET /group/getGroupContactHeaderKey/{groupId}
    """
    return api_response(200, "Header List Fetched Successfully.", _find_contact_header_key_list(groupId))


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def inviteByUrl(request):
    """
    GET /group/inviteByUrl?groupId=&subMemberId=&emailId=
    Encrypt groupId~memberId~subMemberId~emailId and return.
    """
    member_id = get_final_tenant_id(request=request)
    group_id = request.query_params.get('groupId')
    sub_member_id = request.query_params.get('subMemberId')
    email_id = request.query_params.get('emailId')

    raw = f"{group_id}~{member_id}~{sub_member_id}~{email_id}"
    encrypted = DecryptString.set_enc_dec_user(raw, "", "Y")
    return api_response(200, "Data Fetched Successfully.", {"inviteByUrl": encrypted})


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def getInviteByUrlData(request):
    """
    POST /group/getInviteByUrlData
    Decrypt the q param, return memberId, subMemberId, groupId, emailId, udfs, whiteListingLogo.
    """
    serializer = InviteByUrlDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Validation Error", serializer.errors)

    q = serializer.validated_data['q']
    decrypted = DecryptString.set_enc_dec_user(q, "display", "Y")
    parts = decrypted.split("~")

    group_id = int(parts[0])
    tenant_id = int(parts[1])
    sub_tenant_id = int(parts[2])
    email_id = int(parts[3])

    udfs = Udf.objects.filter(groupId=group_id)
    udf_data = UdfSerializer(udfs, many=True).data

    res_body = {
        "memberId": tenant_id,
        "subMemberId": sub_tenant_id,
        "groupId": group_id,
        "emailId": email_id,
        "udfs": udf_data,
        "cliLogo": ""
    }

    try:
        client = Clients.objects.get(cliTenantId=tenant_id)
        country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
        if country_setting and hasattr(country_setting, 'cnty_white_listing') and str(country_setting.cnty_white_listing).lower() == 'y':
            if client.cliLogo:
                res_body["cliLogo"] = client.cliLogo
    except Exception:
        pass

    return api_response(200, "Data Fetched Successfully.", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupFirstRecords(request, groupId):
    """
    GET /group/getGroupFirstRecords/{groupId}
    Retrieve the first record from a group, including contact details and UDFs.
    """
    member_id = get_final_tenant_id(request=request)
    res_body = {}
    try:
        # Apply active contact filters
        userlist = Userlist.objects.filter(
            Q(groupId=groupId),
            Q(memberId=get_client_id_by_tenant_id(member_id)),
            Q(status='Subscribed'),
            Q(badEmail__in=['N', 'B', 'D']),
            Q(optId=0) | Q(optId__isnull=True)
        ).first()
        
        if userlist is None:
            return api_response(200, "Fetched First Record Successfully.", res_body)

        res_body["First_Name"] = userlist.firstName
        res_body["Last_Name"] = userlist.lastName
        res_body["Full_Name"] = getattr(userlist, 'fullName', None)
        res_body["Email"] = userlist.email if userlist.email else ""
        res_body["Contact_No"] = userlist.phoneNumber
        res_body["Phone"] = userlist.phone

        udf_list = Udf.objects.filter(groupId=groupId)
        for udf in udf_list:
            label = udf.udfLabel
            if label and 1 <= label <= 10:
                udf_val = getattr(userlist, f'udf{label}', None) or ""
                udf_key = udf.udf.replace(" ", "_") if udf.udf else f"udf{label}"
                if udf.udf == "birthday":
                    udf_val = udf_val if udf_val else ""
                res_body[udf_key] = udf_val
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] FindGroupFirstRecords Error : {e}")

    return api_response(200, "Fetched First Record Successfully.", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupSmsTotalCount(request):
    """
    GET /group/getGroupSmsTotalCount?flagType=group|segment&id=<id>
    Calculate total SMS-eligible contacts for a group or segment.
    """
    member_id = get_final_tenant_id(request=request)
    flag_type = request.query_params.get('flagType', 'group')
    target_id = int(request.query_params.get('id', 0))
    res_body = {}

    try:
        total_member = 0
        if flag_type == 'group':
            sql = f"select count(UL_EMAIL_ID) from USER_LIST where UL_GROUP_ID={target_id} and UL_CLIENT_ID ={get_client_id_by_tenant_id(member_id)} and (UL_SMS_STATUS='Subscribed' or UL_SMS_STATUS is null) and UL_BAD_PHONE_NUMBER='N' and (UL_OPT_ID is null or UL_OPT_ID=0) and (UL_PHONE_NUMBER is not null)"
    
            with connection.cursor() as cursor:
                cursor.execute(sql)
                row = cursor.fetchone()
                total_member = row[0] if row else 0
        else:
            # Segment: use segment query to count SMS-eligible contacts
            try:
                segment = GroupSegment.objects.get(segId=target_id, memberId=get_client_id_by_tenant_id(member_id))
                with connection.cursor() as cursor:
                    count_sql = segment.segQuery.replace("select *", "SELECT count(*)")
                    cursor.execute(count_sql)
                    row = cursor.fetchone()
                    total_member = row[0] if row else 0
            except GroupSegment.DoesNotExist:
                total_member = 0

        res_body["totalMember"] = total_member
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetGroupSmsTotalCount Error : {e}")
        res_body["totalMember"] = 0

    return api_response(200, "Group Fetched Successfully.", res_body)


@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupContactCount(request, groupId):
    """
    GET /group/getGroupContactCount/{groupId}?segmentId=<optional>
    Matches Java GroupController.getGroupContactCount
    """
    member_id = get_final_tenant_id(request=request)
    segment_id = request.query_params.get('segmentId')
    res_body = {}

    try:
        group = get_object_or_404(Groups, grpId=groupId)
        # matches Java DTO field name 'segment'
        res_body["segment"] = group.grpSegmentYn
        
        if segment_id:
            segment_id = int(segment_id)
            try:
                seg = GroupSegment.objects.get(segId=segment_id, memberId=get_client_id_by_tenant_id(member_id))
                with connection.cursor() as cursor:
                    sql = re.sub(r'select\s+\*', 'SELECT count(*)', seg.segQuery, flags=re.IGNORECASE)
                    sql = clean_oracle_sql(sql)
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    res_body["contactCount"] = row[0] if row else 0
            except GroupSegment.DoesNotExist:
                res_body["contactCount"] = 0
        else:
            # Matches logic of GroupServiceImpl.getGroupContactCount
            res_body["contactCount"] = CommonServices.total_contact_count(groupId, member_id)
    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetGroupContactCount Error : {e}")
        res_body["contactCount"] = 0

    return api_response(200, "Group Contact Count Fetched Successfully.", res_body)

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getGroupFieldsList(request, groupId):
    """
    GET /group/getGroupFieldsList/{groupId}
    Retrieve a list of all fields (predefined + custom UDFs) for a group.
    """
    # This logic is almost identical to getUDFlist (which maps to Java findUDFlist)
    # Java's findGroupFieldsList and findUDFlist are very similar.
    hmudf = {
        "UL_FIRST_NAME": "First Name",
        "UL_LAST_NAME": "Last Name",
        "UL_EMAIL": "Email",
        "UL_PHONE_NUMBER": "Phone Number",
        "UL_PHONE": "Phone",
        "UL_STREET_ADDRESS1": "Street Address1",
        "UL_STREET_ADDRESS2": "Street Address2",
        "UL_CITY": "City",
        "UL_STATE_PROV_REGION": "State/Prov/Region",
        "UL_ZIP_POSTAL_CODE": "Zip/Postal Code",
        "UL_COUNTRY": "Country",
        "UL_BIRTHDAY": "Birthday",
        "UL_GENDER": "Gender",
        "UL_TAGS": "Tags"
    }

    res_field = []
    for key, val in hmudf.items():
        res_field.append({"key": key, "value": val})

    udf_list = Udf.objects.filter(groupId=groupId)
    for udf in udf_list:
        res_field.append({
            "key": f"UL_UDF{udf.udfLabel}",
            "value": udf.udf
        })

    return api_response(200, "Group Fields Fetched Successfully.", res_field)
