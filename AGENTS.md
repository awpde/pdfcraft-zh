# AGENTS.md — 给接手维护本仓库的 agent / 人的第一份必读

> 这份文件里的规则**先于任何任务**生效。你可以在没有任何历史对话上下文的情况下，
> 只靠这个仓库独立完成维护。
>
> 深度内容在 [`docs/维护指南.md`](docs/)；这里只放「开工前必须知道的东西」。

---

## 0. 如果你是从聊天窗口接手（没有仓库工作目录）

按这个顺序读，**这些都是公开链接，不需要登录**：

1. 本文件
   <https://raw.githubusercontent.com/awpde/pdfcraft-zh/main/AGENTS.md>
2. 完整维护知识
   <https://raw.githubusercontent.com/awpde/pdfcraft-zh/main/docs/%E7%BB%B4%E6%8A%A4%E6%8C%87%E5%8D%97.md>
3. 图标相关（改图标才需要）
   <https://raw.githubusercontent.com/awpde/pdfcraft-zh/main/docs/icons/README.md>
4. 姊妹仓库 PhotoCraft 的入口
   <https://raw.githubusercontent.com/awpde/photocraft-zh/main/AGENTS.md>

> 仓库页面：<https://github.com/awpde/pdfcraft-zh>（文件多时可直接在网页上浏览）

**读完之后先别动手**：把理解的现状和打算做的事说出来，确认无误再执行。

---

## 1. 这个仓库是什么

**一句话**：这里没有任何 PdfCraft 代码，只有一条 GitHub Actions 流水线 ——
拉上游 [storytold/pdfcraft](https://github.com/storytold/pdfcraft) 的源码，
套上本仓库 `overrides/` 里的定制（中文界面、字体、图标、安装界面、一处源码补丁），
编译成**简体中文 Windows 安装包**发布到 Releases。

| 要点 | 值 |
|---|---|
| 上游 | `storytold/pdfcraft`（MIT OR Apache-2.0，作者 storytold / ArtCraft） |
| 构建仓库 | `awpde/pdfcraft-zh`（本仓库） |
| 姊妹仓库 | `awpde/photocraft-zh`，**另有一份自己的 `docs/维护指南.md` 和 `AGENTS.md`** |
| 两个版本 | `zh-hans`（纯中文化，**每日自动跟版，用户日常在用**）/ `zh-cjk`（含中文输入修复，**⚠️ 定时触发已于 2026-10-19 停用，只能手动构建**，见 §1.1） |
| 触发 | `zh-hans`：每天 UTC 22:00 自动 + 手动<br>`zh-cjk`：**只有手动** |
| 产物 | MSI + 便携版 zip，每个包都带许可证与「非官方构建」声明四件套 |

**上游更新非常频繁**（2026-10-02 的 v0.1.0 → 10-18 的 v0.9.0，**平均 1.8 天一版**）。
下面的故障是**常态，不是异常**。

---

## 1.0 ★ 2026-10-29 起：zh-cjk 已无必要（上游自己实现了中文回退）

**结论：可以退役 `zh-cjk` 版了。** 现在只需要 `zh-hans`。

**依据（读上游 v0.15.0 源码确认，不是推测）**：

- 上游把 `crates/edit/src/added.rs` 拆成了模块，新增 `crates/edit/src/text/fallback.rs`，
  其中已经实现了完整的中文回退：
  | 上游 v0.15.0 | 我们的 cjk.patch |
  |---|---|
  | `needs_japanese()` 覆盖 **U+4E00..=0x9FFF（中文统一表意文字）** | `is_cjk()` |
  | `type3_glyph` → `japanese_glyph_from` | `cjk_path` → `japanese_glyph_from` |
  | `fallback_face()` | `cjk_face()` |
  | `no_japanese_font()` —— 错误文案**一字不差** | `cjk_no_font()` |
  | 原生路径也有 `ToUnicode`（复制/搜索中文可用） | 我们的补丁也提供 |
- 我们的构建把鸿蒙字体以 **`Hans,Jpan,Latn`** 写进字体清单，而上游写「替换文字」时正是
  按 `covers("Jpan")` 筛候选字体 → 我们的字体在候选集里 → 上游原生机制就能画中文。
- v0.15.0 构建日志里有明确证据：`✅ 含 Jpan → 可用于 PDF 文字替换（简体字不再报 no glyph）`。

**所以**：以前必须靠补丁的「新增中文文字」，现在 `zh-hans` 也能用了；
而 `zh-cjk` 是仓库里唯一需要人工维护的环节（补丁只对准一个上游版本，1.8 天一版）——
它的问题已经自动消失，退役它反而是「减维护」。

**退役前请用户实测一次**：装 `zh-hans` 的最新包 → 用「新增文字」加一句中文 →
确认能显示、能复制。确认后再删 `zh-cjk-windows-build.yml` 与 `overrides/cjk.patch`。

**若将来仍要保留 zh-cjk**（例如用户就是想留着那条线），注意：
`tools/regen-cjk-patch.py` **不兼容 v0.15.0**（上游把文件拆了，它会报「找不到 pub fn width(」），
需要按新结构重写该工具。

---

## 1.1 ★ zh-cjk 的定时构建已停用（2026-10-19），恢复方法在这

**现状：`zh-cjk` 只有手动触发，每天自动跟版的是 `zh-hans`。**

**为什么停**：用户日常只做**合并 / 删页 / 涂黑**，这三样纯中文化版都有。
唯一需要补丁的是「新增中文文字」，而它是整个仓库里**唯一需要人工维护**的环节 ——
上游 1.8 天一版，每发一版就要重新生成一次 `overrides/cjk.patch`，
而且**上游不会接手**（他们的 `AGENTS.md` §1.1 明令禁止捆绑中文 CJK 字体，与补丁思路冲突，
相关 issue #455 至今 open）。为一个用不到的功能每 1.8 天做一次人工维护，不划算。

**如果你看到 zh-cjk 没有定时构建，那是故意的，不是坏了。**

**恢复每日自动跟版**（约 5 分钟，两处改动）：

1. 先为当前最新 tag 重新生成补丁，否则第一次跑**必然失败**（这是设计如此）：
   ```bash
   python tools/regen-cjk-patch.py <最新tag> --push
   python tools/regen-cjk-patch.py --check-ref <最新tag>     # 确认补丁适用
   ```
2. 手动触发一次验证：`gh workflow run zh-cjk-windows-build.yml --repo awpde/pdfcraft-zh -f upstream_ref=<最新tag>`，
   等它跑完，**按铁律 3.1 回读日志**确认补丁真的应用了
3. 验证通过后，把 workflow 里那段注释掉的 `schedule:` 取消注释（文件顶部有醒目提示）：
   ```
   #   schedule:
   #     - cron: '0 22 * * *'
   ```
4. 把本节的现状描述改回「每日自动」

> **别跳过第 1 步**。补丁只对准一个上游版本（见铁律 3.2），
> 直接恢复 schedule 只会让用户每天收一封构建失败邮件。

---

## 2. 开工前，先按这个顺序读

1. **本文件**（你现在在读）
2. [`docs/维护指南.md`](docs/) —— 完整维护知识：铁律、跟版处置流程、踩坑集、风险表
3. 改图标前还要读 [`docs/icons/README.md`](docs/icons/)

然后**核查线上真实状态**（不要相信任何人的转述，包括本文件里的版本号）：

```bash
gh run list --repo awpde/pdfcraft-zh --limit 10        # 最近构建有没有红的
gh release list --repo awpde/pdfcraft-zh --limit 5   # 最新包到哪个版本了
python tools/regen-cjk-patch.py --check-ref <最新tag> # 补丁是否还适用
```

> 上面的 `gh` 路径见 §5。工具都在 `tools/`，用法见维护指南。

---

## 3. 铁律（违反了就是在制造事故）

### 3.1 永远不要只看绿对勾，必须回读构建日志

`gh run list` 显示 success **不代表**定制都生效。必须：

```bash
python tools/fetchlog.py awpde/pdfcraft-zh <run_id> "已应用 CJK|已确认 added.rs|已替换|补充译文：|ok MSI"
```

`fetchlog.py` 匹配不到任何行时会报错退出 —— **那正是它要抓的情况**。

### 3.2 补丁只对准上游 **Release tag**，绝不对准 `main`

定时任务跟的是 Release tag。补丁只能精确匹配一个版本。
把补丁对准 `main` 会让**定时构建全挂而手动构建全过**，极易误判成"没问题"。
手动验证也要用 Release tag，否则验的和定时任务跑的不是一个路径。

### 3.3 根目录 `.gitattributes` 里的声明不能删

`*.patch -text` / `*.tsv -text` 是补丁能打上的前提；
`*.png binary` / `*.ico binary` 防止二进制图标被行尾转换改坏。

### 3.4 上游发新版后，「补丁」和「安装界面」是两处**独立**的失效点

它们在不同步骤失败，要分别检查，**不要只修一个就以为好了**。

---

## 4. 高频任务怎么做

| 场景 | 怎么做 |
|---|---|
| 用户想恢复 zh-cjk 每日自动跟版 | 照 §1.1 的四步做。**第一步必须先重新生成补丁**，否则第一次跑必挂 |
| zh-cjk 构建失败 | 先跑 `tools/regen-cjk-patch.py --check-ref <tag>` 定位是补丁还是界面挂了，再照 `docs/维护指南.md` §6 对症处理 |
| 要重新生成补丁 | `python tools/regen-cjk-patch.py <tag>` → 看自检输出 → `--push` → 手动触发一次构建验证 |
| 改补丁脚本 | 改完**必须**跑 `python tools/verify_regen.py <tag>`，确认脚本仍忠实复现现有补丁 |
| 用户报图标不对 | 先读 `docs/icons/README.md`。**软件有三处图标来源、要维护四个文件**，窗口 PNG 最容易漏 |
| 想知道包里的译文/字体对不对 | 靠构建日志的自检行，不要靠猜 |

---

## 5. 本机 / 仓库的环境事实（踩过的坑）

| 事实 | 说明 |
|---|---|
| **这台机器上没有 git，也没有 GNU patch** | 补丁生成 / 应用 / 验证全部走 `tools/minipatch.py`（纯 Python）。文档里凡是 `git diff` / `git apply --check` 的说法，改用对应脚本 |
| `gh` 不在 PATH | 实际路径 `C:/Users/90714/tools/gh/bin/gh.exe`，已登录 `awpde`（scopes: repo + workflow） |
| **PowerShell 里 `gh api --jq '...'` 会被拆错参数** | 用 `tools/ghapi.py` 代替 |
| 没有 Rust | 本机不能编译验证，一切编译验证靠 CI。改 Rust 源码只能静态核对 + 推 CI 看结果 |
| Python | `D:/Python/python.exe`（3.13） |
| 推文件**不要用 `git push`** | 用 `gh api --method PUT …/contents/<path>` 或 `tools/ghapi.py`（更新已有文件必须带 `sha`） |
| **workflow 的 shell 是 `pwsh`（.NET/ICU），本机是 PowerShell 5.1（NLS）** | ICU 把控制字符视为可忽略，`"\r".StartsWith("\x01")` 在两边结果**相反**。「本地过了 CI 挂了」先怀疑这个。字符串比较一律用 `[StringComparison]::Ordinal` |

更完整的踩坑集见 `docs/维护指南.md` §7。

---

## 6. 用户是谁，以及怎么跟他沟通

用户**不写代码、不碰编译**，只下载安装包。他不熟 GitHub 网页。

- **下载链接必须是可直接点开的完整 URL**（Releases 页 + 认 Latest 徽标，或 asset 直链），不要只给路径或仓库名
- **不要主动生成交接文档**；维护知识就以 `docs/维护指南.md` 为准，需要更新时再改
- 大文件给直链让他浏览器自己下（本机下载很慢）
- 删旧 Release 前**先问**；临时目录用完问是否清理
- 他会收到 GitHub 的构建失败邮件并来问 —— **定时构建失败要当回事**，那是他自动获取更新的通道
- 合规四件套（MIT / Apache / NOTICE / 非官方声明）必须随包，缺一不可
- **不要把上游的狮子 logo 换回来** —— 那是 ArtCraft 商标；换成用户自制的图标正是为了避开它

---

## 7. 不要做的事

- 不要只看构建是绿的就宣布完成（见 §3.1）
- 不要为了"顺手"改 workflow 里的锚点常量 —— 它们带唯一性校验，报错时先查上游改了什么
- 不要把上游的英文字体/英文界面"顺手优化"掉 —— 中文化与图标替换就是本仓库存在的全部理由
- **不要因为「zh-cjk 没有定时构建」就去把它加回来** —— 那是有意停用的，见 §1.1，除非用户明确要求
- 不要在没有读 `docs/icons/README.md` 的情况下按文件名判断某个 png/ico 是给哪个位置用的（**这个仓库已经因此出过两次事故**）
- 不要在本地生成带 CRLF 的补丁 / tsv 再推上去