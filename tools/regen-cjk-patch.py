#!/usr/bin/env python3
"""针对指定上游 tag 重新生成 overrides/cjk.patch（新增中文文字不再显示为问号）。

上游每个新 Release tag 都会改动 crates/edit/src/added.rs，补丁必须跟着重新生成，
否则「含中文输入修复」版的定时构建会在「应用补丁」步骤秒挂（这是设计如此，不是 bug）。

用法
----
    python tools/regen-cjk-patch.py v0.8.0              # 生成 + 自检，写入 work/cjk-v0.8.0.patch
    python tools/regen-cjk-patch.py v0.8.0 --push       # 同上，并推送到仓库 overrides/cjk.patch
    python tools/regen-cjk-patch.py --check-ref v0.7.1  # 只检查仓库里的现有补丁是否还能应用

设计要点
--------
* **不依赖 git / patch 命令**——维护用的 Windows 机器上没装，生成与验证全部用 difflib 完成；
  产物是标准 unified diff，在 runner（有 git）上 `git apply` 能正常吃下。
* **锚点唯一性校验**：6 处改动每一处的锚点在目标文件里必须**恰好命中 1 次**。
  命中 0 次或 >1 次立即中止，并打印实际命中数——这是「上游改了结构」的可靠信号，
  比打完补丁再去 CI 上碰运气强。
* **width() 参数自适应**：v0.7.1 是三参数 (s, size, bold)，v0.8.0 起是四参数 (s, size, bold, italic)。
  脚本自动判定，不需要人来记。
* **生成后立刻自检**：把生成的补丁应用回原始文件，必须逐字节等于修改后的文件。
* 补丁必须是**纯 LF**：仓库 `.gitattributes` 里有 `*.patch -text`，但本地生成时也要保证。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghapi
import minipatch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "awpde/pdfcraft-zh"
UPSTREAM = "storytold/pdfcraft"
TARGET = "crates/edit/src/added.rs"
WORK = os.path.abspath(os.path.join(HERE, "..", "work"))
BLOCK_FILE = os.path.join(HERE, "cjk-block.rs.txt")


# --------------------------------------------------------------------------
# 插入用的代码片段
# --------------------------------------------------------------------------

# 改动 2：first_undrawable 里，CJK 检查必须放在「泰文块之后、阿拉伯之前」。
#         紧贴上一行插入，不要多余空行。
CJK_UNDRAWABLE_CHECK = r"""// This build draws CJK (Chinese/Japanese/Korean) text with the Japanese fallback Type 3 font
// (`draw_cjk`), which upstream doesn't, so those characters are drawable here and must not be
// refused (#125). Judge it the way `draw_cjk` splits a line: what it hands to WinAnsi can still
// fail, which is exactly a character that is neither CJK nor WinAnsi-encodable.
if needs_cjk(&t.text) {
    return t.text.chars().find(|c| !is_cjk(*c) && pdfcraft_fonts::win_ansi_byte(*c).is_none());
}
"""

# 改动 3：is_cjk —— 必须排除泰文（上游已能用日文字体画泰文，误判会导致缺字形报错）
#         与上一函数之间保留一个空行（由调用处补 "\n"）。
CJK_IS_CJK = r"""/// A character WinAnsi can't encode and neither Arabic nor Thai covers: Chinese, Japanese, Korean and
/// other non-Latin scripts drawn through the Japanese fallback Type 3 font. Most Simplified Chinese
/// characters share codepoints with Japanese kanji, so Shippori Mincho covers them.
fn is_cjk(c: char) -> bool {
    !is_bidi_control(c) && !is_arabic(c) && !is_thai(c) && pdfcraft_fonts::win_ansi_byte(c).is_none()
}
"""

# 改动 5：draw 里的 CJK 分发（紧跟在 shaped 分支之后，不留空行）
CJK_DRAW_DISPATCH = r"""// CJK (Chinese/Japanese/Korean) text: drawn with a Type 3 fallback font whose glyphs
// are the Japanese document face, so characters no longer turn into `?`.
if needs_cjk(&t.text) {
    draw_cjk(doc, t, &name, taken, &mut fonts, &mut out)?;
    res.set(b"Font".to_vec(), Object::Dict(fonts));
    out.extend_from_slice(b"Q\n");
    return Ok((out, res));
}
"""


def dedent_lines(text, indent):
    return "".join(indent + line if line.strip() else line
                   for line in text.splitlines(keepends=True))


def replace_once(text, anchor, replacement, what):
    n = text.count(anchor)
    if n != 1:
        raise SystemExit(
            f"❌ 改动「{what}」的锚点在目标文件里命中 {n} 次（应为 1 次）。\n"
            f"   上游改了 {TARGET} 的结构，需要人工重新设计这个锚点。\n"
            f"   锚点内容：{anchor.strip()[:120]!r}")
    return text.replace(anchor, replacement)


# --------------------------------------------------------------------------
# 版本系判定
# --------------------------------------------------------------------------

def detect_series(src):
    """返回 'old'(三参数 width) / 'new'(四参数 width)，并打印判据。"""
    m = re.search(r"pub fn width\(([^)]*)\)", src)
    if not m:
        raise SystemExit("❌ 找不到 `pub fn width(` —— added.rs 结构可能大改，需要人工介入。")
    args = [a.strip() for a in m.group(1).split(",")]
    has_italic = any("italic" in a for a in args)
    print(f"   width() 签名：({m.group(1)}) → {'四参数 new 系' if has_italic else '三参数 old 系'}")
    print(f"   import 区  ：{'单行含 Std14（new 系）' if 'Std14' in src.split('use crate::')[0] else '多行块（old 系）'}")
    print(f"   泰文支持    ：{'有 is_thai' if 'fn is_thai' in src else '无（早于泰文支持）'}")
    return "new" if has_italic else "old"


def load_block(series):
    with open(BLOCK_FILE, encoding="utf-8", newline="") as f:
        block = f.read()
    if "\r" in block:
        raise SystemExit("❌ cjk-block.rs.txt 里出现了 CR —— 补丁必须是纯 LF。")
    extra = ", t.italic" if series == "new" else ""
    block = block.replace("{WIDTH_EXTRA}", extra)
    if "{WIDTH_EXTRA}" in block:
        raise SystemExit("❌ cjk-block.rs.txt 里还有未替换的 {WIDTH_EXTRA} 占位符。")
    return block


# --------------------------------------------------------------------------
# 6 处改动
# --------------------------------------------------------------------------

def apply_modifications(before, series):
    block = load_block(series)
    src = before

    # 1) 独立 use 语句（不改动上游原有 import 行，这样跨版本都成立）
    src = replace_once(
        src,
        "use unicode_bidi::{Level, ParagraphBidiInfo};",
        "use pdfcraft_fonts::{CraftFont, document_japanese_fonts_for_style, japanese_glyph_from};\n"
        "use unicode_bidi::{Level, ParagraphBidiInfo};",
        "1 import")

    # 2) first_undrawable 的 CJK 检查
    src = replace_once(
        src,
        "    // Arabic that nothing can draw: there's no face, or the face lacks it.\n",
        dedent_lines(CJK_UNDRAWABLE_CHECK, "    ") +
        "    // Arabic that nothing can draw: there's no face, or the face lacks it.\n",
        "2 first_undrawable 的 CJK 检查")

    # 3) is_cjk（排除泰文），与 shaped_arabic 之间空一行
    src = replace_once(
        src,
        "fn shaped_arabic(c: char) -> bool {\n    is_arabic(c) && !is_bidi_control(c)\n}\n",
        "fn shaped_arabic(c: char) -> bool {\n    is_arabic(c) && !is_bidi_control(c)\n}\n\n" +
        dedent_lines(CJK_IS_CJK, ""),
        "3 is_cjk")

    # 4) CJK 实现块（223 行）
    src = replace_once(
        src,
        "/// Content and resources for an item;",
        block + "/// Content and resources for an item;",
        "4 CJK 实现块")

    # 5) draw 里的分发：紧跟 shaped 分支之后（上游叫 draw_shaped / 老版本 draw_arabic）。
    #    判据用 `any(is_thai) ||`：`any(is_thai)` 在 first_undrawable 里也有一处（后面跟 `{`），
    #    只有 draw 里这个形如 `any(is_thai) || (...)`，能唯一定位。
    branch = "if t.text.chars().any(is_thai) ||"
    if src.count(branch) != 1:
        raise SystemExit(
            f"❌ 改动「5 draw 里的 CJK 分发」：`{branch}` 命中 {src.count(branch)} 次（应为 1 次）。\n"
            "   上游可能重命名/改写了 draw 里的 shaped 分支，需要人工确认插入点。")
    m = re.search(r"( *)" + re.escape(branch) + r"(?:.|\n)*?\n\1\}\n", src)
    if not m:
        raise SystemExit("❌ 改动 5：找到了 `any(is_thai) ||` 但没能匹配到它的分支结尾。")
    anchor = m.group(0)
    src = replace_once(src, anchor, anchor + dedent_lines(CJK_DRAW_DISPATCH, m.group(1)), "5 draw 里的 CJK 分发")

    # 6) own_fonts 清理 CJK Type 3 字体
    src = replace_once(
        src,
        '.filter(|w| w.starts_with(b"PCAr"))',
        '.filter(|w| w.starts_with(b"PCAr") || w.starts_with(b"PCCjk"))',
        "6 own_fonts 清理 PCCjk")

    return src


# --------------------------------------------------------------------------
# 静态检查
# --------------------------------------------------------------------------

def static_checks(before, after, series, patch_text):
    problems = []

    for name, text in (("原始文件", before), ("修改后文件", after)):
        if text.count("{") != text.count("}"):
            problems.append(f"{name} 花括号不配平：{{={text.count('{')} }}={text.count('}')}")
        if text.count("(") != text.count(")"):
            problems.append(f"{name} 圆括号不配平：(={text.count('(')} )={text.count(')')}")

    # width 参数个数必须与上游一致（上游签名带 self，调用处不带，比较时要剔除 self）
    sig = re.search(r"pub fn width\(([^)]*)\)", before).group(1)
    want = len([a for a in sig.split(",") if a.strip() != "self"])
    args = re.findall(r"t\.family\.width\(([^)]*)\)", after)
    bad = [a for a in args if len(a.split(",")) != want]
    if bad:
        problems.append(
            f"修改后 width 调用有 {len(bad)} 处参数个数（{len(bad[0].split(','))}）"
            f"与上游（{want}）不符：{bad[0]}")
    if not args:
        problems.append("修改后找不到 t.family.width( 调用")
    else:
        print(f"   width 调用 {len(args)} 处，均为 {want} 参数，与上游签名一致")

    # 原 import 行不能被改（独立 use 语句策略的意义所在）
    imp = re.search(r"^use pdfcraft_fonts::\{GlyphError.*$", before, re.M)
    if imp and imp.group(0) not in after:
        problems.append("上游原有 import 行被改动了 —— 应改用独立 use 语句")

    # 泰文排除必须在
    if "!is_thai(c)" not in after:
        problems.append("is_cjk 缺少 !is_thai(c) —— 泰文会被误判成 CJK")

    if b"\r" in patch_text.encode():
        problems.append("补丁含 CR，必须是纯 LF")

    return problems


# --------------------------------------------------------------------------

def cmd_check_ref(tag):
    """检查仓库里的现有补丁是否还能干净应用到指定 tag。"""
    before = ghapi.content(UPSTREAM, TARGET, ref=tag).decode("utf-8")
    patch = ghapi.content(REPO, "overrides/cjk.patch").decode("utf-8")
    try:
        after = minipatch.apply_unified(before, patch)
    except minipatch.PatchError as e:
        print(f"❌ {tag}：现有 overrides/cjk.patch **应用失败** —— {e}")
        print("   需要用本脚本针对该 tag 重新生成并推送。")
        return 1
    print(f"✅ {tag}：现有 overrides/cjk.patch 仍可干净应用（{len(before.splitlines())} → {len(after.splitlines())} 行）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="重新生成 overrides/cjk.patch")
    ap.add_argument("tag", nargs="?", help="上游 tag，例如 v0.8.0")
    ap.add_argument("--push", action="store_true", help="生成后推送到仓库")
    ap.add_argument("--check-ref", metavar="TAG", help="只检查现有补丁对 TAG 是否仍适用")
    args = ap.parse_args()

    if args.check_ref:
        sys.exit(cmd_check_ref(args.check_ref))
    if not args.tag:
        ap.error("需要给出上游 tag（或用 --check-ref）")

    os.makedirs(WORK, exist_ok=True)
    print(f"▶ 上游 {UPSTREAM} @ {args.tag} 的 {TARGET}")
    before = ghapi.content(UPSTREAM, TARGET, ref=args.tag).decode("utf-8")
    print(f"   {len(before.splitlines())} 行，{len(before)} 字节\n")

    print("▶ 判定版本系")
    series = detect_series(before)

    print("\n▶ 应用 6 处改动")
    after = apply_modifications(before, series)
    added = len(after.splitlines()) - len(before.splitlines())
    print(f"   原版 {len(before.splitlines())} 行 → 修改后 {len(after.splitlines())} 行（+{added}）")

    print("\n▶ 生成补丁")
    patch = minipatch.make_unified(before, after, TARGET)
    hunks = len(re.findall(r"^@@ ", patch, re.M))
    print(f"   {len(patch.encode())} 字节，{hunks} 个 hunk，CR 数 {patch.count(chr(13))}")

    print("\n▶ 自检：把补丁应用回原始文件，必须逐字节还原")
    try:
        minipatch.selfcheck(before, after, TARGET)
    except minipatch.PatchError as e:
        print(f"❌ {e}")
        return 1
    print("   ✅ 补丁可应用且结果一致")

    print("\n▶ 静态检查")
    problems = static_checks(before, after, series, patch)
    if problems:
        for p in problems:
            print(f"   ❌ {p}")
        return 1
    print("   ✅ 括号配平 / width 参数一致 / 原 import 未被改 / 排除泰文 / 纯 LF")

    dest = os.path.join(WORK, f"cjk-{args.tag}.patch")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(patch)
    print(f"\n📄 已写入 {dest}")

    if args.push:
        sha = ghapi.sha_of(REPO, "overrides/cjk.patch")
        ghapi.put_content(REPO, "overrides/cjk.patch", patch.encode("utf-8"),
                          f"重新生成 CJK 补丁以对准上游 {args.tag}", sha=sha)
        print(f"✅ 已推送 overrides/cjk.patch（sha {sha[:7]}）")
        print("   下一步：手动触发一次 upstream_ref=%s 的 zh-cjk 构建做端到端验证。" % args.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())