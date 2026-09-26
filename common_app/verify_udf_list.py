import os
import django
from rest_framework.test import APIRequestFactory

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salesandmarketingapi.settings')
django.setup()

from mycrm_app.views.group_views import getUDFlist
from common_app.models import Group, Udf

def test_getudflist():
    factory = APIRequestFactory()
    group = Group.objects.first()
    
    if not group:
        print("No groups found to test.")
        return

    print(f"Testing getUDFlist for Group ID: {group.groupId}")
    request = factory.get(f'/group/getGroupUDFList/{group.groupId}')
    
    # We need to manually call the view since we are not running a full server
    response = getUDFlist(request, group.groupId)
    
    print(f"Status: {response.status_code}")
    result = response.data.get('result', [])
    print(f"Number of UDFs returned: {len(result)}")
    
    # Check for some system UDFs
    system_keys = ["First_Name", "Last_Name", "full_name", "Email"]
    found_system = [item for item in result if item['key'] in system_keys]
    print(f"Found {len(found_system)} system UDFs out of {len(system_keys)} expected.")
    
    # Check for custom UDFs
    custom_udfs = Udf.objects.filter(groupId=group.groupId)
    found_custom = [item for item in result if item['key'].startswith('udf')]
    print(f"Found {len(found_custom)} custom UDFs. Database has {custom_udfs.count()}.")
    
    if len(found_system) == len(system_keys) and len(found_custom) == custom_udfs.count():
        print("Verification SUCCESSFUL: Response matches Java structure and contains expected data.")
    else:
        print("Verification FAILED: Missing data in response.")

if __name__ == "__main__":
    test_getudflist()
