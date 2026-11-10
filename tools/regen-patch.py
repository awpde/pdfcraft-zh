# -*- coding: utf-8 -*-
"""下载指定上游版本的目标文件，检查补丁锚点，并生成补丁。

用法：python regen_patch.py <tag> [--out <补丁路径>]
"""
import base64
import json
import os
import shutil
import subprocess
import sys

GH = 'C:/Users/90714/tools/gh/bin/gh.exe'
TOKEN = subprocess.run([GH, 'auth', 'token'], capture_output=True, text=True).stdout.strip()
IP = '140.82.112.5'
REPO = 'storytold/pdfcraft'
W = os.environ.get('TEMP', '/tmp')

FILES = [
    'crates/edit/src/text.rs',
    'crates/edit/src/text/fallback.rs',
    'crates/edit/src/added/layout.rs',
    'crates/edit/src/added/draw.rs',
    'apps/pdfcraft/src/main.rs',
]


def fetch(path, ref):
    url = f'https://api.github.com/repos/{REPO}/contents/{path}?ref={ref}'
    args = ['curl', '-sSL', '--noproxy', '*', '--ssl-no-revoke',
            '--resolve', f'api.github.com:443:{IP}',
            '-H', f'Authorization: token {TOKEN}',
            '-H', 'Accept: application/vnd.github+json', url]
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
    d = json.loads(r.stdout)
    if 'content' not in d:
        raise RuntimeError(f'{path}@{ref}: {str(d)[:150]}')
    return base64.b64decode(d['content'])


def main():
    ref = sys.argv[1]
    out = W + '/cjk_patch_current.patch'
    if '--out' in sys.argv:
        out = sys.argv[sys.argv.index('--out') + 1]
    tmp = W + '/pg_' + ref.replace('.', '_') + '_' + str(os.getpid())
    if os.path.isdir(tmp):
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', tmp], capture_output=True)  # git objects 只读，走 cmd
    for rel in FILES:
        dst = os.path.join(tmp, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
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
        print(f'  ✅ {label}')

    print('\n=== 应用修改 ===')
    # 1) text.rs
    replace('crates/edit/src/text.rs', 'mod fallback;', 'pub(crate) mod fallback;', 'text.rs 模块可见性')
    # 2) fallback.rs
    replace('crates/edit/src/text/fallback.rs',
            'pub(super) fn type3_font(', 'pub(crate) fn type3_font(', 'type3_font 可见性')
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
    # 3) layout.rs（若上游没变，这三处替换会报「锚点未找到」→ 说明 layout.rs 变了，要重新设计）
    replace('crates/edit/src/added/layout.rs',
            '''/// The first character of `t` that would be drawn as `?`: outside WinAnsiEncoding and not drawn
''',
            '''/// The characters the craft-fonts fallback faces draw: kana, CJK ideographs and their compatibility
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
            '''        // This build never reaches the network on its own: the update check runs only when the
        // user asks for it (Help > Check for updates). Otherwise starting the app would query
        // GitHub for a newer release, which a local-only PDF editor has no reason to do.
        app.set_startup_update_check(false);''',
            'main.rs 关掉启动时的更新检查')

    if errors:
        print('\n'.join(errors))
        sys.exit(1)

    r = subprocess.run(['git', '-c', 'core.autocrlf=false', 'diff', 'HEAD'], cwd=tmp, capture_output=True)
    patch = r.stdout.decode('utf-8')
    open(out, 'w', encoding='utf-8', newline='').write(patch)
    print(f'\n✅ 补丁: {out}  {len(patch)} 字节, {patch.count(chr(10) + "@@")} hunk, CR={patch.count(chr(13))}')

    # 验证：git apply --check
    # 验证：把**原版**文件重新下载到一个干净目录，再 git apply --check
    # （不要用 git checkout 还原：copytree 保留时间戳，git 的 stat cache 会跳过还原，
    #  结果拿修改过的文件去验补丁，必然失败 —— 纯浪费时间。）
    v = W + '/verify_current_' + str(os.getpid())
    if os.path.isdir(v):
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', v], capture_output=True)
    for rel in FILES:
        dst = os.path.join(v, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(fetch(rel, ref))
    os.chdir(v)
    subprocess.run(['git', 'init', '-q'], check=True)
    subprocess.run(['git', 'add', '-A'], check=True)
    env2 = dict(os.environ, GIT_AUTHOR_NAME='x', GIT_AUTHOR_EMAIL='a@b.c',
                GIT_COMMITTER_NAME='x', GIT_COMMITTER_EMAIL='a@b.c')
    subprocess.run(['git', 'commit', '-qm', 'base'], check=True, env=env2)
    r2 = subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--check', out], capture_output=True, text=True)
    print('✅ git apply --check:', '通过' if r2.returncode == 0 else '失败\n' + r2.stderr[:600])
    sys.exit(0 if r2.returncode == 0 else 1)


if __name__ == '__main__':
    main()
