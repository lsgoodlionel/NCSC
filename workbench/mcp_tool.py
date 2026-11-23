"""Read-only stdio MCP tool bound to one NCSC task snapshot."""
import hashlib
import json
import sys
from pathlib import Path

from ncsc import KnowledgeBase
from ncsc.preview_io import encode_response


def answer_digest(answer):
    canonical = json.dumps(answer, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def dispatch(msg, snapshot, receipt):
    if "id" not in msg:
        return None
    method = msg.get("method")
    params = msg.get("params", {})
    response = {"jsonrpc": "2.0", "id": msg["id"]}
    if method == "initialize":
        versions = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
        version = params.get("protocolVersion")
        result = {"protocolVersion": version if version in versions else versions[0],
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "ncsc", "version": "0.1"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": "query", "description": "执行当前已绑定的 NCSC 查询，返回四值状态和来源证据。",
                             "annotations": {"readOnlyHint": True, "openWorldHint": False},
                             "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]}
    elif method == "tools/call":
        if params.get("name") != "query" or params.get("arguments", {}) != {}:
            return dict(response, error={"code": -32602, "message": "Unknown tool or arguments"})
        try:
            q = snapshot["query"]
            answer = KnowledgeBase(snapshot["document"]).query(q["subject"], q["relation"], q["object"],
                                                               q["context"], q["day"] or None)
            encoded = encode_response(answer).decode()
            receipt.write_text(answer_digest(answer), encoding="ascii")
            result = {"content": [{"type": "text", "text": encoded}]}
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            result = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
    else:
        return dict(response, error={"code": -32601, "message": "Method not found"})
    return dict(response, result=result)


def main():
    snapshot = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    receipt = Path(sys.argv[2])
    for line in sys.stdin.buffer:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError()
            response = dispatch(message, snapshot, receipt)
        except (ValueError, TypeError, AttributeError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
        if response is not None:
            print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
