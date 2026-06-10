"""对话 CRUD 接口路由

提供对话的创建、列表、详情、重命名、删除等 REST API 接口。

接口清单:
- GET    /api/conversations          -> 获取对话列表（按 updated_at 倒序）
- POST   /api/conversations          -> 创建新对话
- GET    /api/conversations/{id}     -> 获取对话详情
- GET    /api/conversations/{id}/export -> 导出对话为 Markdown 文件
- DELETE /api/conversations/{id}     -> 删除对话
- PATCH  /api/conversations/{id}/title -> 重命名对话标题
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from typing import List
from datetime import datetime

from core.chat_manager import (
    chat_manager,
    ConversationNotFoundError,
    PathSecurityError,
)
from core.deps import get_current_user
from models.schemas import (
    ConversationCreate,
    ConversationUpdateTitle,
    ConversationSummary,
    ConversationDetail,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=List[ConversationSummary])
async def list_conversations(current_user: dict = Depends(get_current_user)):
    """获取当前用户的对话列表

    按 updated_at 倒序排列，最新的对话在前。

    Returns:
        List[ConversationSummary]: 对话列表
    """
    return chat_manager.list_conversations_by_user(current_user["user_id"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationCreate,
    current_user: dict = Depends(get_current_user),
):
    """创建新对话

    Args:
        data: 创建对话请求数据

    Returns:
        dict: 包含新创建对话的 id 和 title
    """
    conversation_id = chat_manager.create_conversation(
        title=data.title, user_id=current_user["user_id"]
    )
    return {
        "id": conversation_id,
        "title": data.title,
    }


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取对话详情

    Args:
        conversation_id: 对话 ID

    Returns:
        ConversationDetail: 对话详情及消息列表

    Raises:
        HTTPException 404: 对话不存在
        HTTPException 400: 对话 ID 格式无效
    """
    try:
        conv = chat_manager.get_conversation(conversation_id)

        # 校验对话所有权
        if conv.user_id and conv.user_id != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation not found: {conversation_id}",
            )

        return conv
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conversation ID: {str(e)}"
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}"
        )
    except PathSecurityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除对话

    Args:
        conversation_id: 对话 ID

    Raises:
        HTTPException 404: 对话不存在
        HTTPException 400: 对话 ID 格式无效
    """
    try:
        # 先校验对话存在且属于当前用户
        conv = chat_manager.get_conversation(conversation_id)
        if conv.user_id and conv.user_id != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation not found: {conversation_id}",
            )

        chat_manager.delete_conversation(conversation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conversation ID: {str(e)}"
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}"
        )
    except PathSecurityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )


@router.patch("/{conversation_id}/title", response_model=dict)
async def rename_conversation(
    conversation_id: str,
    data: ConversationUpdateTitle,
    current_user: dict = Depends(get_current_user),
):
    """重命名对话标题

    Args:
        conversation_id: 对话 ID
        data: 包含新标题的请求数据

    Returns:
        dict: 包含对话 id 和新 title

    Raises:
        HTTPException 404: 对话不存在
        HTTPException 400: 对话 ID 格式无效
    """
    try:
        # 先校验对话属于当前用户
        conv = chat_manager.get_conversation(conversation_id)
        if conv.user_id and conv.user_id != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation not found: {conversation_id}",
            )

        chat_manager.rename_conversation(conversation_id, data.title)
        return {
            "id": conversation_id,
            "title": data.title,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conversation ID: {str(e)}"
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}"
        )
    except PathSecurityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )


def _build_export_markdown(conv: ConversationDetail) -> str:
    """将对话内容拼接为 Markdown 字符串

    格式:
        # 标题
        > 创建时间 / 更新时间
        ---
        ## 用户
        内容
        ## 助手
        > 参考知识库 / 参考文件
        内容
        ---

    Args:
        conv: 对话详情对象

    Returns:
        str: Markdown 格式的对话内容
    """
    lines: List[str] = []

    # 标题
    lines.append(f"# {conv.title}")
    lines.append("")

    # 时间信息
    created_str = conv.created_at.strftime("%Y-%m-%d %H:%M:%S") if conv.created_at else ""
    updated_str = conv.updated_at.strftime("%Y-%m-%d %H:%M:%S") if conv.updated_at else ""
    if created_str:
        lines.append(f"> 创建时间: {created_str}")
    if updated_str:
        lines.append(f"> 更新时间: {updated_str}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 逐条消息
    for msg in conv.messages:
        role_label = "用户" if msg.role == "user" else "助手"
        lines.append(f"## {role_label}")
        lines.append("")

        # 助手消息：附加参考知识库和文件
        if msg.role == "assistant":
            if msg.kb_names:
                lines.append(f"> 参考知识库: {', '.join(msg.kb_names)}")
            if msg.files_used:
                file_refs = [f"{f.kb_name}/{f.file_path}" for f in msg.files_used]
                lines.append(f"> 参考文件: {', '.join(file_refs)}")
            if msg.thinking_steps:
                lines.append("")
                lines.append("### 深度思考过程")
                lines.append("")
                for step_idx, step in enumerate(msg.thinking_steps, 1):
                    if step.type == "action":
                        lines.append(f"**步骤 {step_idx}：思考**")
                        lines.append("")
                        if step.thought:
                            lines.append(step.thought)
                        if step.tool:
                            lines.append(f"> 使用工具: `{step.tool}`")
                            lines.append(f"> 工具输入: `{step.toolInput or ''}`")
                    elif step.type == "observation":
                        lines.append(f"**步骤 {step_idx}：观察结果**")
                        lines.append("")
                        if step.result:
                            lines.append(step.result)
                    lines.append("")
            if msg.kb_names or msg.files_used:
                lines.append("")
        lines.append(msg.content)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """导出对话为 Markdown 文件

    Args:
        conversation_id: 对话 ID

    Returns:
        Response: Markdown 文件下载响应

    Raises:
        HTTPException 404: 对话不存在
        HTTPException 400: 对话 ID 格式无效
    """
    try:
        conv = chat_manager.get_conversation(conversation_id)

        # 校验对话所有权
        if conv.user_id and conv.user_id != current_user["user_id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation not found: {conversation_id}",
            )

        md_content = _build_export_markdown(conv)

        # 文件名：标题中的特殊字符替换为下划线
        safe_title = conv.title.replace("/", "_").replace("\\", "_").replace(":", "_")
        filename = f"{safe_title}.md"

        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename.encode('ascii', 'ignore').decode()}\"",
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conversation ID: {str(e)}"
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}"
        )
    except PathSecurityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )
