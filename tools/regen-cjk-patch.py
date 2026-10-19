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

# 改动 2：first_undrawable 里，CJK 检查必须放在「泰文块之后、阿拉伯/希伯来之前」。
#         锚点用泰文块的收尾（`return first_undrawable(&rest);` + 它的花括号），
#         而不是阿拉伯那句注释 —— 上游每加一种文字就会改那句注释
#         （v0.9.0 就从 "Arabic that…" 改成了 "Arabic or Hebrew that…"）。
CJK_UNDRAWABLE_CHECK = r"""// This build draws CJK (Chinese/Japanese/Korean) text with the Japanese fallback Type 3 font
// (`draw_cjk`), which upstream doesn't, so those characters are drawable here and must not be
// refused. Judge it the way `draw_cjk` splits a line: what it hands to WinAnsi can still fail,
// which is exactly a character that is neither CJK nor WinAnsi-encodable.
if needs_cjk(&t.text) {
    return t.text.chars().find(|c| !is_cjk(*c) && pdfcraft_fonts::win_ansi_byte(*c).is_none());
}
"""

# 改动 3：is_cjk —— 必须排除上游**自己能画**的文字。
#         排除列表由 upstream_script_guards() 从目标文件自动探测后填进 {GUARDS}。
CJK_IS_CJK = r"""/// A character WinAnsi can't encode and that none of the scripts upstream shapes (Arabic, Thai,
/// Hebrew, …) covers: Chinese, Japanese, Korean and other non-Latin scripts drawn through the
/// Japanese fallback Type 3 font. Most Simplified Chinese characters share codepoints with
/// Japanese kanji, so Shippori Mincho covers them.
///
/// Every script excluded here is one upstream can already draw with its own craft-fonts face.
/// Leaving one in would route it through the Japanese font instead, which has no glyph for it
/// (e.g. Thai and Hebrew already caused that). `upstream_script_guards()` regenerates this list
/// from the target file, so a new upstream script cannot silently break it.
fn is_cjk(c: char) -> bool {
    !is_bidi_control(c) && {GUARDS} && pdfcraft_fonts::win_ansi_byte(c).is_none()
}
"""

# 改动 5：draw 里的 CJK 分发，紧跟在 shaped 分支之后。
#         锚点用 `draw_shaped(...)` 调用本身，而不是 `any(is_thai) ||` 那个条件 ——
#         上游 v0.9.0 把条件重构成了多行 + `face_or_new(...)` 辅助闭包
#         （泰文那条判断在文件里出现了多次，靠它定位已经不可靠）。
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


def upstream_script_guards(src):
    """探测上游**自己能画**的文字脚本，生成 is_cjk 要排除的清单。

    上游每支持一种新文字，就会多出一个 `fn is_xxx(c: char) -> bool`（Arabic / Thai / Hebrew …）。
    这些字符**绝不能**被判成 CJK —— 否则会被送进日文字体，而日文字体没有对应字形，
    构建日志会报 `Japanese fallback font has no glyph for U+XXXX`。
    希伯来语在 v0.9.0 加入时就正好复现了泰文当初那个坑。

    自动探测而不是手写清单，是为了上游下次加新文字时不用改这里。
    """
    names = set(re.findall(r"^fn (is_\w+)\(c: char\) -> bool", src, re.M))
    names.discard("is_cjk")            # 我们自己加的
    names.discard("is_bidi_control")   # 方向标记，单独处理（不绘制但不归 CJK）
    ordered = sorted(names)
    print(f"   上游可自行绘制的文字脚本：{', '.join(ordered) or '（无）'}")
    print(f"   is_cjk 将排除：{', '.join(ordered) or '（无）'}")
    return " && ".join(f"!{n}(c)" for n in ordered)


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
    guards = upstream_script_guards(before)
    src = before

    # 1) 独立 use 语句（不改动上游原有 import 行，这样跨版本都成立）
    src = replace_once(
        src,
        "use unicode_bidi::{Level, ParagraphBidiInfo};",
        "use pdfcraft_fonts::{CraftFont, document_japanese_fonts_for_style, japanese_glyph_from};\n"
        "use unicode_bidi::{Level, ParagraphBidiInfo};",
        "1 import")

    # 2) first_undrawable 的 CJK 检查，插在泰文块之后、阿拉伯/希伯来之前。
    #    锚点 = 泰文块的收尾两行（语义稳定：无论上游之后加几种文字都在这个位置）
    tail = "        return first_undrawable(&rest);\n    }\n"
    if src.count(tail) != 1:
        raise SystemExit(
            f"❌ 改动「2 first_undrawable 的 CJK 检查」：泰文块收尾锚点命中 {src.count(tail)} 次（应为 1 次）。\n"
            "   上游可能重排了 first_undrawable（它每次新增文字脚本都会改这个函数），"
            "需要人工确认 CJK 判断该插在哪个分支之后。")
    src = replace_once(src, tail, tail + dedent_lines(CJK_UNDRAWABLE_CHECK, "    "),
                       "2 first_undrawable 的 CJK 检查")

    # 3) is_cjk，排除列表由上游自己的 is_xxx 自动生成
    is_cjk_src = CJK_IS_CJK.replace("{GUARDS}", guards)
    src = replace_once(
        src,
        "fn shaped_arabic(c: char) -> bool {\n    is_arabic(c) && !is_bidi_control(c)\n}\n",
        "fn shaped_arabic(c: char) -> bool {\n    is_arabic(c) && !is_bidi_control(c)\n}\n\n" +
        dedent_lines(is_cjk_src, ""),
        "3 is_cjk")

    # 4) CJK 实现块（223 行）
    src = replace_once(
        src,
        "/// Content and resources for an item;",
        block + "/// Content and resources for an item;",
        "4 CJK 实现块")

    # 5) draw 里的分发：紧跟 shaped 分支之后。锚点用 draw_shaped(...) 调用本身 ——
    #    上游 v0.9.0 把分支条件重构成多行 + face_or_new(...) 辅助闭包，
    #    「泰文那一行」在文件里已不再唯一，靠它定位会插错地方。
    call = "draw_shaped(doc, t, taken, &mut fonts, &mut out)?;"
    if src.count(call) != 1:
        raise SystemExit(
            f"❌ 改动「5 draw 里的 CJK 分发」：`{call}` 命中 {src.count(call)} 次（应为 1 次）。\n"
            "   上游可能重命名/重构了 draw_shaped 分支，需要人工确认插入点。")
    #    收尾括号要用「调用行缩进 - 4」去找：draw_shaped 调用体比它所属的 if 深一级。
    #    若直接按调用行的缩进找 `}`，会匹配到分支内部更深的括号，插到错误的位置
    #    （这个 bug 曾经真的发生过，被 verify_regen.py 抓出来）。
    call = "draw_shaped(doc, t, taken, &mut fonts, &mut out)?;"
    if src.count(call) != 1:
        raise SystemExit(
            f"❌ 改动「5 draw 里的 CJK 分发」：`{call}` 命中 {src.count(call)} 次（应为 1 次）。\n"
            "   上游可能重命名/重构了 draw_shaped 分支，需要人工确认插入点。")
    pos = src.index(call)
    line_start = src.rfind("\n", 0, pos) + 1
    seg = src[line_start:pos]
    body_indent = len(seg) - len(seg.lstrip())
    if body_indent < 5:
        raise SystemExit(f"❌ 改动 5：draw_shaped 调用缩进异常（{body_indent}），请人工确认。")
    close = "\n" + " " * (body_indent - 4) + "}\n"
    end = src.find(close, pos)
    if end == -1:
        raise SystemExit("❌ 改动 5：找到了 draw_shaped 调用，但找不到它所在 if 分支的收尾 `}`。")
    anchor = src[pos:end + len(close)]
    src = replace_once(src, anchor, anchor + dedent_lines(CJK_DRAW_DISPATCH, " " * (body_indent - 4)),
                       "5 draw 里的 CJK 分发")

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

    # 上游自己能画的每种文字，都必须在 is_cjk 里被排除
    upstream_scripts = set(re.findall(r"^fn (is_\w+)\(c: char\) -> bool", before, re.M))
    upstream_scripts -= {"is_cjk", "is_bidi_control"}
    body = re.search(r"fn is_cjk\(c: char\) -> bool \{\n(.*?)\n\}", after, re.S)
    if not body:
        problems.append("修改后找不到 is_cjk 的函数体")
    else:
        missing = sorted(n for n in upstream_scripts if f"!{n}(c)" not in body.group(1))
        if missing:
            problems.append(
                f"is_cjk 没排除上游可自行绘制的文字：{', '.join(missing)} —— "
                f"这些字符会被送进日文字体，导致缺字形（`Japanese fallback font has no glyph for U+XXXX`）")
        else:
            print(f"   is_cjk 已排除上游全部 {len(upstream_scripts)} 种可绘制文字："
                  f"{', '.join(sorted(upstream_scripts))}")

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