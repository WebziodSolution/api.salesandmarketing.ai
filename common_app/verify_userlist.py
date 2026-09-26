import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salesandmarketingapi.settings')
django.setup()

from common_app.models import Userlist

def test_userlist():
    try:
        count = Userlist.objects.count()
        print(f"Userlist count: {count}")
        print("Userlist query successful!")
    except Exception as e:
        print(f"Userlist query failed: {e}")
        exit(1)

if __name__ == "__main__":
    test_userlist()
