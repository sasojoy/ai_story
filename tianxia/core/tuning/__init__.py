"""新包的 Config 子模型（手冊第十五節「波次 B、C」第 15 條；第二輪第 74 批開）：一包一檔 `<包>.py`，`scripts/new_feature.py` 生，`models.py` 的 `Config` 接一格 `Config.<包>`。
這裡的檔不 import `models`（`models` 引用它們，同 `jianfa_numbers.py`），所以不繼承 `_Strict`，自己寫 `extra="forbid"`。現有的子模型還在 `models.py`，不搬。
"""
