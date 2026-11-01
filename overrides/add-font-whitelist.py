#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一款中文字体加进上游的 CJK 「全嵌入白名单」。

上游 crates/fonts/src/cjk_scripts.rs 里：

    pub const WHOLE_CJK_FAMILIES: [&str; 3] = ["Shippori Mincho", "BIZ UDPGothic", "BIZ UDMincho"];
    pub const MAX_OTHER_CJK_BYTES: u64 = 4 << 20;   // 其余 CJK 字体超过 4 MiB 就跳过

`crates/fonts/build.rs` 用 `#[path]` include 同一个文件，所以白名单里的字体**整份嵌入**，
不受 4 MiB 上限限制；名单外的 CJK 字体超限会被 `Skip` —— **静默丢弃，连警告都没有**。

我们的中文字体（鸿蒙 Sans SC，8.3 MB）超过 4 MiB，必须进这个名单，否则它根本不在二进制里，
写进 PDF 的中文只能靠日文字体，简体独有字（如「还」U+8FD8）就没有字形。

按内容匹配替换（不依赖行号，上游改了这个文件也不会错位），替换后由调用方校验结果。

用法：python add-font-whitelist.py <cjk_scripts.rs 路径> <字体 family>
"""
import re
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: add-font-whitelist.py <cjk_scripts.rs> <family>")
        return 2
    path, family = sys.argv[1], sys.argv[2]
    src = open(path, encoding='utf-8').read()
    m = re.search(r'pub const WHOLE_CJK_FAMILIES: \[&str; (\d+)\] = \[([^\]]*)\];', src)
    if not m:
        print(f"::error::上游的 WHOLE_CJK_FAMILIES 声明变了（{path}），无法自动加入白名单。")
        print("::error::请手动把字体 family 加进那个数组，并确认数组长度。")
        return 1
    fams = [x.strip().strip('"') for x in m.group(2).split(',') if x.strip()]
    if family in fams:
        print(f"  {family} 已在白名单里，跳过")
        return 0
    fams.append(family)
    new = 'pub const WHOLE_CJK_FAMILIES: [&str; %d] = [%s];' % (
        len(fams), ', '.join('"%s"' % f for f in fams))
    src = src[:m.start()] + new + src[m.end():]
    open(path, 'w', encoding='utf-8', newline='\n').write(src)
    print(f"  已改为: {new}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
