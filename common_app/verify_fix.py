import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salesandmarketingapi.settings')
django.setup()

from auth_app.models import Member

def test_member():
    member = Member(member_id=1, member_status=1)
    
    print(f"Testing Member instance:")
    print(f"is_authenticated: {member.is_authenticated}")
    print(f"is_anonymous: {member.is_anonymous}")
    print(f"is_active: {member.is_active}")
    
    assert member.is_authenticated is True
    assert member.is_anonymous is False
    assert member.is_active is True
    
    member.member_status = 0
    print(f"is_active (status=0): {member.is_active}")
    assert member.is_active is False
    
    print("Verification successful!")

if __name__ == "__main__":
    try:
        test_member()
    except Exception as e:
        print(f"Verification failed: {e}")
        exit(1)
