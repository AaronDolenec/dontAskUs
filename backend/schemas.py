
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, List, Union
from datetime import datetime
from enum import Enum
import re

# ============= Admin Schemas (re-exported from admin_schemas for backward compatibility) =============
from admin_schemas import AdminLoginRequest, AdminLoginResponse


# ============= User Auth Schemas =============

class AuthRegisterRequest(BaseModel):
    """Registration request with email, password, and display name."""
    email: EmailStr = Field(..., description="Unique email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars)")
    display_name: str = Field(..., min_length=1, max_length=50, description="Default display name")

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        v = sanitize_string(v, 50)
        if not v or not v.strip():
            raise ValueError('Display name cannot be empty')
        return v


class AuthLoginRequest(BaseModel):
    """Login request with email and password."""
    email: EmailStr
    password: str


class AuthTokenResponse(BaseModel):
    """Response after successful login/register with JWT tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token expiry in seconds")
    account_id: str
    display_name: str
    email: str


class AuthRefreshRequest(BaseModel):
    """Request to refresh an access token."""
    refresh_token: str


class AccountResponse(BaseModel):
    """Full account info returned for /me endpoint."""
    account_id: str
    email: str
    display_name: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class AccountGroupMembership(BaseModel):
    """Represents one group membership for an account."""
    user_id: str  # The per-group user_id
    group_id: str  # The group's group_id (UUID)
    group_name: str
    display_name: str  # Per-group display name
    color_avatar: str
    avatar_url: Optional[str] = None
    answer_streak: int = 0
    longest_answer_streak: int = 0
    joined_at: datetime


class AccountMeResponse(BaseModel):
    """Full /me response with account info and group memberships."""
    account: AccountResponse
    groups: List[AccountGroupMembership]


class UserChangePasswordRequest(BaseModel):
    """Request to change account password."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        return v


class JoinGroupRequest(BaseModel):
    """Request to join a group (authenticated user)."""
    invite_code: str = Field(..., min_length=1, max_length=10)
    display_name: Optional[str] = Field(None, min_length=1, max_length=50, description="Per-group display name (defaults to account display name)")
    color_avatar: Optional[str] = Field(None, description="Optional hex color like #AABBCC")

    @field_validator('invite_code')
    @classmethod
    def validate_invite_code(cls, v):
        v = v.strip().upper()
        if not re.match(r'^[A-Z0-9]{6,8}$', v):
            raise ValueError('Invalid invite code format')
        return v

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        if v is None:
            return v
        v = sanitize_string(v, 50)
        if not v or not v.strip():
            raise ValueError('Display name cannot be empty')
        return v

    @field_validator('color_avatar')
    @classmethod
    def validate_color(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not re.match(r'^#([A-Fa-f0-9]{6})$', v):
            raise ValueError('color_avatar must be a hex color like #AABBCC')
        return v


def sanitize_string(value: str, max_length: int = 1000) -> str:
    """Sanitize string input: remove HTML tags and scripts."""
    if not isinstance(value, str):
        return value
    # Remove common XSS vectors
    value = re.sub(r'<[^>]+>', '', value)  # Remove HTML tags
    value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)  # Remove javascript: protocol
    value = re.sub(r'on\w+\s*=', '', value, flags=re.IGNORECASE)  # Remove event handlers
    return value[:max_length].strip()


class QuestionTypeEnum(str, Enum):
    """Question types: binary voting, single choice, or free text"""
    BINARY_VOTE = "binary_vote"
    SINGLE_CHOICE = "single_choice"
    FREE_TEXT = "free_text"
    MEMBER_CHOICE = "member_choice"
    DUO_CHOICE = "duo_choice"


# ============= Group Schemas =============

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        v = sanitize_string(v, 100)
        if not v or not v.strip():
            raise ValueError('Group name cannot be empty')
        return v

class GroupResponse(BaseModel):
    id: int
    group_id: str
    name: str
    invite_code: str
    admin_token: str
    creator_id: Optional[int] = None
    created_at: datetime
    member_count: int

class GroupResponsePublic(BaseModel):
    id: int
    group_id: str
    name: str
    invite_code: str
    created_at: datetime
    member_count: int

# ============= User Schemas =============

# UserCreate removed — use /api/auth/register + /api/auth/groups/join instead

class UserResponse(BaseModel):
    id: int
    user_id: str
    group_id: str
    display_name: str
    color_avatar: str
    avatar_url: Optional[str] = None
    created_at: datetime
    answer_streak: int = 0
    longest_answer_streak: int = 0

# ============= Daily Question Schemas =============

class DailyQuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=1, max_length=255)
    question_type: QuestionTypeEnum = QuestionTypeEnum.MEMBER_CHOICE
    question_set_id: Optional[str] = None  # Optional; defaults to "Spicy" set
    option_a: Optional[str] = Field(None, max_length=100)
    option_b: Optional[str] = Field(None, max_length=100)
    allow_multiple: bool = False
    
    @field_validator('question_text')
    @classmethod
    def validate_question(cls, v):
        v = sanitize_string(v, 255)
        if not v or not v.strip():
            raise ValueError('Question text cannot be empty')
        return v
    
    @field_validator('option_a')
    @classmethod
    def validate_option_a(cls, v):
        if v is None:
            return v
        v = sanitize_string(v, 100)
        if v and len(v.strip()) == 0:
            return None
        return v
    
    @field_validator('option_b')
    @classmethod
    def validate_option_b(cls, v):
        if v is None:
            return v
        v = sanitize_string(v, 100)
        if v and len(v.strip()) == 0:
            return None
        return v

class DailyQuestionResponse(BaseModel):
    id: int
    question_id: str
    question_text: str
    question_type: QuestionTypeEnum
    options: list | None = None  # list of member names or duo labels (or null for free_text)
    option_counts: dict | None = None  # vote counts per option
    question_date: datetime
    is_active: bool
    total_votes: int
    allow_multiple: bool = False
    user_vote: Optional[Union[str, List[str]]] = None
    user_text_answer: Optional[str] = None
    user_streak: int = 0
    longest_streak: int = 0
    # Deprecated fields (kept for backward compatibility):
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    vote_count_a: int = 0
    vote_count_b: int = 0

# ============= Vote Schemas =============

class VoteCreate(BaseModel):
    answer: Optional[str] = Field(None, max_length=255)

class AnswerSubmissionCreate(BaseModel):
    answer: Optional[Union[str, List[str]]] = Field(None, description="String or list of strings for choices")  # For member/duo/binary/single choice
    text_answer: Optional[str] = Field(None, max_length=1000)  # For free text
    
    @field_validator('text_answer')
    @classmethod
    def validate_text_answer(cls, v):
        if v is None:
            return v
        v = sanitize_string(v, 1000)
        if v and len(v.strip()) == 0:
            return None
        return v

# ============= Question Template Schemas =============

class QuestionTemplateCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    question_text: str = Field(..., min_length=1, max_length=255)
    option_a_template: Optional[str] = Field(None, max_length=100)
    option_b_template: Optional[str] = Field(None, max_length=100)
    question_type: QuestionTypeEnum = QuestionTypeEnum.BINARY_VOTE
    allow_multiple: bool = False
    
    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        v = sanitize_string(v, 50)
        if not v or not v.strip():
            raise ValueError('Category cannot be empty')
        return v
    
    @field_validator('question_text')
    @classmethod
    def validate_question(cls, v):
        v = sanitize_string(v, 255)
        if not v or not v.strip():
            raise ValueError('Question text cannot be empty')
        return v

class QuestionTemplateResponse(BaseModel):
    template_id: str
    category: str
    question_text: str
    option_a_template: Optional[str] = None
    option_b_template: Optional[str] = None
    question_type: QuestionTypeEnum
    allow_multiple: bool = False
    is_public: bool
    created_at: datetime


# ============= Question Set Schemas =============

class QuestionSetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    template_ids: Optional[list[str]] = None
    is_public: Optional[bool] = True


class QuestionSetResponse(BaseModel):
    set_id: str
    name: str
    description: Optional[str]
    is_public: bool
    templates: Optional[list[QuestionTemplateResponse]] = None
    created_at: datetime


class GroupQuestionSetsResponse(BaseModel):
    group_id: str
    question_sets: list[QuestionSetResponse]


class GroupAssignSetsRequest(BaseModel):
    question_set_ids: list[str]
    replace: Optional[bool] = False


# ============= Push Notification Schemas =============

class DeviceTokenRegister(BaseModel):
    """Request to register a device token for push notifications"""
    token: str = Field(..., min_length=10, max_length=255)
    platform: str = Field(..., pattern=r'^(ios|android|web)$')
    device_name: Optional[str] = Field(None, max_length=100)
    
    @field_validator('token')
    @classmethod
    def validate_token(cls, v):
        return sanitize_string(v, 255)
    
    @field_validator('device_name')
    @classmethod
    def validate_device_name(cls, v):
        if v:
            return sanitize_string(v, 100)
        return v


class DeviceTokenResponse(BaseModel):
    """Response after registering a device token"""
    id: int
    token: str
    platform: str
    device_name: Optional[str]
    created_at: datetime
    is_active: bool


class PushNotificationStatus(BaseModel):
    """Status of push notification feature"""
    enabled: bool
    message: str