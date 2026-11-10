#!/bin/sh
# 客服官的手（客服自動受理第 218 批）：客服官 session 的 Bash（Git Bash）只放行這一支，跟 cli.cmd 做同一件事。
# 為什麼不是 cli.cmd：Git Bash 叫 .cmd 時參數不加引號就交給 cmd，./cli.cmd queue "R&D" 的 & 會被 cmd 當成下一個指令
# （第 218 批實跑過），批次檔裡擋不到；這一支直接叫 python，參數不經過 cmd。
# 由 scripts/support_session_init.py 填好、寫成 LF。鎖定模式：金鑰檔、網址、截圖夾只照下面三個環境變數。
export TIANXIA_SUPPORT_LOCKED=1
export TIANXIA_SUPPORT_CONFIG='{{CONFIG}}'
export TIANXIA_SUPPORT_URL='{{URL}}'
export TIANXIA_SUPPORT_INBOX='{{DIR}}\inbox'
export PYTHONIOENCODING=utf-8
# 下面只擋得到原樣傳進來的特殊字：$(...) 與反引號在叫到這一支之前就被 Git Bash 展開，這裡看到的是展開後的結果。
# 擋命令替換靠 Claude Code 的許可比對不把夾帶 $(...)、反引號的指令當成符合 Bash(./cli.sh *)；排練表 Discord 那一半先補這兩條實跑。
for arg in "$@"; do
  case "$arg" in
    *[\&\|\<\>^!]*)
      echo "cli.sh 的參數不收 & | < > ^ 與驚嘆號（回覆與註記的字從 stdin 進）。"  # 待 joy 潤
      exit 2
      ;;
  esac
done
exec '{{PYTHON}}' '{{REPO}}\scripts\support_cli.py' "$@"
