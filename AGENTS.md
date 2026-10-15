# AGENTS.md — 给接手维护本仓库的 agent / 人的第一份必读

> 这份文件里的规则**先于任何任务**生效。你可以在没有任何历史对话上下文的情况下，
> 只靠这个仓库独立完成维护。
>
> 深度内容在 [`docs/维护指南.md`](docs/)；这里只放「开工前必须知道的东西」。

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
| 两个版本 | `zh-cjk`（含中文输入修复，用户实际在用）/ `zh-hans`（纯中文化） |
| 触发 | 每天 UTC 22:00 自动跟上游**最新 Release tag**；也可手动指定 ref |
| 产物 | MSI + 便携版 zip，每个包都带许可证与「非官方构建」声明四件套 |

**上游更新非常频繁**（2026-10-08 的 v0.4.0 → 10-14 的 v0.8.0，一周 4 个版本）。
下面的故障是**常态，不是异常**。

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
| 上游跟版失败 | 先跑 `tools/regen-cjk-patch.py --check-ref <tag>` 定位是补丁还是界面挂了，再照 `docs/维护指南.md` §6 对症处理 |
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
- 不要在没有读 `docs/icons/README.md` 的情况下按文件名判断某个 png/ico 是给哪个位置用的（**这个仓库已经因此出过两次事故**）
- 不要在本地生成带 CRLF 的补丁 / tsv 再推上去