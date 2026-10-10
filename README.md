# daydream0929.github.io

Zhenjun Feng 的个人技术项目门户与技术笔记，使用 Jekyll 构建并由 GitHub Pages 自动部署。

## 添加一个项目

在 `_data/projects.yml` 末尾追加一条记录：

```yaml
- id: example-project
  title: Example Project
  summary: 一句话说明这个项目解决什么问题。
  type: visualization
  type_label: 可视化
  status: live
  status_label: 已上线
  site_url: https://daydream0929.github.io/example-project/
  repo_url: https://github.com/Daydream0929/example-project
  action_label: 打开项目
  tags:
    - Tag One
    - Tag Two
  featured: true
  order: 20
```

推送到 `master` 后，`.github/workflows/jekyll.yml` 会构建并发布站点。

## 本地预览

```bash
bundle install
bundle exec jekyll serve
```

## 技术调研报告集

`reports/` 存放完整的独立 HTML 调研报告（图表内联、离线可读），
`reports/index.html` 从 `_data/reports.yml` 动态生成索引页。日常维护流程：

1. 在工作区用 document skill 生成报告并渲染为自包含 HTML；
2. 运行 document skill 的 `publish_site.py`，脚本把 HTML 复制到 `reports/`、
   按 id 合并 `_data/reports.yml` 条目并提交推送；
3. GitHub Actions 构建后即可在 <https://daydream0929.github.io/reports/> 查看。

`_data/reports.yml` 条目字段：`id / title / summary / date / tags / url`，按 id 合并。

## 内部工具：document skill

`skills/document/` 是生成上述报告的 document skill 副本（编写规范 + 渲染与发布脚本），
仅随仓库做版本管理，已通过 `_config.yml` 的 `exclude` 排除，不发布到站点。
