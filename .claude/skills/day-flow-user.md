# 開工 / 收工 怎麼用（使用者版）

每天開始打 `/day-start`，結束打 `/day-end`。大部分檢查 Claude 會自動做，你只需要在**黃色**的地方回答問題。
想看完整的技術細節，請看 [工程版](day-flow-dev.md)。

| 顏色 | 意思 |
|---|---|
| 🟦 藍 | Claude 自動處理，你不用做事 |
| 🟨 黃 | 輪到你：回答問題，或看一下提醒 |
| 🟩 綠 | 會存檔或送出（日誌、commit、push） |
| 🟥 紅 | 停下來，要你先處理 |

| 線條 | 意思 |
|---|---|
| 實線 → | 正常往下走 |
| 虛線 ⇢ | 有錯誤或要修改，回到前面重做 |

---

## 一天的流程

```mermaid
flowchart LR
    A(["/day-start<br/>開工"]):::sys --> B["照待辦清單工作"]:::write --> C(["/day-end<br/>收工"]):::sys
    C -. 隔天 .-> A

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

---

## 開工 `/day-start`

只會讀資料，**不會改動任何東西**。

```mermaid
flowchart TD
    A(["/day-start"]):::sys --> B{"git 身分<br/>設定好了嗎？"}:::sys
    B -->|沒有| X["🟥 停下來<br/>照提示設定名字與 email"]:::stop
    B -->|有| C["讀回你上次做到哪"]:::sys
    C --> D["看隊友有沒有交接給你<br/>有沒有人在改同一個檔案"]:::sys
    D --> E["⚠ 開工摘要<br/>今日待辦 ＋ 要注意的事"]:::ask
    E --> F["❓ 今天從哪一項開始？"]:::ask
    F --> G(["開始工作"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

**摘要裡可能出現的提醒**（看到再照著做就好）：

- 你在主分支上，或分支已經合併 → 建議開新分支（附指令）
- 有做到一半的 rebase / merge → 先完成或放棄
- 隊友交接了事情給你 → 已排進待辦
- 隊友也在改同一個檔案 → 動手前先和對方確認
- 日誌裡疑似有密碼或個資 → 照提示處理

---

## 收工 `/day-end`

```mermaid
flowchart TD
    A(["/day-end"]):::sys --> B{"可以開始收工嗎？"}:::sys
    B -->|不行| X1["🟥 停下來<br/>身分未設定，或有做到一半的 rebase / merge"]:::stop
    B -->|可以| C["❓ 確認分支<br/>需要開新分支時讓你選名稱"]:::ask
    C --> D["跑測試，整理這次做了什麼"]:::sys
    D --> E["❓ 逐項確認狀態<br/>已完成・進行中・待處理・未決定"]:::ask
    E --> E2{"❓ 還有漏掉的？"}:::ask
    E2 -. 有，補上 .-> E
    E2 -->|沒有了| F["❓ 補充：下次從哪開始<br/>遇到的問題・要交接給誰・做了什麼決定"]:::ask
    F --> G["❓ 確認要 commit 哪些改動"]:::ask
    G --> C1{"自動檢查<br/>改動與 commit 訊息"}:::sys
    C1 -. 有問題，修正 .-> G
    C1 -->|通過| I1["commit 程式碼"]:::write
    I1 --> J["❓ 要同步主分支嗎？"]:::ask
    J --> H["❓ 預覽日誌<br/>可要求修改，確認後存檔"]:::ask
    H --> V{"自動檢查<br/>日誌格式・密碼與個資"}:::sys
    V -. 有問題，修正 .-> H
    V -->|通過| I2["commit 日誌"]:::write
    I2 --> K["❓ 要 push、開 PR 嗎？"]:::ask
    K --> L(["收工摘要"]):::sys

    classDef sys fill:#dbeafe,stroke:#2563eb,color:#111
    classDef ask fill:#fef3c7,stroke:#d97706,color:#111
    classDef write fill:#dcfce7,stroke:#16a34a,color:#111
    classDef stop fill:#fee2e2,stroke:#dc2626,color:#111
```

**你會被問到的問題**：

| 問題 | 怎麼回答 |
|---|---|
| 每一項工作的狀態 | 從四個選項選一個；項目寫得不對可以在「Other」改寫，或說「刪除」 |
| 還有沒列到的工作嗎 | 有就在「Other」補上項目與狀態 |
| 下次從哪開始、問題與解法、交接、決定 | 從選項選，或自己寫；沒有就選「無」 |
| commit / 同步 / push / 開 PR | 不同意的話 Claude 就不會做 |

**沒選「已完成」，就不會被記成完成。** 測試沒過的項目，選項裡不會出現「已完成」；選了「先保留不 commit」的改動，如果之前標成「已完成」，會再問一次狀態。

沒有遠端（或連不上）時，收工只會在本機 commit，跳過同步與 push。

---

## 什麼時候會停下來

| 狀況 | 你要做的事 |
|---|---|
| git 身分沒設定 | 提供名字與 email |
| 電腦沒有 Python | 安裝 Python 3.8 以上 |
| 有做到一半的 rebase / merge | 完成或放棄後再執行一次 |
| 同步主分支時有衝突 | Claude 已經還原，請自己解衝突，或這次先不同步 |
| 內容疑似有密碼或金鑰 | 照提示改寫；密碼已經 push 出去的話，請立刻更換 |
| commit 或 push 被擋下 | 看錯誤訊息修正（例如不能在主分支 commit、不能改別人的日誌） |
