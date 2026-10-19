"""verify_regen —— 回归测试：regen-cjk-patch.py 是否忠实复现仓库里现有的 cjk.patch。

**推送任何重新生成的补丁之前都应该先跑这个。**

原理：同一个上游文件，两条独立路径得到同一个结果 ——
  路径 A：上游原版  +  应用仓库现有的 overrides/cjk.patch
  路径 B：上游原版  +  regen-cjk-patch.py 的 6 处改动
两条路径的产物必须**逐字节一致**。不一致就说明脚本已经跑偏，
拿它去重新生成补丁只会把上游代码改坏。

用法: python tools/verify_regen.py [tag]
"""
import difflib
import importlib.util
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ghapi
import minipatch

spec = importlib.util.spec_from_file_location("regen", os.path.join(HERE, "regen-cjk-patch.py"))
regen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regen)


def strip_rust_comments(src):
    """去掉 Rust 注释，只留代码 —— 用来区分「行为变了」和「只是改了注释措辞」。

    处理 // 行注释（跳过字符串字面量里的 //，例如 "https://"）和 /* */ 块注释。
    """
    out = []
    in_block = False
    for line in src.splitlines():
        res, i, n, quote = [], 0, len(line), None
        while i < n:
            if in_block:
                if line.startswith("*/", i):
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            ch = line[i]
            if quote:
                res.append(ch)
                if ch == "\\":
                    if i + 1 < n:
                        res.append(line[i + 1])
                        i += 1
                elif ch == quote:
                    quote = None
                i += 1
                continue
            if ch in "\"'":
                quote = ch
                res.append(ch)
                i += 1
                continue
            if line.startswith("//", i):
                break
            if line.startswith("/*", i):
                in_block = True
                i += 2
                continue
            res.append(ch)
            i += 1
        code = "".join(res).rstrip()
        # 整行都是注释的，整行丢掉（否则「只改注释」会被误判成代码差异）
        if not code and line.strip():
            continue
        out.append(code)
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    # 必须显式给 tag：脚本无法从 cjk.patch 本身反推出它对准的是哪个上游版本
    tag = sys.argv[1]

    before = ghapi.content(regen.UPSTREAM, regen.TARGET, ref=tag).decode("utf-8")
    existing = ghapi.content(regen.REPO, "overrides/cjk.patch").decode("utf-8")

    try:
        truth = minipatch.apply_unified(before, existing)
    except minipatch.PatchError as e:
        print(f"⚠️  {tag}：仓库现有的 cjk.patch 已经应用不上去了（{e}）")
        print("    这通常意味着上游又更新了 —— 那正是该用 regen-cjk-patch.py 重新生成的时候，")
        print("    但这个回归测试届时无法用（没有基准可比）。")
        return 2

    mine = regen.apply_modifications(before, regen.detect_series(before))

    print(f"\ntag={tag}")
    print(f"  基准（仓库现有补丁）: {len(truth.splitlines())} 行, {len(truth.encode())} 字节")
    print(f"  脚本（6 处改动）    : {len(mine.splitlines())} 行, {len(mine.encode())} 字节")

    if truth == mine:
        print("  ✅ 逐字节一致 —— regen-cjk-patch.py 可安全用于重新生成")
        return 0

    # 字节不一致时，再比一次「忽略注释的代码」——
    # 只改了注释措辞不算回归；代码有任何差异就是真问题。
    a, b = strip_rust_comments(truth), strip_rust_comments(mine)
    if a == b:
        print("  ⚠️  代码完全一致，仅注释措辞不同（不算行为回归）")
        return 0
    print("  ❌ 代码不一致，逐行差异：")
    for i, line in enumerate(difflib.unified_diff(a.splitlines(), b.splitlines(),
                                                  "existing-patch", "regen-script",
                                                  lineterm="", n=2)):
        print("   ", line)
        if i > 60:
            print("    ...（截断）")
            break
    return 1


if __name__ == "__main__":
    sys.exit(main())