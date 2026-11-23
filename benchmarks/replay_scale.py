"""复验 M2 合入前的合成基准。每个哈希种子使用独立进程。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "benchmarks/results/m5-79889f1.json"


def run(module, args, seed):
    env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "benchmarks." + module, *args],
        cwd=ROOT, env=env, check=True, stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout)


def replay(size, repeats):
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))["runs"]
    runs = {}
    for version in ("0.2", "0.3"):
        first = None
        for seed in (0, 1):
            key = f"{version}-{seed}"
            record = run("ir02_smoke", ["--ir", version, "--assertions", str(size),
                                       "--repeats", str(repeats)], seed)
            if record["canonical_answer_sha256"] != reference[key]["canonical_answer_sha256"]:
                raise ValueError(f"{key} 的完整查询答案与旧基准不同")
            if first is not None and record["corpus_sha256"] != first["corpus_sha256"]:
                raise ValueError(f"{key} 的语料因哈希种子改变")
            runs[key] = record
            first = record
    budget = run("proof_budget", ["--repeats", str(repeats)], 0)
    for label, cases in (("current", budget["cases"]), ("reference", reference["budget-0"]["cases"])):
        if len(cases) != 4:
            raise ValueError(f"{label} 的预算对照缺失")
    for new, old in zip(budget["cases"], reference["budget-0"]["cases"]):
        for field in ("ir_version", "corpus_sha256", "result"):
            if new[field] != old[field]:
                raise ValueError(f"预算用例 {field} 与旧基准不同")
    runs["budget-0"] = budget
    return {"kernel_reference": "79889f18766a55de03b31eb88189eab617ec2f8d",
            "runs": runs, "seed_regression": run("seed_regression", [], 0)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assertions", type=int, choices=(1000, 10000), default=1000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats 必须大于 0")
    print(json.dumps(replay(args.assertions, args.repeats), ensure_ascii=False, indent=2))
