#!/usr/bin/env python3
"""sync.py — 把工作区改动通过 GitHub API 推到远程仓库。

为什么存在：本机网络代理只放行 api.github.com，直连 github.com 的
`git push` 会被代理以 CONNECT tunnel 502 拒绝，提权也无法绕过。
本脚本全部流量走 api.github.com，与 `gh` CLI 同一条通路。

用法：
    python3 scripts/sync.py                     # 自动提交信息
    python3 scripts/sync.py -m "feat: 新增 xx"   # 指定提交信息
    python3 scripts/sync.py --dry-run           # 只看会改什么，不推送
    python3 scripts/sync.py --force             # 远程被别人更新时也强行覆盖

行为说明：
- 文件集 = `git ls-files --cached --others --exclude-standard`
  （已跟踪 + 未被忽略的新文件；被 .gitignore 忽略的不会推）
- 本地删除的文件会同步从远程删除
- 没有变化时什么都不做（幂等）
- 推送后本地 .git 历史与远程不一致属正常现象（git 协议被墙），
  请以工作区文件为准，不要在本仓库使用 git commit/push。
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

OWNER = "openfcp"
REPO = "awesome-financial-skills"
BRANCH = "main"


def repo_root():
    """向上找 git 仓库根：先看脚本所在目录，找不到再看当前工作目录。"""
    start = os.path.dirname(os.path.abspath(__file__))
    try:
        return subprocess.check_output(
            ["git", "-C", start, "rev-parse", "--show-toplevel"]
        ).decode().strip()
    except subprocess.CalledProcessError:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=os.getcwd()
        ).decode().strip()


REPO_DIR = repo_root()
SHA_FILE = os.path.join(REPO_DIR, ".commit-sha")


def record_sha(sha):
    """记录远程当前提交，供 build.py 生成 dsh 索引里 git 源的 commit 字段。"""
    try:
        with open(SHA_FILE, "w", encoding="utf-8") as f:
            f.write(sha + "\n")
    except OSError:
        pass


def api(method, path, payload=None, tries=5):
    """调用 GitHub REST API。gh CLI 已登录，token 从它那里取。

    HTTP 错误不直接抛出，返回 {"_error": code, "_body": ...} 由调用方判断——
    空仓库等"预期内"的错误需要分支处理。

    但 502/503/504 和隧道错误要重试：本机出口代理对 api.github.com 会偶发
    502（CONNECT tunnel failed），urllib 抛的是 URLError 而不是 HTTPError，
    不重试就直接 traceback 退出。publish_market.py 早就加了这层，这里补齐。
    """
    token = subprocess.check_output(["gh", "auth", "token"]).decode().strip()
    url = f"https://api.github.com{path}"
    data = json.dumps(payload).encode() if payload is not None else None

    last = None
    for i in range(tries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "awesome-financial-skills-sync")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last = {"_error": e.code, "_body": e.read().decode()[:400]}
            if e.code in (502, 503, 504) and i < tries - 1:
                time.sleep(5 * (i + 1))
                continue
            return last
        except (urllib.error.URLError, TimeoutError) as e:
            last = {"_error": 0, "_body": f"网络失败（第 {i + 1}/{tries} 次）：{e}"}
            if i < tries - 1:
                time.sleep(5 * (i + 1))
                continue
    return last


def die(context, err):
    raise SystemExit(f"[sync] GitHub API {context} -> HTTP {err['_error']}\n{err.get('_body', '')}")


def blob_sha(path):
    """本地计算 git blob sha，免一次 API 调用就能判断文件是否变化。"""
    raw = open(path, "rb").read()
    h = hashlib.sha1()
    h.update(f"blob {len(raw)}\0".encode() + raw)
    return h.hexdigest()


def file_mode(path):
    """保留可执行位。

    以前一律写 100644，结果 install.sh / release.sh 推上去就丢了 +x，别人
    clone 下来得先 chmod 才能跑。tree API 的 mode 是显式字段，不写就没有。
    """
    return "100755" if os.access(path, os.X_OK) else "100644"


def collect_local_files():
    """已跟踪 + 未被忽略的新文件；本地已删除（rm 了但没 git rm）的排除掉，
    否则会在读取内容时崩溃，也无法同步为远程删除。

    必须用 -z：默认 core.quotepath=true 会把非 ASCII 路径输出成
    "plugins/x/06-\\350\\241\\214.md" 这种 C 风格转义串，再按空白 split 就
    彻底散架——结果是中文名的资源文件被静默判成「已删除」，在远端真的删掉。
    -z 用 NUL 分隔、且完全不做转义，同时也不会被路径里的空格搞坏。
    """
    raw = subprocess.check_output(
        ["git", "-C", REPO_DIR, "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    )
    out = [p for p in raw.decode("utf-8", "surrogateescape").split("\0") if p]
    return sorted(f for f in set(out) if os.path.exists(os.path.join(REPO_DIR, f)))


def main():
    parser = argparse.ArgumentParser(description="通过 GitHub API 推送工作区改动")
    parser.add_argument("-m", "--message", help="提交信息")
    parser.add_argument("--dry-run", action="store_true", help="只显示将发生的变更")
    parser.add_argument("--force", action="store_true", help="基于远程当前状态强制覆盖推送")
    args = parser.parse_args()

    local_files = collect_local_files()
    # 比较 (mode, sha)：只比 sha 会漏掉"内容没变、可执行位变了"的情况
    local = {f: (file_mode(os.path.join(REPO_DIR, f)), blob_sha(os.path.join(REPO_DIR, f)))
             for f in local_files}

    # 1) 拿远程基线。注意：空仓库的 GET ref 返回 409（不是 404）。
    #    且空仓库无法直接建 tree/commit（同样 409），需先用 contents API 初始化。
    ref = api("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")
    if "_error" in ref:
        print("[sync] 远程为空，先初始化仓库 ...")
        init = api(
            "PUT",
            f"/repos/{OWNER}/{REPO}/contents/.gitignore",
            {"message": "chore: init repository", "content": base64.b64encode(b".DS_Store\n").decode()},
        )
        if "_error" in init:
            die("init repository", init)
        ref = api("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")
        if "_error" in ref:
            die("get ref after init", ref)

    parent_sha = ref["object"]["sha"]
    parent = api("GET", f"/repos/{OWNER}/{REPO}/git/commits/{parent_sha}")
    if "_error" in parent:
        die("get base commit", parent)
    base_tree_sha = parent["tree"]["sha"]

    remote_tree = api("GET", f"/repos/{OWNER}/{REPO}/git/trees/{base_tree_sha}?recursive=1")
    if "_error" in remote_tree:
        die("get base tree", remote_tree)
    remote = {t["path"]: (t["mode"], t["sha"]) for t in remote_tree["tree"] if t["type"] == "blob"}

    added = [p for p in local if p not in remote]
    modified = [p for p in local if p in remote and remote[p] != local[p]]
    deleted = [p for p in remote if p not in local]

    if not (added or modified or deleted):
        print("[sync] 工作区与远程一致，无需推送。")
        record_sha(parent_sha)
        print(f"[sync] 远程 HEAD = {parent_sha}")
        return 0

    for label, paths in (("新增", added), ("修改", modified), ("删除", deleted)):
        for p in paths:
            print(f"  {label}  {p}")

    if args.dry_run:
        print("[sync] dry-run，未推送。")
        return 0

    # 3) 只为变化文件建 blob，未动的路径由 base_tree 继承
    tree = []
    for p in added + modified:
        raw = open(os.path.join(REPO_DIR, p), "rb").read()
        blob = api(
            "POST",
            f"/repos/{OWNER}/{REPO}/git/blobs",
            {"content": base64.b64encode(raw).decode(), "encoding": "base64"},
        )
        if "_error" in blob:
            die(f"create blob {p}", blob)
        tree.append({"path": p, "mode": local[p][0], "type": "blob", "sha": blob["sha"]})
        print(f"  blob {p} -> {blob['sha'][:10]}")
    for p in deleted:
        # GitHub tree API：sha 为 null 表示删除该路径
        tree.append({"path": p, "mode": "100644", "type": "blob", "sha": None})
        print(f"  del  {p}")

    new_tree = api("POST", f"/repos/{OWNER}/{REPO}/git/trees", {"base_tree": base_tree_sha, "tree": tree})
    if "_error" in new_tree:
        die("create tree", new_tree)

    # 4) 提交并更新分支
    n = len(added) + len(modified) + len(deleted)
    message = args.message or f"sync: {n} 个文件变更（新增 {len(added)} / 修改 {len(modified)} / 删除 {len(deleted)}）"
    commit = api(
        "POST",
        f"/repos/{OWNER}/{REPO}/git/commits",
        {"message": message, "tree": new_tree["sha"], "parents": [parent_sha]},
    )
    if "_error" in commit:
        die("create commit", commit)

    # fast-forward 更新；远程若已被他人推进，除非 --force 否则放弃，避免覆盖别人
    ref_path = f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}"
    if args.force:
        upd = api("PATCH", ref_path, {"sha": commit["sha"], "force": True})
        if "_error" in upd:
            die("force update ref", upd)
    else:
        current = api("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")
        if "_error" in current:
            die("re-check ref", current)
        if current["object"]["sha"] != parent_sha:
            raise SystemExit(
                f"[sync] 远程 {BRANCH} 已前进（{parent_sha[:8]} -> {current['object']['sha'][:8]}），"
                "放弃推送以免覆盖他人提交。确认无冲突后加 --force 重试。"
            )
        upd = api("PATCH", ref_path, {"sha": commit["sha"]})
        if "_error" in upd:
            die("update ref", upd)

    url = f"https://github.com/{OWNER}/{REPO}/commit/{commit['sha']}"
    record_sha(commit["sha"])
    print(f"[sync] 完成 {commit['sha'][:10]}  {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
