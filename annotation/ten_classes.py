"""计算十类实验 H1 单个标注组与 M 组的配对描述统计。"""
import argparse
from collections import Counter
import json
from math import fsum
from pathlib import Path

KINDS = ("entity", "event", "state", "quality", "value", "relation")


def _annotation(value, where):
    if not isinstance(value, dict) or set(value) != {"tags", "kind"}:
        raise ValueError(f"{where} 需要 tags 和 kind")
    kind = value["kind"]
    if kind is not None and kind not in KINDS:
        raise ValueError(f"{where}.kind 未登记")
    tags = value["tags"]
    if tags is not None:
        if (not isinstance(tags, list)
                or any(type(t) is not int or not 0 <= t <= 9 for t in tags)
                or len(set(tags)) != len(tags)):
            raise ValueError(f"{where}.tags 需要互异的 0–9 整数")
        tags = frozenset(tags)
    return tags, kind


def _kappa(pairs, categories):
    n = len(pairs)
    a = Counter(x for x, _ in pairs)
    b = Counter(y for _, y in pairs)
    expected = sum(a[c] * b[c] for c in categories)
    report = {"a_counts": {c: a[c] for c in categories}, "b_counts": {c: b[c] for c in categories},
              "value": None, "na_reason": None}
    if not n:
        report["na_reason"] = "no_paired_concepts"
    elif expected == n * n:
        report["na_reason"] = "constant_marginals"
    else:
        observed = n * sum(x == y for x, y in pairs)
        report["value"] = (observed - expected) / (n * n - expected)
    return report


def summarize(data):
    if not isinstance(data, dict) or set(data) != {"tags_group", "concepts"}:
        raise ValueError("需要 tags_group 和 concepts")
    if data["tags_group"] not in ("T", "M+T") or not isinstance(data["concepts"], list):
        raise ValueError("tags_group 须为 T 或 M+T；concepts 须为数组")
    ids = set()
    paired = []
    tag_pairs, kind_pairs = [], []
    counts = {r: Counter() for r in ("a", "b")}
    exclusions = Counter()
    jaccard = []
    both_empty = missing_pairs = 0
    for row in data["concepts"]:
        if not isinstance(row, dict) or set(row) != {"id", "a", "b"}:
            raise ValueError("每行需要 id、a、b")
        cid = row["id"]
        if not isinstance(cid, str) or not cid.strip() or cid in ids:
            raise ValueError("概念 ID 应非空且唯一")
        ids.add(cid)
        entries = []
        for rater in ("a", "b"):
            tags, kind = _annotation(row[rater], f"{cid}.{rater}")
            entries.append((tags, kind))
            if tags is None:
                label = "missing"
            else:
                label = {0: "unclassifiable", 1: "single"}.get(len(tags), "multiple")
            counts[rater][label] += 1
            if label != "single":
                exclusions[f"{rater}.tags.{label}"] += 1
            if kind is None:
                exclusions[f"{rater}.kind.missing"] += 1
        (at, ak), (bt, bk) = entries
        if at is None or bt is None:
            missing_pairs += 1
            continue
        if at or bt:
            jaccard.append(len(at & bt) / len(at | bt))
        else:
            both_empty += 1
        if len(at) == len(bt) == 1 and ak is not None and bk is not None:
            paired.append(cid)
            tag_pairs.append((next(iter(at)), next(iter(bt))))
            kind_pairs.append((ak, bk))

    raters = {}
    for rater, c in counts.items():
        n = len(ids) - c["missing"]
        raters[rater] = {key: c[key] for key in ("single", "multiple", "unclassifiable", "missing")}
        raters[rater].update(valid_n=n, single_rate=c["single"] / n if n else None,
                             unclassifiable_rate=c["unclassifiable"] / n if n else None,
                             na_reason=None if n else "no_submitted_tags")
    ten, kind = _kappa(tag_pairs, range(10)), _kappa(kind_pairs, KINDS)
    return {"tags_group": data["tags_group"], "concepts_n": len(ids), "raters": raters,
            "jaccard": {"valid_n": len(jaccard), "both_empty": both_empty, "missing_pairs": missing_pairs,
                        "mean": fsum(jaccard) / len(jaccard) if jaccard else None,
                        "na_reason": None if jaccard else "no_nonempty_paired_union"},
            "paired": {"n": len(paired), "ids": sorted(paired),
                       "exclusions_overlapping": dict(sorted(exclusions.items())),
                       "ten_class_kappa": ten, "kind_kappa": kind,
                       "kappas_comparable": ten["value"] is not None and kind["value"] is not None}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        result = summarize(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"H1 输入错误：{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
