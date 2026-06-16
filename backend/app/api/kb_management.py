"""
知识库管理 API — 管理员对知识库及文件的增删操作

所有端点需要管理员认证。
路径穿越防护复用 file_loader._safe_resolve_in_kb 模式。
"""
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from core.config import settings
from core.deps import get_current_admin_user
from core.file_loader import _safe_resolve_in_kb, PathSecurityError
from core.kb_router import list_knowledge_bases

router = APIRouter(prefix="/api/admin/knowledge-bases", tags=["admin-knowledge-bases"])

# ---------------------------------------------------------------------------
# 名称校验
# ---------------------------------------------------------------------------

_NAME_MAX_LEN = 100

def _validate_kb_name(name: str) -> str:
    """校验知识库名称合法性，返回 stripped 名称；不合法则抛 400"""
    name = name.strip()
    if not name or len(name) > _NAME_MAX_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"知识库名称长度为 1-{_NAME_MAX_LEN} 个字符",
        )
    if name.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="知识库名称不能以 . 开头",
        )
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="知识库名称不能包含路径分隔符",
        )
    return name


def _get_kb_file_info(root: Path, file_path: Path) -> dict:
    """获取单个文件的元信息"""
    stat = file_path.stat()
    rel = file_path.relative_to(root).as_posix()
    return {
        "name": file_path.name,
        "rel_path": rel,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "extension": file_path.suffix,
    }


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("")
async def get_knowledge_bases(
    admin: dict = Depends(get_current_admin_user),
):
    """获取所有知识库列表（含文件数、最后修改时间、总大小）"""
    root = settings.get_knowledge_path()
    names = list_knowledge_bases(root)

    result = []
    for name in names:
        kb_path = root / name
        file_count = 0
        total_size = 0
        last_modified = datetime.fromtimestamp(0.0)

        for dirpath, dirnames, filenames in os.walk(kb_path):
            # 跳过隐藏目录
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in filenames:
                if fname.startswith("."):
                    continue
                fp = Path(dirpath) / fname
                try:
                    st = fp.stat()
                except OSError:
                    continue
                file_count += 1
                total_size += st.st_size
                mtime = datetime.fromtimestamp(st.st_mtime)
                if mtime > last_modified:
                    last_modified = mtime

        result.append({
            "name": name,
            "file_count": file_count,
            "last_modified": last_modified.isoformat() if file_count > 0 else None,
            "total_size": total_size,
        })

    return {"knowledge_bases": result}


@router.get("/{kb_name}/files")
async def get_kb_files(
    kb_name: str,
    path: str = Query("", description="子目录路径，留空表示根目录"),
    admin: dict = Depends(get_current_admin_user),
):
    """获取指定知识库的文件列表（非递归，仅返回当前目录下的直接子项）"""
    root = settings.get_knowledge_path()
    kb_path = _safe_resolve_in_kb(root, root / kb_name)
    if not kb_path.exists() or not kb_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"知识库 '{kb_name}' 不存在",
        )

    # 解析当前浏览目录
    current_dir = kb_path
    sub_path = path.strip()
    if sub_path:
        sub_parts = [p for p in sub_path.replace("\\", "/").split("/") if p]
        if any(p.startswith(".") or p in ("..",) for p in sub_parts):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="子目录路径不合法",
            )
        current_dir = _safe_resolve_in_kb(kb_path, kb_path / "/".join(sub_parts))
        if not current_dir.is_dir():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"目录 '{sub_path}' 不存在",
            )

    items: list[dict] = []
    try:
        for entry in os.scandir(current_dir):
            if entry.name.startswith("."):
                continue
            stat = entry.stat()
            rel = Path(entry.path).relative_to(kb_path).as_posix()
            if entry.is_dir():
                items.append({
                    "name": entry.name,
                    "rel_path": rel,
                    "size": 0,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "extension": "",
                    "is_dir": True,
                })
            elif entry.is_file():
                items.append({
                    "name": entry.name,
                    "rel_path": rel,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "extension": Path(entry.name).suffix,
                    "is_dir": False,
                })
    except OSError:
        pass

    # 排序：目录在前，文件在后，各自按名称排序
    dirs = sorted([i for i in items if i["is_dir"]], key=lambda i: i["name"].lower())
    files = sorted([i for i in items if not i["is_dir"]], key=lambda i: i["name"].lower())

    return {
        "kb_name": kb_name,
        "current_path": sub_path if sub_path else "",
        "items": dirs + files,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: dict,
    admin: dict = Depends(get_current_admin_user),
):
    """创建空知识库目录"""
    name = _validate_kb_name(payload.get("name", ""))
    root = settings.get_knowledge_path()

    kb_path = _safe_resolve_in_kb(root, root / name)
    if kb_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"知识库 '{name}' 已存在",
        )

    kb_path.mkdir(parents=True)
    return {"name": name, "message": "知识库已创建"}


def _open_zip_with_encoding(zip_path: str) -> zipfile.ZipFile:
    """尝试多种编码打开 ZIP 文件，解决中文文件名乱码问题。

    Windows 创建的 ZIP 通常用 GBK 编码中文名，macOS/Linux 用 UTF-8。
    优先 GBK，解码失败或出现乱码则回退 UTF-8。
    """
    # 先尝试 GBK（Windows 中文系统默认）
    try:
        zf = zipfile.ZipFile(zip_path, "r", metadata_encoding="gbk")
    except UnicodeDecodeError:
        # GBK 无法解码（如包含 0x80 等非法字节），回退 UTF-8
        return zipfile.ZipFile(zip_path, "r", metadata_encoding="utf-8")

    # 简单探测：如果文件名中有典型的 CP437 乱码字符（如 ©、® 等），回退 UTF-8
    for name in zf.namelist():
        if any(ord(c) > 127 and c in "®©«¬" for c in name):
            zf.close()
            return zipfile.ZipFile(zip_path, "r", metadata_encoding="utf-8")
    return zf


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_kb_zip(
    file: UploadFile = File(...),
    name: str = Form(""),
    admin: dict = Depends(get_current_admin_user),
):
    """上传 ZIP 压缩包解压创建知识库"""
    # 确定知识库名称
    if name and name.strip():
        kb_name = _validate_kb_name(name)
    else:
        # 使用文件名（去掉 .zip 后缀）
        raw = file.filename or "unknown"
        kb_name = _validate_kb_name(raw.removesuffix(".zip"))

    root = settings.get_knowledge_path()
    kb_path = _safe_resolve_in_kb(root, root / kb_name)
    if kb_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"知识库 '{kb_name}' 已存在",
        )

    # 先存到临时文件
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        try:
            content = await file.read()
            tmp.write(content)
            tmp.flush()
            tmp_path = tmp.name
        except Exception:
            os.unlink(tmp.name)
            raise

    file_count = 0
    try:
        kb_path.mkdir(parents=True)
        with _open_zip_with_encoding(tmp_path) as zf:
            for entry in zf.infolist():
                # 跳过目录
                if entry.is_dir():
                    continue
                entry_name = entry.filename.replace("\\", "/")
                parts = entry_name.split("/")

                # 跳过隐藏文件和隐藏目录下的文件
                if any(p.startswith(".") for p in parts):
                    continue

                # 跳过空文件名
                if not parts[-1]:
                    continue

                # 路径穿越校验
                target = kb_path / entry_name
                try:
                    target = _safe_resolve_in_kb(kb_path, target)
                except PathSecurityError:
                    continue  # 跳过不安全条目

                # 确保父目录存在
                target.parent.mkdir(parents=True, exist_ok=True)

                # 解压文件
                with zf.open(entry) as src, open(target, "wb") as dst:
                    dst.write(src.read())

                file_count += 1
    finally:
        os.unlink(tmp_path)

    return {
        "name": kb_name,
        "file_count": file_count,
        "message": "知识库已从压缩包创建",
    }


@router.delete("/{kb_name}")
async def delete_knowledge_base(
    kb_name: str,
    admin: dict = Depends(get_current_admin_user),
):
    """删除整个知识库目录"""
    root = settings.get_knowledge_path()
    kb_path = _safe_resolve_in_kb(root, root / kb_name)

    if not kb_path.exists() or not kb_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"知识库 '{kb_name}' 不存在",
        )

    shutil.rmtree(kb_path)
    return {"message": f"知识库 '{kb_name}' 已删除"}


@router.post("/{kb_name}/files", status_code=status.HTTP_201_CREATED)
async def upload_kb_file(
    kb_name: str,
    file: UploadFile = File(...),
    path: str = Form(""),
    admin: dict = Depends(get_current_admin_user),
):
    """上传单个文件到指定知识库（存在则覆盖）"""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未选择文件",
        )

    # 文件名安全校验
    fname = Path(file.filename).name  # 只取文件名，丢弃客户端路径
    if not fname or fname.startswith(".") or "/" in fname or "\\" in fname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件名不合法: '{fname}'",
        )

    root = settings.get_knowledge_path()
    kb_path = _safe_resolve_in_kb(root, root / kb_name)
    if not kb_path.exists() or not kb_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"知识库 '{kb_name}' 不存在",
        )

    # 子目录路径校验
    sub_path = path.strip() if path else ""
    if sub_path:
        # 清理子路径并校验
        sub_parts = [p for p in sub_path.replace("\\", "/").split("/") if p]
        if any(p.startswith(".") or p in ("..",) for p in sub_parts):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="子目录路径不合法",
            )
        target_dir = _safe_resolve_in_kb(kb_path, kb_path / "/".join(sub_parts))
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = kb_path

    target = _safe_resolve_in_kb(kb_path, target_dir / fname)

    # 写入文件（覆盖模式）
    content = await file.read()
    target.write_bytes(content)

    rel_path = target.relative_to(kb_path).as_posix()
    return {
        "file_name": fname,
        "rel_path": rel_path,
        "message": "文件已上传",
    }


@router.delete("/{kb_name}/files", status_code=status.HTTP_200_OK)
async def delete_kb_file(
    kb_name: str,
    payload: dict,
    admin: dict = Depends(get_current_admin_user),
):
    """删除知识库中的指定文件或目录"""
    file_path = payload.get("file_path", "")
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file_path 不能为空",
        )

    root = settings.get_knowledge_path()
    kb_path = _safe_resolve_in_kb(root, root / kb_name)
    if not kb_path.exists() or not kb_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"知识库 '{kb_name}' 不存在",
        )

    target = _safe_resolve_in_kb(kb_path, kb_path / file_path)
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{file_path}' 不存在",
        )

    if target.is_dir():
        shutil.rmtree(target)
        return {"message": f"目录 '{file_path}' 已删除"}
    else:
        os.remove(target)
        return {"message": f"文件 '{file_path}' 已删除"}


# ---------------------------------------------------------------------------
# 下载端点
# ---------------------------------------------------------------------------

@router.get("/{kb_name}/files/download")
async def download_kb_file(
    kb_name: str,
    file_path: str = Query(..., description="文件相对路径"),
    admin: dict = Depends(get_current_admin_user),
):
    """下载知识库中的单个文件"""
    root = settings.get_knowledge_path()
    kb_path = _safe_resolve_in_kb(root, root / kb_name)
    if not kb_path.exists() or not kb_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"知识库 '{kb_name}' 不存在",
        )

    target = _safe_resolve_in_kb(kb_path, kb_path / file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文件 '{file_path}' 不存在",
        )

    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type="application/octet-stream",
    )


@router.get("/{kb_name}/download")
async def download_knowledge_base(
    kb_name: str,
    admin: dict = Depends(get_current_admin_user),
):
    """下载整个知识库为 ZIP 压缩包"""
    root = settings.get_knowledge_path()
    kb_path = _safe_resolve_in_kb(root, root / kb_name)
    if not kb_path.exists() or not kb_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"知识库 '{kb_name}' 不存在",
        )

    # 创建临时 ZIP 文件
    tmp_dir = tempfile.mkdtemp()
    zip_base = os.path.join(tmp_dir, kb_name)
    try:
        zip_path = shutil.make_archive(
            base_name=zip_base,
            format="zip",
            root_dir=str(kb_path.parent),
            base_dir=kb_name,
        )
        return FileResponse(
            path=zip_path,
            filename=f"{kb_name}.zip",
            media_type="application/zip",
            background=lambda: shutil.rmtree(tmp_dir, ignore_errors=True),
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
