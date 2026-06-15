"""Generate PDF report for ops.py rewrite and Thread TTL analysis."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, ListFlowable, ListItem, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Register Chinese fonts ──
FONT_DIR = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("MSYH", os.path.join(FONT_DIR, "msyh.ttc"), subfontIndex=0))
pdfmetrics.registerFont(TTFont("MSYHBD", os.path.join(FONT_DIR, "msyhbd.ttc"), subfontIndex=0))
pdfmetrics.registerFont(TTFont("SIMHEI", os.path.join(FONT_DIR, "simhei.ttf")))

# ── Colors ──
C_PRIMARY = HexColor("#1a56db")
C_SUCCESS = HexColor("#16a34a")
C_WARNING = HexColor("#d97706")
C_DANGER = HexColor("#dc2626")
C_GRAY = HexColor("#6b7280")
C_LIGHT_BG = HexColor("#f3f4f6")
C_TABLE_HEADER = HexColor("#1e3a5f")
C_TABLE_ALT = HexColor("#f0f4ff")

# ── Styles ──
styles = getSampleStyleSheet()

s_title = ParagraphStyle("TitleCN", parent=styles["Title"],
    fontName="MSYHBD", fontSize=22, leading=28, textColor=C_PRIMARY, spaceAfter=6*mm)

s_h1 = ParagraphStyle("H1CN", parent=styles["Heading1"],
    fontName="MSYHBD", fontSize=16, leading=22, textColor=C_PRIMARY,
    spaceBefore=8*mm, spaceAfter=4*mm,
    borderWidth=0, borderPadding=0)

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
    spaceBefore=1*mm, spaceAfter=2*mm, borderWidth=0.5,
    borderColor=HexColor("#cbd5e1"), borderPadding=3)

s_bullet = ParagraphStyle("BulletCN", parent=s_body,
    leftIndent=8*mm, bulletIndent=3*mm, spaceAfter=1.5*mm)

s_small = ParagraphStyle("SmallCN", parent=s_body, fontSize=8, leading=11, textColor=C_GRAY)

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
output_path = "G:/code/my_lf/docs/ops_rewrite_and_ttl_report.pdf"
doc = SimpleDocTemplate(output_path, pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm,
    title="LangGraph Postgres Runtime - ops.py Rewrite & Thread TTL Report",
    author="Claude Code")

story = []

# ── Cover ──
story.append(Spacer(1, 30*mm))
story.append(P("LangGraph Postgres Runtime", ParagraphStyle("CoverTitle",
    fontName="MSYHBD", fontSize=28, leading=36, textColor=C_PRIMARY, alignment=TA_CENTER)))
story.append(Spacer(1, 5*mm))
story.append(P("ops.py \u91cd\u5199\u62a5\u544a & Thread TTL \u5206\u6790", ParagraphStyle("CoverSub",
    fontName="MSYHBD", fontSize=18, leading=24, textColor=HexColor("#374151"), alignment=TA_CENTER)))
story.append(Spacer(1, 15*mm))
story.append(P("2026-06-14", ParagraphStyle("CoverDate",
    fontName="MSYH", fontSize=12, textColor=C_GRAY, alignment=TA_CENTER)))
story.append(Spacer(1, 5*mm))
story.append(P("\u7248\u672c: langgraph_api 0.10.0 | langgraph_runtime_inmem | postgres_py", ParagraphStyle("CoverVer",
    fontName="MSYH", fontSize=10, textColor=C_GRAY, alignment=TA_CENTER)))

story.append(PageBreak())

# ── Table of Contents ──
story.append(H1("\u76ee\u5f55"))
toc_items = [
    "1. \u6267\u884c\u6982\u8ff0",
    "2. \u63a5\u53e3\u5339\u914d\u539f\u7406",
    "3. \u8fd4\u56de\u7c7b\u578b\u53d8\u66f4\u6c47\u603b",
    "4. \u65b9\u6cd5\u540d\u53d8\u66f4\u6c47\u603b",
    "5. Authenticated \u57fa\u7c7b\u5b9e\u73b0",
    "6. \u5d4c\u5957\u7c7b\u5b9e\u73b0",
    "7. Worker \u5185\u90e8\u65b9\u6cd5",
    "8. \u4ee3\u7801\u8d28\u91cf\u5ba1\u67e5\u4e0e\u4fee\u590d",
    "9. \u6d4b\u8bd5\u9a8c\u8bc1\u7ed3\u679c",
    "10. Thread TTL \u5206\u6790",
    "11. Redis \u6570\u636e\u6e05\u7406\u673a\u5236",
    "12. \u5f85\u5b9e\u73b0\u4e8b\u9879",
]
for item in toc_items:
    story.append(P(item, s_toc))
story.append(PageBreak())

# ═══════════════════════════════════════════════════════════════
# Section 1: Executive Summary
# ═══════════════════════════════════════════════════════════════
story.append(H1("1. \u6267\u884c\u6982\u8ff0"))
story.append(P("\u672c\u62a5\u544a\u8bb0\u5f55\u4e86 <b>langgraph_runtime_postgres_py/ops.py</b> \u7684\u5b8c\u6574\u91cd\u5199\u8fc7\u7a0b\uff0c\u76ee\u6807\u662f\u5339\u914d\u5b89\u88c5\u7684 <b>langgraph_api 0.10.0</b> \u6240\u671f\u671b\u7684 ops \u63a5\u53e3\uff08\u4e0e langgraph_runtime_inmem \u6a21\u5f0f\u4e00\u81f4\uff09\u3002"))
story.append(P("\u91cd\u5199\u524d\uff0c\u65e7\u7248 ops.py \u4f7f\u7528\u7b80\u5355\u7684\u76f4\u63a5\u8fd4\u56de dict/list \u6a21\u5f0f\uff0c\u4e0e langgraph_api \u7684\u6d88\u8d39\u65b9\u5f0f\uff08fetchone/get_pagination_headers\uff09\u4e0d\u517c\u5bb9\u3002\u91cd\u5199\u540e\uff0c\u6240\u6709\u65b9\u6cd5\u7b7e\u540d\u3001\u8fd4\u56de\u7c7b\u578b\u3001Auth \u53c2\u6570\u5747\u4e0e inmem \u7248\u672c\u5bf9\u9f50\u3002"))

story.append(H2("\u6838\u5fc3\u53d8\u66f4\u7edf\u8ba1"))
story.append(make_table(
    ["\u53d8\u66f4\u7c7b\u522b", "\u6570\u91cf", "\u8bf4\u660e"],
    [
        ["\u65b9\u6cd5\u91cd\u547d\u540d", "5", "create\u2192put, update\u2192patch, versions\u2192get_versions"],
        ["\u8fd4\u56de\u7c7b\u578b\u53d8\u66f4", "15+", "dict\u2192AsyncIterator, list\u2192tuple[AsyncIterator,int]"],
        ["\u65b0\u589e\u65b9\u6cd5", "8", "count, set_latest, cancel, enter, Stream.*"],
        ["\u65b0\u589e\u5d4c\u5957\u7c7b", "3", "Threads.State, Threads.Stream, Runs.Stream"],
        ["Auth \u96c6\u6210", "45+", "\u6bcf\u4e2a\u516c\u5f00\u65b9\u6cd5\u6dfb\u52a0 ctx \u53c2\u6570 + handle_event"],
        ["\u4ee3\u7801\u8d28\u91cf\u4fee\u590d", "6", "SQL\u6ce8\u5165\u3001N+1\u67e5\u8be2\u3001\u5f02\u5e38\u5904\u7406\u7b49"],
    ],
    col_widths=[35*mm, 20*mm, 120*mm]
))
story.append(Spacer(1, 3*mm))

# ═══════════════════════════════════════════════════════════════
# Section 2: Interface Matching
# ═══════════════════════════════════════════════════════════════
story.append(H1("2. \u63a5\u53e3\u5339\u914d\u539f\u7406"))
story.append(P("langgraph_api \u4f7f\u7528\u591a\u6001\u5206\u53d1\u6a21\u5f0f\u52a0\u8f7d ops \u7c7b\uff1a"))
story.append(Code(
    "if IS_POSTGRES_OR_GRPC_BACKEND:\n"
    "    from langgraph_api.grpc.ops import Runs, Threads, Assistants, Crons\n"
    "else:\n"
    "    from langgraph_runtime.ops import Runs, Threads, Assistants, Crons"
))
story.append(P("\u5f53 LANGGRAPH_RUNTIME_EDITION \u4e0d\u662f postgres/grpc \u65f6\uff0clanggraph_runtime \u4f1a\u52a8\u6001\u52a0\u8f7d\u6211\u4eec\u7684\u540e\u7aef\u5305\u3002\u56e0\u6b64\u6211\u4eec\u7684 ops.py \u5fc5\u987b\u5b8c\u5168\u5339\u914d inmem \u7684\u63a5\u53e3\u89c4\u8303\u3002"))

story.append(H2("\u6838\u5fc3\u6d88\u8d39\u6a21\u5f0f"))
story.append(H3("fetchone() - \u5355\u6761\u7ed3\u679c\u6d88\u8d39"))
story.append(Code(
    "async def fetchone(it, not_found_code=404):\n"
    "    try:\n"
    "        return await anext(it)  # \u53d6 AsyncIterator \u7b2c\u4e00\u4e2a yield\n"
    "    except StopAsyncIteration:\n"
    "        raise HTTPException(status_code=not_found_code)"
))
story.append(P("\u6240\u6709 put/get/patch/delete \u65b9\u6cd5\u5fc5\u987b\u8fd4\u56de AsyncIterator\uff0c\u8ba9 fetchone \u6d88\u8d39\u3002\u7a7a\u8fed\u4ee3\u5668\u89e6\u53d1 404\u3002"))

story.append(H3("get_pagination_headers() - \u5206\u9875\u7ed3\u679c\u6d88\u8d39"))
story.append(Code(
    "async def get_pagination_headers(resource, next_offset, offset):\n"
    "    resources = [r async for r in resource]  # \u6536\u96c6\u4e3a list\n"
    "    if next_offset is None:\n"
    "        headers = {'X-Pagination-Total': str(len(resources) + offset)}\n"
    "    else:\n"
    "        headers = {'X-Pagination-Next': str(next_offset), ...}\n"
    "    return resources, headers"
))
story.append(P("search() \u65b9\u6cd5\u5fc5\u987b\u8fd4\u56de tuple[AsyncIterator, int]\uff0c\u5176\u4e2d int \u662f\u4e0b\u4e00\u9875 offset \u6216 None\u3002\u5b9e\u73b0\u65b9\u5f0f\uff1a\u67e5\u8be2 LIMIT limit+1\uff0c\u82e5\u8fd4\u56de limit+1 \u884c\u5219\u6709\u66f4\u591a\u9875\uff0c\u5426\u5219 cursor=None\u3002"))

# ═══════════════════════════════════════════════════════════════
# Section 3: Return Type Changes
# ═══════════════════════════════════════════════════════════════
story.append(H1("3. \u8fd4\u56de\u7c7b\u578b\u53d8\u66f4\u6c47\u603b"))
story.append(P("\u4e0b\u8868\u5217\u51fa\u6240\u6709\u65b9\u6cd5\u7684\u65e7\u8fd4\u56de\u7c7b\u578b\u2192\u65b0\u8fd4\u56de\u7c7b\u578b\u53ca\u6d88\u8d39\u65b9\u5f0f\uff1a"))

return_type_rows = [
    ["Assistants.put", "dict", "AsyncIterator[dict]", "fetchone(not_found_code=409)"],
    ["Assistants.get", "dict | None", "AsyncIterator[dict]", "fetchone()"],
    ["Assistants.search", "list[dict]", "tuple[AsyncIterator, int|None]", "get_pagination_headers()"],
    ["Assistants.patch", "dict", "AsyncIterator[dict]", "fetchone()"],
    ["Assistants.delete", "None", "AsyncIterator[UUID]", "fetchone() (drain)"],
    ["Assistants.count", "-", "int", "\u76f4\u63a5\u8fd4\u56de"],
    ["Assistants.set_latest", "-", "AsyncIterator[dict]", "fetchone()"],
    ["Assistants.get_versions", "list[dict]", "AsyncIterator[dict]", "async for \u8fed\u4ee3"],
    ["Threads.put", "dict", "AsyncIterator[dict]", "fetchone(not_found_code=409)"],
    ["Threads.get", "dict | None", "AsyncIterator[dict]", "fetchone()"],
    ["Threads.search", "list[dict]", "tuple[AsyncIterator, int|None]", "get_pagination_headers()"],
    ["Threads.patch", "dict", "AsyncIterator[dict]", "fetchone()"],
    ["Threads.delete", "None", "AsyncIterator[UUID]", "fetchone() (drain)"],
    ["Threads.count", "-", "int", "\u76f4\u63a5\u8fd4\u56de"],
    ["Threads.State.get", "Any", "StateSnapshot", "\u76f4\u63a5\u8fd4\u56de\uff08\u975e\u8fed\u4ee3\u5668\uff09"],
    ["Threads.State.post", "dict", "ThreadUpdateResponse", "\u76f4\u63a5\u8fd4\u56de\uff08\u975e\u8fed\u4ee3\u5668\uff09"],
    ["Threads.State.list", "list[Any]", "list[StateSnapshot]", "\u76f4\u63a5\u8fd4\u56de list"],
    ["Runs.put", "dict", "AsyncIterator[dict]", "anext() + async for"],
    ["Runs.get", "dict | None", "AsyncIterator[dict]", "fetchone()"],
    ["Runs.search", "list[dict]", "AsyncIterator[dict]", "async for \u8fed\u4ee3\uff08\u65e0\u5206\u9875\uff09"],
    ["Runs.delete", "None", "AsyncIterator[UUID]", "fetchone() (drain)"],
    ["Runs.cancel", "-", "None", "\u76f4\u63a5\u8fd4\u56de"],
    ["Runs.enter", "-", "AsyncIterator[ValueEvent]", "@asynccontextmanager"],
    ["Crons.put", "dict", "AsyncIterator[dict]", "fetchone()"],
    ["Crons.search", "list[dict]", "tuple[AsyncIterator, int|None]", "get_pagination_headers()"],
    ["Crons.delete", "None", "AsyncIterator[UUID]", "fetchone() (drain)"],
    ["Crons.count", "-", "int", "\u76f4\u63a5\u8fd4\u56de"],
]
story.append(make_table(
    ["\u65b9\u6cd5", "\u65e7\u8fd4\u56de\u7c7b\u578b", "\u65b0\u8fd4\u56de\u7c7b\u578b", "\u6d88\u8d39\u65b9\u5f0f"],
    return_type_rows,
    col_widths=[42*mm, 30*mm, 48*mm, 55*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 4: Method Name Changes
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("4. \u65b9\u6cd5\u540d\u53d8\u66f4\u6c47\u603b"))
story.append(make_table(
    ["\u7c7b", "\u65e7\u65b9\u6cd5\u540d", "\u65b0\u65b9\u6cd5\u540d", "\u5907\u6ce8"],
    [
        ["Assistants", "create()", "put()", "\u589e\u52a0 assistant_id, if_exists, system \u53c2\u6570"],
        ["Assistants", "update()", "patch()", "\u589e\u52a0 ctx, config/context \u4e92\u8865\u903b\u8f91"],
        ["Assistants", "versions()", "get_versions()", "\u589e\u52a0 metadata \u8fc7\u6ee4, ctx"],
        ["Threads", "create()", "put()", "\u589e\u52a0 thread_id, if_exists, ttl \u53c2\u6570"],
        ["Threads", "update()", "patch()", "\u589e\u52a0 ttl, read_mask_paths"],
        ["Runs", "create()", "put()", "\u589e\u52a0 \u5927\u91cf\u65b0\u53c2\u6570\uff08multitask \u7b49\uff09"],
        ["Runs", "update()", "set_status()", "\u7b80\u5316\u4e3a worker \u5185\u90e8\u65b9\u6cd5\uff0c\u8fd4\u56de None"],
        ["Crons", "create()", "put()", "\u589e\u52a0 cron_id, enabled, timezone \u53c2\u6570"],
    ],
    col_widths=[28*mm, 30*mm, 32*mm, 85*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 5: Authenticated Base Class
# ═══════════════════════════════════════════════════════════════
story.append(H1("5. Authenticated \u57fa\u7c7b\u5b9e\u73b0"))
story.append(P("\u6bcf\u4e2a ops \u7c7b\u7ee7\u627f Authenticated\uff0c\u63d0\u4f9b\u7edf\u4e00\u7684\u8ba4\u8bc1\u4e0a\u4e0b\u6587\u5904\u7406\uff1a"))
story.append(Code(
    "class Authenticated:\n"
    "    resource: Literal['threads', 'crons', 'assistants']\n"
    "\n"
    "    @classmethod\n"
    "    def _context(cls, ctx, action) -> Auth.types.AuthContext | None:\n"
    "        if not ctx: return None\n"
    "        return Auth.types.AuthContext(\n"
    "            user=ctx.user, permissions=ctx.permissions,\n"
    "            resource=cls.resource, action=action)\n"
    "\n"
    "    @classmethod\n"
    "    async def handle_event(cls, ctx, action, value):\n"
    "        from langgraph_api.auth.custom import handle_event\n"
    "        from langgraph_api.utils import get_auth_ctx\n"
    "        ctx = ctx or get_auth_ctx()\n"
    "        if not ctx: return None\n"
    "        return await handle_event(cls._context(ctx, action), value)"
))
story.append(P("\u6bcf\u4e2a\u516c\u5f00\u65b9\u6cd5\u8c03\u7528 handle_event \u83b7\u53d6\u8fc7\u6ee4\u6761\u4ef6\uff0c\u7136\u540e\u7528 _check_filter_match(metadata, filters) \u68c0\u67e5\u6743\u9650\u3002"))

# ═══════════════════════════════════════════════════════════════
# Section 6: Nested Classes
# ═══════════════════════════════════════════════════════════════
story.append(H1("6. \u5d4c\u5957\u7c7b\u5b9e\u73b0"))
story.append(H2("Threads.State"))
story.append(P("\u7ebf\u7a0b\u72b6\u6001\u64cd\u4f5c\uff0c\u76f4\u63a5\u8fd4\u56de\u5bf9\u8c61\uff08\u975e AsyncIterator\uff09\uff1a"))
story.append(make_table(
    ["\u65b9\u6cd5", "\u8fd4\u56de\u7c7b\u578b", "\u8bf4\u660e"],
    [
        ["get(conn, config, subgraphs)", "StateSnapshot", "\u83b7\u53d6\u7ebf\u7a0b\u5f53\u524d\u72b6\u6001\u5feb\u7167"],
        ["post(conn, config, values, as_node)", "ThreadUpdateResponse", "\u66f4\u65b0\u7ebf\u7a0b\u72b6\u6001"],
        ["bulk(conn, config, supersteps)", "ThreadUpdateResponse", "\u6279\u91cf\u66f4\u65b0\u72b6\u6001"],
        ["list(conn, config, limit, before)", "list[StateSnapshot]", "\u83b7\u53d6\u72b6\u6001\u5386\u53f2"],
    ],
    col_widths=[55*mm, 40*mm, 80*mm]
))

story.append(H2("Threads.Stream"))
story.append(P("\u7ebf\u7a0b\u6d41\u64cd\u4f5c\uff0c\u7528\u4e8e SSE \u4e8b\u4ef6\u63a8\u9001\uff1a"))
story.append(make_table(
    ["\u65b9\u6cd5", "\u8fd4\u56de\u7c7b\u578b", "\u8bf4\u660e"],
    [
        ["join(thread_id, ...)", "AsyncIterator[tuple[bytes,bytes,bytes|None]]", "SSE EventSourceResponse"],
        ["publish(thread_id, event, message)", "None", "\u53d1\u5e03\u7ebf\u7a0b\u6d41\u4e8b\u4ef6"],
        ["subscribe(thread_id)", "ContextQueue", "\u8ba2\u9605\u7ebf\u7a0b\u6d41"],
        ["check_thread_stream_auth(thread_id)", "None", "\u6743\u9650\u68c0\u67e5"],
    ],
    col_widths=[55*mm, 55*mm, 65*mm]
))

story.append(H2("Runs.Stream"))
story.append(P("Run \u6d41\u64cd\u4f5c\uff0c\u7528\u4e8e SSE \u4e8b\u4ef6\u63a8\u9001\uff1a"))
story.append(make_table(
    ["\u65b9\u6cd5", "\u8fd4\u56de\u7c7b\u578b", "\u8bf4\u660e"],
    [
        ["subscribe(run_id, thread_id)", "ContextQueue", "\u8ba2\u9605 run \u6d41"],
        ["join(run_id, stream_channel, ...)", "AsyncIterator[tuple[bytes,bytes,bytes|None]]", "SSE \u6d41\u8f93\u51fa"],
        ["check_run_stream_auth(run_id, thread_id)", "None", "\u6743\u9650\u68c0\u67e5"],
        ["publish(run_id, event, message)", "None", "\u53d1\u5e03 run \u4e8b\u4ef6"],
    ],
    col_widths=[55*mm, 55*mm, 65*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 7: Worker Internal Methods
# ═══════════════════════════════════════════════════════════════
story.append(H1("7. Worker \u5185\u90e8\u65b9\u6cd5"))
story.append(P("\u8fd9\u4e9b\u65b9\u6cd5\u4e0d\u8d70 HTTP API\uff0c\u7531 worker \u8fdb\u7a0b\u76f4\u63a5\u8c03\u7528\uff1a"))
story.append(make_table(
    ["\u65b9\u6cd5", "\u8fd4\u56de\u7c7b\u578b", "\u8c03\u7528\u4f4d\u7f6e", "\u4f5c\u7528"],
    [
        ["Threads.set_status(conn, tid, cp, exc)", "None", "worker.py", "\u66f4\u65b0\u7ebf\u7a0b\u72b6\u6001"],
        ["Threads.set_joint_status(conn, tid, rid, ...)", "None", "worker.py", "\u539f\u5b50\u66f4\u65b0\u7ebf\u7a0b+\u8fd0\u884c\u72b6\u6001"],
        ["Runs.set_status(conn, rid, status)", "None", "worker.py", "\u66f4\u65b0 run \u72b6\u6001"],
        ["Runs.cancel(conn, run_ids, action, ...)", "None", "worker/api", "\u53d6\u6d88 run"],
        ["Runs.enter(rid, tid, loop, resumable)", "ValueEvent", "worker.py", "@asynccontextmanager \u8fdb\u5165 run \u6267\u884c\u4e0a\u4e0b\u6587"],
        ["Runs.next(wait, limit)", "AsyncIterator[tuple[Run,int]]", "worker.py", "\u4ece\u961f\u5217\u53d6 run"],
        ["Runs.sweep()", "None", "\u5b9a\u65f6\u4efb\u52a1", "\u6e05\u7406\u8d85\u65f6 run"],
    ],
    col_widths=[50*mm, 35*mm, 25*mm, 65*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 8: Code Quality Review
# ═══════════════════════════════════════════════════════════════
story.append(H1("8. \u4ee3\u7801\u8d28\u91cf\u5ba1\u67e5\u4e0e\u4fee\u590d"))
story.append(P("\u4ee3\u7801\u8d28\u91cf\u5ba1\u67e5\u53d1\u73b0 4 \u4e2a\u4e25\u91cd\u95ee\u9898\u548c 6 \u4e2a\u91cd\u8981\u95ee\u9898\uff0c\u5747\u5df2\u4fee\u590d\uff1a"))

story.append(H2("\u4e25\u91cd\u95ee\u9898\uff08\u5df2\u4fee\u590d\uff09"))
story.append(make_table(
    ["\u7f16\u53f7", "\u95ee\u9898", "\u4fee\u590d\u65b9\u6848"],
    [
        ["C1", "Runs.sweep() \u4e2d INTERVAL \u4f7f\u7528 f-string \u62fc\u63a5\uff0cSQL \u6ce8\u5165\u98ce\u9669", "\u6539\u4e3a\u53c2\u6570\u5316\u67e5\u8be2 INTERVAL '%s seconds'"],
        ["C2", "Runs.cancel() \u88ab\u4ee5 conn=None \u8c03\u7528\u4f1a\u5d29\u6e83", "\u6dfb\u52a0 AsyncExitStack \u6a21\u5f0f\u83b7\u53d6\u8fde\u63a5"],
        ["C3", "Runs.Stream.subscribe() \u521b\u5efa\u5b64\u7acb pubsub\uff0c\u961f\u5217\u6c38\u8fdc\u4e3a\u7a7a", "\u6539\u7528 StreamManager.add_queue()"],
        ["C4", "Threads.Stream.subscribe() \u540c\u4e0a", "\u6539\u7528 StreamManager \u6b63\u786e\u8fde\u63a5"],
    ],
    col_widths=[12*mm, 75*mm, 88*mm]
))

story.append(H2("\u91cd\u8981\u95ee\u9898\uff08\u5df2\u4fee\u590d\uff09"))
story.append(make_table(
    ["\u7f16\u53f7", "\u95ee\u9898", "\u4fee\u590d\u65b9\u6848"],
    [
        ["I1", "Runs.cancel() \u4e2d N+1 \u67e5\u8be2\u83b7\u53d6\u7ebf\u7a0b\u5143\u6570\u636e", "\u6279\u91cf WHERE thread_id IN (...) \u67e5\u8be2"],
        ["I2", "Runs.search() \u4e2d\u6bcf\u884c\u90fd\u67e5\u8be2\u7ebf\u7a0b\u5143\u6570\u636e", "\u5faa\u73af\u5916\u4e00\u6b21\u67e5\u8be2"],
        ["I4", "\u7f3a\u5931\u8bb0\u5f55\u9519\u8bef\u5904\u7406\u4e0d\u4e00\u81f4", "\u7edf\u4e00 patch/delete \u629b 404"],
        ["I5", "Threads.delete() \u4e2d\u88f8 except Exception:pass", "\u6dfb\u52a0 logger.warning()"],
        ["I6", "Runs.delete() \u540c\u4e0a", "\u6dfb\u52a0 logger.warning()"],
        ["I7", "count() \u65b9\u6cd5\u5728\u6709 auth filter \u65f6\u52a0\u8f7d\u5168\u90e8\u884c", "\u5f85\u4f18\u5316\uff0c\u76ee\u524d\u53ef\u63a5\u53d7"],
    ],
    col_widths=[12*mm, 75*mm, 88*mm]
))

# ═══════════════════════════════════════════════════════════════
# Section 9: Test Results
# ═══════════════════════════════════════════════════════════════
story.append(H1("9. \u6d4b\u8bd5\u9a8c\u8bc1\u7ed3\u679c"))
story.append(H2("Demo \u6d4b\u8bd5"))
story.append(make_table(
    ["Demo", "\u5185\u5bb9", "\u7ed3\u679c"],
    [
        ["Demo 1", "Counter Graph (increment \u2192 double \u5faa\u73af)", "\u2705 \u901a\u8fc7"],
        ["Demo 2", "Human-in-the-Loop (\u4e2d\u65ad\u540e\u6062\u590d)", "\u2705 \u901a\u8fc7"],
        ["Demo 3", "\u5b8c\u6574 API \u6d41\u7a0b (Assistant\u2192Thread\u2192Run\u2192Events)", "\u2705 \u901a\u8fc7"],
    ],
    col_widths=[20*mm, 90*mm, 30*mm]
))

story.append(H2("PostgreSQL \u6570\u636e\u9a8c\u8bc1"))
story.append(make_table(
    ["\u8868\u540d", "\u8bb0\u5f55\u6570", "\u8bf4\u660e"],
    [
        ["assistants", "2", "\u6ce8\u518c\u7684 counter + agent \u56fe"],
        ["assistant_versions", "2", "\u6bcf\u4e2a\u56fe\u4e00\u4e2a\u7248\u672c"],
        ["threads", "0", "Demo \u6e05\u7406\u540e\u5220\u9664"],
        ["runs", "0", "Demo \u6e05\u7406\u540e\u5220\u9664"],
        ["checkpoints", "59", "\u5b8c\u6574\u7684 checkpoint \u94fe"],
        ["checkpoint_writes", "122", "checkpoint \u5199\u5165\u64cd\u4f5c"],
    ],
    col_widths=[40*mm, 25*mm, 110*mm]
))
story.append(P("Checkpoint \u94fe\u9a8c\u8bc1\uff1aparent_checkpoint_id \u5173\u7cfb\u6b63\u786e\u5efa\u7acb\uff0c\u4ece\u6839\u8282\u70b9 (parent=None) \u5230\u53f6\u5b50\u8282\u70b9\u5f62\u6210\u5b8c\u6574\u7684\u72b6\u6001\u5386\u53f2\u94fe\u3002"))

story.append(H2("\u670d\u52a1\u5668\u542f\u52a8\u6d4b\u8bd5"))
story.append(P("\u901a\u8fc7 start_server.py \u542f\u52a8 langgraph_api \u670d\u52a1\uff0c\u9a8c\u8bc1\uff1a"))
story.append(Bullet("/ok \u7aef\u70b9\u8fd4\u56de {\"ok\": true}"))
story.append(Bullet("/assistants/search \u8fd4\u56de\u5df2\u6ce8\u518c\u7684\u56fe\u5217\u8868"))
story.append(Bullet("Graph \u6ce8\u518c\u6210\u529f\uff08counter + agent\uff09"))
story.append(Bullet("\u670d\u52a1\u5668\u65e0 AttributeError \u6216\u63a5\u53e3\u4e0d\u5339\u914d\u9519\u8bef"))

# ═══════════════════════════════════════════════════════════════
# Section 10: Thread TTL Analysis
# ═══════════════════════════════════════════════════════════════
story.append(PageBreak())
story.append(H1("10. Thread TTL \u5206\u6790"))

story.append(H2("10.1 ThreadTTLConfig \u5b9a\u4e49"))
story.append(P("ThreadTTLConfig \u662f\u7ebf\u7a0b\u751f\u547d\u5468\u671f\u7ba1\u7406\u914d\u7f6e\uff0c\u5305\u542b\u4e09\u4e2a\u5b57\u6bb5\uff1a"))
story.append(make_table(
    ["\u5b57\u6bb5", "\u7c7b\u578b", "\u8bf4\u660e"],
    [
        ["strategy", "Literal['delete', 'keep_latest']", "'delete': \u5220\u9664\u7ebf\u7a0b\u53ca\u5168\u90e8\u6570\u636e\uff1b'keep_latest': \u4fdd\u7559\u6700\u65b0\u72b6\u6001\uff0c\u6e05\u7406\u65e7 checkpoint"],
        ["default_ttl", "float | None", "\u7ebf\u7a0b\u5b58\u6d3b\u65f6\u95f4\uff08\u5206\u949f\uff09\uff0c\u8d85\u671f\u540e\u6267\u884c strategy"],
        ["sweep_interval_minutes", "int | None", "\u626b\u63cf\u95f4\u9694\uff08\u5206\u949f\uff09\uff0c\u5b9a\u65f6\u68c0\u67e5\u8fc7\u671f\u7ebf\u7a0b"],
    ],
    col_widths=[40*mm, 40*mm, 95*mm]
))

story.append(H2("10.2 TTL \u4e24\u79cd\u7b56\u7565"))
story.append(H3("strategy='delete'"))
story.append(P("\u7ebf\u7a0b\u8fc7\u671f\u65f6\uff1a\u5220\u9664 thread \u884c + \u6240\u6709 runs + \u6240\u6709 crons + <b>\u6240\u6709 checkpoint\uff08PG saver \u6570\u636e\uff09</b>\u3002\u8fd9\u662f\u5f7b\u5e95\u6e05\u7406\uff0c\u91ca\u653e\u6240\u6709\u78c1\u76d8\u7a7a\u95f4\u3002"))
story.append(H3("strategy='keep_latest'"))
story.append(P("\u7ebf\u7a0b\u8fc7\u671f\u65f6\uff1a\u53ea\u6e05\u7406\u65e7\u7684 checkpoint \u5386\u53f2\uff0c\u4fdd\u7559\u7ebf\u7a0b\u548c\u6700\u65b0\u72b6\u6001\u3002<b>\u6ce8\u610f\uff1ainmem \u540e\u7aef\u4e0d\u652f\u6301\u6b64\u7b56\u7565</b>\uff0c\u4f1a\u629b HTTPException(422)\u3002"))

story.append(H2("10.3 TTL \u6267\u884c\u673a\u5236\u5bf9\u6bd4"))
story.append(make_table(
    ["\u540e\u7aef", "TTL \u6e05\u626b", "\u673a\u5236", "\u72b6\u6001"],
    [
        ["grpc (Go)", "\u2705 Go \u540e\u7aef\u5185\u90e8\u5b9a\u65f6\u6e05\u626b", "Python \u53d1\u9001 sweep_interval \u2192 Go \u81ea\u5df1\u8dd1\u5b9a\u65f6\u4efb\u52a1", "\u5df2\u5b9e\u73b0"],
        ["inmem", "\u274c \u7a7a\u58f3", "sweep_ttl() \u76f4\u63a5 return (0, 0)", "\u672a\u5b9e\u73b0"],
        ["postgres_py", "\u274c \u672a\u5b9e\u73b0", "\u9700\u8981\u81ea\u5df1\u5b9e\u73b0", "\u5f85\u5b9e\u73b0"],
    ],
    col_widths=[25*mm, 35*mm, 75*mm, 20*mm]
))

story.append(H2("10.4 TTL \u6e05\u626b\u5220\u9664\u7684\u6570\u636e\u8303\u56f4"))
story.append(P("\u5f53\u7ebf\u7a0b\u56e0 TTL \u8fc7\u671f\u88ab\u6e05\u7406\u65f6\uff0c\u4ee5\u4e0b\u6570\u636e\u88ab\u5220\u9664\uff1a"))
story.append(make_table(
    ["\u6570\u636e\u4f4d\u7f6e", "\u662f\u5426\u5220\u9664", "\u8bf4\u660e"],
    [
        ["threads \u8868\u884c", "\u2705", "strategy='delete' \u65f6\u5220\u9664\uff1b'keep_latest' \u65f6\u4fdd\u7559"],
        ["runs \u8868\u884c", "\u2705", "\u7ea7\u8054\u5220\u9664\u8be5\u7ebf\u7a0b\u7684\u6240\u6709 run"],
        ["crons \u8868\u884c", "\u2705", "\u7ea7\u8054\u5220\u9664\u8be5\u7ebf\u7a0b\u7684\u6240\u6709 cron"],
        ["checkpoints (PG saver)", "\u2705", "\u8c03\u7528 checkpointer.adelete_thread(thread_id)"],
        ["checkpoint_writes", "\u2705", "\u968f checkpoint \u7ea7\u8054\u5220\u9664"],
        ["Redis Stream \u6570\u636e", "\u274c", "\u4f9d\u8d56\u81ea\u8eab TTL (120\u79d2) \u81ea\u7136\u8fc7\u671f"],
    ],
    col_widths=[40*mm, 20*mm, 115*mm]
))

story.append(H2("10.5 \u914d\u7f6e\u65b9\u5f0f"))
story.append(P("\u5168\u5c40 TTL \u914d\u7f6e\u901a\u8fc7\u73af\u5883\u53d8\u91cf\uff1a"))
story.append(Code("LANGGRAPH_THREAD_TTL={\"strategy\":\"delete\",\"default_ttl\":60,\"sweep_interval_minutes\":5}"))
story.append(P("\u5355\u7ebf\u7a0b TTL \u901a\u8fc7 API \u8bbe\u7f6e\uff1a"))
story.append(Code("POST /threads  {\"ttl\": {\"strategy\": \"delete\", \"ttl\": 30}}  # 30\u5206\u949f\u540e\u8fc7\u671f"))
story.append(P("\u5b9e\u9645\u5b58\u50a8\uff1a\u8ba1\u7b97\u5f97\u5230 expires_at = now + timedelta(minutes=ttl)\uff0c\u5199\u5165 threads.expires_at \u5217\u3002"))

# ═══════════════════════════════════════════════════════════════
# Section 11: Redis Data Cleanup
# ═══════════════════════════════════════════════════════════════
story.append(H1("11. Redis \u6570\u636e\u6e05\u7406\u673a\u5236"))

story.append(H2("11.1 Redis \u4e2d\u5b58\u50a8\u7684\u6570\u636e\u7c7b\u578b"))
story.append(make_table(
    ["\u6570\u636e\u7c7b\u578b", "Redis Key \u6a21\u5f0f", "TTL"],
    [
        ["Run \u4e8b\u4ef6\u6d41", "run:{run_id}:events", "RESUMABLE_STREAM_TTL_SECONDS (120\u79d2)"],
        ["Run \u6a21\u5f0f\u6d41", "run:{run_id}:modes", "\u540c\u4e0a"],
        ["\u4efb\u52a1\u961f\u5217", "langgraph:runs", "\u65e0 TTL\uff0c\u6d88\u8d39\u540e\u5220\u9664"],
        ["Worker \u5fc3\u8df3", "langgraph:workers", "\u5fc3\u8df3\u8d85\u65f6\u81ea\u52a8\u8fc7\u671f"],
    ],
    col_widths=[30*mm, 50*mm, 95*mm]
))

story.append(H2("11.2 \u7ebf\u7a0b\u5220\u9664\u65f6 Redis \u7684\u5904\u7406"))
story.append(P("<b>\u5173\u952e\u53d1\u73b0\uff1aThread \u5220\u9664\u65f6\uff0cRedis stream \u6570\u636e\u6ca1\u6709\u88ab\u663e\u5f0f\u6e05\u7406\u3002</b>"))
story.append(Bullet("\u65e0\u8bba\u662f inmem \u8fd8\u662f grpc \u540e\u7aef\uff0cThreads.delete() \u90fd\u4e0d\u5305\u542b Redis \u6e05\u7406\u4ee3\u7801"))
story.append(Bullet("Redis Stream \u6570\u636e\u4f9d\u8d56\u81ea\u8eab TTL \u673a\u5236\uff08\u9ed8\u8ba4 120 \u79d2\uff09\u81ea\u7136\u8fc7\u671f"))
story.append(Bullet("\u8fd9\u610f\u5473\u7740\u7ebf\u7a0b\u5220\u9664\u540e\uff0c\u6700\u591a 2 \u5206\u949f\u5185\u4ecd\u6709\u53ef\u80fd\u901a\u8fc7 stream \u8bfb\u5230\u8be5\u7ebf\u7a0b\u7684\u6b8b\u7559\u4e8b\u4ef6"))
story.append(Bullet("\u5bf9\u4e8e\u751f\u4ea7\u73af\u5883\uff0c\u8fd9\u662f\u53ef\u63a5\u53d7\u7684\uff0c\u56e0\u4e3a stream \u6d88\u8d39\u8005\u4f1a\u68c0\u67e5 run \u72b6\u6001\u5e76\u81ea\u884c\u7ec8\u6b62"))

story.append(H2("11.3 \u5bf9 postgres_py \u7684\u5efa\u8bae"))
story.append(P("\u5728\u6211\u4eec\u7684 postgres_py \u540e\u7aef\u4e2d\uff0cRedis \u6e05\u7406\u7b56\u7565\uff1a"))
story.append(Bullet("\u4fdd\u6301\u73b0\u72b6\uff1a\u4f9d\u8d56 Redis Stream \u81ea\u8eab TTL\uff08120\u79d2\uff09\u81ea\u7136\u8fc7\u671f\uff0c\u4e0d\u505a\u663e\u5f0f\u5220\u9664"))
story.append(Bullet("\u5982\u9700\u66f4\u5feb\u6e05\u7406\uff0c\u53ef\u5728 Threads.delete() \u4e2d\u6dfb\u52a0 Redis XTRIM/XDEL \u64cd\u4f5c"))
story.append(Bullet("\u4f46\u8003\u8651\u5230 Redis stream key \u662f\u6309 run_id \u800c\u975e thread_id \u7ec4\u7ec7\u7684\uff0c\u9700\u8981\u5148\u67e5\u8be2\u8be5\u7ebf\u7a0b\u7684\u6240\u6709 run_id \u624d\u80fd\u6e05\u7406"))

# ═══════════════════════════════════════════════════════════════
# Section 12: TODO
# ═══════════════════════════════════════════════════════════════
story.append(H1("12. \u5f85\u5b9e\u73b0\u4e8b\u9879"))
story.append(make_table(
    ["\u4f18\u5148\u7ea7", "\u4e8b\u9879", "\u8bf4\u660e"],
    [
        ["P0", "\u5b9e\u73b0 Threads.sweep_ttl()", "\u626b\u63cf expires_at < NOW() \u7684\u7ebf\u7a0b\u5e76\u5220\u9664\uff0c\u8fd4\u56de (deleted_count, checkpoint_count)"],
        ["P0", "\u5728 lifespan \u4e2d\u542f\u52a8 TTL \u6e05\u626b\u5b9a\u65f6\u4efb\u52a1", "\u6bcf sweep_interval_minutes \u5206\u949f\u8c03\u7528\u4e00\u6b21 sweep_ttl()"],
        ["P1", "\u5b9e\u73b0 keep_latest \u7b56\u7565", "\u53ea\u6e05\u7406\u65e7 checkpoint\uff0c\u4fdd\u7559\u7ebf\u7a0b\u548c\u6700\u65b0\u72b6\u6001"],
        ["P1", "\u4f18\u5316 count() \u65b9\u6cd5\u7684 auth filter", "\u5f53\u524d\u5728\u6709 auth filter \u65f6\u52a0\u8f7d\u5168\u90e8\u884c\u8ba1\u6570\uff0c\u5e94\u63a8\u5165 SQL"],
        ["P2", "\u6dfb\u52a0 Redis \u663e\u5f0f\u6e05\u7406\uff08\u53ef\u9009\uff09", "\u5728 Threads.delete() \u4e2d\u6e05\u7406\u8be5\u7ebf\u7a0b\u7684 run stream"],
        ["P2", "Runs.next() \u8f6e\u8be2\u4f18\u5316", "\u6dfb\u52a0\u6307\u6570\u9000\u907f\u7b56\u7565\uff0c\u51cf\u5c11\u7a7a\u8f6c\u65f6\u7684\u8d44\u6e90\u6d6a\u8d39"],
    ],
    col_widths=[18*mm, 55*mm, 102*mm]
))

story.append(Spacer(1, 10*mm))
story.append(P("\u2014 \u62a5\u544a\u7ed3\u675f \u2014", ParagraphStyle("EndMark",
    fontName="MSYH", fontSize=10, textColor=C_GRAY, alignment=TA_CENTER)))

# ── Build PDF ──
doc.build(story)
print(f"PDF saved to: {output_path}")
