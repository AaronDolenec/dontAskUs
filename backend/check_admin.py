#!/usr/bin/env python3
"""Check if admin user exists and show details"""
from database import SessionLocal
from models import AdminUser

db = SessionLocal()

admins = db.query(AdminUser).all()
if not admins:
    print("[INFO] No admin users found in database!")
else:
    print(f"[INFO] Found {len(admins)} admin user(s):")
    for admin in admins:
        print(f"  - Username: {admin.username}")
        print(f"    ID: {admin.id}")
        print(f"    Active: {admin.is_active}")
        print(f"    TOTP Enabled: {admin.totp_enabled}")
        print(f"    Created: {admin.created_at}")
        print()

db.close()
