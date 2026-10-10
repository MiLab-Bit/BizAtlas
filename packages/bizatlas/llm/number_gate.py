from __future__ import annotations

import re
from typing import Any, Iterable

# 抓取正文中的阿拉伯数字（含百分号、小数）
_NUM_RE = re.compile(
    r"(?<![A-Za-z_/])(-?\d+(?:\.\d+)?)(%)?(?![A-Za-z_])",
)


def extract_numbers(text: str) -> list[float]:
    """Normalize numbers found in text to comparable floats (percent → ratio)."""
    out: list[float] = []
    for m in _NUM_RE.finditer(text or ""):
        raw = float(m.group(1))
        if m.group(2) == "%":
            raw = raw / 100.0
        out.append(raw)
    return out


def collect_allowed_numbers(
    *,
    metrics: Iterable[dict[str, Any] | Any] | None = None,
    risk: dict[str, Any] | None = None,
    extra: Iterable[float] | None = None,
) -> set[float]:
    """Build allowlist from computed metrics / risk dump (ADR-001)."""
    allowed: set[float] = set()
    if extra:
        for n in extra:
            allowed.add(float(n))

    for m in metrics or []:
        if isinstance(m, dict):
            val = m.get("value")
        else:
            val = getattr(m, "value", None)
        if val is None:
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        allowed.add(f)
        # also allow percent display form
        if abs(f) <= 1.5:
            allowed.add(round(f * 100, 6))

    risk = risk or {}
    for key in ("score",):
        if risk.get(key) is not None:
            try:
                allowed.add(float(risk[key]))
            except (TypeError, ValueError):
                pass
    for d in risk.get("dimensions") or []:
        for k in ("score", "weight"):
            if d.get(k) is not None:
                try:
                    allowed.add(float(d[k]))
                    if k == "weight":
                        allowed.add(round(float(d[k]) * 100, 6))
                except (TypeError, ValueError):
                    pass
    for h in risk.get("hits") or []:
        # rule messages may already contain numbers — gate compares against metrics primarily
        pass
    dq = (risk.get("quality") or {}) if isinstance(risk.get("quality"), dict) else {}
    if dq.get("completeness") is not None:
        try:
            c = float(dq["completeness"])
            allowed.add(c)
            allowed.add(round(c * 100, 6))
        except (TypeError, ValueError):
            pass
    if dq.get("conflicts") is not None:
        try:
            allowed.add(float(dq["conflicts"]))
        except (TypeError, ValueError):
            pass

    # common integers that appear in narrative (counts)
    allowed.update({0.0, 1.0, 2.0, 3.0, 4.0, 5.0})
    return allowed


def _close(a: float, b: float) -> bool:
    if a == b:
        return True
    # percent vs ratio: 0.78 vs 78
    if abs(a) <= 1.5 and abs(abs(a * 100) - abs(b)) < 0.051:
        return True
    if abs(b) <= 1.5 and abs(abs(b * 100) - abs(a)) < 0.051:
        return True
    return abs(a - b) < 0.051


def number_gate(text: str, allowed: set[float]) -> tuple[bool, list[float]]:
    """Return (ok, offenders). Empty text is ok."""
    if not (text or "").strip():
        return True, []
    found = extract_numbers(text)
    offenders: list[float] = []
    for n in found:
        if not any(_close(n, a) for a in allowed):
            offenders.append(n)
    return (len(offenders) == 0), offenders


def gate_or_fallback(text: str | None, fallback: str, allowed: set[float]) -> tuple[str, bool]:
    """If text fails Number Gate, try to annotate offenders before discarding.

    改进（2026-10-05）：原来出现任何不在 allowlist 的数字就全盘丢弃回 fallback，
    导致 LLM 好的输出也被浪费。现在改为：
    1. 先检查是否有 offender
    2. 如果 offender 数量 <= 2，尝试在文本里标注 [待核验] 并保留
    3. 超过 2 个才回退 fallback
    """
    if not text or not text.strip():
        return fallback, False
    ok, offenders = number_gate(text, allowed)
    if ok:
        return text.strip(), True
    # 少量可疑数字：标注后保留（比全盘丢弃更好）
    if len(offenders) <= 2:
        annotated = text.strip()
        for off in offenders:
            # 把可疑数字旁边加 [待核验] 标注
            off_str = str(int(off)) if off == int(off) else str(off)
            annotated = annotated.replace(off_str, f"{off_str}[待核验]", 1)
        return annotated, True  # 返回 True 因为大部分内容是可用的
    return fallback, False
