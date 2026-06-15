"""Complete architecture analysis: LangGraph Postgres Runtime Python+Go cooperation."""
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

FONT_DIR = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("MSYH", os.path.join(FONT_DIR, "msyh.ttc"), subfontIndex=0))
pdfmetrics.registerFont(TTFont("MSYHBD", os.path.join(FONT_DIR, "msyhbd.ttc"), subfontIndex=0))

C_PRIMARY = HexColor("#1a56db")
C_SUCCESS = HexColor("#16a34a")
C_WARNING = HexColor("#d97706")
C_DANGER = HexColor("#dc2626")
C_GRAY = HexColor("#6b7280")
C_TABLE_HEADER = HexColor("#1e3a5f")
C_TABLE_ALT = HexColor("#f0f4ff")

styles = getSampleStyleSheet()

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
    fontName="Courier", fontSize=7.5, leading=10, textColor=HexColor("#1e293b"),
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

def P(text, style=s_body): return Paragraph(text, style)
def H1(text): return Paragraph(text, s_h1)
def H2(text): return Paragraph(text, s_h2)
def H3(text): return Paragraph(text, s_h3)
def Code(text): return Paragraph(text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>"), s_code)
def Bullet(text): return Paragraph(f"\u2022  {text}", s_bullet)
def Callout(text): return Paragraph(text, s_callout)

def make_table(headers, rows, col_widths=None):
    header_row = [Paragraph(f"<b>{h}</b>", ParagraphStyle("TH", fontName="MSYHBD",
        fontSize=8.5, leading=12, textColor=white, alignment=TA_CENTER)) for h in headers]
    data = [header_row]
    for row in rows:
        data.append([Paragraph(str(c), ParagraphStyle("TD", fontName="MSYH",
            fontSize=8.5, leading=12, textColor=black)) for c in row])
    if col_widths is None: col_widths = [None] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
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
    ]))
    return t

output_path = "G:/code/my_lf/docs/langgraph_postgres_runtime_architecture.pdf"
doc = SimpleDocTemplate(output_path, pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm,
    title="LangGraph Postgres Runtime 架构完整分析",
    author="Claude Code")
story = []

# ── Cover ──
story.append(Spacer(1, 30*mm))
story.append(P("LangGraph Postgres Runtime", ParagraphStyle("CT",
    fontName="MSYHBD", fontSize=28, leading=36, textColor=C_PRIMARY, alignment=TA_CENTER)))
story.append(Spacer(1, 5*mm))
story.append(P("架构完整分析报告", ParagraphStyle("CS",
    fontName="MSYHBD", fontSize=18, leading=24, textColor=HexColor("#374151"), alignment=TA_CENTER)))
story.append(Spacer(1, 15*mm))
story.append(P("Python \u2192 gRPC \u2192 Go 双进程协作全链路详解", ParagraphStyle("CS2",
    fontName="MSYH", fontSize=14, leading=20, textColor=C_GRAY, alignment=TA_CENTER)))
story.append(Spacer(1, 20*mm))
story.append(P("2026-06-15", ParagraphStyle("CD",
    fontName="MSYH", fontSize=12, textColor=C_GRAY, alignment=TA_CENTER)))
story.append(PageBreak())

# ── TOC ──
story.append(H1("目录"))
for item in [
    "1. 整体架构概览",
    "2. 进程启动与生命周期",
    "3. gRPC 通信机制详解",
    "4. Python \u2192 Go：元数据操作",
    "5. Python 端：图执行全流程",
    "6. Go \u2192 Python：反向调用",
    "7. Checkpoint 存储的三条路径",
    "8. 流事件分发全链路",
    "9. 认证与加密",
    "10. 环境变量与配置",
    "11. 与自研 postgres_py 的对比",
    "12. 总结",
]:
    story.append(P(item, s_toc))
story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════
# Section 1
# ═══════════════════════════════════════════════════════════════
story.append(H1("1. 整体架构概览"))
story.append(P("LangGraph Postgres Runtime 采用 <b>Python + Go 双进程架构</b>，两个进程通过 gRPC 通信，共享同一个 PostgreSQL 数据库。"))

story.append(H2("1.1 架构图"))
story.append(Code(
    "┌───────────────────────────────────────────────────────────────────────┐\n"
    "│                        用户 / SDK / Studio                           │\n"
    "│                              │ HTTP/SSE                              │\n"
    "│                              ▼                                       │\n"
    "│  ┌─────────────────────────────────────────────────────────────┐     │\n"
    "│  │                    Python 进程                               │     │\n"
    "│  │                                                              │     │\n"
    "│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │     │\n"
    "│  │  │ FastAPI       │  │ gRPC Client  │  │ Python gRPC Server│  │     │\n"
    "│  │  │ HTTP Server   │  │ (→Go :50051) │  │ (←Go :50071)     │  │     │\n"
    "│  │  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │     │\n"
    "│  │         │                  │                     │            │     │\n"
    "│  │  ┌──────┴───────┐         │              ┌──────┴──────────┐ │     │\n"
    "│  │  │ grpc.ops     │─────────┤              │ Checkpointer    │ │     │\n"
    "│  │  │ (Threads等)  │         │              │ Servicer        │ │     │\n"
    "│  │  └──────────────┘         │              │ Encryption      │ │     │\n"
    "│  │                           │              │ Servicer        │ │     │\n"
    "│  │  ┌──────────────┐         │              └─────────────────┘ │     │\n"
    "│  │  │ Worker       │         │                                  │     │\n"
    "│  │  │ graph.astream│         │                                  │     │\n"
    "│  │  └──────┬───────┘         │                                  │     │\n"
    "│  │         │                 │                                  │     │\n"
    "│  │  ┌──────┴───────┐         │                                  │     │\n"
    "│  │  │ Checkpointer │         │                                  │     │\n"
    "│  │  │ (直连PG)     │         │                                  │     │\n"
    "│  │  └──────────────┘         │                                  │     │\n"
    "│  └────────────────────────────┼──────────────────────────────────┘     │\n"
    "│                               │ gRPC                                 │\n"
    "│                               ▼                                      │\n"
    "│  ┌─────────────────────────────────────────────────────────────┐     │\n"
    "│  │                    Go 进程 (core-api-grpc)                   │     │\n"
    "│  │                                                              │     │\n"
    "│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │     │\n"
    "│  │  │ gRPC Server   │  │ PostgreSQL   │  │ 流事件分发        │  │     │\n"
    "│  │  │ (:50051)      │  │ CRUD         │  │ (SSE/WebSocket)  │  │     │\n"
    "│  │  └──────────────┘  └──────┬───────┘  └───────────────────┘  │     │\n"
    "│  │                          │                                    │     │\n"
    "│  └──────────────────────────┼────────────────────────────────────┘     │\n"
    "│                             ▼                                         │\n"
    "│                    ┌──────────────────┐                               │\n"
    "│                    │   PostgreSQL     │                               │\n"
    "│                    │   (共享数据库)    │                               │\n"
    "│                    └──────────────────┘                               │\n"
    "└───────────────────────────────────────────────────────────────────────┘"
))

story.append(H2("1.2 两个进程的职责"))
story.append(make_table(
    ["进程", "语言", "端口", "职责", "开源"],
    [
        ["Python", "Python", "HTTP:8000\nGRPC:50071", "API接口、图执行、Checkpoint", "\u2705 开源"],
        ["Go", "Go", "GRPC:50051", "元数据CRUD、事件分发、TTL", "\u274c 闭源"],
    ],
    col_widths=[20*mm, 18*mm, 30*mm, 60*mm, 20*mm]
))

story.append(Callout("核心原则：图执行在 Python，数据管理在 Go，两者共享 PostgreSQL。"))

# ═══════════════════════════════════════════════════════════════
# Section 2
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("2. 进程启动与生命周期"))

story.append(H2("2.1 启动顺序"))
story.append(Code(
    "1. Go 进程先启动 (core-api-grpc)\n"
    "   - 监听 :50051\n"
    "   - 连接 PostgreSQL\n"
    "   - 运行数据库迁移\n\n"
    "2. Python 进程启动\n"
    "   - 连接 Go gRPC 服务 (:50051)\n"
    "   - 健康检查 (最多等60秒)\n"
    "   - 启动 Python gRPC 服务 (:50071, 可选)\n"
    "   - 注册 Checkpointer/Encryption Servicer\n"
    "   - 加载用户图\n"
    "   - 启动 Worker 消费队列"
))

story.append(H2("2.2 Python 进程启动细节 (lifespan)"))
story.append(Code(
    "async def lifespan(app):\n"
    "    # 1. 启动 HTTP 客户端\n"
    "    await start_http_client()\n\n"
    "    # 2. 等待 Go gRPC 服务就绪\n"
    "    await wait_until_grpc_ready(timeout=60)\n\n"
    "    # 3. 启动 Python gRPC 服务 (可选)\n"
    "    if PYTHON_GRPC_SERVER_ENABLED:  # 加密或自定义checkpointer时启用\n"
    "        await start_python_grpc_server(port=50071)\n\n"
    "    # 4. 加载用户图\n"
    "    await collect_graphs_from_env()\n\n"
    "    # 5. 启动后台任务\n"
    "    async with SimpleTaskGroup(cancel=True) as tg:\n"
    "        tg.create_task(queue())           # Worker 队列消费\n"
    "        tg.create_task(cron_scheduler())  # 定时任务\n"
    "        yield  # 应用运行中\n\n"
    "    # 6. 关闭\n"
    "    await stop_python_grpc_server()\n"
    "    await stop_http_client()"
))

story.append(H2("2.3 Python gRPC 服务何时启动？"))
story.append(P("Python gRPC 服务 (:50071) <b>不是总是启动</b>，仅在以下条件满足时启动："))
story.append(Code(
    "PYTHON_GRPC_SERVER_ENABLED = bool(\n"
    "    LANGGRAPH_ENCRYPTION or       # 配置了自定义加密\n"
    "    USE_CUSTOM_CHECKPOINTER       # 配置了自定义 checkpointer\n"
    ")"))
story.append(P("默认 Postgres 后端（无自定义加密/checkpointer）时，<b>Python gRPC 服务不启动</b>，因为 Go 不需要反向调用 Python。"))

# ═══════════════════════════════════════════════════════════════
# Section 3
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("3. gRPC 通信机制详解"))

story.append(H2("3.1 双向 gRPC 通信"))
story.append(P("两个进程之间有 <b>两条 gRPC 通道</b>："))
story.append(make_table(
    ["方向", "Python 端", "Go 端", "用途"],
    [
        ["Python \u2192 Go", "gRPC Client (:50051)", "gRPC Server", "元数据CRUD、任务队列、事件发布"],
        ["Go \u2192 Python", "gRPC Server (:50071)", "gRPC Client", "Checkpoint读写、加解密"],
    ],
    col_widths=[25*mm, 40*mm, 30*mm, 55*mm]
))

story.append(H2("3.2 Python \u2192 Go 的 7 个 gRPC Stub"))
story.append(Code(
    "class GrpcClient:\n"
    "    self._assistants_stub = AssistantsStub(channel)  # 助手管理\n"
    "    self._runs_stub = RunsStub(channel)              # Run 管理\n"
    "    self._threads_stub = ThreadsStub(channel)        # 线程管理\n"
    "    self._crons_stub = CronsStub(channel)            # 定时任务\n"
    "    self._admin_stub = AdminStub(channel)            # 运维管理\n"
    "    self._cache_stub = CacheStub(channel)            # 缓存\n"
    "    self._checkpointer_stub = CheckpointerStub(channel)  # Checkpoint(仅Mongo)"))

story.append(H2("3.3 客户端连接池"))
story.append(P("Python 维护一个 gRPC 客户端池，轮询分发请求："))
story.append(Code(
    "class GrpcClientPool:\n"
    "    pool_size = 5  # 默认5个客户端实例\n"
    "    \n"
    "    async def get_client(self) -> GrpcClient:\n"
    "        idx = self._current_index % self.pool_size  # 轮询\n"
    "        self._current_index = idx + 1\n"
    "        return self.clients[idx]"))

story.append(H2("3.4 Go \u2192 Python 的 2 个 Servicer"))
story.append(P("Python gRPC 服务注册的 Servicer（条件注册）："))
story.append(make_table(
    ["Servicer", "注册条件", "提供的方法"],
    [
        ["CheckpointerServicer", "USE_CUSTOM_CHECKPOINTER", "Put, PutWrites, List, GetTuple, DeleteThread, CopyThread, Prune"],
        ["EncryptionServicer", "LANGGRAPH_ENCRYPTION", "EncryptJSON, DecryptJSON"],
    ],
    col_widths=[35*mm, 40*mm, 75*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 4
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("4. Python \u2192 Go：元数据操作"))

story.append(H2("4.1 调用模式"))
story.append(P("所有元数据操作（Thread/Run/Assistant/Cron 的 CRUD）都通过 gRPC 调用 Go 服务："))
story.append(Code(
    "# 典型调用流程\n"
    "async def Threads.get(conn, thread_id, ctx=None):\n"
    "    # 1. 构造 protobuf 请求\n"
    "    request = pb.GetThreadRequest(\n"
    "        thread_id=pb.UUID(value=str(thread_id)),\n"
    "        filters=auth_filters,\n"
    "    )\n"
    "    # 2. 获取 gRPC 客户端\n"
    "    client = await get_shared_client()\n"
    "    # 3. 调用 Go 服务\n"
    "    response = await client.threads.Get(request)\n"
    "    # 4. 转换响应\n"
    "    yield proto_to_thread(response.thread)"))

story.append(H2("4.2 各操作的 gRPC 映射"))
story.append(make_table(
    ["Python ops 方法", "gRPC 调用", "Go 执行"],
    [
        ["Assistants.put()", "client.assistants.Create()", "INSERT INTO assistants"],
        ["Assistants.get()", "client.assistants.Get()", "SELECT FROM assistants"],
        ["Assistants.search()", "client.assistants.Search()", "SELECT + 分页"],
        ["Threads.put()", "client.threads.Create()", "INSERT INTO threads"],
        ["Threads.get()", "client.threads.Get()", "SELECT FROM threads"],
        ["Threads.delete()", "client.threads.Delete()", "DELETE + 级联清理"],
        ["Runs.put()", "client.runs.Create()", "INSERT INTO runs + 入队"],
        ["Runs.next()", "client.runs.Next()", "SELECT pending + 更新状态"],
        ["Runs.Stream.publish()", "client.runs.Publish()", "Redis XADD + 分发"],
        ["Crons.put()", "client.crons.Create()", "INSERT INTO crons"],
    ],
    col_widths=[40*mm, 45*mm, 50*mm]
))

story.append(H2("4.3 Runs.put() 的完整流程"))
story.append(P("创建 Run 是最复杂的操作，涉及认证、加密、入队："))
story.append(Code(
    "async def Runs.put(conn, assistant_id, kwargs, *, thread_id, ...):\n"
    "    # 1. Thread 认证\n"
    "    auth_filters = await Runs.handle_event(ctx, 'create_run', value)\n\n"
    "    # 2. Assistant 认证 (自动检查助手归属)\n"
    "    assistant_auth_filters = await auth_handle_event(\n"
    "        AuthContext(resource='assistants', action='read'), ...\n"
    "    )\n\n"
    "    # 3. 构建加密上下文\n"
    "    enc_ctx = build_encryption_context('run')\n\n"
    "    # 4. gRPC 调用 Go\n"
    "    response = await client.runs.Create(pb.CreateRunRequest(\n"
    "        assistant_id=..., kwargs_json=...,\n"
    "        thread_filters=auth_filters,\n"
    "        assistant_filters=assistant_auth_filters,\n"
    "        encryption_context=enc_ctx,\n"
    "    ))\n\n"
    "    # 5. 返回创建的 Run\n"
    "    for run in response.runs:\n"
    "        yield proto_to_run(run)"))

# ═══════════════════════════════════════════════════════════════
# Section 5
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("5. Python 端：图执行全流程"))
story.append(Callout("图在 Python 进程的 Worker 中执行，Go 完全不参与图执行。"))

story.append(H2("5.1 Worker 获取任务"))
story.append(P("Worker 通过 <b>Runs.next()</b> 从 Go 服务获取待执行的 Run："))
story.append(Code(
    "# gRPC 实现\n"
    "async def Runs.next(wait, limit):\n"
    "    client = await get_shared_client()\n"
    "    response = await client.runs.Next(\n"
    "        pb.NextRunRequest(wait=wait, limit=limit)\n"
    "    )\n"
    "    for run_with_attempt in response.runs:\n"
    "        yield proto_to_run(run_with_attempt.run), run_with_attempt.attempt"))

story.append(H2("5.2 进入 Run 执行上下文"))
story.append(P("Runs.enter() 打开一个<b>双向 gRPC 流</b>，用于接收中断/回滚信号："))
story.append(Code(
    "@asynccontextmanager\n"
    "async def Runs.enter(run_id, thread_id, loop, resumable):\n"
    "    done = ValueEvent()  # 中断信号\n\n"
    "    # 打开双向流到 Go 服务\n"
    "    client = await get_shared_client()\n"
    "    enter_stream = client.runs.Enter(\n"
    "        pb.EnterRunRequest(run_id=..., thread_id=..., resumable=...)\n"
    "    )\n\n"
    "    # 后台监听控制信号\n"
    "    async def listen_for_signals():\n"
    "        async for event in enter_stream:\n"
    "            if event.action == 'interrupt':\n"
    "                done.set(UserInterrupt())  # 中断！\n"
    "            elif event.action == 'rollback':\n"
    "                done.set(UserRollback())  # 回滚！\n\n"
    "    listener = asyncio.create_task(listen_for_signals())\n"
    "    yield done  # 返回给 Worker\n"
    "    await Runs.mark_done(run_id, thread_id, resumable)"))

story.append(H2("5.3 图执行核心 (worker.py + stream.py)"))
story.append(Code(
    "async def worker(run, attempt, main_loop):\n"
    "    # 1. 解密 run kwargs\n"
    "    run['kwargs'] = await decrypt_response(run['kwargs'], ...)\n\n"
    "    # 2. 进入 Run 上下文 (接收中断信号)\n"
    "    async with Runs.enter(run_id, thread_id, loop, resumable) as done:\n\n"
    "        # 3. 创建图执行流\n"
    "        stream = astream_state(run, attempt, done)\n\n"
    "        # 4. 消费流 (发布事件)\n"
    "        await consume(stream, run_id, resumable, stream_modes, thread_id)\n\n"
    "    # 5. 更新状态\n"
    "    async with connect() as conn:\n"
    "        await Threads.set_joint_status(conn, thread_id, run_id, 'success', ...)"))

story.append(H2("5.4 astream_state() - 图的实际执行"))
story.append(Code(
    "async def astream_state(run, attempt, done, ...):\n"
    "    # 1. 获取图 (Python 对象)\n"
    "    graph = await get_graph(graph_id, config,\n"
    "        checkpointer=await get_checkpointer(),  # Python Checkpointer!\n"
    "    )\n\n"
    "    # 2. 执行图 (纯 Python！)\n"
    "    async for event in graph.astream(input, config, stream_mode=...):\n"
    "        # 3. 检查中断\n"
    "        event = await wait_if_not_done(anext(stream), done)\n"
    "        # 如果 done 被设置 (中断/回滚), 立即停止\n\n"
    "        # 4. 处理 checkpoint\n"
    "        if mode == 'debug' and chunk['type'] == 'checkpoint':\n"
    "            on_checkpoint(chunk)  # 保存到 run 结果\n\n"
    "        # 5. yield 事件给 consume()\n"
    "        yield mode, chunk"))

story.append(H2("5.5 consume() - 事件发布"))
story.append(Code(
    "async def consume(stream, run_id, resumable, stream_modes, thread_id):\n"
    "    async for mode, payload in stream:\n"
    "        payload_bytes = json_dumpb(payload)\n"
    "        # 通过 gRPC 发布到 Go 服务\n"
    "        await Runs.Stream.publish(\n"
    "            run_id, mode, payload_bytes,\n"
    "            thread_id=thread_id, resumable=is_resumable,\n"
    "        )"))

story.append(H2("5.6 完整时序图"))
story.append(Code(
    "Worker          Runs.next()       Go:Next()        Go:SQL          PG\n"
    "  │                │                 │                │              │\n"
    "  │  获取任务      │                 │                │              │\n"
    "  │───────────────►│  gRPC Next      │                │              │\n"
    "  │                │────────────────►│  SELECT pending│              │\n"
    "  │                │                 │───────────────►│              │\n"
    "  │                │                 │◄───────────────│              │\n"
    "  │  (run,attempt) │◄────────────────│                │              │\n"
    "  │◄───────────────│                 │                │              │\n"
    "  │                │                 │                │              │\n"
    "  │  Runs.enter()  │                 │                │              │\n"
    "  │─────────────────────────────────►│  标记running   │              │\n"
    "  │                │                 │───────────────►│              │\n"
    "  │  done=ValueEvent                 │                │              │\n"
    "  │                │                 │                │              │\n"
    "  │  graph.astream() [Python执行图]  │                │              │\n"
    "  │  ──────────────────────────────────────────────────────────────►│\n"
    "  │  checkpointer.aput() [Python直写PG]              │              │\n"
    "  │  ──────────────────────────────────────────────────────────────►│\n"
    "  │                │                 │                │              │\n"
    "  │  Runs.Stream.publish(event)     │                │              │\n"
    "  │─────────────────────────────────►│  分发给订阅者  │              │\n"
    "  │                │                 │                │              │\n"
    "  │  set_joint_status('success')    │                │              │\n"
    "  │─────────────────────────────────►│  UPDATE status │              │\n"
    "  │                │                 │───────────────►│              │\n"
    "  │  done          │                 │                │              │"
))

# ═══════════════════════════════════════════════════════════════
# Section 6
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("6. Go \u2192 Python：反向调用"))
story.append(P("Go 服务在某些场景下需要<b>反向调用 Python</b>，通过 Python gRPC 服务 (:50071) 实现。"))

story.append(H2("6.1 何时发生反向调用？"))
story.append(make_table(
    ["场景", "Go 调用 Python", "条件"],
    [
        ["读取 Checkpoint", "CheckpointerServicer.GetTuple()", "使用自定义 Checkpointer (如 Redis)"],
        ["写入 Checkpoint", "CheckpointerServicer.Put()", "同上"],
        ["删除线程 Checkpoint", "CheckpointerServicer.DeleteThread()", "同上"],
        ["加密数据", "EncryptionServicer.EncryptJSON()", "配置了自定义加密"],
        ["解密数据", "EncryptionServicer.DecryptJSON()", "同上"],
    ],
    col_widths=[35*mm, 55*mm, 60*mm]
))

story.append(H2("6.2 默认 Postgres 后端：无需反向调用"))
story.append(Callout("默认 Postgres 后端时，Go 和 Python 各自直连 PostgreSQL，Go 不需要反向调用 Python！"))
story.append(P("原因："))
story.append(Bullet("Python Worker 直接用 <b>AsyncPostgresSaver</b> 读写 checkpoint"))
story.append(Bullet("Go 服务直接用 <b>pgx</b> 读写元数据表"))
story.append(Bullet("两者共享同一个 PostgreSQL 数据库，通过数据库做数据交接"))
story.append(Bullet("Python gRPC 服务 (:50071) <b>不启动</b>"))

story.append(H2("6.3 自定义 Checkpointer 时：Go 需要反向调用"))
story.append(Code(
    "# Go 需要读取 checkpoint 时\n"
    "Go 进程\n"
    "  │\n"
    "  │  gRPC GetTuple()\n"
    "  │──────────────────────────────────────►\n"
    "  │                                      Python 进程 (:50071)\n"
    "  │                                        │\n"
    "  │                                        │ checkpointer.aget_tuple()\n"
    "  │                                        │ (如: Redis/Mongo/S3)\n"
    "  │                                        │\n"
    "  │  CheckpointTuple                      │\n"
    "  │◄──────────────────────────────────────│\n"
    "  │"))

# ═══════════════════════════════════════════════════════════════
# Section 7
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("7. Checkpoint 存储的三条路径"))
story.append(P("Checkpoint 的存储方式取决于配置，有三种路径："))

story.append(H2("7.1 路径 A：默认 Postgres（最常见）"))
story.append(Code(
    "配置: LANGGRAPH_RUNTIME_EDITION=postgres (无自定义checkpointer)\n\n"
    "流程:\n"
    "  Python Worker\n"
    "    │\n"
    "    │ checkpointer.aput() / aget_tuple()\n"
    "    │ (AsyncPostgresSaver 直连 PG)\n"
    "    ▼\n"
    "  PostgreSQL\n"
    "    ├── checkpoints 表\n"
    "    ├── checkpoint_blobs 表\n"
    "    └── checkpoint_writes 表\n\n"
    "Go 服务: 不参与 checkpoint 操作\n"
    "Python gRPC 服务: 不启动"))

story.append(H2("7.2 路径 B：自定义 Checkpointer（如 Redis）"))
story.append(Code(
    "配置: LANGGRAPH_CHECKPOINTER={\"backend\":\"custom\",\"path\":\"my_checkpointer\"}\n\n"
    "流程:\n"
    "  Python Worker\n"
    "    │\n"
    "    │ checkpointer.aput() (自定义实现)\n"
    "    ▼\n"
    "  Redis / S3 / 其他存储\n\n"
    "  Go 服务需要 checkpoint 时:\n"
    "    Go ──gRPC──► Python (:50071) ──► checkpointer.aget_tuple()\n\n"
    "Python gRPC 服务: 启动 (注册 CheckpointerServicer)"))

story.append(H2("7.3 路径 C：Mongo 后端"))
story.append(Code(
    "配置: LANGGRAPH_CHECKPOINTER={\"backend\":\"mongo\"}\n\n"
    "流程:\n"
    "  Python Worker\n"
    "    │\n"
    "    │ GrpcCheckpointer (gRPC 客户端)\n"
    "    ▼\n"
    "  Go 服务 (:50051)\n"
    "    │\n"
    "    ▼\n"
    "  MongoDB\n\n"
    "注意: 这是唯一 Python 通过 gRPC 调 Go 做 checkpoint 的路径"))

story.append(H2("7.4 三条路径对比"))
story.append(make_table(
    ["路径", "Checkpoint 存储", "Python 写入", "Go 读取", "Python gRPC Server"],
    [
        ["A: 默认PG", "PostgreSQL", "直连 psycopg3", "直连 pgx", "不启动"],
        ["B: 自定义", "Redis/S3/...", "直连自定义实现", "gRPC→Python", "启动"],
        ["C: Mongo", "MongoDB", "gRPC→Go→Mongo", "直连 Mongo", "不启动(注)"],
    ],
    col_widths=[22*mm, 30*mm, 35*mm, 35*mm, 30*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 8
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("8. 流事件分发全链路"))
story.append(P("图执行产生的事件需要实时推送给客户端（SDK / LangGraph Studio）。"))

story.append(H2("8.1 事件产生到客户端的完整路径"))
story.append(Code(
    "1. 图执行产生事件 (Python)\n"
    "   graph.astream() → yield (mode, payload)\n\n"
    "2. consume() 序列化并发布 (Python)\n"
    "   payload_bytes = json_dumpb(payload)\n"
    "   await Runs.Stream.publish(run_id, mode, payload_bytes, ...)\n\n"
    "3. gRPC 发送到 Go 服务 (Python → Go)\n"
    "   client = await get_shared_client()\n"
    "   await client.runs.Publish(PublishStreamEventRequest(...))\n\n"
    "4. Go 服务分发事件 (Go)\n"
    "   - 存储到 Redis Stream (可恢复, TTL 120秒)\n"
    "   - 推送给 SSE/WebSocket 订阅者\n\n"
    "5. 客户端接收 (SDK / Studio)\n"
    "   GET /threads/{id}/runs/{id}/stream  (SSE)"))

story.append(H2("8.2 事件类型"))
story.append(make_table(
    ["事件类型", "说明", "产生时机"],
    [
        ["values", "图的完整状态", "每个 superstep 后"],
        ["updates", "增量更新", "每个节点执行后"],
        ["messages", "消息流 (流式输出)", "LLM 生成 token 时"],
        ["debug", "调试信息 (含 checkpoint)", "每步执行后"],
        ["interrupt", "中断事件", "遇到 interrupt() 时"],
        ["error", "错误事件", "执行异常时"],
        ["metadata", "运行元数据", "Run 开始时"],
    ],
    col_widths=[25*mm, 55*mm, 50*mm]
))

story.append(H2("8.3 中断处理机制"))
story.append(P("当用户请求中断 Run 时："))
story.append(Code(
    "1. 用户调用 POST /runs/cancel (action='interrupt')\n\n"
    "2. Python API → gRPC → Go 服务\n"
    "   client.runs.Cancel(CancelRunRequest(action=INTERRUPT))\n\n"
    "3. Go 服务通过 Enter 流发送中断信号\n"
    "   (Go 已持有 Runs.enter() 的双向流)\n\n"
    "4. Python Worker 收到信号\n"
    "   listen_for_signals() → done.set(UserInterrupt())\n\n"
    "5. 图执行停止\n"
    "   wait_if_not_done() 检测到 done 被设置\n"
    "   → 抛出 UserInterrupt 异常\n"
    "   → 图在当前 checkpoint 处暂停"))

# ═══════════════════════════════════════════════════════════════
# Section 9
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("9. 认证与加密"))

story.append(H2("9.1 认证流程"))
story.append(P("每个 ops 方法在执行前都会调用 handle_event() 进行认证："))
story.append(Code(
    "# Python 端\n"
    "auth_filters = await Threads.handle_event(ctx, 'read', value)\n"
    "# 返回过滤条件，如 {\"owner\": \"user123\"}\n\n"
    "# 转换为 protobuf 格式\n"
    "proto_filters = _filters_to_proto(auth_filters)\n\n"
    "# 发送给 Go 服务\n"
    "response = await client.threads.Get(\n"
    "    GetThreadRequest(thread_id=..., filters=proto_filters)\n"
    ")\n"
    "# Go 服务在 SQL 查询中应用过滤条件"))

story.append(H2("9.2 加密机制"))
story.append(P("加密有两种模式："))
story.append(make_table(
    ["模式", "配置", "处理位置", "Python gRPC Server"],
    [
        ["AES 加密", "LANGGRAPH_AES_KEY", "Python 端 (中间件)", "不启动"],
        ["自定义加密", "LANGGRAPH_ENCRYPTION", "Go→Python (gRPC)", "启动 EncryptionServicer"],
    ],
    col_widths=[30*mm, 35*mm, 40*mm, 45*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 10
# ═══════════════════════════════════════════════════════════════
story.append(H1("10. 环境变量与配置"))
story.append(make_table(
    ["环境变量", "默认值", "说明"],
    [
        ["LANGGRAPH_RUNTIME_EDITION", "inmem", "运行时版本: inmem/postgres"],
        ["LSD_GRPC_SERVER_ADDRESS", "localhost:50051", "Go gRPC 服务地址"],
        ["GRPC_CLIENT_POOL_SIZE", "5", "gRPC 客户端池大小"],
        ["PYTHON_GRPC_SERVER_PORT", "50071", "Python gRPC 服务端口"],
        ["PYTHON_GRPC_BIND_HOST", "127.0.0.1", "Python gRPC 绑定地址"],
        ["DATABASE_URI", "-", "PostgreSQL 连接串"],
        ["N_JOBS_PER_WORKER", "10", "Worker 并发数"],
        ["LANGGRAPH_CHECKPOINTER", "-", "自定义 Checkpointer 配置"],
        ["LANGGRAPH_ENCRYPTION", "-", "自定义加密配置"],
        ["LANGGRAPH_AES_KEY", "-", "AES 加密密钥"],
    ],
    col_widths=[50*mm, 30*mm, 70*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 11
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("11. 与自研 postgres_py 的对比"))

story.append(H2("11.1 架构对比"))
story.append(make_table(
    ["维度", "官方 Postgres Runtime", "自研 postgres_py"],
    [
        ["进程数", "2 (Python + Go)", "1 (Python)"],
        ["通信方式", "gRPC 双向", "无 (函数调用)"],
        ["元数据存储", "Go → PostgreSQL", "Python → PostgreSQL"],
        ["Checkpoint", "Python → PostgreSQL (直连)", "Python → PostgreSQL (直连)"],
        ["事件分发", "Python → gRPC → Go → SSE", "Python → Redis Pub/Sub"],
        ["任务队列", "Go 内部队列", "Redis Streams"],
        ["TTL 清理", "Go 后台任务", "待实现"],
        ["部署", "Docker (必须)", "pip install (可选 Docker)"],
        ["调试", "跨语言，复杂", "纯 Python，简单"],
    ],
    col_widths=[25*mm, 55*mm, 55*mm]
))

story.append(H2("11.2 数据流对比"))
story.append(Code(
    "# 官方: 创建 Thread\n"
    "Python API → gRPC → Go → SQL → PostgreSQL\n\n"
    "# 自研: 创建 Thread\n"
    "Python API → ops.Threads.put() → SQL → PostgreSQL\n\n"
    "# 官方: 执行图\n"
    "Worker → graph.astream() → Checkpointer → PostgreSQL (直连)\n"
    "       → Runs.Stream.publish() → gRPC → Go → SSE\n\n"
    "# 自研: 执行图\n"
    "Worker → graph.astream() → Checkpointer → PostgreSQL (直连)\n"
    "       → Runs.Stream.publish() → Redis Pub/Sub → SSE"))

# ═══════════════════════════════════════════════════════════════
# Section 12
# ═══════════════════════════════════════════════════════════════
story.append(H1("12. 总结"))

story.append(H2("12.1 核心架构原则"))
story.append(Bullet("<b>图执行在 Python</b>：用户代码、LangChain、LLM 调用都在 Python"))
story.append(Bullet("<b>数据管理在 Go</b>：元数据 CRUD、任务队列、事件分发由 Go 处理"))
story.append(Bullet("<b>共享 PostgreSQL</b>：两个进程直连同一个数据库，通过数据做交接"))
story.append(Bullet("<b>gRPC 是胶水</b>：Python 通过 gRPC 调 Go 做元数据操作，Go 偶尔反向调 Python"))
story.append(Bullet("<b>默认无需反向调用</b>：标准 Postgres 后端时，Go 不需要调 Python"))

story.append(H2("12.2 为什么要这样设计？"))
story.append(Bullet("<b>性能</b>：Go 处理大量并发连接和数据库操作更高效"))
story.append(Bullet("<b>隔离</b>：图执行崩溃不影响数据管理服务"))
story.append(Bullet("<b>可扩展</b>：可以独立扩展 Go 服务实例数"))
story.append(Bullet("<b>商业保护</b>：核心持久化逻辑闭源，Python 层开源"))

story.append(Spacer(1, 10*mm))
story.append(P("\u2014 报告结束 \u2014", ParagraphStyle("EndMark",
    fontName="MSYH", fontSize=10, textColor=C_GRAY, alignment=TA_CENTER)))

doc.build(story)
print(f"PDF saved to: {output_path}")
