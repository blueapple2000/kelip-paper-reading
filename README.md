# kelip-paper-reading · v0.2.0

[English](README.en.md) · [版本记录](CHANGELOG.md)

用原图、公式、数据样本和代码读懂论文，同时核验关键实验、局限与项目应用条件。

本仓库是 [skJack/kelip-paper-reading](https://github.com/skJack/kelip-paper-reading) 的增强衍生版本，基于上传快照 `925953b15813f18b25eeb1a1dca9790f54a47498`。保留原作者 MIT 许可证；不代表原作者发布或背书。

## 三种阅读方式

| 模式 | 示例 | 内容 |
|---|---|---|
| 快速判断 | “这篇值得继续研究吗？” | 任务、贡献、证据、局限，一次回答 |
| 逐步精读 | “带我读懂这篇论文” | 动机→架构→训练→数据→信息流→例子→实验与局限 |
| 项目应用 | “能替换现有系统吗？” | 适配差距、资源证据、最小验证计划 |

尊重“直接讲某一部分”“一次讲完”等要求；不强制每站等待确认。关键数字需要原文位置和版本；推断、独立实测、作者报告及教学示例分开标注。

## 安装与使用

需要 **Python 3.10+**、PyMuPDF；可选 Git 用于读取代码。私有仓库需要已有的 GitHub 访问权限。

```bash
git clone https://github.com/blueapple2000/kelip-paper-reading.git
cd kelip-paper-reading
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell 改用：.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

在支持本地 skills 的 agent 中，按该宿主规则安装此目录；或让 agent 读取本仓库的 `SKILL.md`。本仓库不自动修改任何 agent 配置。可用提示：

> 使用 kelip-paper-reading，快速判断这篇论文的核心贡献、实验是否支持其结论，以及适合什么应用。

## 材料获取

```bash
# 第一轮只获取 PDF、文本和大纲
python scripts/fetch_paper.py 2410.24164v1 --dest ./papers/example-v1 --level quick

# 继续补充源码、图表和候选代码链接
python scripts/fetch_paper.py ./papers/example-v1 --level full

# 离线分析本地 PDF
python scripts/fetch_paper.py ./input.pdf --dest ./papers/local --offline

# 人工核对仓库归属后再指定代码；URL 必须为 GitHub HTTPS 仓库根地址
python scripts/fetch_paper.py ./papers/example-v1 --code https://github.com/owner/repo

# 仅记录选择，不下载代码
python scripts/fetch_paper.py ./papers/example-v1 --code https://github.com/owner/repo --no-clone
```

一个目录固定一篇论文的一个版本。重复运行时直接传论文目录；获取新版本使用新目录。脚本不自动更新已有代码，以保持引用提交一致。

`--level quick` 避免预先下载源码、裁全部图片和查找代码。`--offline` 禁止网络与克隆，但仍处理本地已有材料。联网请求有超时和大小限制，实际耗时取决于网络及论文大小，不承诺固定秒数。

## 可追溯性与文件保护

- `meta.json`：PDF 哈希、arXiv 固定版本、源码各文件哈希、来源状态、候选代码及所选仓库提交号。
- 论文版本无法确认时明确标记。旧目录的源码无法证明与 PDF 一致时标为 `user-or-legacy-source-unverified`，关键公式和表格需要人工对照 PDF。
- 自动发现的链接只进入 `code_candidates`；分数不代表官方身份。`--code` 表示用户/agent 已核对后作出的选择，脚本不作独立认证。
- 修改或替换固定版本的 PDF/源码时停止处理，避免旧笔记混入新材料；独立裁图入口也检查 PDF 哈希。
- 非空代码目录必须是来源匹配的有效 Git 仓库；不会清空用户目录。
- 人工修改过的图片按标记或内容哈希保护。旧版索引没有哈希时保守保留；需要重新生成时，在备份后明确移走对应图片。
- 用户自己的 `figures/` 不被覆盖；已有 `figures-auto/` 也有用户内容时自动选择其他目录。
- 源码归档、LaTeX 引用限制在源码目录内；限制下载与解压体积。只读论文代码，不执行其脚本。

## 裁图与输出

```bash
python scripts/extract_figures.py ./papers/example-v1
python scripts/crop.py ./papers/example-v1/paper.pdf --page 3 --grid
python scripts/crop.py ./papers/example-v1/paper.pdf --page 3 0.1 0.1 0.9 0.6 -o ./papers/example-v1/figures/fig-01.png
```

图表索引中保留页码、caption、裁剪坐标及人工修正信息。重跑不会覆盖人工修图。先查看 `_contact.png`，再逐张核对关键图；坐标取值为 0–1。

逐步精读时，由 agent 按模板更新 `精读笔记.md` 和 `reading-state.json`；脚本本身只准备材料，不调用大模型或生成论文结论。个人偏好存到宿主记忆或用户指定的私有位置，不自动写入共享 skill。

## 验证与限制

```bash
python -m unittest discover -s tests -v
```

测试使用合成 PDF、临时归档、临时代码仓库与网络模拟，覆盖路径边界、版本固定、缓存保留、候选仓库处理、离线流程、人工裁图和错误参数。CI 配置了 Python 3.10、3.12、3.13；本地实际验证环境为 Python 3.12 / PyMuPDF 1.26.6。配置矩阵不代表各环境均已完成运行。

- 裁图仍依赖 caption 和版式规则，需要视觉核对；没有覆盖所有真实期刊版式。
- 扫描 PDF 会提示需要 OCR/视觉阅读，不内置 OCR。
- LaTeX 拍平是有限解析，不完整模拟 TeX 宏和条件编译。
- 无代码/权重时仍可解释论文，但不能声称已复现或已验证部署性能。
- 此版本不声称真实论文在线下载链路已全面验证；网络服务变化可能需要维护。

## 文件

`SKILL.md` 是入口；`references/` 提供证据、领域和项目应用检查表及笔记模板；`scripts/` 准备材料；`tests/` 是离线回归测试。`agents/openai.yaml` 提供兼容宿主的展示信息。

MIT，原作者 © 2026 skJack。参见 [LICENSE](LICENSE)。
