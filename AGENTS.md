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
套上本仓库 `overrides/` 里的定制（中文界面、字体、图标、一处源码补丁），
编译成**简体中文 Windows 安装包**发布到 Releases。

| 要点 | 值 |
|---|---|
| 上游 | `storytold/pdfcraft`（MIT OR Apache-2.0，作者 storytold / ArtCraft） |
| 构建仓库 | `awpde/pdfcraft-zh`（本仓库） |
| 姊妹仓库 | `awpde/photocraft-zh`，**另有一份自己的 `docs/维护指南.md` 和 `AGENTS.md`** |
| 版本 | **只有一条流水线** `zh-hans-windows-build.yml`（2026-11-01 起，原 `zh-cjk` 已退役并合并进来，见 §1.0） |
| 触发 | 每天 UTC 22:00 自动 + 手动 |
| 产物 | MSI + 便携版 zip，每个包都带许可证与「非官方构建」声明四件套 |

**上游更新非常频繁**（2026-10-02 的 v0.1.0 → 10-18 的 v0.9.0，**平均 1.8 天一版**）。
下面的故障是**常态，不是异常**。

---

## 1.0 ★ 2026-11-01 起：单流水线（zh-cjk 已退役，补丁合并进 zh-hans）

**仓库现在只有一条流水线 `zh-hans-windows-build.yml`。** 原 `zh-cjk-windows-build.yml`
已删除，它的能力（中文输入修复补丁）**合并进了 zh-hans**。

**为什么合并**（2026-11-01 实测 + 读上游源码确认）：

- 上游 v0.15.0 起在 `crates/edit/src/text/fallback.rs` 实现了完整的 CJK 回退
  （`needs_japanese()` 覆盖 U+4E00..9FFF、`type3_glyph`、`fallback_face`、`no_japanese_font`，
  错误文案与我们补丁一字不差，原生路径也有 ToUnicode）。
- 但上游**漏改了判定函数** `crates/edit/src/added/layout.rs` 的 `first_undrawable` ——
  它只更新了泰文/阿拉伯文/希伯来文分支，于是**任何中日韩字符都被判成
  「标准字体画不出来」**。用户看到的现象：「新增文字」输入中文，底下飘红
  `PDF 文本字体无法显示「还」（U+8FD8）。请选择受支持的文本。`，**而且无法提交**
  （上游 `hold_blocked()` 把这样的草稿一直留着，只报"画不出来"，不报哪个字）。
**所以补丁**不是多余的**。它现在负责三件事：
  1. 给 `first_undrawable` 补 CJK 分支（按上游挑回退字体的同一判据：某字符只要有任一候选
     face 有字形就画得出来）→ 红字消失；
  2. **给「新增文字」的绘制路径补 CJK 分支**（`crates/edit/src/added/draw.rs`）→ 中文真正
     写进 PDF，而不是被 `win_ansi()` 写成 `?`；
  3. 关掉启动时的自动更新检查（见 §1.2）。

> ★ **关键教训（2026-11-01 用户实测两次才发现）**：
> 上游 v0.15.0 起的 CJK 回退（`crates/edit/src/text/fallback.rs` 的 `type3_font`）**只用在
> 「替换文字」那条路径上**；「新增文字」的绘制路径（`added/draw.rs`）**压根没有 CJK 分支**，
> 非 shaped 的文本直接交给 `win_ansi(line)` → 非 WinAnsi 字符全变成 `?`。
> 所以只修判定（不飘红）不够，**绘制路径也必须修** —— 否则用户看到的是「不报错了，但写出来
> 全是问号」。查上游时**要看清是哪条路径**，别看到 `needs_japanese` 就以为整条链路都支持了。

**代价**：补丁仍要跟着上游版本走（上游 1.8 天一版）。重生成流程见
`docs/维护指南.md` §6.1。注意 `tools/regen-cjk-patch.py` **已不兼容 v0.15+ 的新结构**
（上游把 `added.rs` 拆成了模块），要重生成得按 §6.1 的手工步骤做。

**别再按「上游自己实现了中文回退，补丁可以退休」来理解** —— 那是 10-29 的结论，
被 11-01 的实测推翻了：上游只改了绘制路径，没改校验路径。


---

## 1.1 ★ 上游发新版后要重做补丁（唯一的日常维护点）

**现状**：补丁只对准一个上游版本。上游发新版后，`overrides/cjk.patch` 会打不上，
构建在「应用「新增中文文字」修复补丁」这一步**中止**（设计如此：不发布坏包）——
用户会收到 GitHub 的失败邮件，那就是他来催你的信号。

重生成流程见 `docs/维护指南.md` §6.1（含 v0.16.1 补丁的两处改动位置）。

> 别跳过「先重新生成补丁」这一步。补丁没跟上就直接构建，只会���用户每天收一封失败邮件。

## 1.3 ★ 上游 v0.18.1 起：界面词条搬到了独立仓库（2026-11-09）

**上游把各语言的界面词条从 `crates/ui-egui/src/i18n/*.tsv` 搬走了** —— 现在在
`storytold/craft-i18n` 仓库的 `locales/<locale>/` 目录下：

| 位置 | 内容 |
|---|---|
| `storytold/craft-i18n` 的 `locales/<locale>/pdfcraft.tsv` | 本应用专属词条 |
| `storytold/craft-i18n` 的 `locales/<locale>/common.tsv` | 多个 Crafting Apps 共享的词条 |
| 上游仓库根目录的 `craft-i18n.rev` | 锁定上面那个仓库的 commit（一个 40 字符的 sha） |

`crates/ui-egui/build.rs` 从 **`$CRAFT_I18N_DIR/locales/<locale>/pdfcraft.tsv`** 读词条。
不提供它，编译仍会成功，但**界面是纯英文**（上游 release 用 `CRAFT_I18N_REQUIRED=1`，
缺了直接构建失败）。

**我们工作流的对应改动**（已落地）：

- 新增两个步骤：「读上游锁定的 craft-i18n 版本」（读 `src/craft-i18n.rev`）+
  「拉取 craft-i18n」（检出到 `craft-i18n/` 目录）；
- 编译步骤加 `CRAFT_I18N_DIR` 与 `CRAFT_I18N_REQUIRED=1`；
- 「校验中文词条确实存在」与「补充译文」改在 `craft-i18n/locales/zh-hans/pdfcraft.tsv` 上做；
- resolve 阶段的词条检查改成两段式：新机制查 `craft-i18n@rev` 里有没有
  `locales/zh-hans/pdfcraft.tsv`，旧机制（v0.18.1 之前）查上游仓库里的
  `crates/ui-egui/src/i18n/zh-hans.tsv`。

> ★ **一个隐蔽的失败模式**：改动前的那几个版本（v0.18.1 / v0.18.2 / v0.19.0）**天天构建
> 「成功」却一个包都没出** —— resolve 阶段判定「上游不含中文词条」→ `skip`，
> 而 job 的结论显示成 `skipped`、run 显示成 `success`。
> **只看 run 的 success/failure 会以为一切正常。** 要看 job 级别的结论，
> 并且确认 release 真的更新了（`assets[].updatedAt`）。

## 1.2 ★ 启动时不再联网（补丁干的第二件事）

上游桌面版在 `apps/pdfcraft/src/main.rs` 里无条件 `app.set_startup_update_check(true)`，
启动即访问 GitHub 查询新版本（`craft_update` crate 用 `ureq`）。这就是杀毒软件提示
「该软件有联网请求」的来源 —— 上游说的「完全本地运行」指的是**文档数据不出本地**，
更新检查是另一回事。

我们的补丁把它改成 `false`：**只有用户主动点「帮助 ▸ 检查更新」才会联网**。

其余与网络有关的点（都不自动发生，无需处理）：

| 现象 | 出处 | 结论 |
|---|---|---|
| 监听本机端口 | `crates/ui-egui/src/control/transport.rs` 绑 **127.0.0.1** 随机端口（带 token 认证），供 CLI 控制正在运行的 GUI | 回环，不出网 |
| 打开远程文档 | `crates/engine/src/links.rs` 的 `read_remote_document` | 用户主动操作 |
| 点击 PDF 里的链接 | `crates/annot/src/links.rs` | 用户主动操作，会开浏览器 |


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

### 3.4 上游发新版后，「补丁」是唯一的自动失效点

它们在不同步骤失败，要分别检查，**不要只修一个就以为好了**。

---

### 3.5 ★ 安装界面不再覆盖（2026-11-10 起）

上游 **v0.20.0（#1139）自己实现了「选择安装位置」**：欢迎页有 `InstallTo` 路径框 +
`Browse` 按钮 + `BrowseFolder` 浏览对话框，直接用 `INSTALLFOLDER` 属性。
我们从 v0.7 时代起自建的那套覆盖（`overrides/installer-ui.wxs`）**已删除**。

**为什么删**：自建覆盖既多余（功能上游有了），又因为跟不上上游的文案变化被拦下 ——
上游把 `PdfContextMenu` 复选框的文案从 `Add "&Edit with PdfCraft"…` 改成
`Add "&Edit and Combine files"…`（#585 合并文件功能），我们的旧文案不含 `Combine files`，
上游 `test-msi.ps1:248` 直接抛错 → 构建失败（2026-11-10 踩到）。

**教训（与 photocraft 侧同一条原则）**：**上游原生支持某功能后，就别再自建覆盖** ——
自建覆盖每逢上游改那块就会失效，而失效方式是「静默”或「构建挂」。

## 4. 高频任务怎么做

| 场景 | 怎么做 |
|---|---|
| 上游发了新版，构建挂在「应用「新增中文文字」修复补丁」 | 按 `docs/维护指南.md` §6.1 用新 tag 的源码重生成 `overrides/cjk.patch`（**注意工具已不兼容 v0.15+**，按文档的手工步骤做） |
| 构建失败要定位是补丁还是上游问题 | 看失败步骤名：补丁步骤 = 补丁问题；「编译并打包」= 上游自检/打包问题，见 `docs/维护指南.md` §6 |
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
- **不要把 `zh-cjk-windows-build.yml` 加回来** —— 它已于 2026-11-01 退役并合并进 zh-hans，见 §1.0；用户明确要「只留一条流水线」
- 不要在没有读 `docs/icons/README.md` 的情况下按文件名判断某个 png/ico 是给哪个位置用的（**这个仓库已经因此出过两次事故**）
- 不要在本地生成带 CRLF 的补丁 / tsv 再推上去