"""在同日、同上下文内，分别改变 IR 0.3 活跃事实数和 R1 的证明分支数。"""
import argparse
from hashlib import sha256
import json
import os
import platform
from statistics import median
import subprocess
from time import perf_counter_ns

from .ir02_smoke import CONTEXT, QUERIES, ROOT, encode, load, peak
from .proof_budget import DEFAULT_TRACE_BUDGET, check, inputs, run_query

INTERVAL = {"from": "2026-11-18", "to": "2026-11-20"}
EXTRAS = (0, 64, 512)
COPIES = (1, 8, 32, 64)


def corpus(axis, size):
    copies = size if axis == "proof_branches" else 1
    doc = json.loads(inputs("0.3", copies))
    for assertion in doc["assertions"]:
        del assertion["valid_at"]
        assertion["valid_during"] = INTERVAL
    if axis == "active_facts":
        # 所有档位共用登记表；新增事实使用独立的关系，不参与 R1 连接。
        relation = "r:bench:observed"
        doc["concepts"].append({"id": relation, "aliases": ["已观测"], "kind": "relation"})
        for i in range(max(EXTRAS)):
            subject = f"c:bench:item-{i}"
            doc["concepts"].append({"id": subject, "aliases": [f"观测项{i}"], "kind": "entity"})
            if i < size:
                doc["assertions"].append({
                    "id": f"a:observed-{i}", "roles": {
                        "subject": subject, "relation": relation, "object": "c:value:true",
                    }, "polarity": "positive", "context": CONTEXT, "valid_during": INTERVAL,
                    "sources": [{"id": "src:bench", "description": "合成观测记录"}],
                })
    return encode(doc)


def verified(outcome, copies, limited):
    summary = check(outcome, copies, limited)
    if summary["outcome"] == "success":
        for root in outcome["evidence"]:
            children = root["trace"]
            if ("valid_during" in root or [c["assertion_id"] for c in children] != root["premises"]
                    or any(c.get("valid_during") != INTERVAL for c in children)):
                raise ValueError("区间溯源与原始前提不符")
    return summary


def measure(axis, size, repeats):
    data = corpus(axis, size)
    copies = size if axis == "proof_branches" else 1
    limited = axis == "proof_branches" and size == 64
    loads, queries = [], []
    reference = None
    for run in range(repeats + 1):
        start = perf_counter_ns()
        kb = load(data)
        loaded = perf_counter_ns()
        outcome = run_query(kb)
        done = perf_counter_ns()
        result = verified(outcome, copies, limited)
        if run:
            loads.append(loaded - start)
            queries.append(done - loaded)
            if result != reference:
                raise ValueError("同一输入上的输出发生变化")
        reference = result
        del kb, outcome
    load_peak, kb = peak(lambda: load(data))
    query_peak, outcome = peak(lambda: run_query(kb))
    if verified(outcome, copies, limited) != reference:
        raise ValueError("内存采样轮的结果不同")
    return {
        "axis": axis, "size": size, "active_input_facts": 2 + size if axis == "active_facts" else 2,
        "assertions": 2 + size if axis == "active_facts" else copies * 2,
        "premise_combinations": copies**2, "corpus_sha256": sha256(data).hexdigest(), "result": reference,
        "elapsed_ns": {"load": loads, "query": queries}, "median_ns": {"load": median(loads), "query": median(queries)},
        "tracemalloc_peak_bytes": {"load": load_peak, "query": query_peak},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats 必须为正数")
    facts = [measure("active_facts", n, args.repeats) for n in EXTRAS]
    if any(row["result"] != facts[0]["result"] for row in facts):
        raise ValueError("添加无关活跃事实后目标证明发生变化")
    branches = [measure("proof_branches", n, args.repeats) for n in COPIES]
    if branches[0]["result"] != facts[0]["result"]:
        raise ValueError("两轴的基线答案不同")
    print(json.dumps({
        "protocol": "ir03-active-density-v1", "query": QUERIES["inferred"], "interval": INTERVAL,
        "version": "0.3", "warmups": 1, "repeats": args.repeats, "trace_budget": DEFAULT_TRACE_BUDGET,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "system": platform.platform(), "architecture": platform.machine(), "logical_cpus": os.cpu_count(),
        "python": platform.python_version(), "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "cases": facts + branches,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
