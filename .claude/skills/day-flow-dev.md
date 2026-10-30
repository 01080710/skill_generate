# Day Start / Day End 流程圖（工程版）

`/day-start`（開工，只讀）與 `/day-end`（收工，只寫）的完整流程，包含 `daily.py` 子命令、`context` 欄位、git 指令與每一個分支狀況。給維護 skill、排查問題的人看；一般使用者請看 [使用者版](day-flow-user.md)。
規則細節見 [day-start/SKILL.md](day-start/SKILL.md)、[day-end/SKILL.md](day-end/SKILL.md)、[_daily/git-workflow.md](_daily/git-workflow.md)。

## 圖例

| 顏色 | 代表 | 標記 |
|---|---|---|
| 🟦 藍 | 系統自動處理：步驟、判斷、`daily.py` 檢查 | ①② ⚙ ◇ |
| 🟨 黃 | 需要使用者：回答問題（❓），或放進摘要的提醒（⚠，流程繼續） | ❓ ⚠ |
| 🟩 綠 | 寫入：檔案、git config、commit、push | ✏ |
| 🟥 紅 | 停止，等使用者處理 | ⛔ |

| 線條 | 意思 |
|---|---|
| 實線 → | 正常往下走 |
| 虛線 ⇢ | 有錯誤或要修改，回到前面重做 |

---

## 0. 總覽

```mermaid
flowchart LR
    DS["/day-start<br/>開工（只讀）"]:::sys
    WORK["開發中<br/>手動 commit"]:::write
    DE["/day-end<br/>收工（只寫）"]:::sys
    HOOK{{"git hooks<br/>pre-commit / commit-msg / pre-push"}}:::sys
    LOG[("自己的日誌<br/>docs/{project}_journal/{username}/")]:::write
    MEM[("本地記憶<br/>只在這台電腦")]:::write

    DS --> WORK --> DE
    DE -. 隔天 .-> DS
    WORK -. 每次 commit / push .-> HOOK
    DE -. 每次 commit / push .-> HOOK
    DE -- 寫入 --> LOG
    DE -- 寫入 --> MEM
    LOG -. 讀取（含隊友的交接） .-> DS
    MEM -. 讀取（只有自己的） .-> DS

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

> 總覽裡的虛線表示「隔天 / 每次觸發 / 讀取」，不是錯誤回頭；其他圖的虛線都是錯誤回頭。

---

## 1. /day-start（只讀）

```mermaid
flowchart TD
    S0(["/day-start"]):::sys --> S1["① 身分與 repo 狀態<br/>⚙ context --fetch"]:::sys
    S1 --> D1{"身分有效？"}:::sys
    D1 -->|否| X1["⛔ 停止<br/>給 git config 指令，請使用者自己設定"]:::stop
    D1 -->|是| D2{"state / hook / fetch<br/>有異常？"}:::sys
    D2 -->|有| N1["⚠ 加入「注意」<br/>附處理指令，不執行"]:::ask
    D2 -->|無| S2
    N1 --> S2["② 多個身分<br/>⚙ identities"]:::sys

    S2 --> D3{"有其他身分<br/>且沒拒絕過？"}:::sys
    D3 -->|是| N2["⚠ 建議 .mailmap 行<br/>寫入交給 /day-end"]:::ask
    D3 -->|否| S3
    N2 --> S3["③ 自己的日誌<br/>⚙ journal find --user 自己"]:::sys

    S3 --> D4{"找到日誌？"}:::sys
    D4 -->|否| N3["⚠ 還沒有日誌"]:::ask
    D4 -->|是| S3b["解析 進行中 / 待處理 / 未決定<br/>註明日誌所在分支、日誌之後的 commit<br/>⚙ scan 機敏巡檢"]:::sys
    S3b --> D5{"🔴 命中？"}:::sys
    D5 -->|是| N4["⚠ 注意第一優先<br/>請立刻更換帳密"]:::ask
    D5 -->|否| S4
    N3 --> S4
    N4 --> S4["④ 讀本地記憶<br/>使用者習慣與 feedback"]:::sys

    S4 --> S5["⑤ 讀判斷點<br/>docs/decisions.md 待決定"]:::sys
    S5 --> S6["⑥ 隊友<br/>⚙ journal find --all ＋ overlap"]:::sys
    S6 --> D6{"有交接給我<br/>或檔案重疊？"}:::sys
    D6 -->|有| N5["⚠ 交接排進 TDL<br/>重疊檔案加入「注意」"]:::ask
    D6 -->|無| S7
    N5 --> S7["⑦ 備份檢查<br/>專案有才做，只看檔名與時間"]:::sys

    S7 --> S8["⑧ 輸出開工摘要與 TDL"]:::sys
    S8 --> Q1["❓ ⑨ 今天從哪一項開始？"]:::ask
    Q1 --> S9(["等待使用者選擇"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

### 第 ① 步可能的狀況

| 狀況（`context` 的欄位） | 放進「注意」的提醒 |
|---|---|
| `state: in-progress` | **第一優先**：有進行中的 rebase / merge / cherry-pick / revert，請先完成或放棄 |
| `state: default` / `detached` | 今天的工作要開分支 `git switch --no-track -c <username>/<主題> origin/<default>` |
| `state: gone` / `merged` | 分支已合併或遠端已刪除，從最新主分支開新分支 |
| `state: tracks-default` | upstream 指向主分支，`git branch --unset-upstream` |
| `hooks.enabled: false` | 沒有專案 hook → 設定 `core.hooksPath`；專案 hook 沒有三個都呼叫 `daily.py` → 建議補上呼叫 |
| `offline: true` | 沒有 remote → 略過隊友與遠端比對；`fetch: failed` → 離線，遠端比對都標「未更新」 |

---

## 2. /day-end（只寫）

流程比較長，分成四段。收工的 commit 順序固定為：**程式碼 → 同步主分支 → 判斷點 / `.mailmap` → 日誌（最後一筆）**。先同步再寫日誌，rebase 改掉的 hash 才不會讓日誌失效。

### 2-1 前置檢查與分支

```mermaid
flowchart TD
    E0(["/day-end"]):::sys --> P1{"找得到 Python？"}:::sys
    P1 -->|否| X0["⛔ 停止<br/>請安裝 Python 3.8+"]:::stop
    P1 -->|是| E1["① 身分、狀態、hook<br/>⚙ context --fetch"]:::sys

    E1 --> C1{"身分有效？"}:::sys
    C1 -->|否| Q1["❓ 請提供名字與 email"]:::ask
    Q1 -->|未提供| X1["⛔ 停止"]:::stop
    Q1 -->|提供| G1["✏ git config user.name / email"]:::write
    C1 -->|是| C2
    G1 --> C2{"有進行中的<br/>rebase / merge？"}:::sys
    C2 -->|是| X2["⛔ 停止<br/>請先完成或放棄"]:::stop
    C2 -->|否| C3{"hook 已啟用？"}:::sys
    C3 -->|否| Q2["❓ 要啟用 hook 嗎？<br/>沒有專案 hook → 設 core.hooksPath<br/>有專案 hook → 在裡面呼叫 daily.py"]:::ask
    C3 -->|是| C4
    Q2 --> C4{"在線？<br/>offline 是 false"}:::sys
    C4 -->|否| N1["⚠ 離線（沒有遠端或 fetch 失敗）<br/>之後不同步、不 push"]:::ask
    C4 -->|是| B1
    N1 --> B1{"② 分支 state"}:::sys

    B1 -->|own / new| K1["沿用目前分支"]:::sys
    B1 -->|default / detached| Q3["❓ 選分支名稱"]:::ask
    B1 -->|gone / merged| Q4["❓ 選分支名稱"]:::ask
    B1 -->|tracks-default| Q5["❓ 要 unset-upstream 嗎？"]:::ask
    Q3 --> G2["✏ git switch -c 名稱"]:::write
    Q4 --> G3["✏ git switch --no-track -c 名稱 origin/default"]:::write
    G2 --> C5{"切換成功？"}:::sys
    G3 --> C5
    C5 -->|否| X3["⛔ 停止<br/>改動和主分支衝突，請使用者決定"]:::stop
    C5 -->|是| NX
    K1 --> NX
    Q5 --> NX(["接 2-2"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

### 2-2 問卷與 commit 程式碼

```mermaid
flowchart TD
    F0(["接 2-1"]):::sys --> E3["③ 跑測試<br/>N passed / N failed・無自動測試・未執行"]:::sys
    E3 --> E4["④ 整理候選項目（草稿）<br/>⚙ journal find --user 自己<br/>上次未完事項 ＋ 新 commit ＋ 未 commit 改動 ＋ 對話"]:::sys

    E4 --> Q1["❓ ⑤-1 每項狀態（每次最多 4 題）<br/>已完成・進行中・待處理・未決定<br/>測試失敗或未實測的不提供「已完成」"]:::ask
    Q1 --> D1{"❓ ⑤-2 還有漏掉的？"}:::ask
    D1 -. 有，補上 .-> Q1
    D1 -->|沒有了| Q2["❓ ⑤-3 下次起點・問題與解法<br/>交接・已拍板的決定"]:::ask

    Q2 --> W1["✏ ⑥ 更新本地記憶"]:::write
    W1 --> Q3["❓ ⑦ 每組未 commit 的改動<br/>現在 commit 還是先保留？"]:::ask
    Q3 --> C6{"保留的改動<br/>被標成「已完成」？"}:::sys
    C6 -.->|是| R1["❓ 重新問那幾項的狀態<br/>只給 進行中・待處理・未決定"]:::ask
    C6 -->|否| S1
    R1 --> S1["⚙ commit 前檢查<br/>git add 明確路徑 → preflight commit<br/>＋ scan commit 訊息"]:::sys
    S1 --> D2{"通過？"}:::sys
    D2 -.->|否| FX1["修正 errors 或改寫訊息"]:::ask
    FX1 -. 修正後重跑 .-> S1
    D2 -->|是| G1["✏ commit 程式碼（依主題分批）<br/>hash 先不寫進日誌"]:::write
    G1 --> NX(["接 2-3"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

### 2-3 同步主分支、共用檔與日誌

```mermaid
flowchart TD
    H0(["接 2-2"]):::sys --> C1{"⑧ 在線而且<br/>落後主分支？"}:::sys
    C1 -->|否| SH
    C1 -->|是| C2{"還有沒 commit 的改動？"}:::sys
    C2 -->|有| N1["⚠ 不同步<br/>不用 autostash，寫進摘要"]:::ask
    C2 -->|沒有| Q1{"❓ 要同步嗎？"}:::ask
    N1 --> SH
    Q1 -->|先不同步| SH
    Q1 -->|同步| C3{"分支 push 過？"}:::sys
    C3 -->|沒有| G1["✏ git rebase origin/default"]:::write
    C3 -->|有| G2["✏ git merge origin/default"]:::write
    G1 --> C4{"有衝突？"}:::sys
    G2 --> C4
    C4 -->|有| X1["⛔ abort<br/>回報衝突檔案後停止"]:::stop
    C4 -->|沒有| T1["有自動測試就重跑<br/>更新 tests 結果"]:::sys
    T1 --> SH{"⑨ 有拍板的決定<br/>或確認過的 .mailmap？"}:::sys

    SH -->|有| G3["✏ 各自獨立一筆 commit<br/>docs(decisions) ・ chore: .mailmap"]:::write
    SH -->|無| W2
    G3 --> W2["✏ ⑩ 寫日誌（hash 用同步後的值）<br/>同一天已有就接一段新的「收工 HH:MM」"]:::write
    W2 --> Q4{"❓ 預覽全文：寫入？"}:::ask
    Q4 -. 要修改 .-> W2
    Q4 -->|寫入| S2["⚙ ⑪ validate → coverage → scan"]:::sys
    S2 --> D3{"檢查結果"}:::sys
    D3 -.->|格式錯 / 🔴| FX2["修正日誌"]:::ask
    FX2 -. 修正後重跑 .-> S2
    D3 -.->|漏寫 commit / 🟡| Q5["❓ 補進日誌？<br/>改寫還是保留原句？"]:::ask
    Q5 -. 處理後重跑 .-> S2
    D3 -->|全部通過| G4["✏ commit 日誌（最後一筆）<br/>docs(journal): username 日期"]:::write
    G4 --> NX(["接 2-4"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

### 2-4 push 與收尾

```mermaid
flowchart TD
    K0(["接 2-3"]):::sys --> O1{"離線？"}:::sys
    O1 -->|是| BK
    O1 -->|否| P1["⚙ ⑫ preflight push ＋ overlap"]:::sys
    P1 --> C5{"通過？"}:::sys
    C5 -.->|否| X2["⛔ 停止<br/>回到 2-2 修正還沒 push 的 commit"]:::stop
    C5 -->|是| Q2{"❓ 要 push 嗎？<br/>列出 commit、掃描結果、重疊檔案"}:::ask
    Q2 -->|先不 push| BK
    Q2 -->|push| G3["✏ git push -u origin 分支<br/>pre-push hook 會再檢查"]:::write
    G3 --> Q3{"❓ 要開 PR 嗎？"}:::ask
    Q3 -->|否| BK
    Q3 -->|是| G4["⚙ scan PR 內文<br/>✏ gh pr create 或給連結"]:::write
    G4 --> BK["⑬ 備份<br/>專案有備份指令才做"]:::sys
    BK --> SUM(["⑭ 收工摘要"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

---

## 3. Git hooks（手動 commit / push 也會檢查）

```mermaid
flowchart LR
    A1["git commit"]:::write --> H1["⚙ pre-commit"]:::sys
    H1 --> R1{"merge / rebase<br/>進行中？"}:::sys
    R1 -->|是| K1["只擋禁止檔案<br/>別人帶進來的改動不檢查"]:::sys
    R1 -->|否| R2{"主分支？禁止檔案？<br/>別人的日誌？日誌格式錯？<br/>🔴 帳密？共用檔混在一起？"}:::sys
    R2 -->|有任一| X1["⛔ 擋下 commit"]:::stop
    R2 -->|都沒有| H2
    K1 --> H2["⚙ commit-msg"]:::sys
    H2 --> R3{"訊息有 🔴？"}:::sys
    R3 -->|有| X2["⛔ 擋下 commit"]:::stop
    R3 -->|沒有| OK1(["commit 完成<br/>🟡 只提醒"]):::sys

    A2["git push"]:::write --> H3["⚙ pre-push"]:::sys
    H3 --> R4{"push 到主分支？<br/>非 fast-forward（force）？<br/>要 push 的 commit 有 🔴？"}:::sys
    R4 -->|有任一| X3["⛔ 擋下 push"]:::stop
    R4 -->|都沒有| OK2(["push 完成"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

> 被擋下時照錯誤訊息修正，**不要用 `--no-verify` 繞過**。沒有啟用 hook 時，`/day-end` 每次 commit 前會手動跑同樣的檢查（`preflight commit` ＋ 掃 commit 訊息）。沒衝突、自動完成的 `git merge` 不會經過 pre-commit；在主分支上 merge 的結果會在 push 時被 pre-push 擋下。

---

## 4. 所有停止點（⛔）一覽

| 在哪 | 狀況 | 使用者要做的事 |
|---|---|---|
| day-start ① | git 身分未設定，或是電腦自動產生的 email | 自己執行 `git config user.name / user.email` |
| day-end 開頭 | 找不到 Python | 安裝 Python 3.8+ |
| day-end ① | 不提供名字或 email | 提供後重跑 |
| day-end ① | 有進行中的 rebase / merge | 完成（`--continue`）或放棄（`--abort`） |
| day-end ② | 開新分支時，改動和主分支衝突 | 決定怎麼處理改動（例如自己 stash） |
| day-end ⑧ | 同步主分支時有衝突（已自動 abort） | 手動解衝突，或這次先不同步 |
| day-end ⑫ | 要 push 的 commit 有 🔴 或違反規則 | 修正還沒 push 的 commit 後重跑 |
| hook | commit / push 被擋 | 照錯誤訊息修正 |
