# 渲染与发布管线（含环境适配）

## 管线总览

`.md`（工作区根目录）→ `publish.py` 批量转换 → `reports/*.html` + `reports/index.html` → `serve.sh` 起端口 → 用户本地浏览器访问 `http://<远端主机>:8899/`。渲染全部在远端完成，无需本地渲染。

## 脚本

```bash
# 批量发布（扫描 <root>/*.md，跳过 README*，输出 <root>/reports/）
python3 skills/document/scripts/publish.py [--root DIR] [--out DIR]

# 单份转换
python3 skills/document/scripts/md2html.py <report.md> [--out DIR]

# 服务管理（默认 8899）
bash skills/document/scripts/serve.sh [start|stop|<port>]
```

## 转换器能力

- GFM 管道表格、围栏代码块、有序/无序列表、引用块
- mermaid：渲染为 `.mermaid` div，jsdelivr CDN 加载，失败自动降级为源码块
- 可靠性徽章：`C` / `C*` / `S` / `P` / `?` 自动转为带 title 提示的彩色徽章（仅遗留报告使用；2026-10-10 版结构的新报告正文不再含此类标记）
- 侧边栏 TOC（1-3 级标题，sticky）、深色模式、打印样式、移动端折叠
- 全量 HTML 转义后再渲染，防止经 HTTP 服务注入

## 发布后验证（必须执行）

```bash
# HTTP 200 且标题正确（thin SSH 下输出重定向再 Grep）
curl -s -o /dev/null -w "%{http_code}" http://localhost:8899/<report>.html > .skillsearch/code.txt
curl -s http://localhost:8899/<report>.html | grep -o "<title>[^<]*" > .skillsearch/title.txt
```

浏览器侧（browser-use MCP，evaluate_script DOM 检查）：

- 徽章数量与 MD 中标注数一致
- TOC 链接数 = 章节数
- mermaid 渲染为 SVG（`.mermaid svg` 存在）或已明确降级
- 控制台无红色错误

## 发布到个人网站（实时归档）

```bash
# 单份：拷贝 HTML + 合并 _data/reports.yml + commit + push（约 1 分钟后线上生效）
python3 skills/document/scripts/publish_site.py reports/<report>.html \
  --summary "一句话摘要" --tags RISC-V,Linux

# 批量：--manifest 提供 {file,title?,summary?,date?,tags?} 列表
python3 skills/document/scripts/publish_site.py --manifest .skillsearch/reports-manifest.yml

# 只提交不推送 / 仅预览
python3 skills/document/scripts/publish_site.py <html> --no-push
python3 skills/document/scripts/publish_site.py <html> --dry-run
```

- 站点仓库默认 `~/github/daydream0929.github.io`（环境变量 `TECH_REPORT_SITE` 可覆盖），skill 副本位于其 `skills/document/`（不参与站点构建）。
- 线上地址：`https://daydream0929.github.io/reports/<report>.html`；索引页 `reports/index.html` 读取 `_data/reports.yml` 自动列出全部报告。
- 发布结果验证：

```bash
gh run list -R Daydream0929/daydream0929.github.io -L 3
curl -s -o /dev/null -w "%{http_code}" https://daydream0929.github.io/reports/<report>.html
```

## 环境适配（thin SSH 会话）

Agent SDK 与 qodercli 在本地 macOS，工作区在远端 Linux 主机；一切在远端工作区内完成。

| 工具 | 差异 | 对策 |
|------|------|------|
| Bash | 只返回 exitCode | 输出重定向到文件（`.skillsearch/*.txt`）再 Grep |
| Read | 只返回元数据 | 用 Grep `output_mode: content` 看内容 |
| 本地路径 | macOS 本地路径不可达 | 全部用远端工作区路径 |
| 文件监听/多根 | 不可用 | 发布验证用 curl + 浏览器快照 |
| 远端 node | 版本旧，ESM 跑不动 | 脚本零依赖 python3，避免 npx 生态 |

其他注意：

- 服务启动有竞态：curl 失败先 sleep 1 重试再判失败。
- 用户浏览器可访问外网 CDN（已验证 jsdelivr）。
- 写长文件优先一次成文；结构完整性用 Grep 计数校验：

```text
pattern="^## "          → 章节数
pattern="^```mermaid"   → 图数
pattern="`[?CSP][*]?`"  → 标注数
```

计数与写作计划一致才算完成。
