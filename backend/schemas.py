from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List
import secrets
import string

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    
    @validator('name')
    def name_not_empty(cls, v):
        assert v.strip(), "Group name cannot be empty"
        return v.strip()

class GroupResponse(BaseModel):
    id: int
    group_id: str
    name: str
    invite_code: str
    created_at: datetime
    member_count: int = 0
    
    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=50)
    group_invite_code: str
    color_avatar: Optional[str] = "#3498db"

class UserResponse(BaseModel):
    id: int
    user_id: str
    display_name: str
    color_avatar: str
    session_token: str
    created_at: datetime
    answer_streak: int = 0
    longest_answer_streak: int = 0
    
    class Config:
        from_attributes = True

class DailyQuestionCreate(BaseModel):
    question_text: str = Field(..., min_length=5, max_length=255)
    option_a: str = Field(..., min_length=1, max_length=100)
    option_b: str = Field(..., min_length=1, max_length=100)

class VoteCreate(BaseModel):
    answer: str = Field(..., regex=r"^[AB]$")

class VoteResponse(BaseModel):
    vote_id: str
    answer: str
    user_id: str
    voted_at: datetime
    
    class Config:
        from_attributes = True

class DailyQuestionResponse(BaseModel):
    id: int
    question_id: str
    question_text: str
    option_a: str
    option_b: str
    question_date: datetime
    is_active: bool
    vote_count_a: int = 0
    vote_count_b: int = 0
    total_votes: int = 0
    user_vote: Optional[str] = None
    user_streak: int = 0
    longest_streak: int = 0
    
    class Config:
        from_attributes = True
