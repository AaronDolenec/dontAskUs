
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Union
from datetime import datetime
from enum import Enum
import re

# ============= Admin Schemas =============
class AdminLoginRequest(BaseModel):
    username: str
    password: str

class AdminLoginResponse(BaseModel):
    temp_token: str
    message: str = "2FA required"

class Admin2FARequest(BaseModel):
    temp_token: str
    totp_code: str

class Admin2FAResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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

class UserCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=50)
    group_invite_code: str = Field(..., min_length=1, max_length=10)
    color_avatar: Optional[str] = Field(
        default=None,
        description="Optional hex color like #AABBCC"
    )
    
    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        v = sanitize_string(v, 50)
        if not v or not v.strip():
            raise ValueError('Display name cannot be empty')
        if len(v) < 1:
            raise ValueError('Display name too short')
        return v
    
    @field_validator('group_invite_code')
    @classmethod
    def validate_invite_code(cls, v):
        v = v.strip().upper()
        if not re.match(r'^[A-Z0-9]{6,8}$', v):
            raise ValueError('Invalid invite code format')
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

class UserResponse(BaseModel):
    id: int
    user_id: str
    group_id: str
    display_name: str
    color_avatar: str
    avatar_url: Optional[str] = None
    session_token: str
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