"""管理后台 API 路由

提供模型配置、用户管理、会话管理等功能。

接口清单:
- GET    /api/admin/model-config        -> 获取全部模型配置
- PUT    /api/admin/model-config        -> 批量更新模型配置
- GET    /api/admin/users               -> 获取用户列表
- POST   /api/admin/users               -> 管理员创建用户
- PUT    /api/admin/users/{id}          -> 更新用户（设置/取消管理员）
- DELETE /api/admin/users/{id}          -> 删除用户
- GET    /api/admin/conversations       -> 获取所有对话（含用户信息）
- GET    /api/admin/conversations/{id}  -> 查看任意对话详情
- DELETE /api/admin/conversations/{id}  -> 删除任意对话
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from core.chat_manager import (
    chat_manager,
    ConversationNotFoundError,
    PathSecurityError,
)
from core.database import get_db
from core.deps import get_current_admin_user
from core.model_config import get_all_public as mc_get_all_public, update_batch as mc_update_batch
from core.model_config import MODEL_CONFIG_KEYS, _SENSITIVE_KEYS
from core.security import hash_password, create_access_token
from models.schemas import (
    AdminUserCreate,
    AdminUserInfo,
    AdminConversationSummary,
    ConversationDetail,
    ModelConfigUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================
# 模型配置
# ============================================================

@router.get("/model-config")
async def get_model_config(admin: dict = Depends(get_current_admin_user)):
    """获取全部模型配置（含描述，敏感键不出现在返回中）"""
    return {"configs": mc_get_all_public()}


@router.put("/model-config")
async def update_model_config(
    data: ModelConfigUpdate,
    admin: dict = Depends(get_current_admin_user),
):
    """批量更新模型配置，即时生效

    Args:
        data: 配置项列表，每项含 key + value

    Returns:
        dict: {"message": "配置已更新", "updated": [...键列表...]}
    """
    updates = {}
    for item in data.configs:
        if item.key not in MODEL_CONFIG_KEYS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"未知的配置键: {item.key}",
            )
        if item.key in _SENSITIVE_KEYS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"配置项 {item.key} 不允许通过 API 修改",
            )
        updates[item.key] = item.value

    await mc_update_batch(updates)
    return {
        "message": "配置已更新，即时生效",
        "updated": list(updates.keys()),
    }


# ============================================================
# 用户管理
# ============================================================

@router.get("/users", response_model=List[AdminUserInfo])
async def list_users(admin: dict = Depends(get_current_admin_user)):
    """获取所有用户列表（含对话数量统计）"""
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT u.id, u.username, u.is_admin, u.created_at,
                   (SELECT COUNT(*) FROM conversations c WHERE c.user_id = u.id) AS conversation_count
            FROM users u
            ORDER BY u.created_at DESC
        """)
        rows = await cursor.fetchall()
        return [
            AdminUserInfo(
                id=row["id"],
                username=row["username"],
                is_admin=bool(row["is_admin"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                conversation_count=row["conversation_count"],
            )
            for row in rows
        ]


@router.post("/users", response_model=AdminUserInfo, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: AdminUserCreate,
    admin: dict = Depends(get_current_admin_user),
):
    """管理员创建新用户

    Args:
        data: 用户名、密码、是否管理员

    Returns:
        AdminUserInfo: 新用户信息
    """
    async with get_db() as db:
        # 检查用户名是否已存在
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?", (data.username,)
        )
        if await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        password_hash = hash_password(data.password)

        await db.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, data.username, password_hash, 1 if data.is_admin else 0, now),
        )
        await db.commit()

    return AdminUserInfo(
        id=user_id,
        username=data.username,
        is_admin=data.is_admin,
        created_at=datetime.fromisoformat(now),
        conversation_count=0,
    )


@router.put("/users/{user_id}", response_model=AdminUserInfo)
async def update_user(
    user_id: str,
    data: dict,
    admin: dict = Depends(get_current_admin_user),
):
    """更新用户（设置/取消管理员权限）

    请求体: {"is_admin": true/false}
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, is_admin, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在",
            )

        # 不允许取消自己的管理员权限
        if row["id"] == admin["user_id"] and data.get("is_admin") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能取消自己的管理员权限",
            )

        new_is_admin = 1 if data.get("is_admin") else 0
        await db.execute(
            "UPDATE users SET is_admin = ? WHERE id = ?",
            (new_is_admin, user_id),
        )
        await db.commit()

        # 获取对话数量
        cursor = await db.execute(
            "SELECT COUNT(*) AS cnt FROM conversations WHERE user_id = ?",
            (user_id,),
        )
        conv_count = (await cursor.fetchone())["cnt"]

    return AdminUserInfo(
        id=row["id"],
        username=row["username"],
        is_admin=bool(new_is_admin),
        created_at=datetime.fromisoformat(row["created_at"]),
        conversation_count=conv_count,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    """删除用户及其所有对话

    Args:
        user_id: 要删除的用户 ID

    Raises:
        HTTPException 400: 不允许删除自己
    """
    if user_id == admin["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己",
        )

    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在",
            )

        # 获取该用户的所有对话
        cursor = await db.execute(
            "SELECT id FROM conversations WHERE user_id = ?",
            (user_id,),
        )
        conv_ids = [row["id"] for row in await cursor.fetchall()]

        # 删除对话（DB 记录 + JSON 文件）
        for cid in conv_ids:
            try:
                chat_manager.delete_conversation(cid)
            except (ConversationNotFoundError, PathSecurityError):
                pass  # 对话可能已被手动删除

        # 删除用户
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()


# ============================================================
# 会话管理
# ============================================================

@router.get("/conversations", response_model=List[AdminConversationSummary])
async def list_all_conversations(
    admin: dict = Depends(get_current_admin_user),
    user_id: str = Query(default="", description="按用户 ID 筛选"),
    search: str = Query(default="", description="按标题搜索"),
):
    """获取所有用户的对话列表（管理员视角）

    Args:
        user_id: 可选，按用户 ID 筛选
        search: 可选，按标题模糊搜索
    """
    query = """
        SELECT c.id, c.title, c.user_id, u.username, c.created_at, c.updated_at
        FROM conversations c
        LEFT JOIN users u ON c.user_id = u.id
        WHERE 1=1
    """
    params: list = []

    if user_id:
        query += " AND c.user_id = ?"
        params.append(user_id)

    if search:
        query += " AND c.title LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY c.updated_at DESC LIMIT 500"

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        results = []
        for row in rows:
            # 从 JSON 文件获取消息数量
            try:
                conv = chat_manager.get_conversation(row["id"])
                msg_count = len(conv.messages)
            except Exception:
                msg_count = 0

            results.append(AdminConversationSummary(
                id=row["id"],
                title=row["title"],
                user_id=row["user_id"],
                username=row["username"],
                message_count=msg_count,
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            ))

        return results


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_any_conversation(
    conversation_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    """查看任意用户的对话详情（管理员不受所有权限制）"""
    try:
        return chat_manager.get_conversation(conversation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conversation ID: {str(e)}",
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}",
        )
    except PathSecurityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_any_conversation(
    conversation_id: str,
    admin: dict = Depends(get_current_admin_user),
):
    """删除任意对话（管理员不受所有权限制）"""
    try:
        chat_manager.delete_conversation(conversation_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conversation ID: {str(e)}",
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}",
        )
    except PathSecurityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format",
        )