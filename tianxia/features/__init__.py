"""功能包（開發規範手冊 docs/superpowers/specs/2026-10-30-開發模式-design.md 3.1、3.2）：一個功能一包，tianxia/features/<包>/。

- 包只能 import 核心（tianxia/core/ 與手冊 3.1 列的核心模組）、共用規則層（registry.SHARED）與自己這一包，不能 import 別的包（tests/core/test_feature_boundaries.py 守）。
- 登記在 tianxia/core/registry.py 的 FEATURES；新的一包用 scripts/new_feature.py <包名> 生。
- 每一包的測試在自己的 tests/（pyproject 的 testpaths 有 tianxia/features；共用的 fixture 由 tianxia/features/conftest.py 接過來）。
"""
