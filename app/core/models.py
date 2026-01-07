from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime
from bson import ObjectId
from pydantic_core import core_schema

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler):
        return core_schema.union_schema([
            core_schema.is_instance_schema(ObjectId),
            core_schema.no_info_plain_validator_function(cls.validate),
        ], serialization=core_schema.plain_serializer_function_ser_schema(lambda x: str(x)))

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")

# User Models
class UserBase(BaseModel):
    discord_id: str
    username: str
    discriminator: str
    avatar: Optional[str] = None
    email: Optional[str] = None

class UserCreate(UserBase):
    pass

class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    roles: List[str] = []
    guild_roles: List[str] = []
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class User(UserInDB):
    pass

# Application Models
class ApplicationBase(BaseModel):
    user_id: str
    form_type: str = "membership"
    data: dict

class ApplicationCreate(ApplicationBase):
    pass

class ApplicationInDB(ApplicationBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    result_score: Optional[float] = None
    ai_analysis: Optional[dict] = None
    status: str = "pending"  # pending, approved, rejected
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Application(ApplicationInDB):
    pass

# Event Models
class EventBase(BaseModel):
    title: str
    description: str
    game: str
    date: datetime
    max_participants: int
    prize: str
    rules: Optional[str] = None

class EventCreate(EventBase):
    pass

class EventInDB(EventBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    participants: List[str] = []
    winners: List[str] = []
    status: str = "upcoming"  # upcoming, ongoing, completed, cancelled
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    rewards: Optional[dict] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

class Event(EventInDB):
    pass

# Activity Log Models
class ActivityLog(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    action: str
    metadata: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

# System Log Models
class SystemLog(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    event: str
    level: str = "info"  # debug, info, warning, error, critical
    metadata: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

# Economy Models
class Economy(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    balance: int = 0
    transactions: List[dict] = []
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# Role Models
class RoleAssignment(BaseModel):
    user_id: str
    role: str
    assigned_by: str
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

# Announcement Models
class EmbedField(BaseModel):
    """Discord Embed Field"""
    name: str
    value: str
    inline: bool = False

class EmbedData(BaseModel):
    """Discord Embed Configuration"""
    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = "#5865F2"  # Discord blurple default
    thumbnail_url: Optional[str] = None
    image_url: Optional[str] = None
    footer_text: Optional[str] = None
    footer_icon_url: Optional[str] = None
    author_name: Optional[str] = None
    author_icon_url: Optional[str] = None
    timestamp: bool = False
    fields: List[EmbedField] = []

class MentionConfig(BaseModel):
    """Mention Configuration"""
    role_ids: List[str] = []
    user_ids: List[str] = []
    everyone: bool = False
    here: bool = False

class AnnouncementCreate(BaseModel):
    """Create Announcement Request"""
    guild_id: str
    channel_id: str
    embed: EmbedData
    mentions: MentionConfig = MentionConfig()
    content: Optional[str] = None  # Optional message before embed

class AnnouncementLog(BaseModel):
    """Announcement Log for Audit Trail"""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    manager_id: str
    manager_username: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    embed_summary: dict
    mentions: dict
    content: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}

