"""NCSC 命令行入口。"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .core import IRValidationError, KnowledgeBase, validate_document
from .migration import preview_migration
from .preview_io import encode_response, load_inputs, load_query_inputs
from .query_preview import DEFAULT_TRACE_BUDGET, QueryLimitError, TraceLimitError, query_preview


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NCSC 确定性语义内核")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="校验 JSON IR")
    validate.add_argument("file")
    migrate = commands.add_parser("migrate", help="预览类别迁移，输出候选文档与报告")
    migrate.add_argument("file")
    query = commands.add_parser("query", help="执行四值查询")
    preview_query = commands.add_parser("query-preview", help="实验性 0.2 分区查询，输出有限证据图")
    query.add_argument("--rule", action="append", help="指定 IR 0.2 / 0.3 查询使用的规则集，每个文件一条规则")
    preview_query.add_argument("--rule", action="append", default=[], help="每次指定一个 P-4 规则文件")
    preview_query.add_argument("--trace-budget", type=int, default=DEFAULT_TRACE_BUDGET,
                               help=f"证明展开预算，1–{DEFAULT_TRACE_BUDGET}")
    for cmd in (query, preview_query):
        cmd.add_argument("file")
        cmd.add_argument("--subject", required=True)
        cmd.add_argument("--relation", required=True)
        cmd.add_argument("--object", dest="object_", required=True)
        cmd.add_argument("--context", required=True)
        cmd.add_argument("--valid-at")
    args = parser.parse_args(argv)
    try:
        if args.command in ("query", "query-preview"):
            if args.command == "query-preview":
                doc, documents = load_inputs(args.file, args.rule)
                answer = query_preview(doc, documents, args.subject, args.relation, args.object_,
                                       args.context, args.valid_at, trace_budget=args.trace_budget)
            else:
                doc, documents = load_query_inputs(args.file, args.rule or [])
                kb = KnowledgeBase(doc, documents if args.rule else None)
                answer = kb.query(args.subject, args.relation, args.object_, args.context, args.valid_at)
                if kb.doc["version"] == "0.1":
                    print(json.dumps(answer, ensure_ascii=False, indent=2))
                    return 0
            response = encode_response(answer)
            if hasattr(sys.stdout, "buffer"):
                sys.stdout.buffer.write(response)
            else:
                sys.stdout.write(response.decode("utf-8"))
            return 0
        if args.command == "migrate":
            with Path(args.file).open(encoding="utf-8") as handle:
                preview = preview_migration(json.load(handle), args.file)
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            report = preview["report"]
            if report["rejected"] or "unhandled_first_error" in report:
                return 2
            return 1 if report["output_status"] == "candidate" else 0
        if args.command == "validate":
            with Path(args.file).open(encoding="utf-8") as handle:
                doc = validate_document(json.load(handle))
            print(json.dumps({"valid": True, "version": doc["version"]}, ensure_ascii=False))
        return 0
    except QueryLimitError as exc:
        code = "trace_limit_exceeded" if isinstance(exc, TraceLimitError) else "query_limit_exceeded"
        print(json.dumps({"error": code, "resource": exc.resource,
                          "limit": exc.limit}), file=sys.stderr)
        return 3
    except RecursionError:
        print(json.dumps({"error": "nesting_limit_exceeded"}), file=sys.stderr)
        return 3
    except (IRValidationError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
