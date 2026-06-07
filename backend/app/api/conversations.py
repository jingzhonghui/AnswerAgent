"""对话 CRUD 接口路由

提供对话的创建、列表、详情、重命名、删除等 REST API 接口。

接口清单:
- GET    /api/conversations          -> 获取对话列表（按 updated_at 倒序）
- POST   /api/conversations          -> 创建新对话
- GET    /api/conversations/{id}     -> 获取对话详情
- DELETE /api/conversations/{id}     -> 删除对话
- PATCH  /api/conversations/{id}/title -> 重命名对话标题
"""
from fastapi import APIRouter, HTTPException, status
from typing import List

from core.chat_manager import (
    chat_manager,
    ConversationNotFoundError,
    PathSecurityError,
)
from models.schemas import (
    ConversationCreate,
    ConversationUpdateTitle,
    ConversationSummary,
    ConversationDetail,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=List[ConversationSummary])
async def list_conversations():
    """获取对话列表

    按 updated_at 倒序排列，最新的对话在前。

    Returns:
        List[ConversationSummary]: 对话列表
    """
    return chat_manager.list_conversations()


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_conversation(data: ConversationCreate):
    """创建新对话

    Args:
        data: 创建对话请求数据

    Returns:
        dict: 包含新创建对话的 id 和 title
    """
    conversation_id = chat_manager.create_conversation(title=data.title)
    return {
        "id": conversation_id,
        "title": data.title,
    }


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
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
        return chat_manager.get_conversation(conversation_id)
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
async def delete_conversation(conversation_id: str):
    """删除对话

    Args:
        conversation_id: 对话 ID

    Raises:
        HTTPException 404: 对话不存在
        HTTPException 400: 对话 ID 格式无效
    """
    try:
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
async def rename_conversation(conversation_id: str, data: ConversationUpdateTitle):
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
