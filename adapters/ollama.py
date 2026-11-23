"""默认关闭的本地 Ollama 参考适配器，仅向回环地址发送调用者提供的盲材料。"""
import http.client
import json
import os

from .base import propose_ir


def extract(text, version, *, sources, registry, enabled=False):
    if not enabled:
        return {"status": "disabled"}
    model = os.environ.get("NCSC_OLLAMA_MODEL", "").strip()
    if not model:
        return {"status": "invalid_config", "error": "请在 NCSC_OLLAMA_MODEL 中指定本机模型"}
    if model.endswith(("-cloud", ":cloud")):
        return {"status": "invalid_config", "error": "请指定本地模型，当前为云端模型标签"}
    token = os.environ.get("NCSC_OLLAMA_TOKEN", "")
    if os.environ.get("NCSC_OLLAMA_REQUIRE_TOKEN") == "1" and not token:
        return {"status": "invalid_config", "error": "缺少 NCSC_OLLAMA_TOKEN"}
    try:
        port = int(os.environ.get("NCSC_OLLAMA_PORT", "11434"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        return {"status": "invalid_config", "error": "NCSC_OLLAMA_PORT 须为 1–65535"}
    try:
        concepts = registry["concepts"]
        contexts = [row["id"] for row in registry["contexts"]]
        year = registry["document_year"]
    except (KeyError, TypeError):
        return {"status": "invalid_input", "error": "登记表须提供 concepts、contexts 和 document_year"}

    def generate(source_text, schema):
        prompt = {
            "version": schema, "text": source_text, "concepts": concepts, "contexts": contexts,
            "document_year": year, "source_excerpts": sources,
        }
        system = (
            "从 text 提取直接陈述的 IR 断言。仅输出 JSON 对象，字段为 assertions 数组。"
            "每项含 id（a: 前缀）、roles（subject、relation、object）、polarity"
            "（positive/negative）、context、sources（id 和逐字 description），日期明确时加 valid_at。"
            "使用登记表 ID、来源表及指定版本。信息不明则省略，勿从缺失推否定或把报告原因升级为事实。"
        )
        payload = json.dumps({"model": model, "stream": False, "format": "json", "system": system,
                              "prompt": json.dumps(prompt, ensure_ascii=False), "options": {"temperature": 0, "seed": 0}})
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        try:
            conn.request("POST", "/api/generate", body=payload.encode(), headers=headers)
            response = conn.getresponse()
            if response.status != 200:
                raise RuntimeError("Ollama HTTP error")
            envelope = json.load(response)
        finally:
            conn.close()
        if envelope.get("done") is not True:
            raise ValueError("模型生成不完整")
        body = json.loads(envelope["response"])
        if not isinstance(body, dict) or set(body) != {"assertions"}:
            return None
        return {"version": schema, "concepts": concepts, "assertions": body["assertions"]}

    result = propose_ir(text, version, sources=sources, provider=generate)
    if result["status"] == "candidate" and any(
        a["context"] not in contexts for a in result["candidate"]["assertions"]
    ):
        return {"status": "invalid_candidate", "error": "出现未登记上下文"}
    return result
