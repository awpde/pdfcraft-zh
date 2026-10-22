"""ghapi —— GitHub API 极简封装。

为什么不用 `gh api`：在 PowerShell 里 `gh api <path> --jq '.[] | ...'` 的参数
经常被拆开而报 `accepts 1 arg(s), received 2`。这里统一走 curl + Python 解析，稳定。

需要环境里有 gh（只用它取 token）和 curl。
"""
import base64, json, os, subprocess, sys, tempfile, urllib.parse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GH = r"C:/Users/90714/tools/gh/bin/gh.exe"
CURL = r"C:\Windows\System32\curl.exe"

# 本机 hosts 被 GitHubHosts 工具改写过（2026-10-20 装的，在桌面 GitHubHosts\ 下）。
# 它把 api.github.com 指到了 20.27.177.113 —— 那个 IP 能开 github.com 网页，
# 但 **api.github.com 在它上面返回 301**（指向 github.com/repos/… 的非法地址），
# raw.githubusercontent.com 更是直接连接被重置。等于 API 全废。
#
# 下面这组是实测可用的 API IP，直接用 curl --resolve 绕过 hosts，
# 不需要管理员权限、也不改用户的系统配置。
API_FALLBACK_IPS = ["20.205.243.168", "140.82.112.6", "140.82.114.6", "140.82.113.6"]


def _curl(url, extra_args=None, method="GET", body=None):
    """发一次请求。extra_args 用来附加 --resolve 等参数。

    必须设超时 —— hosts 指向坏 IP 时连接可能一直挂着不返回。
    """
    args = [CURL, "-sS", "--ssl-no-revoke", "--connect-timeout", "12", "--max-time", "60"]
    if extra_args:
        args += extra_args
    args += ["-H", f"Authorization: token {token()}",
             "-H", "Accept: application/vnd.github+json",
             "-H", "X-GitHub-Api-Version: 2022-11-28"]
    if method != "GET":
        args += ["-X", method, "-H", "Content-Type: application/json"]
    if body is not None:
        args += ["-d", "@" + body]
    args.append(url)
    return subprocess.run(args, capture_output=True)


def token():
    r = subprocess.run([GH, "auth", "token"], capture_output=True)
    if r.returncode:
        raise RuntimeError("取不到 gh token，请先 `gh auth login`")
    return r.stdout.decode().strip()


def _is_json(b):
    """能否解析成 JSON。空响应 / HTML / 301 文本都算不行。"""
    if not b:
        return False
    s = b.lstrip()[:1]
    if s not in (b"{", b"["):
        return False
    try:
        json.loads(b)
        return True
    except Exception:
        return False


def api(path, method="GET", raw=False, **params):
    """GET/POST/PUT 到 api.github.com。

    GET  : 参数进 query string
    其他 : 参数进 **JSON body**（GitHub 不接受 form-urlencoded）。
           body 写临时文件再 `curl -d @file`，避免 Windows 命令行长度上限
           （base64 后的文档很容易超过 32K）。
    params 里值为 None 的会被跳过。

    走不通时会自动改用 `--resolve` 指定可用的 API IP（绕过被改坏的 hosts）。
    """
    url = f"https://api.github.com/{path.lstrip('/')}"
    body_file = None
    if method == "GET":
        for k, v in params.items():
            if v is None:
                continue
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v})
    else:
        body = {k: v for k, v in params.items() if v is not None}
        fd, body_file = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
    try:
        r = _curl(url, method=method, body=body_file)
        out = r.stdout
        # hosts 指向坏 IP 时，API 会返回 301 或空响应 —— 换 IP 重试。
        # 判据是「能不能解析成 JSON」，不纠结 curl 返回码：
        # 实测部分 IP 会中途断开（rc=56）但数据其实已经完整。
        if not _is_json(out):
            for ip in API_FALLBACK_IPS:
                r = _curl(url, extra_args=["--resolve", f"api.github.com:443:{ip}"],
                          method=method, body=body_file)
                if _is_json(r.stdout):
                    out = r.stdout
                    break
    finally:
        if body_file:
            os.unlink(body_file)
    if raw:
        return out
    try:
        data = json.loads(out)
    except Exception:
        raise RuntimeError(f"响应不是 JSON：{out[:400]!r}")
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