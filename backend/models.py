
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint, Index, Float, Enum, JSON
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
import enum
import pyotp
import bcrypt
from database import Base




def hash_password(password: str) -> str:
    """Hash a password for storing in the database."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_totp_secret() -> str:
    return pyotp.random_base32()

def verify_totp(token: str, secret: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)
class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    totp_secret = Column(String(32), nullable=True)  # Nullable until TOTP is set up
    totp_enabled = Column(Boolean, default=False)  # Track if TOTP has been configured
    temp_token = Column(String(64), nullable=True)  # For 2FA step
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, default=None, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # New fields for login security
    login_attempt_count = Column(Integer, default=0)
    last_login_attempt = Column(DateTime, nullable=True)
    last_login_ip = Column(INET, nullable=True)
    is_locked_until = Column(DateTime, nullable=True)  # Lockout timestamp
    
    # Relationships
    audit_logs = relationship("AuditLog", back_populates="admin", cascade="all, delete-orphan")


class QuestionTypeEnum(enum.Enum):
    """Question types: binary voting, single choice, or free text"""
    BINARY_VOTE = "binary_vote"
    SINGLE_CHOICE = "single_choice"
    FREE_TEXT = "free_text"
    MEMBER_CHOICE = "member_choice"  # choose one member from the group
    DUO_CHOICE = "duo_choice"        # choose one pair (duo) from generated pairs


class QuestionTemplate(Base):
    __tablename__ = "question_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    category = Column(String(50))
    question_text = Column(String(255))
    option_a_template = Column(String(100), nullable=True)
    option_b_template = Column(String(100), nullable=True)
    question_type = Column(Enum(QuestionTypeEnum), default=QuestionTypeEnum.BINARY_VOTE)
    allow_multiple = Column(Boolean, default=False)
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
    admin_token = Column(String(255), unique=True)  # Hashed token
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # New admin fields
    instance_admin_notes = Column(Text, nullable=True)
    total_sets_created = Column(Integer, default=0)
    
    members = relationship("User", back_populates="group", cascade="all, delete-orphan", foreign_keys="User.group_id")
    daily_questions = relationship("DailyQuestion", back_populates="group", cascade="all, delete-orphan")
    analytics = relationship("GroupAnalytics", back_populates="group", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[creator_id], backref="created_groups")

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
        UniqueConstraint('group_id', 'display_name', name='uq_group_display_name'),
        Index('idx_user_session', 'session_token'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(Integer, ForeignKey("groups.id"))
    display_name = Column(String(50))
    session_token = Column(String(255), unique=True)  # Hashed token
    session_token_expires_at = Column(DateTime, nullable=True)  # Token expiry
    color_avatar = Column(String(7), default="#3498db")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    answer_streak = Column(Integer, default=0)
    longest_answer_streak = Column(Integer, default=0)
    last_answer_date = Column(DateTime, default=None)
    # New admin fields
    is_suspended = Column(Boolean, default=False)
    suspension_reason = Column(Text, nullable=True)
    last_known_ip = Column(INET, nullable=True)
    user_metadata = Column(JSONB, nullable=True, default={})
    
    group = relationship("Group", back_populates="members", foreign_keys=[group_id])
    votes = relationship("Vote", back_populates="user", cascade="all, delete-orphan")
    group_streaks = relationship("UserGroupStreak", back_populates="user", cascade="all, delete-orphan")

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
    option_a = Column(String(100), nullable=True)
    option_b = Column(String(100), nullable=True)
    options = Column(Text, nullable=True)  # JSON-serialized list of answer choices
    question_type = Column(Enum(QuestionTypeEnum), default=QuestionTypeEnum.BINARY_VOTE)
    allow_multiple = Column(Boolean, default=False)
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
    # New ownership fields
    creator_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    created_by_group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    usage_count = Column(Integer, default=0)

    templates = relationship(
        "QuestionTemplate",
        secondary="question_set_templates",
        backref="question_sets"
    )
    creator = relationship("AdminUser", foreign_keys=[creator_id])
    created_by_group = relationship("Group", foreign_keys=[created_by_group_id])


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
    # New admin tracking fields
    assigned_by_admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    assignment_notes = Column(Text, nullable=True)

    # relationships (optional)
    group = relationship("Group", backref="group_question_sets")
    question_set = relationship("QuestionSet", backref="group_question_sets")
    assigned_by_admin = relationship("AdminUser", foreign_keys=[assigned_by_admin_id])

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
    answer = Column(Text, nullable=True)  # member name, duo label, or option key
    text_answer = Column(Text, nullable=True)  # For free-text answers
    voted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    question = relationship("DailyQuestion", back_populates="votes")
    user = relationship("User", back_populates="votes")


class UserGroupStreak(Base):
    __tablename__ = "user_group_streaks"
    __table_args__ = (
        UniqueConstraint('user_id', 'group_id', name='uq_user_group_streak'),
        Index('idx_user_group', 'user_id', 'group_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    group_id = Column(Integer, ForeignKey("groups.id"))
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    last_answer_date = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    user = relationship("User", back_populates="group_streaks")
    group = relationship("Group", backref="user_streaks")


class AuditLog(Base):
    """Track all critical admin actions for security and compliance."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index('idx_audit_logs_admin_id', 'admin_id'),
        Index('idx_audit_logs_action', 'action'),
        Index('idx_audit_logs_timestamp', 'timestamp'),
        Index('idx_audit_logs_target', 'target_type', 'target_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False)
    action = Column(String(50), nullable=False)  # e.g., 'token_recovery', 'user_data_change'
    target_type = Column(String(50), nullable=False)  # e.g., 'user', 'group', 'set'
    target_id = Column(String(255), nullable=False)  # UUID or ID of target
    before_state = Column(JSONB, nullable=True)  # Previous state as JSON
    after_state = Column(JSONB, nullable=True)  # New state as JSON
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    ip_address = Column(INET, nullable=True)  # IP of admin making the change
    reason = Column(Text, nullable=True)  # Admin's explanation
    
    admin = relationship("AdminUser", back_populates="audit_logs")


class GroupCustomSet(Base):
    """Tracks private question sets created by group creators (max 5 per group)."""
    __tablename__ = "group_custom_sets"
    __table_args__ = (
        UniqueConstraint('set_id', 'group_id', name='uq_group_custom_set'),
        Index('idx_group_custom_sets_group_id', 'group_id'),
        Index('idx_group_custom_sets_creator_id', 'creator_user_id'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    set_id = Column(Integer, ForeignKey("question_sets.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    creator_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    question_set = relationship("QuestionSet", foreign_keys=[set_id])
    group = relationship("Group", foreign_keys=[group_id])
    creator_user = relationship("User", foreign_keys=[creator_user_id])


class UserDeviceToken(Base):
    """
    Store FCM device tokens for push notifications.
    
    This table is only used when push notifications are enabled via FCM_SERVER_KEY.
    Each user can have multiple device tokens (one per device).
    """
    __tablename__ = "user_device_tokens"
    __table_args__ = (
        UniqueConstraint('user_id', 'token', name='uq_user_device_token'),
        Index('idx_device_tokens_user_id', 'user_id'),
        Index('idx_device_tokens_active', 'is_active'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False)  # FCM device token
    platform = Column(String(20), nullable=False)  # 'ios', 'android', 'web'
    device_name = Column(String(100), nullable=True)  # Optional device identifier
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    
    user = relationship("User", backref="device_tokens")

