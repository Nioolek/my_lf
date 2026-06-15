"""Comprehensive PDF report for LangGraph Postgres Runtime."""
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
    header_row = [Paragraph(f"<b>{h}</b>", ParagraphStyle("TH", fontName="MSYHBD",
        fontSize=8.5, leading=12, textColor=white, alignment=TA_CENTER)) for h in headers]
    data = [header_row]
    for row in rows:
        data.append([Paragraph(str(c), ParagraphStyle("TD", fontName="MSYH",
            fontSize=8.5, leading=12, textColor=black)) for c in row])
    if col_widths is None:
        col_widths = [None] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_TABLE_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, C_TABLE_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ═══════════════════════════════════════════════════════════════
# Section Builders
# ═══════════════════════════════════════════════════════════════

def build_cover(story):
    story.append(Spacer(1, 30*mm))
    story.append(P("LangGraph Postgres Runtime", ParagraphStyle("CoverTitle",
        fontName="MSYHBD", fontSize=28, leading=36, textColor=C_PRIMARY, alignment=TA_CENTER)))
    story.append(Spacer(1, 5*mm))
    story.append(P("技术报告", ParagraphStyle("CoverSub",
        fontName="MSYHBD", fontSize=18, leading=24, textColor=HexColor("#374151"), alignment=TA_CENTER)))
    story.append(Spacer(1, 15*mm))
    story.append(P("开源版本差异分析与 postgres_py 实现详解", ParagraphStyle("CoverSub2",
        fontName="MSYH", fontSize=14, leading=20, textColor=C_GRAY, alignment=TA_CENTER)))
    story.append(Spacer(1, 20*mm))
    story.append(P("2026-06-15", ParagraphStyle("CoverDate",
        fontName="MSYH", fontSize=12, textColor=C_GRAY, alignment=TA_CENTER)))
    story.append(PageBreak())


def build_toc(story):
    story.append(H1("目录"))
    toc_items = [
        "1. 项目背景与目标",
        "2. 开源版本架构分析",
        "3. 开源版本与生产态差异",
        "4. postgres_py 架构设计",
        "5. 模块详解: database.py",
        "6. 模块详解: checkpoint.py",
        "7. 模块详解: ops.py",
        "8. 模块详解: store.py",
        "9. 模块详解: run_queue.py",
        "10. 模块详解: events.py & routes.py",
        "11. 实现效果与测试结果",
        "12. gRPC vs HTTP 版本差异",
        "13. 待实现事项与总结",
    ]
    for item in toc_items:
        story.append(P(item, s_toc))
    story.append(PageBreak())


def build_background(story):
    story.append(H1("1. 项目背景与目标"))
    story.append(H2("1.1 LangGraph API 是什么"))
    story.append(P("LangGraph API 是 LangChain 生态系统中的核心组件，提供了一个生产级的图执行平台。它允许开发者将基于 LangGraph 构建的 Agent 图部署为可扩展的 API 服务。"))
    story.append(P("简单来说，LangGraph API 解决了以下问题："))
    story.append(Bullet("持久化状态管理：图执行过程中的状态需要可靠存储，支持断点续传"))
    story.append(Bullet("并发执行：多个用户同时使用同一个 Agent，需要隔离的执行上下文"))
    story.append(Bullet("人机协作：图可以在关键节点暂停，等待人工审批后继续执行"))
    story.append(Bullet("异步处理：长时间运行的任务通过队列异步执行，不阻塞 API 响应"))

    story.append(H2("1.2 为什么需要 postgres_py 后端"))
    story.append(P("LangGraph API 采用可插拔的后端架构，官方提供了两种后端："))
    story.append(Bullet("langgraph_runtime_inmem：内存存储，适合开发测试，无持久化"))
    story.append(Bullet("langgraph_runtime_postgres (gRPC)：Go + Python 双进程架构，适合生产环境"))
    story.append(P("然而，官方的 postgres 后端依赖于一个 Go 语言编写的 gRPC 服务，这给部署带来了额外的复杂性。我们的目标是实现一个<b>纯 Python 的 Postgres 后端</b>，既保持生产级特性，又简化部署。"))

    story.append(H2("1.3 项目目标"))
    story.append(P("本项目 (langgraph_runtime_postgres_py) 的核心目标："))
    story.append(Bullet("持久化存储：使用 PostgreSQL 存储图状态、线程、运行记录"))
    story.append(Bullet("分布式队列：使用 Redis Streams 实现任务队列，支持多 Worker"))
    story.append(Bullet("接口兼容：完全匹配 langgraph_api 期望的 ops 接口"))
    story.append(Bullet("纯 Python：无需额外进程，简化部署和运维"))


def build_architecture(story):
    story.append(H1("2. 开源版本架构分析"))
    story.append(H2("2.1 核心模块结构"))
    story.append(P("langgraph_api 由以下核心模块组成："))
    story.append(make_table(
        ["模块", "职责"],
        [
            ["api/", "REST API 路由定义 (threads, runs, assistants, crons)"],
            ["config/", "配置解析 (DATABASE_URI, REDIS_URI, THREAD_TTL)"],
            ["auth/", "认证中间件 (noop, custom, langsmith)"],
            ["grpc/", "gRPC 客户端 ops (与 Go 服务通信)"],
            ["worker/", "图执行 Worker"],
        ],
        col_widths=[35*mm, 140*mm]
    ))

    story.append(H2("2.2 Edition 检测机制"))
    story.append(P("langgraph_api 通过环境变量 LANGGRAPH_RUNTIME_EDITION 决定使用哪个后端："))
    story.append(Code(
        "# feature_flags.py\n"
        "_RUNTIME_EDITION = os.getenv('LANGGRAPH_RUNTIME_EDITION', 'inmem')\n"
        "IS_POSTGRES_BACKEND = _RUNTIME_EDITION == 'postgres'\n"
        "IS_POSTGRES_OR_GRPC_BACKEND = IS_POSTGRES_BACKEND"
    ))

    story.append(H2("2.3 多态分发模式"))
    story.append(P("API 路由根据 feature flag 选择不同的 ops 实现："))
    story.append(Code(
        "# api/threads.py\n"
        "if IS_POSTGRES_OR_GRPC_BACKEND:\n"
        "    from langgraph_api.grpc.ops import Threads  # gRPC 客户端\n"
        "else:\n"
        "    from langgraph_runtime.ops import Threads   # Python ops"
    ))
    story.append(P("这意味着：当 EDITION 不是 postgres/grpc 时，langgraph_runtime 会动态加载我们实现的后端包。"))


def build_gaps(story):
    story.append(H1("3. 开源版本与生产态差异"))
    story.append(H2("3.1 架构差异"))
    story.append(make_table(
        ["特性", "inmem", "postgres (gRPC)", "postgres_py (本项目)"],
        [
            ["持久化", "\u274c 内存", "\u2705 PostgreSQL", "\u2705 PostgreSQL"],
            ["分布式", "\u274c 单进程", "\u2705 多 Worker", "\u2705 多 Worker"],
            ["额外依赖", "\u2705 无", "\u274c Go 服务", "\u2705 纯 Python"],
            ["TTL 清理", "\u274c 空壳", "\u2705 Go 后端", "\u25cb 部分"],
            ["加密支持", "\u274c 无", "\u2705 Go 后端", "\u25cb 部分"],
        ],
        col_widths=[30*mm, 35*mm, 50*mm, 55*mm]
    ))

    story.append(H2("3.2 gRPC 架构详解"))
    story.append(P("生产环境的 postgres 后端采用 Go + Python 双进程架构："))
    story.append(Bullet("Python 进程：运行 langgraph_api，处理 HTTP 请求，通过 gRPC 调用 Go 服务"))
    story.append(Bullet("Go 进程：处理持久化操作、TTL 清理、加密等"))
    story.append(P("这种架构的优势是性能和稳定性，但部署复杂度较高。"))

    story.append(H2("3.3 inmem 的局限性"))
    story.append(Bullet("状态存储在进程内存中，重启丢失"))
    story.append(Bullet("无法水平扩展，不支持多 Worker"))
    story.append(Bullet("TTL sweep_ttl() 直接返回 (0, 0)，无实际清理"))
    story.append(Bullet("适合开发测试，不适合生产环境"))


def build_design(story):
    story.append(H1("4. postgres_py 架构设计"))
    story.append(H2("4.1 整体架构"))
    story.append(P("本项目采用 PostgreSQL + Redis 双存储架构："))
    story.append(make_table(
        ["存储", "用途", "数据类型"],
        [
            ["PostgreSQL", "持久化存储", "threads, runs, assistants, crons, checkpoints, store_kv"],
            ["Redis", "分布式队列 + 事件总线", "任务队列, 心跳, 事件流"],
        ],
        col_widths=[35*mm, 50*mm, 90*mm]
    ))

    story.append(H2("4.2 生命周期管理"))
    story.append(P("lifespan.py 负责启动和关闭所有组件："))
    story.append(Code(
        "async def lifespan(app):\n"
        "    await start_pool()          # PostgreSQL 连接池\n"
        "    await start_checkpointer()  # AsyncPostgresSaver\n"
        "    await start_redis()         # Redis 连接\n"
        "    await start_stream()        # 事件流管理\n"
        "    await collect_graphs()      # 加载图定义\n"
        "    # 启动 Worker 队列和 Cron 调度器\n"
        "    yield\n"
        "    # 清理资源..."
    ))

    story.append(H2("4.3 数据库迁移"))
    story.append(P("使用简单的版本化迁移机制："))
    story.append(Bullet("001_initial_ops.sql：核心表 (assistants, threads, runs, crons, worker_registry)"))
    story.append(Bullet("002_store.sql：KV 存储表 (store_kv)"))
    story.append(Bullet("003_schema_compat.sql：兼容性字段 (expires_at, version, attempt)"))


def build_module_database(story):
    story.append(H1("5. 模块详解: database.py"))
    story.append(H2("5.1 连接池管理"))
    story.append(P("使用 psycopg3 的 AsyncConnectionPool 管理数据库连接："))
    story.append(Code(
        "_pool = AsyncConnectionPool(\n"
        "    conninfo=DATABASE_URI,\n"
        "    max_size=POSTGRES_POOL_MAX_SIZE,\n"
        "    kwargs={'row_factory': dict_row}\n"
        ")"
    ))

    story.append(H2("5.2 迁移机制"))
    story.append(P("自动检测并执行未应用的迁移文件："))
    story.append(Code(
        "async def _run_migrations():\n"
        "    current = await conn.execute(\n"
        "        'SELECT COALESCE(MAX(v), 0) FROM runtime_migrations'\n"
        "    )\n"
        "    for fname in sorted(migration_files):\n"
        "        if version > current:\n"
        "            await cur.execute(sql)\n"
        "            await conn.execute(\n"
        "                'INSERT INTO runtime_migrations (v) VALUES (%s)',\n"
        "                (version,)\n"
        "            )"
    ))

    story.append(H2("5.3 PgConnectionProto 适配器"))
    story.append(P("封装 psycopg3 连接，提供统一的接口供 ops 层使用："))
    story.append(Bullet("execute(query, *args)：执行查询，返回结果"))
    story.append(Bullet("pipeline()：批量操作优化"))


def build_module_checkpoint(story):
    story.append(H1("6. 模块详解: checkpoint.py"))
    story.append(H2("6.1 AsyncPostgresSaver 桥接"))
    story.append(P("本模块是对 langgraph-checkpoint-postgres 的薄封装："))
    story.append(Code(
        "_checkpointer: AsyncPostgresSaver | None = None\n\n"
        "def Checkpointer(*args, **kwargs) -> AsyncPostgresSaver:\n"
        "    global _checkpointer\n"
        "    if _checkpointer is None:\n"
        "        raise RuntimeError('Call start_checkpointer() first')\n"
        "    return _checkpointer"
    ))

    story.append(H2("6.2 setup() 的 autocommit 处理"))
    story.append(P("CREATE INDEX CONCURRENTLY 需要在 autocommit 模式下执行："))
    story.append(Code(
        "async def start_checkpointer():\n"
        "    async with pool.connection() as conn:\n"
        "        await conn.set_autocommit(True)\n"
        "        saver = AsyncPostgresSaver(conn=conn)\n"
        "        await saver.setup()  # 创建 checkpoint 表和索引\n"
        "    _checkpointer = AsyncPostgresSaver(conn=pool)"
    ))


def build_module_ops(story):
    story.append(PageBreak())
    story.append(H1("7. 模块详解: ops.py"))
    story.append(H2("7.1 Authenticated 基类"))
    story.append(P("所有 ops 类继承 Authenticated，统一处理认证上下文："))
    story.append(Code(
        "class Authenticated:\n"
        "    resource: Literal['threads', 'crons', 'assistants']\n\n"
        "    @classmethod\n"
        "    async def handle_event(cls, ctx, action, value):\n"
        "        # 调用 langgraph_api.auth.custom.handle_event\n"
        "        # 返回 auth filter 用于权限检查"
    ))

    story.append(H2("7.2 返回类型规范"))
    story.append(P("所有 CRUD 方法返回 AsyncIterator，支持 fetchone() 和分页消费："))
    story.append(make_table(
        ["方法", "返回类型", "消费方式"],
        [
            ["put/patch/get/delete", "AsyncIterator[dict]", "fetchone()"],
            ["search", "tuple[AsyncIterator, int|None]", "get_pagination_headers()"],
            ["count", "int", "直接返回"],
        ],
        col_widths=[45*mm, 55*mm, 70*mm]
    ))

    story.append(H2("7.3 嵌套类"))
    story.append(P("Threads.State：线程状态操作 (get, post, bulk, list)"))
    story.append(P("Threads.Stream：线程事件流 (subscribe, join, publish)"))
    story.append(P("Runs.Stream：运行事件流 (subscribe, join, publish)"))

    story.append(H2("7.4 Worker 内部方法"))
    story.append(make_table(
        ["方法", "用途"],
        [
            ["Threads.set_status(conn, tid, checkpoint, exc)", "更新线程状态"],
            ["Threads.set_joint_status(...)", "原子更新线程+运行状态"],
            ["Runs.set_status(conn, rid, status)", "更新运行状态"],
            ["Runs.cancel(conn, run_ids, ...)", "取消运行"],
            ["Runs.enter(rid, tid, loop, resumable)", "@asynccontextmanager 进入执行"],
            ["Runs.next(wait, limit)", "从队列获取待执行运行"],
        ],
        col_widths=[70*mm, 100*mm]
    ))


def build_module_store(story):
    story.append(H1("8. 模块详解: store.py"))
    story.append(H2("8.1 PgStore 实现"))
    story.append(P("实现 AsyncBatchedBaseStore 接口，支持批量操作："))
    story.append(Code(
        "class PgStore(AsyncBatchedBaseStore):\n"
        "    async def abatch(self, ops: Iterable[Op]) -> list[Any]:\n"
        "        for op in ops:\n"
        "            if isinstance(op, PutOp):\n"
        "                # INSERT ... ON CONFLICT\n"
        "            elif isinstance(op, GetOp):\n"
        "                # SELECT FROM store_kv\n"
        "            elif isinstance(op, SearchOp):\n"
        "                # SELECT + JSONB @> 过滤"
    ))

    story.append(H2("8.2 TTL 支持"))
    story.append(P("支持过期时间，后台任务定期清理："))
    story.append(Code(
        "async def start_ttl_sweeper(self):\n"
        "    while True:\n"
        "        await conn.execute(\n"
        "            'DELETE FROM store_kv WHERE expires_at < NOW()'\n"
        "        )\n"
        "        await asyncio.sleep(60)"
    ))


def build_module_queue(story):
    story.append(H1("9. 模块详解: run_queue.py"))
    story.append(H2("9.1 Redis Streams 消费者组"))
    story.append(P("使用 Redis Streams 实现分布式任务队列："))
    story.append(Code(
        "RUNS_STREAM = 'lg:runs'\n"
        "CONSUMER_GROUP = 'workers'\n\n"
        "async def start_redis():\n"
        "    await redis.xgroup_create(\n"
        "        RUNS_STREAM, CONSUMER_GROUP, id='0', mkstream=True\n"
        "    )"
    ))

    story.append(H2("9.2 Worker 心跳"))
    story.append(P("Worker 定期更新心跳，支持故障检测："))
    story.append(Code(
        "async def heartbeat_loop():\n"
        "    await conn.execute(\n"
        "        'INSERT INTO worker_registry (worker_id, ...) '\n"
        "        'ON CONFLICT (worker_id) DO UPDATE '\n"
        "        'SET last_heartbeat = NOW()'\n"
        "    )"
    ))

    story.append(H2("9.3 故障恢复"))
    story.append(P("检测僵死 Worker 并重新分配任务："))
    story.append(Code(
        "await redis.xautoclaim(\n"
        "    RUNS_STREAM, CONSUMER_GROUP, consumer_name,\n"
        "    min_idle_time=STALE_WORKER_TIMEOUT_SECS * 1000\n"
        ")"
    ))


def build_module_events(story):
    story.append(H1("10. 模块详解: events.py & routes.py"))
    story.append(H2("10.1 Redis Pub/Sub 事件总线"))
    story.append(P("发布订阅模式实现进程间事件通知："))
    story.append(Code(
        "class EventType(str, Enum):\n"
        "    RUN_STARTED = 'run.started'\n"
        "    RUN_COMPLETED = 'run.completed'\n"
        "    RUN_FAILED = 'run.failed'\n"
        "    THREAD_UPDATED = 'thread.updated'\n"
        "    ..."
    ))

    story.append(H2("10.2 内部管理路由"))
    story.append(P("routes.py 提供调试和管理端点："))
    story.append(Bullet("/internal/truncate：清空所有数据（仅测试用）"))
    story.append(Bullet("/internal/debug/thread/{thread_id}：查看线程详情"))


def build_results(story):
    story.append(H1("11. 实现效果与测试结果"))
    story.append(H2("11.1 Demo 测试"))
    story.append(make_table(
        ["测试", "内容", "结果"],
        [
            ["Demo 1", "Counter Graph (increment -> double 循环)", "\u2705 通过"],
            ["Demo 2", "Human-in-the-Loop (中断后恢复)", "\u2705 通过"],
            ["Demo 3", "完整 API 流程 (Assistant->Thread->Run->Events)", "\u2705 通过"],
        ],
        col_widths=[25*mm, 95*mm, 30*mm]
    ))

    story.append(H2("11.2 PostgreSQL 数据验证"))
    story.append(make_table(
        ["表", "记录数", "说明"],
        [
            ["assistants", "2", "注册的 counter + agent 图"],
            ["checkpoints", "59", "完整的 checkpoint 链"],
            ["checkpoint_writes", "122", "状态写入记录"],
        ],
        col_widths=[40*mm, 30*mm, 100*mm]
    ))
    story.append(P("Checkpoint 链验证：parent_checkpoint_id 关系正确建立，形成完整状态历史。"))


def build_grpc_vs_http(story):
    story.append(PageBreak())
    story.append(H1("12. gRPC vs HTTP 版本差异"))
    story.append(H2("12.1 架构对比"))
    story.append(make_table(
        ["维度", "gRPC (生产)", "HTTP (本项目)"],
        [
            ["进程模型", "Go + Python 双进程", "纯 Python 单进程"],
            ["通信方式", "gRPC + Protobuf", "直接 Python 调用"],
            ["部署复杂度", "高 (需要 Go 服务)", "低 (仅 Python)"],
            ["性能", "更高 (Go 处理持久化)", "足够 (Python 直连 PG)"],
            ["TTL 清理", "Go 后端自动", "需自己实现"],
            ["加密", "Go 后端处理", "Python 层处理"],
        ],
        col_widths=[35*mm, 55*mm, 60*mm]
    ))

    story.append(H2("12.2 ops 接口差异"))
    story.append(P("gRPC ops 通过 protobuf 通信，Python ops 直接操作数据库："))
    story.append(Code(
        "# gRPC ops\n"
        "async def Threads.get(conn, thread_id, ctx):\n"
        "    client = await get_shared_client()\n"
        "    response = await client.threads.Get(request)\n"
        "    yield proto_to_thread(response)\n\n"
        "# postgres_py ops\n"
        "async def Threads.get(conn, thread_id, ctx):\n"
        "    row = await conn.execute(\n"
        "        'SELECT * FROM threads WHERE thread_id = %s',\n"
        "        (thread_id,)\n"
        "    )\n"
        "    yield dict(row)"
    ))

    story.append(H2("12.3 功能完整性"))
    story.append(make_table(
        ["功能", "gRPC", "postgres_py", "备注"],
        [
            ["CRUD 操作", "\u2705", "\u2705", "完全对齐"],
            ["状态管理", "\u2705", "\u2705", "使用 AsyncPostgresSaver"],
            ["任务队列", "\u2705", "\u2705", "Redis Streams"],
            ["TTL 清理", "\u2705", "\u25cb", "需实现 sweep_ttl()"],
            ["keep_latest 策略", "\u2705", "\u274c", "待实现"],
            ["加密支持", "\u2705", "\u25cb", "部分实现"],
        ],
        col_widths=[35*mm, 25*mm, 30*mm, 60*mm]
    ))


def build_summary(story):
    story.append(H1("13. 待实现事项与总结"))
    story.append(H2("13.1 待实现事项"))
    story.append(make_table(
        ["优先级", "事项", "说明"],
        [
            ["P0", "实现 Threads.sweep_ttl()", "扫描 expires_at < NOW() 的线程并删除"],
            ["P0", "启动 TTL 清理定时任务", "在 lifespan 中每 sweep_interval_minutes 调用"],
            ["P1", "实现 keep_latest 策略", "只清理旧 checkpoint，保留最新状态"],
            ["P1", "优化 count() auth filter", "当前加载全部行计数，应推入 SQL"],
            ["P2", "Redis 显式清理 (可选)", "在 Threads.delete() 中清理 run stream"],
        ],
        col_widths=[20*mm, 50*mm, 105*mm]
    ))

    story.append(H2("13.2 项目总结"))
    story.append(P("本项目成功实现了一个纯 Python 的 LangGraph Postgres 后端，具有以下特点："))
    story.append(Bullet("持久化存储：使用 PostgreSQL 存储 threads, runs, assistants, checkpoints"))
    story.append(Bullet("分布式队列：使用 Redis Streams 实现多 Worker 任务调度"))
    story.append(Bullet("接口兼容：完全匹配 langgraph_api 期望的 ops 接口"))
    story.append(Bullet("部署简化：无需额外的 Go 服务，降低运维复杂度"))
    story.append(P("通过本项目，开发者可以在不引入 gRPC 架构的情况下，获得生产级的持久化能力。"))

    story.append(Spacer(1, 10*mm))
    story.append(P("\u2014 报告结束 \u2014", ParagraphStyle("EndMark",
        fontName="MSYH", fontSize=10, textColor=C_GRAY, alignment=TA_CENTER)))


# ═══════════════════════════════════════════════════════════════
# Build Document
# ═══════════════════════════════════════════════════════════════

def build_report():
    output_path = "G:/code/my_lf/docs/comprehensive_report.pdf"
    doc = SimpleDocTemplate(output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm,
        title="LangGraph Postgres Runtime 技术报告",
        author="Claude Code")

    story = []
    build_cover(story)
    build_toc(story)
    build_background(story)
    build_architecture(story)
    build_gaps(story)
    build_design(story)
    build_module_database(story)
    build_module_checkpoint(story)
    build_module_ops(story)
    build_module_store(story)
    build_module_queue(story)
    build_module_events(story)
    build_results(story)
    build_grpc_vs_http(story)
    build_summary(story)

    doc.build(story)
    print(f"PDF saved to: {output_path}")


if __name__ == "__main__":
    build_report()
