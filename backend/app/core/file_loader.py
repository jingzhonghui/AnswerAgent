"""文件选取模块（两阶段：本地粗筛 + LLM 精读）

针对单个匹配到的知识库:
1. 扫描知识库内所有支持类型的文件，建立 (文件路径, 元数据) 候选池。
2. 对用户问题做中英文分词，按文件名/标题/索引.md/路径关键词命中数评分，
   取 Top _ROUGH_LIMIT 作为候选。
3. 将候选文件的"简要目录"喂给 LLM，让 LLM 选出 ≤ _FINE_LIMIT 个最相关文件。
4. 读取选中文件完整内容（带单文件字符上限），按知识库内相对路径返回。

安全:
- 所有路径 resolve 后必须落在知识库根目录内，否则抛 PathSecurityError。
- 仅读取白名单后缀文件，避免误读二进制。
- 单文件、单知识库总字符均有上限，防止上下文爆炸。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

import jieba
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings
from core.llm_factory import create_chat_llm


# 文件类型白名单（小写）
_TEXT_EXTENSIONS: Set[str] = {
    ".md", ".markdown", ".txt",
    ".py", ".ts", ".tsx", ".js", ".jsx", ".vue",
    ".java", ".go", ".rs", ".cpp", ".c", ".h", ".hpp",
    ".rb", ".php", ".cs", ".kt", ".swift", ".scala",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".css", ".scss", ".sql",
}

# 数量与大小上限
_ROUGH_LIMIT = 10            # 粗筛候选最多 10
_FINE_LIMIT = 5              # LLM 精读最多选 5
_SINGLE_FILE_CHAR_LIMIT = 20_000      # 单文件读入上限
_PER_KB_TOTAL_CHAR_LIMIT = 60_000     # 单知识库总字符上限
_FILE_SCAN_LIMIT = 500       # 单知识库最多扫描 500 个候选文件

# 路由 + 路径 + 标题预览的字符上限
_TITLE_PREVIEW_LIMIT = 300
_INDEX_PREVIEW_LIMIT = 2000

# 英文 token 的最小长度（避免一个字母被当 keyword）
_MIN_EN_TOKEN_LEN = 2

# 极常见的中英文停用词（最小集，覆盖问题中常见嘈杂词）
_STOPWORDS: Set[str] = {
    "的", "了", "和", "与", "或", "是", "在", "我", "你", "他", "她", "它",
    "有", "没有", "怎么", "如何", "什么", "为什么", "请问", "请", "可以", "需要",
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on",
    "and", "or", "for", "with", "how", "what", "why", "do", "does", "did",
    "can", "could", "should", "would", "i", "you", "he", "she", "it", "we",
    "they", "this", "that", "these", "those", "be", "been", "being",
}


class PathSecurityError(Exception):
    """路径安全异常（路径穿透）"""
    pass


@dataclass
class FileCandidate:
    """粗筛阶段的文件候选

    Attributes:
        rel_path: 知识库内相对路径（使用 POSIX 分隔符 "/"）
        abs_path: 绝对路径
        title: 文档标题（md 第一行 # 标题；其他文件取文件名）
        score: 关键词命中评分
    """
    rel_path: str
    abs_path: Path
    title: str
    score: int = 0


@dataclass
class LoadedFile:
    """精读阶段读取后的文件内容

    Attributes:
        kb_name: 所属知识库
        rel_path: 知识库内相对路径（POSIX）
        content: 文件内容（可能被截断）
        truncated: 是否被截断
    """
    kb_name: str
    rel_path: str
    content: str
    truncated: bool = False


def _safe_resolve_in_kb(kb_root: Path, target: Path) -> Path:
    """resolve target 并校验其落在 kb_root 内，否则抛 PathSecurityError"""
    resolved = target.resolve()
    try:
        resolved.relative_to(kb_root)
    except ValueError as e:
        raise PathSecurityError(
            f"Path escapes knowledge base: {target} -> {resolved}"
        ) from e
    return resolved


def _tokenize(text: str) -> Set[str]:
    """中英文混合分词

    - 英文/数字: 按 \\w+ 抽取，转小写
    - 中文: 用 jieba.cut_for_search 切分
    - 过滤长度与停用词
    """
    text = text or ""
    tokens: Set[str] = set()

    # 英文/数字
    for m in re.findall(r"[A-Za-z][A-Za-z0-9_]+|[0-9]+", text):
        token = m.lower()
        if len(token) < _MIN_EN_TOKEN_LEN or token in _STOPWORDS:
            continue
        tokens.add(token)

    # 中文（含其他 unicode 词）
    for tok in jieba.cut_for_search(text):
        tok = tok.strip()
        if not tok or tok in _STOPWORDS:
            continue
        # 跳过纯标点
        if not re.search(r"[一-鿿A-Za-z0-9]", tok):
            continue
        # 已经被英文分支抓过的纯英文 token 不重复加
        if re.fullmatch(r"[A-Za-z0-9_]+", tok):
            continue
        tokens.add(tok)

    return tokens


def _extract_title(file_path: Path) -> str:
    """提取文档标题

    - .md: 读取第一个非空 # 开头行；没有则用文件名
    - 其他: 文件名
    """
    if file_path.suffix.lower() in {".md", ".markdown"}:
        try:
            with file_path.open("r", encoding="utf-8") as f:
                for _ in range(20):  # 只看前 20 行
                    line = f.readline()
                    if not line:
                        break
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        return stripped.lstrip("#").strip()[:_TITLE_PREVIEW_LIMIT]
        except (OSError, UnicodeDecodeError):
            pass
    return file_path.stem


def _read_index_md(kb_root: Path) -> str:
    """读取知识库 索引.md 内容（截断）"""
    for name in ("索引.md", "index.md"):
        p = kb_root / name
        if p.exists() and p.is_file():
            try:
                text = p.read_text(encoding="utf-8")
                if len(text) > _INDEX_PREVIEW_LIMIT:
                    text = text[:_INDEX_PREVIEW_LIMIT] + "\n...(truncated)"
                return text
            except (OSError, UnicodeDecodeError):
                return ""
    return ""


def _iter_kb_files(kb_root: Path) -> Iterable[Path]:
    """递归扫描知识库内白名单后缀文件

    跳过隐藏目录、超大文件、超过 _FILE_SCAN_LIMIT 的部分。
    """
    count = 0
    for path in kb_root.rglob("*"):
        if count >= _FILE_SCAN_LIMIT:
            break
        if not path.is_file():
            continue
        # 跳过隐藏目录
        if any(part.startswith(".") for part in path.relative_to(kb_root).parts):
            continue
        if path.suffix.lower() not in _TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > _SINGLE_FILE_CHAR_LIMIT * 4:  # 粗略防大文件
                continue
        except OSError:
            continue
        count += 1
        yield path


def _build_candidates(kb_root: Path) -> List[FileCandidate]:
    """构建知识库内的全部候选文件元数据"""
    candidates: List[FileCandidate] = []
    for abs_path in _iter_kb_files(kb_root):
        try:
            rel = abs_path.resolve().relative_to(kb_root).as_posix()
        except ValueError:
            continue
        # 不把 索引.md 自身作为候选（它会单独作为路由提示）
        if rel in ("索引.md", "index.md"):
            continue
        candidates.append(FileCandidate(
            rel_path=rel,
            abs_path=abs_path,
            title=_extract_title(abs_path),
        ))
    return candidates


def _score_candidates(
    candidates: List[FileCandidate],
    question_tokens: Set[str],
    index_text: str,
) -> List[FileCandidate]:
    """根据 question_tokens 对候选打分，返回 Top _ROUGH_LIMIT

    评分策略（命中即加分，加权）:
      - 文件名 token 命中: +3
      - 标题 token 命中: +2
      - 路径 token 命中: +1
      - 索引.md 中提及该文件且 token 命中: +2
    """
    # 解析索引中提及的文件名 -> 索引段落 token
    index_tokens_by_file: Dict[str, Set[str]] = {}
    if index_text:
        # 简单按行扫，记下"行内含某 rel_path 或 文件名"时的整行 token
        for line in index_text.splitlines():
            line_tokens = _tokenize(line)
            for cand in candidates:
                if cand.rel_path in line or Path(cand.rel_path).name in line:
                    if cand.rel_path not in index_tokens_by_file:
                        index_tokens_by_file[cand.rel_path] = set()
                    index_tokens_by_file[cand.rel_path].update(line_tokens)

    for cand in candidates:
        score = 0
        name_tokens = _tokenize(Path(cand.rel_path).name)
        title_tokens = _tokenize(cand.title)
        path_tokens = _tokenize(cand.rel_path.replace("/", " "))
        idx_tokens = index_tokens_by_file.get(cand.rel_path, set())

        for q in question_tokens:
            if q in name_tokens:
                score += 3
            if q in title_tokens:
                score += 2
            if q in path_tokens:
                score += 1
            if q in idx_tokens:
                score += 2
        cand.score = score

    # 仅保留 score > 0 的；按 score 降序、rel_path 升序保证稳定
    scored = [c for c in candidates if c.score > 0]
    scored.sort(key=lambda c: (-c.score, c.rel_path))
    return scored[:_ROUGH_LIMIT]


_FILE_SELECT_SYSTEM_PROMPT = (
    "你是一个文档检索助手。\n"
    "用户会给出一个问题，以及若干候选文件（文件路径 + 标题）。\n"
    "你的任务是从候选文件中选出与问题最相关的文件路径，最多 5 个。\n"
    "\n"
    "规则:\n"
    "1. 只从候选列表中选择，禁止虚构。\n"
    "2. 如果没有任何候选文件相关，返回空数组。\n"
    "3. 严格只返回 JSON，禁止任何额外说明文字。\n"
    "\n"
    '输出格式: {"files": ["相对路径1", "相对路径2"]}'
)


def _parse_file_selection_json(raw: str, candidates: List[FileCandidate]) -> List[str]:
    """解析 LLM 选文件结果，与候选交集去重"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = None

    if not isinstance(data, dict):
        return []

    files = data.get("files", [])
    if not isinstance(files, list):
        return []

    candidate_set = {c.rel_path for c in candidates}
    seen = set()
    out: List[str] = []
    for p in files:
        if not isinstance(p, str):
            continue
        p_norm = p.replace("\\", "/").strip().lstrip("./")
        if p_norm in candidate_set and p_norm not in seen:
            seen.add(p_norm)
            out.append(p_norm)
        if len(out) >= _FINE_LIMIT:
            break
    return out


def _llm_select_files(
    question: str,
    candidates: List[FileCandidate],
) -> List[str]:
    """让 LLM 从粗筛候选中精选文件路径"""
    catalog_lines = []
    for c in candidates:
        title = c.title.replace("\n", " ").strip()
        catalog_lines.append(f"- 路径: {c.rel_path}\n  标题: {title}")
    catalog = "\n".join(catalog_lines)

    user_prompt = (
        f"候选文件:\n{catalog}\n\n"
        f"用户问题: {question}\n\n"
        '请返回 JSON: {"files": [...]}'
    )

    llm = create_chat_llm(streaming=False, temperature=0.0)
    response = llm.invoke([
        SystemMessage(content=_FILE_SELECT_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ])
    raw = response.content if hasattr(response, "content") else str(response)
    if isinstance(raw, list):
        raw = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )
    return _parse_file_selection_json(raw, candidates)


def _read_file_safely(kb_root: Path, rel_path: str) -> Optional[str]:
    """安全读取知识库内文件，处理路径穿透与编码

    Returns:
        Optional[str]: 文件内容（可能被截断到 _SINGLE_FILE_CHAR_LIMIT），失败返回 None
    """
    try:
        abs_path = _safe_resolve_in_kb(kb_root, kb_root / rel_path)
    except PathSecurityError:
        return None
    if not abs_path.exists() or not abs_path.is_file():
        return None
    try:
        text = abs_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) > _SINGLE_FILE_CHAR_LIMIT:
        return text[:_SINGLE_FILE_CHAR_LIMIT]
    return text


def select_and_load_files(
    question: str,
    kb_name: str,
    knowledge_root: Optional[Path] = None,
) -> List[LoadedFile]:
    """对单个知识库执行两阶段文件选取并加载内容

    Args:
        question: 用户问题
        kb_name: 知识库名（一级目录名）
        knowledge_root: 可选覆盖根目录

    Returns:
        List[LoadedFile]: 选中并读取成功的文件列表，最多 _FINE_LIMIT 个，
                          总字符数受 _PER_KB_TOTAL_CHAR_LIMIT 限制。
                          无候选或全部读取失败时返回 []。

    Raises:
        PathSecurityError: kb_name 解析后逃出知识库根目录
        LLMConfigError / KBRouterError 透传
    """
    root = (knowledge_root or settings.get_knowledge_path()).resolve()
    kb_root = _safe_resolve_in_kb(root, root / kb_name)
    if not kb_root.is_dir():
        return []

    # Step 1: 候选池
    candidates = _build_candidates(kb_root)
    if not candidates:
        return []

    # Step 2: 关键词粗筛
    question_tokens = _tokenize(question)
    index_text = _read_index_md(kb_root)
    # 即使 question_tokens 为空，也用索引/文件名做兜底（取按文件名字母序的前 N）
    if not question_tokens:
        rough = sorted(candidates, key=lambda c: c.rel_path)[:_ROUGH_LIMIT]
    else:
        rough = _score_candidates(candidates, question_tokens, index_text)
        # 粗筛 0 命中时仍给 LLM 一些默认候选，避免直接放弃
        if not rough:
            rough = sorted(candidates, key=lambda c: c.rel_path)[:_ROUGH_LIMIT]

    # Step 3: LLM 精选
    selected_paths = _llm_select_files(question, rough)
    if not selected_paths:
        return []

    # Step 4: 读取内容（受单文件 / 单知识库总量限制）
    loaded: List[LoadedFile] = []
    used_chars = 0
    for rel in selected_paths:
        content = _read_file_safely(kb_root, rel)
        if content is None:
            continue
        truncated = len(content) >= _SINGLE_FILE_CHAR_LIMIT
        # 单知识库总量预算
        remaining = _PER_KB_TOTAL_CHAR_LIMIT - used_chars
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining]
            truncated = True
        loaded.append(LoadedFile(
            kb_name=kb_name,
            rel_path=rel,
            content=content,
            truncated=truncated,
        ))
        used_chars += len(content)

    return loaded
