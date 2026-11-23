"""Run with python3 -m workbench.server from the repository root."""
import argparse
import json
import sys
from tempfile import TemporaryDirectory
from threading import Lock

from workbench.mcp_tool import answer_digest
from workbench.codex_bridge import explain, find_codex
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter_ns

from ncsc import KnowledgeBase
from ncsc.core import validate_document
from ncsc.preview_io import encode_response

ROOT = Path(__file__).resolve().parent
LIMIT = 2 * 1024 * 1024


# A follow-up is scoped to a session created by this server for the same facts and query.
SESSIONS = {}
SESSION_LOCK = Lock()


def model_query(request, answer, send):
    question = request.get("question") or "请用中文解释当前结果、给出依据和下一步核查建议。"
    if not isinstance(question, str) or len(question) > 4000:
        raise ValueError("问题须为 4000 字以内文本")
    snapshot = {"document": request["document"], "query": request["query"]}
    signature = answer_digest(snapshot)
    session = request.get("session")
    with SESSION_LOCK:
        if session and SESSIONS.get(session) != signature:
            raise ValueError("会话或事实快照已改变，请新建会话")
    with TemporaryDirectory(prefix="ncsc-workbench-") as folder:
        source = Path(folder) / "snapshot.json"
        receipt = Path(folder) / "receipt"
        source.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        result = explain(answer, question, session, send, snapshot_path=source, receipt_path=receipt)
        verified = receipt.is_file() and receipt.read_text(encoding="ascii") == answer_digest(answer)
    if result.get("session"):
        with SESSION_LOCK:
            SESSIONS[result["session"]] = signature
            if len(SESSIONS) > 256:
                del SESSIONS[next(iter(SESSIONS))]
    return dict(result, answer=answer, verified=verified)


def execute(request, send):
    def stage(name, operation):
        send({"kind": "start", "name": name})
        start = perf_counter_ns()
        value = operation()
        send({"kind": "done", "name": name, "ms": (perf_counter_ns() - start) / 1e6})
        return value

    program = request["program"]
    if program not in ("query", "validate", "optimize"):
        raise ValueError("请选择已登记的程序")
    engine = request.get("engine", "ncsc")
    if engine not in ("ncsc", "codex") or (engine == "codex" and program != "query"):
        raise ValueError("当前应用不支持该任务")
    doc = stage("校验事实与来源", lambda: validate_document(request["document"]))
    if program == "validate":
        return {"valid": True, "version": doc["version"], "concepts": len(doc["concepts"]),
                "assertions": len(doc["assertions"])}
    q = request["query"]

    def query(kb, day):
        result = kb.query(q["subject"], q["relation"], q["object"], q["context"], day)
        encode_response(result)
        return result

    if program == "query":
        kb = stage("建立事实索引", lambda: KnowledgeBase(doc))
        answer = stage("执行规则与追溯证据", lambda: query(kb, q["day"] or None))
        if engine == "codex":
            return stage("Codex 调用规则与解释", lambda: model_query(request, answer, send))
        return answer
    first = date.fromisoformat(q["day"])
    days = [(first + timedelta(days=i)).isoformat() for i in range(4)]

    def timed(batch):
        start = perf_counter_ns()
        results = batch()
        return results, (perf_counter_ns() - start) / 1e6

    baseline, before = stage("对照运行 · 逐日重建", lambda: timed(
        lambda: [query(KnowledgeBase(doc), d) for d in days]))

    def reuse():
        kb = KnowledgeBase(doc)
        return [query(kb, d) for d in days]

    optimized, after = stage("优化运行 · 四日复用索引", lambda: timed(reuse))

    def verify():
        if baseline != optimized:
            raise ValueError("两种执行方式的完整答案或证据不一致")
        return {"verified": True, "baseline_ms": before, "reuse_ms": after,
                "days": [{"day": d, "status": r["status"]} for d, r in zip(days, optimized)]}

    return stage("逐日比对完整结果与证据", verify)


class Handler(BaseHTTPRequestHandler):
    def serve_bytes(self, data, mime):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/capabilities":
            return self.serve_bytes(json.dumps({"codex": bool(find_codex())}).encode(), "application/json")
        paths = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                 "/style.css": ("style.css", "text/css"),
                 "/example.json": ("../examples/release-readiness.json", "application/json")}
        if self.path not in paths:
            return self.send_error(404)
        path, mime = paths[self.path]
        self.serve_bytes((ROOT / path).read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        if host not in (f"localhost:{port}", f"127.0.0.1:{port}") or self.headers.get("Origin") not in (None, "http://" + host):
            return self.send_error(403)
        if self.path != "/run":
            return self.send_error(404)
        if self.headers.get_content_type() != "application/json":
            return self.send_error(415)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= LIMIT:
                return self.send_error(413)
            data = json.loads(self.rfile.read(size))
        except (ValueError, RecursionError):
            return self.send_error(400)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def send(event):
            self.wfile.write(json.dumps(event, ensure_ascii=False).encode() + b"\n")
            self.wfile.flush()

        try:
            result = execute(data, send)
            send({"kind": "result", "value": result})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, KeyError, TypeError, RecursionError, OverflowError, AttributeError) as exc:
            send({"kind": "error", "message": str(exc)})
        except Exception as exc:
            print(type(exc).__name__, file=sys.stderr)
            send({"kind": "error", "message": str(exc)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()
