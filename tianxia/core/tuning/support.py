"""客服的數字（Config.support；手冊第十五節「波次 B、C」第 15 條）。不 import models（models 引用這裡），所以不繼承 _Strict，自己寫 extra="forbid"。
設計 docs/superpowers/specs/2026-11-08-帳號綁定與客服-design.md 6.1、6.2（企劃者 2026-11-08 點頭第 2 版）。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SupportTuning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False  # 緊急開關：關著時 /api/support/* 全部 404、/api/main 不多鍵、不建旁檔
    staff: list[str] = Field(default_factory=list)  # 客服名單（認帳號：accounts.id 的數字或登入名，不認名號）；另有 .local/support.txt 與 TIANXIA_SUPPORT（features/support/staff.py）
    body_max: int = Field(default=1000, ge=1)  # 一則（單或回覆）最多幾個字
    open_max: int = Field(default=3, ge=1)  # 同時最多幾張沒結的單
    daily_max: int = Field(default=5, ge=1)  # 24 小時內最多送幾張
    mailbox: str = "support@tianxiadashi.com"  # 登入頁寫給登不進去的人的信箱（暫定；人工收信，不進客服單）
    lookup_hourly: int = Field(default=20, ge=1)  # 每位客服每小時查帳號幾次（設計 6.3；看單帶出的帳號卡不算）
    ledger_rows: int = Field(default=50, ge=1)  # 帳號卡的元寶帳本最多列幾筆（新的在前）
    files_max: int = Field(default=3, ge=0)  # 一張單最多附幾張截圖（客服自動受理第 215 批；0＝主機把截圖關掉）
    file_bytes_max: int = Field(default=3_000_000, ge=1)  # 一張截圖最多幾個位元組（上傳串流累計，超過就停止讀）
    # 客服自動受理第 216 批（設計第八節）：客服官用哪一個帳號回（accounts.id 的數字或登入名；空＝token 路一律 404）、answered 幾天沒動就自動結單
    bot_account: str = ""
    auto_close_days: int = Field(default=3, ge=1)
