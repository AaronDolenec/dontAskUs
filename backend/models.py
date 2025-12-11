from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint, Index, Float, Enum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
import enum
from database import Base

class QuestionTemplate(Base):
    __tablename__ = "question_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    category = Column(String(50))
    question_text = Column(String(255))
    option_a_template = Column(String(100))
    option_b_template = Column(String(100))
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        Index('idx_group_code', 'invite_code'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), index=True)
    invite_code = Column(String(8), unique=True, index=True)
    qr_data = Column(Text)
    admin_token = Column(String(255), unique=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    members = relationship("User", back_populates="group", cascade="all, delete-orphan")
    daily_questions = relationship("DailyQuestion", back_populates="group", cascade="all, delete-orphan")
    analytics = relationship("GroupAnalytics", back_populates="group", cascade="all, delete-orphan")

class GroupAnalytics(Base):
    __tablename__ = "group_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    total_members = Column(Integer, default=0)
    total_questions_created = Column(Integer, default=0)
    total_votes_cast = Column(Integer, default=0)
    average_participation_rate = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    group = relationship("Group", back_populates="analytics")

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint('group_id', 'session_token', name='uq_group_session'),
        Index('idx_user_session', 'session_token'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(Integer, ForeignKey("groups.id"))
    display_name = Column(String(50))
    session_token = Column(String(255), unique=True)
    color_avatar = Column(String(7), default="#3498db")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    answer_streak = Column(Integer, default=0)
    longest_answer_streak = Column(Integer, default=0)
    last_answer_date = Column(DateTime, default=None)
    
    group = relationship("Group", back_populates="members")
    votes = relationship("Vote", back_populates="user", cascade="all, delete-orphan")

class DailyQuestion(Base):
    __tablename__ = "daily_questions"
    __table_args__ = (
        UniqueConstraint('group_id', 'question_date', name='uq_group_date'),
        Index('idx_group_date', 'group_id', 'question_date'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(Integer, ForeignKey("groups.id"))
    template_id = Column(Integer, ForeignKey("question_templates.id"), nullable=True)
    question_text = Column(String(255))
    option_a = Column(String(100))
    option_b = Column(String(100))
    question_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    group = relationship("Group", back_populates="daily_questions")
    template = relationship("QuestionTemplate")
    votes = relationship("Vote", back_populates="question", cascade="all, delete-orphan")


class QuestionSet(Base):
    __tablename__ = "question_sets"

    id = Column(Integer, primary_key=True, index=True)
    set_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), index=True)
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    templates = relationship(
        "QuestionTemplate",
        secondary="question_set_templates",
        backref="question_sets"
    )


class QuestionSetTemplate(Base):
    __tablename__ = "question_set_templates"

    id = Column(Integer, primary_key=True)
    question_set_id = Column(Integer, ForeignKey("question_sets.id"))
    template_id = Column(Integer, ForeignKey("question_templates.id"))


class GroupQuestionSet(Base):
    __tablename__ = "group_question_sets"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    question_set_id = Column(Integer, ForeignKey("question_sets.id"))
    is_active = Column(Boolean, default=True)
    selected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # relationships (optional)
    group = relationship("Group", backref="group_question_sets")
    question_set = relationship("QuestionSet", backref="group_question_sets")

class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint('question_id', 'user_id', name='uq_question_user'),
        Index('idx_vote_question', 'question_id'),
        Index('idx_vote_user', 'user_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    vote_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    question_id = Column(Integer, ForeignKey("daily_questions.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    answer = Column(String(1))  # 'A' or 'B'
    voted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    question = relationship("DailyQuestion", back_populates="votes")
    user = relationship("User", back_populates="votes")
