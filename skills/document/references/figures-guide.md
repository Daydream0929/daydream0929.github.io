# 图表规范（图文并茂是硬要求）

头部公司报告（GPT-4 / Gemini / NVIDIA 技术博客）的共同点：图承担主要说服力——评估结果几乎全用图表呈现，正文只做解读。本工作区要求一致：**数据一律成图，机制一律成图，表格只留精确值**。纯文字长报告视为不合格。

## 工具分工（已验证可用）

| 图类型 | 工具 | 说明 |
|--------|------|------|
| 数据图（柱状/折线/散点/热力图） | matplotlib 3.7.5 | 经 figstyle.py 房屋风格 |
| 架构图 / 流程图 / 依赖图 / 状态机 | graphviz 2.43（dot） | 布局专业，替代 mermaid |
| ~~mermaid~~ | 弃用 | 布局与观感不达标；存量报告暂不迁移 |

环境事实（2026-09-04 核实）：远端 python3.8 + matplotlib 3.7.5（user 安装，经清华镜像）；中文字体用系统 Alibaba PuHuiTi 2.0（matplotlib 文字默认转矢量路径，浏览器零字体依赖）；graphviz 在 /usr/bin/dot。

## 房屋风格（figstyle.py）

写图脚本的标准开头：

```python
import sys
sys.path.insert(0, '<workspace>/skills/document/scripts')
import figstyle
plt = figstyle.apply()          # 中文字体 + 去 top/right 边框 + 网格风格
fig, ax = plt.subplots(figsize=(7, 3.6))
# ...画图...
figstyle.save(fig, 'reportname-chart1')   # 存 reports/figures/*.svg + .png，打印 md 引用行
```

graphviz 图：

```python
body = figstyle.dot_prelude() + '''
  a [label="编译目标", fillcolor="#fce8e6", color="#ea4335"];
  b [label="RVV10 后端", fillcolor="#e6f4ea", color="#34a853"];
  a -> b [label="启用"];
'''
figstyle.save_dot(body, 'reportname-arch')
```

风格要点（NVIDIA 博客风）：直接数值标签（figstyle.value_labels）；单色为主、语义色点缀（红=错误/绿=通过/黄=门控/灰=弃用）；无立体、无阴影、无多余图例；标题讲结论而非名词（"FP16 吞吐受 float 路径限制"优于"FP16 性能图"）。

## 数量与编号

- 长报告（>10 章）：主体章节至少每 2-3 章一张图；每份报告至少 3 张图。
- 统一编号：图 1、图 2……题注写在 md 引用行 `![图 N：结论式标题](figures/xxx.svg)`。
- 正文必须显式引用每张图（"如图 2 所示，……"），没有正文引用的图删掉。
- 数据既出图又出表：图给形状与对比，表给精确值，两者都要。

## 生成与验证流程

1. 图脚本放 /tmp 或 .figs/（一次性），输出固定到 reports/figures/（发布目录，随报告一起被端口服务）。
2. md 里引用相对路径 `figures/<name>.svg`；md2html 渲染为带题注的 figure。
3. 发布后浏览器验证：图 URL 可达、figure/figcaption 元素存在、无 404。
4. 图的生成脚本若含关键数据转换，把脚本存档到报告同目录 `.figs/`（数据可复现原则同样适用于图）。
