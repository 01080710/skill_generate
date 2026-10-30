# CLAUDE.md

這個專案用來設計與維護多人協作用的 Claude Code skill：每日閉環 `/day-start`（開工，只讀）與 `/day-end`（收工，只寫）。成品要能套用到任何 git 專案與協作者，不針對單一專案客製化。

## 溝通

- 一律用**繁體中文**（台灣用語）回覆與撰寫文件；程式識別碼、commit 訊息、分支名稱用英文。
- 回覆用表格與條列整理，結論先講；不要長篇敘述。
- 報告結果要具體：改了哪些檔案、怎麼測的、測試結果，沒做的也要說。

## 工作方式

1. **先討論、後實作**：需求寫「先提出選項與優缺點」「先討論方案」時，只給分析與選項，**不要直接實作或定案**。把需要我決定的事列成編號（D1、D2…），附上你的傾向與理由。
2. 我回覆決定後（例如「D1. … D2. …」），照決定直接實作到完成，不用再問一次。決定有不明確的地方（例如數量和列出的項目對不起來），照字面最合理的解讀做，並在回報裡說明。
3. 實作完要**實際驗證**再回報：在 scratchpad 建測試 repo 跑過，圖表要實際渲染過。
4. 不要為了抽象化增加不必要的架構；能用一支工具解決就不要拆成很多個。

## 設計原則

- **能用程式明確驗證的，就不要靠 AI 判斷**：狀態判斷、格式驗證、機敏掃描、git 安全檢查都寫成程式（Python 優先，搭配 git hooks），AI 只負責文字整理與對話。
- **不猜**：缺少的資訊用 AskUserQuestion 讓使用者選或填；沒得到回答就不寫、不做。工作沒有使用者確認就不能標成「已完成」。
- **讀寫分離**：`/day-start` 只讀（`git fetch` 例外）；`/day-end` 只寫自己的東西，不讀別人的日誌與記憶。
- **記憶留本機、交接寫日誌**：要讓隊友知道的事寫進日誌的「交接」段，不要只寫在本地記憶。
- **機敏資訊最高優先**：規則在 `.claude/skills/_daily/sensitive-rules.md`，日誌、commit 訊息、PR 內文都適用。

## 專案結構

```
.claude/skills/
├── day-start/SKILL.md        開工流程（只讀）
├── day-end/SKILL.md          收工流程（只寫）
├── _daily/                   兩個 skill 共用（沒有 SKILL.md，不會被當成 skill）
│   ├── daily.py              狀態、日誌、機敏掃描、commit / push 前檢查（只用標準函式庫）
│   ├── hooks/                pre-commit、commit-msg、pre-push，都轉交給 daily.py
│   ├── sensitive-rules.md    機敏資訊規則
│   └── git-workflow.md       Git 協作規範（通用版）
├── day-flow-user.md          流程圖：使用者版
└── day-flow-dev.md           流程圖：工程版
```

## 已定案的設計（改動前先確認是否要推翻）

| 項目 | 決定 |
|---|---|
| 記憶 | 只留本機；交接內容寫進日誌 |
| 工作狀態 | 四類：已完成、進行中、待處理、未決定 |
| 收集輸入 | 問卷式（AskUserQuestion），每項逐一確認狀態 |
| 日誌位置 | `docs/<project>_journal/<username>/YYYY-MM-DD.md`，跟著功能分支走，由 `daily.py journal find` 跨分支找 |
| 腳本語言 | Python 3.8+，只用標準函式庫 |
| 共用檔案 | 日誌、`docs/decisions.md`、`.mailmap` 各自獨立一筆 commit；程式碼走 PR、Squash and merge |

## Skill 撰寫慣例

- SKILL.md 用 frontmatter（`name`、`description`、`disable-model-invocation: true`），內文用編號步驟 `## 1.`、`## 2.`…，每步寫清楚「依什麼判斷、做什麼、什麼情況停下來」。
- 不寫死專案細節（主分支名稱、測試指令、備份路徑）；用「專案有 X 才做」的寫法。
- 判斷一律以 `daily.py` 的 JSON 輸出與 exit code 為準，SKILL 裡不要重寫判斷邏輯。
- 兩個 skill 共用的規則放 `_daily/`，不要在兩份 SKILL.md 各寫一次。

## Git 安全規範

細節見 `.claude/skills/_daily/git-workflow.md`。重點：

- 不在主分支 commit / push，不 force push，不用 `--no-verify` 繞過 hook。
- 只用明確路徑 `git add <檔案>`，不用 `-A` / `.`。
- 開分支、改 git config、merge / rebase、push、開 PR 都要先問使用者；衝突一律 abort 後停下來，不自己解。
- 不用 `--autostash`，不 amend / rebase 已 push 的 commit。

## 流程圖（mermaid）慣例

- **只用四個顏色**，每張圖都用同一組 classDef：
  ```
  classDef sys fill:#dbeafe,stroke:#2563eb,color:#111     藍：系統自動處理（步驟、判斷、程式檢查）
  classDef ask fill:#fef3c7,stroke:#d97706,color:#111     黃：需要使用者（回答問題、提醒）
  classDef write fill:#dcfce7,stroke:#16a34a,color:#111   綠：寫入（存檔、commit、push）
  classDef stop fill:#fee2e2,stroke:#dc2626,color:#111    紅：停止
  ```
- **錯誤或要修改、回到前面重做的線一律用虛線**（`-. 標籤 .->`），正常流程用實線。回頭的線從判斷節點拉出來，不用自我迴圈（線會拉歪、標籤會重疊）。
- 線路不能凌亂：主線由上往下一條直線，分支往旁邊岔；流程太長就拆成幾張圖，用「接 2-1」「接 2-2」串起來。
- 分**使用者版**（不出現指令與程式名稱，節點少、只講使用者會遇到什麼）與**工程版**（完整分支、指令、欄位）。
- 每份圖開頭放顏色與線條的圖例表；圖後面用表格補充狀況與處理方式。
- 寫完用 mermaid-cli 實際渲染並看過圖再交付：
  ```bash
  npx -y @mermaid-js/mermaid-cli@11.4.2 -i diagram.mmd -o diagram.png -b white
  ```

## 測試 daily.py

在 scratchpad 建 bare 遠端加兩個 clone（模擬自己和隊友），設定 `core.hooksPath .claude/skills/_daily/hooks` 後實際操作 commit / merge / push。Windows 測試時加 `GIT_CONFIG_PARAMETERS="'core.autocrlf=false'"`，避免 hook 被轉成 CRLF。至少要測：

- 會被擋下：主分支 commit、帳密、`.env`、改別人的日誌、日誌格式錯、日誌和程式碼混在同一筆、push 主分支、force push
- 不能誤擋：一般程式碼的 `token = ...`、解完衝突的 merge commit
- 偵測：分支已合併或遠端已刪除、跨分支找日誌、重疊檔案、漏寫的 commit、專案 hook 沒呼叫 `daily.py`
- 不能誤報：rebase 後才寫的日誌、merge commit、`docs(decisions)` / `.mailmap` commit 不算漏寫
