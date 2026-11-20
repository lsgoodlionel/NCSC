"""将正式接口验收纳入 unittest discover，保留独立探针的命令行入口。"""
from . import m2_semantics, seeded_cycle


def load_tests(loader, tests, pattern):
    for module in (m2_semantics, seeded_cycle):
        tests.addTests(loader.loadTestsFromModule(module))
    return tests
