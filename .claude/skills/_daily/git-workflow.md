# Git 協作規範

多人開發時的分支、commit 與 push 規則。`/day-end` 照這份規範操作；手動操作也請遵守。專案若有自己的 `docs/git-workflow.md`，以專案文件為準。
以下 `<default>` 是主分支（`main` 或 `master`），`<username>` 是 git email `@` 前面那段轉小寫。

## 1. 第一次 clone 後

```bash
git config user.name  "<你的名字>"
git config user.email "<你的公司 email>"      # 日誌資料夾以 email 的 @ 前面命名
git config core.hooksPath .claude/skills/_daily/hooks   # 專案已有 .githooks/ 時，改在專案 hook 裡呼叫 daily.py
```

專案導入這套流程時，根目錄 `.gitattributes` 加一行，避免 Windows 把 hook 轉成 CRLF 而無法執行：

```
.claude/skills/_daily/hooks/* text eol=lf
```

沒設定身分時 git 會用電腦名稱產生身分（例如 `xxx@Someones-MacBook.local`），同一個人的 commit 與日誌會分散，所以 `/day-start`、`/day-end` 會停下來請你設定。

## 2. 硬性規則（hook 會擋）

| 規則 | 擋在哪 |
|---|---|
| 不在 `<default>` 上 commit，不 push 到 `<default>` | pre-commit、pre-push |
| 不 force push（push 必須是 fast-forward） | pre-push |
| 不能進版控：`.env*`（`.env.example` 除外）、`.secret_key`、`*.pem`、`*.key`、`*.db`、`*.sqlite*`、`* copy/` | pre-commit |
| 只能改自己的日誌資料夾 `docs/<project>_journal/<username>/` | pre-commit |
| 日誌格式要通過 `daily.py journal validate` | pre-commit |
| 日誌、`docs/decisions.md`、`.mailmap` 各自獨立一筆 commit，不和其他改動混在一起 | pre-commit |
| commit 內容、commit 訊息、要 push 的 commit 不能有 🔴 帳密或金鑰 | pre-commit、commit-msg、pre-push |
| 不用 `--no-verify` 繞過 | — |

完成 merge / rebase 時 git 也會跑 hook，這時不檢查別人帶進來的改動（別人的日誌、主分支上的程式碼）。

## 3. 要先問使用者（`/day-end` 一律用選項問，沒得到回答不做）

- 開新分支與分支名稱、修改 git config
- 同步主分支（merge / rebase）；有衝突就 abort，回報衝突檔案，不自己解
- push、開 PR
- 有沒 commit 的改動時：要 commit 還是先保留（**不用 `--autostash`、不自動 stash**）

## 4. 分支

- 分支名稱：`<username>/<主題>`，主題英文小寫加連字號。
- 從最新主分支開分支：
  ```bash
  git fetch origin
  git switch --no-track -c <username>/<主題> origin/<default>   # --no-track：不要把 upstream 設成主分支
  ```
- 已經在主分支上改了東西：`git switch -c <username>/<主題>`，改動會跟著帶過去。
- 分支已合併或遠端已刪除：今天的改動不要再放在這個分支，照上面從最新主分支開新分支。

## 5. commit

- **只用明確路徑 `git add <檔案>`**，不用 `git add -A` / `git add .`。
- 訊息用 Conventional Commits，第一行英文、小寫開頭：`feat` 新功能、`fix` 修錯、`docs` 文件、`style` 外觀、`refactor` 重構、`test` 測試、`chore` 設定 / 套件。
- 一筆 commit 一個主題。同一個檔案混了不同主題：問使用者要合成一筆還是自己手動拆，不要自己組 patch。
- **共用檔案各自獨立一筆**，不和程式碼或日誌混在一起：
  - 日誌：`docs(journal): <username> YYYY-MM-DD`
  - 判斷點：`docs(decisions): <username> YYYY-MM-DD`（只增修相關的行，不重排整份檔案）
  - `.mailmap`：`chore: map <username> identities in .mailmap`
- 不 amend、不 rebase 已經 push 的 commit。

## 6. 同步與 push

收工時的順序固定是：**commit 程式碼 → 同步主分支 → commit 判斷點 / `.mailmap` → 寫日誌並 commit → push**。同步可能 rebase、改掉 commit hash，所以一定在寫日誌之前做，日誌記的 hash 才不會失效；日誌是最後一筆 commit。

1. 落後主分支時（先問；工作目錄有沒 commit 的改動就不同步）：分支**還沒 push 過** → `git rebase origin/<default>`；**已經 push 過** → `git merge origin/<default>`（避免 force push）。有衝突 → `--abort` 後停下來。
2. `python .claude/skills/_daily/daily.py preflight push` 列出要 push 的 commit 與掃描結果，使用者同意才 `git push -u origin <branch>`。
3. 用 PR 合併進主分支，一律 **Squash and merge**。

## 7. 同一個人有多個身分：`.mailmap`

根目錄 `.mailmap` 每行一個舊身分，左邊是要統一成的身分：

```
<正式名稱> <正式email> <舊名稱> <舊email>
```

只改顯示方式，不改寫歷史。`git shortlog -sne` 同一個人只剩一行就是對了。`/day-start` 會偵測並給建議，寫入由 `/day-end` 用獨立 commit 處理。

## 8. GitHub 分支保護（管理員設定一次，連沒啟用 hook 的人也擋得住）

Settings → Branches（或 Rules → Rulesets）對 `<default>` 勾選：Require a pull request before merging、Require linear history、Do not allow bypassing；不勾 Allow force pushes / deletions。Settings → General → Pull Requests 只開 Allow squash merging，並開 Automatically delete head branches。
