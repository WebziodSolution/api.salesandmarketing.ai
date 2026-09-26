import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salesandmarketingapi.settings')
django.setup()

from common_app.models import Group, Udf

def test_udf_logic():
    group = Group.objects.first()
    if not group:
        print("No groups found.")
        return
        
    groupId = group.groupId
    print(f"Testing for Group ID: {groupId}")
    
    udf_keys = [
        "First_Name", "Last_Name", "full_name", "Email", "phoneNumber", "phone", 
        "street_address1", "street_address2", "city", "stateProvRegion", 
        "zipPostalCode", "region", "gender", "age", "contactRating", "tags"
    ]
    udf_values = [
        "First Name", "Last Name", "Full Name", "Email", "Mobile Number", "Phone", 
        "Street Address1", "Street Address2", "City", "State", "Zip Code", 
        "Region", "Gender", "Age", "Contact Rating", "Tags"
    ]
    
    udf_list = []
    for key, value in zip(udf_keys, udf_values):
        udf_list.append({"key": key, "value": value})
        
    # Custom UDFs
    custom_udfs = Udf.objects.filter(groupId=groupId)
    for udf in custom_udfs:
        udf_list.append({
            "key": f"udf{udf.udfLabel}",
            "value": udf.udf
        })
    
    print(f"Total UDFs: {len(udf_list)}")
    print(f"Custom UDFs count: {custom_udfs.count()}")
    
    # Check if first few are correct
    print(f"First UDF: {udf_list[0]}")
    
    # Check for a specific custom udf if it exists
    if custom_udfs.exists():
        first_custom = custom_udfs.first()
        if first_custom is not None:
            expected_key = f"udf{first_custom.udfLabel}"
        else:
            expected_key = f"udf"
        found = [item for item in udf_list if item['key'] == expected_key]
        if found:
            print(f"Found custom UDF {expected_key}: {found[0]}")
        else:
            print(f"FAILED to find custom UDF {expected_key}")
    else:
        print("No custom UDFs to verify.")

if __name__ == "__main__":
    test_udf_logic()
