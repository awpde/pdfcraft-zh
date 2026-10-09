# PdfCraft 简体中文版（自动构建）

这个仓库本身**不存放 PdfCraft 的代码**，只放一个 GitHub Actions 工作流：
它会在云端拉取上游 [storytold/pdfcraft](https://github.com/storytold/pdfcraft) 的源码，
编译出**界面为简体中文**的 Windows 安装包，并发布到本仓库的
[Releases](../../releases) 页面。

## ⚠️ 非官方构建声明

本仓库产出的是**非官方第三方构建**，**不是官方发布**，与原项目作者不存在隶属、
赞助或背书关系。

- 程序主体为原作者（ArtCraft Team and the PdfCraft contributors）的作品，
  采用 **MIT OR Apache-2.0** 双许可
  （[LICENSE-MIT](https://github.com/storytold/pdfcraft/blob/main/LICENSE-MIT)、
  [LICENSE-APACHE](https://github.com/storytold/pdfcraft/blob/main/LICENSE-APACHE)）。
- 本仓库**只修改构建配置，未修改程序源码**：
  1. 界面简体中文字体改为随包嵌入 HarmonyOS Sans SC（上游官方 Windows 包缺失该字体，
     会导致简体中文显示成方块）；
  2. 该字体的脚本声明为 `Hans,Jpan,Latn`，使其同时参与 PDF 内文字替换
     （否则简体独有字会报 `Japanese fallback font has no glyph for U+XXXX`）；
  3. 安装界面新增「选择安装位置」。
- 名称 `PdfCraft` 仅用于说明本软件来源，不构成对其名称或商标的任何主张。
- 随每个 Release 一并分发的 `LICENSE-MIT.txt`、`LICENSE-APACHE.txt`、`NOTICE.txt`
  是上游许可证与声明**原文**；`UNOFFICIAL-BUILD-zh-CN.txt` 说明本构建具体改了什么。

## 为什么需要它

PdfCraft 把界面译文用 `include_str!()` **编译进二进制**，所以界面是不是中文，
只取决于「编译的是哪个 commit」。上游 `v0.2.1` 官方安装包只有 English / 日本語，
而 `main` 分支已经有完整简体中文（`crates/ui-egui/src/i18n/zh-hans.tsv`）。
本工作流直接编译 `main`，因此产出的安装包开箱即中文。

## 怎么用

**下载安装包**：打开本仓库的 [Releases](../../releases) 页面，下载 `*.msi` 双击安装即可。

**手动触发一次构建**：
`Actions` → 左侧选「构建简体中文版 (Windows)」→ `Run workflow`。
`upstream_ref` 保持默认的 `main` 即可（填不含中文的旧 tag 会被自动跳过）。

## 自动跟版

工作流每天检查一次上游最新 Release，**仅在它确实包含简体中文词条时**才编译，
结果放到 Releases 页面。

两个已知注意事项：

- 上游当前最新 Release（v0.2.1）不含中文，因此定时任务会持续「空转」跳过，
  这是有意的防呆设计。等上游发布带中文的版本就会自动出包。
- 公开仓库连续 60 天无提交时 GitHub 会自动停用定时任务且不通知，所以工作流里
  带了一个 `keepalive` 保活步骤，会自动补空提交重置计时。

## 注意事项

- 产物**未做代码签名**（官方用付费的 Azure Trusted Signing）。首次运行 Windows
  可能提示「未知发布者」，点「更多信息 → 仍要运行」即可。
- 软件里的 **帮助 → 检查更新** 指向的是**官方**发布页（英文包），
  适合用来判断上游有没有发新版，但**不要用它下载**，请回到本仓库 Releases。
- 本仓库仅修改构建配置，未修改上游源码；上游更新后无需手动同步本仓库。

## 许可证、署名与改动声明

PdfCraft 采用 **MIT OR Apache-2.0** 双许可。每个 Release 都附带：

| 文件 | 内容 |
|---|---|
| `LICENSE-MIT.txt`、`LICENSE-APACHE.txt` | 上游许可证全文 |
| `NOTICE.txt` | 上游版权声明、商标说明与第三方组件许可清单 |
| `UNOFFICIAL-BUILD-zh-CN.txt` | 本构建的改动说明（非官方声明）|

便携版 zip 内同时含 `LICENSE-MIT`、`LICENSE-APACHE`、`README.md` 与内嵌字体的许可文件。

**界面中文字体署名**：本构建嵌入了 **HarmonyOS Sans 字体**，由 Huawei Device Co., Ltd.
授权，未经修改地随程序分发，许可全文见便携版内的 `OFL-harmonyos-sans-sc.txt`。

> HarmonyOS Sans fonts are licensed from Huawei Device Co., Ltd.
