"""将抽取参考与盲输入绑定到已审核的工程冻结版本。"""
from hashlib import sha256
import json

from annotation import verify_ai_freeze as freeze
from .extraction import index_rows, score, validate_batch


def score_frozen(packet, registry, reference_path, responses):
    freeze.verify()
    manifest = freeze.read(freeze.FREEZE)
    if manifest["version"] != "ai-eng-v1" or registry["ir_version"] != manifest["ir"]:
        raise ValueError("冻结版本不匹配")
    corpus = freeze.read(freeze.ROOT / "datasets/synthetic-v0/items.json")
    public_packet = [{"id": row["id"], "text": row["text"]} for row in corpus["items"]]
    if packet != public_packet or len(packet) != manifest["items"]:
        raise ValueError("盲包与冻结输入不匹配")
    if registry != freeze.read(freeze.ROOT / "datasets/synthetic-v0/registry.json"):
        raise ValueError("登记表与冻结输入不匹配")
    raw_reference = reference_path.read_bytes()
    digest = sha256(raw_reference).hexdigest()
    if digest != manifest["private_files"]["adjudicated.json"]:
        raise ValueError("抽取参考与冻结裁决表的摘要不匹配")

    # 此入口读取未经包装的逐条生成记录；用绑定的原文重新核查来源。
    validated = validate_batch(packet, registry, responses)
    generated = index_rows(responses)
    citations = 0
    for item, result in zip(packet, validated):
        claims = generated[item["id"]].get("assertions")
        if isinstance(claims, list):
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                sources = claim.get("sources")
                if not isinstance(sources, list) or not sources or any(
                    source != {"id": "src:excerpt", "description": item["text"]} for source in sources
                ):
                    raise ValueError(f"{item['id']}: 来源无法与冻结原文核验")
        if result["status"] == "candidate":
            citations += sum(len(a["sources"]) for a in result["candidate"]["assertions"])
    report = score(json.loads(raw_reference), validated)
    report.update(freeze=manifest["version"], reference_sha256=digest,
                  verified_source_occurrences=citations)
    return report
