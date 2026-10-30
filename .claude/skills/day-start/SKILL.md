---
name: day-start
description: 每天開工：確認 git 身分與 repo 狀態、從所有分支找出自己最新的日誌、讀本地記憶裡的使用者習慣、看待決定事項、隊友的交接與重疊的檔案，整理出今天的待辦建議（TDL）。只在使用者輸入 /day-start 時執行。
disable-model-invocation: true
---

# 開工（/day-start）

目的：新對話沒有昨天的記憶，開工時把「做到哪、還有什麼沒收、隊友交接了什麼、使用者習慣怎麼做事」讀回來，給出今天的待辦建議。

**這個指令只讀不寫**：不改程式、不改設定、不 commit、不切分支。唯一的例外是 `git fetch`（只更新遠端追蹤資訊）。需要寫入的（設定身分、合併身分、切分支、啟用 hook）只給指令，交給使用者或 `/day-end`。

這份流程適用任何 git 專案；專案自己的規範若有文件（例如 `docs/git-workflow.md`）就以文件為準，否則看 `.claude/skills/_daily/git-workflow.md`。

## 0. 工具與規則

- `<daily>` = `<py> .claude/skills/_daily/daily.py`（在 repo 根目錄執行）。`<py>`：依序試 `python3`、`python`、`py`，取第一個 `<名稱> -c ""` 成功的（Windows 的 `python3` 可能是商店捷徑，會失敗）。找不到 Python → 說明需要 Python 3.8+，後面能用 git 指令做的照做。
- 這裡用到的子命令（`context`、`identities`、`overlap`、`journal find`、`scan`）都**只讀**，輸出 JSON。判斷以 JSON 為準，不要自己重算。
- **機敏資訊**：照 `.claude/skills/_daily/sensitive-rules.md`。摘要與 TDL 只寫改寫後的說法；讀到機敏內容只寫「檔案:行號 有疑似機敏內容」，不抄原文、姓名、數值。

## 1. 身分與 repo 狀態

執行 `<daily> context --fetch`，依欄位處理（異常放進摘要「注意」並附指令，**不要自己執行**）：

| 欄位 | 處理 |
|---|---|
| `user.valid` 是 false | **停下來**，請使用者提供「名字」「email」兩個欄位，給他指令 `git config user.name "<名字>"`、`git config user.email "<email>"`。他設定好、或明確說「用這組」後才繼續 |
| `state: in-progress` | 「注意」**第一優先**：有進行中的 `in_progress`，請先完成或放棄（`git rebase --continue` / `--abort` 等） |
| `state: default` / `detached` | 提醒今天要開分支：`git switch --no-track -c <username>/<主題> origin/<default>` |
| `state: gone` / `merged` | 分支已合併或遠端已刪除：`git switch <default> && git pull --ff-only && git switch -c <username>/<新主題>`（有沒 commit 的改動要先處理） |
| `state: tracks-default` | upstream 被設成主分支，`git push` 會指向主分支：`git branch --unset-upstream` |
| `hooks.enabled` 是 false | `project_githooks` 是 false → `git config core.hooksPath <hooks.daily_hooks>`；是 true（專案有自己的 hook，但沒有三個都呼叫 `daily.py`）→ 建議在專案的 `pre-commit`、`commit-msg`、`pre-push` 裡呼叫 `daily.py`，不要直接換掉 `core.hooksPath` |
| `offline` 是 true | 沒有 remote → 說明這個 repo 沒有遠端，略過隊友與遠端比對；`fetch: failed` → 說明離線，遠端比對都標「未更新」 |
| `uncommitted` / `unpushed` / `behind_default` | 放進摘要的 git 數字 |

## 2. 多個身分（建議 `.mailmap`）

`<daily> identities` 列出可能是同一人的其他身分（`candidates`，附理由與填好的 `mailmap` 行）。
- 本地記憶 `user-<username>.md` 記著「`.mailmap`：使用者已拒絕」→ **不要再提**。
- 否則列出候選與 `mailmap` 行讓使用者確認；理由含「電腦自動產生的 email」的要特別請他確認是不是自己。寫入交給 `/day-end`（獨立 commit）。

## 3. 自己的日誌

`<daily> journal find --user <username>`（工具已經跨所有分支找出最新一份）：
- `users.<username>` 是 null → 「還沒有日誌」，跳過這步。
- `source` 不是 `worktree` → 摘要註明「日誌在分支 `<source>`，尚未合併進目前分支」。
- `format: v2` → 用 `sections`：**🔵 進行中**（先接著做）→ **🟡 待處理**（依順序）→ **🔴 未決定**；`next` 是上次指定的第一件事。
- `format: legacy`（舊格式，`content` 是全文）→ 三色格式抓「🟡 待完成」「🔴 待決定」；更舊的 `## 明天從這裡開始` 當作待處理、`## 未完成` 當作補充。
- `commits_after` 有內容 → 列出來：這些 commit 在最新日誌之後，可能上次沒收工。
- **機敏巡檢**（只讀）：`source` 是 `worktree` 時 `<daily> scan --file <path>`；否則 `git show <commit>:<path> | <daily> scan --file -`。專案有 `docs/decisions.md` 也一起掃。再人工讀一遍有沒有姓名、業務資料、內部網址。
  - 🔴 → 「注意」**第一優先**：這組帳密已在 git 歷史裡，請立刻更換；清理歷史由使用者決定。
  - 🟡 → 列出檔案與行號（不抄原文），建議下次 `/day-end` 改寫。

## 4. 本地記憶（使用者習慣）

- 讀 Claude 的本地記憶資料夾（系統提示 Memory 段落指定的路徑）的 `MEMORY.md`，再讀 `user-<username>.md` 與 `type: feedback` 的記憶。
- 今天的待辦照這些習慣排（例如使用者要求「先提方案、確認後才實作」，第一步就寫「提方案」）。
- 記憶寫的是當時的狀況；提到的檔案或指令，先確認還存在再建議。
- 記憶只存在這台電腦，讀不到時說明，不影響其他步驟。隊友的資訊只看日誌（記憶不共享）。

## 5. 判斷點

- 專案有 `docs/decisions.md` 就讀「待決定」，和日誌的「🔴 未決定」合併、去掉重複。這些要使用者拍板，不要自己決定。
- 「已決定」只在和今天要做的事有關時提一下。

## 6. 隊友（多人開發時）

1. `<daily> journal find --all`，看其他人（`users` 裡不是自己的）最新一份日誌：
   - **「交接」對象是自己的 username 或「全體」** → 一律列出，排進 TDL。
   - 「未決定」和今天的工作有關才提。
   - `format: legacy` 的只看三行重點與待決定。
2. `<daily> overlap`：`overlaps` 列出其他還沒合併的分支也改到、和我重疊的檔案 → 放進「注意」（哪個分支、哪些檔案），建議先和對方確認再改。
3. 其他隊友動態和今天無關就省略。

## 7. 資料備份（專案有才做）

- README、CLAUDE.md 有寫備份資料夾或備份指令 → 列出最新備份的檔名與時間，超過 1 天就提醒。
- 只看檔名與時間，**不要打開或複製資料庫或備份檔**（可能含個資）。沒有就省略。

## 8. 開工摘要與 TDL

越短越好；待辦依優先順序排：交接給我的（需要先處理的）→ 進行中 → 待處理 → 需要我決定的。

```
## 開工 YYYY-MM-DD · <username>（分支：<branch>）

**上次做到**（日誌 YYYY-MM-DD）：1–3 行
**下次從這裡開始**（上次指定）：…

### 今日 TDL 建議
1. 🤝 …（隊友交接，誰給的）
2. 🔵 …（進行中，具體到可以直接動手）
3. 🟡 …（待處理）
4. 🔴 先請你決定：…（選項 A / B，Claude 的建議）

**待你決定**：N 項（列出；沒有就寫「無」）
**git**：未 commit N 檔 / 未 push N 筆 / 落後 <default> N 筆
**備份**：最新備份 <檔名>（N 小時前）（專案沒有就省略）
**注意**：🔴 已進 git 的帳密（第一優先）、進行中的 rebase / merge、在主分支上、分支已合併、upstream 指向主分支、hook 未啟用、身分要合併、日誌在未合併的分支、和隊友重疊的檔案、🟡 日誌有疑似機敏內容（檔案:行號）…（沒有就省略）
```

## 9. 問今天從哪開始

用 AskUserQuestion 問「今天從哪一項開始？」：選項是 TDL 前 4 項（標籤寫短名稱，說明寫內容），使用者可以從「Other」自己寫。**沒回答就不要替他決定。**
