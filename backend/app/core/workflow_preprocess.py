"""工作流预处理模块

负责输入验证、Git 克隆、压缩包解压、临时目录管理。
所有操作限制在工作目录内，防止路径遍历攻击。
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 最大解压文件大小 200MB
MAX_FILE_SIZE = 200 * 1024 * 1024
# 最大解压文件总数
MAX_FILE_COUNT = 10000


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def get_workflow_data_dir() -> Path:
    path = _backend_root() / "data" / "workflow"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_input(input_type: str, input_value: str) -> None:
    """验证输入有效性，无效时抛出 ValueError"""
    if input_type == "local_path":
        path = Path(input_value).resolve()
        if not path.exists():
            raise ValueError(f"路径不存在: {input_value}")
        if not path.is_dir():
            raise ValueError(f"路径不是目录: {input_value}")
    elif input_type == "git_url":
        if not input_value.startswith(("http://", "https://", "git@", "ssh://")):
            raise ValueError(f"无效的 Git 地址: {input_value}")
    elif input_type == "archive":
        path = Path(input_value)
        if not path.exists():
            raise ValueError(f"压缩包不存在: {input_value}")
        if not path.is_file():
            raise ValueError(f"压缩包路径不是文件: {input_value}")
    else:
        raise ValueError(f"不支持的输入类型: {input_type}")


def prepare_work_dir(task_id: str) -> Path:
    """创建工作目录并返回路径"""
    work_dir = get_workflow_data_dir() / task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def detect_archive_format(file_path: Path) -> str:
    """检测压缩包格式，返回 'zip' 或 'tar'"""
    with open(file_path, "rb") as f:
        header = f.read(4)
    if header[:2] == b"PK":
        return "zip"
    if header[:2] == b"\x1f\x8b":
        return "tar"
    if len(header) >= 4 and header[0:1] == b"\x1f" and header[1:2] == b"\x8b":
        return "tar"
    raise ValueError(f"无法识别的压缩包格式: {file_path.name}")


def _is_safe_path(member_path: str, target_dir: Path) -> bool:
    """检查解压成员路径是否安全（防止路径遍历）"""
    resolved = (target_dir / member_path).resolve()
    return str(resolved).startswith(str(target_dir.resolve()))


def extract_archive(file_path: Path, dest_dir: Path) -> Path:
    """解压压缩包到目标目录，返回源文件根目录"""
    fmt = detect_archive_format(file_path)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "zip":
        with zipfile.ZipFile(file_path, "r") as zf:
            file_count = len(zf.infolist())
            if file_count > MAX_FILE_COUNT:
                raise ValueError(f"压缩包文件数 {file_count} 超过上限 {MAX_FILE_COUNT}")

            for member in zf.infolist():
                if member.file_size > MAX_FILE_SIZE:
                    raise ValueError(f"文件 {member.filename} 大小超过上限")
                if not _is_safe_path(member.filename, dest_dir):
                    raise ValueError(f"不安全的路径: {member.filename}")
                # 跳过目录
                if member.is_dir():
                    continue
                zf.extract(member, dest_dir)
    else:
        with tarfile.open(file_path, "r:*") as tf:
            members = tf.getmembers()
            if len(members) > MAX_FILE_COUNT:
                raise ValueError(f"压缩包文件数 {len(members)} 超过上限 {MAX_FILE_COUNT}")

            for member in members:
                if member.size > MAX_FILE_SIZE:
                    raise ValueError(f"文件 {member.name} 大小超过上限")
                if not _is_safe_path(member.name, dest_dir):
                    raise ValueError(f"不安全的路径: {member.name}")
                if member.isdir():
                    continue
                tf.extract(member, dest_dir, set_attrs=False)

    # 如果解压后只有一个顶层目录，返回该目录
    items = list(dest_dir.iterdir())
    if len(items) == 1 and items[0].is_dir():
        return items[0]
    return dest_dir


def clone_git(url: str, dest_dir: Path) -> Path:
    """克隆 Git 仓库到目标目录，返回源码根目录"""
    dest_dir.mkdir(parents=True, exist_ok=True)

    source_dir = dest_dir / "source"
    if source_dir.exists():
        shutil.rmtree(source_dir)

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(source_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Git 克隆超时: {url}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git 克隆失败: {e.stderr.strip()}")

    return source_dir


def resolve_local_path(path_str: str) -> Path:
    """解析本地路径，返回绝对路径"""
    path = Path(path_str).resolve()
    if not path.exists():
        raise ValueError(f"路径不存在: {path_str}")
    if not path.is_dir():
        raise ValueError(f"路径不是目录: {path_str}")
    return path


def preprocess(task_id: str, input_type: str, input_value: str) -> Path:
    """执行预处理，返回源码根目录路径

    Returns:
        Path: 源码根目录（供后续分析阶段使用）
    """
    validate_input(input_type, input_value)
    work_dir = prepare_work_dir(task_id)

    if input_type == "local_path":
        source_dir = resolve_local_path(input_value)
        logger.info(f"本地路径已验证: {source_dir}")
    elif input_type == "git_url":
        source_dir = clone_git(input_value, work_dir)
        logger.info(f"Git 仓库已克隆: {source_dir}")
    elif input_type == "archive":
        archive_path = Path(input_value)
        source_dir = extract_archive(archive_path, work_dir / "source")
        logger.info(f"压缩包已解压: {source_dir}")
    else:
        raise ValueError(f"不支持的输入类型: {input_type}")

    return source_dir


def cleanup_work_dir(task_id: str) -> None:
    """清理工作目录"""
    work_dir = get_workflow_data_dir() / task_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
        logger.info(f"工作目录已清理: {work_dir}")


# 拷贝源码时忽略的目录和扩展名（与 analyzer 保持一致）
_COPY_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", "dist", "build", ".next", ".nuxt",
    "target", "vendor", ".cache", ".tox", ".eggs",
}
_COPY_IGNORE_EXTS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
    ".jpg", ".jpeg", ".png", ".gif", ".ico", ".svg",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".ttf", ".woff", ".woff2", ".eot",
    ".lock", ".log",
}
_COPY_MAX_FILE_SIZE = 10 * 1024 * 1024  # 单个文件最大 10MB


def copy_source_to_knowledge(source_dir: Path, knowledge_name: str) -> int:
    """将源码目录拷贝到知识库的 src/ 子目录下

    Returns:
        int: 拷贝的文件数
    """
    backend_root = Path(__file__).parent.parent.parent
    dest_dir = backend_root / "knowledge" / knowledge_name / "src"
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for entry in source_dir.rglob("*"):
        if not entry.is_file():
            continue

        # 检查忽略目录
        parts = set(entry.relative_to(source_dir).parts)
        if parts & _COPY_IGNORE_DIRS:
            continue

        # 检查忽略扩展名
        if entry.suffix.lower() in _COPY_IGNORE_EXTS:
            continue

        # 检查文件大小
        if entry.stat().st_size > _COPY_MAX_FILE_SIZE:
            continue

        rel_path = entry.relative_to(source_dir)
        target = dest_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)
        count += 1

    logger.info(f"源码已拷贝到 {dest_dir}，共 {count} 个文件")
    return count