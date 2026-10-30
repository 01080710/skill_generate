#!/usr/bin/env python3
"""daily.py 與 git hooks 的失敗場景回歸測試。

用假資料在暫存資料夾建立 bare 遠端與多個 clone（模擬自己與隊友），逐一跑「會出錯 / 應該被擋 / 不該誤擋」
的情境，最後輸出 Markdown 報告。不會碰到你的真實 repo 與 git 設定（全域與系統設定都被隔離）。

  python .claude/skills/_daily/test_daily.py [--report 報告路徑] [--keep]
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
J = "docs/proj_journal/"
SCENARIOS = []

# 假金鑰在執行時才組出來，這個檔案本身才不會被掃描器擋下
FAKE = {
    "aws": "AKIA" + "FAKE" * 4,
    "gh": "ghp_" + "Fake0" * 8,
    "pem": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "pw": "Fak3" + "Passw0rd",
    "url": "postgres://" + "admin:" + "Fak3Pass" + "@db.acme.test/app",
}


def scenario(group, sid, name, expect):
    def deco(fn):
        SCENARIOS.append((group, sid, name, expect, fn))
        return fn
    return deco


# ---------- 測試環境 ----------

class Lab:
    def __init__(self, base):
        self.base, self.n = base, 0
        gc = os.path.join(base, "empty.gitconfig")
        open(gc, "w").close()
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=gc, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")

    def run(self, cwd, *cmd, input=None, env=None):
        return subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", input=input, env=env or self.env)

    def new(self, hooks=True, remote=True):
        """建立 repo：main 上有 init commit（含 _daily），切到 test.user/feat"""
        self.n += 1
        d = os.path.join(self.base, "s%03d" % self.n)
        os.makedirs(d)
        bare = os.path.join(d, "proj.git")
        me = os.path.join(d, "me")
        if remote:
            self.run(d, "git", "init", "-q", "--bare", "-b", "main", bare)
            self.run(d, "git", "clone", "-q", bare, me)
        else:
            self.run(d, "git", "init", "-q", "-b", "main", me)
        r = Repo(self, me, bare, d)
        r.ident("Test User", "test.user@acme.test")
        shutil.copytree(HERE, os.path.join(me, ".claude", "skills", "_daily"),
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
        r.write("a.txt", "a\n")
        r.git("add", ".")
        r.git("commit", "-q", "-m", "init")
        if remote:
            r.git("push", "-q", "origin", "main")
            r.git("remote", "set-head", "origin", "-a")
        if hooks:
            r.git("config", "core.hooksPath", ".claude/skills/_daily/hooks")
        r.git("switch", "-q", "-c", "test.user/feat")
        return r


class Repo:
    def __init__(self, lab, path, bare, d):
        self.lab, self.path, self.bare, self.d = lab, path, bare, d

    def git(self, *a, **k):
        return self.lab.run(self.path, "git", *a, **k)

    def daily(self, *a, input=None):
        r = self.lab.run(self.path, sys.executable, ".claude/skills/_daily/daily.py", *a, input=input)
        try:
            data = json.loads(r.stdout)
        except ValueError:
            data = None
        return r.returncode, data

    def ident(self, name, email):
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)

    def write(self, rel, text):
        p = os.path.join(self.path, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def commit(self, files, msg, verify=True):
        for k, v in files.items():
            self.write(k, v)
        self.git("add", "--", *files)
        return self.git("commit", "-q", "-m", msg, *([] if verify else ["--no-verify"]))

    def clone(self, user, name, email):
        p = os.path.join(self.d, user)
        self.lab.run(self.d, "git", "clone", "-q", self.bare, p)
        r = Repo(self.lab, p, self.bare, self.d)
        r.ident(name, email)
        r.git("config", "core.hooksPath", ".claude/skills/_daily/hooks")
        return r

    def head(self):
        return self.git("log", "-1", "--format=%h").stdout.strip()


def journal(user="test.user", date="2026-10-30", branch="test.user/feat", tests="無自動測試", blocks=None, **sec):
    out = ["---", "date: " + date, "user: " + user, "branch: " + branch, "tests: " + tests, "---", "# %s 開發日誌" % date, ""]
    for t, s in blocks or [("18:00", sec)]:
        out += ["## 收工 " + t, "", "**下次從這裡開始**：" + s.get("next", "繼續做下一步"), ""]
        for title, key in (("✅ 已完成", "done"), ("🔵 進行中", "doing"), ("🟡 待處理", "todo"),
                           ("🔴 未決定", "undecided"), ("🧩 問題與解法", "issues"), ("🤝 交接", "handoff")):
            out.append("### " + title)
            out += ["- " + x for x in s.get(key, ["無"])]
        out.append("")
    return "\n".join(out) + "\n"


def blocked(r, word=""):
    return r.returncode != 0 and word in r.stderr, "exit=%d %s" % (r.returncode, last_line(r.stderr))


def allowed(r):
    return r.returncode == 0, "exit=%d %s" % (r.returncode, last_line(r.stderr) or "（無訊息）")


def last_line(s):
    ls = [l.strip() for l in s.strip().splitlines() if l.strip()]
    return ls[0] if ls else ""


def validate(r, text, name="test.user/2026-10-30.md"):
    r.write(J + name, text)
    code, d = r.daily("journal", "validate", J + name)
    f = list(d["files"].values())[0]
    return code, f["errors"], f["warnings"]


def has(errors, word):
    hit = [e for e in errors if word in e]
    return bool(hit), hit[0] if hit else ("、".join(errors) or "無錯誤")


# ---------- A 身分與環境 ----------

G = "A 身分與環境"


@scenario(G, "A1", "git email 沒設定", "valid=false，流程停下要求設定")
def _(lab):
    r = lab.new()
    r.git("config", "user.email", "")
    _, d = r.daily("context")
    return d["user"]["valid"] is False, "valid=%s" % d["user"]["valid"]


@scenario(G, "A2", "email 是電腦自動產生的（.local）", "valid=false")
def _(lab):
    r = lab.new()
    r.git("config", "user.email", "tu@Test-Mac.local")
    _, d = r.daily("context")
    return d["user"]["valid"] is False, "valid=%s" % d["user"]["valid"]


@scenario(G, "A3", "沒有設定任何 hook", "hooks.enabled=false")
def _(lab):
    r = lab.new(hooks=False)
    _, d = r.daily("context")
    return d["hooks"]["enabled"] is False, "enabled=%s" % d["hooks"]["enabled"]


@scenario(G, "A4", "專案有 .githooks 但沒呼叫 daily.py", "hooks.enabled=false（不能誤判為已啟用）")
def _(lab):
    r = lab.new(hooks=False)
    r.write(".githooks/pre-commit", "#!/bin/sh\nexit 0\n")
    r.git("config", "core.hooksPath", ".githooks")
    _, d = r.daily("context")
    return d["hooks"]["enabled"] is False, "enabled=%s project_hooks_call_daily=%s" % (d["hooks"]["enabled"], d["hooks"]["project_hooks_call_daily"])


@scenario(G, "A5", "專案 .githooks 三個都呼叫 daily.py", "hooks.enabled=true")
def _(lab):
    r = lab.new(hooks=False)
    for h in ("pre-commit", "commit-msg", "pre-push"):
        r.write(".githooks/" + h, open(os.path.join(HERE, "hooks", h), encoding="utf-8").read())
    r.git("config", "core.hooksPath", ".githooks")
    _, d = r.daily("context")
    return d["hooks"]["enabled"] is True, "enabled=%s" % d["hooks"]["enabled"]


@scenario(G, "A6", "repo 沒有 remote", "offline=true（跳過同步與 push）")
def _(lab):
    r = lab.new(remote=False)
    _, d = r.daily("context", "--fetch")
    return d["offline"] is True and d["fetch"] == "no-remote", "offline=%s fetch=%s" % (d["offline"], d["fetch"])


@scenario(G, "A7", "遠端連不上（fetch 失敗）", "fetch=failed、offline=true")
def _(lab):
    r = lab.new()
    r.git("remote", "set-url", "origin", os.path.join(r.d, "missing.git"))
    _, d = r.daily("context", "--fetch")
    return d["offline"] is True and d["fetch"] == "failed", "offline=%s fetch=%s" % (d["offline"], d["fetch"])


@scenario(G, "A8", "電腦找不到 Python 時 commit", "hook 擋下並提示安裝 Python（不靜默放行）")
def _(lab):
    if os.name != "nt":
        return None, "只在 Windows 驗證（其他系統的 Python 通常和 git 在同一個 PATH）"
    r = lab.new()
    git_dir = os.path.dirname(shutil.which("git"))
    env = dict(lab.env, PATH=git_dir + os.pathsep + os.environ.get("SystemRoot", r"C:\Windows") + r"\System32")
    r.write("b.txt", "b\n")
    r.git("add", "b.txt")
    res = lab.run(r.path, "git", "commit", "-q", "-m", "feat: b", env=env)
    return blocked(res, "找不到 Python")


# ---------- B 分支狀態 ----------

G = "B 分支狀態"


def state(r):
    _, d = r.daily("context")
    return d["state"], d


@scenario(G, "B1", "在主分支上", "state=default")
def _(lab):
    r = lab.new()
    r.git("switch", "-q", "main")
    s, _ = state(r)
    return s == "default", "state=" + s


@scenario(G, "B2", "detached HEAD", "state=detached")
def _(lab):
    r = lab.new()
    r.git("checkout", "-q", "--detach")
    s, _ = state(r)
    return s == "detached", "state=" + s


@scenario(G, "B3", "merge 衝突進行中", "state=in-progress，preflight commit 擋下")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    m.commit({"a.txt": "mate\n"}, "feat: mate", verify=False)
    m.git("push", "-q", "origin", "main", "--no-verify")
    r.commit({"a.txt": "mine\n"}, "feat: mine")
    r.git("fetch", "-q")
    r.git("merge", "origin/main")
    s, d = state(r)
    code, p = r.daily("preflight", "commit")
    ok = s == "in-progress" and d["in_progress"] == "merge" and code == 1
    return ok, "state=%s in_progress=%s preflight=%s" % (s, d["in_progress"], (p or {}).get("errors", [""])[0])


@scenario(G, "B4", "從 origin/main 開分支時忘了 --no-track", "state=tracks-default（不能誤判成已合併）")
def _(lab):
    r = lab.new()
    r.git("switch", "-q", "-c", "test.user/oops", "--track", "origin/main")
    s, _ = state(r)
    return s == "tracks-default", "state=" + s


@scenario(G, "B5", "分支已 push，遠端分支被刪（PR 合併後）", "state=gone")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: b")
    r.git("push", "-q", "-u", "origin", "test.user/feat")
    r.git("push", "-q", "origin", "--delete", "test.user/feat", "--no-verify")
    r.git("fetch", "-q", "--prune")
    s, _ = state(r)
    return s == "gone", "state=" + s


@scenario(G, "B6", "分支內容已全部在主分支", "state=merged")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: b")
    r.git("push", "-q", "-u", "origin", "test.user/feat")
    r.git("push", "-q", "origin", "HEAD:main", "--no-verify")
    r.git("fetch", "-q")
    s, _ = state(r)
    return s == "merged", "state=" + s


@scenario(G, "B7", "新分支還沒 push", "state=new（不能誤判成已合併）")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: b")
    s, _ = state(r)
    return s == "new", "state=" + s


@scenario(G, "B8", "已 push 而且有新 commit", "state=own，unpushed=1")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: b")
    r.git("push", "-q", "-u", "origin", "test.user/feat")
    r.commit({"c.txt": "c\n"}, "feat: c")
    s, d = state(r)
    return s == "own" and d["unpushed"] == 1, "state=%s unpushed=%s" % (s, d["unpushed"])


# ---------- C commit 前檢查（pre-commit hook） ----------

G = "C commit 前檢查（pre-commit）"


@scenario(G, "C1", "在主分支上 commit", "擋下")
def _(lab):
    r = lab.new()
    r.git("switch", "-q", "main")
    return blocked(r.commit({"a.txt": "x\n"}, "feat: x"), "主分支")


for i, path in enumerate([".env", "certs/server.pem", "certs/server.key", "data/app.db", "data/app.sqlite3",
                          "old copy/a.txt", ".secret_key"], 1):
    @scenario(G, "C2-%d" % i, "commit 禁止檔案 `%s`" % path, "擋下")
    def _(lab, path=path):
        return blocked(lab.new().commit({path: "x\n"}, "chore: add file"), "不能進版控")


@scenario(G, "C3", "commit `.env.example`（範本）", "放行")
def _(lab):
    return allowed(lab.new().commit({".env.example": "API_KEY=\n"}, "chore: add env template"))


for sid, name, content in [
    ("C4", "程式碼裡有 AWS key", 'KEY_ID = "%s"\n' % FAKE["aws"]),
    ("C5", "程式碼裡有私鑰", FAKE["pem"] + "\nMIIE\n"),
    ("C6", "程式碼裡寫死密碼（`DB_PASSWORD = \"…\"`）", 'DB_PASSWORD = "%s"\n' % FAKE["pw"]),
    ("C7", "程式碼裡有含帳密的連線字串", 'URL = "%s"\n' % FAKE["url"]),
    ("C8", "程式碼裡有 GitHub token", 'TOKEN = "%s"\n' % FAKE["gh"]),
]:
    @scenario(G, sid, name, "擋下（🔴）")
    def _(lab, content=content):
        return blocked(lab.new().commit({"src/conf.py": content}, "feat: conf"), "🔴")


@scenario(G, "C9", "一般程式碼 `token = request.headers[...]`", "放行（不能誤擋）")
def _(lab):
    return allowed(lab.new().commit({"src/auth.py": 'token = request.headers["x-token"]\n'}, "feat: auth"))


@scenario(G, "C10", "範例值 `password = \"<your-password>\"`", "放行（佔位字不算帳密）")
def _(lab):
    return allowed(lab.new().commit({"src/conf.py": 'password = "<your-password>"\n'}, "feat: conf"))


@scenario(G, "C11", "修改別人的日誌資料夾", "擋下")
def _(lab):
    r = lab.new()
    return blocked(r.commit({J + "mate/2026-10-30.md": journal(user="mate")}, "docs(journal): mate"), "別人的日誌")


@scenario(G, "C12", "自己的日誌格式錯誤", "擋下")
def _(lab):
    r = lab.new()
    return blocked(r.commit({J + "test.user/2026-10-30.md": "# 隨便寫\n- 做了一些事\n"}, "docs(journal): test.user"), "日誌格式")


@scenario(G, "C13", "自己的日誌格式正確", "放行")
def _(lab):
    r = lab.new()
    return allowed(r.commit({J + "test.user/2026-10-30.md": journal()}, "docs(journal): test.user 2026-10-30"))


@scenario(G, "C14", "自己的日誌裡寫了 `token: …`", "擋下（🔴）")
def _(lab):
    r = lab.new()
    text = journal(done=["換了新的 token: abcd1234efgh"])
    return blocked(r.commit({J + "test.user/2026-10-30.md": text}, "docs(journal): test.user"), "🔴")


for sid, name, files in [
    ("C15", "日誌和程式碼放在同一筆 commit", {J + "test.user/2026-10-30.md": journal(), "b.txt": "b\n"}),
    ("C16", "判斷點和程式碼放在同一筆 commit", {"docs/decisions.md": "- 2026-10-30｜x｜y\n", "b.txt": "b\n"}),
    ("C17", "`.mailmap` 和程式碼放在同一筆 commit", {".mailmap": "Test User <test.user@acme.test> T <t@x.local>\n", "b.txt": "b\n"}),
]:
    @scenario(G, sid, name, "擋下（共用檔要獨立一筆）")
    def _(lab, files=files):
        return blocked(lab.new().commit(files, "chore: mixed"), "獨立一筆")


@scenario(G, "C18", "暫存區是空的（--allow-empty）", "擋下")
def _(lab):
    r = lab.new()
    return blocked(r.git("commit", "-q", "--allow-empty", "-m", "chore: empty"), "暫存區是空的")


@scenario(G, "C19", "解完衝突的 merge commit，帶進隊友的日誌", "放行（不檢查別人帶進來的改動）")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    m.commit({"a.txt": "mate\n", J + "mate/2026-10-30.md": "隊友的舊格式日誌\n"}, "feat: mate", verify=False)
    m.git("push", "-q", "origin", "main", "--no-verify")
    r.commit({"a.txt": "mine\n"}, "feat: mine")
    r.git("fetch", "-q")
    r.git("merge", "origin/main")
    r.write("a.txt", "merged\n")
    r.git("add", "a.txt")
    return allowed(r.git("commit", "-q", "--no-edit"))


# ---------- D commit 訊息（commit-msg hook） ----------

G = "D commit 訊息（commit-msg）"


@scenario(G, "D1", "commit 訊息寫了密碼", "擋下（🔴）")
def _(lab):
    return blocked(lab.new().commit({"b.txt": "b\n"}, "fix: login, password=%s" % FAKE["pw"]), "🔴")


@scenario(G, "D2", "commit 訊息有 GitHub token", "擋下（🔴）")
def _(lab):
    return blocked(lab.new().commit({"b.txt": "b\n"}, "fix: use %s" % FAKE["gh"]), "🔴")


@scenario(G, "D3", "Co-Authored-By 結尾（含 email）", "放行，而且沒有 🟡 誤報")
def _(lab):
    r = lab.new().commit({"b.txt": "b\n"}, "feat: b\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    return r.returncode == 0 and "🟡" not in r.stderr, "exit=%d %s" % (r.returncode, last_line(r.stderr) or "（無訊息）")


@scenario(G, "D4", "commit 訊息有內部網址", "放行但提示 🟡")
def _(lab):
    r = lab.new().commit({"b.txt": "b\n"}, "docs: see https://wiki.acme.test/page")
    return r.returncode == 0 and "🟡" in r.stderr, "exit=%d %s" % (r.returncode, last_line(r.stderr))


# ---------- E push 前檢查（pre-push hook） ----------

G = "E push 前檢查（pre-push）"


@scenario(G, "E1", "直接 push 到主分支", "擋下")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: b")
    return blocked(r.git("push", "-q", "origin", "HEAD:main"), "主分支")


@scenario(G, "E2", "force push 覆蓋遠端", "擋下")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: b")
    r.git("push", "-q", "-u", "origin", "test.user/feat")
    r.git("commit", "-q", "--amend", "-m", "feat: b amended")
    return blocked(r.git("push", "-q", "-f", "origin", "test.user/feat"), "fast-forward")


@scenario(G, "E3", "用 --no-verify 繞過 commit 檢查塞進金鑰，再 push", "push 時擋下（🔴）")
def _(lab):
    r = lab.new()
    r.commit({"src/conf.py": 'KEY_ID = "%s"\n' % FAKE["aws"]}, "feat: conf", verify=False)
    return blocked(r.git("push", "-q", "-u", "origin", "test.user/feat"), "🔴")


@scenario(G, "E4", "正常 push 自己的分支", "放行")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: b")
    return allowed(r.git("push", "-q", "-u", "origin", "test.user/feat"))


@scenario(G, "E5", "在主分支上執行 preflight push", "ok=false")
def _(lab):
    r = lab.new()
    r.git("switch", "-q", "main")
    code, d = r.daily("preflight", "push")
    return code == 1 and d["ok"] is False, "exit=%d %s" % (code, d["errors"][0] if d["errors"] else "")


@scenario(G, "E6", "沒有要 push 的 commit", "ok=true，提示沒有 commit")
def _(lab):
    r = lab.new()
    code, d = r.daily("preflight", "push")
    return code == 0 and any("沒有要 push" in w for w in d["warnings"]), "exit=%d %s" % (code, d["warnings"])


# ---------- F 日誌格式驗證 ----------

G = "F 日誌格式（journal validate）"


def bad(sid, name, word, make, fname="test.user/2026-10-30.md"):
    @scenario(G, sid, name, "驗證失敗：" + word)
    def _(lab):
        code, errors, _ = validate(lab.new(), make(), fname)
        ok, got = has(errors, word)
        return ok and code == 1, got


bad("F1", "frontmatter 少了 tests", "缺 tests", lambda: journal().replace("tests: 無自動測試\n", ""))
bad("F2", "frontmatter user 和資料夾不同", "資料夾名稱", lambda: journal(user="mate"))
bad("F3", "frontmatter date 和檔名不同", "date 和檔名", lambda: journal(date="2026-10-29"))
bad("F4", "檔名不是日期", "檔名", lambda: journal(), "test.user/today.md")
bad("F5", "tests 寫法不對", "tests 要寫", lambda: journal(tests="全部通過"))
bad("F6", "covers 寫法不對", "covers", lambda: journal().replace("tests:", "covers: 10/29-10/30\ntests:"))
bad("F7", "少了標題", "第一行標題", lambda: journal().replace("# 2026-10-30 開發日誌\n", ""))
bad("F8", "少了「下次從這裡開始」", "下次從這裡開始", lambda: journal().replace("**下次從這裡開始**：繼續做下一步\n", ""))
bad("F9", "少了「交接」段落", "缺段落", lambda: journal().replace("### 🤝 交接\n- 無\n", ""))
bad("F10", "段落順序錯（待處理在進行中前面）", "段落順序",
    lambda: journal().replace("### 🔵 進行中\n- 無\n### 🟡 待處理\n- 無\n", "### 🟡 待處理\n- 無\n### 🔵 進行中\n- 無\n"))
bad("F11", "段落裡寫成一段文字", "不是條列項目", lambda: journal().replace("### ✅ 已完成\n", "### ✅ 已完成\n今天做了很多事情。\n"))
bad("F12", "段落是空的（沒寫「- 無」）", "至少一項", lambda: journal().replace("### 🔴 未決定\n- 無\n", "### 🔴 未決定\n"))
bad("F13", "寫了「無」又有其他項目", "寫了「無」", lambda: journal(done=["無", "加了登入頁"]))
bad("F14", "未決定沒寫選項與建議", "問題｜選項", lambda: journal(undecided=["要不要換套件"]))
bad("F15", "交接沒寫對象", "對象｜內容", lambda: journal(handoff=["記得看一下登入頁"]))
bad("F16", "收工段落時間倒過來（覆蓋了前一段）", "由早到晚", lambda: journal(blocks=[("18:00", {}), ("09:00", {})]))


@scenario(G, "F17", "測試失敗卻沒有進行中 / 待處理", "通過但警告：失敗的項目不能算已完成")
def _(lab):
    code, errors, warnings = validate(lab.new(), journal(tests="5 passed / 2 failed", done=["做完登入頁"]))
    return code == 0 and bool(warnings), warnings[0] if warnings else "沒有警告"


@scenario(G, "F18", "同一天收工兩次（接在後面）", "通過")
def _(lab):
    code, errors, _ = validate(lab.new(), journal(blocks=[("12:00", {}), ("18:30", {"done": ["下午的工作"]})]))
    return code == 0, "、".join(errors) or "無錯誤"


# ---------- G 找日誌與漏寫檢查 ----------

G = "G 找日誌與漏寫檢查"


def coverage(r, text, name="test.user/2026-10-30.md"):
    r.write(J + name, text)
    _, d = r.daily("journal", "coverage", J + name)
    return [m["subject"] for m in d["missing"]]


@scenario(G, "G1", "commit 了但日誌沒寫", "coverage 列出那筆 commit")
def _(lab):
    r = lab.new()
    r.commit({"b.txt": "b\n"}, "feat: forgotten work")
    miss = coverage(r, journal())
    return "feat: forgotten work" in miss, "missing=%s" % miss


@scenario(G, "G2", "先 rebase 再寫日誌（hash 已改變）", "coverage 認得 rebase 後的 hash")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    m.commit({"m.txt": "m\n"}, "feat: mate", verify=False)
    m.git("push", "-q", "origin", "main", "--no-verify")
    r.commit({"b.txt": "b\n"}, "feat: b")
    r.git("fetch", "-q")
    r.git("rebase", "-q", "origin/main")
    miss = coverage(r, journal(done=["加了 b（%s）" % r.head()]))
    return "feat: b" not in miss, "missing=%s" % miss


@scenario(G, "G3", "日誌之後有 merge commit 與判斷點 commit", "coverage 不列出（不算漏寫）")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    r.commit({J + "test.user/2026-10-29.md": journal(date="2026-10-29")}, "docs(journal): test.user 2026-10-29")
    m.commit({"m.txt": "m\n"}, "feat: mate", verify=False)
    m.git("push", "-q", "origin", "main", "--no-verify")
    r.git("fetch", "-q")
    r.git("merge", "-q", "--no-ff", "origin/main", "-m", "Merge origin/main")
    r.commit({"docs/decisions.md": "- 2026-10-30｜x｜y\n"}, "docs(decisions): test.user 2026-10-30")
    miss = coverage(r, journal())
    return miss == [], "missing=%s" % miss


@scenario(G, "G4", "開工時列出「日誌之後的 commit」", "只列真正的工作，略過 merge 與紀錄類 commit")
def _(lab):
    r = lab.new()
    r.commit({J + "test.user/2026-10-29.md": journal(date="2026-10-29")}, "docs(journal): test.user 2026-10-29")
    r.commit({"docs/decisions.md": "- x｜y｜z\n"}, "docs(decisions): test.user 2026-10-29")
    r.commit({".mailmap": "Test User <test.user@acme.test> T <t@x.local>\n"}, "chore: map test.user identities in .mailmap")
    r.commit({"b.txt": "b\n"}, "fix: real work after journal")
    _, d = r.daily("journal", "find", "--user", "test.user")
    after = d["users"]["test.user"]["commits_after"]
    return len(after) == 1 and "fix: real work" in after[0], "commits_after=%s" % after


@scenario(G, "G5", "隊友日誌只在他的遠端分支上（我在 main）", "journal find --all 找得到並解析交接")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    m.git("switch", "-q", "-c", "mate/x")
    m.commit({J + "mate/2026-10-29.md": journal(user="mate", date="2026-10-29", branch="mate/x",
                                                handoff=["test.user｜登入 API 改了，請先看"])}, "docs(journal): mate 2026-10-29")
    m.git("push", "-q", "-u", "origin", "mate/x")
    r.git("fetch", "-q")
    r.git("switch", "-q", "main")
    _, d = r.daily("journal", "find", "--all")
    u = d["users"].get("mate") or {}
    ok = u.get("source", "").startswith("origin/") and u.get("sections", {}).get("交接") == ["test.user｜登入 API 改了，請先看"]
    return ok, "source=%s 交接=%s" % (u.get("source"), u.get("sections", {}).get("交接"))


@scenario(G, "G6", "舊格式日誌", "format=legacy，交給 AI 讀全文")
def _(lab):
    r = lab.new()
    r.commit({J + "test.user/2026-10-20.md": "# 日誌\n## 完成\n- x\n## 明天從這裡開始\n- y\n"}, "docs(journal): old", verify=False)
    _, d = r.daily("journal", "find", "--user", "test.user")
    return d["users"]["test.user"]["format"] == "legacy", "format=%s" % d["users"]["test.user"]["format"]


@scenario(G, "G7", "還沒有任何日誌", "users.<me>=null")
def _(lab):
    _, d = lab.new().daily("journal", "find", "--user", "test.user")
    return d["users"]["test.user"] is None, "users=%s" % d["users"]


@scenario(G, "G8", "最新一份日誌被刪掉了", "退回上一份")
def _(lab):
    r = lab.new()
    r.commit({J + "test.user/2026-10-29.md": journal(date="2026-10-29")}, "docs(journal): test.user 2026-10-29")
    r.commit({J + "test.user/2026-10-30.md": journal()}, "docs(journal): test.user 2026-10-30")
    r.git("rm", "-q", J + "test.user/2026-10-30.md")
    r.git("commit", "-q", "-m", "docs(journal): remove")
    _, d = r.daily("journal", "find", "--user", "test.user")
    return d["users"]["test.user"]["date"] == "2026-10-29", "date=%s" % d["users"]["test.user"]["date"]


@scenario(G, "G9", "日誌在自己另一個還沒合併的分支", "找得到，source 標出分支名稱")
def _(lab):
    r = lab.new()
    r.commit({J + "test.user/2026-10-29.md": journal(date="2026-10-29")}, "docs(journal): test.user 2026-10-29")
    r.git("switch", "-q", "-c", "test.user/other", "main")
    _, d = r.daily("journal", "find", "--user", "test.user")
    u = d["users"]["test.user"] or {}
    return u.get("source") == "test.user/feat", "source=%s" % u.get("source")


# ---------- H 機敏掃描 ----------

G = "H 機敏掃描（scan）"


@scenario(G, "H1", "日誌裡有 email、電話、手機、IP、本機路徑、內部網址、長亂碼", "7 種 🟡 全部抓到")
def _(lab):
    r = lab.new()
    text = "\n".join(["- 聯絡 lin@acme.test", "- 電話 +886 2 1234 5678", "- 手機 0912-345-678", "- 主機 10.1.2.3",
                      r"- 路徑 C:\Users\lin\proj", "- 文件 https://wiki.acme.test/page", "- 代碼 " + "Ab3" * 12])
    r.write(J + "test.user/x.md", text)
    _, d = r.daily("scan", "--file", J + "test.user/x.md")
    rules = {h["rule"] for h in d["hits"] if h["level"] == "yellow"}
    want = {"email", "phone", "mobile-tw", "ip", "user-path", "url", "long-token"}
    return want <= rules, "抓到 %s，缺 %s" % (sorted(rules), sorted(want - rules) or "無")


@scenario(G, "H2", "允許清單（noreply、example.com、localhost、127.0.0.1、commit hash）", "不誤報")
def _(lab):
    r = lab.new()
    text = "noreply@anthropic.com dev@example.com http://localhost:8000 127.0.0.1 " + "0123456789abcdef" * 2 + "01234567"
    _, d = r.daily("scan", "--file", "-", input=text)
    return d["hits"] == [], "hits=%s" % d["hits"]


@scenario(G, "H3", "專案自訂格式（員工編號 EMP1234）", "🟡 custom 規則抓到")
def _(lab):
    r = lab.new()
    r.write(".journal-sensitive-patterns", "# 員工編號\nEMP[0-9]{4}\n")
    _, d = r.daily("scan", "--file", "-", input="- 幫 EMP1234 排班")
    return any(h["rule"].startswith("custom") for h in d["hits"]), "hits=%s" % d["hits"]


@scenario(G, "H4", "專案自訂格式寫錯（不是正規表示式）", "回報錯誤，不當掉")
def _(lab):
    r = lab.new()
    r.write(".journal-sensitive-patterns", "EMP[0-9\n")
    code, d = r.daily("scan", "--file", "-", input="x")
    return bool(d and d["errors"]), "errors=%s" % (d or {}).get("errors")


@scenario(G, "H5", "掃描結果不外洩原文", "輸出裡沒有金鑰本身")
def _(lab):
    r = lab.new()
    res = lab.run(r.path, sys.executable, ".claude/skills/_daily/daily.py", "scan", "--file", "-", input="key " + FAKE["gh"])
    return FAKE["gh"] not in res.stdout and '"red": 1' in res.stdout, "red 命中、輸出不含原文" if FAKE["gh"] not in res.stdout else "輸出含原文"


@scenario(G, "H6", "程式碼裡的 email / 網址", "不提示 🟡（只掃寫給人看的文字）")
def _(lab):
    r = lab.new()
    r.write("src/mail.py", 'SUPPORT = "help@acme.test"\nURL = "https://api.acme.test"\n')
    r.git("add", "src/mail.py")
    _, d = r.daily("scan", "--staged")
    return d["yellow"] == 0, "yellow=%s" % d["yellow"]


# ---------- I 多人協作 ----------

G = "I 多人協作（重疊與身分）"


@scenario(G, "I1", "隊友的分支也改了我在改的檔案", "overlap 列出分支與檔案")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    m.git("switch", "-q", "-c", "mate/x")
    m.commit({"a.txt": "mate\n"}, "feat: mate")
    m.git("push", "-q", "-u", "origin", "mate/x")
    r.git("fetch", "-q")
    r.write("a.txt", "mine\n")
    _, d = r.daily("overlap")
    o = d["overlaps"]
    return len(o) == 1 and o[0]["branch"] == "origin/mate/x" and o[0]["files"] == ["a.txt"], "overlaps=%s" % o


@scenario(G, "I2", "隊友的分支已經合併進主分支", "不列出（不誤報）")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    m.git("switch", "-q", "-c", "mate/x")
    m.commit({"a.txt": "mate\n"}, "feat: mate")
    m.git("push", "-q", "-u", "origin", "mate/x")
    m.git("push", "-q", "origin", "mate/x:main", "--no-verify")
    r.git("fetch", "-q")
    r.write("a.txt", "mine\n")
    _, d = r.daily("overlap")
    return d["overlaps"] == [], "overlaps=%s" % d["overlaps"]


@scenario(G, "I3", "同一人用舊電腦身分 commit 過", "identities 列出候選與 .mailmap 行")
def _(lab):
    r = lab.new()
    r.write("b.txt", "b\n")
    r.git("add", "b.txt")
    r.git("-c", "user.email=tu@Test-Mac.local", "commit", "-q", "-m", "feat: old", "--no-verify")
    _, d = r.daily("identities")
    c = [x for x in d["candidates"] if x["email"] == "tu@Test-Mac.local"]
    return bool(c) and c[0]["mailmap"].startswith("Test User <test.user@acme.test>"), "candidates=%s" % [x["email"] for x in d["candidates"]]


@scenario(G, "I4", "隊友的身分", "不會被當成我的身分")
def _(lab):
    r = lab.new()
    m = r.clone("mate", "Mate Lin", "mate@acme.test")
    m.commit({"m.txt": "m\n"}, "feat: mate", verify=False)
    m.git("push", "-q", "origin", "main", "--no-verify")
    r.git("fetch", "-q")
    _, d = r.daily("identities")
    return all(x["email"] != "mate@acme.test" for x in d["candidates"]), "candidates=%s" % [x["email"] for x in d["candidates"]]


# ---------- 執行與報告 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(HERE, "..", "test-report.md"))
    ap.add_argument("--keep", action="store_true", help="保留暫存 repo 方便除錯")
    a = ap.parse_args()
    base = tempfile.mkdtemp(prefix="daily-test-")
    lab = Lab(base)
    started, t0 = datetime.now(), time.time()
    results = []
    for group, sid, name, expect, fn in SCENARIOS:
        try:
            ok, got = fn(lab)
        except Exception as e:
            ok, got = False, "例外：%s（%s）" % (type(e).__name__, traceback.extract_tb(e.__traceback__)[-1].lineno)
        results.append((group, sid, name, expect, ok, got))
        print("%s %-6s %s" % ({True: "PASS", False: "FAIL", None: "SKIP"}[ok], sid, name), flush=True)
    write_report(results, os.path.abspath(a.report), started, time.time() - t0, lab)
    if not a.keep:
        shutil.rmtree(base, ignore_errors=True)
    failed = sum(r[4] is False for r in results)
    print("\n%d 項：通過 %d、失敗 %d、略過 %d → %s" % (len(results), sum(r[4] is True for r in results), failed,
                                                 sum(r[4] is None for r in results), os.path.abspath(a.report)))
    sys.exit(1 if failed else 0)


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def write_report(results, path, started, dur, lab):
    gitv = lab.run(lab.base, "git", "--version").stdout.strip()
    mark = {True: "✅ 通過", False: "❌ 失敗", None: "⏭ 略過"}
    groups = list(dict.fromkeys(r[0] for r in results))
    total = [sum(r[4] is v for r in results) for v in (True, False, None)]
    L = ["# daily.py 失敗場景測試報告", "",
         "> 由 `.claude/skills/_daily/test_daily.py` 自動產生。",
         "", "| 項目 | 內容 |", "|---|---|",
         "| 執行時間 | %s（耗時 %.0f 秒） |" % (started.strftime("%Y-%m-%d %H:%M"), dur),
         "| 環境 | %s %s・Python %s・%s |" % (platform.system(), platform.release(), platform.python_version(), gitv),
         "| 測試資料 | 全部是假資料：假姓名（Test User、Mate Lin）、保留網域 `acme.test`、執行時才組出來的假金鑰 |",
         "| 測試方式 | 每個場景在暫存資料夾建立新的 bare 遠端＋clone（需要時再 clone 一份當隊友），隔離全域與系統 git 設定，實際執行 git commit / merge / push 與 `daily.py` |",
         "| 結果 | **%d 項：✅ %d、❌ %d、⏭ %d** |" % (len(results), *total), "",
         "## 總覽", "", "| 分組 | 場景數 | ✅ 通過 | ❌ 失敗 | ⏭ 略過 |", "|---|---|---|---|---|"]
    for g in groups:
        rs = [r for r in results if r[0] == g]
        L.append("| %s | %d | %d | %d | %d |" % (g, len(rs), *[sum(r[4] is v for r in rs) for v in (True, False, None)]))
    fails = [r for r in results if r[4] is False]
    if fails:
        L += ["", "## ❌ 失敗項目", "", "| ID | 場景 | 預期 | 實際 |", "|---|---|---|---|"]
        L += ["| %s | %s | %s | %s |" % (r[1], cell(r[2]), cell(r[3]), cell(r[5])) for r in fails]
    for g in groups:
        L += ["", "## " + g, "", "| ID | 場景 | 預期 | 實際 | 結果 |", "|---|---|---|---|---|"]
        L += ["| %s | %s | %s | %s | %s |" % (r[1], cell(r[2]), cell(r[3]), cell(r[5]), mark[r[4]])
              for r in results if r[0] == g]
    L += ["", "## 沒有自動測試、需要人工驗證的部分", "",
          "| 項目 | 原因 |", "|---|---|",
          "| AskUserQuestion 問卷流程（狀態確認、分支命名、同步 / push 詢問） | 由 Claude 依 SKILL.md 執行，屬於對話行為 |",
          "| 步驟順序（commit 程式碼 → 同步 → 共用檔 → 日誌 → push） | 順序由 SKILL.md 規定；程式只保證每一步的檢查 |",
          "| 姓名、業務資料等語意上的機敏內容 | 正規表示式抓不到，靠 Claude 人工讀過 |",
          "| 本地記憶的讀寫 | 存在 Claude 的記憶資料夾，不經過 daily.py |",
          "| GitHub 分支保護、`gh pr create` | 需要真實的 GitHub repo |", ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
