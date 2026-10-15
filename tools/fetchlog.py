"""fetchlog —— 下载并筛选 GitHub Actions 的 job 日志。

「永远不要只看绿对勾」这条铁律靠它落实：它把 build job 的原始日志拉下来，
按正则筛出关键行（补丁是否真的应用、图标是否真的替换、翻译是否真的补齐……）。

用法
----
    python tools/fetchlog.py <repo> <run_id> "<正则>"
    python tools/fetchlog.py awpde/pdfcraft-zh 38679958881 "已应用 CJK|已替换|补充译文|ok MSI"
    python tools/fetchlog.py awpde/pdfcraft-zh 38679958881          # 不带正则 = 打全量

说明：GitHub 的 job 日志接口会 302 到对象存储，直连 Python 会丢 Authorization 头导致 403，
所以这里用 curl 跟随重定向（目标 URL 自带签名，不需要再带 auth）。
"""
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ghapi

CURL = ghapi.CURL


def fetch(repo, run_id, outdir=None):
    outdir = outdir or os.path.join(HERE, "..", "work", "logs")
    os.makedirs(outdir, exist_ok=True)
    jobs = ghapi.api(f"repos/{repo}/actions/runs/{run_id}/jobs")["jobs"]
    tok = ghapi.token()
    chunks = []
    for j in jobs:
        jid = j["id"]
        dest = os.path.join(outdir, f"{repo.replace('/', '_')}-{run_id}-{jid}.log")
        url = f"https://api.github.com/repos/{repo}/actions/jobs/{jid}/logs"
        r = subprocess.run(
            [CURL, "-sS", "--ssl-no-revoke", "-L",
             "-H", f"Authorization: token {tok}",
             "-H", "Accept: application/vnd.github+json", url, "-o", dest],
            capture_output=True)
        if r.returncode:
            print(f"curl 失败：{r.stderr.decode('utf-8', 'replace')}", file=sys.stderr)
            continue
        with open(dest, encoding="utf-8", errors="replace") as f:
            chunks.append(f.read())
    return "\n".join(chunks)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    repo, run_id = sys.argv[1], sys.argv[2]
    pattern = sys.argv[3] if len(sys.argv) > 3 else None

    text = re.sub(r"\x1b\[[0-9;]*m", "", fetch(repo, run_id))

    if not pattern:
        print(text)
        return 0
    hits = [ln for ln in text.splitlines() if re.search(pattern, ln)]
    if not hits:
        print("❌ 没有匹配到任何行 —— 停下来查一下：run_id 对不对、该 job 名字变没变、"
              "或者这些定制其实根本没执行（这正是铁律 1 要抓的情况）。")
        return 1
    for ln in hits:
        print(ln)
    print(f"\n共 {len(hits)} 行匹配 /{pattern}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())