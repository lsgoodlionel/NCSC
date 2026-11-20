"""在正式查询入口观察同分区证据组合与默认溯源预算。"""
import argparse
from hashlib import sha256
from itertools import product
import json
import os
import platform
from statistics import median
import subprocess
from time import perf_counter_ns

from .ir02_smoke import CONTEXT, FIXTURE, QUERIES, ROOT, encode, load, peak
from ncsc.query_preview import DEFAULT_TRACE_BUDGET, TraceLimitError


def inputs(version, copies):
    doc = json.loads(FIXTURE.read_bytes())
    doc["version"] = version
    doc["assertions"] = [
        dict(fact, id=f"a:p{side}-{i}", context=CONTEXT)
        for side, fact in enumerate(doc["assertions"][:2]) for i in range(copies)
    ]
    return encode(doc)


def run_query(kb):
    try:
        return kb.query(*QUERIES["inferred"])
    except TraceLimitError as error:
        if error.resource != "trace_budget" or error.limit != DEFAULT_TRACE_BUDGET:
            raise
        return error.resource, error.limit


def check(outcome, copies, expect_limit):
    if isinstance(outcome, tuple):
        if not expect_limit:
            raise ValueError("预期完整证明却耗尽预算")
        return {"outcome": "limited", "resource": outcome[0], "limit": outcome[1]}
    if expect_limit:
        raise ValueError("应当受默认预算限制的查询返回了答案")
    evidence = outcome["evidence"]
    pairs = {tuple(node["premises"]) for node in evidence}
    expected = set(product((f"a:p0-{i}" for i in range(copies)), (f"a:p1-{i}" for i in range(copies))))
    if outcome["status"] != "支持" or len(evidence) != len(expected) or pairs != expected:
        raise ValueError("R1 结果与预期的全部有序前提组合不符")
    return {"outcome": "success", "evidence": len(evidence),
            "canonical_answer_sha256": sha256(encode(outcome)).hexdigest()}


def measure(version, copies, expect_limit, repeats):
    data = inputs(version, copies)
    loads, queries = [], []
    reference = None
    for i in range(repeats + 1):
        start = perf_counter_ns()
        kb = load(data)
        loaded = perf_counter_ns()
        outcome = run_query(kb)
        done = perf_counter_ns()
        result = check(outcome, copies, expect_limit)
        if i:
            loads.append(loaded - start)
            queries.append(done - loaded)
            if result != reference:
                raise ValueError("查询结果在重复轮次中改变")
        reference = result
        del kb, outcome
    load_peak, kb = peak(lambda: load(data))
    query_peak, outcome = peak(lambda: run_query(kb))
    if check(outcome, copies, expect_limit) != reference:
        raise ValueError("内存轮次结果与计时轮次不符")
    return {"ir_version": version, "assertions": copies * 2, "premise_combinations": copies**2,
            "corpus_sha256": sha256(data).hexdigest(), "result": reference,
            "elapsed_ns": {"load": loads, "query": queries},
            "median_ns": {"load": median(loads), "query": median(queries)},
            "tracemalloc_peak_bytes": {"load": load_peak, "query": query_peak}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats 必须大于 0")
    cases = [measure(version, n, limited, args.repeats) for version in ("0.2", "0.3")
             for n, limited in ((3, False), (64, True))]
    if [row["result"] for row in cases[:2]] != [row["result"] for row in cases[2:]]:
        raise ValueError("同日输入的跨版本证明或失败原因不同")
    print(json.dumps({
        "protocol": "same-day-proof-budget-v1", "warmups": 1, "repeats": args.repeats,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "system": platform.platform(), "architecture": platform.machine(), "logical_cpus": os.cpu_count(),
        "python": platform.python_version(), "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "query_args": QUERIES["inferred"], "trace_budget": DEFAULT_TRACE_BUDGET, "cases": cases,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
