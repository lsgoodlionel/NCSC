"""核对公开工程冻结；可选地核对本机协调人已锁存的 AI 试标记录。"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .trial import trial_metrics, validate_sheet


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "datasets/freezes/ai-eng-v1/FROZEN.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_files(folder, hashes):
    for name, digest in hashes.items():
        if sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"文件摘要不一致：{name}")


def verify(pilot=None):
    record = read(FREEZE)
    check_files(ROOT, record["public_files"])
    data = read(ROOT / "datasets/synthetic-v0/items.json")["items"]
    if {row["family"] for row in data} != set(record["family_partition"]):
        raise ValueError("场景族与划分不一致")
    if pilot is None:
        return
    check_files(pilot, record["private_files"])
    check_files(pilot, read(pilot / "manifest.json")["files"])
    packet, registry = read(pilot / "A/packet.json"), read(pilot / "A/registry.json")
    if packet != [{k: row[k] for k in ("id", "text")} for row in data]:
        raise ValueError("试标语料与查询集原文不匹配")
    if registry != read(ROOT / "datasets/synthetic-v0/registry.json"):
        raise ValueError("试标登记表与公开登记表不匹配")
    metrics = trial_metrics(packet, registry, read(pilot / "A/output.json"), read(pilot / "B/output.json"))
    if metrics != read(pilot / "metrics-before.json"):
        raise ValueError("复算的裁决前指标不匹配")
    if validate_sheet(packet, registry, read(pilot / "adjudicated.json")):
        raise ValueError("裁决表仍有空项")
    disputed = {row["item"] for row in read(pilot / "differences.json")}
    decisions = read(pilot / "decisions.json")
    if {row["item"] for row in decisions} != disputed or any(row["unresolved"] for row in decisions):
        raise ValueError("尚有未覆盖或未解决的分歧")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path)
    verify(parser.parse_args().pilot)
    print("ai-eng-v1 核对通过")
