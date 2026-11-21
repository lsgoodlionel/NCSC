"""离线候选入口。调用方显式提供候选生成函数及可引用的来源片段。"""
from copy import deepcopy
from typing import Any, Callable, Dict, Mapping, Optional

from ncsc.core import IRValidationError, validate_document


def propose_ir(text: str, schema: str, *, sources: Mapping[str, str],
               provider: Optional[Callable[[str, str], Any]] = None) -> Dict[str, Any]:
    if provider is None:
        return {"status": "disabled"}
    if schema not in ("0.2", "0.3") or not isinstance(text, str) or not text.strip():
        return {"status": "invalid_input", "error": "需要非空原文及 IR 0.2 或 0.3 版本号"}
    if not isinstance(sources, Mapping):
        return {"status": "invalid_input", "error": "需要来源 ID 到原文片段的对照表"}
    allowed = dict(sources)
    for sid, excerpt in allowed.items():
        if (not isinstance(sid, str) or not isinstance(excerpt, str)
                or not excerpt.strip() or excerpt not in text):
            return {"status": "invalid_input", "error": "来源须能定位到输入原文"}
    try:
        raw = provider(text, schema)
    except Exception as exc:
        # Provider messages can contain the input text. Report only the exception type.
        return {"status": "provider_error", "error": type(exc).__name__}
    try:
        if not isinstance(raw, dict) or raw.get("version") != schema:
            raise IRValidationError("候选须为指定版本的 IR 文档")
        candidate = validate_document(deepcopy(raw))
        for assertion in candidate["assertions"]:
            for source in assertion["sources"]:
                if allowed.get(source["id"]) != source["description"]:
                    raise IRValidationError(f"{assertion['id']}: 来源 ID 或原文片段与登记记录不符")
    except (IRValidationError, TypeError, RecursionError) as exc:
        return {"status": "invalid_candidate", "error": str(exc)}
    return {"status": "candidate", "candidate": candidate}
