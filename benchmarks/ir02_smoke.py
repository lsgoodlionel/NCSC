"""运行正式 IR 0.2 加载和查询的分区规模检查。"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
from statistics import median
import subprocess
from time import perf_counter_ns
import tracemalloc

from ncsc import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/contract/fixtures/0.2/valid/example-migrated.json"
CONTEXT = "ctx:bench-0"
DAY = "2026-11-19"
QUERIES = {
    "direct": ("c:task:release", "r:task:requires", "c:resource:signing-key", CONTEXT, DAY),
    "inferred": ("c:task:release", "r:status:blocked", "c:value:true", CONTEXT, DAY),
}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def corpus(size):
    doc = json.loads(FIXTURE.read_bytes())
    pair = doc["assertions"][:2]
    doc["assertions"] = [
        dict(pair[i % 2], id=f"a:bench-{i}", context=f"ctx:bench-{i // 2}") for i in range(size)
    ]
    return encode(doc)


def source_hash():
    # 即使测量未提交的内核，也能用源码指纹区分实现。
    paths = sorted((ROOT / "ncsc").rglob("*.py")) + [Path(__file__).resolve()]
    digest = sha256()
    for path in paths:
        digest.update(encode([str(path.relative_to(ROOT)), sha256(path.read_bytes()).hexdigest()]))
    return digest.hexdigest()


def load(data):
    return KnowledgeBase(json.loads(data))


def digest_answer(key, answer):
    evidence = answer["evidence"]
    if answer["status"] != "支持" or len(evidence) != 1:
        raise ValueError(f"{key} 查询未得到预期证据")
    node = evidence[0]
    if key == "direct" and node["assertion_id"] != "a:bench-0":
        raise ValueError("直接证据 ID 不符")
    if key == "inferred" and node.get("premises") != ["a:bench-0", "a:bench-1"]:
        raise ValueError("推导前提不符")
    return sha256(encode(answer)).hexdigest()


def peak(fn):
    tracemalloc.start()
    try:
        value = fn()
        used = tracemalloc.get_traced_memory()[1]
        return used, value
    finally:
        tracemalloc.stop()


def measure(size, repeats):
    data = corpus(size)
    timings = {k: [] for k in ("load", *QUERIES)}
    expected = {}
    # 第零轮预热；每一轮都从相同的 UTF-8 字节重新构建知识库。
    for run in range(repeats + 1):
        start = perf_counter_ns()
        kb = load(data)
        elapsed = perf_counter_ns() - start
        if run:
            timings["load"].append(elapsed)
        for key, query in QUERIES.items():
            start = perf_counter_ns()
            answer = kb.query(*query)
            elapsed = perf_counter_ns() - start
            if run:
                timings[key].append(elapsed)
            digest = digest_answer(key, answer)
            if expected.setdefault(key, digest) != digest:
                raise ValueError(f"{key} 重复查询的结果摘要不同")
        del kb

    load_peak, kb = peak(lambda: load(data))
    peak_bytes = {"load": load_peak}
    for key, query in QUERIES.items():
        peak_bytes[key], answer = peak(lambda: kb.query(*query))
        if digest_answer(key, answer) != expected[key]:
            raise ValueError(f"{key} 内存测量轮结果不同")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    return {
        "protocol": "ir02-partitions-v1", "ir_version": "0.2", "assertions": size,
        "partitions": size // 2, "corpus_bytes": len(data), "corpus_sha256": sha256(data).hexdigest(),
        "query_args": QUERIES, "canonical_answer_sha256": expected,
        "head": commit, "source_sha256": source_hash(),
        "system": platform.platform(), "architecture": platform.machine(),
        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
        "python": platform.python_version(), "python_implementation": platform.python_implementation(),
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"), "warmups": 1, "repeats": repeats,
        "elapsed_ns": timings, "median_ns": {key: median(xs) for key, xs in timings.items()},
        "tracemalloc_peak_bytes": peak_bytes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assertions", type=int, choices=(1000, 10000, 100000, 1000000), default=1000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats 必须大于 0")
    print(json.dumps(measure(args.assertions, args.repeats), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
