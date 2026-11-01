#!/usr/bin/env python3
"""Add a Simplified Chinese font to the upstream CJK "embedded whole" whitelist.

Upstream crates/fonts/src/cjk_scripts.rs:

    pub const WHOLE_CJK_FAMILIES: [&str; 3] = ["Shippori Mincho", "BIZ UDPGothic", "BIZ UDMincho"];
    pub const MAX_OTHER_CJK_BYTES: u64 = 4 << 20;   # other CJK faces over 4 MiB are skipped

crates/fonts/build.rs includes the same file with #[path], so a family in that list is embedded
whole (no size cap); any other CJK face over the cap is *silently* skipped -- no warning at all.

Our Simplified Chinese face (HarmonyOS Sans SC, 8.3 MB) is over the 4 MiB cap, so it MUST be in
the list. Otherwise it is not in the binary, the only faces left for PDF text are the Japanese
ones, and Simplified-only characters (e.g. U+8FD8) have no glyph.

The line is replaced by content match (not by line number), so an upstream edit of that file
cannot silently misplace it. The caller verifies the result afterwards.

NOTE: the Windows runner's Python prints with cp1252, so every message here is ASCII -- a
non-ASCII character in a print() raises UnicodeEncodeError and aborts the build.

Usage: python add-font-whitelist.py <cjk_scripts.rs> <font family>
"""
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

QUOTE = chr(34)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: add-font-whitelist.py <cjk_scripts.rs> <family>")
        return 2
    path, family = sys.argv[1], sys.argv[2]
    src = open(path, encoding="utf-8").read()
    m = re.search(r"pub const WHOLE_CJK_FAMILIES: \[&str; (\d+)\] = \[([^\]]*)\];", src)
    if not m:
        print("::error::upstream WHOLE_CJK_FAMILIES declaration changed; "
              "cannot add the font automatically")
        print("::error::add the font family to that array by hand and fix the array length")
        return 1
    fams = [x.strip().strip(QUOTE) for x in m.group(2).split(",") if x.strip()]
    if family in fams:
        print("  " + family + " is already whitelisted, skipped")
        return 0
    fams.append(family)
    new = ("pub const WHOLE_CJK_FAMILIES: [&str; %d] = [%s];"
           % (len(fams), ", ".join(QUOTE + f + QUOTE for f in fams)))
    src = src[:m.start()] + new + src[m.end():]
    open(path, "w", encoding="utf-8", newline="\n").write(src)
    print("  rewritten: " + new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
