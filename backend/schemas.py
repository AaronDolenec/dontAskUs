from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# ============= Group Schemas =============

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class GroupResponse(BaseModel):
    id: int
    group_id: str
    name: str
    invite_code: str
    admin_token: str
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
    color_avatar: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    user_id: str
    display_name: str
    color_avatar: str
    session_token: str
    created_at: datetime
    answer_streak: int = 0
    longest_answer_streak: int = 0

# ============= Daily Question Schemas =============

class DailyQuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=1, max_length=255)
    option_a: str = Field(..., min_length=1, max_length=100)
    option_b: str = Field(..., min_length=1, max_length=100)

class DailyQuestionResponse(BaseModel):
    id: int
    question_id: str
    question_text: str
    option_a: str
    option_b: str
    question_date: datetime
    is_active: bool
    vote_count_a: int
    vote_count_b: int
    total_votes: int
    user_vote: Optional[str] = None
    user_streak: int = 0
    longest_streak: int = 0

# ============= Vote Schemas =============

class VoteCreate(BaseModel):
    answer: str = Field(..., pattern=r"^[AB]$")

# ============= Question Template Schemas =============

class QuestionTemplateCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    question_text: str = Field(..., min_length=1, max_length=255)
    option_a_template: str = Field(..., min_length=1, max_length=100)
    option_b_template: str = Field(..., min_length=1, max_length=100)

class QuestionTemplateResponse(BaseModel):
    template_id: str
    category: str
    question_text: str
    option_a_template: str
    option_b_template: str
    is_public: bool
    created_at: datetime