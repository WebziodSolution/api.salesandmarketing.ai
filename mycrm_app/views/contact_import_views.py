import os
import re
import csv
import json
import logging
import pandas as pd
from typing import Any, Dict
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Count, Min, Max
from rest_framework.decorators import api_view, permission_classes
from common_app.custom_permissions import WhitelistPermission
from bs4 import BeautifulSoup
from common_app.telnyx_utils import send_sms_telnyx
from common_app.utils import (api_response, get_final_tenant_id, minutes_convert, trim_file_extension, header_filter,
                              uc_first, nl2br, strip_slashes, cron_send_campaign_content_remove, set_file_permissions,
                              get_tenants, get_phone_numbers_first, get_client_id_by_tenant_id,
                              get_tenant_id_by_client_id)
from common_app.models import (Groups, Udf, TempUserlist, TempCronUserListTotal, EmailVerification, ContactSendSmsLogs, Country, MyPages, SmsTemplates, UnsubscribeLogs, Userlist, CampaignTransaction, Clients)
from common_app.services import CommonServices, MailRequestDTO
from common_app.decrypt_string import DecryptString
from mycrm_app.serializers import (ImportContactDtoSerializer, HeaderFileMappingDtoSerializer, UpdateImportContactSerializer, OptOutDtoSerializer, OptOutDetailsDtoSerializer, OptInDtoSerializer, SendSubscribeLinkDtoSerializer, EmailVerificationGroupDtoSerializer, TempUserlistSerializer, UploadFileOrPicDtoSerializer)
import random
import time
import base64

logger = logging.getLogger(__name__)

# Constants from Java implementation
SELECTED_FIELDS = ["First Name", "Last Name", "Full Name", "Email", "Contact No", "Phone", "Language", "Gender", "Birthday", "Street Address1", "Street Address2", "City", "State", "Country", "Zip Code", "Date Added", "Opt In Date", "Date Last Modified", "Signup Source", "Tags", "Add this field"]
PHONE_NUMBER_LIST = ["mobilenumber", "mobileno", "mobile", "mobilephone", "contactnumber", "contactno", "contact", "cellnumber", "cellno", "cell", "cellphone", "phonenumber", "phoneno", "phonehome"]
EMAIL_LIST = ["emailaddressother", "emailaddress", "email"]

KEY_VALUE_FIELDS = {
    # DTO Field -> Model Field mapping
    "emailId": "emailId", "firstName": "firstName", "lastName": "lastName", "fullName": "fullName",
    "email": "email", "phoneNumber": "phoneNumber", "phone": "phone", "usDefaultLanguage": "usDefaultLanguage",
    "streetAddress1": "streetAddress1", "streetAddress2": "streetAddress2", "birthday": "birthday",
    "city": "city", "country": "country", "dateAdded": "dateAdded", "dateLastModified": "dateLastModified", "gender": "gender", "optDate": "optDate",
    "stateProvRegion": "stateProvRegion", "status": "status", "tags": "tags", "zipPostalCode": "zipPostalCode",
    "udf1": "udf1", "udf2": "udf2", "udf3": "udf3", "udf4": "udf4", "udf5": "udf5", "udf6": "udf6", "udf7": "udf7", "udf8": "udf8", "udf9": "udf9", "udf10": "udf10",
    
    # dbField -> Model Field mapping
    "UL_FIRST_NAME": "firstName", "UL_LAST_NAME": "lastName", "UL_FULL_NAME": "fullName",
    "UL_EMAIL": "email", "UL_US_DEFAULT_LANGUAGE": "usDefaultLanguage",
    "UL_STREET_ADDRESS1": "streetAddress1", "UL_STREET_ADDRESS2": "streetAddress2"
}

def remove_utf8_bom_string(s):
    if s.startswith('\ufeff'):
        return s[1:]
    return s

def excel_to_csv(path):
    """
    Python port of ExcelToCsv
    """
    if not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in ['.xlsx', '.xls']:
        output_path = trim_file_extension(path) + ".csv"
        try:
            df = pd.read_excel(path)
            df.to_csv(output_path, index=False, header=True)
            return output_path
        except Exception as e:
            logger.error(f"excel_to_csv Error: {e}")
            return None
    return None

def populate_headers_with_header_file(headers, group_id=None):
    """
    Python port of populateHeadersWithHeaderFile
    Matches sequential UDF mapping logic of Spring Boot.
    """
    query_headers = []
    data: Dict[str, Any] = {"error": "", "email": False, "phoneNumber": False}
    data_table_headers = {}
    
    k = 0
    for header in headers:
        h = header.lower()
        if "firstname" in h:
            query_headers.append("firstName")
            data_table_headers["firstName"] = "First Name"
        elif "lastname" in h:
            query_headers.append("lastName")
            data_table_headers["lastName"] = "Last Name"
        elif "fullname" in h:
            query_headers.append("fullName")
            data_table_headers["fullName"] = "Full Name"
        elif header_filter(h) in EMAIL_LIST:
            query_headers.append("email")
            data["email"] = True
            data_table_headers["email"] = "Email"
        elif header_filter(h) in PHONE_NUMBER_LIST:
            query_headers.append("phoneNumber")
            data["phoneNumber"] = True
            data_table_headers["phoneNumber"] = "Phone Number"
        elif "phone" in h:
            query_headers.append("phone")
            data_table_headers["phone"] = "Phone"
        elif "language" in h:
            query_headers.append("usDefaultLanguage")
            data_table_headers["usDefaultLanguage"] = "Language"
        elif "gender" in h:
            query_headers.append("gender")
            data_table_headers["gender"] = "Gender"
        elif "birthday" in h or "dob" in h:
            query_headers.append("birthday")
            data_table_headers["birthday"] = "Birthday"
        elif "streetaddress1" in h:
            query_headers.append("streetAddress1")
            data_table_headers["streetAddress1"] = "Street Address1"
        elif "streetaddress2" in h:
            query_headers.append("streetAddress2")
            data_table_headers["streetAddress2"] = "Street Address2"
        elif "city" in h:
            query_headers.append("city")
            data_table_headers["city"] = "City"
        elif "state" in h or "stateprovregion" in h or "province" in h:
            query_headers.append("stateProvRegion")
            data_table_headers["stateProvRegion"] = "State"
        elif any(x in h for x in ["zippostalcode", "zip", "zipcode", "postalcode"]):
            query_headers.append("zipPostalCode")
            data_table_headers["zipPostalCode"] = "Zipcode"
        elif "region" in h:
            query_headers.append("region")
            data_table_headers["region"] = "Region"
        elif "country" in h:
            query_headers.append("country")
            data_table_headers["country"] = "Country"
        elif "dateadded" in h:
            query_headers.append("dateAdded")
            data_table_headers["dateAdded"] = "Date Added"
        elif "datelastmodified" in h:
            query_headers.append("dateLastModified")
            data_table_headers["dateLastModified"] = "Date Added"
        elif "contactrating" in h:
            query_headers.append("contactRating")
            data_table_headers["contactRating"] = "Contact Rating"
        elif "optinipaddress" in h:
            query_headers.append("optInIPAddress")
            data_table_headers["optInIPAddress"] = "optInIPAddress"
        elif "optdate" in h:
            query_headers.append("optDate")
            data_table_headers["optDate"] = "optDate"
        elif "confirmip" in h:
            query_headers.append("confirmIP")
            data_table_headers["confirmIP"] = "confirmIP"
        elif "confirmdatetime" in h:
            query_headers.append("confirmDateTime")
            data_table_headers["confirmDateTime"] = "confirmDateTime"
        elif "optoutipaddress" in h:
            query_headers.append("optOutIpAddress")
            data_table_headers["optOutIpAddress"] = "optOutIpAddress"
        elif "latitude" in h:
            query_headers.append("latitude")
            data_table_headers["latitude"] = "Latitude"
        elif "longitude" in h:
            query_headers.append("longitude")
            data_table_headers["longitude"] = "Longitude"
        elif "gmtoff" in h:
            query_headers.append("gmtOff")
            data_table_headers["gmtOff"] = "GMT Off"
        elif "dstoff" in h:
            query_headers.append("dstOff")
            data_table_headers["dstOff"] = "DST Off"
        elif "timezone" in h:
            query_headers.append("timeZone")
            data_table_headers["timeZone"] = "Timezone"
        elif "notes" in h:
            query_headers.append("notes")
            data_table_headers["notes"] = "Notes"
        elif "tags" in h:
            query_headers.append("tags")
            data_table_headers["tags"] = "Tags"
        elif "cc" in h:
            query_headers.append("cc")
            data_table_headers["cc"] = "CC"
        elif "leid" in h:
            query_headers.append("leid")
            data_table_headers["leid"] = "LEID"
        elif "euid" in h:
            query_headers.append("euid")
            data_table_headers["euid"] = "EUID"
        elif "emailclientused" in h:
            query_headers.append("emailClientUsed")
            data_table_headers["emailClientUsed"] = "Email Client Used"
        elif "age" in h:
            query_headers.append("age")
            data_table_headers["age"] = "Age"
        elif "status" in h:
            query_headers.append("status")
            data_table_headers["status"] = "Status"
        elif "jobtitle" in h:
            query_headers.append("jobTitle")
            data_table_headers["jobTitle"] = "Job Title"
        elif "emailpermissionstatusother" in h:
            query_headers.append("emailPermissionStatusOther")
            data_table_headers["emailpermissionstatusother"] = "Email Permission Status Other"
        elif "emaillists" in h:
            query_headers.append("emailLists")
            data_table_headers["emailLists"] = "Email Lists"
        else:
            k += 1
            query_headers.append(f"udf{k}")
            data_table_headers[f"udf{k}"] = header

    if k > 10:
        data["error"] = "error"
        
    data["queryHeaders"] = query_headers
    data["dataTableHeaders"] = data_table_headers
    return data

def populate_import_contact(import_contact_dto, res_body, headers, with_header):
    """
    Python port of populateImportContact
    """
    data_map = populate_headers_with_header_file(headers, import_contact_dto.get('groupId'))
    if data_map["error"] == "":
        if data_map["email"] or data_map["phoneNumber"]:
            path = import_contact_dto['path']
            try:
                logger.info(f"Populate Import Contact for memberId: {import_contact_dto['memberId']}")
                df = pd.read_csv(path, skiprows=1 if with_header else 0, header=None)
                objs = []
                query_headers: list = data_map["queryHeaders"]
                
                for _, row in df.iterrows():
                    temp_user = TempUserlist(
                        memberId=get_client_id_by_tenant_id(import_contact_dto['memberId']),
                        transId=import_contact_dto['transId'],
                    )
                    for i, val in enumerate(row):
                        if i < len(query_headers) and query_headers[i]:
                            val_str = str(val) if not pd.isna(val) else None
                            setattr(temp_user, query_headers[i], val_str)
                    objs.append(temp_user)
                
                if objs:
                    logger.info(f"Bulk creating {len(objs)} TempUserlist records for memberId: {import_contact_dto['memberId']}")
                    TempUserlist.objects.bulk_create(objs, batch_size=100000)
                
                qs = TempUserlist.objects.filter(memberId=get_client_id_by_tenant_id(import_contact_dto['memberId']), transId=import_contact_dto['transId'])
                if qs.exists():
                    aggregate = qs.aggregate(min_id=Min('emailId'), max_id=Max('emailId'))
                    res_body["cronStartId"] = aggregate['min_id']
                    res_body["cronEndId"] = aggregate['max_id']
                else:
                    res_body["cronStartId"] = 0
                    res_body["cronEndId"] = 0

                # Regex matching Java's invalidEmailsList
                email_regex = r'^[a-zA-Z0-9][+a-zA-Z0-9._-]*@[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]*\.[a-zA-Z]{2,4}$'
                
                # Exclude empty/null emails from invalid list to match Spring Boot
                invalid_emails_qs = qs.exclude(email__regex=email_regex).exclude(Q(email='') | Q(email__isnull=True))
                
                # FullName logic matching Java
                temp_userlists = []
                for user in invalid_emails_qs:
                    full_name = ""
                    if user.firstName:
                        full_name += user.firstName
                    if user.lastName:
                        full_name += (" " if full_name else "") + user.lastName
                    
                    if not user.fullName or user.fullName.strip() == "":
                        user.fullName = full_name.strip()
                    
                    temp_userlists.append(user)

                res_body["body"] = TempUserlistSerializer(temp_userlists, many=True).data
                res_body["totalRecord"] = qs.count()
                res_body["invalidEmails"] = invalid_emails_qs.count()
                res_body["transId"] = import_contact_dto['transId']
                
                # isPhoneNumber check including both phoneNumber and phone
                res_body["isPhoneNumber"] = qs.filter(
                    Q(phoneNumber__isnull=False) & ~Q(phoneNumber='') | 
                    Q(phone__isnull=False) & ~Q(phone='')
                ).exists()

                res_body["dataTableHeaders"] = data_map.get("dataTableHeaders", {})
                
                # Final response re-ordering for parity with Spring Boot
                ordered_result = {
                    "isPhoneNumber": res_body.get("isPhoneNumber", False),
                    "emailVerificationPrice": res_body.get("emailVerificationPrice", []),
                    "dataTableHeaders": res_body.get("dataTableHeaders", {}),
                    "transId": res_body.get("transId", ""),
                    "filePath": res_body.get("filePath", ""),
                    "invalidEmails": res_body.get("invalidEmails", 0),
                    "cronStartId": res_body.get("cronStartId", 0),
                    "body": res_body.get("body", []),
                    "totalRecord": res_body.get("totalRecord", 0),
                    "cronEndId": res_body.get("cronEndId", 0)
                }
                res_body.clear()
                res_body.update(ordered_result)
                
            except Exception as e:
                logger.error(f"populate_import_contact Error: {e}")
                res_body["error"] = str(e)

def random_generation():
    """
    Python port of ContactImportImpl.randomGeneration
    Produces a 5-digit random integer.
    """
    r = random.Random(time.time() * 1000)
    return (1 + r.randint(0, 1)) * 10000 + r.randint(0, 10000)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def import_contact(request):
    """
    POST /contactImport/importContact
    Migrated from ContactImportController.importContact
    """
    member_id = get_final_tenant_id(request=request)
    
    serializer = ImportContactDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    import_contact_dto = serializer.validated_data
    import_contact_dto['memberId'] = member_id
    
    res_body = dict()
    res_body["filePath"] = trim_file_extension(import_contact_dto['path']) + ".csv"
    
    # Excel to CSV conversion (Java lines 228-232)
    csv_path = excel_to_csv(import_contact_dto['path'])
    if csv_path:
        if os.path.exists(import_contact_dto['path']):
            os.remove(import_contact_dto['path'])
        import_contact_dto['path'] = csv_path
        
    # Generate transId (Java line 233)
    import_contact_dto['transId'] = str(random_generation())

    # Remove Blank Columns (Java lines 235-279)
    try:
        df = pd.read_csv(import_contact_dto['path'], header=None)
        if not df.empty:
            header_row = df.iloc[0]
            # Identifies columns with non-empty headers (Java logic)
            cols_to_keep = [i for i, val in enumerate(header_row) if pd.notna(val) and str(val).strip() != '']
            df_filtered = df[cols_to_keep]
            df_filtered.to_csv(import_contact_dto['path'], index=False, header=False)
    except Exception as e:
        logger.error(f"ImportContact Remove Blank Column Error: {e}")

    message = "File Import Successfully."
    try:
        with open(import_contact_dto['path'], 'r', encoding='utf-8') as f:
            # Using pandas to read the first line reliably
            first_row_df = pd.read_csv(import_contact_dto['path'], nrows=1, header=None)
            if first_row_df.empty:
                return api_response(400, "Empty file")
            first_row = first_row_df.iloc[0].astype(str).tolist()
            
            # Header sanitization (Java line 290)
            headers = [header_filter(remove_utf8_bom_string(h)) for h in first_row]
            
        # Check if file has phone/email header (Java lines 292-297)
        phone_email_header = any(h in PHONE_NUMBER_LIST or h in EMAIL_LIST for h in headers)
        
        with_header = True
        if import_contact_dto.get('columnHeaders'):
            # Java lines 300-324
            non_headers = [header_filter(str(v)) for v in import_contact_dto['columnHeaders'].values()]
            phone_email = any(h in PHONE_NUMBER_LIST or h in EMAIL_LIST for h in non_headers)
            
            if "" in non_headers:
                res_body["error"] = "Please Select Field."
            elif len(set(non_headers)) < len(non_headers):
                res_body["error"] = "Same Header Name Is Not Allow."
            elif not phone_email:
                res_body["error"] = "Please Select Email Address / Mobile Number."
            else:
                with_header = False
                populate_import_contact(import_contact_dto, res_body, non_headers, with_header)
        elif phone_email_header:
            # Java line 326
            populate_import_contact(import_contact_dto, res_body, headers, with_header)
        else:
            # Java lines 328-336
            select_headers = {i+1: str(h).strip() for i, h in enumerate(first_row)}
            res_body["headers"] = SELECTED_FIELDS
            res_body["body"] = select_headers
            
    except Exception as e:
        logger.error(f"import_contact Error: {e}")
        # Java line 68
        return api_response(500, "Whoops, looks like something went wrong.", res_body)
        
    # Java Controller lines 69-78 logic
    if "error" in res_body:
        message = str(res_body["error"])
        del res_body["error"]
        if message == "error":
            return api_response(500, "Whoops, looks like something went wrong.", res_body)
        else:
            return api_response(204, message, res_body)
            
    return api_response(200, message, res_body)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def get_header_field_mapping(request):
    """
    POST /contactImport/getHeaderFieldMapping
    Migrated from ContactImportController.getHeaderFieldMapping
    """
    serializer = HeaderFileMappingDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    dto = serializer.validated_data
    path = dto['path']
    group_id = dto['groupId']
    quickbook = dto.get('quickbook', '').lower()
    salesforce = dto.get('salesforce', '').lower()
    trans_id = dto.get('transId')

    # Java line 539-543: Handling ExcelToCsv
    c_path = excel_to_csv(path)
    if c_path and quickbook != "yes" and salesforce != "yes":
        path = c_path
    
    # Java line 544-550: Fetch UDFs
    udfs = Udf.objects.filter(groupId=group_id)
    udf_list = [udf.udf for udf in udfs]
    
    # Java line 551-552: Add constant UDF options
    udf_list.append("Add This Field")
    udf_list.append("Do Not Add This Field")

    results = []
    try:
        # Java line 555: if quickbook.equals("yes") || salesforce.equals("yes")
        if quickbook == "yes" or salesforce == "yes":
            temp_user = TempUserlist.objects.filter(transId=trans_id).first()
            if temp_user:
                results.append(populate_contact_mapping_with_headers_dto("First Name", ["First Name"], temp_user.firstName, "First_Name"))
                results.append(populate_contact_mapping_with_headers_dto("Last Name", ["Last Name"], temp_user.lastName, "Last_Name"))
                results.append(populate_contact_mapping_with_headers_dto("Full Name", ["Full Name"], temp_user.fullName, "full_name"))
                results.append(populate_contact_mapping_with_headers_dto("Email", ["Email"], temp_user.email, "Email "))
                results.append(populate_contact_mapping_with_headers_dto("Mobile Number", ["Mobile Number"], temp_user.phoneNumber, "phoneNumber"))
                results.append(populate_contact_mapping_with_headers_dto("Phone", ["Phone"], temp_user.phone, "phone"))
                results.append(populate_contact_mapping_with_headers_dto("Language", ["Language"], temp_user.usDefaultLanguage, "us_default_language"))
                results.append(populate_contact_mapping_with_headers_dto("Street Address1", ["Street Address1"], temp_user.streetAddress1, "street_address1"))
                results.append(populate_contact_mapping_with_headers_dto("Street Address2", ["Street Address2"], temp_user.streetAddress2, "street_address2"))
                results.append(populate_contact_mapping_with_headers_dto("City", ["City"], temp_user.city, "city"))
                results.append(populate_contact_mapping_with_headers_dto("Country", ["Country"], temp_user.country, "country"))
                results.append(populate_contact_mapping_with_headers_dto("Zip Code", ["Zip Code"], temp_user.zipPostalCode, "zipPostalCode"))

                if quickbook == "yes":
                    results.append(populate_contact_mapping_with_headers_dto("Tags", ["Tags"], temp_user.tags, "tags"))
        else:
            # Java line 597: BufferedReader logic
            with open(str(path), 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                headers_display = next(reader)
                eg = next(reader, [""] * len(headers_display))
                
                # Java line 627-638: Header processing
                if dto.get('columnHeaders'):
                    headers = [header_filter(h) for h in dto['columnHeaders']]
                    headers_display = dto['columnHeaders']
                else:
                    headers = [header_filter(h) for h in headers_display]
                
                # Java line 647-651: ensure eg matches headers length
                if len(headers) > len(eg):
                    eg.extend([""] * (len(headers) - len(eg)))

                # Java line 652: Mapping loop
                for i, h in enumerate(headers):
                    val = eg[i] if i < len(eg) else ""
                    if "firstname" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["First Name"], val, "First_Name"))
                    elif "lastname" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Last Name"], val, "Last_Name"))
                    elif "fullname" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Full Name"], val, "full_name"))
                    elif header_filter(h) in EMAIL_LIST:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Email"], val, "Email"))
                    elif header_filter(h) in PHONE_NUMBER_LIST:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Mobile Number"], val, "phoneNumber"))
                    elif "phone" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Phone"], val, "phone"))
                    elif "language" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Language"], val, "us_default_language"))
                    elif "gender" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Gender"], val, "gender"))
                    elif "birthday" in h or "dob" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Birthday"], val, "birthday"))
                    elif "streetaddress1" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Street Address1"], val, "street_address1"))
                    elif "streetaddress2" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Street Address2"], val, "street_address2"))
                    elif "city" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["City"], val, "city"))
                    elif "state" in h or "stateprovregion" in h or "province" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["State Proven Region"], val, "stateProvRegion"))
                    elif any(x in h for x in ["zip", "zipcode", "postalcode"]):
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Zip Code"], val, "zipPostalCode"))
                    elif "region" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Region"], val, "region"))
                    elif "country" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Country"], val, "country"))
                    elif "dateadded" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Date Added"], val, "dateAdded"))
                    elif "datelastmodified" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Last Date Modified"], val, "dateLastModified"))
                    elif "contactrating" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Contact Rating"], val, "contactRating"))
                    elif "optinipaddress" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Opt In Ip Address"], val, "optInIPAddress"))
                    elif "optdate" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Opt In Date"], val, "optDate"))
                    elif "confirmip" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Confirm Ip"], val, "confirmIP"))
                    elif "confirmdatetime" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Confirm Date Time"], val, "confirmDateTime"))
                    elif "optoutipaddress" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Opt Out Ip Address"], val, "optOutIpAddress"))
                    elif "latitude" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Latitude"], val, "latitude"))
                    elif "longitude" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Longitude"], val, "longitude"))
                    elif "gmtoff" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["GMTOff"], val, "gmtOff"))
                    elif "dstoff" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["DSTOff"], val, "dstOff"))
                    elif "timezone" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Timezone"], val, "timeZone"))
                    elif "notes" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Notes"], val, "notes"))
                    elif "tags" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Tags"], val, "tags"))
                    elif "cc" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["CC"], val, "CC"))
                    elif "leid" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["LEID"], val, "LEID"))
                    elif "euid" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["EUID"], val, "EUID"))
                    elif "emailclientused" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Email Client Used"], val, "emailClientUsed"))
                    elif "age" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Age"], val, "age"))
                    elif "status" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Status"], val, "Status"))
                    elif "jobtitle" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Job Title"], val, "jobTitle"))
                    elif "emailpermissionstatusother" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Email Permission Status - Other"], val, "emailPermissionStatusOther"))
                    elif "emaillists" in h:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], ["Email Lists"], val, "emailLists"))
                    else:
                        results.append(populate_contact_mapping_with_headers_dto(headers_display[i], udf_list, val, None))

    except Exception as e:
        logger.error(f"get_header_field_mapping Error: {e}")
        return api_response(500, "Operation failed", str(e))

    return api_response(200, "Contact Mapping Fetched Successfully.", results)


def populate_contact_mapping_with_headers_dto(key, value, eg, db_field):
    return {
        "key": key,
        "value": value,
        "eg": eg,
        "dbField": db_field
    }



@api_view(['GET'])
@permission_classes([WhitelistPermission])
def get_selected_headers(request):
    """
    GET /contactImport/selectHeaders
    Migrated from ContactImportController.getSelectedHeaders
    """
    return api_response(200, "Contact Mapping Fetched Successfully.", SELECTED_FIELDS)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def add_temp_cron_contact(request):
    """
    POST /contactImport/addTempCronContact
    Migrated from ContactImportController.addTempCronContact
    """
    member_id = get_final_tenant_id(request=request)
    data = request.data
    
    res_body = {"countMessage": ""}

    try:
        # 1. Main Fields Processing
        main_fields = data.get('mainFields', {})
        temp_field = {}
        swap_columns = ""
        
        for main_field_key, value in main_fields.items():
            h1 = re.sub(r'[_+\- ]', '', main_field_key).lower()
            
            if "firstname" in h1:
                temp_field["First_Name"] = value
            elif "lastname" in h1:
                temp_field["Last_Name"] = value
            elif "fullname" in h1:
                temp_field["full_name"] = value
            elif header_filter(h1) in EMAIL_LIST:
                temp_field["Email"] = value
            elif "language" in h1:
                temp_field["us_default_language"] = value
            elif "gender" in h1:
                temp_field["gender"] = value
            elif "birthday" in h1 or "dob" in h1:
                temp_field["birthday"] = value
            elif "streetaddress1" in h1:
                temp_field["street_address1"] = value
            elif "streetaddress2" in h1:
                temp_field["street_address2"] = value
            elif "city" in h1:
                temp_field["city"] = value
            elif "state" in h1 or "province" in h1 or "stateprovregion" in h1:
                temp_field["stateProvRegion"] = value
            elif any(x in h1 for x in ["zippostalcode", "zip", "zipcode", "postalcode"]):
                temp_field["zipPostalCode"] = value
            elif "region" in h1:
                temp_field["region"] = value
            elif "country" in h1:
                temp_field["country"] = value
            elif "dateadded" in h1:
                temp_field["dateAdded"] = value
            elif "datelastmodified" in h1:
                temp_field["dateLastModified"] = value
            elif "contactrating" in h1:
                temp_field["contactRating"] = value
            elif "optinipaddress" in h1:
                temp_field["optInIPAddress"] = value
            elif "optdate" in h1:
                temp_field["optDate"] = value
            elif "confirmip" in h1:
                temp_field["confirmIP"] = value
            elif "confirmdatetime" in h1:
                temp_field["confirmDateTime"] = value
            elif "optoutipaddress" in h1:
                temp_field["optOutIpAddress"] = value
            elif "latitude" in h1:
                temp_field["latitude"] = value
            elif "longitude" in h1:
                temp_field["longitude"] = value
            elif "gmtoff" in h1:
                temp_field["gmtOff"] = value
            elif "dstoff" in h1:
                temp_field["dstOff"] = value
            elif "timezone" in h1:
                temp_field["timeZone"] = value
            elif "notes" in h1:
                temp_field["notes"] = value
            elif "tags" in h1:
                temp_field["tags"] = value
            elif "cc" in h1:
                temp_field["CC"] = value
            elif "leid" in h1:
                temp_field["LEID"] = value
            elif "euid" in h1:
                temp_field["EUID"] = value
            elif "emailclientused" in h1:
                temp_field["emailClientUsed"] = value
            elif "age" in h1:
                temp_field["age"] = value
            elif "status" in h1:
                temp_field["Status"] = value
            elif "jobtitle" in h1:
                temp_field["jobTitle"] = value
            elif "emailpermissionstatusother" in h1:
                temp_field["emailPermissionStatusOther"] = value
            elif header_filter(h1) in EMAIL_LIST:
                temp_field["emailLists"] = value
            elif h1 == "phone":
                temp_field["phone"] = value
            elif header_filter(h1) in PHONE_NUMBER_LIST:
                temp_field["phoneNumber"] = value

        for k, v in temp_field.items():
            swap_columns += f"{k}={v}\n"

        # 2. UDF Processing
        udf_req = data.get('udfs', {})
        requested_udfs_names = list(udf_req.values())
        requested_udfs_labels_in_data = list(udf_req.keys())
        
        cron_group_id = data.get('cronGroupId')
        existing_udfs = Udf.objects.filter(groupId=cron_group_id)
        existing_udf_names = [u.udf for u in existing_udfs]
        
        # Add new UDFs if they don't exist
        for udf_name in requested_udfs_names:
            if udf_name not in existing_udf_names:
                total_udfs = Udf.objects.filter(groupId=cron_group_id).count()
                if total_udfs < 10:
                    Udf.objects.create(
                        udf=udf_name,
                        groupId=cron_group_id,
                        udfLabel=total_udfs + 1
                    )
        
        # Build blankFieldsList and movesList
        blank_fields_list = ""
        moves_list = ""
        all_group_udfs = Udf.objects.filter(groupId=cron_group_id)
        
        # For movesList: map udfLabel to data index
        for data_idx_str, udf_name in udf_req.items():
            try:
                udf_obj = all_group_udfs.filter(udf=udf_name).first()
                if udf_obj:
                    moves_list += f"{udf_obj.udfLabel}:{data_idx_str}-"
            except Exception:
                pass
                
        # For blankFieldsList: fields 1-10 not in requested labels
        for i in range(1, 11):
            if str(i) not in requested_udfs_labels_in_data:
                blank_fields_list += f"TUL_UDF{i}=''"
                if i < 10: blank_fields_list += ","
        blank_fields_list = blank_fields_list.rstrip(',')

        # 3. Create TempCronUserListTotal
        temp_cron_user_list_total = TempCronUserListTotal(
            cronMemberId=get_client_id_by_tenant_id(member_id),
            cronGroupId=cron_group_id,
            transId=data.get('transId'),
            cronStartId=data.get('cronStartId'),
            cronEndId=data.get('cronEndId'),
            cronProcess='N',
            cronProcessFinished='N',
            cronCheckDuplicateYN=data.get('cronCheckDuplicateYN', 'N'),
            cronOptInYN=data.get('cronOptInYN', 'N'),
            cronEmailVerification=data.get('cronEmailVerification', 'N'),
            cronOptInMessage=data.get('cronOptInMessage', ''),
            swapColumns=swap_columns,
            moveList=moves_list,
            blankFieldsList=blank_fields_list
        )
        temp_cron_user_list_total.save()
        
        # 4. Success Response and Time Calculation
        count_contact = TempUserlist.objects.filter(memberId=get_client_id_by_tenant_id(data.get('memberId')), transId=data.get('transId')).count()
        minutes = 5 if count_contact <= 1000 else (int((count_contact + 2999) / 3000)) * 20
        res_body["countMessage"] = minutes_convert(minutes)
        
    except Exception as e:
        logger.error(f"add_temp_cron_contact Error: {e}")
        # Java line 116 logic
        res_body["error"] = "error"
        return api_response(204, "Whoops, looks like something went wrong.", res_body)

    if "error" in res_body:
        msg = str(res_body["error"])
        return api_response(204, msg, res_body)

    message = "We have successfully staged your contacts. For your safety, All data will be encrypted and tokenized. You will receive an email notification when it is complete. "
    if res_body["countMessage"]:
        message += f"The process should be complete in {res_body['countMessage']}."
    message += "\n\nWhile your data is loading, please ensure your email DNS settings are set at My Profile > Domain and Email Verification or start building your first Email Template."
    
    return api_response(200, message, res_body)

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def update_import_contact(request):
    """
    POST /contactImport/updateImportContact
    Migrated from ContactImportController.updateImportContact
    """
    member_id = get_final_tenant_id(request=request)
    serializer = UpdateImportContactSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    dto = serializer.validated_data
    field_to_update = KEY_VALUE_FIELDS.get(dto['key'])
    if not field_to_update:
        return api_response(400, "Invalid key")
    
    try:
        TempUserlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), emailId=dto['emailId']).update(**{field_to_update: dto['value']})
    except Exception as e:
        logger.error(f"update_import_contact Error: {e}")
        return api_response(500, "Update failed", str(e))
        
    return api_response(200, "Update Contact Successfully.", {})

@api_view(['POST'])
@permission_classes([WhitelistPermission])
def cancel_upload(request):
    """
    POST /contactImport/cancelUpload
    Migrated from ContactImportController.cancelUpload
    """
    try:
        trans_id = request.data.get('transId')
        file_path = request.data.get('filePath')
        
        if trans_id:
            TempUserlist.objects.filter(transId=trans_id).delete()
            TempCronUserListTotal.objects.filter(transId=trans_id).delete()
            
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            
        return api_response(200, "Cancel Successfully")
    except Exception as e:
        logger.error(f"CancelUpload Error: {str(e)}")
        return api_response(500, str(e))


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def contact_import_file(request):
    """
    POST /contactImport/contactImportFile
    Migrated from ContactImportController.importContactFile
    """
    serializer = UploadFileOrPicDtoSerializer(data=request.data)
    if not serializer.is_valid():
        return api_response(400, "Invalid data", serializer.errors)
    
    dto = serializer.validated_data
    if not dto['file']:
        return api_response(500, "Request must contains file")
    
    try:
        file_data = dto['file']
        # Remove data:type;base64, prefix if present
        if ',' in file_data:
            file_data = file_data.split(',')[1]
        
        decoded_bytes = base64.b64decode(file_data.replace(' ', ''))
        
        file_path = os.path.join(settings.CSV_STORE_DIR, dto['fileName'])
        
        # Ensure directory exists
        if not os.path.exists(settings.CSV_STORE_DIR):
            os.makedirs(settings.CSV_STORE_DIR)
            
        set_file_permissions(file_path, decoded_bytes)
        
        return api_response(200, "The File Uploaded Successfully", {"filePath": file_path})
        
    except Exception as e:
        logger.error(f"contact_import_file Error: {e}")
        return api_response(500, "Upload failed", str(e))


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def opt_out_details(request):
    """
    POST /contactImport/optOutDetails
    Migrated from ContactImportController.optOutDetails
    """
    serializer = OptOutDetailsDtoSerializer(data=request.data)
    if serializer.is_valid():
        res_body = opt_out_details_base(serializer.validated_data)
        if res_body.get('error') == "":
            return api_response(200, "Opt Out Details Successfully", res_body)
        else:
            return api_response(500, "Internal Server Error", res_body)
    return api_response(400, "Bad Request", serializer.errors)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def opt_in_details(request):
    """
    POST /contactImport/optInDetails
    Migrated from ContactImportController.optInDetails
    """
    serializer = OptOutDetailsDtoSerializer(data=request.data)
    if serializer.is_valid():
        dto = serializer.validated_data
        res_body_base = opt_out_details_base(dto)
        
        res_body = {
            "error": "",
            "optInDetails": res_body_base.get("optOutDetails"),
            "groupList": []
        }
        
        try:
            member_id = int(DecryptString.set_enc_dec_user(dto['encMemberId'], "display", "Y"))
            email_id = int(DecryptString.set_enc_dec_user(dto['encEmailId'], "display", "Y"))
            
            userlist = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), emailId=email_id).first()
            if not userlist:
                res_body["error"] = "User not found"
                return api_response(200, "Opt In Details Successfully", res_body)
            
            enc_email = userlist.email or ""
            phone_number = userlist.phoneNumber or userlist.phone or ""
            
            group_ids = set()
            
            if enc_email:
                email_unsubscribed_groups = Userlist.objects.filter(
                    memberId=get_client_id_by_tenant_id(member_id),
                    status='Unsubscribed', 
                    email=enc_email
                ).values_list('groupId', flat=True).distinct()
                group_ids.update(email_unsubscribed_groups)
                
            if phone_number:
                phone_unsubscribed_groups = Userlist.objects.filter(
                    memberId=get_client_id_by_tenant_id(member_id),
                    smsStatus='Unsubscribed'
                ).filter(
                    Q(phoneNumber=phone_number) | Q(phone=phone_number)
                ).values_list('groupId', flat=True).distinct()
                group_ids.update(phone_unsubscribed_groups)
            
            group_list = []
            if group_ids:
                groups = Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id), grpId__in=list(group_ids))
                for g in groups:
                    group_list.append({
                        "groupId": g.grpId,
                        "groupName": g.grpGroupName
                    })
            
            res_body["groupList"] = group_list
            return api_response(200, "Opt In Details Successfully", res_body)
            
        except Exception as e:
            logger.error(f"OptInDetails Error: {str(e)}")
            res_body["error"] = "error"
            return api_response(200, "Internal Server Error", res_body, sendErrorAs200=True)
            
    return api_response(400, "Bad Request", serializer.errors)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def opt_out(request):
    """
    POST /contactImport/optOut
    Migrated from ContactImportController.optOut
    """
    serializer = OptOutDtoSerializer(data=request.data)
    if serializer.is_valid():
        opt_out_dto = serializer.validated_data
        try:
            member_id = int(DecryptString.set_enc_dec_user(opt_out_dto['encMemberId'], "display", "Y"))
            group_id = int(DecryptString.set_enc_dec_user(opt_out_dto['encGroupId'], "display", "Y"))
            email_id = int(DecryptString.set_enc_dec_user(opt_out_dto['encEmailId'], "display", "Y"))
            
            userlist = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), emailId=email_id).first()
            if not userlist:
                return api_response(404, "User not found")

            email = ""
            if opt_out_dto.get('email'):
                email = opt_out_dto['email']

            opt_out_type = opt_out_dto.get('optOutType')

            if email and (opt_out_type == "email" or opt_out_type == "removeThisList"):
                Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=group_id, email=email).update(
                    status='Unsubscribed', optId=1
                )
                send_opt_out_details_email(userlist)
                check_duplicate_records(group_id, member_id)
                check_total_member(group_id, member_id)

            if email and opt_out_type == "removeAllList":
                Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), email=email).update(
                    status='Unsubscribed', optId=1
                )
                send_opt_out_details_email(userlist)
                
                group_ids = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), email=email).values_list('groupId', flat=True).distinct()
                for g_id in group_ids:
                    check_duplicate_records(g_id, member_id)
                    check_total_member(g_id, member_id)

            phone_number = opt_out_dto.get('phoneNumber', "")
            if phone_number and (opt_out_type == "phone" or opt_out_type == "removeThisList"):
                Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), groupId=group_id, phoneNumber=phone_number).update(
                    smsStatus='Unsubscribed', optId=1
                )
                send_opt_out_details_sms(userlist)

            if phone_number and opt_out_type == "removeAllList":
                Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), phoneNumber=phone_number).update(
                    smsStatus='Unsubscribed', optId=1
                )
                send_opt_out_details_sms(userlist)

            send_opt_out_admin_email(userlist)
            
            return api_response(200, "Opt Out Successfully")
        except Exception as e:
            logger.error(f"OptOut Error: {str(e)}")
            return api_response(500, "error")
    return api_response(400, "Bad Request", serializer.errors)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def opt_in(request):
    """
    POST /contactImport/optIn
    Migrated from ContactImportController.optIn
    """
    serializer = OptInDtoSerializer(data=request.data)
    if serializer.is_valid():
        opt_in_dto = serializer.validated_data
        try:
            member_id = int(DecryptString.set_enc_dec_user(opt_in_dto['encMemberId'], "display", "Y"))
            email = opt_in_dto.get('email', "").lower().strip()
            
            if email:
                UnsubscribeLogs.objects.filter(member_id=get_client_id_by_tenant_id(member_id), email=email).delete()
                
                if opt_in_dto.get('groupList'):
                    Userlist.objects.filter(
                        memberId=get_client_id_by_tenant_id(member_id),
                        email=opt_in_dto['email'],
                        groupId__in=opt_in_dto['groupList']
                    ).update(status='Subscribed', optId=0)
                    
                    for group_id in opt_in_dto['groupList']:
                        check_duplicate_records(group_id, member_id)
                        check_total_member(group_id, member_id)

            phone_number = opt_in_dto.get('phoneNumber')
            if phone_number:
                if opt_in_dto.get('groupList'):
                    Userlist.objects.filter(
                        memberId=get_client_id_by_tenant_id(member_id),
                        phoneNumber=phone_number,
                        groupId__in=opt_in_dto['groupList']
                    ).update(smsStatus='Subscribed', optId=0)

            return api_response(200, "Opt-In Successfully")
        except Exception as e:
            logger.error(f"OptIn Error: {str(e)}")
            return api_response(500, "error")
    return api_response(400, "Bad Request", serializer.errors)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def send_subscribe_link(request):
    """
    POST /contactImport/sendSubscribeLink
    Migrated from ContactImportController.sendSubscribeLink
    """
    serializer = SendSubscribeLinkDtoSerializer(data=request.data)
    if serializer.is_valid():
        try:
            member_id = get_final_tenant_id(request=request)
            data = serializer.validated_data
            userlist = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(member_id), emailId=data['emailId']).first()
            if userlist:
                send_rejoin_group_details_email(userlist)
                return api_response(200, "We Have Sent An Opt-In Email.\nPlease Click On \"Subscribe\" In Email.")
            return api_response(404, "User not found")
        except Exception as e:
            logger.error(f"SendSubscribeLink Error: {str(e)}")
            return api_response(500, "error")
    return api_response(400, "Bad Request", serializer.errors)


@api_view(['POST'])
@permission_classes([WhitelistPermission])
def email_verification_group(request):
    """
    POST /contactImport/emailVerificationGroup
    Migrated from ContactImportController.emailVerificationGroup
    """
    serializer = EmailVerificationGroupDtoSerializer(data=request.data)
    if serializer.is_valid():
        try:
            member_id = get_final_tenant_id(request=request)
            data = serializer.validated_data
            group_id = data['groupId']
            
            if group_id > 0:
                pending_count = Userlist.objects.filter(
                    memberId=get_client_id_by_tenant_id(member_id),
                    groupId=group_id,
                    typeEmail__in=['pending', 'unverified']
                ).count()
                
                if pending_count > 0:
                    ev = EmailVerification.objects.create(
                        evTotalRecords=pending_count,
                        evFileUpload='N',
                        evFileDownload='N',
                        evBounceRate=0.0,
                        evGroupId=group_id,
                        evMemberId=get_client_id_by_tenant_id(member_id),
                        evDateTime=timezone.now(),
                        evOptInYN='N',
                        evStep=1
                    )
                    
                    Userlist.objects.filter(
                        memberId=get_client_id_by_tenant_id(member_id),
                        groupId=group_id,
                        typeEmail__in=['pending', 'unverified']
                    ).update(
                        typeEmail='email',
                        smtpHost=None,
                        emailVerificationStatus='email',
                        evId=ev.evId,
                        sendToEmailVerification='Yes'
                    )
                    
                    check_duplicate_records(group_id, member_id)
                    check_total_member(group_id, member_id)
                    
                    Groups.objects.filter(grpClientId=get_client_id_by_tenant_id(member_id), grpId=group_id).update(grpLockGroup='N')
                    Groups.objects.filter(grpId=group_id).update(grpTypeEmail='email')
                    
                    eta = ((pending_count * 12) + 600) // 60
                    msg = f"Email Verification submitted. This process take takes time and is estimated to be completed in {eta} minutes. You will receive an email when it is complete"
                    return api_response(200, msg, {"eta": eta})
                else:
                    return api_response(200, "Group Emails Already Verified", {"error": "error1"})
            else:
                return api_response(200, "error", {"error": "error"})
        except Exception as e:
            logger.error(f"EmailVerificationGroup Error: {str(e)}")
            return api_response(500, "Internal Server Error", {"error": "error"})
    return api_response(400, "Bad Request", serializer.errors)


@api_view(['POST'])
def sms_status_url_send_sms_opt_in(request):
    """
    POST /contactImport/smsStatusUrlSendSmsOptIn
    Migrated from ContactImportController.smsStatusUrlSendSmsOptIn
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
        payload = data.get('data', {}).get('payload', {})
        sms_sid = payload.get('id')
        status_val = payload.get('to', [{}])[0].get('status')
        
        if sms_sid:
            log_entry = ContactSendSmsLogs.objects.filter(sid=sms_sid).first()
            if log_entry:
                log_entry.sms_status = status_val
                log_entry.save()
                
        return api_response(200, "success")
    except Exception as e:
        logger.error(f"SmsStatusUrlSendSmsOptIn Error: {str(e)}")
        return api_response(200, "success")


# --- Helper Functions ---

def check_duplicate_records(group_id, member_id):
    duplicate_records = 'N'
    
    email_duplicates = Userlist.objects.filter(
        groupId=group_id, 
        memberId=get_client_id_by_tenant_id(member_id),
        status='Subscribed',
        badEmail__in=['N', 'B', 'D'],
        optId__in=[0, None]
    ).exclude(email='').exclude(email__isnull=True).values('email').annotate(count=Count('pk')).filter(count__gt=1)
    
    if email_duplicates.exists():
        duplicate_records = 'Y'
    else:
        phone_duplicates = Userlist.objects.filter(
            groupId=group_id,
            memberId=get_client_id_by_tenant_id(member_id),
            smsStatus__in=['Subscribed', None],
            badPhoneNumber='N',
            optId__in=[0, None]
        ).exclude(phoneNumber='').exclude(phoneNumber__isnull=True).values('phoneNumber').annotate(count=Count('pk')).filter(count__gt=1)
        
        if phone_duplicates.exists():
            duplicate_records = 'Y'
            
    Groups.objects.filter(grpId=group_id).update(grpDuplicateRecordsYn=duplicate_records)


def check_type_email(group_id, member_id):
    type_email = 'unverified'
    count = Userlist.objects.filter(
        groupId=group_id,
        memberId=get_client_id_by_tenant_id(member_id),
        status='Subscribed',
        badEmail__in=['N', 'B', 'D'],
        optId__in=[0, None]
    ).exclude(email='').exclude(email__isnull=True).count()
    
    if count > 0:
        count_email = Userlist.objects.filter(
            groupId=group_id,
            memberId=get_client_id_by_tenant_id(member_id),
            typeEmail__in=['email', 'pending']
        ).count()
        
        if count_email == 0:
            count_unverified = Userlist.objects.filter(
                groupId=group_id,
                memberId=get_client_id_by_tenant_id(member_id),
                typeEmail='unverified'
            ).count()
            
            if count_unverified == 0:
                type_email = 'done'
            else:
                type_email = 'unverified'
        else:
            type_email = 'email'
            
    Groups.objects.filter(grpId=group_id).update(grpTypeEmail=type_email)


def check_total_member(group_id, member_id):
    count = Userlist.objects.filter(
        groupId=group_id,
        memberId=get_client_id_by_tenant_id(member_id),
        status='Subscribed',
        badEmail__in=['N', 'B', 'D'],
        optId__in=[0, None]
    ).exclude(email='').exclude(email__isnull=True).count()
    
    Groups.objects.filter(grpId=group_id).update(grpTotalMember=count)


def opt_out_details_base(opt_out_details_dto):
    res_body = {"error": "", "optOutDetails": opt_out_details_dto}
    try:
        tenant_id = int(DecryptString.set_enc_dec_user(opt_out_details_dto['encMemberId'], "display", "Y"))
        group_id = int(DecryptString.set_enc_dec_user(opt_out_details_dto['encGroupId'], "display", "Y"))
        email_id = int(DecryptString.set_enc_dec_user(opt_out_details_dto['encEmailId'], "display", "Y"))
        
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": tenant_id
                }
            }
        )
        client = Clients.objects.get(cliTenantId=tenant_id)
        if not tenant:
            res_body['error'] = "Tenant not found"
            return res_body
            
        first_name = tenant.ten_first_name if tenant.ten_first_name else ""
        last_name = tenant.ten_last_name if tenant.ten_last_name else ""
        
        tenant_name = ""
        if first_name:
            tenant_name += uc_first(first_name)
        if last_name:
            if tenant_name:
                tenant_name += " "
            tenant_name += uc_first(last_name)
            
        opt_out_details_dto['tenantName'] = tenant_name
        
        cli_business_name = ""
        if client.cliBusinessName:
            cli_business_name = client.cliBusinessName
        opt_out_details_dto['cliBusinessName'] = cli_business_name
        
        group = Groups.objects.filter(grpId=group_id).first()
        if group:
            opt_out_details_dto['groupName'] = group.grpGroupName
            
        userlist = Userlist.objects.filter(memberId=get_client_id_by_tenant_id(tenant_id), emailId=email_id).first()
        if userlist:
            client_name = ""
            if userlist.firstName:
                client_name += uc_first(userlist.firstName)
            if userlist.lastName:
                if client_name:
                    client_name += " "
                client_name += uc_first(userlist.lastName)
            opt_out_details_dto['clientName'] = client_name
            
            if userlist.email:
                opt_out_details_dto['clientEmail'] = userlist.email.lower().strip()
            
            client_phone_number = ""
            if userlist.phoneNumber:
                client_phone_number = userlist.phoneNumber
            else:
                if userlist.phone:
                    client_phone_number = userlist.phone
            opt_out_details_dto['clientPhoneNumber'] = client_phone_number
            
        country_setting = CommonServices.country_setting_by_tenant_id(tenant_id)
        if country_setting and country_setting.cnty_white_listing.lower() == 'y':
            opt_out_details_dto['cliLogo'] = client.cliLogo or ""
        else:
            opt_out_details_dto['cliLogo'] = ""
            
        res_body['optOutDetails'] = opt_out_details_dto
    except Exception as e:
        logger.error(f"OptOutDetails Error: {str(e)}")
        res_body['error'] = "error"
    return res_body

def send_opt_out_details_email(userlist):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": userlist.memberId
                }
            }
        )
        client = Clients.objects.get(cliTenantId=userlist.memberId)
        tenant_name = ""
        if tenant.ten_first_name:
            tenant_name = tenant.ten_first_name
        if tenant.ten_last_name:
            tenant_name += " " + tenant.ten_last_name

        cli_business_name = ""
        if client.cliBusinessName:
            cli_business_name = client.cliBusinessName

        country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(userlist.memberId))
        cnty_white_listing = country_setting.cnty_white_listing if country_setting else "N"

        first_name = userlist.firstName or ""
        last_name = userlist.lastName or ""
        email = userlist.email
        
        udf_array = list(Udf.objects.filter(groupId=userlist.groupId).values_list('tblUdfcol', flat=True))
        
        mypage = MyPages.objects.filter(mpClientId=userlist.memberId, mpName="Opt Out").first()
        if not mypage:
            return
            
        camp_detail_temp = mypage.mpDetails or ""
        camp_detail_temp = camp_detail_temp.replace("\u200c", "").replace("\u200b", "")
        camp_detail_temp = camp_detail_temp.replace("447px", "5px").replace('height="100%"', "")
        
        # Remove style tags using regex
        camp_detail_temp = re.sub(r'<style[\s\S]*?</style>', '', camp_detail_temp, flags=re.IGNORECASE)
        # Remove RT3 comments
        camp_detail_temp = re.sub(r'<!--RT3S-->[\s\S]*?<!--RT3E-->', '', camp_detail_temp)

        # Replace standard placeholders
        replace_map = {
            r"##business_name##": cli_business_name.strip() if cli_business_name else tenant_name.strip(),
            r"##first_name##": first_name.strip(),
            r"##last_name##": last_name.strip(),
            r"##email##": email.strip(),
        }
        
        client_phone_number = userlist.phoneNumber or userlist.phone or ""
        if client_phone_number:
            replace_map[r"##contact_no##"] = client_phone_number.replace(" ", "").strip()

        for pattern, replacement in replace_map.items():
            camp_detail_temp = re.sub(re.escape(pattern), replacement, camp_detail_temp, flags=re.IGNORECASE)

        # UDF replacements
        udfs = [userlist.udf1, userlist.udf2, userlist.udf3, userlist.udf4, userlist.udf5, 
                userlist.udf6, userlist.udf7, userlist.udf8, userlist.udf9, userlist.udf10]
        for i, udf_label in enumerate(udf_array):
            if i < len(udfs):
                val = (udfs[i] or "").strip()
                camp_detail_temp = re.sub(re.escape(f"##{udf_label}##"), val, camp_detail_temp, flags=re.IGNORECASE)

        # HTML Cleaning with BeautifulSoup
        soup = BeautifulSoup(camp_detail_temp, "html.parser")
        for tag in soup.select("div.removeClass"):
            tag.decompose()
        camp_detail_temp = str(soup)
        
        camp_detail_temp = cron_send_campaign_content_remove(camp_detail_temp)
        camp_detail_temp = camp_detail_temp.replace("</body></html>", "")
        
        # Footer reconstruction
        site_url = getattr(settings, 'SITE_URL', 'https://salesandmarketing.ai/')
        site_url_www = getattr(settings, 'SITE_URL_WWW', 'https://www.salesandmarketing.ai')
        site_url_address = getattr(settings, 'SITE_URL_ADDRESS', '123 Business St, City, Country')
        
        footer_html = f"<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:'Myriad Pro',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
        footer_html += "<div style='padding-top:2px'>"
        
        cli_logo = client.cliLogo
        cli_customer_footer = client.cliCustomerFooter
        
        if (cnty_white_listing or "N").lower() == "y" and cli_logo:
             footer_html += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
        else:
             footer_html += f'<a style="color:#00599A;margin: 0px auto;" href="{site_url_www}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{site_url}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'
        
        footer_html += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"
        if (cnty_white_listing or "N").lower() == "y" and cli_customer_footer:
            footer_html += nl2br(cli_customer_footer)
        else:
            footer_html += site_url_address
            
        # Links
        v = DecryptString.set_enc_dec_user(str(userlist.memberId), "", "Y")
        w = DecryptString.set_enc_dec_user(str(userlist.groupId), "", "Y")
        y = DecryptString.set_enc_dec_user(str(userlist.emailId), "", "Y")
        subscribe_link = f"{site_url}subscribelink?v={v}&w={w}&y={y}"
        
        q_str = f"{userlist.groupId}~{userlist.memberId}~0~{userlist.emailId}"
        q = DecryptString.set_enc_dec_user(q_str, "", "Y")
        update_contact_link = f"{site_url}inviteurl?q={q}"
        
        footer_html += "</div></div></div>"
        footer_html += f"</div><div align='center' style='color:#4285F4;font-size:12px;'><a href='{subscribe_link}' style='color:#4285F4'>Subscribe</a> | <a href='{update_contact_link}' style='color:#4285F4'>Update Contact Information</a></div>"
        
        camp_detail_temp += footer_html + "</body></html>"
        
        name_list = cli_business_name if cli_business_name else tenant_name
        subject = f"Opt-Out From {name_list} Contact List"
        
        model = {
            "SITEURL": site_url,
            "msgBody": strip_slashes(camp_detail_temp),
            "siteName": getattr(settings, 'SITE_NAME', 'SalesAndMarketing'),
            "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai'),
            "siteUrlWWW": site_url_www,
            "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', 'www.salesandmarketing.ai'),
            "companyName": getattr(settings, 'COMPANY_NAME', 'SalesAndMarketing AI'),
            "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', 'SalesAndMarketing AI'),
            "siteUrlAddress": site_url_address,
            "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', '123 Business St<br>City, Country'),
            "companyNumber": getattr(settings, 'COMPANY_NUMBER', '1-800-123-4567'),
            "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', 'salesandmarketing.ai'),
            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', 'SALESANDMARKETING.AI'),
        }
        
        mail_request = MailRequestDTO(to=email.lower(), subject=subject, template_name="optout-template.ftl")
        CommonServices.sendEmail(mail_request, model)
        
    except Exception as e:
        logger.error(f"send_opt_out_details_email Error: {e}")


def send_opt_out_details_sms(userlist):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": userlist.memberId
                }
            }
        )
        phone_number = get_phone_numbers_first(tenant.ten_id, "CAMPAIGN")
        client = Clients.objects.get(cliTenantId=tenant.ten_id)
        tenant_name = ""
        if tenant.ten_first_name:
            tenant_name = tenant.ten_first_name
        if tenant.ten_last_name:
            tenant_name += " " + tenant.ten_last_name

        cli_business_name = ""
        if client.cliBusinessName:
            cli_business_name = client.cliBusinessName

        first_name = userlist.firstName or ""
        last_name = userlist.lastName or ""
        email = userlist.email
        mobile_number = userlist.phoneNumber or ""
        
        udf_list = list(Udf.objects.filter(groupId=userlist.groupId).values_list('tblUdfcol', flat=True))
        
        sms_details = ""
        template = SmsTemplates.objects.filter(stClientId=userlist.memberId, stName='Opt Out').first()
        if template:
            sms_details = template.stDetails or ""
        
        # Replacements
        biz_name = cli_business_name if cli_business_name else tenant_name
        sms_details = re.sub(r"##Business Name##", biz_name, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##First Name##", first_name, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Last Name##", last_name, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Email##", email, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Mobile Number##", mobile_number, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Contact No##", mobile_number, sms_details, flags=re.IGNORECASE)

        udfs = [userlist.udf1, userlist.udf2, userlist.udf3, userlist.udf4, userlist.udf5, 
                userlist.udf6, userlist.udf7, userlist.udf8, userlist.udf9, userlist.udf10]
        for i, udf_label in enumerate(udf_list):
            if i < len(udfs):
                val = (udfs[i] or "").strip()
                sms_details = re.sub(re.escape(f"##{udf_label}##"), val, sms_details, flags=re.IGNORECASE)

        country = Country.objects.filter(cnt_name=userlist.country).first()
        phone_max_length = country.phone_max_length if country else 10
        cnt_code = country.cnt_code if country else "1"

        client_phone = ""
        if userlist.phoneNumber:
            client_phone = userlist.phoneNumber[-phone_max_length:]
        elif userlist.phone:
            client_phone = userlist.phone[-phone_max_length:]

        if phone_number.phPhoneNumber and client_phone:
            client_phone = f"+{cnt_code}{client_phone}"
            
            site_url = getattr(settings, 'SITE_URL', 'https://salesandmarketing.ai/')
            q_str = f"{userlist.groupId}~{userlist.memberId}~0~{userlist.emailId}"
            q = DecryptString.set_enc_dec_user(q_str, "", "Y")
            update_contact_link = f"{site_url}inviteurl?q={q}"
            sms_details = re.sub(r"##Link##", update_contact_link, sms_details, flags=re.IGNORECASE)

            country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(userlist.memberId))
            tran_member_rate = country_setting.cnty_sms_per_price if country_setting else 0.02
            tran_count_total_sms = len(sms_details) // 160 + 1
            tran_total_amount = tran_member_rate * tran_count_total_sms

            CampaignTransaction.objects.create(
                tran_campaign_name="Opt Out SMS Charges",
                tran_total_member=1,
                tran_type="sms",
                tran_invoiced_status="uninvoiced",
                ct_client_id=userlist.memberId,
                tran_total_amount=tran_total_amount,
                tran_member_rate=tran_member_rate,
                tran_count_total_sms=tran_count_total_sms,
                tran_campaign_date=timezone.now()
            )

            msg = send_sms_telnyx(
                mobile_no=client_phone,
                telnyx_number=phone_number.phPhoneNumber,
                sms_type="text",
                sms_details=sms_details,
                sms_count="first",
                opt_out_msg="",
                sms_status_url=getattr(settings, 'SMS_STATUS_URL', '')
            )

            ContactSendSmsLogs.objects.create(
                member_id=userlist.memberId,
                email_id=userlist.emailId,
                sid=msg.get("msgId"),
                sms_status=msg.get("msgStatus"),
                error_code=msg.get("msgErrorCode"),
                from_contact=phone_number.phPhoneNumber,
                to_contact=client_phone,
                sms_detail=sms_details,
                group_id=userlist.groupId,
                sms_send_date=timezone.now()
            )
    except Exception as e:
        logger.error(f"send_opt_out_details_sms Error: {e}")

def send_opt_out_admin_email(userlist):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": userlist.memberId
                }
            }
        )
        ten_first_name = tenant.ten_first_name if tenant.ten_first_name else ""
        ten_last_name = tenant.ten_last_name if tenant.ten_last_name else ""
        ten_email = tenant.ten_email if tenant.ten_email else ""
        
        email = userlist.email

        model = {
            "memFirstName": ten_first_name,
            "memLastName": ten_last_name,
            "firstName": userlist.firstName,
            "lastName": userlist.lastName,
            "email": email,
            "SITEURL": getattr(settings, 'SITE_URL', 'https://salesandmarketing.ai/'),
            "siteName": getattr(settings, 'SITE_NAME', 'SalesAndMarketing'),
            "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai'),
            "siteUrlWWW": getattr(settings, 'SITE_URL_WWW', 'https://www.salesandmarketing.ai'),
            "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', 'www.salesandmarketing.ai'),
            "companyName": getattr(settings, 'COMPANY_NAME', 'SalesAndMarketing AI'),
            "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', 'SalesAndMarketing AI'),
            "siteUrlAddress": getattr(settings, 'SITE_URL_ADDRESS', '123 Business St, City, Country'),
            "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', '123 Business St<br>City, Country'),
            "companyNumber": getattr(settings, 'COMPANY_NUMBER', '1-800-123-4567'),
            "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', 'salesandmarketing.ai'),
            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', 'SALESANDMARKETING.AI'),
        }
        
        mail_request = MailRequestDTO(to=ten_email, subject="Tenant Opted Out of Your Contact List", template_name="opted-out-member-template.ftl")
        CommonServices.sendEmail(mail_request, model)
    except Exception as e:
        logger.error(f"send_opt_out_admin_email Error: {e}")


def send_rejoin_group_details_email(userlist):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": get_tenant_id_by_client_id(userlist.memberId)
                }
            }
        )
        client = Clients.objects.get(cliTenantId=userlist.memberId)
        tenant_name = ""
        if tenant.ten_first_name:
            tenant_name = tenant.ten_first_name
        if tenant.ten_last_name:
            tenant_name += " " + tenant.ten_last_name

        cli_business_name = ""
        if client.cliBusinessName:
            cli_business_name = client.cliBusinessName

        country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(userlist.memberId))
        cnty_white_listing = country_setting.cnty_white_listing if country_setting else "N"

        first_name = userlist.firstName or ""
        last_name = userlist.lastName or ""
        email = userlist.email
        
        udf_array = list(Udf.objects.filter(groupId=userlist.groupId).values_list('tblUdfcol', flat=True))
        
        mypage = MyPages.objects.filter(mpClientId=userlist.memberId, mpName="Rejoin Group").first() # Assuming Rejoin is also mpType 2 or similar logic
        # Java uses findRejoinGroupMyPage, I'll assume mpType 2 for now or a different one if defined
        if not mypage:
            return
            
        camp_detail_temp = mypage.mpDetails or ""
        camp_detail_temp = camp_detail_temp.replace("\u200c", "").replace("\u200b", "")
        camp_detail_temp = camp_detail_temp.replace("447px", "5px").replace('height="100%"', "")
        
        # Style/Comment removal
        camp_detail_temp = re.sub(r'<style[\s\S]*?</style>', '', camp_detail_temp, flags=re.IGNORECASE)
        camp_detail_temp = re.sub(r'<!--RT3S-->[\s\S]*?<!--RT3E-->', '', camp_detail_temp)

        site_url = getattr(settings, 'SITE_URL', 'https://salesandmarketing.ai/')
        v = DecryptString.set_enc_dec_user(str(userlist.memberId), "", "Y")
        w = DecryptString.set_enc_dec_user(str(userlist.groupId), "", "Y")
        y = DecryptString.set_enc_dec_user(str(userlist.emailId), "", "Y")
        link = f"{site_url}subscribelink?v={v}&w={w}&y={y}"

        # Approve link replacement
        camp_detail_temp = re.sub(r"(?i)##link##", f"<a href='{link}'>Approve</a>", camp_detail_temp)

        # Standard replacements
        replace_map = {
            r"##business_name##": cli_business_name.strip() if cli_business_name else tenant_name.strip(),
            r"##first_name##": first_name.strip(),
            r"##last_name##": last_name.strip(),
            r"##email##": email.strip(),
        }
        client_phone_number = userlist.phoneNumber or userlist.phone or ""
        if client_phone_number:
            replace_map[r"##contact_no##"] = client_phone_number.replace(" ", "").strip()

        for pattern, replacement in replace_map.items():
            camp_detail_temp = re.sub(re.escape(pattern), replacement, camp_detail_temp, flags=re.IGNORECASE)

        # UDFs
        udfs = [userlist.udf1, userlist.udf2, userlist.udf3, userlist.udf4, userlist.udf5, 
                userlist.udf6, userlist.udf7, userlist.udf8, userlist.udf9, userlist.udf10]
        for i, udf_label in enumerate(udf_array):
            if i < len(udfs):
                val = (udfs[i] or "").strip()
                camp_detail_temp = re.sub(re.escape(f"##{udf_label}##"), val, camp_detail_temp, flags=re.IGNORECASE)

        soup = BeautifulSoup(camp_detail_temp, "html.parser")
        for tag in soup.select("div.removeClass"):
            tag.decompose()
        camp_detail_temp = str(soup)
        camp_detail_temp = cron_send_campaign_content_remove(camp_detail_temp)
        camp_detail_temp = camp_detail_temp.replace("</body></html>", "")
        
        # Footer
        site_url_www = getattr(settings, 'SITE_URL_WWW', 'https://www.salesandmarketing.ai')
        site_url_address = getattr(settings, 'SITE_URL_ADDRESS', '123 Business St, City, Country')
        
        footer_html = f"<div align='center'><div style=\"margin:0;word-wrap:normal;font-family:'Myriad Pro',Arial,sans-serif;font-size:14px;color:#00599A;line-height:25px;text-align:center;margin-top:5px;\">"
        footer_html += "<div style='padding-top:2px'>"
        
        cli_logo = client.cliLogo
        cli_customer_footer = client.cliCustomerFooter
        if (cnty_white_listing or "N").lower() == "y" and cli_logo:
             footer_html += f'<img src="{cli_logo}" alt="logo" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width: 150px; max-height: 75px;" border="0">'
        else:
             footer_html += f'<a style="color:#00599A;margin: 0px auto;" href="{site_url_www}" target="_blank"><img tabindex="0" class="CToWUd a6T" src="{site_url}img/logo.png" style="margin:0;margin-top: 15px;padding:0;outline:none;text-decoration:none;max-width:170px;max-height: 70px;" border="0"></a>'
        
        footer_html += "<br><div style='color:#4285F4;padding-top:2px;font-size:12px; '>"
        if (cnty_white_listing or "N").lower() == "y" and cli_customer_footer:
            footer_html += nl2br(cli_customer_footer)
        else:
            footer_html += site_url_address
            
        q_str = f"{userlist.groupId}~{userlist.memberId}~0~{userlist.emailId}"
        q = DecryptString.set_enc_dec_user(q_str, "", "Y")
        update_contact_link = f"{site_url}inviteurl?q={q}"
        
        footer_html += "</div></div></div>"
        footer_html += f"</div><div align='center' style='color:#4285F4;font-size:12px;'><a href='{link}' style='color:#4285F4'>Subscribe</a> | <a href='{update_contact_link}' style='color:#4285F4'>Update Contact Information</a></div>"
        
        camp_detail_temp += footer_html + "</body></html>"
        
        name_list = cli_business_name if cli_business_name else tenant_name
        subject = f"Opt-In to {name_list} Contact List"
        
        model = {
            "SITEURL": site_url,
            "msgBody": strip_slashes(camp_detail_temp),
            "siteName": getattr(settings, 'SITE_NAME', 'SalesAndMarketing'),
            "toAdminSupportEmail": getattr(settings, 'TO_ADMIN_SUPPORT_EMAIL', 'support@salesandmarketing.ai'),
            "siteUrlWWW": site_url_www,
            "siteUrlWWWDisplay": getattr(settings, 'SITE_URL_WWW_DISPLAY', 'www.salesandmarketing.ai'),
            "companyName": getattr(settings, 'COMPANY_NAME', 'SalesAndMarketing AI'),
            "mainCompanyName": getattr(settings, 'MAIN_COMPANY_NAME', 'SalesAndMarketing AI'),
            "siteUrlAddress": site_url_address,
            "siteUrlAddressBr": getattr(settings, 'SITE_URL_ADDRESS_BR', '123 Business St<br>City, Country'),
            "companyNumber": getattr(settings, 'COMPANY_NUMBER', '1-800-123-4567'),
            "siteNameSmallCom": getattr(settings, 'SITE_NAME_SMALL_COM', 'salesandmarketing.ai'),
            "siteNameBigCom": getattr(settings, 'SITE_NAME_BIG_COM', 'SALESANDMARKETING.AI'),
        }
        
        mail_request = MailRequestDTO(to=email.lower(), subject=subject, template_name="optin-template.ftl")
        CommonServices.sendEmail(mail_request, model)
    except Exception as e:
        logger.error(f"send_rejoin_group_details_email Error: {e}")


def send_opt_in_details_sms(userlist, automation_sms_reply_log=None):
    try:
        tenant = get_tenants(
            where_conditions={
                "tenant": {
                    "ten_id": get_tenant_id_by_client_id(userlist.memberId)
                }
            }
        )
        phone_number = get_phone_numbers_first(tenant.ten_id, "CAMPAIGN")
        client = Clients.objects.get(cliTenantId=tenant.ten_id)
        tenant_name = ""
        if tenant.ten_first_name:
            tenant_name = tenant.ten_first_name
        if tenant.ten_last_name:
            tenant_name += " " + tenant.ten_last_name

        cli_business_name = ""
        if client.cliBusinessName:
            cli_business_name = client.cliBusinessName

        first_name = userlist.firstName or ""
        last_name = userlist.lastName or ""
        email = userlist.email
        mobile_number = userlist.phoneNumber or ""
        
        udf_list = list(Udf.objects.filter(groupId=userlist.groupId).values_list('tblUdfcol', flat=True))
        
        sms_details = ""
        template = SmsTemplates.objects.filter(stClientId=userlist.memberId, stName='Opt In').first()
        if template:
            sms_details = template.stDetails or ""
        
        # Replacements
        biz_name = cli_business_name if cli_business_name else tenant_name
        sms_details = re.sub(r"##Business Name##", biz_name, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##First Name##", first_name, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Last Name##", last_name, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Email##", email, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Mobile Number##", mobile_number, sms_details, flags=re.IGNORECASE)
        sms_details = re.sub(r"##Contact No##", mobile_number, sms_details, flags=re.IGNORECASE)

        udfs = [userlist.udf1, userlist.udf2, userlist.udf3, userlist.udf4, userlist.udf5, 
                userlist.udf6, userlist.udf7, userlist.udf8, userlist.udf9, userlist.udf10]
        for i, udf_label in enumerate(udf_list):
            if i < len(udfs):
                val = (udfs[i] or "").strip()
                sms_details = re.sub(re.escape(f"##{udf_label}##"), val, sms_details, flags=re.IGNORECASE)

        country = Country.objects.filter(cnt_name=userlist.country).first()
        phone_max_length = country.phone_max_length if country else 10
        cnt_code = country.cnt_code if country else "1"

        client_phone = ""
        if userlist.phoneNumber:
            client_phone = userlist.phoneNumber[-phone_max_length:]
        elif userlist.phone:
            client_phone = userlist.phone[-phone_max_length:]

        if phone_number.phPhoneNumber and client_phone:
            client_phone = f"+{cnt_code}{client_phone}"
            
            site_url = getattr(settings, 'SITE_URL', 'https://salesandmarketing.ai/')
            q_str = f"{userlist.groupId}~{userlist.memberId}~0~{userlist.emailId}"
            q = DecryptString.set_enc_dec_user(q_str, "", "Y")
            update_contact_link = f"{site_url}inviteurl?q={q}"
            sms_details = re.sub(r"##Link##", update_contact_link, sms_details, flags=re.IGNORECASE)

            country_setting = CommonServices.country_setting_by_tenant_id(get_tenant_id_by_client_id(userlist.memberId))
            tran_member_rate = country_setting.cnty_sms_per_price if country_setting else 0.02
            tran_count_total_sms = len(sms_details) // 160 + 1
            tran_total_amount = tran_member_rate * tran_count_total_sms

            CampaignTransaction.objects.create(
                tran_campaign_name="Opt In SMS Charges",
                tran_total_member=1,
                tran_type="sms",
                tran_invoiced_status="uninvoiced",
                ct_client_id=userlist.memberId,
                tran_total_amount=tran_total_amount,
                tran_member_rate=tran_member_rate,
                tran_count_total_sms=tran_count_total_sms,
                tran_campaign_date=timezone.now()
            )

            msg = send_sms_telnyx(
                mobile_no=client_phone,
                telnyx_number=phone_number.phPhoneNumber,
                sms_type="text",
                sms_details=sms_details,
                sms_count="first",
                opt_out_msg="",
                sms_status_url=getattr(settings, 'SMS_STATUS_URL', '')
            )

            ContactSendSmsLogs.objects.create(
                member_id=userlist.memberId,
                email_id=userlist.emailId,
                sid=msg.get("msgId"),
                sms_status=msg.get("msgStatus"),
                error_code=msg.get("msgErrorCode"),
                from_contact=phone_number.phPhoneNumber,
                to_contact=client_phone,
                sms_detail=sms_details,
                group_id=userlist.groupId,
                sms_send_date=timezone.now()
            )
    except Exception as e:
        logger.error(f"send_opt_in_details_sms Error: {e}")
