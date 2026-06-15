"""Research report: LangGraph Runtime Postgres Open Source Status."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Register Chinese fonts ──
FONT_DIR = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("MSYH", os.path.join(FONT_DIR, "msyh.ttc"), subfontIndex=0))
pdfmetrics.registerFont(TTFont("MSYHBD", os.path.join(FONT_DIR, "msyhbd.ttc"), subfontIndex=0))

# ── Colors ──
C_PRIMARY = HexColor("#1a56db")
C_SUCCESS = HexColor("#16a34a")
C_WARNING = HexColor("#d97706")
C_DANGER = HexColor("#dc2626")
C_GRAY = HexColor("#6b7280")
C_TABLE_HEADER = HexColor("#1e3a5f")
C_TABLE_ALT = HexColor("#f0f4ff")

# ── Styles ──
styles = getSampleStyleSheet()

s_title = ParagraphStyle("TitleCN", parent=styles["Title"],
    fontName="MSYHBD", fontSize=22, leading=28, textColor=C_PRIMARY, spaceAfter=6*mm)

s_h1 = ParagraphStyle("H1CN", parent=styles["Heading1"],
    fontName="MSYHBD", fontSize=16, leading=22, textColor=C_PRIMARY,
    spaceBefore=8*mm, spaceAfter=4*mm)

s_h2 = ParagraphStyle("H2CN", parent=styles["Heading2"],
    fontName="MSYHBD", fontSize=13, leading=18, textColor=HexColor("#1e40af"),
    spaceBefore=5*mm, spaceAfter=3*mm)

s_h3 = ParagraphStyle("H3CN", parent=styles["Heading3"],
    fontName="MSYHBD", fontSize=11, leading=15, textColor=HexColor("#374151"),
    spaceBefore=3*mm, spaceAfter=2*mm)

s_body = ParagraphStyle("BodyCN", parent=styles["Normal"],
    fontName="MSYH", fontSize=9.5, leading=14, textColor=black,
    alignment=TA_JUSTIFY, spaceAfter=2*mm)

s_code = ParagraphStyle("CodeCN", parent=styles["Code"],
    fontName="Courier", fontSize=8, leading=11, textColor=HexColor("#1e293b"),
    backColor=HexColor("#f1f5f9"), leftIndent=3*mm, rightIndent=3*mm,
    spaceBefore=1*mm, spaceAfter=2*mm)

s_bullet = ParagraphStyle("BulletCN", parent=s_body,
    leftIndent=8*mm, bulletIndent=3*mm, spaceAfter=1.5*mm)

s_toc = ParagraphStyle("TOCCN", parent=s_body, fontSize=11, leading=18,
    leftIndent=5*mm, textColor=C_PRIMARY)

# ── Helpers ──
def P(text, style=s_body):
    return Paragraph(text, style)

def H1(text):
    return Paragraph(text, s_h1)

def H2(text):
    return Paragraph(text, s_h2)

def H3(text):
    return Paragraph(text, s_h3)

def Code(text):
    return Paragraph(text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>"), s_code)

def Bullet(text):
    return Paragraph(f"\u2022  {text}", s_bullet)

def make_table(headers, rows, col_widths=None):
    """Create a styled table with Chinese font."""
    header_row = [Paragraph(f"<b>{h}</b>", ParagraphStyle("TH", fontName="MSYHBD",
        fontSize=8.5, leading=12, textColor=white, alignment=TA_CENTER)) for h in headers]
    data = [header_row]
    for row in rows:
        data.append([Paragraph(str(c), ParagraphStyle("TD", fontName="MSYH",
            fontSize=8.5, leading=12, textColor=black)) for c in row])

    if col_widths is None:
        col_widths = [None] * len(headers)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), C_TABLE_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, C_TABLE_ALT]),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


# ═══════════════════════════════════════════════════════════════
# Build Document
# ═══════════════════════════════════════════════════════════════
output_path = "G:/code/my_lf/docs/postgres_runtime_opensource_research.pdf"
doc = SimpleDocTemplate(output_path, pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm,
    title="LangGraph Runtime Postgres 开源情况调研报告",
    author="Claude Code")

story = []

# ── Cover ──
story.append(Spacer(1, 30*mm))
story.append(P("LangGraph Runtime Postgres", ParagraphStyle("CoverTitle",
    fontName="MSYHBD", fontSize=28, leading=36, textColor=C_PRIMARY, alignment=TA_CENTER)))
story.append(Spacer(1, 5*mm))
story.append(P("开源情况调研报告", ParagraphStyle("CoverSub",
    fontName="MSYHBD", fontSize=18, leading=24, textColor=HexColor("#374151"), alignment=TA_CENTER)))
story.append(Spacer(1, 15*mm))
story.append(P("官方 Postgres Runtime 架构分析与 postgres_py 项目定位", ParagraphStyle("CoverSub2",
    fontName="MSYH", fontSize=14, leading=20, textColor=C_GRAY, alignment=TA_CENTER)))
story.append(Spacer(1, 20*mm))
story.append(P("2026-06-15", ParagraphStyle("CoverDate",
    fontName="MSYH", fontSize=12, textColor=C_GRAY, alignment=TA_CENTER)))

story.append(PageBreak())

# ── Table of Contents ──
story.append(H1("目录"))
toc_items = [
    "1. 调研背景与目的",
    "2. 官方开源声明",
    "3. 官方架构分析",
    "4. 开源范围界定",
    "5. PyPI 包发布情况",
    "6. 自研 postgres_py 定位",
    "7. 技术选型建议",
    "8. 参考资料",
]
for item in toc_items:
    story.append(P(item, s_toc))
story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════
# Section 1: Background
# ═══════════════════════════════════════════════════════════════
story.append(H1("1. 调研背景与目的"))
story.append(P("在开发 <b>langgraph_runtime_postgres_py</b> 项目的过程中，我们需要明确以下问题："))
story.append(Bullet("官方是否已经开源了 LangGraph Runtime Postgres？"))
story.append(Bullet("如果开源了，开源的范围和程度如何？"))
story.append(Bullet("官方实现与我们的自研方案有何差异？"))
story.append(Bullet("自研方案是否仍有价值？"))

story.append(P("本报告通过查阅官方文档、博客、GitHub 仓库以及分析本地安装的代码包，对以上问题进行解答。"))

# ═══════════════════════════════════════════════════════════════
# Section 2: Official Announcement
# ═══════════════════════════════════════════════════════════════
story.append(H1("2. 官方开源声明"))
story.append(P("LangChain 于 <b>2025年1月28日</b> 在官方博客宣布开源 LangGraph Runtime for Postgres："))
story.append(Bullet("博客标题：\"Announcing LangGraph Runtime for Postgres\""))
story.append(Bullet("原文表述：\"We're excited to announce the open source release of LangGraph Runtime for Postgres.\""))
story.append(Bullet("定位：生产级、自托管、开源的运行时方案"))

story.append(H2("LangGraph 平台层级"))
story.append(make_table(
    ["层级", "类型", "说明"],
    [
        ["Postgres Runtime", "开源 (自托管)", "生产级、自管理运行时，支持 PostgreSQL 持久化"],
        ["Local Runtime", "免费", "仅限本地开发使用"],
        ["Enterprise", "商业", "企业级支持，需联系销售"],
    ],
    col_widths=[35*mm, 35*mm, 110*mm]
))

story.append(Spacer(1, 3*mm))
story.append(P("官方文档明确将 Postgres Runtime 定义为 <b>\"Open source, self-hosted\"</b>（开源、自托管）。"))

# ═══════════════════════════════════════════════════════════════
# Section 3: Architecture Analysis
# ═══════════════════════════════════════════════════════════════
story.append(H1("3. 官方架构分析"))
story.append(P("通过分析本地安装的 <b>langgraph_api 0.10.0</b> 代码，我们发现了官方的架构实现方式。"))

story.append(H2("3.1 核心发现：Go + Python 双进程架构"))
story.append(P("官方 Postgres Runtime 并非纯 Python 实现，而是采用 <b>Go + Python 双进程架构</b>："))
story.append(Bullet("<b>Python 层</b>：langgraph-api 包，提供 HTTP API 接口"))
story.append(Bullet("<b>Go 层</b>：独立的持久化服务，通过 gRPC 与 Python 层通信"))

story.append(H2("3.2 代码证据：feature_flags.py"))
story.append(P("在 langgraph_api/feature_flags.py 中定义了 edition 检测逻辑："))
story.append(Code(
    "_RUNTIME_EDITION = os.getenv(\"LANGGRAPH_RUNTIME_EDITION\", \"inmem\")\n"
    "IS_POSTGRES_BACKEND = _RUNTIME_EDITION == \"postgres\"\n"
    "IS_POSTGRES_OR_GRPC_BACKEND = IS_POSTGRES_BACKEND"
))

story.append(H2("3.3 多态分发模式"))
story.append(P("API 路由根据 edition 选择不同的 ops 实现："))
story.append(Code(
    "# langgraph_api/api/threads.py\n"
    "from langgraph_api.feature_flags import IS_POSTGRES_OR_GRPC_BACKEND\n\n"
    "if IS_POSTGRES_OR_GRPC_BACKEND:\n"
    "    from langgraph_api.grpc.ops import Threads  # gRPC client (调用 Go 服务)\n"
    "else:\n"
    "    from langgraph_runtime.ops import Threads  # Python 直连"
))

story.append(H2("3.4 架构对比图解"))
story.append(make_table(
    ["架构", "Python 进程", "Go 进程", "数据流向"],
    [
        ["官方 postgres", "langgraph-api (HTTP)", "持久化服务 (gRPC)", "Python \u2192 gRPC \u2192 Go \u2192 PostgreSQL"],
        ["官方 inmem", "langgraph-api", "无", "Python \u2192 内存字典"],
        ["自研 postgres_py", "langgraph-api", "无", "Python \u2192 psycopg3 \u2192 PostgreSQL"],
    ],
    col_widths=[30*mm, 40*mm, 40*mm, 70*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 4: Open Source Scope
# ═══════════════════════════════════════════════════════════════
story.append(H1("4. 开源范围界定"))
story.append(P("官方宣称的\"开源\"存在范围限制："))

story.append(H2("4.1 已开源部分"))
story.append(Bullet("<b>langgraph-api</b>：Python API 服务层，提供 REST API 和 WebSocket 接口"))
story.append(Bullet("<b>langgraph-runtime-inmem</b>：纯 Python 的内存运行时，用于开发测试"))
story.append(Bullet("<b>langgraph SDK</b>：核心图编排库"))
story.append(Bullet("<b>checkpoint-postgres</b>：PostgreSQL checkpoint saver（但仅限 checkpoint 层）"))

story.append(H2("4.2 未开源部分"))
story.append(Bullet("<b>Go 持久化服务</b>：官方 Docker 镜像中包含的二进制文件，源码未公开"))
story.append(Bullet("<b>gRPC 协议定义</b>：部分 proto 文件未公开"))
story.append(Bullet("<b>企业级特性</b>：高级监控、集群支持等"))

story.append(H2("4.3 开源程度总结"))
story.append(make_table(
    ["组件", "开源状态", "说明"],
    [
        ["Python API 层", "\u2705 完全开源", "langgraph-api 包，pip 可安装"],
        ["Go 持久化服务", "\u274c 未开源", "仅提供 Docker 镜像中的二进制"],
        ["gRPC 通信层", "\u26a0\ufe0f 部分开源", "Python 客户端开源，Go 服务端闭源"],
        ["PostgreSQL Schema", "\u2705 开源", "可通过迁移文件获取"],
    ],
    col_widths=[40*mm, 30*mm, 110*mm]
))

story.append(P("<b>关键结论</b>：官方 Postgres Runtime 的核心持久化逻辑（Go 服务）<b>未开源</b>，用户只能通过 Docker 镜像使用闭源二进制。"))

# ═══════════════════════════════════════════════════════════════
# Section 5: PyPI Status
# ═══════════════════════════════════════════════════════════════
story.append(H1("5. PyPI 包发布情况"))
story.append(P("我们查询了 PyPI 官方仓库："))

story.append(H2("5.1 已发布的包"))
story.append(make_table(
    ["包名", "版本", "说明"],
    [
        ["langgraph-api", "0.10.0", "Python API 服务，提供 HTTP/gRPC 接口"],
        ["langgraph-runtime-inmem", "0.30.0", "内存运行时，用于开发测试"],
        ["langgraph-checkpoint-postgres", "2.0.x", "PostgreSQL checkpoint saver"],
    ],
    col_widths=[55*mm, 25*mm, 100*mm]
))

story.append(H2("5.2 未发布的包"))
story.append(Bullet("<b>langgraph-runtime-postgres</b>：PyPI 上<b>不存在</b>此包"))
story.append(Bullet("官方通过 Docker 镜像分发，而非 pip install"))

story.append(H2("5.3 安装方式"))
story.append(P("官方推荐的安装方式："))
story.append(Code(
    "# 使用 Docker Compose\n"
    "docker run -d langchain/langgraph-api:latest \\\n"
    "    -e LANGGRAPH_RUNTIME_EDITION=postgres \\\n"
    "    -e DATABASE_URI=postgresql://... \\\n"
    "    ..."
))

# ═══════════════════════════════════════════════════════════════
# Section 6: postgres_py Positioning
# ═══════════════════════════════════════════════════════════════
story.append(H1("6. 自研 postgres_py 定位"))
story.append(P("基于以上调研，我们的 <b>langgraph_runtime_postgres_py</b> 项目具有独特价值。"))

story.append(H2("6.1 方案对比"))
story.append(make_table(
    ["特性", "官方 Postgres Runtime", "自研 postgres_py"],
    [
        ["架构", "Go + Python 双进程", "纯 Python 单进程"],
        ["核心代码", "Go 层闭源", "完全开源"],
        ["依赖", "Docker + Go 二进制", "仅需 PostgreSQL + Redis"],
        ["调试", "需调试 Go + Python", "纯 Python，易调试"],
        ["可定制性", "受限于闭源层", "完全可控"],
        ["部署", "必须 Docker", "支持 pip install"],
        ["Edition", "postgres", "postgres_py"],
    ],
    col_widths=[35*mm, 55*mm, 60*mm]
))

story.append(H2("6.2 自研方案优势"))
story.append(Bullet("<b>完全开源</b>：无需依赖闭源二进制，代码完全透明"))
story.append(Bullet("<b>轻量部署</b>：无需 Docker，可直接 pip install 使用"))
story.append(Bullet("<b>易于调试</b>：纯 Python 代码，IDE 断点调试无障碍"))
story.append(Bullet("<b>高度可控</b>：可根据需求修改核心逻辑"))
story.append(Bullet("<b>学习价值</b>：深入理解 LangGraph 运行时原理"))

story.append(H2("6.3 自研方案劣势"))
story.append(Bullet("需要自行维护 ops.py 接口与官方同步"))
story.append(Bullet("缺少官方企业级特性支持"))
story.append(Bullet("需要自行实现 TTL sweep 等后台任务"))

# ═══════════════════════════════════════════════════════════════
# Section 7: Recommendations
# ═══════════════════════════════════════════════════════════════
story.append(H1("7. 技术选型建议"))
story.append(P("根据不同场景，给出以下建议："))

story.append(H2("7.1 选择官方 Postgres Runtime 的场景"))
story.append(Bullet("企业生产环境，需要官方支持"))
story.append(Bullet("不需要定制核心逻辑"))
story.append(Bullet("接受使用 Docker 部署"))
story.append(Bullet("不需要了解底层实现细节"))

story.append(H2("7.2 选择自研 postgres_py 的场景"))
story.append(Bullet("需要完全掌控代码，不接受闭源依赖"))
story.append(Bullet("需要深度定制或二次开发"))
story.append(Bullet("需要轻量级部署，不想依赖 Docker"))
story.append(Bullet("用于学习研究 LangGraph 运行时原理"))
story.append(Bullet("对代码透明度有严格要求的项目"))

story.append(H2("7.3 总结"))
story.append(make_table(
    ["决策因素", "官方方案", "自研方案"],
    [
        ["生产稳定性", "\u2705 官方维护", "\u26a0\ufe0f 自行负责"],
        ["代码透明度", "\u274c 部分闭源", "\u2705 完全开源"],
        ["部署复杂度", "\u26a0\ufe0f 需要 Docker", "\u2705 pip install"],
        ["定制灵活性", "\u274c 受限", "\u2705 完全自由"],
        ["技术支持", "\u2705 官方支持", "\u274c 自行解决"],
    ],
    col_widths=[35*mm, 45*mm, 50*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 8: References
# ═══════════════════════════════════════════════════════════════
story.append(H1("8. 参考资料"))
story.append(Bullet("<b>官方博客</b>：https://blog.langchain.dev/announcing-langgraph-runtime-for-postgres/"))
story.append(Bullet("<b>平台概述</b>：https://langchain-ai.github.io/langgraph/concepts/langgraph_platform/"))
story.append(Bullet("<b>Postgres Runtime 文档</b>：https://langchain-ai.github.io/langgraph/how-tos/deploy/postgres-runtime/"))
story.append(Bullet("<b>GitHub 主仓库</b>：https://github.com/langchain-ai/langgraph"))
story.append(Bullet("<b>PyPI - langgraph-api</b>：https://pypi.org/project/langgraph-api/"))
story.append(Bullet("<b>PyPI - langgraph-runtime-inmem</b>：https://pypi.org/project/langgraph-runtime-inmem/"))

story.append(Spacer(1, 10*mm))
story.append(P("\u2014 报告结束 \u2014", ParagraphStyle("EndMark",
    fontName="MSYH", fontSize=10, textColor=C_GRAY, alignment=TA_CENTER)))

# ── Build PDF ──
doc.build(story)
print(f"PDF saved to: {output_path}")
