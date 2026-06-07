"""知识库接口路由

提供:
- GET /api/knowledge-bases  扫描 KNOWLEDGE_PATH 一级目录，返回知识库名称列表
"""
from typing import List

from fastapi import APIRouter

from core.kb_router import list_knowledge_bases

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


@router.get("", response_model=List[str])
async def get_knowledge_bases() -> List[str]:
    """获取所有知识库名称列表（按字母序排列）

    Returns:
        List[str]: 知识库名称列表；KNOWLEDGE_PATH 不存在或为空时返回 []
    """
    return list_knowledge_bases()
