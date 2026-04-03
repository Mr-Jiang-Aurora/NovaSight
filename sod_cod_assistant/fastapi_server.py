"""
FastAPI 服务：提供 REST API 接口给前端调用
与现有的 Agent 系统完全兼容，只是新增了 HTTP 接口层
启动方式：cd sod_cod_assistant && python fastapi_server.py
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# 确保 sod_cod_assistant 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent))

app = FastAPI(
    title="SOD/COD Research Assistant API",
    description="多 Agent 科研辅助系统后端接口",
    version="1.0.0",
)

# 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 缓存目录（相对于 sod_cod_assistant）
CACHE_BASE = Path(__file__).parent / "cache"


# ── 请求/响应模型 ──────────────────────────────────────────────────────

class Agent1Request(BaseModel):
    domain: str = "COD"
    start_year: int = 2024
    end_year: int = 2025
    tiers: list[str] = ["CCF-A", "SCI Q1"]
    use_cache: bool = True


class Agent2Request(BaseModel):
    domain: str = "COD"
    user_method_desc: str = ""


class Agent3GithubRequest(BaseModel):
    domain: str = "COD"
    github_url: str
    structure_hint: str = ""
    agent2_summary: str = ""


class Agent4Params(BaseModel):
    mode: str = "arch"
    user_method: str = ""
    user_hint: str = ""


class MasterRequest(BaseModel):
    domain: str = "COD"
    github_url: Optional[str] = None
    user_method_desc: str = ""
    run_agent3: bool = False
    run_agent4: bool = False


# ── 路由 ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "SOD/COD Research Assistant API", "status": "running"}


@app.get("/health/claude")
async def check_claude():
    """检测 Claude API 是否可达（仅检查 key 配置，不实际调用，避免阻塞事件循环）"""
    try:
        from config.settings import settings
        if not settings.ANTHROPIC_API_KEY:
            return {"ok": False, "reason": "ANTHROPIC_API_KEY 未配置"}
        # 快速检查：只验证 key 格式，不实际发起 Claude 请求（避免堵塞事件循环）
        key = settings.ANTHROPIC_API_KEY
        if not key.startswith("sk-"):
            return {"ok": False, "reason": "ANTHROPIC_API_KEY 格式不正确（应以 sk- 开头）"}
        return {
            "ok": True,
            "model": settings.ANTHROPIC_MODEL,
            "base_url": settings.ANTHROPIC_BASE_URL or "官方",
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


@app.get("/health/claude/ping")
async def ping_claude():
    """真正调用 Claude API 测试连通性（慢，仅在用户主动点击时调用）"""
    def _ping():
        from config.settings import settings
        import anthropic, httpx
        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_BASE_URL or None,
            timeout=httpx.Timeout(60.0, connect=30.0),
        )
        client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        return settings.ANTHROPIC_MODEL, settings.ANTHROPIC_BASE_URL or "官方"

    try:
        model, base_url = await asyncio.to_thread(_ping)
        return {"ok": True, "model": model, "base_url": base_url}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


@app.post("/agent1/run")
async def run_agent1(req: Agent1Request):
    """运行 Agent1 SOTA 搜索"""
    try:
        # 正确类名为 Agent1SOTAAgent，__init__ 无参数
        from agents.agent1_sota.agent1_main import Agent1SOTAAgent

        agent = Agent1SOTAAgent()
        # run() 返回 List[PaperRecord]，无 use_cache 参数，使用 force_full 取反
        papers = await agent.run(
            domain=req.domain,
            force_full=not req.use_cache,
        )
        return {
            "status": "success",
            "total_papers": len(papers),
            "scored_papers": len([p for p in papers if p.scores]),
            "domain": req.domain,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent2/run")
async def run_agent2(req: Agent2Request):
    """运行 Agent2 指标诊断"""
    try:
        from config.settings import settings
        from agents.agent1_sota.cache.cache_manager import CacheManager
        from agents.agent2_gap.agent2_main import Agent2
        from shared.models import SOTALeaderboard

        cm = CacheManager(settings.CACHE_DIR)
        # load_cache 可能返回 list 或 dict，统一处理
        raw = cm.load_cache(req.domain)
        if not raw:
            raise HTTPException(status_code=404, detail="未找到 Agent1 缓存，请先运行 Agent1")
        papers = list(raw) if not isinstance(raw, list) else raw

        leaderboard = SOTALeaderboard(domain=req.domain, papers=papers, total_papers=len(papers))
        agent = Agent2(settings)
        report = await agent.run(
            leaderboard=leaderboard,
            domain=req.domain,
            user_method_desc=req.user_method_desc,
            generate_narrative=True,   # 确保调用 Claude API 生成叙事报告
        )
        return {
            "status": "success",
            "domain": req.domain,
            "scored_methods": getattr(report, "scored_methods", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent3/run/github")
async def run_agent3_github(req: Agent3GithubRequest):
    """运行 Agent3 代码分析（GitHub 模式）"""
    try:
        from config.settings import settings
        from agents.agent3_code.agent3_main import Agent3

        agent = Agent3(settings)
        report = await agent.run(
            github_url=(req.github_url or "").strip().replace(" ", ""),
            structure_hint=req.structure_hint,
            agent2_summary=req.agent2_summary,
            domain=req.domain,
        )
        status = "success" if (report.analysis and report.analysis.status == "success") else "partial"
        return {
            "status": status,
            "arch_summary": report.analysis.arch_summary if report.analysis else "",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent3/run/upload")
async def run_agent3_upload(
    files: list[UploadFile] = File(...),
    domain: str = Form("COD"),
    structure_hint: str = Form(""),
    agent2_summary: str = Form(""),
):
    """运行 Agent3 代码分析（文件上传模式）"""
    try:
        from config.settings import settings
        from agents.agent3_code.agent3_main import Agent3

        uploaded = {}
        for f in files:
            content = await f.read()
            uploaded[f.filename] = content.decode("utf-8", errors="ignore")

        agent = Agent3(settings)
        await agent.run(
            uploaded_files=uploaded,
            structure_hint=structure_hint,
            agent2_summary=agent2_summary,
            domain=domain,
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent4/run")
async def run_agent4(
    image: UploadFile = File(...),
    params: str = Form(...),
):
    """运行 Agent4 图像分析"""
    try:
        from config.settings import settings
        from agents.agent4_vision.agent4_main import Agent4

        params_dict = json.loads(params)
        image_bytes = await image.read()

        agent = Agent4(settings)
        if params_dict.get("mode") == "arch":
            report = await agent.run(
                arch_image_bytes=image_bytes,
                arch_user_hint=params_dict.get("user_hint", ""),
            )

            # ── 尝试生成架构-代码双向验证（若 Agent3 数据已存在）──────────
            await asyncio.to_thread(_try_generate_validation, report, settings)
        else:
            report = await agent.run(
                visual_image_bytes=image_bytes,
                visual_user_method=params_dict.get("user_method", ""),
                visual_user_hint=params_dict.get("user_hint", ""),
            )

        return {
            "status": "success",
            "structure_hint": getattr(report, "structure_hint_for_agent3", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _try_generate_validation(report, settings) -> None:
    """
    尝试从最新的 Agent3 缓存生成架构-代码双向验证报告。
    在后台线程中运行，失败不影响主流程。
    """
    import logging
    logger_val = logging.getLogger(__name__)
    try:
        arch_hint = getattr(report, "arch_hint", None)
        if not arch_hint or not arch_hint.key_modules:
            logger_val.info("[Agent4] 跳过双向验证：arch_hint 为空或无 key_modules")
            return

        # 查找最新的 Agent3 JSON 报告（搜索整个 cache/agent3 目录树）
        from config.settings import get_agent_output_dir
        from pathlib import Path
        import json

        # get_agent_output_dir 返回今日日期子目录，需向上到父目录全局搜索
        agent3_today = Path(get_agent_output_dir(3))
        agent3_root  = agent3_today.parent   # cache/agent3
        if not agent3_root.exists():
            agent3_root = agent3_today       # fallback

        json_files = sorted(
            agent3_root.rglob("agent3_report_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not json_files:
            logger_val.info("[Agent4] 跳过双向验证：未找到 Agent3 报告缓存")
            return

        latest_json = json_files[0]
        with open(latest_json, encoding="utf-8") as f:
            a3_data = json.load(f)

        analysis_data = a3_data.get("analysis", {})
        if not analysis_data or not analysis_data.get("components"):
            logger_val.info("[Agent4] 跳过双向验证：Agent3 数据无组件信息")
            return

        # 构造 UserCodeAnalysis 对象
        from shared.models import UserCodeAnalysis, ArchComponent, LossConfig
        code_analysis = UserCodeAnalysis()
        code_analysis.arch_summary    = analysis_data.get("arch_summary", "")
        code_analysis.framework       = analysis_data.get("framework")
        code_analysis.key_innovations = analysis_data.get("key_innovations", [])
        for c in analysis_data.get("components", []):
            code_analysis.components.append(ArchComponent(
                component_type = c.get("component_type", "module"),
                name           = c.get("name", ""),
                source_file    = c.get("source_file", ""),
                is_pretrained  = c.get("is_pretrained", False),
                pretrained_on  = c.get("pretrained_on"),
            ))

        # 运行验证
        from agents.master.arch_code_validator import ArchCodeValidator
        from agents.agent4_vision.vision_report_writer import VisionReportWriter
        from datetime import datetime

        validator  = ArchCodeValidator()
        val_report = validator.validate(arch_hint, code_analysis)

        out_dir  = Path(get_agent_output_dir(4))
        out_dir.mkdir(parents=True, exist_ok=True)
        val_ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        val_path = out_dir / f"arch_code_validation_{val_ts}.md"
        VisionReportWriter()._write_validation_md(val_report, val_path)

        logger_val.info(
            f"[Agent4] 双向验证完成：一致性={val_report.consistency_score}%，"
            f"报告={val_path.name}"
        )
    except Exception as e:
        logging.getLogger(__name__).warning(f"[Agent4] 双向验证生成失败（不影响主流程）：{e}")


@app.post("/master/run")
async def run_master(req: MasterRequest):
    """运行主控 Agent"""
    try:
        from config.settings import settings
        from agents.master.master_agent import MasterAgent

        master = MasterAgent(settings)
        report = await master.run(
            domain=req.domain,
            github_url=req.github_url,
            user_method_desc=req.user_method_desc,
        )
        return {
            "status": "success",
            "agents_run": getattr(report, "agents_run", []),
            "total_time_s": getattr(report, "total_time_s", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _classify_agent4_report(filename: str) -> str:
    """根据文件名推断 Agent4 报告类型"""
    name = filename.lower()
    if "figure_trace" in name:
        return "figure_trace"
    elif "innovation_evaluation" in name:
        return "innovation"
    elif "arch_code_validation" in name:
        return "arch_validation"
    elif "arch_analysis" in name or "arch_hint" in name:
        return "arch_analysis"
    else:
        return "other"


@app.get("/reports/{agent_id}/list")
async def list_reports(agent_id: str):
    """列出某个 Agent 的所有历史报告"""
    agent_dir_map = {
        "agent1": CACHE_BASE / "agent1",
        "agent2": CACHE_BASE / "agent2",
        "agent3": CACHE_BASE / "agent3",
        "agent4": CACHE_BASE / "agent4",
        "master": CACHE_BASE / "master",
    }
    cache_dir = agent_dir_map.get(agent_id)
    if not cache_dir or not cache_dir.exists():
        return {"files": []}

    md_files = []
    for f in sorted(cache_dir.rglob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        stat = f.stat()
        entry = {
            "name": f.name,
            "path": str(f),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "agentId": agent_id,
        }
        # Agent4 额外附加报告类型分类
        if agent_id == "agent4":
            entry["report_type"] = _classify_agent4_report(f.name)
        md_files.append(entry)

    return {"files": md_files}


@app.get("/reports/{agent_id}/content")
async def get_report_content(agent_id: str, file: str):
    """获取报告文件的 Markdown 内容"""
    file_path = Path(file)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file}")
    try:
        content = file_path.read_text(encoding="utf-8")
        return PlainTextResponse(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pipeline/status")
async def get_pipeline_status():
    """获取当前流程状态"""
    master_dir = CACHE_BASE / "master"
    if not master_dir.exists():
        return {"status": "idle", "agents_done": []}

    ctx_files = sorted(master_dir.rglob("master_context_*.json"), reverse=True)
    if not ctx_files:
        return {"status": "idle", "agents_done": []}

    try:
        ctx = json.loads(ctx_files[0].read_text(encoding="utf-8"))
        agents_done = []
        for a in ["agent1", "agent2", "agent3", "agent4"]:
            if ctx.get(f"{a}_done"):
                agents_done.append(a)

        return {
            "status": "complete",
            "agents_done": agents_done,
            "session_id": ctx.get("session_id", ""),
        }
    except Exception:
        return {"status": "idle", "agents_done": []}


# ── AI 提供商管理接口 ──────────────────────────────────────────────────

class ProviderSwitchRequest(BaseModel):
    provider: str   # "claude" | "openai"


@app.get("/ai/provider")
async def get_provider():
    """获取当前激活的 AI 提供商"""
    from config.settings import settings
    from shared.ai_caller import get_active_provider
    provider = get_active_provider(settings)
    return {
        "provider": provider,
        "claude_configured": bool(settings.ANTHROPIC_API_KEY),
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "claude_model":  settings.ANTHROPIC_MODEL,
        "openai_model":  settings.OPENAI_MODEL,
    }


@app.post("/ai/provider")
async def switch_provider(req: ProviderSwitchRequest):
    """运行时切换 AI 提供商（重启前有效）"""
    if req.provider not in ("claude", "openai"):
        raise HTTPException(status_code=400, detail="provider 必须是 claude 或 openai")
    from shared.ai_caller import set_active_provider
    set_active_provider(req.provider)
    return {"ok": True, "provider": req.provider}


@app.get("/ai/test/{provider}")
async def test_provider_endpoint(provider: str):
    """测试指定提供商的连通性（同步阻塞，较慢，仅供用户主动调用）"""
    if provider not in ("claude", "openai"):
        raise HTTPException(status_code=400, detail="provider 必须是 claude 或 openai")

    def _test():
        from config.settings import settings
        from shared.ai_caller import test_provider
        return test_provider(provider, settings)

    result = await asyncio.to_thread(_test)
    return result


@app.get("/health/claude")
async def check_claude():
    """检测 Claude API Key 配置（不实际调用，避免阻塞）"""
    try:
        from config.settings import settings
        if not settings.ANTHROPIC_API_KEY:
            return {"ok": False, "reason": "ANTHROPIC_API_KEY 未配置"}
        key = settings.ANTHROPIC_API_KEY
        if not key.startswith("sk-"):
            return {"ok": False, "reason": "ANTHROPIC_API_KEY 格式不正确（应以 sk- 开头）"}
        return {
            "ok": True,
            "model": settings.ANTHROPIC_MODEL,
            "base_url": settings.ANTHROPIC_BASE_URL or "官方",
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


@app.get("/health/claude/ping")
async def ping_claude():
    """真正调用 Claude API 测试连通性（慢，仅在用户主动点击时调用）"""
    def _ping():
        from config.settings import settings
        import anthropic, httpx
        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_BASE_URL or None,
            timeout=httpx.Timeout(60.0, connect=30.0),
        )
        client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        return settings.ANTHROPIC_MODEL, settings.ANTHROPIC_BASE_URL or "官方"

    try:
        model, base_url = await asyncio.to_thread(_ping)
        return {"ok": True, "model": model, "base_url": base_url}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:200]}


if __name__ == "__main__":
    import uvicorn, sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Starting SOD/COD Research Assistant API on port {port}...")
    print(f"API docs: http://localhost:{port}/docs")
    print(f"Frontend: http://localhost:3000")
    uvicorn.run("fastapi_server:app", host="0.0.0.0", port=port, reload=False, workers=1)
