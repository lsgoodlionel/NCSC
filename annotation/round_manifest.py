"""创建或复核试标准备阶段的 round.json，记录每份材料的原始字节摘要。"""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

DOCUMENTS = Path(__file__).resolve().parent


def describe(folder, documents=DOCUMENTS):
    inputs = {
        "packet.json": folder / "packet.json",
        "registry.json": folder / "registry.json",
        "GUIDE.md": documents / "GUIDE.md",
        "TRIAL_PROTOCOL.md": documents / "TRIAL_PROTOCOL.md",
    }
    contents = {name: path.read_bytes() for name, path in inputs.items()}
    packet = json.loads(contents["packet.json"].decode("utf-8"))
    registry = json.loads(contents["registry.json"].decode("utf-8"))
    if not isinstance(packet, list) or not packet:
        raise ValueError("packet.json 须包含盲包条目")
    ids = []
    for item in packet:
        if not isinstance(item, dict) or set(item) != {"id", "text"}:
            raise ValueError("盲包条目只接受 id 和 text")
        if not all(isinstance(value, str) and value.strip() for value in item.values()):
            raise ValueError("盲包条目 ID 或文本无效")
        ids.append(item["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("盲包条目 ID 重复")
    if not isinstance(registry, dict) or not all(
        isinstance(registry.get(key), str) and registry[key].strip() for key in ("dataset", "ir_version")
    ):
        raise ValueError("登记表缺少有效的数据集或 IR 标识")
    return {
        "format": "ncsc-trial-draft/1",
        "freeze_status": "pending",
        "dataset": registry["dataset"],
        "ir_version": registry["ir_version"],
        "item_ids": ids,
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    }


def create(folder, documents=DOCUMENTS):
    manifest = describe(folder, documents)
    data = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    # 完整写出后发布，两个准备者同时操作时只允许首个清单成功。
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as stream:
        temp = Path(stream.name)
    try:
        temp.write_bytes(data)
        os.link(temp, folder / "round.json")
    finally:
        temp.unlink()
    return manifest


def verify(folder, documents=DOCUMENTS):
    expected = json.loads((folder / "round.json").read_text(encoding="utf-8"))
    actual = describe(folder, documents)
    if expected != actual:
        if isinstance(expected, dict) and isinstance(expected.get("sha256"), dict):
            changed = [name for name, digest in actual["sha256"].items() if expected["sha256"].get(name) != digest]
            if changed:
                raise ValueError("材料摘要不符：" + "、".join(changed))
        raise ValueError("round.json 的轮次字段与准备材料不符")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("folder", type=Path, help="annotation.trial prepare 的输出目录")
    parser.add_argument("--documents", type=Path, default=DOCUMENTS, help="存放本轮指南与协议的目录")
    args = parser.parse_args()
    try:
        operation = create if args.command == "create" else verify
        manifest = operation(args.folder, args.documents)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"试标清单：{exc}\n")
    print(json.dumps({"dataset": manifest["dataset"], "items": len(manifest["item_ids"]),
                      "freeze_status": manifest["freeze_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
