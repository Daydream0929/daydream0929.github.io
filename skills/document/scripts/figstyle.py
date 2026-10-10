#!/usr/bin/env python3
"""House chart style for report figures.

Usage in a figure script:

    import figstyle
    figstyle.apply()
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4))
    # ...draw...
    figstyle.save(fig, 'eigen-coverage')   # -> reports/figures/eigen-coverage.svg

For architecture/flow diagrams use graphviz:

    src = figstyle.dot_prelude() + 'digraph G { a -> b }'
    figstyle.save_dot(src, 'arch')
"""
import os
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
FIG_DIR = os.path.join(REPO_ROOT, 'reports', 'figures')

PALETTE = {
    'primary': '#4285f4', 'accent': '#ea4335', 'good': '#34a853',
    'warn': '#fbbc04', 'muted': '#9aa0a6', 'dark': '#202124',
    'text': '#3c4043', 'subtle': '#5f6368', 'grid': '#dadce0', 'bg': '#ffffff',
}
SERIES = ['#4285f4', '#ea4335', '#34a853', '#fbbc04', '#9aa0a6', '#a142f4', '#24c1e0']

def apply():
    """Apply house style to matplotlib rcParams. Call before creating figures."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.family': ['Alibaba PuHuiTi 2.0', 'Droid Sans Fallback', 'sans-serif'],
        'font.size': 11,
        'axes.unicode_minus': False,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.edgecolor': PALETTE['grid'],
        'axes.linewidth': 0.8,
        'axes.labelcolor': PALETTE['text'],
        'axes.titlesize': 13,
        'axes.titlecolor': PALETTE['dark'],
        'axes.titlepad': 12,
        'xtick.color': PALETTE['subtle'],
        'ytick.color': PALETTE['subtle'],
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'grid.color': PALETTE['grid'],
        'grid.linestyle': '--',
        'grid.linewidth': 0.6,
        'grid.alpha': 0.5,
        'legend.frameon': False,
        'legend.fontsize': 10,
        'figure.facecolor': PALETTE['bg'],
        'axes.facecolor': PALETTE['bg'],
        'savefig.facecolor': PALETTE['bg'],
        'savefig.bbox': 'tight',
        'savefig.dpi': 150,
    })
    return plt


def value_labels(ax, bars, fmt='{:.0f}', dy=0.0, fontsize=10, color=None):
    """Direct value labels on bar tops; drop chartjunk like legends when possible."""
    color = color or PALETTE['text']
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0, height + dy,
                fmt.format(height), ha='center', va='bottom',
                fontsize=fontsize, color=color)

def save(fig, name, svg=True, png=True):
    """Save figure to reports/figures/<name>.svg (+ .png). Returns markdown path.

    Markdown 引用 PNG（工作区预览器不渲染 SVG）；**不要**把该函数的返回值
    直接当图片路径，请把 .svg 改成 .png。SVG 仅作为矢量源保留。
    """
    os.makedirs(FIG_DIR, exist_ok=True)
    if svg:
        fig.savefig(os.path.join(FIG_DIR, name + '.svg'))
    if png:
        fig.savefig(os.path.join(FIG_DIR, name + '.png'))
    print('![图：%s](figures/%s.png)' % (name, name))
    return 'figures/%s.png' % name


def dot_prelude():
    """Styled DOT prelude for architecture/flow diagrams; append digraph body."""
    return ('  graph [fontname="Helvetica", bgcolor="white", pad="0.35", '
            'nodesep="0.55", ranksep="0.85"];\n'
            '  node [fontname="Helvetica", fontsize=12, shape=box, '
            'style="rounded,filled", fillcolor="#e8f0fe", color="#4285f4", '
            'fontcolor="#202124", margin="0.16,0.09"];\n'
            '  edge [fontname="Helvetica", fontsize=10, color="#5f6368", '
            'arrowsize="0.7"];\n')


def save_dot(dot_body, name, engine='dot', svg=True, png=True, dpi=192):
    """Render DOT body (without digraph wrapper) to <name>.svg and a high-res <name>.png.

    Markdown 图片引用必须用 PNG 路径（工作区预览器不渲染 SVG）；PNG 以
    ``-Gdpi=192`` 输出以便预览放大后仍清晰；SVG 作为矢量源供 HTML 发布内嵌。
    """
    os.makedirs(FIG_DIR, exist_ok=True)
    full = 'digraph __g {\n' + dot_body + '\n}\n'
    tmp_dot = os.path.join(FIG_DIR, name + '.dot')
    with open(tmp_dot, 'w', encoding='utf-8') as handle:
        handle.write(full)
    for ext in (['svg'] if svg else []) + (['png'] if png else []):
        target = os.path.join(FIG_DIR, '%s.%s' % (name, ext))
        args = [engine, '-T' + ext]
        if ext == 'png':
            args.append('-Gdpi=%d' % dpi)
        args += [tmp_dot, '-o', target]
        subprocess.run(args, check=True)
    os.remove(tmp_dot)
    print('![图：%s](figures/%s.png)' % (name, name))
    return 'figures/%s.png' % name
