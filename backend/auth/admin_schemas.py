"""
Pydantic schemas for admin endpoints
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class AdminLoginRequest(BaseModel):
    """Request for admin login with username and password"""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "securepassword123"
            }
        }


class AdminLoginResponse(BaseModel):
    """Response after successful password verification, before 2FA"""
    temp_token: str = Field(..., description="Temporary token valid for 5 minutes, use for 2FA verification")
    message: str = "Password verified. Please provide 2FA code."
    
    class Config:
        json_schema_extra = {
            "example": {
                "temp_token": "eyJhbGc...",
                "message": "Password verified. Please provide 2FA code."
            }
        }


class AdminTOTPVerifyRequest(BaseModel):
    """Request to verify TOTP 2FA code"""
    temp_token: str = Field(..., description="Temporary token from login step")
    totp_code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")
    
    class Config:
        json_schema_extra = {
            "example": {
                "temp_token": "eyJhbGc...",
                "totp_code": "123456"
            }
        }


class AdminTokenResponse(BaseModel):
    """Response with JWT tokens after successful 2FA"""
    access_token: str = Field(..., description="JWT access token (60 minutes)")
    refresh_token: str = Field(..., description="JWT refresh token (7 days)")
    token_type: str = "Bearer"
    expires_in: int = 3600
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGc...",
                "refresh_token": "eyJhbGc...",
                "token_type": "Bearer",
                "expires_in": 3600
            }
        }


class AdminRefreshRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str = Field(..., description="JWT refresh token")
    
    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGc..."
            }
        }


class AdminProfileResponse(BaseModel):
    """Response with admin user profile"""
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    totp_configured: bool
    created_at: datetime
    last_login_ip: Optional[str]
    
    class Config:
        from_attributes = True


class ChangePasswordRequest(BaseModel):
    """Request model to change admin password"""
    current_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        import re
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v


class TOTPSetupStartResponse(BaseModel):
    """Response containing TOTP secret and provisioning URI for setup"""
    secret: str
    provisioning_uri: str


class TOTPSetupVerifyRequest(BaseModel):
    """Request to verify TOTP setup with a code"""
    code: str = Field(..., min_length=6, max_length=6)


class AdminLogoutRequest(BaseModel):
    """Request to logout (invalidate refresh token on client)"""
    message: str = "Logged out successfully"


class GroupBasicInfo(BaseModel):
    """Basic info about a group"""
    id: int
    name: str
    created_by: str
    created_at: datetime
    member_count: int
    
    class Config:
        from_attributes = True


class UserBasicInfo(BaseModel):
    """Basic info about a user"""
    id: int
    name: str
    email: Optional[str]
    created_at: datetime
    is_suspended: bool = False
    last_known_ip: Optional[str]
    
    class Config:
        from_attributes = True


class QuestionSetInfo(BaseModel):
    """Info about a question set"""
    id: int
    name: str
    is_public: bool
    creator_id: Optional[int]
    usage_count: int
    created_at: datetime
    question_count: int
    
    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    """Response for audit log entry"""
    id: int
    admin_id: int
    action: str
    target_type: str
    target_id: Optional[int]
    before_state: Optional[Dict[str, Any]]
    after_state: Optional[Dict[str, Any]]
    timestamp: datetime
    ip_address: Optional[str]
    reason: Optional[str]
    
    class Config:
        from_attributes = True


class AdminDashboardStats(BaseModel):
    """Stats for admin dashboard"""
    total_groups: int
    total_users: int
    total_question_sets: int
    public_sets: int
    private_sets: int
    active_sessions_today: int
    recent_audit_logs: List[AuditLogResponse]
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_groups": 42,
                "total_users": 256,
                "total_question_sets": 18,
                "public_sets": 10,
                "private_sets": 8,
                "active_sessions_today": 15,
                "recent_audit_logs": []
            }
        }


class UserSuspensionRequest(BaseModel):
    """Request to suspend/unsuspend a user"""
    is_suspended: bool
    suspension_reason: Optional[str] = Field(None, max_length=500)
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_suspended": True,
                "suspension_reason": "Violates community guidelines"
            }
        }


class AccountPasswordResetRequest(BaseModel):
    """Request for admin to reset a user account's password"""
    new_password: str = Field(..., min_length=8, max_length=128, description="New password for the account")
    reason: str = Field(..., max_length=500, description="Reason for password reset")

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        import re
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "new_password": "NewSecure1Pass",
                "reason": "User lost access to their account"
            }
        }


class AccountPasswordResetResponse(BaseModel):
    """Response after admin resets a user account's password"""
    message: str
    account_email: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Password reset for user@example.com",
                "account_email": "user@example.com"
            }
        }
