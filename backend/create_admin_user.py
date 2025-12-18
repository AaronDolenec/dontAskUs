from models import AdminUser, hash_password
from database import SessionLocal

# Run this script once to create the initial admin user
# Usage: python create_admin_user.py


import os

def main():
    db = SessionLocal()
    username = os.getenv("ADMIN_INITIAL_USERNAME", "admin")
    password = os.getenv("ADMIN_INITIAL_PASSWORD", "changeme123")

    # Create only if no admin exists yet
    existing = db.query(AdminUser).first()
    if existing:
        print("[INFO] Admin user already exists; skipping auto-create.")
        db.close()
        return

    print(f"[INFO] Creating initial admin user with username: {username}")
    print("[INFO] Initial password taken from ADMIN_INITIAL_PASSWORD env variable.")

    admin = AdminUser(
        username=username,
        password_hash=hash_password(password),
        totp_secret=None,
        totp_enabled=False,
        is_active=True
    )
    db.add(admin)
    db.commit()
    print("[INFO] Admin user created successfully!")
    print("[INFO] TOTP can be set up after login in the admin UI.")
    db.close()

if __name__ == "__main__":
    main()
