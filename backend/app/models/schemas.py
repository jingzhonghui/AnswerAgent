"""
Pydantic request/response models for AnswerAgent backend.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class FileSelection(BaseModel):
    """File selection information for assistant messages."""
    kb_name: str = Field(..., description="Knowledge base name")
    file_path: str = Field(..., description="Relative file path within knowledge base")
    file_name: str = Field(..., description="File name only")


class ThinkingStep(BaseModel):
    """深度思考步骤"""
    type: str = Field(..., description="Step type: 'action' or 'observation'")
    thought: Optional[str] = Field(None, description="Agent reasoning text")
    tool: Optional[str] = Field(None, description="Tool name")
    toolInput: Optional[str] = Field(None, description="Tool input arguments")
    result: Optional[str] = Field(None, description="Tool execution result")


class Message(BaseModel):
    """Single message in a conversation."""
    id: Optional[str] = Field(None, description="Message UUID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    kb_names: Optional[List[str]] = Field(None, description="Knowledge bases used for this message")
    files_used: Optional[List[FileSelection]] = Field(None, description="Files referenced in this message")
    thinking_steps: Optional[List[ThinkingStep]] = Field(None, description="Deep thinking steps (only for assistant messages in deep mode)")
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
    mode: str = Field(default="default", description="Chat mode: 'default', 'deep', or 'agent'")


class HistoryMessage(BaseModel):
    """历史消息（外部接口传入）"""
    role: str = Field(..., pattern="^(user|assistant)$", description="消息角色")
    content: str = Field(..., min_length=1, description="消息内容")


class ExternalChatRequest(BaseModel):
    """免登录外部流式聊天请求"""
    message: str = Field(..., min_length=1, description="用户消息内容")
    mode: str = Field(default="default", pattern="^(default|deep)$", description="聊天模式")
    history: List[HistoryMessage] = Field(default_factory=list, description="可选历史消息")


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
    is_admin: bool = Field(default=False, description="是否为管理员")
    created_at: datetime = Field(..., description="注册时间")


class TokenResponse(BaseModel):
    """认证令牌响应"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    user: UserResponse = Field(..., description="用户信息")


# ============================================================
# Admin request/response models
# ============================================================

class AdminUserCreate(BaseModel):
    """管理员创建用户请求"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    is_admin: bool = Field(default=False, description="是否设为管理员")


class AdminUserUpdate(BaseModel):
    """管理员更新用户请求"""
    is_admin: Optional[bool] = Field(None, description="是否设为管理员")


class AdminResetPasswordRequest(BaseModel):
    """管理员重置用户密码请求"""
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class AdminUserInfo(BaseModel):
    """管理员视角的用户信息"""
    id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    is_admin: bool = Field(default=False, description="是否为管理员")
    created_at: datetime = Field(..., description="注册时间")
    conversation_count: int = Field(default=0, description="对话数量")


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class ModelConfigItem(BaseModel):
    """模型配置项"""
    key: str = Field(..., description="配置键")
    value: str = Field(default="", description="配置值")
    description: str = Field(default="", description="配置说明")

    @field_validator('value', mode='before')
    @classmethod
    def coerce_value_to_str(cls, v):
        if v is None:
            return ""
        return str(v)


class ModelConfigUpdate(BaseModel):
    """批量更新模型配置请求"""
    configs: List[ModelConfigItem] = Field(..., description="配置项列表")


class AdminConversationSummary(BaseModel):
    """管理员视角的对话摘要（含用户信息）"""
    id: str = Field(..., description="对话 ID")
    title: str = Field(..., description="对话标题")
    user_id: Optional[str] = Field(None, description="所属用户 ID")
    username: Optional[str] = Field(None, description="所属用户名")
    message_count: int = Field(default=0, description="消息数量")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


# ============================================================
# 知识库生成工作流模型
# ============================================================

class AnalysisTask(BaseModel):
    """分析阶段生成的知识库文件任务"""
    id: str = Field(..., description="任务 ID")
    description: str = Field(..., description="任务描述（该文件涵盖什么内容）")
    target_file: str = Field(..., description="目标文件名（相对路径）")
    dependencies: List[str] = Field(default_factory=list, description="依赖的任务 ID 列表")


class WorkflowStartRequest(BaseModel):
    """启动知识库生成工作流请求"""
    input_type: str = Field(..., pattern="^(local_path|git_url|archive)$", description="输入类型")
    input_value: str = Field(..., min_length=1, description="输入值（路径/URL）")


class WorkflowTaskResponse(BaseModel):
    """工作流任务状态响应"""
    id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="状态: pending/preprocessing/analyzing/executing/completed/failed/paused")
    input_type: str = Field(..., description="输入类型")
    input_value: str = Field(..., description="输入值")
    knowledge_name: Optional[str] = Field(None, description="知识库名称")
    repo_type: Optional[str] = Field(None, description="仓库类型: code/doc")
    stage: str = Field(default="init", description="当前阶段")
    stage_progress: dict = Field(default_factory=dict, description="阶段内进度")
    task_list: List[AnalysisTask] = Field(default_factory=list, description="分析任务表")
    completed_tasks: List[str] = Field(default_factory=list, description="已完成任务 ID 列表")
    result_path: Optional[str] = Field(None, description="生成的知识库路径")
    error: Optional[str] = Field(None, description="错误信息")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class WorkflowStartResponse(BaseModel):
    """启动工作流响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="初始状态")
