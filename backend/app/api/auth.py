"""认证接口路由

提供用户注册、登录、获取当前用户信息等 REST API 接口。

接口清单:
- POST /api/auth/register    -> 用户注册
- POST /api/auth/login       -> 用户登录
- GET  /api/auth/me          -> 获取当前用户信息（需认证）
- POST /api/auth/change-password -> 修改密码（需认证）
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import get_db
from core.deps import get_current_user
from core.security import hash_password, verify_password, create_access_token
from models.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
    ChangePasswordRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegisterRequest):
    """用户注册

    创建新用户账号，成功后返回 JWT 令牌和用户信息。

    Args:
        data: 注册请求（用户名 + 密码）

    Returns:
        TokenResponse: 包含 access_token 和用户信息

    Raises:
        HTTPException 409: 用户名已存在
    """
    async with get_db() as db:
        # 检查用户名是否已存在
        cursor = await db.execute(
            "SELECT id FROM users WHERE username = ?", (data.username,)
        )
        existing = await cursor.fetchone()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

        # 创建用户
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        password_hash = hash_password(data.password)

        await db.execute(
            "INSERT INTO users (id, username, password_hash, is_admin, created_at) VALUES (?, ?, ?, 0, ?)",
            (user_id, data.username, password_hash, now),
        )
        await db.commit()

    # 生成 JWT 令牌
    access_token = create_access_token(user_id, data.username, is_admin=False)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            username=data.username,
            is_admin=False,
            created_at=datetime.fromisoformat(now),
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLoginRequest):
    """用户登录

    验证用户名和密码，成功后返回 JWT 令牌和用户信息。

    Args:
        data: 登录请求（用户名 + 密码）

    Returns:
        TokenResponse: 包含 access_token 和用户信息

    Raises:
        HTTPException 401: 用户名或密码错误
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, password_hash, is_admin, created_at FROM users WHERE username = ?",
            (data.username,),
        )
        row = await cursor.fetchone()

        if not row or not verify_password(data.password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        user_id = row["id"]
        username = row["username"]
        is_admin = bool(row["is_admin"])
        created_at = row["created_at"]

    # 生成 JWT 令牌
    access_token = create_access_token(user_id, username, is_admin=is_admin)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user_id,
            username=username,
            is_admin=is_admin,
            created_at=datetime.fromisoformat(created_at),
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息

    Args:
        current_user: 从 JWT 令牌中提取的当前用户信息（依赖注入）

    Returns:
        UserResponse: 当前用户信息
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, is_admin, created_at FROM users WHERE id = ?",
            (current_user["user_id"],),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在",
            )

        return UserResponse(
            id=row["id"],
            username=row["username"],
            is_admin=bool(row["is_admin"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


@router.post("/change-password", response_model=dict)
async def change_password(
    data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """修改当前用户密码

    Args:
        data: 包含旧密码和新密码的请求

    Returns:
        dict: {"message": "密码修改成功"}

    Raises:
        HTTPException 401: 旧密码错误
    """
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (current_user["user_id"],),
        )
        row = await cursor.fetchone()

        if not row or not verify_password(data.old_password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="旧密码错误",
            )

        new_hash = hash_password(data.new_password)
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, current_user["user_id"]),
        )
        await db.commit()

    return {"message": "密码修改成功"}