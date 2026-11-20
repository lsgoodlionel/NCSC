"""CLI 查询的 UTF-8 文件读取和响应边界。"""
import io
import json
import os
import stat
from pathlib import Path
from typing import Any, Iterable, List, Tuple

from .query_preview import QueryLimitError

IR_BYTES = 2 * 1024 * 1024
RULE_BYTES = 128 * 1024
RULE_SET_BYTES = 512 * 1024
OUTPUT_BYTES = 1024 * 1024


def _read(path: str, available: int, resource: str, limit: int) -> bytes:
    with Path(path).open("rb") as stream:
        info = os.fstat(stream.fileno())
        if stat.S_ISREG(info.st_mode) and info.st_size > available:
            raise QueryLimitError(resource, limit)
        data = stream.read(available + 1)
    if len(data) > available:
        raise QueryLimitError(resource, limit)
    return data


def _load_rule_files(rule_paths: Iterable[str]) -> List[Any]:
    rules = []
    remaining = RULE_SET_BYTES
    for rule_path in rule_paths:
        if remaining < RULE_BYTES:
            raw = _read(rule_path, remaining, "rule_set_bytes", RULE_SET_BYTES)
        else:
            raw = _read(rule_path, RULE_BYTES, "rule_bytes", RULE_BYTES)
        remaining -= len(raw)
        rules.append(json.loads(raw.decode("utf-8")))
    return rules


def load_inputs(path: str, rule_paths: Iterable[str]) -> Tuple[Any, List[Any]]:
    doc = json.loads(_read(path, IR_BYTES, "ir_bytes", IR_BYTES).decode("utf-8"))
    return doc, _load_rule_files(rule_paths)


def load_query_inputs(path: str, rule_paths: Iterable[str]) -> Tuple[Any, List[Any]]:
    # 正式 query 兼容既有 0.1 任意大小的有效输入，完整解析后才知道版本。
    with Path(path).open("rb") as stream:
        raw = stream.read()
    doc = json.loads(raw.decode("utf-8"))
    if isinstance(doc, dict) and doc.get("version") in ("0.2", "0.3") and len(raw) > IR_BYTES:
        raise QueryLimitError("ir_bytes", IR_BYTES)
    return doc, _load_rule_files(rule_paths)


def encode_response(answer: Any) -> bytes:
    buffer = io.BytesIO()
    for chunk in json.JSONEncoder(ensure_ascii=False, indent=2).iterencode(answer):
        available = OUTPUT_BYTES - buffer.tell() - 1  # 尾部 LF 也占一个字节
        if len(chunk) > available:
            raise QueryLimitError("output_bytes", OUTPUT_BYTES)
        data = chunk.encode("utf-8")
        if len(data) > available:
            raise QueryLimitError("output_bytes", OUTPUT_BYTES)
        buffer.write(data)
    buffer.write(b"\n")
    return buffer.getvalue()
