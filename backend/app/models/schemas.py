"""
Pydantic request/response models for AnswerAgent backend.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class FileSelection(BaseModel):
    """File selection information for assistant messages."""
    kb_name: str = Field(..., description="Knowledge base name")
    file_path: str = Field(..., description="Relative file path within knowledge base")
    file_name: str = Field(..., description="File name only")


class Message(BaseModel):
    """Single message in a conversation."""
    id: Optional[str] = Field(None, description="Message UUID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    kb_names: Optional[List[str]] = Field(None, description="Knowledge bases used for this message")
    files_used: Optional[List[FileSelection]] = Field(None, description="Files referenced in this message")
    timestamp: Optional[datetime] = Field(None, description="Message timestamp")
    created_at: Optional[datetime] = Field(None, description="Message creation timestamp (alias)")


class ConversationSummary(BaseModel):
    """Summary of a conversation for list view."""
    id: str = Field(..., description="Conversation UUID")
    title: str = Field(..., description="Conversation title")
    kb_names: List[str] = Field(default_factory=list, description="Associated knowledge bases")
    updated_at: datetime = Field(..., description="Last update timestamp")
    message_count: Optional[int] = Field(None, description="Number of messages in conversation")


class ConversationDetail(BaseModel):
    """Full conversation details including all messages."""
    id: str = Field(..., description="Conversation UUID")
    title: str = Field(..., description="Conversation title")
    kb_names: List[str] = Field(default_factory=list, description="Associated knowledge bases")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    messages: List[Message] = Field(default_factory=list, description="All messages in the conversation")
    user_id: Optional[str] = Field(None, description="Owning user ID")


class ConversationInStorage(BaseModel):
    """Internal storage model for conversation JSON files."""
    id: str = Field(..., description="Conversation UUID")
    title: str = Field(..., description="Conversation title")
    kb_names: List[str] = Field(default_factory=list, description="Associated knowledge bases")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    messages: List[Message] = Field(default_factory=list, description="All messages in the conversation")
    user_id: Optional[str] = Field(None, description="Owning user ID")


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    title: Optional[str] = Field(None, description="Optional initial title")


# Alias for API consistency
ConversationCreate = CreateConversationRequest


class CreateConversationResponse(BaseModel):
    """Response after creating a conversation."""
    id: str = Field(..., description="Created conversation UUID")


class RenameConversationRequest(BaseModel):
    """Request to rename a conversation."""
    title: str = Field(..., min_length=1, max_length=200, description="New title")


# Alias for API consistency
ConversationUpdateTitle = RenameConversationRequest


class ChatStreamRequest(BaseModel):
    """Request for SSE streaming chat."""
    conversation_id: str = Field(..., description="Conversation UUID")
    message: str = Field(..., min_length=1, description="User message content")
    mode: str = Field(default="default", description="Chat mode: 'default' or 'agent'")


class SseKbMatched(BaseModel):
    """SSE event: knowledge bases matched."""
    type: str = "kb_matched"
    kb_names: List[str] = Field(default_factory=list, description="Matched knowledge base names")


class SseFilesSelected(BaseModel):
    """SSE event: files selected for a knowledge base."""
    type: str = "files_selected"
    kb: str = Field(..., description="Knowledge base name")
    files: List[str] = Field(default_factory=list, description="Selected file paths")


class SseToken(BaseModel):
    """SSE event: streaming token."""
    type: str = "token"
    content: str = Field(..., description="Token content")


class SseDone(BaseModel):
    """SSE event: stream completed."""
    type: str = "done"
    message_id: str = Field(..., description="Assistant message UUID")


class SseError(BaseModel):
    """SSE event: error occurred."""
    type: str = "error"
    message: str = Field(..., description="Error message")


# ============================================================
# Auth request/response models
# ============================================================

class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLoginRequest(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户信息响应"""
    id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    created_at: datetime = Field(..., description="注册时间")


class TokenResponse(BaseModel):
    """认证令牌响应"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    user: UserResponse = Field(..., description="用户信息")
