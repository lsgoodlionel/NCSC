"""NCSC 命令行入口。"""

import argparse
import json
import sys
from typing import Optional, Sequence

from .core import IRValidationError, KnowledgeBase


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NCSC 确定性语义内核")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="校验 JSON IR")
    validate.add_argument("file")
    query = commands.add_parser("query", help="执行四值查询")
    query.add_argument("file")
    query.add_argument("--subject", required=True)
    query.add_argument("--relation", required=True)
    query.add_argument("--object", dest="object_", required=True)
    query.add_argument("--context", required=True)
    query.add_argument("--valid-at")
    args = parser.parse_args(argv)
    try:
        kb = KnowledgeBase.from_path(args.file)
        if args.command == "validate":
            print(json.dumps({"valid": True, "version": kb.doc["version"]}, ensure_ascii=False))
        else:
            result = kb.query(args.subject, args.relation, args.object_, args.context, args.valid_at)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (IRValidationError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
