"""DeepAgents Skill 加载器

自动扫描 backend/skills 目录，并将技能文件转换为 StateBackend 可用的虚拟文件。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict


SKILLS_SOURCE = "/skills"
SKILL_FILE_NAME = "SKILL.md"


def _backend_root() -> Path:
    return Path(__file__).parent.parent.parent


def get_skills_path() -> Path:
    """获取 skills 目录绝对路径。"""
    return (_backend_root() / "skills").resolve()


def load_skill_files() -> Dict[str, dict]:
    """加载本地 skills 目录下的技能文件。

    目录不存在时返回空字典。当前最小可用版只加载每个技能目录中的 SKILL.md。
    """
    skills_path = get_skills_path()
    if not skills_path.exists() or not skills_path.is_dir():
        return {}

    files: Dict[str, dict] = {}
    for skill_dir in sorted(skills_path.iterdir(), key=lambda p: p.name):
        if not skill_dir.is_dir():
            continue

        skill_file = skill_dir / SKILL_FILE_NAME
        if not skill_file.is_file():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        virtual_path = f"{SKILLS_SOURCE}/{skill_dir.name}/{SKILL_FILE_NAME}"
        files[virtual_path] = {
            "content": content,
            "encoding": "utf-8",
        }

    return files


def get_skill_sources() -> list[str] | None:
    """返回 DeepAgents skills source 配置。"""
    return [SKILLS_SOURCE] if load_skill_files() else None
