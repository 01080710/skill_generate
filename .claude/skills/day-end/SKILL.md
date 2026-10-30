---
name: day-end
description: 每天收工：確認 git 身分與分支、用問卷確認每項工作的狀態、寫個人日誌（已完成 / 進行中 / 待處理 / 未決定 / 問題與解法 / 交接）、整理本地記憶、更新判斷點，在自己的分支上依主題 commit，同步與 push 都先問。只在使用者輸入 /day-end 時執行。
disable-model-invocation: true
---

# 收工（/day-end）

目的：把這次的進度、決定、交接與還沒收的事記下來，讓下次的 `/day-start`（自己和隊友）接得上；並確保程式碼、資料與使用者習慣都有保存。

這份流程適用任何 git 專案；專案自己的規範若有文件（例如 `docs/git-workflow.md`）就以文件為準，否則照 `.claude/skills/_daily/git-workflow.md`。

## 0. 工具與規則

- `<daily>` = `<py> .claude/skills/_daily/daily.py`（在 repo 根目錄執行）。`<py>`：依序試 `python3`、`python`、`py`，取第一個 `<名稱> -c ""` 成功的。找不到 Python → **停下來**，請使用者安裝 Python 3.8+（commit 前的檢查都靠它）。
- 判斷一律以 `<daily>` 的 JSON 與 exit code 為準，不要自己重算或略過；它擋下（exit 非 0）就照 `errors` 修正，**不要用 `--no-verify` 繞過 hook**。
- **只寫自己的東西，不讀別人的日誌與記憶**：不要執行 `journal find --all`、`identities`，不打開 `<journal>` 底下別人的資料夾。只讀必要的 git 狀態與自己的日誌。
- **不猜**：要使用者提供或確認的資訊一律用 AskUserQuestion 問（每次最多 4 題、每題 2–4 個選項，使用者可從「Other」自己寫）；沒得到回答就不寫、不做。
- **機敏資訊**：照 `.claude/skills/_daily/sensitive-rules.md`。日誌、判斷點、commit 訊息、PR 內文都要遵守；整理對話時只抽出「做了什麼」，不抄對話裡的資料（查詢結果、截圖文字、log、使用者貼上的內容）。

## 1. 身分、repo 狀態與 hook

執行 `<daily> context --fetch`：

- `user.valid` 是 false → **停下來**，請使用者提供「名字」與「email」。拿到後告訴他要執行的指令，再執行 `git config user.name "<名字>"`、`git config user.email "<email>"`（只設在這個 repo）。沒提供就停在這裡。
- `state: in-progress` → **停下來**，回報是哪一種操作（`in_progress`），請使用者先完成或放棄。不要開分支、不要 commit。
- `hooks.enabled` 是 false → 用 AskUserQuestion 問要不要啟用：
  - `project_githooks` 是 false → `git config core.hooksPath <hooks.daily_hooks>`
  - `project_githooks` 是 true（專案有自己的 hook，但沒有三個都呼叫 `daily.py`）→ 建議在專案的 `pre-commit`、`commit-msg`、`pre-push` 裡呼叫 `daily.py`（寫法照 `.claude/skills/_daily/hooks/`），使用者同意才改；不要直接把 `core.hooksPath` 換掉，那會停用專案原本的 hook。
  - 不啟用也照樣繼續：第 7、9、11 步每次 commit 前都會手動跑同樣的檢查（`preflight commit` ＋ 掃 commit 訊息），第 12 步 push 前跑 `preflight push`。
- `offline` 是 true（沒有 remote，或 `fetch: failed`）→ 離線：第 8、12 步跳過，只在本機 commit；摘要寫明是「沒有遠端」還是「fetch 失敗」。

## 2. 確認分支（不得在主分支上 commit）

依 `state`：

| state | 做法 |
|---|---|
| `own` / `new` | 沿用目前分支 |
| `default` / `detached` | 要開新分支 |
| `gone` / `merged` | 分支已合併或遠端已刪除，今天的改動不能再放在這裡 → 要從最新主分支開新分支 |
| `tracks-default` | upstream 指向主分支 → 問使用者是否執行 `git branch --unset-upstream`，之後沿用 |

要開新分支時，用 AskUserQuestion 提 2–3 個名稱讓使用者選（`<username>/<主題>`，主題英文小寫加連字號，依今天的主要工作命名），選定後：
- `default` / `detached`：`git switch -c <名稱>`（沒 commit 的改動會跟著帶過去）
- `gone` / `merged`：`git switch --no-track -c <名稱> origin/<default>`（一定要 `--no-track`，否則 upstream 會被設成主分支）
- 切不過去（改動和主分支衝突）→ 停下來回報，請使用者決定。

不論哪種，都不要 checkout / reset / stash / 丟掉使用者的改動。

## 3. 跑測試

依專案而定（看 README、CLAUDE.md、`pyproject.toml`、`package.json`）：Python 專案 `<py> -m pytest`，Node 專案 `npm test`。結果記成 `N passed / N failed`；找不到測試寫「無自動測試」；使用者說這次不跑就寫「未執行」。測試沒過照樣可以收工，但日誌與回報都要寫明。

## 4. 整理這次的工作項目（草稿，還不寫入）

工作常常跨過午夜，所以**不用「今天 00:00」切，而是從「上一份日誌之後」開始算**：

1. `<daily> journal find --user <username>`（只查自己）：
   - 上一份日誌的 `sections` 裡「進行中」「待處理」「未決定」→ **全部列為候選**，避免沒做完的事在這次消失。
   - `commits_after` → 這次的 commit。
   - 沒有日誌 → 用 `git log --branches --remotes --no-merges --use-mailmap --author=<email> --since="7 days ago" --format='%h %ad %s'`，並問使用者從哪天開始算。
2. 加上 `git status --porcelain`、`git diff --stat` 的未 commit 改動，以及對話裡做過、但 git 看不到的（只討論沒實作、評估後不做、改了 git 以外的設定）。
3. 合併成一份候選清單，一項一句，依機敏規則改寫好，附上依據（commit hash / 未 commit / 上次的待處理 / 對話）。

## 5. 問卷確認（AskUserQuestion，沒確認的不寫）

1. **每一項的狀態**：一題一項，每次最多 4 題，分批問到全部問完。
   - 題目：「<項目>」（依據：…）目前的狀態？　header：「項目 N」
   - 選項固定四個：**已完成**（做完而且驗證過）、**進行中**（做到一半）、**待處理**（還沒開始）、**未決定**（要拍板才能往下）
   - 和失敗測試有關、或還沒實測的項目：**不提供「已完成」**，在題目裡說明原因。
   - 使用者從 Other 改寫項目文字就照他的寫；說「刪除」就拿掉。
2. **有沒有漏掉的**：「還有沒列到的工作嗎？」選項「沒有了」/「有（在 Other 寫：項目＋狀態）」，有就重複到選「沒有了」。
3. **其他欄位**（一次問完，最多 4 題）：
   - 「下次從哪一項開始？」選項：進行中 / 待處理裡的前 3 項。
   - 「這次遇到的問題與解法？」（multiSelect）選項：「無」＋最多 3 個從對話整理的「問題→解法」。
   - 「有要交接給誰的嗎？」選項：「無」＋最多 2 個從對話整理的候選；Other 寫「對象｜內容」（對象寫 username，或「全體」）。
   - 「這次有拍板的決定嗎？」（multiSelect）選項：「無」＋最多 3 個對話裡使用者明確做的決定。**不要把 Claude 的建議當成選項。**
4. 狀態是「未決定」的項目，整理成「問題｜選項 A / B｜Claude 的建議」，在第 10 步的預覽裡一起給使用者確認。

## 6. 整理本地記憶

記憶在 Claude 的本地記憶資料夾（系統提示 Memory 段落指定的路徑），不進版控，只存在這台電腦，**也不和隊友共享**——要讓隊友知道的事寫進日誌的「交接」，不要只寫在記憶裡。依系統提示的記憶規則（一檔一事、frontmatter、`MEMORY.md` 索引）操作：

- 從這次的對話整理出值得留下的：使用者的做事習慣與偏好、給過的修正或認可（`feedback`，附 **Why** 與 **How to apply**）、repo 裡查不到的專案背景（`project`，日期寫絕對日期）、外部資源位置（`reference`）。
- 維護 `user-<username>.md`（`type: user`）：這個人的角色、習慣、偏好與設定（例如 `.mailmap` 是否已拒絕），用 `[[名稱]]` 連到相關的 feedback 記憶；`/day-start` 會讀它。
- 先找有沒有已經涵蓋的記憶：有就**更新**，不要重複建立；錯誤或過時的就**刪除**，並同步更新 `MEMORY.md`。
- 不記：程式結構、git 歷史、日誌已經寫的進度。記憶同樣適用機敏規則：不記帳密、個人資料、業務資料。

## 7. commit 程式碼（依主題分批）

1. 剩下沒 commit 的改動，依主題分組列給使用者，用 AskUserQuestion 問每組「現在 commit」或「先保留不 commit」。
   - 選了「先保留」的組，對應的項目在第 5 步被標成「已完成」→ **重新問那幾項的狀態**（只給「進行中」「待處理」「未決定」三個選項），以新答案為準。沒有 commit 的工作不能記成完成。
2. 每個主題一筆：**只用明確路徑 `git add <檔案>`**（不用 `-A` / `.`），然後做「commit 前檢查」，通過才 commit。
   - 同一個檔案混了不同主題 → 問使用者「合成一筆」或「我自己手動拆」，不要自己組 patch。
   - 訊息用 Conventional Commits（`feat` / `fix` / `docs` / `style` / `refactor` / `test` / `chore`），第一行英文、小寫開頭，需要時內文說為什麼，結尾加上系統提示指定的 Co-Authored-By。
3. 先不要把 commit hash 寫進任何地方：第 8 步同步時可能會 rebase，hash 會變。

**commit 前檢查**（第 7、9、11 步的每一筆 commit 都要做，不論 hook 有沒有啟用）：
1. `<daily> preflight commit` → `ok` 是 false 就照 `errors` 修正後重跑。
2. 把完整的 commit 訊息餵進 `<daily> scan --file -`（例如 `printf '%s\n' "<訊息>" | <daily> scan --file -`）→ 🔴 就改寫訊息；🟡 照機敏規則處理。
3. 都通過才 `git commit`（hook 會再檢查一次，被擋就照訊息修正，不要 `--no-verify`）。

## 8. 同步主分支（先問；在寫日誌之前做）

**為什麼放在這裡**：同步可能 rebase，rebase 會改掉 commit hash；先同步再寫日誌，日誌記的 hash 才是最終版本。也不能更早做——第 7 步之前工作目錄一定有沒 commit 的改動，而規則不允許 autostash。

離線（第 1 步 `offline` 是 true）或 `behind_default`（第 1 步）是 0 → 跳過。否則：

1. 工作目錄還有沒 commit 的改動（第 7 步選了「先保留」）→ **不同步**（不用 `--autostash`），在摘要說明。
2. 用 AskUserQuestion 問：「先不同步」/「同步」，並說明方式——`pushed` 是 false（還沒 push 過）用 `git rebase origin/<default>`；true 用 `git merge origin/<default>`（避免 force push）。
3. 有衝突 → `git rebase --abort` / `git merge --abort`，回報衝突的檔案，**停下來**讓使用者決定，不要自己解。
4. 同步成功而且專案有自動測試 → 重跑一次，用新的結果寫日誌的 `tests`（主分支帶進來的改動也要驗證）。

## 9. 共用檔案：判斷點與 `.mailmap`（各自獨立一筆 commit，在日誌之前）

放在日誌之前 commit，日誌才會是這次收工的最後一筆；這兩種 commit 不需要寫進日誌（`coverage` 與 `/day-start` 會自動略過）。

- **判斷點**（專案有 `docs/decisions.md` 才做）：第 5 步拍板的決定 → 加到「已決定」最上面 `- YYYY-MM-DD｜決定內容｜理由`；這次提出、還沒決定、而且會影響其他人的 → 加到「待決定」；「待決定」裡這次已決定的 → 移到「已決定」。只增修相關的行，不重排整份檔案。`<daily> scan --file docs/decisions.md` 後 `git add docs/decisions.md` → 「commit 前檢查」→ `docs(decisions): <username> YYYY-MM-DD`。
- **`.mailmap`**：只有使用者在這次對話明確確認了要合併的身分（例如 `/day-start` 給的建議）才寫，已有就加在後面、不重複 → 「commit 前檢查」→ `chore: map <username> identities in .mailmap`。使用者拒絕 → 在第 6 步把「`.mailmap`：使用者已拒絕（日期）」記進 `user-<username>.md`。

## 10. 寫日誌 `<journal><username>/YYYY-MM-DD.md`

- 日期用**收工當下的日期**；涵蓋的工作跨了不同日期時，frontmatter 加 `covers: <最早日期> ~ <今天>`。
- 每人一個資料夾，**只寫自己的**（pre-commit 會擋別人的路徑）。
- commit hash 用**現在**的值（`git log --format='%h %s' origin/<default>..HEAD`），第 8 步之後 hash 不會再變。
- 同一天已有檔案（收工兩次）→ **接在最後面**加一段新的 `## 收工 HH:MM`，frontmatter 的 `branch`、`tests` 改成最新狀態；不要改前一段。這個檔案只存在其他分支時（第 4 步 `source` 不是 `worktree`），先 `git show <commit>:<path>` 取出原內容再接在後面，不要另起一份。同一天的舊格式檔案 → 問使用者要轉成新格式，還是保留舊內容、新內容另起一段。

格式（`<daily> journal validate` 會檢查，段落一個都不能少，沒有就寫「- 無」）：

```markdown
---
date: YYYY-MM-DD
covers: YYYY-MM-DD ~ YYYY-MM-DD
user: <username>
branch: <branch>
tests: N passed / N failed
---
# YYYY-MM-DD 開發日誌

## 收工 HH:MM

**下次從這裡開始**：一句話，具體到可以直接動手

### ✅ 已完成
- 做了什麼、為什麼（主要檔案；有 commit 附短 hash）
- 決定：…（這次拍板的決定）
### 🔵 進行中
- 做到一半的，寫到哪裡、下一步是什麼
### 🟡 待處理
1. 依優先順序，還沒開始的
### 🔴 未決定
- 問題｜選項 A / B｜Claude 的建議
### 🧩 問題與解法
- 問題｜解法
### 🤝 交接
- 對象（username 或「全體」）｜內容
```

寫法規則：
- 每一項都要來自第 5 步使用者確認過的答案，狀態放對段落；沒確認的不寫。第 7 步選了「先保留不 commit」的改動，對應的項目不能放在「已完成」。
- 一項一行，不寫段落；`covers` 只有跨日時才寫。
- 寫完把**全文**給使用者看，用 AskUserQuestion 問「寫入」或「要修改（在 Other 說明）」，確認後才存檔。

## 11. 檢查並 commit 日誌

1. `<daily> journal validate <檔案>` → 有 `errors` 就修正到通過；`warnings`（例如測試失敗卻沒有進行中 / 待處理）要告訴使用者。
2. `<daily> journal coverage <檔案>` → `missing` 是這次 commit 了但日誌沒提到的（已自動略過 merge 與日誌 / 判斷點 / `.mailmap` 的 commit），用 AskUserQuestion 問每筆「補進日誌」或「不用寫」。
3. `<daily> scan --file <檔案>`，再人工讀一遍全文：
   - 🔴 → 改寫或刪除，不能 commit。
   - 🟡 或人工讀到的 → 列出原句與改寫後的句子，用 AskUserQuestion 逐條問「改寫」或「保留原句」。
4. `git add <檔案>`（只有這個檔案）→ 「commit 前檢查」→ `git commit -m "docs(journal): <username> YYYY-MM-DD"`（日誌獨立一筆，是這次收工的最後一筆 commit）。

## 12. push 與 PR（先問）

離線（第 1 步 `offline` 是 true）就跳過，摘要寫「未 push（沒有遠端 / fetch 失敗）」。

1. `<daily> preflight push`：`commits` 是要 push 的 commit，`scan` 是掃描結果；`ok` 是 false 就照 `errors` 處理（🔴 → 回到前面修正還沒 push 的 commit；已 push 的不要改寫）。
2. `<daily> overlap`：有 `overlaps` 就告訴使用者哪些分支也改了同樣的檔案（只提醒）。
3. 用 AskUserQuestion 問「push」或「先不 push」，列出分支、commit 與掃描結果；同意才 `git push -u origin <branch>`（pre-push hook 會再檢查一次：不 push 主分支、不 force push）。
4. push 完問要不要開 PR（合併方式 **Squash and merge**）。PR 標題與內文先 `<daily> scan --file -`（從 stdin 餵進去）。`gh auth status` 已登入就 `gh pr create --base <default>`（內文結尾加上系統提示指定的 PR 標示）；沒登入就給連結 `https://github.com/<owner>/<repo>/compare/<default>...<branch>?expand=1`。

## 13. 資料備份（專案有備份指令才做）

- README、CLAUDE.md 有資料備份指令才做，沒有就跳過並說明。
- 執行前先確認要備份的檔案**存在**（有些備份程式開不存在的資料庫會建一個空的）。
- 回報新備份的檔名；確認備份資料夾在 `.gitignore` 裡。

## 14. 收工摘要

```
## 收工 YYYY-MM-DD · <username>（分支：<branch>）
✅ **完成**：N 項　🔵 **進行中**：N 項　🟡 **待處理**：N 項　🔴 **未決定**：N 項
**下次從這裡開始**：…
**交接**：N 則（給誰）
**記憶**：新增 N / 更新 N / 刪除 N
**日誌**：<journal><username>/YYYY-MM-DD.md（涵蓋 YYYY-MM-DD ~ YYYY-MM-DD）
**git**：N 筆 commit、同步（rebase / merge / 未同步：原因）、push（已 push / 未 push：使用者選擇 / 離線）、PR 連結；和其他分支重疊的檔案（有才寫）
**測試**：N passed / N failed（或「無自動測試」「未執行」）
**機敏檢查**：🔴 0 / 🟡 N（改寫 N 句、使用者確認保留 N 句）
**備份**：<備份檔名或「專案無備份指令」>
```
