"""成对测量同一批过期区间移入查询上下文对 IR 0.3 的影响。"""
import argparse
from hashlib import sha256
import json
import os
import platform
from statistics import median
import subprocess
from time import perf_counter_ns

from .ir02_smoke import CONTEXT, DAY, QUERIES, ROOT, corpus, digest_answer, encode, load, peak


def materials(count):
    doc = json.loads(corpus(2, "0.3"))
    active = doc["assertions"][:]
    expired = [dict(active[1], id=f"a:old-{i}", polarity="negative",
                    valid_during={"from": "2025-01-01", "to": "2026-11-18"}) for i in range(count)]
    return {arm: encode(dict(doc, assertions=active + [dict(a, context=context) for a in expired]))
            for arm, context in (("same", CONTEXT), ("other", "ctx:bench-1"))}


def distribution(samples):
    values = sorted(samples)
    return {"min": values[0], "median": median(values), "max": values[-1]}


def measure(count, pairs, batch):
    data = materials(count)
    query = QUERIES["inferred"]
    reference = load(corpus(2, "0.3")).query(*query)
    digest = digest_answer("inferred", reference, "0.3")
    samples = []
    for i in range(-2, pairs):  # 两个方向各预热一对
        order = ["same", "other"] if i % 2 == 0 else ["other", "same"]
        pair = {"order": order}
        for arm in order:
            start = perf_counter_ns()
            kb = load(data[arm])
            build = perf_counter_ns() - start
            # 逐次计时，完整答案比对与摘要计算均在计时区间之外。
            durations = []
            for _ in range(batch):
                start = perf_counter_ns()
                answer = kb.query(*query)
                durations.append(perf_counter_ns() - start)
                if answer != reference:
                    raise ValueError(f"{arm}: 答案、活跃证据或冲突抑制与两条活跃事实的对照不符")
            pair[arm] = {"build_ns": build, "queries_ns": durations, "query_median_ns": median(durations)}
            del kb
        if i >= 0:
            samples.append(pair)
    memory = {}
    for arm in data:
        build, kb = peak(lambda: load(data[arm]))
        cost, answer = peak(lambda: kb.query(*query))
        if answer != reference:
            raise ValueError("内存轮结果不一致")
        memory[arm] = {"build": build, "query": cost}
        del kb
    return {"expired": count, "active": 2, "total": count + 2,
            "corpus_sha256": {k: sha256(v).hexdigest() for k, v in data.items()},
            "answer_sha256": digest, "samples": samples, "tracemalloc_peak_bytes": memory,
            "query_batch_median_ns": {arm: distribution([p[arm]["query_median_ns"] for p in samples])
                                      for arm in data},
            "paired_difference_ns": distribution([p["same"]["query_median_ns"] - p["other"]["query_median_ns"]
                                                  for p in samples])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expired", type=int, nargs="+", default=[0, 128, 1024, 4096])
    parser.add_argument("--pairs", type=int, default=10)
    parser.add_argument("--batch", type=int, default=7)
    args = parser.parse_args()
    if min(args.expired) < 0 or args.pairs < 2 or args.pairs % 2 or args.batch < 1:
        parser.error("规模须非负；pairs 须为正偶数，batch 须为正整数")
    rows = [measure(n, args.pairs, args.batch) for n in args.expired]
    print(json.dumps({"protocol": "expired-density-v1", "ir": "0.3", "day": DAY,
                      "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                      "python": platform.python_version(), "platform": platform.platform(),
                      "hashseed": os.environ.get("PYTHONHASHSEED"), "pairs": args.pairs, "batch": args.batch,
                      "warmup_pairs": 2, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
