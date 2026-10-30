#!/usr/bin/env python3
"""/day-start、/day-end 共用工具：能用程式確定的事都在這裡做，AI 只負責文字與對話。

  context [--fetch]                  專案參數、身分與 repo 狀態
  identities                         可能屬於同一人的其他 git 身分（給 /day-start 建議 .mailmap）
  overlap                            其他分支也改到、和我重疊的檔案
  journal find (--user U | --all)    跨分支找每人最新一份日誌並解析
  journal validate FILE...           檢查日誌格式
  journal coverage FILE              這次的 commit 有沒有都寫進日誌
  scan (--staged | --unpushed | --message FILE | --file FILE...)
                                     機敏掃描；只回報位置與規則，不輸出內容
  preflight (commit | push | message FILE) [--hook]
                                     commit / push 前的硬性檢查；--hook 給 git hook 用

輸出 JSON（--hook 時輸出文字到 stderr）。
exit code：0 通過；1 有問題（scan：只有 🟡）；2 scan 有 🔴。
只用標準函式庫，Python 3.8+。
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

ZERO = "0" * 40
ORIG_CWD = os.getcwd()
HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------- git ----------
def git(*args, input=None, timeout=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", "-c", "core.quotepath=off", *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", input=input, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "timeout")


def out(*args):
    r = git(*args)
    return r.stdout.strip() if r.returncode == 0 else ""


def ok(*args):
    return git(*args).returncode == 0


def ref_exists(ref):
    return ok("rev-parse", "--verify", "--quiet", ref)


def lines(*args):
    return [l for l in out(*args).splitlines() if l.strip()]


def die(msg):
    print(json.dumps({"ok": False, "errors": [msg]}, ensure_ascii=False, indent=2))
    sys.exit(1)


def arg_path(p):
    return p if p == "-" else os.path.abspath(os.path.join(ORIG_CWD, p))


def emit(data, hook=False, code=None):
    if code is None:
        code = 1 if data.get("errors") else 0
    if hook:
        for e in data.get("errors", []):
            print("[daily] ✗ " + e, file=sys.stderr)
        for w in data.get("warnings", []):
            print("[daily] ! " + w, file=sys.stderr)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(code)


# ---------- 基本參數 ----------

MACHINE_EMAIL = re.compile(r"(\.local|\.lan|\.localdomain|\(none\))$", re.I)


def email_ok(email):
    if "@" not in email:
        return False
    return "." in email.rsplit("@", 1)[1] and not MACHINE_EMAIL.search(email)


def base():
    root = out("rev-parse", "--show-toplevel")
    if not root:
        die("不在 git repo 裡")
    os.chdir(root)
    url = out("remote", "get-url", "origin")
    project = re.sub(r"\.git$", "", re.split(r"[/:]", url.rstrip("/"))[-1]) if url else os.path.basename(root)
    head = out("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        default = head.split("/", 1)[1]
    elif ref_exists("refs/remotes/origin/main"):
        default = "main"
    elif ref_exists("refs/remotes/origin/master"):
        default = "master"
    else:
        default = "main" if ref_exists("refs/heads/main") else "master"
    name, email = out("config", "user.name"), out("config", "user.email")
    valid = bool(name) and email_ok(email)
    return {
        "project": project,
        "has_remote": bool(url),
        "default": default,
        "origin_default": "origin/" + default if ref_exists("refs/remotes/origin/" + default) else None,
        "journal": "docs/%s_journal/" % project,
        "decisions": "docs/decisions.md" if os.path.isfile("docs/decisions.md") else None,
        "user": {"name": name, "email": email, "valid": valid,
                 "username": email.split("@")[0].lower() if valid else None},
    }


OPS = [("rebase-merge", "rebase"), ("rebase-apply", "rebase"), ("MERGE_HEAD", "merge"),
       ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert")]


def in_progress():
    for name, label in OPS:
        p = out("rev-parse", "--git-path", name)
        if p and os.path.exists(p):
            return label
    return None


def branch_info(b):
    """state：in-progress / detached / default / tracks-default / gone / merged / own / new"""
    branch = out("branch", "--show-current") or None
    info = {"branch": branch, "in_progress": in_progress(), "upstream": None, "pushed": False}
    if info["in_progress"]:
        info["state"] = "in-progress"
    elif not branch:
        info["state"] = "detached"
    elif branch == b["default"]:
        info["state"] = "default"
    else:
        info["pushed"] = ref_exists("refs/remotes/origin/" + branch)
        # 看 config 而不是 @{upstream}：遠端分支被刪後 @{upstream} 會解析失敗，會誤判成新分支
        merge = out("config", "branch.%s.merge" % branch)
        remote = out("config", "branch.%s.remote" % branch) or "origin"
        if not merge:
            info["state"] = "new"
        else:
            up = remote + "/" + re.sub(r"^refs/heads/", "", merge)
            info["upstream"] = up
            if merge == "refs/heads/" + b["default"]:
                info["state"] = "tracks-default"
            elif not ref_exists("refs/remotes/" + up):
                info["state"] = "gone"
            elif b["origin_default"] and ok("merge-base", "--is-ancestor", "HEAD", b["origin_default"]):
                info["state"] = "merged"
            else:
                info["state"] = "own"
    return info


def porcelain_paths():
    paths = []
    for l in git("status", "--porcelain").stdout.splitlines():
        if len(l) > 3:
            paths.append(l[3:].split(" -> ")[-1].strip('"'))
    return paths


def cmd_context(a):
    b = base()
    if not a.fetch:
        b["fetch"] = "skipped"
    elif not b["has_remote"]:
        b["fetch"] = "no-remote"
    else:
        b["fetch"] = "ok" if git("fetch", "origin", "--prune", timeout=90).returncode == 0 else "failed"
        b["origin_default"] = "origin/" + b["default"] if ref_exists("refs/remotes/origin/" + b["default"]) else None
    b["offline"] = not b["has_remote"] or b["fetch"] == "failed"  # 不同步、不 push
    b.update(branch_info(b))
    b["uncommitted"] = len(porcelain_paths())
    b["unpushed"] = int(out("rev-list", "--count", "HEAD", "--not", "--remotes=origin") or 0) if b["branch"] else None
    b["behind_default"] = int(out("rev-list", "--count", "HEAD.." + b["origin_default"]) or 0) if b["origin_default"] else None
    daily_hooks = os.path.relpath(os.path.join(HERE, "hooks"), os.getcwd()).replace("\\", "/")
    hooks_path = out("config", "core.hooksPath").rstrip("/")
    # 專案自己的 hook 三個都要呼叫 daily.py 才算有檢查
    project_calls_daily = all(
        os.path.isfile(os.path.join(".githooks", h))
        and "daily.py" in open(os.path.join(".githooks", h), encoding="utf-8", errors="replace").read()
        for h in ("pre-commit", "commit-msg", "pre-push"))
    b["hooks"] = {
        "hooks_path": hooks_path or None,
        "daily_hooks": daily_hooks,
        "project_githooks": os.path.isdir(".githooks"),
        "project_hooks_call_daily": project_calls_daily,
        "enabled": hooks_path == daily_hooks or (hooks_path == ".githooks" and project_calls_daily),
    }
    b["python"] = sys.executable
    emit(b)


# ---------- 身分、重疊檔案 ----------

def norm(s):
    return re.sub(r"[\s.]", "", s).lower()


def cmd_identities(a):
    b = base()
    me = b["user"]
    counts = Counter(git("log", "--branches", "--remotes", "--use-mailmap", "--format=%aN\t%aE").stdout.splitlines())
    cands = []
    for key, n in counts.items():
        if "\t" not in key:
            continue
        name, email = key.split("\t", 1)
        if name == me["name"] and email.lower() == me["email"].lower():
            continue
        reasons = []
        if me["name"] and norm(name) == norm(me["name"]):
            reasons.append("名稱相同")
        if me["username"] and email.split("@")[0].lower() == me["username"]:
            reasons.append("email @ 前面相同")
        if me["username"] and norm(name) == norm(me["username"]):
            reasons.append("名稱等於 username")
        if not email_ok(email):
            reasons.append("電腦自動產生的 email（也可能是別人的，要確認）")
        if reasons:
            cands.append({"name": name, "email": email, "commits": n, "reasons": reasons,
                          "mailmap": "%s <%s> %s <%s>" % (me["name"], me["email"], name, email)})
    emit({"me": me, "candidates": cands})


def cmd_overlap(a):
    b = base()
    od = b["origin_default"]
    if not od:
        emit({"mine": [], "overlaps": [], "note": "沒有 origin/" + b["default"] + "，無法比對"})
    branch = out("branch", "--show-current")
    mine = set(lines("diff", "--name-only", od + "...HEAD")) | set(porcelain_paths())
    overlaps = []
    for r in lines("for-each-ref", "--format=%(refname)", "refs/remotes/origin"):
        short = r[len("refs/remotes/"):]
        if short.endswith("/HEAD") or short in (od, "origin/" + (branch or "")):
            continue
        if ok("merge-base", "--is-ancestor", r, od):  # 已經合併進主分支
            continue
        files = sorted(mine & set(lines("diff", "--name-only", od + "..." + r)))
        if files:
            overlaps.append({"branch": short, "files": files,
                             "last_commit": out("log", "-1", "--format=%ad", "--date=short", r)})
    emit({"mine": sorted(mine), "overlaps": overlaps})


# ---------- 日誌 ----------

DATE_MD = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
BLOCK = re.compile(r"^## 收工 (\d{2}:\d{2})\s*$")
HEADING = re.compile(r"^### (?:\S+\s+)?(已完成|進行中|待處理|未決定|問題與解法|交接)\s*$")
NEXT = re.compile(r"^\*\*下次從這裡開始\*\*[：:]\s*(.*)$")
ITEM = re.compile(r"^(?:-|\d+\.)\s+(.+)$")
SECTIONS = ["已完成", "進行中", "待處理", "未決定", "問題與解法", "交接"]
PIPES = {"未決定": (2, "問題｜選項 A / B｜建議"), "問題與解法": (1, "問題｜解法"), "交接": (1, "對象｜內容")}
TESTS = re.compile(r"^(\d+ passed / (\d+) failed|無自動測試|未執行)$")
# 收工時的紀錄類 commit（日誌、判斷點、.mailmap），不算「工作」，不要求寫進日誌
BOOKKEEPING = re.compile(r"^(docs\((journal|decisions)\):|chore: map \S+ identities in \.mailmap)")
COVERS = re.compile(r"^\d{4}-\d{2}-\d{2} ~ \d{4}-\d{2}-\d{2}$")


def split_frontmatter(all_lines):
    """回傳 (frontmatter dict 或 None, 內文起始行 index)"""
    if not all_lines or all_lines[0].strip() != "---":
        return None, 0
    for i in range(1, len(all_lines)):
        if all_lines[i].strip() == "---":
            fm = {}
            for l in all_lines[1:i]:
                l = re.sub(r"\s+#.*$", "", l)
                if ":" in l:
                    k, v = l.split(":", 1)
                    fm[k.strip()] = v.strip()
            return fm, i + 1
    return None, 0


def parse_journal(text):
    all_lines = text.splitlines()
    fm, start = split_frontmatter(all_lines)
    starts = [i for i in range(start, len(all_lines)) if BLOCK.match(all_lines[i])]
    if not starts:
        return {"format": "legacy", "frontmatter": fm, "content": text}
    sections, nxt, cur = {s: [] for s in SECTIONS}, None, None
    for l in all_lines[starts[-1] + 1:]:
        m = HEADING.match(l)
        if m:
            cur = m.group(1)
        elif NEXT.match(l):
            nxt = NEXT.match(l).group(1).strip()
        elif cur and ITEM.match(l) and ITEM.match(l).group(1).strip() != "無":
            sections[cur].append(ITEM.match(l).group(1).strip())
    return {"format": "v2", "frontmatter": fm, "blocks": len(starts),
            "last_block": BLOCK.match(all_lines[starts[-1]]).group(1), "next": nxt, "sections": sections}


def journal_paths(b, user=None):
    prefix = b["journal"] + (user + "/" if user else "")
    paths = set()
    if os.path.isdir(prefix):
        for d, _, files in os.walk(prefix):
            paths.update(os.path.join(d, f).replace("\\", "/") for f in files)
    paths.update(lines("log", "--branches", "--remotes", "--format=", "--name-only", "--", prefix))
    by_user = defaultdict(set)
    for p in paths:
        parts = p[len(b["journal"]):].split("/") if p.startswith(b["journal"]) else []
        if len(parts) == 2 and DATE_MD.match(parts[1]):
            by_user[parts[0]].add(p)
    return by_user


def read_latest(paths):
    for p in sorted(paths, key=os.path.basename, reverse=True):
        c = out("log", "--branches", "--remotes", "-1", "--format=%H", "--", p)
        if os.path.isfile(p) and (not c or ok("merge-base", "--is-ancestor", c, "HEAD")):
            text, source = open(p, encoding="utf-8", errors="replace").read(), "worktree"
        elif c:
            r = git("show", "%s:%s" % (c, p))
            if r.returncode:  # 最後一次是刪除
                continue
            text = r.stdout
            on = lines("branch", "-a", "--contains", c, "--format=%(refname:short)")
            source = on[0] if on else c[:7]
        else:
            continue
        info = {"path": p, "date": os.path.basename(p)[:-3], "source": source, "commit": c[:7] or None}
        info.update(parse_journal(text))
        return info
    return None


def cmd_journal_find(a):
    b = base()
    by_user = journal_paths(b, a.user)
    users = [a.user] if a.user else sorted(by_user)
    result = {}
    for u in users:
        latest = read_latest(by_user.get(u, ()))
        if latest and u == b["user"]["username"]:
            since = out("log", "--branches", "--remotes", "-1", "--format=%cI", "--", b["journal"] + u + "/")
            if since:
                after = lines("log", "--branches", "--remotes", "--no-merges", "--use-mailmap", "--author=" + b["user"]["email"],
                              "--since=" + since, "--format=%h %ad\t%s", "--date=format:%m-%d %H:%M")
                latest["commits_after"] = [c.replace("\t", " ") for c in after if not BOOKKEEPING.match(c.split("\t", 1)[-1])]
        result[u] = latest
    emit({"journal": b["journal"], "users": result})


def validate_text(path, text):
    errors, warnings = [], []
    name = os.path.basename(path)
    m = DATE_MD.match(name)
    if not m:
        errors.append("檔名要是 YYYY-MM-DD.md")
    user_dir = os.path.basename(os.path.dirname(path))
    all_lines = text.splitlines()
    fm, start = split_frontmatter(all_lines)
    if fm is None:
        errors.append("缺 frontmatter（--- 包起來的 date / user / branch / tests）")
        fm = {}
    else:
        for k in ("date", "user", "branch", "tests"):
            if not fm.get(k):
                errors.append("frontmatter 缺 " + k)
        if m and fm.get("date") and fm["date"] != m.group(1):
            errors.append("frontmatter date 和檔名不同")
        if fm.get("user") and fm["user"] != user_dir:
            errors.append("frontmatter user（%s）和資料夾名稱（%s）不同" % (fm["user"], user_dir))
        if fm.get("tests") and not TESTS.match(fm["tests"]):
            errors.append("tests 要寫「N passed / N failed」「無自動測試」或「未執行」")
        if fm.get("covers") and not COVERS.match(fm["covers"]):
            errors.append("covers 要寫「YYYY-MM-DD ~ YYYY-MM-DD」")

    body = [(i + 1, all_lines[i]) for i in range(start, len(all_lines))]
    content = [(n, l) for n, l in body if l.strip()]
    title = "# %s 開發日誌" % fm.get("date", m.group(1) if m else "YYYY-MM-DD")
    if not content or content[0][1].strip() != title:
        errors.append("第一行標題要是「%s」" % title)
    else:
        content = content[1:]
    if not content or not BLOCK.match(content[0][1]):
        errors.append("內容要放在「## 收工 HH:MM」段落裡（至少一段）")

    blocks, times = [], []
    for n, l in content:
        bm = BLOCK.match(l)
        if bm:
            times.append(bm.group(1))
            blocks.append((bm.group(1), []))
        elif blocks:
            blocks[-1][1].append((n, l))
    if times != sorted(times) or len(set(times)) != len(times):
        errors.append("收工段落的時間要由早到晚、不重複（接在後面，不要覆蓋）")

    for t, blines in blocks:
        p = "收工 %s：" % t
        got, cur, nxt = {}, None, None
        for n, l in blines:
            hm = HEADING.match(l)
            if hm:
                cur = hm.group(1)
                if cur in got:
                    errors.append(p + "「%s」重複" % cur)
                got[cur] = []
            elif NEXT.match(l) and cur is None:
                nxt = NEXT.match(l).group(1).strip()
            elif cur and ITEM.match(l):
                got[cur].append((n, ITEM.match(l).group(1).strip()))
            else:
                errors.append(p + "第 %d 行不是條列項目（一項一行；段落外不寫內容）" % n)
        if not nxt:
            errors.append(p + "缺「**下次從這裡開始**：…」")
        order = [s for s in got if s in SECTIONS]
        missing = [s for s in SECTIONS if s not in got]
        if missing:
            errors.append(p + "缺段落：" + "、".join(missing))
        elif order != SECTIONS:
            errors.append(p + "段落順序要是 " + " → ".join(SECTIONS))
        for s, items in got.items():
            texts = [x for _, x in items]
            if not items:
                errors.append(p + "「%s」至少一項，沒有就寫「- 無」" % s)
            elif "無" in texts and len(texts) > 1:
                errors.append(p + "「%s」寫了「無」又有其他項目" % s)
            elif s in PIPES and texts != ["無"]:
                need, fmt = PIPES[s]
                for n, x in items:
                    if x.count("｜") < need:
                        errors.append(p + "第 %d 行格式要是「%s」" % (n, fmt))
        tm = TESTS.match(fm.get("tests", ""))
        if t == times[-1] and tm and tm.group(2) and int(tm.group(2)) > 0:
            if all([x for _, x in got.get(s, [])] in ([], ["無"]) for s in ("進行中", "待處理")):
                warnings.append(p + "測試有失敗，但「進行中」「待處理」都是空的——失敗的項目不能算已完成")
    return errors, warnings


def cmd_journal_validate(a):
    results, bad = {}, False
    for f in a.files:
        path = arg_path(f)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError as e:
            results[f] = {"ok": False, "errors": [str(e)], "warnings": []}
            bad = True
            continue
        errors, warnings = validate_text(path.replace("\\", "/"), text)
        results[f] = {"ok": not errors, "errors": errors, "warnings": warnings}
        bad = bad or bool(errors)
    emit({"ok": not bad, "files": results}, code=1 if bad else 0)


def cmd_journal_coverage(a):
    path = arg_path(a.file)
    b = base()
    text = open(path, encoding="utf-8", errors="replace").read()
    user = os.path.basename(os.path.dirname(path))
    since = out("log", "--branches", "--remotes", "-1", "--format=%cI", "--", b["journal"] + user + "/") or "7 days ago"
    commits = [l.split("\t", 1) for l in lines("log", "--branches", "--remotes", "--no-merges", "--use-mailmap",
                                                 "--author=" + b["user"]["email"], "--since=" + since, "--format=%H\t%s")]
    mentioned = set(re.findall(r"\b[0-9a-f]{7,40}\b", text))
    missing = [{"commit": h[:7], "subject": s} for h, s in commits
               if not BOOKKEEPING.match(s) and not any(h.startswith(x) for x in mentioned)]
    emit({"since": since, "missing": missing, "uncommitted": porcelain_paths()}, code=1 if missing else 0)


# ---------- 機敏掃描 ----------

KEYS = r"(?:password|passwd|pwd|secret|token|api[_-]?key|app[_-]?(?:id|secret)|access[_-]?key|client[_-]?secret)"
# 任何檔案都擋：格式明確的金鑰
RED_ANY = [
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    ("aws-key", r"AKIA[0-9A-Z]{16}"),
    ("github-token", r"gh[pousr]_[A-Za-z0-9]{20,}"),
    ("sk-key", r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    ("slack-token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("jwt", r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ("url-credential", r"[a-z][a-z0-9+.-]*://[^/\s:@]+:(?P<v>[^/\s@]+)@"),
    ("assigned-secret", r"\b" + KEYS + r"\w*\s*[:=]\s*[\"'](?P<v>[^\"'\s]{8,})[\"']"),
]
# 日誌、判斷點、commit 訊息（寫給人看的文字）才掃
RED_TEXT = [("secret-value", r"\b" + KEYS + r"\s*[:=]\s*(?P<v>[^\s`]{4,})")]
YEL_TEXT = [
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("phone", r"\+[0-9][0-9 -]{7,}[0-9]"),
    ("mobile-tw", r"(?<![0-9])09[0-9]{2}-?[0-9]{3}-?[0-9]{3}(?![0-9])"),
    ("ip", r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])"),
    ("user-path", r"/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\"),
    ("url", r"https?://[^\s)`>]+"),
    ("long-token", r"[A-Za-z0-9+=-]{32,}"),
]
PLACEHOLDER = re.compile(r"^(?:[<${%*]|x{3,}|\.{3}|your[_-]?|example|changeme|placeholder|dummy|fake|test|none|null)", re.I)
ALLOW = re.compile(r"noreply@|@example\.(?:com|org|net)$|^(?:127\.0\.0\.1|0\.0\.0\.0)$|^https?://(?:localhost|127\.0\.0\.1)|^[0-9a-f]{40}$", re.I)


def compile_rules():
    red_any = [(n, re.compile(p, re.I)) for n, p in RED_ANY]
    red_text = red_any + [(n, re.compile(p, re.I)) for n, p in RED_TEXT]
    yel = [(n, re.compile(p, re.I)) for n, p in YEL_TEXT]
    errors = []
    if os.path.isfile(".journal-sensitive-patterns"):  # 專案自訂（例如員工編號），一行一個正規表示式
        for i, l in enumerate(open(".journal-sensitive-patterns", encoding="utf-8"), 1):
            l = l.strip()
            if l and not l.startswith("#"):
                try:
                    yel.append(("custom:%d" % i, re.compile(l)))
                except re.error:
                    errors.append(".journal-sensitive-patterns 第 %d 行不是正確的正規表示式" % i)
    return red_any, red_text, yel, errors


class Scanner:
    def __init__(self, b):
        self.b = b
        self.red_any, self.red_text, self.yel, self.errors = compile_rules()
        self.hits, self.seen = [], set()

    def is_text_path(self, path):
        return path.startswith(self.b["journal"]) or path == "docs/decisions.md"

    def add(self, where, n, level, rule):
        if (where, n, rule) not in self.seen:
            self.seen.add((where, n, rule))
            self.hits.append({"where": where, "line": n, "level": level, "rule": rule})

    def line(self, where, n, text, text_mode):
        if text_mode and text.lstrip().lower().startswith("co-authored-by:"):
            return
        for rule, rx in (self.red_text if text_mode else self.red_any):
            for m in rx.finditer(text):
                v = m.groupdict().get("v")
                if v and PLACEHOLDER.match(v.strip("\"'")):
                    continue
                self.add(where, n, "red", rule)
        if text_mode:
            for rule, rx in self.yel:
                for m in rx.finditer(text):
                    if not ALLOW.search(m.group(0)):
                        self.add(where, n, "yellow", rule)

    def text(self, where, text):
        for n, l in enumerate(text.splitlines(), 1):
            self.line(where, n, l, True)

    def diff(self, diff_text, prefix=""):
        path, n = None, 0
        for l in diff_text.splitlines():
            if l.startswith("+++ "):
                p = l[4:].strip('"')
                path = p[2:] if p.startswith("b/") else None
            elif l.startswith("@@"):
                m = re.search(r"\+(\d+)", l)
                n = int(m.group(1)) if m else 0
            elif l.startswith("+") and path:
                self.line(prefix + path, n, l[1:], self.is_text_path(path))
                n += 1

    def commits(self, revs):
        for c in revs:
            self.text(c[:7] + ":message", out("log", "-1", "--format=%B", c))
            if len(out("log", "-1", "--format=%P", c).split()) < 2:  # merge commit 只看訊息，不看帶進來的別人的改動
                self.diff(git("show", "--format=", "-U0", "--no-color", "--no-ext-diff", c).stdout, c[:7] + ":")

    def result(self):
        red = sum(h["level"] == "red" for h in self.hits)
        return {"red": red, "yellow": len(self.hits) - red, "hits": self.hits, "errors": self.errors}


def unpushed(rev="HEAD"):
    return lines("rev-list", rev, "--not", "--remotes=origin")


def cmd_scan(a):
    b = base()
    s = Scanner(b)
    if a.staged:
        s.diff(git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff").stdout)
    if a.unpushed:
        s.commits(unpushed())
    if a.message:
        s.text("message", read_message(arg_path(a.message)))
    for f in a.file or []:
        p = arg_path(f)
        s.text(f, sys.stdin.read() if p == "-" else open(p, encoding="utf-8", errors="replace").read())
    r = s.result()
    emit(r, code=2 if r["red"] else 1 if r["yellow"] or r["errors"] else 0)


def read_message(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    return "\n".join(l for l in text.splitlines() if not l.startswith("#"))


def hit_summary(r):
    return "、".join("%s 第 %d 行（%s）" % (h["where"], h["line"], h["rule"]) for h in r["hits"] if h["level"] == "red")


# ---------- commit / push 前的硬性檢查 ----------

FORBIDDEN = re.compile(r"(^|/)(\.env(\.[^/]*)?|\.secret_key)$|\.(pem|key|db|sqlite3?)$|(^|/)[^/]* copy( \d+)?/", re.I)
ENV_TEMPLATE = re.compile(r"\.env\.(example|sample|template)$")


def staged_changes():
    """[(status, path)]，rename 的新舊路徑都算"""
    result = []
    for l in git("diff", "--cached", "--name-status", "--no-renames").stdout.splitlines():
        parts = l.split("\t")
        if len(parts) >= 2:
            result.append((parts[0][0], parts[-1]))
    return result


def cmd_preflight_commit(a):
    b = base()
    info = branch_info(b)
    errors, warnings = [], []
    op = info["in_progress"]
    merging = a.hook and op is not None  # 完成 merge / rebase 時 git 也會跑 hook，那時檢查的是別人帶進來的改動
    if op and not a.hook:
        errors.append("有進行中的 %s，先完成或放棄" % op)
    if not merging:
        if not info["branch"]:
            errors.append("detached HEAD，先切到自己的分支")
        elif info["branch"] == b["default"]:
            errors.append("不能在主分支 %s 上 commit，先開 <username>/<主題> 分支" % b["default"])
    changes = staged_changes()
    if not changes:
        errors.append("暫存區是空的")
    username = b["user"]["username"]
    if not username:
        errors.append("git 身分未設定或是電腦自動產生的 email")
    groups = set()
    for st, p in changes:
        if FORBIDDEN.search(p) and not ENV_TEMPLATE.search(p) and st != "D":
            errors.append("不能進版控：" + p)
        if p.startswith(b["journal"]):
            groups.add("journal")
            if merging:
                continue
            if username and not p.startswith(b["journal"] + username + "/"):
                errors.append("不能修改別人的日誌：" + p)
            elif st != "D" and DATE_MD.match(os.path.basename(p)):
                text = git("show", ":" + p).stdout
                if st == "A" or any(BLOCK.match(l) for l in text.splitlines()):
                    errs, warns = validate_text(p, text)
                    errors += ["日誌格式 %s：%s" % (p, e) for e in errs]
                    warnings += ["日誌 %s：%s" % (p, w) for w in warns]
        elif p == "docs/decisions.md":
            groups.add("decisions")
        elif p == ".mailmap":
            groups.add(".mailmap")
        else:
            groups.add("code")
    if len(groups) > 1 and not merging:
        errors.append("日誌、docs/decisions.md、.mailmap 要各自獨立一筆 commit，不要和其他改動混在一起（這次有：%s）"
                      % "、".join(sorted(groups)))
    if not merging:
        s = Scanner(b)
        s.diff(git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff").stdout)
        r = s.result()
        errors += r["errors"]
        if r["red"]:
            errors.append("🔴 疑似帳密或金鑰：" + hit_summary(r))
        if r["yellow"]:
            warnings.append("🟡 %d 處疑似個資或內部資訊，執行 scan --staged 看位置" % r["yellow"])
    emit({"ok": not errors, "branch": info["branch"], "files": [p for _, p in changes],
          "errors": errors, "warnings": warnings}, a.hook)


def cmd_preflight_message(a):
    b = base()
    s = Scanner(b)
    s.text("commit 訊息", read_message(arg_path(a.file)))
    r = s.result()
    errors = r["errors"] + (["🔴 commit 訊息疑似含帳密或金鑰：" + hit_summary(r)] if r["red"] else [])
    warnings = ["🟡 commit 訊息有 %d 處疑似個資或內部資訊" % r["yellow"]] if r["yellow"] else []
    emit({"ok": not errors, "errors": errors, "warnings": warnings}, a.hook)


def cmd_preflight_push(a):
    b = base()
    errors, warnings, revs = [], [], []
    default_ref = "refs/heads/" + b["default"]
    if a.hook:
        for l in sys.stdin.read().splitlines():
            parts = l.split()
            if len(parts) != 4:
                continue
            lref, lsha, rref, rsha = parts
            if rref == default_ref:
                errors.append("不能直接 push 到主分支 %s，請開 PR" % b["default"])
            if lsha == ZERO:
                continue
            if rsha != ZERO and not (ref_exists(rsha + "^{commit}") and ok("merge-base", "--is-ancestor", rsha, lsha)):
                errors.append("%s 不是 fast-forward（會覆蓋遠端的 commit），不 force push；先 fetch 並和使用者確認" % rref)
            revs += unpushed(lsha)
    else:
        info = branch_info(b)
        if info["in_progress"]:
            errors.append("有進行中的 %s" % info["in_progress"])
        if not info["branch"] or info["branch"] == b["default"]:
            errors.append("只能 push 自己的分支")
        revs = unpushed()
        if not revs:
            warnings.append("沒有要 push 的 commit")
    s = Scanner(b)
    s.commits(list(dict.fromkeys(revs)))
    r = s.result()
    errors += r["errors"]
    if r["red"]:
        errors.append("🔴 要 push 的 commit 疑似含帳密或金鑰：" + hit_summary(r))
    if r["yellow"]:
        warnings.append("🟡 要 push 的 commit 有 %d 處疑似個資或內部資訊" % r["yellow"])
    commits = [out("log", "-1", "--format=%h %s", c) for c in dict.fromkeys(revs)]
    emit({"ok": not errors, "commits": commits, "scan": {"red": r["red"], "yellow": r["yellow"]},
          "errors": errors, "warnings": warnings}, a.hook)


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("context")
    p.add_argument("--fetch", action="store_true", help="先 git fetch origin --prune")
    p.set_defaults(func=cmd_context)
    sub.add_parser("identities").set_defaults(func=cmd_identities)
    sub.add_parser("overlap").set_defaults(func=cmd_overlap)

    j = sub.add_parser("journal").add_subparsers(dest="jcmd", required=True)
    p = j.add_parser("find")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--user")
    g.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_journal_find)
    p = j.add_parser("validate")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_journal_validate)
    p = j.add_parser("coverage")
    p.add_argument("file")
    p.set_defaults(func=cmd_journal_coverage)

    p = sub.add_parser("scan")
    p.add_argument("--staged", action="store_true")
    p.add_argument("--unpushed", action="store_true", help="還沒 push 的 commit（訊息與改動）")
    p.add_argument("--message", help="commit 訊息檔")
    p.add_argument("--file", nargs="+", help="整份當成寫給人看的文字掃描；- 代表 stdin（例如 PR 內文）")
    p.set_defaults(func=cmd_scan)

    pf = sub.add_parser("preflight").add_subparsers(dest="pcmd", required=True)
    for name, func in (("commit", cmd_preflight_commit), ("push", cmd_preflight_push)):
        p = pf.add_parser(name)
        p.add_argument("--hook", action="store_true")
        p.set_defaults(func=func)
    p = pf.add_parser("message")
    p.add_argument("file")
    p.add_argument("--hook", action="store_true")
    p.set_defaults(func=cmd_preflight_message)

    a = ap.parse_args()
    if a.cmd == "scan" and not (a.staged or a.unpushed or a.message or a.file):
        ap.error("scan 要指定 --staged / --unpushed / --message / --file")
    a.func(a)


if __name__ == "__main__":
    main()
