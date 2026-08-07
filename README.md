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
