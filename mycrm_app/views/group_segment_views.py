from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from django.db import connection, transaction
from common_app.models import Groups, GroupSegment, GroupSegmentField, Udf
from common_app.custom_permissions import WhitelistPermission
from common_app.utils import (
    display_date, get_final_tenant_id,
    api_response, add_slashes, get_client_id_by_tenant_id
)
from mycrm_app.serializers import (
    GroupSegmentSerializer, BulkDeleteGroupSegmentSerializer
)
from django.utils import timezone
import re
import logging
logger = logging.getLogger(__name__)

ERROR_MSG = "Whoops! An Expected Error Has Occurred, But We Have Logged This Event And Working On It."

def clean_oracle_sql(sql):
    sql = re.sub(r'(\bfrom\b\s+\w+)\s+as\s+(\w+)', r'\1 \2', sql, flags=re.IGNORECASE)
    sql = re.sub(r'(\bjoin\b\s+\w+)\s+as\s+(\w+)', r'\1 \2', sql, flags=re.IGNORECASE)
    
    join_pattern = r'INNER\s+JOIN\s+tbl_usergroups\s+(?:AS\s+)?ug\s+ON\s+ug\.Email_Id\s*=\s*tul\.Email_Id'
    if re.search(join_pattern, sql, flags=re.IGNORECASE):
        sql = re.sub(join_pattern, '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bug\.Group_Id\b', 'tul.group_id', sql, flags=re.IGNORECASE)
        
    return sql

def _find_contact_header_key_list(group_id):
    """Get contact header keys list for group."""
    keys = [
        "firstName", "lastName", "fullName", "email", "phoneNumber", "phone",
        "usDefaultLanguage", "streetAddress1", "streetAddress2", "city",
        "stateProvRegion", "zipPostalCode", "country", "birthday", "gender",
        "emailDomain", "dateRegistered", "status", "smsStatus", "optDate",
        "optBackInDate", "optOutDate", "tags"
    ]
    udfs = Udf.objects.filter(groupId=group_id).order_by('udfLabel')
    for udf in udfs:
        keys.append(f"udf{udf.udfLabel}")
    return keys

def _find_contact_header_list(group_id):
    """Get contact header display map for group."""
    header_map = {
        "birthday": "Birthday",
        "lastName": "Last Name",
        "country": "Country",
        "emailDomain": "Email Domain",
        "stateProvRegion": "State",
        "gender": "Gender",
        "city": "City",
        "streetAddress1": "Street Address1",
        "fullName": "Full Name",
        "streetAddress2": "Street Address2",
        "dateRegistered": "Registered Date",
        "optOutDate": "Opt Out Date",
        "tags": "Tags",
        "firstName": "First Name",
        "phoneNumber": "Mobile",
        "zipPostalCode": "Zip Code",
        "optDate": "Opt Date",
        "phone": "Phone",
        "smsStatus": "SMS Status",
        "optBackInDate": "Opt Back In Date",
        "usDefaultLanguage": "Language",
        "email": "Email",
        "status": "Status"
    }
    udfs = Udf.objects.filter(groupId=group_id).order_by('udfLabel')
    for udf in udfs:
        header_map[f"udf{udf.udfLabel}"] = udf.udf
    return header_map

def _create_or_update_segment_logic(member_id, data):
    group_id = data.get('groupId')
    seg_id = data.get('segId')
    
    # 1. Delete old fields if updating
    if seg_id:
        GroupSegmentField.objects.filter(segId=seg_id).delete()
        
    # 2. Build Query
    sub_query = (
        "select * from USER_LIST WHERE UL_GROUP_ID = " + str(group_id) +
        " AND UL_CLIENT_ID = " + str(get_client_id_by_tenant_id(member_id)) +
        " AND (UL_BAD_EMAIL in ('N', 'B', 'D') OR (UL_BAD_PHONE_NUMBER = 'N' and length(UL_PHONE_NUMBER)>0)) " +
        "and ((UL_STATUS = 'Subscribed' and (UL_SMS_STATUS='Subscribed' or UL_SMS_STATUS is null)) " +
        "OR (UL_STATUS = 'Unsubscribed' and (UL_SMS_STATUS='Subscribed' or UL_SMS_STATUS is null)) " +
        "Or (UL_STATUS = 'Subscribed' and (UL_SMS_STATUS='Unsubscribed'))) " +
        "AND (UL_OPT_ID is null or UL_OPT_ID=0) AND  (   "
    )
    
    sub_field_query = ""
    fields_data = data.get('groupSegmentFieldDtos', [])
    # Sort fields by display order
    fields_data = sorted(fields_data, key=lambda x: x.get('segDisplayOrder', 0))
    
    for field_dto in fields_data:
        conditions = field_dto.get('segConditions')
        if conditions:
            sub_field_query += conditions + " "
            
        field_name = field_dto.get('segFieldName', '')
        if field_name == "Email":
            sub_field_query += "email_domain "
        else:
            sub_field_query += field_name + " "
            
        operator = field_dto.get('segFieldOperator', '')
        # add_slashes matches Java's CommonFunction.addSlashes
        field_value = add_slashes(field_dto.get('segFieldValue', ''))
        
        if operator.lower() in ["begins with", "ends with"]:
            sub_field_query += " like "
        elif operator.lower() in ["not begins with", "not ends with"]:
            sub_field_query += " not like "
        else:
            sub_field_query += operator
            
        if operator.lower() in ["like", "not like"]:
            sub_field_query += " '%" + field_value + "%' "
        elif operator.lower() in ["begins with", "not begins with"]:
            sub_field_query += " '" + field_value + "%' "
        elif operator.lower() in ["ends with", "not ends with"]:
            sub_field_query += " '%" + field_value + "' "
        else:
            sub_field_query += " '" + field_value + "' "
            
    seg_query = sub_query + sub_field_query + " )"
    
    # 3. Save/Update GroupSegment
    if seg_id:
        segment = get_object_or_404(GroupSegment, segId=seg_id)
        segment.segName = data.get('segName')
        segment.segQuery = seg_query
        segment.save()
    else:
        segment = GroupSegment.objects.create(
            segName=data.get('segName'),
            groupId=group_id,
            memberId=get_client_id_by_tenant_id(member_id),
            segQuery=seg_query,
            segDateAdded=timezone.now()
        )
        
    # 4. Save Fields
    for field_dto in fields_data:
        GroupSegmentField.objects.create(
            segId=segment.segId,
            segFieldName=field_dto.get('segFieldName'),
            segFieldOperator=field_dto.get('segFieldOperator'),
            segFieldValue=field_dto.get('segFieldValue'),
            segConditions=field_dto.get('segConditions'),
            segDisplayOrder=field_dto.get('segDisplayOrder')
        )
    return segment

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def addSegment(request):
    """
    Create a new group segment.
    """
    member_id = get_final_tenant_id(request=request)
    data = request.data
    group_id = data.get('groupId')
    
    if not group_id:
        return api_response(500, "groupId is required", {})

    # Validation matching Java GroupSegmentController:50-54
    field_dtos = data.get('groupSegmentFieldDtos', [])
    for field in field_dtos:
        if not field.get('segFieldName'):
            return api_response(500, "Please Select Segment Field", {})
        if not field.get('segFieldValue'):
            return api_response(500, "Please Select Segment Field Value", {})

    try:
        with transaction.atomic():
            Groups.objects.filter(grpId=group_id).update(grpSegmentYn='Y')
            
            segment = _create_or_update_segment_logic(member_id, data)
            
            res_body = {"segId": segment.segId}
            return api_response(200, "Segment Added Successfully.", res_body)
    except Exception as e:
        logger.error(f"CreateGroupSegment Error : {e}")
        return api_response(500, ERROR_MSG, {})

@api_view(['PUT'])
@permission_classes([WhitelistPermission])
def updateSegment(request, segmentId):
    """
    Update an existing group segment.
    """
    member_id = get_final_tenant_id(request=request)
    data = request.data.copy()
    data['segId'] = segmentId
    
    # Validation matching Java GroupSegmentController:71-75
    field_dtos = data.get('groupSegmentFieldDtos', [])
    for field in field_dtos:
        if not field.get('segFieldName'):
            return api_response(500, "Please Select Segment Field", {})
        if not field.get('segFieldValue'):
            return api_response(500, "Please Select Segment Field Value", {})

    try:
        with transaction.atomic():
            _create_or_update_segment_logic(member_id, data)
            return api_response(200, "Segment Updated Successfully.", {})
    except Exception as e:
        logger.error(f"UpdateGroupSegment Error : {e}")
        return api_response(500, ERROR_MSG, {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSegment(request, segmentId):
    """
    Retrieve a specific group segment.
    """
    try:
        segment = get_object_or_404(GroupSegment, segId=segmentId)
        serializer = GroupSegmentSerializer(segment)
        data = serializer.data
        # Update date format to match Java findSegment logic
        data['segAddedDate'] = display_date(segment.segDateAdded)
        return api_response(200, "Segment Fetched Successfully.", data)
    except Exception as e:
        logger.error(f"GetSegment Error : {e}")
        return api_response(500, ERROR_MSG, {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSegmentList(request, groupId):
    """
    Retrieve a list of group segments for a specific group.
    """
    member_id = get_final_tenant_id(request=request)
    try:
        segments = GroupSegment.objects.filter(groupId=groupId, memberId=get_client_id_by_tenant_id(member_id))
        
        final_data = []
        for seg in segments:
            seg_dto = {
                "segId": seg.segId,
                "segName": seg.segName,
                "totalMember": 0
            }
            try:
                # Direct SQL count matching Java logic
                with connection.cursor() as cursor:
                    # Robust replacement for count query
                    sql = re.sub(r'select\s+\*', 'SELECT count(*)', seg.segQuery, flags=re.IGNORECASE)
                    # Clean for Oracle
                    sql = clean_oracle_sql(sql)
                    cursor.execute(sql)
                    row = cursor.fetchone()
                    seg_dto['totalMember'] = row[0] if row else 0
            except Exception as e:
                logger.error(f"GetSegmentTotalMember Error for segId {seg.segId}: {e}")
                
            final_data.append(seg_dto)
                
        return api_response(200, "Segment Fetched Successfully.", final_data)
    except Exception as e:
        logger.error(f"GetSegmentList Error : {e}")
        return api_response(500, ERROR_MSG, {})

@api_view(['GET'])
@permission_classes([WhitelistPermission])
def getSegmentContactList(request, groupId, segmentId):
    """
    Retrieve a list of contact records based on the criteria defined by a group segment.
    """
    member_id = get_final_tenant_id(request=request)
    try:
        # 1. Fetch duplicate records criteria (from ContactRepository queries in Java)
        with connection.cursor() as cursor:
            # getEmailIdByGroupId
            cursor.execute("""
                SELECT UL_EMAIL FROM USER_LIST
                WHERE UL_GROUP_ID = %s AND UL_CLIENT_ID = %s AND UL_STATUS = 'Subscribed' 
                AND (UL_BAD_EMAIL in ('N', 'B', 'D') and (UL_OPT_ID is null or UL_OPT_ID=0)) 
                AND UL_EMAIL <> '' AND UL_EMAIL is not null 
                GROUP BY UL_EMAIL HAVING COUNT(*) > 1
            """, [groupId, get_client_id_by_tenant_id(member_id)])
            group_emails = {row[0] for row in cursor.fetchall()}

            # getPhoneNumberByGroupId
            cursor.execute("""
                SELECT UL_PHONE_NUMBER FROM USER_LIST
                WHERE UL_GROUP_ID = %s AND UL_CLIENT_ID = %s AND UL_STATUS = 'Subscribed' 
                AND (UL_BAD_PHONE_NUMBER in ('N', 'B', 'D') and (UL_OPT_ID is null or UL_OPT_ID=0)) 
                AND UL_PHONE_NUMBER <> '' AND UL_PHONE_NUMBER is not null 
                GROUP BY UL_PHONE_NUMBER HAVING COUNT(*) > 1
            """, [groupId, get_client_id_by_tenant_id(member_id)])
            group_phones = {row[0] for row in cursor.fetchall()}

        segment = get_object_or_404(GroupSegment, segId=segmentId)
        sql = clean_oracle_sql(segment.segQuery) + " ORDER BY UL_FIRST_NAME ASC"

        contact_list = []
        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [col[0].upper() for col in cursor.description]
            rows = cursor.fetchall()

            for row in rows:
                res = dict(zip(columns, row))
                user_dto = dict()
                user_dto['duplicateRecords'] = "N"

                user_dto['emailId'] = res.get('UL_EMAIL_ID')
                user_dto['memberId'] = res.get('UL_CLIENT_ID')
                user_dto['firstName'] = res.get('UL_FIRST_NAME')
                user_dto['lastName'] = res.get('UL_LAST_NAME')
                user_dto['fullName'] = res.get('UL_FULL_NAME')

                raw_email = res.get('UL_EMAIL')
                if raw_email:
                    user_dto['email'] = raw_email
                    if raw_email in group_emails:
                        user_dto['duplicateRecords'] = "Y"
                else:
                    user_dto['email'] = ""

                for i in range(1, 11):
                    user_dto[f'udf{i}'] = res.get(f'UL_UDF{i}')

                user_dto['status'] = res.get('UL_STATUS')
                user_dto['dateRegistered'] = res.get('UL_DATE_REGISTERED')
                user_dto['badEmail'] = res.get('UL_BAD_EMAIL')
                user_dto['isChecked'] = res.get('UL_IS_CHECKED')
                user_dto['optId'] = res.get('UL_OPT_ID')
                user_dto['bounceReason'] = res.get('UL_BOUNCE_REASON')
                user_dto['tempCronId'] = res.get('UL_TEMP_CRON_ID')

                birthday = res.get('UL_BIRTHDAY')
                if birthday:
                    user_dto['birthday'] = display_date(birthday)

                user_dto['smsStatus'] = res.get('UL_SMS_STATUS')
                user_dto['smsSid'] = res.get('UL_SMS_ID')
                user_dto['streetAddress1'] = res.get('UL_STREET_ADDRESS1')
                user_dto['streetAddress2'] = res.get('UL_STREET_ADDRESS2')
                user_dto['phone'] = res.get('UL_PHONE')
                user_dto['stateProvRegion'] = res.get('UL_STATE_PROV_REGION')
                user_dto['zipPostalCode'] = res.get('UL_ZIP_POSTAL_CODE')
                user_dto['country'] = res.get('UL_COUNTRY')
                user_dto['gender'] = res.get('UL_GENDER')
                user_dto['dateAdded'] = res.get('UL_DATE_ADDED')
                user_dto['dateLastModified'] = res.get('UL_DATE_LAST_MODIFIED')
                user_dto['tags'] = res.get('UL_TAGS')

                phone_number = res.get('UL_PHONE_NUMBER')
                user_dto['phoneNumber'] = phone_number
                if phone_number in group_phones:
                    user_dto['duplicateRecords'] = "Y"

                user_dto['emailDomain'] = res.get('UL_EMAIL_DOMAIN')
                user_dto['badPhoneNumber'] = res.get('UL_BAD_PHONE_NUMBER')
                user_dto['usDefaultLanguage'] = res.get('UL_US_DEFAULT_LANGUAGE')
                user_dto['isEmailValidate'] = res.get('UL_IS_EMAIL_VALIDATE')

                contact_list.append(user_dto)

        res_body = {
            "contactHeaderKey": _find_contact_header_key_list(groupId),
            "contactHeader": _find_contact_header_list(groupId),
            "contact": contact_list,
            "getTotalPages": None,
            "getNumber": None,
            "getSize": None,
            "totalContact": len(contact_list)
        }
        return api_response(200, "Segment Fetched Successfully.", res_body)

    except Exception as e:
        logger.error(f"[ memberId : {member_id} ] GetSegmentContactList Error : {e}")
        return api_response(500, ERROR_MSG, {})

@api_view(['DELETE'])
@permission_classes([WhitelistPermission])
def deleteBulkSegment(request):
    """
    Delete multiple group segments.
    """
    serializer = BulkDeleteGroupSegmentSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    seg_ids = serializer.validated_data.get('segIds', [])
    
    try:
        with transaction.atomic():
            # Find group IDs associated with these segments
            target_segments = GroupSegment.objects.filter(segId__in=seg_ids)
            group_ids = list(target_segments.values_list('groupId', flat=True).distinct())
            
            # Delete segments and their fields
            GroupSegmentField.objects.filter(segId__in=seg_ids).delete()
            target_segments.delete()
            
            for group_id in group_ids:
                count = GroupSegment.objects.filter(groupId=group_id).count()
                Groups.objects.filter(grpId=group_id).update(grpSegmentYn='N' if count == 0 else 'Y')
                
            return api_response(200, "Segment Deleted Successfully.", {})
    except Exception as e:
        logger.error(f"DeleteBulkSegment Error : {e}")
        return api_response(500, ERROR_MSG, {})
