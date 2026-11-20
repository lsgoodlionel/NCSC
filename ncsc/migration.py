"""0.1 → 0.2 只读预览；报告与候选文档始终一起返回。"""

from copy import deepcopy
from itertools import groupby
from typing import Any, Dict

from .core import IRValidationError, validate_document


def preview_migration(doc: Dict[str, Any], source: str) -> Dict[str, Any]:
    validate_document(doc)
    if doc["version"] != "0.1":
        raise IRValidationError("迁移输入须为 IR 0.1")
    candidate = deepcopy(doc)
    candidate["version"] = "0.2"
    report: Dict[str, Any] = {
        "from": "0.1", "to": "0.2", "source": source,
        "output_status": "candidate",
        "automatic": [{"path": "version", "from": "0.1", "to": "0.2"}],
        "needs_confirmation": [], "id_changes": [], "rejected": [],
    }
    known = {"关系": "relation", "资源": "entity", "值": "value"}
    for old, group in groupby(enumerate(candidate["concepts"]), key=lambda pair: pair[1]["kind"]):
        entries = list(group)
        if old in known:
            for _, concept in entries:
                concept["kind"] = known[old]
            lo, hi = entries[0][0], entries[-1][0]
            index = str(lo) if lo == hi else f"{lo}..{hi}"
            report["automatic"].append({"path": f"concepts[{index}].kind", "from": old, "to": known[old]})
        else:
            for i, concept in entries:
                decision: Dict[str, Any] = {"path": f"concepts[{i}].kind", "from": old}
                if old == "任务":
                    concept["kind"] = "event"
                    decision.update(proposed="event", alternatives=["entity"],
                                    why="“任务”既可视为计划中的活动（event），也可视为被管理的工作项（entity）；影响后续规则的 domain 约束")
                else:
                    decision.update(proposed=None, alternatives=[], why="源类别没有确定映射")
                report["needs_confirmation"].append(decision)
    try:
        validate_document(candidate)
    except IRValidationError as exc:
        path = str(exc).partition(":")[0]
        if not any(item["path"] == path for item in report["needs_confirmation"]):
            report["unhandled_first_error"] = str(exc)
    else:
        if not report["needs_confirmation"]:
            report["output_status"] = "final"
    return {"candidate": candidate, "report": report}
