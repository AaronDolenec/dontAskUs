"""
Script to set up initial admin user with 2FA
Run this once to create the first admin account
"""

import os
import sys
import getpass
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import AdminUser
from admin_auth import hash_password, get_totp_secret, get_totp_uri
import pyotp


def setup_admin():
    """Create initial admin user"""
    db = SessionLocal()
    
    try:
        # Check if admin already exists
        existing_admin = db.query(AdminUser).first()
        if existing_admin:
            print("❌ Admin user already exists. To create additional admins, use the API.")
            return
        
        print("=" * 60)
        print("INITIAL ADMIN SETUP")
        print("=" * 60)
        print()
        
        # Get input
        username = input("Enter admin username (min 3 chars): ").strip()
        if len(username) < 3:
            print("❌ Username too short")
            return
        
        password = getpass.getpass("Enter admin password (min 8 chars): ")
        if len(password) < 8:
            print("❌ Password too short")
            return
        
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("❌ Passwords don't match")
            return
        
        # Hash password
        password_hash = hash_password(password)
        
        # Generate TOTP secret
        totp_secret = get_totp_secret()
        
        # Create admin user
        admin = AdminUser(
            username=username,
            password_hash=password_hash,
            totp_secret=totp_secret,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            login_attempt_count=0
        )
        
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        print()
        print("✅ Admin user created successfully!")
        print()
        print("=" * 60)
        print("NEXT STEPS: SET UP 2FA (TOTP)")
        print("=" * 60)
        print()
        print("Scan this QR code with your authenticator app (Google Authenticator, Authy, etc):")
        print()
        
        # Display QR code URI (in production, would generate QR image)
        uri = get_totp_uri(username, totp_secret)
        print(f"Or enter this secret manually:")
        print(f"Secret: {totp_secret}")
        print()
        print(f"Provisioning URI: {uri}")
        print()
        
        # For testing, show how to verify
        print("=" * 60)
        print("TO TEST 2FA (for development only):")
        print("=" * 60)
        totp = pyotp.TOTP(totp_secret)
        print(f"Current TOTP code: {totp.now()}")
        print("Use this code in the login flow at /api/admin/2fa")
        print()
        
        print("=" * 60)
        print("ADMIN ACCOUNT DETAILS")
        print("=" * 60)
        print(f"Username: {username}")
        print(f"User ID: {admin.id}")
        print()
        print("🔐 KEEP YOUR TOTP SECRET SAFE!")
        print("If you lose it, you won't be able to login.")
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    setup_admin()
