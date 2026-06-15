"""Report: LangGraph gRPC Architecture Explained for Beginners."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
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
C_PYTHON = HexColor("#3776ab")
C_GO = HexColor("#00add8")
C_GRPC = HexColor("#244c5a")

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

s_callout = ParagraphStyle("CalloutCN", parent=s_body,
    fontName="MSYHBD", fontSize=10, leading=14, textColor=HexColor("#1e40af"),
    backColor=HexColor("#eff6ff"), leftIndent=3*mm, rightIndent=3*mm,
    spaceBefore=2*mm, spaceAfter=2*mm, borderWidth=1,
    borderColor=HexColor("#3b82f6"), borderPadding=4)

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

def Callout(text):
    return Paragraph(text, s_callout)

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
output_path = "G:/code/my_lf/docs/grpc_architecture_explained.pdf"
doc = SimpleDocTemplate(output_path, pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm,
    title="LangGraph gRPC 架构详解 - 面向小白的完整指南",
    author="Claude Code")

story = []

# ── Cover ──
story.append(Spacer(1, 30*mm))
story.append(P("LangGraph gRPC 架构详解", ParagraphStyle("CoverTitle",
    fontName="MSYHBD", fontSize=28, leading=36, textColor=C_PRIMARY, alignment=TA_CENTER)))
story.append(Spacer(1, 5*mm))
story.append(P("面向小白的完整指南", ParagraphStyle("CoverSub",
    fontName="MSYHBD", fontSize=18, leading=24, textColor=HexColor("#374151"), alignment=TA_CENTER)))
story.append(Spacer(1, 15*mm))
story.append(P("Python \u2192 gRPC \u2192 Go 调用链路与图执行位置全解析", ParagraphStyle("CoverSub2",
    fontName="MSYH", fontSize=14, leading=20, textColor=C_GRAY, alignment=TA_CENTER)))
story.append(Spacer(1, 20*mm))
story.append(P("2026-06-15", ParagraphStyle("CoverDate",
    fontName="MSYH", fontSize=12, textColor=C_GRAY, alignment=TA_CENTER)))

story.append(PageBreak())

# ── Table of Contents ──
story.append(H1("目录"))
toc_items = [
    "1. 写给小白：什么是 gRPC？",
    "2. 官方架构全景图",
    "3. Python 端：gRPC 客户端",
    "4. Go 端：核心服务",
    "5. 完整调用链路（带时序图）",
    "6. 核心问题：图在哪里执行？",
    "7. Checkpoint 存储机制",
    "8. 流事件分发机制",
    "9. 总结与对比",
]
for item in toc_items:
    story.append(P(item, s_toc))
story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════
# Section 1: gRPC Basics
# ═══════════════════════════════════════════════════════════════
story.append(H1("1. 写给小白：什么是 gRPC？"))
story.append(P("在深入 LangGraph 架构之前，我们需要先理解 gRPC 是什么。本节假设你完全没有 gRPC 背景。"))

story.append(H2("1.1 传统方式：REST API"))
story.append(P("你可能熟悉 REST API：客户端发送 HTTP 请求，服务器返回 JSON 响应。"))
story.append(Code(
    "# 客户端\n"
    "response = requests.get('https://api.example.com/threads/123')\n"
    "thread = response.json()  # 解析 JSON\n\n"
    "# 服务端\n"
    "@app.get('/threads/{thread_id}')\n"
    "def get_thread(thread_id):\n"
    "    return {'id': thread_id, 'name': 'My Thread'}"
))

story.append(H2("1.2 gRPC 方式：像调用本地函数一样"))
story.append(P("gRPC 让你<b>像调用本地函数一样</b>调用远程服务："))
story.append(Code(
    "# 客户端 - 看起来像本地函数调用！\n"
    "thread = await client.threads.Get(thread_id='123')\n"
    "# 返回的是强类型对象，不是 JSON 字典\n\n"
    "# 服务端 - 实现一个接口\n"
    "class ThreadsServicer:\n"
    "    async def Get(self, request, context):\n"
    "        return Thread(id='123', name='My Thread')"
))

story.append(H2("1.3 gRPC 的核心概念"))
story.append(make_table(
    ["概念", "说明", "类比"],
    [
        ["Protocol Buffers", "定义消息格式的语言，比 JSON 更小更快", "像提前定义好的表格模板"],
        ["Service / Method", "定义可调用的远程方法", "像 REST 的 API 端点"],
        ["Stub / Client", "客户端生成的调用代理", "像电话的拨号键盘"],
        ["Channel", "客户端到服务器的连接", "像电话线"],
        ["Request/Response", "请求和响应消息", "像电话通话内容"],
    ],
    col_widths=[35*mm, 70*mm, 70*mm]
))

story.append(H2("1.4 为什么要用 gRPC？"))
story.append(Bullet("<b>性能</b>：二进制传输，比 JSON 快 5-10 倍"))
story.append(Bullet("<b>类型安全</b>：编译时检查，不会拼错字段名"))
story.append(Bullet("<b>双向流</b>：支持服务端推送，适合实时场景"))
story.append(Bullet("<b>跨语言</b>：Python 调 Go 服务，像调本地函数"))

story.append(H2("1.5 LangGraph 中的应用"))
story.append(P("官方 LangGraph 使用 gRPC 让 <b>Python API 层</b> 调用 <b>Go 持久化服务</b>："))
story.append(Code(
    "# Python 客户端调用 Go 服务\n"
    "client = await get_shared_client()          # 获取 gRPC 客户端\n"
    "thread = await client.threads.Get(          # 调用 Go 的 Get 方法\n"
    "    pb.GetThreadRequest(thread_id='123')\n"
    ")\n"
    "# 看起来像本地调用，实际通过网络发到了 Go 服务"
))

# ═══════════════════════════════════════════════════════════════
# Section 2: Architecture Overview
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("2. 官方架构全景图"))
story.append(P("LangGraph Postgres Runtime 采用 <b>Python + Go 双进程架构</b>："))

story.append(H2("2.1 架构图"))
story.append(Code(
    "┌─────────────────────────────────────────────────────────────────┐\n"
    "│                        用户请求                                  │\n"
    "│                          │                                       │\n"
    "│                          ▼                                       │\n"
    "│  ┌────────────────────────────────────┐                         │\n"
    "│  │        Python 进程                  │                         │\n"
    "│  │  ┌────────────────────────────┐    │                         │\n"
    "│  │  │   FastAPI HTTP Server      │    │                         │\n"
    "│  │  │   (接收 REST 请求)          │    │                         │\n"
    "│  │  └────────────┬───────────────┘    │                         │\n"
    "│  │               │                     │                         │\n"
    "│  │               ▼                     │                         │\n"
    "│  │  ┌────────────────────────────┐    │     gRPC 调用           │\n"
    "│  │  │   gRPC Client (Stub)       │────┼───────────────┐         │\n"
    "│  │  │   (把请求序列化发送)        │    │               │         │\n"
    "│  │  └────────────────────────────┘    │               │         │\n"
    "│  │                                    │               │         │\n"
    "│  │  ┌────────────────────────────┐    │               ▼         │\n"
    "│  │  │   Worker (图执行!)         │    │   ┌───────────────────┐  │\n"
    "│  │  │   graph.astream_events()   │    │   │   Go 进程         │  │\n"
    "│  │  └────────────────────────────┘    │   │                   │  │\n"
    "│  │                                    │   │  ┌─────────────┐  │  │\n"
    "│  │  ┌────────────────────────────┐    │   │  │ gRPC Server│  │  │\n"
    "│  │  │   Checkpointer             │◄───┼───┼──│ (处理请求) │  │  │\n"
    "│  │  │   (存取 checkpoint)         │    │   │  └──────┬──────┘  │  │\n"
    "│  │  └────────────────────────────┘    │   │         │         │  │\n"
    "│  │                                    │   │         ▼         │  │\n"
    "│  └────────────────────────────────────┘   │  ┌─────────────┐  │  │\n"
    "│                                           │  │ PostgreSQL  │  │  │\n"
    "│                                           │  │ (元数据存储) │  │  │\n"
    "│                                           │  └─────────────┘  │  │\n"
    "│                                           └───────────────────┘  │\n"
    "└─────────────────────────────────────────────────────────────────┘"
))

story.append(H2("2.2 两个进程的职责"))
story.append(make_table(
    ["进程", "语言", "职责", "开源状态"],
    [
        ["Python 进程", "Python", "HTTP API、图执行、Checkpoint 存取", "\u2705 完全开源"],
        ["Go 进程", "Go", "元数据 CRUD、流事件分发、TTL 清理", "\u274c 闭源二进制"],
    ],
    col_widths=[30*mm, 20*mm, 70*mm, 30*mm]
))

story.append(Callout("关键发现：图的实际执行在 Python 进程中，Go 进程只负责元数据管理和事件分发！"))

# ═══════════════════════════════════════════════════════════════
# Section 3: Python gRPC Client
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("3. Python 端：gRPC 客户端"))

story.append(H2("3.1 客户端连接池 (client.py)"))
story.append(P("Python 端维护一个 gRPC 客户端池，通过轮询方式分发请求："))
story.append(Code(
    "class GrpcClient:\n"
    "    def __init__(self, server_address):\n"
    "        # 创建到 Go 服务的连接\n"
    "        self._channel = aio.insecure_channel(server_address)\n"
    "        \n"
    "        # 创建各种服务的 Stub（代理）\n"
    "        self._threads_stub = ThreadsStub(self._channel)\n"
    "        self._runs_stub = RunsStub(self._channel)\n"
    "        self._crons_stub = CronsStub(self._channel)\n"
    "        # ... 更多 stub\n\n"
    "class GrpcClientPool:\n"
    "    \"\"\"多个客户端实例，负载均衡\"\"\"\n"
    "    def __init__(self, pool_size=5):\n"
    "        self.clients = [GrpcClient() for _ in range(pool_size)]\n"
    "    \n"
    "    async def get_client(self):\n"
    "        # 轮询选择客户端\n"
    "        return self.clients[self._current_index % self.pool_size]"
))

story.append(H2("3.2 调用示例：获取 Thread"))
story.append(P("当 API 收到 GET /threads/{thread_id} 请求时："))
story.append(Code(
    "# 第一步：API 路由层 (api/threads.py)\n"
    "@router.get('/threads/{thread_id}')\n"
    "async def get_thread(thread_id: str):\n"
    "    async with connect() as conn:\n"
    "        thread = await Threads.get(conn, thread_id)  # 调用 ops\n"
    "    return thread\n\n"
    "# 第二步：gRPC ops 层 (grpc/ops/threads.py)\n"
    "class Threads:\n"
    "    @staticmethod\n"
    "    async def get(conn, thread_id, ctx=None):\n"
    "        # 构造 protobuf 请求\n"
    "        request = pb.GetThreadRequest(\n"
    "            thread_id=pb.UUID(value=str(thread_id))\n"
    "        )\n"
    "        \n"
    "        # 发送 gRPC 请求到 Go 服务\n"
    "        client = await get_shared_client()\n"
    "        response = await client.threads.Get(request)\n"
    "        \n"
    "        # 转换响应为 Python dict\n"
    "        yield proto_to_thread(response.thread)"
))

story.append(H2("3.3 gRPC vs 直连数据库"))
story.append(make_table(
    ["操作类型", "Python 处理方式", "Go 处理方式"],
    [
        ["Thread 元数据 CRUD", "通过 gRPC 发请求", "执行 SQL 操作 PostgreSQL"],
        ["Run 元数据 CRUD", "通过 gRPC 发请求", "执行 SQL 操作 PostgreSQL"],
        ["Checkpoint 读写", "直接调用 Checkpointer", "不参与（或通过反向 gRPC 调 Python）"],
        ["图执行", "直接执行 graph.astream()", "不参与"],
        ["流事件分发", "通过 gRPC 发送事件", "分发给 SSE/WebSocket 订阅者"],
    ],
    col_widths=[40*mm, 50*mm, 60*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 4: Go Service
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("4. Go 端：核心服务"))
story.append(P("Go 服务是官方闭源的二进制文件，我们从 Python 端的调用推断其功能。"))

story.append(H2("4.1 Go 服务提供的 gRPC 接口"))
story.append(make_table(
    ["Service", "主要方法", "功能"],
    [
        ["Threads", "Get, Search, Create, Patch, Delete", "线程元数据管理"],
        ["Runs", "Get, Search, Create, Delete, Next, Enter", "Run 管理 + 队列"],
        ["Assistants", "Get, Search, Create, Patch, Delete", "助手管理"],
        ["Crons", "Get, Search, Create, Delete, Next", "定时任务管理"],
        ["Cache", "Get, Set, Delete", "缓存管理"],
        ["Admin", "Migrate, Health", "运维管理"],
    ],
    col_widths=[30*mm, 60*mm, 60*mm]
))

story.append(H2("4.2 Go 服务的数据库操作"))
story.append(P("Go 服务直接操作 PostgreSQL，处理元数据："))
story.append(Code(
    "-- Go 服务执行的典型 SQL（推断）\n"
    "SELECT * FROM threads WHERE thread_id = $1;\n"
    "INSERT INTO runs (run_id, thread_id, status, ...) VALUES (...);\n"
    "UPDATE threads SET status = 'busy', updated_at = NOW() WHERE thread_id = $1;"
))

story.append(H2("4.3 Go 服务不做什么"))
story.append(Bullet("<b>不执行图</b>：图执行在 Python Worker 中"))
story.append(Bullet("<b>不直接操作 Checkpoint</b>：通过反向 gRPC 调 Python"))
story.append(Bullet("<b>不解析用户代码</b>：用户图定义在 Python 端"))

# ═══════════════════════════════════════════════════════════════
# Section 5: Call Chain
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("5. 完整调用链路（带时序图）"))

story.append(H2("5.1 创建 Run 的完整流程"))
story.append(Code(
    "用户                Python API          gRPC Client          Go Service         PostgreSQL\n"
    "  │                     │                    │                    │                  │\n"
    "  │  POST /runs         │                    │                    │                  │\n"
    "  │────────────────────►│                    │                    │                  │\n"
    "  │                     │                    │                    │                  │\n"
    "  │                     │ Runs.put()         │                    │                  │\n"
    "  │                     │───────────────────►│                    │                  │\n"
    "  │                     │                    │                    │                  │\n"
    "  │                     │                    │ CreateRunRequest   │                  │\n"
    "  │                     │                    │───────────────────►│                  │\n"
    "  │                     │                    │                    │                  │\n"
    "  │                     │                    │                    │ INSERT INTO runs │\n"
    "  │                     │                    │                    │─────────────────►│\n"
    "  │                     │                    │                    │                  │\n"
    "  │                     │                    │                    │     INSERT OK    │\n"
    "  │                     │                    │                    │◄─────────────────│\n"
    "  │                     │                    │                    │                  │\n"
    "  │                     │                    │  CreateRunResponse │                  │\n"
    "  │                     │                    │◄───────────────────│                  │\n"
    "  │                     │                    │                    │                  │\n"
    "  │                     │  AsyncIterator[Run]│                    │                  │\n"
    "  │                     │◄───────────────────│                    │                  │\n"
    "  │                     │                    │                    │                  │\n"
    "  │  201 Created        │                    │                    │                  │\n"
    "  │◄────────────────────│                    │                    │                  │"
))

story.append(H2("5.2 执行 Run 的完整流程"))
story.append(Code(
    "Worker              Python              Checkpointer         Go Service         PostgreSQL\n"
    "  │                   │                      │                    │                  │\n"
    "  │ Runs.next()       │                      │                    │                  │\n"
    "  │─────────────────────────────────────────►│                    │                  │\n"
    "  │                   │                      │ gRPC Next          │                  │\n"
    "  │                   │                      │───────────────────►│                  │\n"
    "  │                   │                      │                    │ SELECT pending   │\n"
    "  │                   │                      │                    │─────────────────►│\n"
    "  │                   │                      │                    │◄─────────────────│\n"
    "  │  Run 对象         │                      │◄───────────────────│                  │\n"
    "  │◄─────────────────────────────────────────│                    │                  │\n"
    "  │                   │                      │                    │                  │\n"
    "  │ Runs.enter()      │                      │                    │                  │\n"
    "  │───────────────────────────────────────────────────────────────►│                  │\n"
    "  │                   │                      │                    │ 标记 running     │\n"
    "  │                   │                      │                    │─────────────────►│\n"
    "  │                   │                      │                    │                  │\n"
    "  │ graph.astream()   │                      │                    │                  │\n"
    "  │──────────────────►│                      │                    │                  │\n"
    "  │                   │                      │                    │                  │\n"
    "  │                   │ aput(checkpoint)     │                    │                  │\n"
    "  │                   │─────────────────────►│                    │                  │\n"
    "  │                   │                      │ 直接写 PostgreSQL  │                  │\n"
    "  │                   │                      │─────────────────────────────────────►│\n"
    "  │                   │                      │                    │                  │\n"
    "  │ Runs.Stream.publish(event)              │                    │                  │\n"
    "  │─────────────────────────────────────────────────────────────►│                  │\n"
    "  │                   │                      │                    │ 分发到订阅者     │\n"
    "  │                   │                      │                    │                  │"
))

# ═══════════════════════════════════════════════════════════════
# Section 6: Where Graph Executes
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("6. 核心问题：图在哪里执行？"))

story.append(Callout("答案：图在 Python 进程的 Worker 中执行，Go 服务完全不参与图的执行！"))

story.append(H2("6.1 图执行的代码证据"))
story.append(P("在 worker.py 中，我们找到了图执行的核心代码："))
story.append(Code(
    "# worker.py (Python 端)\n"
    "async def worker(run: Run, attempt: int, ...):\n"
    "    # 1. 获取图定义（Python 对象）\n"
    "    async with get_graph(graph_id, config, checkpointer=checkpointer) as graph:\n"
    "        \n"
    "        # 2. 执行图！（这是纯 Python 操作）\n"
    "        async for event in graph.astream_events(input, config, ...):\n"
    "            # 3. 处理每个事件\n"
    "            if event['event'] == 'on_chain_start':\n"
    "                # 节点开始执行\n"
    "            elif event['event'] == 'on_chain_end':\n"
    "                # 节点执行完成\n"
    "                \n"
    "            # 4. 发布事件给订阅者\n"
    "            await Runs.Stream.publish(run_id, event_type, payload)"
))

story.append(H2("6.2 为什么图必须在 Python 执行？"))
story.append(Bullet("<b>用户代码在 Python</b>：图的节点是 Python 函数，Go 无法执行"))
story.append(Bullet("<b>LangChain 在 Python</b>：LLM 调用、工具调用都是 Python 库"))
story.append(Bullet("<b>状态类型在 Python</b>：TypedDict、Pydantic 模型都是 Python 类型"))

story.append(H2("6.3 Go 服务的真正角色"))
story.append(P("Go 服务是一个<b>元数据管理和事件分发中间件</b>，不是执行引擎："))
story.append(make_table(
    ["Go 服务角色", "具体功能"],
    [
        ["元数据存储", "管理 Thread、Run、Assistant、Cron 的元数据（存在 PostgreSQL）"],
        ["任务队列", "维护 pending runs 队列，Worker 通过 Runs.next() 拉取"],
        ["事件分发", "接收 Python 发布的事件，分发给 SSE/WebSocket 订阅者"],
        ["TTL 清理", "后台清理过期的 Thread 和 Run"],
        ["健康检查", "监控服务状态"],
    ],
    col_widths=[35*mm, 115*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 7: Checkpoint Mechanism
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("7. Checkpoint 存储机制"))
story.append(P("Checkpoint 是图执行过程中的状态快照，用于暂停/恢复、回滚等功能。"))

story.append(H2("7.1 Checkpoint 存储位置"))
story.append(Bullet("Checkpoint 数据存储在 <b>PostgreSQL</b> 的 checkpoint 相关表中"))
story.append(Bullet("表由 <b>langgraph-checkpoint-postgres</b> 包管理（Python 库）"))
story.append(Bullet("Go 服务 <b>不直接操作</b> checkpoint 表"))

story.append(H2("7.2 Python 写入 Checkpoint"))
story.append(P("图执行时，Python Checkpointer 直接写入 PostgreSQL："))
story.append(Code(
    "# 图执行过程中，自动触发 checkpoint 保存\n"
    "async def on_checkpoint(checkpoint):\n"
    "    checkpointer = await get_checkpointer()\n"
    "    await checkpointer.aput(config, checkpoint, metadata)\n"
    "    # 直接写入 PostgreSQL，不经过 Go 服务"
))

story.append(H2("7.3 Go 读取 Checkpoint（反向 gRPC）"))
story.append(P("当 Go 服务需要读取 checkpoint（如恢复执行）时，会<b>反向调用 Python</b>："))
story.append(Code(
    "# Python 端暴露的 gRPC 服务 (grpc/servicers/checkpointer.py)\n"
    "class CheckpointerServicerImpl:\n"
    "    async def GetTuple(self, request, context):\n"
    "        # Go 服务调用这个方法来获取 checkpoint\n"
    "        checkpointer = await get_checkpointer()\n"
    "        result = await checkpointer.aget_tuple(config)\n"
    "        return GetTupleResponse(checkpoint_tuple=result)\n"
    "    \n"
    "    async def Put(self, request, context):\n"
    "        # Go 服务调用这个方法来保存 checkpoint\n"
    "        await checkpointer.aput(config, checkpoint, metadata)"
))

story.append(H2("7.4 双向 gRPC 通信"))
story.append(Code(
    "Python \u2192 Go (正向):\n"
    "  client.threads.Get()     # 获取线程元数据\n"
    "  client.runs.Next()       # 获取下一个待执行 run\n"
    "  client.runs.Publish()    # 发布流事件\n\n"
    "Go \u2192 Python (反向):\n"
    "  CheckpointerServicer.GetTuple()  # Go 读取 checkpoint\n"
    "  CheckpointerServicer.Put()       # Go 写入 checkpoint"
))

# ═══════════════════════════════════════════════════════════════
# Section 8: Stream Event Distribution
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("8. 流事件分发机制"))
story.append(P("当图执行产生事件时，需要实时推送给订阅者（如 LangGraph Studio）。"))

story.append(H2("8.1 事件产生与发布"))
story.append(Code(
    "# Python Worker 执行图\n"
    "async for event in graph.astream_events(input, config):\n"
    "    # event = {'event': 'on_chain_start', 'name': 'agent', 'data': {...}}\n"
    "    \n"
    "    # 序列化事件\n"
    "    payload = json_dumpb(event)\n"
    "    \n"
    "    # 通过 gRPC 发布到 Go 服务\n"
    "    await Runs.Stream.publish(\n"
    "        run_id=run_id,\n"
    "        event='values',  # 事件类型\n"
    "        message=payload,\n"
    "        thread_id=thread_id,\n"
    "    )"
))

story.append(H2("8.2 Go 服务分发事件"))
story.append(P("Go 服务接收事件后，分发给所有订阅者："))
story.append(Code(
    "# Go 服务内部逻辑（推断）\n"
    "func (s *RunsServer) Publish(ctx context.Context, req *PublishRequest) {\n"
    "    // 存储到 Redis Stream（可恢复）\n"
    "    s.redis.XAdd(ctx, &redis.XAddArgs{\n"
    "        Stream: fmt.Sprintf(\"run:%s:events\", req.RunId),\n"
    "        Values: map[string]interface{}{\n"
    "            \"event\":   req.Event,\n"
    "            \"message\": req.Message,\n"
    "        },\n"
    "    })\n"
    "    \n"
    "    // 推送给 WebSocket/SSE 订阅者\n"
    "    for _, sub := range s.subscribers[req.RunId] {\n"
    "        sub.Send(req.Message)\n"
    "    }\n"
    "}"
))

story.append(H2("8.3 客户端订阅事件"))
story.append(Code(
    "# 客户端通过 SSE 订阅\n"
    "GET /threads/{thread_id}/runs/{run_id}/stream\n\n"
    "# 响应是 SSE 事件流\n"
    "event: values\n"
    "data: {\"event\": \"on_chain_start\", \"name\": \"agent\", ...}\n\n"
    "event: values\n"
    "data: {\"event\": \"on_chain_end\", \"name\": \"agent\", ...}"
))

# ═══════════════════════════════════════════════════════════════
# Section 9: Summary
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("9. 总结与对比"))

story.append(H2("9.1 核心结论"))
story.append(Callout("图在 Python 进程执行，Go 服务只负责元数据管理和事件分发。"))

story.append(H2("9.2 Python vs Go 职责划分"))
story.append(make_table(
    ["职责", "Python 进程", "Go 进程"],
    [
        ["HTTP API", "\u2705 处理请求", "\u274c 不参与"],
        ["图执行", "\u2705 执行 graph.astream()", "\u274c 不参与"],
        ["Checkpoint 读写", "\u2705 直接操作 PostgreSQL", "\u274c 通过反向 gRPC 调 Python"],
        ["Thread/Run 元数据", "\u274c 通过 gRPC 调 Go", "\u2705 直接操作 PostgreSQL"],
        ["流事件分发", "\u274c 发送到 Go", "\u2705 分发给订阅者"],
        ["任务队列", "\u274c 拉取任务", "\u2705 维护队列"],
        ["TTL 清理", "\u274c 不参与", "\u2705 后台定时清理"],
    ],
    col_widths=[40*mm, 50*mm, 50*mm]
))

story.append(H2("9.3 为什么官方用 Go？"))
story.append(Bullet("<b>性能</b>：Go 处理大量并发连接更高效"))
story.append(Bullet("<b>数据库连接池</b>：Go 的 pgx 库性能优秀"))
story.append(Bullet("<b>部署独立</b>：可以单独扩展持久化层"))
story.append(Bullet("<b>商业保护</b>：核心持久化逻辑闭源"))

story.append(H2("9.4 自研 postgres_py 的优势"))
story.append(Bullet("<b>完全开源</b>：无需依赖闭源 Go 二进制"))
story.append(Bullet("<b>简单部署</b>：单进程，无需 Docker"))
story.append(Bullet("<b>易于调试</b>：纯 Python，IDE 断点无障碍"))
story.append(Bullet("<b>学习友好</b>：理解每个细节如何工作"))

story.append(Spacer(1, 10*mm))
story.append(P("\u2014 报告结束 \u2014", ParagraphStyle("EndMark",
    fontName="MSYH", fontSize=10, textColor=C_GRAY, alignment=TA_CENTER)))

# ── Build PDF ──
doc.build(story)
print(f"PDF saved to: {output_path}")
