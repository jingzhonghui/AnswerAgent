"""
FastAPI 依赖注入——从请求中提取当前认证用户

提供 get_current_user 依赖（用于保护需要认证的路由）
和 get_current_admin_user 依赖（用于保护需要管理员权限的路由）。
"""
from fastapi import Depends, HTTPException, Request, status

from core.security import decode_access_token


async def get_current_user(request: Request) -> dict:
    """从 Authorization 头中提取并验证 JWT 令牌，返回当前用户信息

    用法:
        @router.get("/protected")
        async def protected_route(current_user: dict = Depends(get_current_user)):
            user_id = current_user["user_id"]
            username = current_user["username"]

    Args:
        request: FastAPI Request 对象

    Returns:
        dict: {"user_id": str, "username": str, "is_admin": bool}

    Raises:
        HTTPException 401: 未提供令牌或令牌无效/过期
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
        )

    # 解析 Bearer token
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证头格式",
        )

    token = parts[1]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
        )

    return {
        "user_id": payload.get("sub", ""),
        "username": payload.get("username", ""),
        "is_admin": payload.get("is_admin", False),
    }


async def get_current_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """要求当前用户为管理员，否则返回 403

    用法:
        @router.get("/admin/xxx")
        async def admin_route(admin: dict = Depends(get_current_admin_user)):
            ...

    Args:
        current_user: 从 get_current_user 注入的用户信息

    Returns:
        dict: 管理员用户信息

    Raises:
        HTTPException 403: 当前用户不是管理员
    """
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user