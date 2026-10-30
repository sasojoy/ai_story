"""核心（開發規範手冊 docs/superpowers/specs/2026-10-30-開發模式-design.md 第三節）：功能包只能 import 這裡與核心的那幾個模組。

- services.py：服務清單（功能包准叫的 Game 方法）、錢包服務（票的庫存與消耗）、共用的字。
- features.py：掛鉤（Protocol 與有預設值的基底）、核心照 FEATURES 彙整選項、分派、狀態、換日、換季、清失效參照。
- registry.py：FEATURES（有順序）；核心唯一 import 功能包的地方。
- swap.py：JSON 裡整個字串相等的換字（易名帖、資料庫改名共用）。

第一階 ctx 就是 Game 本身，不另包一層（手冊 3.3）。
"""
