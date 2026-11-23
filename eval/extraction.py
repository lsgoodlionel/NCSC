"""盲文先生成候选，锁存候选之后独立计算逐条断言的 micro-P/R。"""
import argparse
from collections import Counter
import json
from pathlib import Path

from adapters.base import propose_ir
from adapters.ollama import extract
from ncsc.core import validate_document


def index_rows(rows):
    indexed = {}
    for row in rows:
        key = row["id"]
        if not isinstance(key, str) or not key or key in indexed:
            raise ValueError("条目 ID 须为唯一非空字符串")
        indexed[key] = row
    if not indexed:
        raise ValueError("条目集为空")
    return indexed


def predict(packet, registry, *, enabled=False):
    rows = []
    for key, row in index_rows(packet).items():
        if set(row) != {"id", "text"}:
            raise ValueError("盲包仅允许 id 和 text")
        result = extract(row["text"], registry["ir_version"], registry=registry,
                         sources={"src:excerpt": row["text"]}, enabled=enabled)
        if result["status"] in ("disabled", "invalid_config", "invalid_input"):
            raise ValueError(result.get("error", result["status"]))
        rows.append({"id": key, **result})
    return rows


def validate_batch(packet, registry, responses):
    """验证外部离线生成器已锁存的逐条输出，保留显式失败。"""
    inputs = index_rows(packet)
    generated = index_rows(responses)
    if inputs.keys() != generated.keys():
        raise ValueError("盲包与生成结果的 ID 必须完全匹配")
    rows = []
    version = registry["ir_version"]
    contexts = {row["id"] for row in registry["contexts"]}
    for key, item in inputs.items():
        if set(item) != {"id", "text"}:
            raise ValueError("盲包仅允许 id 和 text")
        raw = generated[key]
        def provider(text, schema):
            if set(raw) != {"id", "assertions"}:
                return None
            return {"version": schema, "concepts": registry["concepts"], "assertions": raw["assertions"]}
        result = propose_ir(item["text"], version, sources={"src:excerpt": item["text"]}, provider=provider)
        if result["status"] == "candidate" and any(
            a["context"] not in contexts for a in result["candidate"]["assertions"]
        ):
            result = {"status": "invalid_candidate", "error": "出现未登记上下文"}
        rows.append({"id": key, **result})
    return rows


def fact_keys(assertions):
    return {(a["roles"]["subject"], a["roles"]["relation"], a["roles"]["object"],
             a["polarity"], a["context"], a.get("valid_at"), tuple(sorted(a.get("valid_during", {}).items())))
            for a in assertions}


def score(references, predictions):
    expected, actual = index_rows(references), index_rows(predictions)
    if expected.keys() != actual.keys():
        raise ValueError("参考与候选条目 ID 须完全匹配")
    tp = n_gold = n_pred = 0
    outcomes = Counter()
    for key, row in expected.items():
        gold = fact_keys(row["assertions"])
        pred = actual[key]
        status = pred["status"]
        if status == "candidate":
            candidate = validate_document(pred["candidate"])
            found = fact_keys(candidate["assertions"])
        elif status in ("provider_error", "invalid_candidate"):
            found = set()
        else:
            raise ValueError("未知或未执行的候选状态")
        outcomes[status] += 1
        tp += len(gold & found)
        n_gold += len(gold)
        n_pred += len(found)
    return {"items": len(expected), "outcomes": dict(outcomes), "matched": tp, "predicted": n_pred,
            "expected": n_gold, "precision": tp / n_pred if n_pred else None,
            "recall": tp / n_gold if n_gold else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    infer = commands.add_parser("predict")
    infer.add_argument("packet", type=Path)
    infer.add_argument("registry", type=Path)
    infer.add_argument("--enable-local-model", action="store_true")
    validate = commands.add_parser("validate")
    validate.add_argument("packet", type=Path)
    validate.add_argument("registry", type=Path)
    validate.add_argument("responses", type=Path)
    evaluate = commands.add_parser("score")
    evaluate.add_argument("reference", type=Path)
    evaluate.add_argument("predictions", type=Path)
    def read(path):
        return json.loads(path.read_text(encoding="utf8"))
    args = parser.parse_args()
    try:
        if args.action == "predict":
            result = predict(read(args.packet), read(args.registry), enabled=args.enable_local_model)
        elif args.action == "validate":
            result = validate_batch(read(args.packet), read(args.registry), read(args.responses))
        else:
            ref = read(args.reference)
            result = score(ref["items"] if isinstance(ref, dict) else ref, read(args.predictions))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
