# -*- coding: utf-8 -*-
"""生成（或重新生成）CJK 修复补丁：检查锚点、改造目标文件、产出补丁并验证。

用法：
    python regen-patch.py <tag> [--out <补丁路径>] [--src <上游源码目录>] [--no-verify]

一次运行生成**两个**补丁：cjk.patch（中文输入修复，5 个文件）和 cursor.patch
（高对比软光标，1 个文件，改自上游 PR #6173；上游合并 #6173 后整个摘除）。

在 GitHub Actions 里：
    python tools/regen-patch.py "$REF" --src src --out "$RUNNER_TEMP/cjk.patch" --no-verify

设计要点（每一条都对应一次真实踩坑）：
  * 锚点全部用「内容匹配」而不是行号 —— 上游改文件也不会错位；
  * 任何一处锚点找不到、或在文件里出现多次 → **直接失败并逐条列出原因**，
    绝不产出「半个补丁」（半个补丁比没有补丁更危险：它可能编译通过但行为不对）；
  * 补丁是纯 LF（不用 CRLF），CI 的 checkout 正好是 LF；
  * `--src` 给出已 checkout 的上游源码目录时直接用它作基线（CI 里就是 src/），
    不重新下载 —— 省一次 API 配额，也避免下载到不同 commit。

环境变量：
    GITHUB_TOKEN / GH_TOKEN   GitHub token（CI 里自动注入）
    GITHUB_API_URL            API 根地址（CI 里自动注入）
    GH_API_IP                 API 域名要解析到的 IP（本地 DNS 被劫持时用；留空则不指定）
"""
import base64
import json
import os
import subprocess
import sys

# GitHub Actions 的 Windows runner 上 Python 默认用 cp1252 输出，中文 print 会抛
# UnicodeEncodeError 直接把构建弄挂（2026-11-01 踩过）。这里强制改成 UTF-8。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

API = os.environ.get('GITHUB_API_URL', 'https://api.github.com').rstrip('/')
GH_IP = os.environ.get('GH_API_IP', '').strip()
REPO = 'storytold/pdfcraft'
W = os.environ.get('TEMP', '/tmp')

FILES = [
    'crates/edit/src/text.rs',
    'crates/edit/src/text/fallback.rs',
    'crates/edit/src/added/layout.rs',
    'crates/edit/src/added/draw.rs',
    'apps/pdfcraft/src/main.rs',
    # The high-contrast soft-cursor patch (adapted from upstream PR #6173) touches one more
    # file; its diff is split off into cursor.patch in the diff step below, so the two
    # patches can be regenerated in one run and retired separately (cursor's ends the day
    # upstream merges #6173).
    'crates/ui-egui/src/canvas/page_cursor.rs',
]
CURSOR_FILE = 'crates/ui-egui/src/canvas/page_cursor.rs'
# Files that belong to cjk.patch (everything except the cursor file):
CJK_PREFIXES = ('crates/edit', 'apps')


def get_token():
    """取 GitHub token。

    注意：**不能**在这里无条件调用 gh CLI —— CI runner 上没有 gh，
    FileNotFoundError 会直接把构建弄挂（2026-11-17 踩过）。
    所以 gh 只是本地开发的兜底，找不到就返回空串，由 curl() 给出清晰报错。
    """
    t = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if t and t.strip():
        return t.strip()
    exe = os.environ.get('GH_CLI', 'C:/Users/90714/tools/gh/bin/gh.exe')
    if os.path.isfile(exe):
        r = subprocess.run([exe, 'auth', 'token'], capture_output=True, text=True)
        return r.stdout.strip()
    return ''


def curl(url):
    token = get_token()
    if not token:
        raise RuntimeError(
            '没有 GitHub token：请设置 GITHUB_TOKEN（或 GH_TOKEN）环境变量。'
            '（用 --src 指定本地源码目录时本来就不需要 token）')
    args = ['curl', '-sSL', '--noproxy', '*', '--ssl-no-revoke']
    if GH_IP:
        host = url.split('/')[2]
        args += ['--resolve', f'{host}:443:{GH_IP}']
    args += ['-H', f'Authorization: token {token}',
             '-H', 'Accept: application/vnd.github+json', url]
    r = subprocess.run(args, capture_output=True)
    try:
        return json.loads(r.stdout.decode('utf-8', errors='replace'))
    except Exception:
        raise RuntimeError(f'API 返回的不是 JSON: {url}\n{r.stdout[:200]!r}')


def fetch(path, ref):
    d = curl(f'{API}/repos/{REPO}/contents/{path}?ref={ref}')
    if 'content' not in d:
        raise RuntimeError(f'{path}@{ref}: {str(d)[:200]}')
    return base64.b64decode(d['content'])


# ─── 软光标补丁的锚点（对准 v0.22.0 的 page_cursor.rs，单文件单锚点）───
# 与 PR #6173 的差异：指针在 resolve 内部自取（签名不变 → canvas.rs 与上游 tests 零改动）；
# 默认启用，PDFCRAFT_SOFT_CURSOR=0 可关；不带 PR 的测试 hunk。
CURSOR_OLD = '''    /// Sets the cursor, once, to the icon of the claim on the highest layer `tool` reaches, and
    /// returns the tip: that claim's own, or else the description. With no such claim the cursor
    /// is left as it is. The claims are spent: the next frame starts with none.
    pub(crate) fn resolve(&mut self, ctx: &egui::Context, tool: QuickTool) -> Option<String> {
        let PageCursor { claims, description } = std::mem::take(self);
        let winner = Self::winner(claims, tool);
        if let Some(w) = &winner {
            ctx.set_cursor_icon(w.icon);
        }
        winner.and_then(|w| w.tip).or(description.map(|(_, text)| text))
    }
}
'''

CURSOR_NEW = '''    /// Sets the cursor, once, to the icon of the claim on the highest layer `tool` reaches, and
    /// returns the tip: that claim's own, or else the description. With no such claim the cursor
    /// is left as it is. The claims are spent: the next frame starts with none.
    pub(crate) fn resolve(&mut self, ctx: &egui::Context, tool: QuickTool) -> Option<String> {
        // zh-hans build patch (awpde/pdfcraft-zh): the pointer's position is read here rather than
        // passed in, so this signature stays exactly what upstream and its tests call. See
        // UNOFFICIAL-BUILD-zh-CN.txt in the release assets.
        let pointer = ctx.input(|i| i.pointer.latest_pos());
        self.resolve_with(ctx, tool, pointer, soft_cursor())
    }

    /// zh-hans build patch (awpde/pdfcraft-zh), adapted from upstream PR #6173: [`PageCursor::resolve`]
    /// with the high-contrast `soft` cursor on or off. With it on, a text or crosshair cursor over the
    /// page is drawn by the app, at `pointer`, and the system's is hidden -- on some Windows drivers the
    /// system's I-beam and crosshair are drawn white, which vanishes on a white page (#3935, #5738).
    fn resolve_with(&mut self, ctx: &egui::Context, tool: QuickTool, pointer: Option<egui::Pos2>, soft: bool) -> Option<String> {
        let PageCursor { claims, description } = std::mem::take(self);
        let winner = Self::winner(claims, tool);
        if let Some(w) = &winner {
            match pointer.filter(|_| soft && matches!(w.icon, CursorIcon::Text | CursorIcon::Crosshair)) {
                Some(at) => {
                    ctx.set_cursor_icon(CursorIcon::None);
                    paint_soft_cursor(ctx, w.icon, at);
                }
                None => ctx.set_cursor_icon(w.icon),
            }
        }
        winner.and_then(|w| w.tip).or(description.map(|(_, text)| text))
    }
}

/// zh-hans build patch (awpde/pdfcraft-zh): whether the app draws its own text and crosshair cursors.
/// On by default; set `PDFCRAFT_SOFT_CURSOR=0` to fall back to the system's. The system draws them
/// thin and, on some Windows drivers, white or not at all, so over a white page they can't be seen
/// (#3935, #5738).
fn soft_cursor() -> bool {
    static ON: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *ON.get_or_init(|| std::env::var_os("PDFCRAFT_SOFT_CURSOR").map_or(true, |v| v != "0"))
}

/// Half the length of a soft cursor's arm, in points.
const SOFT_ARM: f32 = 9.0;
/// How far an I-beam's serifs reach to each side, in points.
const SOFT_SERIF: f32 = 3.0;

/// The line segments of the soft cursor for `icon`, centred on `at`: an I-beam with serifs, or a plus.
fn soft_cursor_segments(icon: CursorIcon, at: egui::Pos2) -> Vec<[egui::Pos2; 2]> {
    let (x, y) = (at.x, at.y);
    match icon {
        CursorIcon::Text => vec![
            [egui::pos2(x, y - SOFT_ARM), egui::pos2(x, y + SOFT_ARM)],
            [egui::pos2(x - SOFT_SERIF, y - SOFT_ARM), egui::pos2(x + SOFT_SERIF, y - SOFT_ARM)],
            [egui::pos2(x - SOFT_SERIF, y + SOFT_ARM), egui::pos2(x + SOFT_SERIF, y + SOFT_ARM)],
        ],
        _ => vec![
            [egui::pos2(x - SOFT_ARM, y), egui::pos2(x + SOFT_ARM, y)],
            [egui::pos2(x, y - SOFT_ARM), egui::pos2(x, y + SOFT_ARM)],
        ],
    }
}

/// Draws the soft cursor over everything: a black line with a white halo, which shows on a white page
/// and on a dark one.
fn paint_soft_cursor(ctx: &egui::Context, icon: CursorIcon, at: egui::Pos2) {
    let painter = ctx.layer_painter(egui::LayerId::new(egui::Order::Tooltip, egui::Id::unique("pdfcraft_soft_cursor")));
    let segments = soft_cursor_segments(icon, at);
    for segment in &segments {
        painter.line_segment(*segment, egui::Stroke::new(3.5, egui::Color32::WHITE));
    }
    for segment in &segments {
        painter.line_segment(*segment, egui::Stroke::new(1.5, egui::Color32::BLACK));
    }
}
'''


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    ref = sys.argv[1]
    out = os.path.join(W, 'cjk_patch_current.patch')
    if '--out' in sys.argv:
        out = sys.argv[sys.argv.index('--out') + 1]
    src_base = None
    if '--src' in sys.argv:
        src_base = sys.argv[sys.argv.index('--src') + 1]
    do_verify = '--no-verify' not in sys.argv

    tmp = os.path.join(W, 'pg_' + ref.replace('.', '_') + '_' + str(os.getpid()))
    if os.path.isdir(tmp):
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', tmp], capture_output=True)  # git objects 只读，走 cmd
    for rel in FILES:
        dst = os.path.join(tmp, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if src_base:
            s = os.path.join(src_base, rel.replace('/', os.sep))
            if not os.path.isfile(s):
                raise RuntimeError(f'--src 目录里没有 {rel}（{s}）')
            data = open(s, 'rb').read()
        else:
            data = fetch(rel, ref)
        open(dst, 'wb').write(data)
        print(f'  {rel}  {len(data)} 字节')

    os.chdir(tmp)
    subprocess.run(['git', 'init', '-q'], check=True)
    subprocess.run(['git', 'add', '-A'], check=True)
    env = dict(os.environ, GIT_AUTHOR_NAME='x', GIT_AUTHOR_EMAIL='a@b.c',
               GIT_COMMITTER_NAME='x', GIT_COMMITTER_EMAIL='a@b.c')
    subprocess.run(['git', 'commit', '-qm', 'base'], check=True, env=env)

    errors = []

    def replace(rel, old, new, label):
        p = os.path.join(tmp, rel.replace('/', os.sep))
        src = open(p, encoding='utf-8', newline='').read()
        if old not in src:
            errors.append(f'锚点未找到: {label}')
            return
        if src.count(old) != 1:
            errors.append(f'锚点不唯一({src.count(old)}次): {label}')
            return
        open(p, 'w', encoding='utf-8', newline='').write(src.replace(old, new, 1))
        print(f'  OK  {label}')

    print('\n=== 应用修改 ===')
    # 1) text.rs：把 fallback 模块放开给同级模块用
    replace('crates/edit/src/text.rs', 'mod fallback;',
            '// zh-hans build patch (awpde/pdfcraft-zh): the Type 3 fallback font is opened to the\n'
            '// sibling `added` module so added text can be drawn with it. See\n'
            '// UNOFFICIAL-BUILD-zh-CN.txt in the release assets.\n'
            'pub(crate) mod fallback;', 'text.rs 模块可见性')
    # 2) fallback.rs：放开 Type3 机制给 added 模块用
    replace('crates/edit/src/text/fallback.rs',
            'pub(super) fn type3_font(',
            '// zh-hans build patch (awpde/pdfcraft-zh): the Type 3 fallback font and its data\n'
            '// are opened to the sibling `added` module, so added text can be drawn with the\n'
            '// same mechanism the "replace text" path uses. See UNOFFICIAL-BUILD-zh-CN.txt in\n'
            '// the release assets.\n'
            'pub(crate) fn type3_font(', 'type3_font 可见性')
    replace('crates/edit/src/text/fallback.rs',
            'pub(super) fn type3_encode(', 'pub(crate) fn type3_encode(', 'type3_encode 可见性')
    replace('crates/edit/src/text/fallback.rs',
            '    pub(super) widths: Vec<(char, f64)>,', '    pub(crate) widths: Vec<(char, f64)>,',
            'Type3Fallback::widths 可见性')
    # v0.20.0 起 type3_encode 返回 Type3Run 结构体（不是元组），它与字段也要放开可见性，
    # 否则 added 模块用不了（还会触发 private-type-in-public-interface）。
    replace('crates/edit/src/text/fallback.rs',
            'pub(super) struct Type3Run {', 'pub(crate) struct Type3Run {', 'Type3Run 可见性')
    replace('crates/edit/src/text/fallback.rs',
            '    pub(super) name: String,', '    pub(crate) name: String,', 'Type3Run::name 可见性')
    replace('crates/edit/src/text/fallback.rs',
            '    pub(super) bytes: Vec<u8>,', '    pub(crate) bytes: Vec<u8>,', 'Type3Run::bytes 可见性')
    replace('crates/edit/src/text/fallback.rs',
            '    pub(super) spacing: Option<f64>,', '    pub(crate) spacing: Option<f64>,',
            'Type3Run::spacing 可见性')
    # 3) layout.rs（若上游没变，这两处替换会报「锚点未找到」→ 说明 layout.rs 变了，要重新设计）
    replace('crates/edit/src/added/layout.rs',
            '''/// The first character of `t` that would be drawn as `?`: outside WinAnsiEncoding and not drawn
''',
            '''// zh-hans build patch (awpde/pdfcraft-zh): the CJK branch below judges a character by the
// same rule the fallback uses to pick a face, so Chinese text is no longer refused as
// undrawable. See UNOFFICIAL-BUILD-zh-CN.txt in the release assets.
//
// The characters the craft-fonts fallback faces draw: kana, CJK ideographs and their compatibility
/// and full-width forms. The Japanese document faces cover them, and so does a Simplified Chinese
/// face that declares `Jpan`, so text in them is drawn and must not be refused.
pub(super) fn is_cjk(c: char) -> bool {
    matches!(u32::from(c), 0x3000..=0x30FF | 0x3400..=0x4DBF | 0x4E00..=0x9FFF | 0xF900..=0xFAFF | 0xFF00..=0xFFEF)
}

/// Whether any face that can draw document text has a glyph for `c`. The fallback picks the first
/// face that has every character of the line, so a character is drawable when one of them has it.
fn cjk_has(c: char) -> bool {
    pdfcraft_fonts::document_japanese_fonts_for_style(false, false)
        .iter()
        .any(|face| pdfcraft_fonts::japanese_glyph_from(face, c).is_ok())
}

/// The first character of `t` that would be drawn as `?`: outside WinAnsiEncoding and not drawn
''', 'layout.rs 加 is_cjk / cjk_has')
    replace('crates/edit/src/added/layout.rs',
            '''    if !shaped_by_a_face(t) {
        // Drawn line by line in the item's standard font (`\\n` splits lines). Without the face
        // that is also how `draw` redraws an existing item, so it's checked that way.
        return t.text.split('\\n').find_map(pdfcraft_fonts::first_non_win_ansi);
    }''',
            '''    // CJK (Chinese/Japanese/Korean) text is drawn with the craft-fonts fallback faces, so those
    // characters are drawable here and must not be refused (#125). Judge them the way the
    // fallback picks a face: only a character that no candidate face has a glyph for is a
    // problem, and then the write itself refuses it with the character named.
    if t.text.chars().any(is_cjk) {
        return t.text.chars().find(|c| is_cjk(*c) && !cjk_has(*c));
    }
    if !shaped_by_a_face(t) {
        // Drawn line by line in the item's standard font (`\\n` splits lines). Without the face
        // that is also how `draw` redraws an existing item, so it's checked that way.
        return t.text.split('\\n').find_map(pdfcraft_fonts::first_non_win_ansi);
    }''',
            'layout.rs first_undrawable 加 CJK 分支')
    # 4) draw.rs
    replace('crates/edit/src/added/draw.rs',
            '    Piece, arabic_error, hebrew_error, is_arabic, is_hebrew, is_thai, latin_width, norm, shaped_layout, text_rect, thai_error, wrapped,',
            '    // zh-hans build patch (awpde/pdfcraft-zh): `is_cjk` is added by this build;\n'
            '    // see UNOFFICIAL-BUILD-zh-CN.txt in the release assets.\n'
            '    Piece, arabic_error, hebrew_error, is_arabic, is_cjk, is_hebrew, is_thai, latin_width, norm, shaped_layout, text_rect, thai_error,\n'
            '    wrapped,',
            'draw.rs import 加 is_cjk')
    DRAW_CJK = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'draw-cjk-block.rs'),
                     encoding='utf-8').read()
    replace('crates/edit/src/added/draw.rs',
            'pub(super) fn draw(doc: &mut Document, c: &Content, view: [f64; 6], taken: &Dict, existing: bool) -> Result<(Vec<u8>, Dict), EditError> {',
            DRAW_CJK,
            'draw.rs 加 draw_cjk 函数')
    replace('crates/edit/src/added/draw.rs',
            '''            res.set(b"Font".to_vec(), Object::Dict(fonts));
            let r = text_rect(t);''',
            '''            // CJK (Chinese/Japanese/Korean) text: drawn with a Type 3 fallback font, the same
            // mechanism the "replace text" path uses. Without this the standard font would write
            // '?' for every one of these characters (#125).
            if t.text.chars().any(is_cjk) {
                draw_cjk(doc, t, &mut fonts, &mut out)?;
                res.set(b"Font".to_vec(), Object::Dict(fonts));
                out.extend_from_slice(b"Q\\n");
                return Ok((out, res));
            }
            res.set(b"Font".to_vec(), Object::Dict(fonts));
            let r = text_rect(t);''',
            'draw.rs 加 CJK 分支')
    # 5) main.rs
    replace('apps/pdfcraft/src/main.rs',
            '        app.set_startup_update_check(true);',
            '''        // zh-hans build patch (awpde/pdfcraft-zh): changed from true to false. See
        // UNOFFICIAL-BUILD-zh-CN.txt in the release assets.
        //
        // This build never reaches the network on its own: the update check runs only when the
        // user asks for it (Help > Check for updates). Otherwise starting the app would query
        // GitHub for a newer release, which a local-only PDF editor has no reason to do.
        app.set_startup_update_check(false);''',
            'main.rs 关掉启动时的更新检查')
    # 6) page_cursor.rs：高对比软光标（PR #6173 的单文件变体，默认启用、PDFCRAFT_SOFT_CURSOR=0
    #    可关）。单文件单锚点；指针在 resolve 内部自取，签名不变，上游 tests 不受影响。
    replace('crates/ui-egui/src/canvas/page_cursor.rs', CURSOR_OLD, CURSOR_NEW,
            'page_cursor.rs 软光标')

    if errors:
        print('\n'.join(errors))
        print(f'\n共 {len(errors)} 处锚点对不上 —— 上游的改动超出了自动处理范围，需要人工重新设计补丁。')
        return 1

    # 两个补丁按 pathspec 拆分：cjk.patch = crates/edit + apps；cursor.patch = crates/ui-egui。
    r = subprocess.run(['git', '-c', 'core.autocrlf=false', 'diff', 'HEAD', '--', *CJK_PREFIXES],
                       cwd=tmp, capture_output=True)
    patch = r.stdout.decode('utf-8')
    with open(out, 'w', encoding='utf-8', newline='') as f:
        f.write(patch)
    print(f'\n补丁: {out}  {len(patch)} 字节, {patch.count(chr(10) + "@@")} hunk, CR={patch.count(chr(13))}')

    rc = subprocess.run(['git', '-c', 'core.autocrlf=false', 'diff', 'HEAD', '--', CURSOR_FILE],
                        cwd=tmp, capture_output=True)
    patch_c = rc.stdout.decode('utf-8')
    out_c = os.path.join(os.path.dirname(out), 'cursor.patch')
    with open(out_c, 'w', encoding='utf-8', newline='') as f:
        f.write(patch_c)
    print(f'补丁: {out_c}  {len(patch_c)} 字节, {patch_c.count(chr(10) + "@@")} hunk, CR={patch_c.count(chr(13))}')

    if not do_verify:
        return 0

    # 验证：在**干净的原版副本**上 git apply --check。
    # 不要用 git checkout 还原：copytree 保留时间戳，git 的 stat cache 会跳过还原，
    # 结果拿修改过的文件去验补丁，必然失败 —— 纯浪费时间。
    v = os.path.join(W, 'verify_current_' + str(os.getpid()))
    if os.path.isdir(v):
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', v], capture_output=True)
    for rel in FILES:
        dst = os.path.join(v, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if src_base:
            open(dst, 'wb').write(open(os.path.join(src_base, rel.replace('/', os.sep)), 'rb').read())
        else:
            open(dst, 'wb').write(fetch(rel, ref))
    os.chdir(v)
    subprocess.run(['git', 'init', '-q'], check=True)
    subprocess.run(['git', 'add', '-A'], check=True)
    env2 = dict(os.environ, GIT_AUTHOR_NAME='x', GIT_AUTHOR_EMAIL='a@b.c',
                GIT_COMMITTER_NAME='x', GIT_COMMITTER_EMAIL='a@b.c')
    subprocess.run(['git', 'commit', '-qm', 'base'], check=True, env=env2)
    ok = True
    r2 = subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--check', out],
                        capture_output=True, text=True)
    print('cjk apply --check:', '通过' if r2.returncode == 0 else '失败\n' + r2.stderr[:600])
    ok = ok and r2.returncode == 0
    rc2 = subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--check', out_c],
                         capture_output=True, text=True)
    print('cursor apply --check:', '通过' if rc2.returncode == 0 else '失败\n' + rc2.stderr[:600])
    ok = ok and rc2.returncode == 0
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
