"""在 NCSC 根目录使用 PYTHONPATH=. python3 /path/to/assess.py 运行。"""
import gc
import json
from pathlib import Path
from statistics import median
import tempfile
from time import perf_counter
import tracemalloc

from ncsc.preview_io import encode_response, load_inputs
from ncsc.query_preview import QueryLimitError, TraceLimitError, query_preview

def measure(label, fn):
    def run():
        try:
            return fn()
        except QueryLimitError as exc:
            return exc.resource
    times = []
    for _ in range(3):
        gc.collect()
        start = perf_counter()
        outcome = run()
        times.append(1000 * (perf_counter() - start))
    gc.collect()
    tracemalloc.start()
    run()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(label, round(median(times), 2), round(peak / 1048576, 2), outcome, flush=True)

doc = json.loads(Path("tests/contract/fixtures/0.2/valid/example-migrated.json").read_text())
base = doc["assertions"][0]
q = ("c:task:release", "r:status:blocked", "c:value:true", "ctx:project-alpha", "2026-11-19")
r1 = json.loads(Path("tests/contract/fixtures/rules-0.2/valid/r1-resource-unavailable.json").read_text())
with tempfile.TemporaryDirectory() as folder:
    p = Path(folder) / "ir.json"
    for n in (256, 2048, 8192):
        data = dict(doc, assertions=[dict(base, id=f"a:{i}") for i in range(n)])
        p.write_text(json.dumps(data, ensure_ascii=False))
        measure(("read+parse", n, p.stat().st_size), lambda: len(load_inputs(str(p), [])[0]["assertions"]))

for n in (20, 50, 100):
    # 两个前提各有 n 项，共享资源；每个任务和 n 个不同的明示事实配对。
    # 第二前提允许可变宾语，用于隔离测量合法规则的多对多连接。
    rule = json.loads(json.dumps(r1))
    rule["id"] = "bench_join"
    rule["premises"][1]["object"] = "?value"
    concepts = list(doc["concepts"])
    facts = []
    for i in range(n):
        for prefix, template, slot in (("t", base, "subject"), ("v", doc["assertions"][1], "object")):
            cid = f"c:{prefix}{i}"
            concepts.append(dict(id=cid, kind="entity", aliases=["对象"]))
            facts.append(dict(template, id=f"a:{prefix}{i}", roles=dict(template["roles"], **{slot:cid})))
    data = dict(doc, concepts=concepts, assertions=facts)
    # 查询没有证据的已声明任务：不会调用证明展开。
    def join():
        ans = query_preview(data, [rule], *q, trace_budget=1)
        assert ans["status"] == "未知"
        return ans["status"]
    measure(("join-query", n, n*n), join)

for n in (10, 101):
    data = dict(doc, assertions=[dict(a, id=f"a:{j}-{i}") for j,a in enumerate(doc["assertions"][:2]) for i in range(n)])
    def explain():
        try:
            return len(query_preview(data, [r1], *q)["evidence"])
        except TraceLimitError as exc:
            return exc.resource
    measure(("proof-options", n, n*n), explain)

for size in (256, 8192):
    data = dict(doc, assertions=[dict(a, id=f"a:{j}-{i}",
                                      sources=[{"id": f"src:{j}", "description": "x" * size}])
                                 for j,a in enumerate(doc["assertions"][:2]) for i in range(10)])
    answer = query_preview(data, [r1], *q)
    measure(("encode-output", size, len(answer["evidence"])), lambda: len(encode_response(answer)))
