"""minipatch —— 不依赖 git / patch 命令的最小 unified diff 生成与应用。

为什么需要它：维护用的这台机器上**没有安装 git**（也没有 GNU patch），
而上游源码、更新补丁、`git apply --check` 这一整套验证都默认 git 存在。
这里用 difflib + 少量手工解析补齐，生成的文件是标准 unified diff，
在有 git 的环境（GitHub Actions runner）里 `git apply` 能正常吃下。

提供:
    make_unified(before, after, path, context=3) -> str
    apply_unified(original, patch, strict=True) -> str
"""
import difflib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(Exception):
    pass


def git_blob_sha(data: bytes) -> str:
    """git 的 blob 对象名：sha1("blob <长度>\\0" + 内容)。用于让生成的补丁与 git 输出同形。"""
    import hashlib
    h = hashlib.sha1()
    h.update(b"blob " + str(len(data)).encode() + b"\0" + data)
    return h.hexdigest()


def make_unified(before, after, path, context=3, header=True, with_index=True):
    """生成 git-apply 兼容的 unified diff（LF 行尾），格式与 `git diff` 对齐：

        diff --git a/<path> b/<path>
        index <旧blob>..<新blob> 100644
        --- a/<path>
        +++ b/<path>
        @@ ...
    """
    b = before.splitlines()
    a = after.splitlines()
    if b == a:
        return ""
    out = []
    if header:
        out.append(f"diff --git a/{path} b/{path}")
        if with_index:
            old = git_blob_sha(before.encode("utf-8"))
            new = git_blob_sha(after.encode("utf-8"))
            out.append(f"index {old[:7]}..{new[:7]} 100644")
    out.extend(difflib.unified_diff(b, a, fromfile=f"a/{path}", tofile=f"b/{path}",
                                    n=context, lineterm=""))
    return "\n".join(out) + "\n"


def _parse_hunks(patch_lines):
    """产出 (旧起始行(1-based), 旧行数, 新起始行, 新行数, [hunk 行])。"""
    i = 0
    while i < len(patch_lines):
        m = HUNK_RE.match(patch_lines[i])
        if not m:
            i += 1
            continue
        os_, oc, ns, nc = (int(g) if g else (1 if os_ == 0 else 0) for g in m.groups())
        # @@ -0,0 +1,n @@ 的简写 "-a" 表示 a=0 行数
        body, i = [], i + 1
        while i < len(patch_lines):
            ln = patch_lines[i]
            if ln.startswith("@@") or ln.startswith("diff --git") or ln.startswith("--- "):
                break
            if ln == "" or ln[0] in " +-":
                body.append(ln)
                i += 1
            elif ln.startswith("\\"):  # "\ No newline at end of file"
                i += 1
            else:
                break
        yield os_ or 1, oc or 0, ns or 1, nc or 0, body


def apply_unified(original, patch, strict=True):
    """把 unified diff 应用到 original 上，返回结果文本。"""
    src = original.splitlines()
    result, cursor, hunks = [], 0, list(_parse_hunks(patch.splitlines()))

    for os_, oc, ns, nc, body in hunks:
        start = os_ - 1
        # 容错：允许整体偏移（git 的 fuzz 行为），便于手工核对
        offset = None
        for cand in (start, *[start + d for d in (1, -1, 2, -2, 3, -3, 5, -5, 10, -10)]):
            if cand >= 0 and src[cand:cand + oc] == [l[1:] for l in body if l[:1] in (" ", "-")]:
                offset = cand
                break
        if offset is None:
            if strict:
                raise PatchError(f"hunk @@ -{os_},{oc} @@ 无法应用（上下文不匹配）")
            offset = start
        result.extend(src[cursor:offset])
        cursor = offset
        for line in body:
            if not line:
                raise PatchError("hunk 中出现空行（补丁文件疑似被 CRLF 污染）")
            kind, text = line[0], line[1:]
            if kind == " ":
                if cursor < len(src) and src[cursor] == text:
                    result.append(text)
                    cursor += 1
                elif strict:
                    raise PatchError(f"上下文不匹配 @ 行 {cursor + 1}: {text!r} != {src[cursor: cursor+1]!r}")
                else:
                    result.append(text)
            elif kind == "-":
                if cursor < len(src) and src[cursor] == text:
                    cursor += 1
                elif strict:
                    raise PatchError(f"待删行不匹配 @ 行 {cursor + 1}: {text!r}")
            elif kind == "+":
                result.append(text)
        # 多行合并：删除行不会前进输出指针，只影响 src 读取；此处无需处理
    result.extend(src[cursor:])
    return "\n".join(result) + "\n"


def selfcheck(before, after, path):
    """生成补丁 → 再应用回来，必须逐字节还原。失败抛 PatchError。"""
    p = make_unified(before, after, path)
    back = apply_unified(before, p)
    if back != after:
        for n, (x, y) in enumerate(zip(back.splitlines(), after.splitlines()), 1):
            if x != y:
                raise PatchError(f"自检失败 @ 行 {n}: {x!r} != {y!r}")
        raise PatchError(f"自检失败：行数 {len(back.splitlines())} != {len(after.splitlines())}")
    return p


if __name__ == "__main__":
    # 自检：对自己生成再应用，验证实现本身没问题
    src = "a\nb\nc\nd\n"
    dst = "a\nB\nc\nD\n"
    p = selfcheck(src, dst, "demo.txt")
    print(p)
    print("✅ 自检通过" if apply_unified(src, p) == dst else "❌ 自检失败")