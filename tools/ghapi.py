"""ghapi —— GitHub API 极简封装。

为什么不用 `gh api`：在 PowerShell 里 `gh api <path> --jq '.[] | ...'` 的参数
经常被拆开而报 `accepts 1 arg(s), received 2`。这里统一走 curl + Python 解析，稳定。

需要环境里有 gh（只用它取 token）和 curl。
"""
import base64, json, os, subprocess, sys, tempfile, urllib.parse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GH = r"C:/Users/90714/tools/gh/bin/gh.exe"
CURL = r"C:\Windows\System32\curl.exe"


def token():
    r = subprocess.run([GH, "auth", "token"], capture_output=True)
    if r.returncode:
        raise RuntimeError("取不到 gh token，请先 `gh auth login`")
    return r.stdout.decode().strip()


def api(path, method="GET", raw=False, **params):
    """GET/POST/PUT 到 api.github.com。

    GET  : 参数进 query string
    其他 : 参数进 **JSON body**（GitHub 不接受 form-urlencoded）。
           body 写临时文件再 `curl -d @file`，避免 Windows 命令行长度上限
           （base64 后的文档很容易超过 32K）。
    params 里值为 None 的会被跳过。
    """
    url = f"https://api.github.com/{path.lstrip('/')}"
    args = [CURL, "-sS", "--ssl-no-revoke",
            "-H", f"Authorization: token {token()}",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28"]
    body_file = None
    if method == "GET":
        for k, v in params.items():
            if v is None:
                continue
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v})
    else:
        args += ["-X", method, "-H", "Content-Type: application/json"]
        body = {k: v for k, v in params.items() if v is not None}
        fd, body_file = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        args += ["-d", f"@{body_file}"]
    args.append(url)
    try:
        r = subprocess.run(args, capture_output=True)
    finally:
        if body_file:
            os.unlink(body_file)
    if raw:
        return r.stdout
    try:
        data = json.loads(r.stdout)
    except Exception:
        raise RuntimeError(f"响应不是 JSON：{r.stdout[:400]!r}")
    if isinstance(data, dict) and "documentation_url" in data:
        raise RuntimeError(f"GitHub API 错误 {data.get('status')}：{data.get('message')}")
    return data


def content(repo, path, ref="main"):
    """取文件原始字节；path 是目录时返回该目录下所有文件的字节串拼接（按文件名排序）。"""
    d = api(f"repos/{repo}/contents/{urllib.parse.quote(path)}", ref=ref)
    if isinstance(d, list):
        return b"".join(content(repo, e["path"], ref=ref) for e in sorted(d, key=lambda x: x["name"]))
    return base64.b64decode(d["content"])


def sha_of(repo, path, ref="main"):
    """取文件的 blob sha，更新文件时必须带上。"""
    return api(f"repos/{repo}/contents/{urllib.parse.quote(path)}", ref=ref)["sha"]


def put_content(repo, path, data, message, branch="main", sha=None):
    """新增或更新文件。更新已有文件必须传 sha。返回提交信息 dict。"""
    p = {"message": message,
         "content": base64.b64encode(data).decode(),
         "branch": branch}
    if sha:
        p["sha"] = sha
    return api(f"repos/{repo}/contents/{urllib.parse.quote(path)}", method="PUT", **p)


def delete_content(repo, path, message, branch="main", sha=None):
    """删除文件。GitHub 要求必须同时给 message、branch 和当前文件的 sha。"""
    p = {"message": message, "branch": branch,
         "sha": sha or sha_of(repo, path)}
    return api(f"repos/{repo}/contents/{urllib.parse.quote(path)}", method="DELETE", **p)