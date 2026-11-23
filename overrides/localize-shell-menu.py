#!/usr/bin/env python3
"""Localize the Windows Explorer shell-verb menu entries and switch their icon.

What it changes (by content match, never by line number):

1. packaging/windows/pdfcraft.wxs
   - "Edit with PdfCraft"          -> 用 PdfCraft 编辑
   - "Combine files in PdfCraft"   -> 在 PdfCraft 中合并文件…
   - "Create PDF with PdfCraft…"   -> 用 PdfCraft 创建 PDF…   (10 image extensions)
   - the Edit/Combine verbs' Icon: the exe's big "P" logo (resource 0) -> the
     PDF-document icon (resource -2), the same one the .pdf default icon uses;
   - adds an Icon row (resource -2) to every PdfCraft.CreatePdf verb, which
     upstream ships without one.

2. packaging/windows/test-msi.ps1
   - the assertion constants must match the new labels and the new icon value,
     otherwise the MSI self-check (run by package.ps1) would fail the build.

Translations follow the project's own zh-hans catalogue (storytold/craft-i18n,
locales/zh-hans/pdfcraft.tsv): "Combine files in PdfCraft…" is already
translated there as "在 PdfCraft 中合并文件…", so the verb label uses the same
wording. The welcome-dialog checkbox ("Add &Edit and Combine files...") is NOT
touched: test-msi.ps1 asserts its exact English text and it is installer UI,
not a shell menu entry.

Safety: every replacement is expected a fixed number of times; if any anchor is
missing or appears an unexpected number of times the script fails as a whole
and lists every problem -- it never leaves the two files half-updated (the MSI
self-check compares the .wxs against the assertions, so a half update would
fail the build in a much more confusing way).

Idempotent: re-running after a successful localization is a no-op.

Encoding: pdfcraft.wxs is UTF-8 without BOM; test-msi.ps1 is UTF-8 with BOM.
Both are written back unchanged in kind. All log output is ASCII-only unless
stdout can be reconfigured to UTF-8 (the GitHub Actions Windows runner's
Python defaults to cp1252 and a non-ASCII print() would raise).

Usage: python localize-shell-menu.py <pdfcraft.wxs> <test-msi.ps1>
"""
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# The Chinese labels, mirroring the zh-hans catalogue's own style
# ("Combine files in PdfCraft…" is literally in the catalogue).
LABEL_EDIT = '用 PdfCraft 编辑'
LABEL_COMBINE = '在 PdfCraft 中合并文件…'
LABEL_CREATE = '用 PdfCraft 创建 PDF…'

OLD_EDIT = 'Edit with PdfCraft'
OLD_COMBINE = 'Combine files in PdfCraft'
OLD_CREATE = 'Create PDF with PdfCraft…'

ICON_OLD = '"[#PdfcraftExe]",0'
ICON_NEW = '"[#PdfcraftExe]",-2'

IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'tif', 'tiff', 'gif', 'bmp', 'jp2', 'j2k', 'jpx']


def read(path):
    data = open(path, 'rb').read()
    bom = data.startswith(b'\xef\xbb\xbf')
    return data.decode('utf-8-sig'), bom


def write(path, text, bom):
    data = text.encode('utf-8')
    if bom:
        data = b'\xef\xbb\xbf' + data
    open(path, 'wb').write(data)


def replace_exact(src, old, new, expect, label, errors):
    n = src.count(old)
    if n != expect:
        errors.append(f'{label}: expected {expect} occurrence(s), found {n}')
        return src
    return src.replace(old, new)


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: localize-shell-menu.py <pdfcraft.wxs> <test-msi.ps1>')
        return 2
    wxs_path, ps1_path = sys.argv[1], sys.argv[2]

    wxs, wxs_bom = read(wxs_path)
    ps1, ps1_bom = read(ps1_path)

    already = LABEL_EDIT in wxs or LABEL_CREATE in wxs
    if already:
        print('  already localized, nothing to do')
        return 0

    errors = []

    # ---- pdfcraft.wxs ----
    wxs = replace_exact(wxs, f'Value="{OLD_EDIT}"', f'Value="{LABEL_EDIT}"', 1,
                        'wxs Edit label', errors)
    wxs = replace_exact(wxs, f'Value="{OLD_COMBINE}"', f'Value="{LABEL_COMBINE}"', 1,
                        'wxs Combine label', errors)
    wxs = replace_exact(wxs, f'Value="{OLD_CREATE}"', f'Value="{LABEL_CREATE}"', len(IMAGE_EXTS),
                        'wxs CreatePdf labels', errors)

    # Icon: the Edit and Combine verbs each carry one Icon row pointing at the
    # exe's big logo (resource 0). Point both at the PDF-document icon (-2).
    for verb in ('Edit', 'Combine'):
        old = (f'shell\\PdfCraft.{verb}" Name="Icon" '
               f'Value="&quot;[#PdfcraftExe]&quot;,0"')
        new = (f'shell\\PdfCraft.{verb}" Name="Icon" '
               f'Value="&quot;[#PdfcraftExe]&quot;,-2"')
        wxs = replace_exact(wxs, old, new, 1, f'wxs {verb} icon', errors)

    # The CreatePdf verbs ship without any icon; add one (the same PDF-document
    # icon, since the action produces a PDF) after each label row.
    added_icons = 0
    for ext in IMAGE_EXTS:
        pat = re.compile(
            r'(<RegistryValue Root="HKMU" '
            r'Key="Software\\Classes\\SystemFileAssociations\\.' + re.escape(ext) +
            r'\\shell\\PdfCraft\.CreatePdf" Value="[^"]*" Type="string"(?: KeyPath="yes")? />)')
        m = pat.search(wxs)
        if not m:
            errors.append(f'wxs CreatePdf label row for .{ext}: not found')
            continue
        key = f'Software\\Classes\\SystemFileAssociations\\.{ext}\\shell\\PdfCraft.CreatePdf'
        icon_row = (f'\n        <RegistryValue Root="HKMU" Key="{key}" Name="Icon" '
                    f'Value="&quot;[#PdfcraftExe]&quot;,-2" Type="string" />')
        wxs = wxs[:m.end(1)] + icon_row + wxs[m.end(1):]
        added_icons += 1

    # ---- test-msi.ps1 ----
    # The self-check reads the MSI's Registry table and compares the labels and
    # the icon value against literal constants; they must track the .wxs.
    ps1 = replace_exact(ps1, f"'{OLD_EDIT}'", f"'{LABEL_EDIT}'", 2,
                        'ps1 Edit label assertions', errors)
    ps1 = replace_exact(ps1, f"'{OLD_COMBINE}'", f"'{LABEL_COMBINE}'", 1,
                        'ps1 Combine label assertion', errors)
    ps1 = replace_exact(ps1, f"'{OLD_CREATE}'", f"'{LABEL_CREATE}'", 2,
                        'ps1 CreatePdf label assertions', errors)
    ps1 = replace_exact(ps1, f"'{ICON_OLD}'", f"'{ICON_NEW}'", 2,
                        'ps1 Icon assertions', errors)

    if errors:
        print('problems found; no file was written:')
        for e in errors:
            print('  - ' + e)
        return 1

    # Final sanity: no upstream label may remain in an actual registry value or
    # an actual assertion constant. Comments in both files intentionally keep
    # the English wording so the files stay diffable against upstream.
    for leftover in (f'Value="{OLD_EDIT}"', f'Value="{OLD_COMBINE}"', f'Value="{OLD_CREATE}"'):
        if leftover in wxs:
            print(f'- leftover in wxs after replace: "{leftover}" (should be gone)')
            return 1
    for leftover in (f"'{OLD_EDIT}'", f"'{OLD_COMBINE}'", f"'{OLD_CREATE}'", f"'{ICON_OLD}'"):
        if leftover in ps1:
            print(f'- leftover in ps1 after replace: "{leftover}" (should be gone)')
            return 1

    write(wxs_path, wxs, wxs_bom)
    write(ps1_path, ps1, ps1_bom)
    print(f'  wxs: 3 labels localized, 2 icon rows switched to {ICON_NEW}, '
          f'{added_icons}/10 CreatePdf verbs gained an icon row')
    print(f'  ps1: 5 assertion constants updated to the Chinese labels and {ICON_NEW}')
    print('OK: shell menu localized')
    return 0


if __name__ == '__main__':
    sys.exit(main())
