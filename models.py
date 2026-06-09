from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from utils.timezone import local_now
from database import Base

class UserGroup(Base):
    __tablename__ = "user_groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    description = Column(String(255))
    permissions = Column(String(255))  # Comma separated: "user:read,user:write"
    
    users = relationship("AdminUser", back_populates="group")

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(255))
    full_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    group_id = Column(Integer, ForeignKey("user_groups.id"), nullable=True)
    
    group = relationship("UserGroup", back_populates="users")

class TokenRecord(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(255), unique=True, index=True)
    name = Column(String(255))
    external_user_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=local_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    ai_quota = Column(Float, default=1000000.0) # Total credits allowed
    used_quota = Column(Float, default=0.0) # Total credits used
    permissions = Column(String(255), default="all") # Comma separated permissions: "bio,ai"
    
    projects = relationship("ThesisProject", back_populates="token_owner")
    video_search_conversations = relationship("VideoSearchConversation", back_populates="token_owner")

class ExternalUser(Base):
    __tablename__ = "external_users"
    __table_args__ = (
        UniqueConstraint("provider", "openid", name="uq_external_users_provider_openid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(64), default="biyu", index=True)
    openid = Column(String(255), index=True)
    entitlement_level = Column(String(64), default="experience")
    metadata_info = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=local_now)
    updated_at = Column(DateTime(timezone=True), default=local_now, onupdate=local_now)

class OAuthUserSession(Base):
    __tablename__ = "oauth_user_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_token = Column(String(255), unique=True, index=True)
    external_user_id = Column(Integer, nullable=True, index=True)
    openid = Column(String(255), index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=local_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)

class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    id = Column(Integer, primary_key=True, index=True)
    third_order_no = Column(String(128), unique=True, index=True)
    external_user_id = Column(Integer, nullable=True, index=True)
    openid = Column(String(255), index=True)
    product_id = Column(String(255), index=True)
    request_id = Column(String(255), nullable=True)
    pay_url = Column(Text, nullable=True)
    status = Column(String(32), default="pending", index=True)
    state = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=local_now)
    updated_at = Column(DateTime(timezone=True), default=local_now, onupdate=local_now)

class PaymentOrderEntitlement(Base):
    __tablename__ = "payment_order_entitlements"
    id = Column(Integer, primary_key=True, index=True)
    third_order_no = Column(String(128), unique=True, index=True)
    external_user_id = Column(Integer, nullable=True, index=True)
    openid = Column(String(255), index=True)
    product_id = Column(String(255), index=True)
    product_slug = Column(String(64), nullable=True, index=True)
    product_name = Column(String(255), nullable=True)
    product_price = Column(Float, nullable=True)
    product_quota = Column(Float, nullable=True)
    duration_days = Column(Integer, nullable=True)
    product_snapshot = Column(Text, nullable=True)
    paid_amount = Column(Float, nullable=True)
    paid_at = Column(String(64), nullable=True)
    notify_payload = Column(Text, nullable=True)
    issued_token_id = Column(Integer, nullable=True, index=True)
    issued_ai_quota = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=local_now)
    updated_at = Column(DateTime(timezone=True), default=local_now, onupdate=local_now)

class ThesisProject(Base):
    __tablename__ = "thesis_projects"
    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("tokens.id"), nullable=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    title = Column(String(255))
    topic = Column(String(255))
    discipline = Column(String(255))
    language = Column(String(32), default="zh")
    length = Column(String(64))
    style = Column(String(64))
    thesis_type = Column(String(64))
    current_step = Column(Integer, default=1)
    reference_files = Column(Text, nullable=True)  # JSON: list of verified reference metadata
    style_example_file = Column(Text, nullable=True)  # JSON: style example metadata
    created_at = Column(DateTime(timezone=True), default=local_now)
    updated_at = Column(DateTime(timezone=True), default=local_now, onupdate=local_now)
    
    token_owner = relationship("TokenRecord", back_populates="projects")
    admin_owner = relationship("AdminUser")
    steps = relationship("ThesisStep", back_populates="project", cascade="all, delete-orphan")

class ThesisStep(Base):
    __tablename__ = "thesis_steps"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("thesis_projects.id"))
    step_num = Column(Integer)
    content = Column(Text) # JSON or markdown content
    metadata_info = Column(Text) # JSON string for extra info like references
    created_at = Column(DateTime(timezone=True), default=local_now)
    
    project = relationship("ThesisProject", back_populates="steps")

class VideoSearchConversation(Base):
    __tablename__ = "video_search_conversations"
    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("tokens.id"), nullable=True, index=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    title = Column(String(255))
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=local_now)
    updated_at = Column(DateTime(timezone=True), default=local_now, onupdate=local_now)

    token_owner = relationship("TokenRecord", back_populates="video_search_conversations")
    admin_owner = relationship("AdminUser")
    messages = relationship(
        "VideoSearchMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="VideoSearchMessage.id",
    )

class VideoSearchMessage(Base):
    __tablename__ = "video_search_messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("video_search_conversations.id"), index=True)
    role = Column(String(32), index=True)
    content = Column(Text, default="")
    tool_name = Column(String(128), nullable=True)
    tool_arguments = Column(Text, nullable=True)
    video_result = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=local_now)

    conversation = relationship("VideoSearchConversation", back_populates="messages")
