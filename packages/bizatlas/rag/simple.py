from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from typing import Any

from bizatlas.data.db import get_connection
from bizatlas.ingest.fixtures import fixtures_root


def _tokenize(text: str) -> list[str]:
    # 中英混合粗分词
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", text.lower())
    return parts


def index_text(document_id: str, text: str, *, page: int | None = None, chunk_size: int = 180) -> int:
    chunks = []
    text = text.strip()
    if not text:
        return 0
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i : i + chunk_size])
    conn = get_connection()
    try:
        conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        for idx, chunk in enumerate(chunks):
            conn.execute(
                "INSERT INTO document_chunks (id, document_id, chunk_index, content, page) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"chk-{uuid.uuid4().hex[:10]}", document_id, idx, chunk, page),
            )
        conn.commit()
    finally:
        conn.close()
    return len(chunks)


def _load_chunks(document_ids: list[str] | None = None) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            rows = conn.execute(
                f"SELECT id, document_id, chunk_index, content, page FROM document_chunks "
                f"WHERE document_id IN ({placeholders})",
                document_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, document_id, chunk_index, content, page FROM document_chunks"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _tfidf_rank(query: str, chunks: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    q_tokens = _tokenize(query)
    if not q_tokens or not chunks:
        return []
    docs_tokens = [_tokenize(c.get("content") or "") for c in chunks]
    df: Counter[str] = Counter()
    for toks in docs_tokens:
        df.update(set(toks))
    n = len(docs_tokens)
    q_tf = Counter(q_tokens)

    scored = []
    for chunk, toks in zip(chunks, docs_tokens):
        if not toks:
            continue
        tf = Counter(toks)
        score = 0.0
        for t, qf in q_tf.items():
            if t not in tf:
                continue
            idf = math.log((1 + n) / (1 + df[t])) + 1
            score += (tf[t] / len(toks)) * idf * qf
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {**c, "score": round(s, 4)}
        for s, c in scored[:top_k]
    ]


def ensure_fixture_index(fixture_id: str) -> str:
    """Index fixture excerpt/company json text under a synthetic document id."""
    doc_id = f"fixture-doc-{fixture_id}"
    parts = []
    company_json = fixtures_root() / fixture_id / "company.json"
    if company_json.exists():
        parts.append(company_json.read_text(encoding="utf-8"))
    from bizatlas.config import get_settings

    sample = get_settings().root / "content" / "templates" / "sample_financial_excerpt.txt"
    if fixture_id == "risky" and sample.exists():
        parts.append(sample.read_text(encoding="utf-8"))
    index_text(doc_id, "\n".join(parts))
    return doc_id


def ask_company(
    question: str,
    *,
    company_id: str | None = None,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    doc_ids = None
    if fixture_id:
        doc_id = ensure_fixture_index(fixture_id)
        doc_ids = [doc_id]
    chunks = _load_chunks(doc_ids)
    # also if company uploads exist, include all chunks when no fixture
    if not chunks and company_id:
        chunks = _load_chunks(None)

    hits = _tfidf_rank(question, chunks, top_k=3)
    if not hits:
        return {
            "answer": "未在本地资料中检索到相关片段。请先上传资料或选择含文本的案例。",
            "citations": [],
            "confidence": 0.0,
            "llm_used": False,
        }

    citations = [
        {
            "chunk_id": h.get("id"),
            "document_id": h.get("document_id"),
            "page": h.get("page"),
            "score": h.get("score"),
            "snippet": (h.get("content") or "")[:160],
        }
        for h in hits
    ]
    context = "\n---\n".join((h.get("content") or "")[:480] for h in hits)

    # LLM 只润色/归纳检索片段；无 key 或失败时回退抽取式拼接（ADR-001）
    answer = None
    llm_used = False
    try:
        from bizatlas.llm.client import chat_completion, llm_configured

        if llm_configured():
            answer = chat_completion(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是 BizAtlas 企业风险研判助手。只根据用户提供的【资料片段】作答；"
                            "禁止编造任何财务数字、比例、日期或结论。"
                            "片段中没有的信息请明确说「资料未提及」。用简洁中文回答。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"【资料片段】\n{context}\n\n【问题】\n{question}",
                    },
                ],
                temperature=0.2,
                max_tokens=700,
            )
            llm_used = True
    except Exception:  # noqa: BLE001 — including LLMUnavailable
        answer = None
        llm_used = False

    if not answer:
        answer = "根据本地资料（摘录）：\n" + "\n---\n".join(
            (h.get("content") or "")[:240] for h in hits
        )

    return {
        "answer": answer,
        "citations": citations,
        "confidence": hits[0]["score"],
        "llm_used": llm_used,
    }


def _split_sentences(text: str) -> list[str]:
    """抽取式回退时按句切分，便于逐段流式输出。"""
    import re

    parts = re.split(r"(?<=[。！？\n])", text)
    return [p for p in parts if p.strip()]


def stream_ask_company(
    question: str,
    *,
    company_id: str | None = None,
    fixture_id: str | None = None,
    provider: dict[str, Any] | None = None,
) -> Any:
    """流式版 ask_company：返回生成器，依次 yield 事件 dict：
      {"type":"meta","citations":[...],"confidence":float,"llm_used":bool}
      {"type":"token","text":str}            # 逐段文本
      {"type":"done"}
    仅 ask_doc 意图使用；命中缓存时 chat_completion(stream=True) 重放缓存，仍按 chunk 输出。
    """
    doc_ids = None
    if fixture_id:
        doc_id = ensure_fixture_index(fixture_id)
        doc_ids = [doc_id]
    chunks = _load_chunks(doc_ids)
    if not chunks and company_id:
        chunks = _load_chunks(None)

    hits = _tfidf_rank(question, chunks, top_k=3)
    if not hits:
        yield {
            "type": "meta",
            "citations": [],
            "confidence": 0.0,
            "llm_used": False,
        }
        yield {
            "type": "token",
            "text": "未在本地资料中检索到相关片段。请先上传资料或选择含文本的案例。",
        }
        yield {"type": "done"}
        return

    citations = [
        {
            "chunk_id": h.get("id"),
            "document_id": h.get("document_id"),
            "page": h.get("page"),
            "score": h.get("score"),
            "snippet": (h.get("content") or "")[:160],
        }
        for h in hits
    ]
    context = "\n---\n".join((h.get("content") or "")[:480] for h in hits)

    yield {
        "type": "meta",
        "citations": citations,
        "confidence": hits[0]["score"],
        "llm_used": True,
    }

    try:
        from bizatlas.llm.client import chat_completion, llm_configured

        if llm_configured():
            for tok in chat_completion(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是 BizAtlas 企业风险研判助手。只根据用户提供的【资料片段】作答；"
                            "禁止编造任何财务数字、比例、日期或结论。"
                            "片段中没有的信息请明确说「资料未提及」。用简洁中文回答。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"【资料片段】\n{context}\n\n【问题】\n{question}",
                    },
                ],
                temperature=0.2,
                max_tokens=700,
                stream=True,
                provider=provider,
            ):
                yield {"type": "token", "text": tok}
        else:
            raise LLMUnavailable("LLM not configured")
    except Exception:  # noqa: BLE001 — 回退抽取式拼接
        extract = "根据本地资料（摘录）：\n" + "\n---\n".join(
            (h.get("content") or "")[:240] for h in hits
        )
        for piece in _split_sentences(extract):
            yield {"type": "token", "text": piece}

    yield {"type": "done"}
