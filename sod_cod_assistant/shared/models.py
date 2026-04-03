"""
SOD/COD 科研助手 - 共享数据模型
所有 Agent 间传递数据的 Pydantic 模型定义
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class ExtractionConfidence(str, Enum):
    """指标提取置信度"""
    HIGH   = "high"     # 来自 ar5iv HTML 或 PyMuPDF 规则提取，高可信
    MEDIUM = "medium"   # 来自 Docling 结构识别
    LOW    = "low"      # 来自 VLM 提取，需人工核查
    MANUAL = "manual"   # 用户手动输入


class PaperSource(str, Enum):
    """论文发现来源"""
    SEMANTIC_SCHOLAR = "semantic_scholar"
    OPENALEX         = "openalex"
    DBLP             = "dblp"
    CVF_OPEN_ACCESS  = "cvf_open_access"
    MANUAL           = "manual"


class MetricScores(BaseModel):
    """单个数据集上的指标分数"""
    Sm:    Optional[float] = None
    Em:    Optional[float] = None
    Fm:    Optional[float] = None
    MAE:   Optional[float] = None
    maxFm: Optional[float] = None
    avgFm: Optional[float] = None
    # 原始提取的值（用于 debug，key 为原始列名）
    raw_values: Dict[str, float] = Field(default_factory=dict)
    confidence: ExtractionConfidence = ExtractionConfidence.LOW

    model_config = {"extra": "allow"}  # 允许存储额外的指标字段


class PaperRecord(BaseModel):
    """一篇论文的完整记录（搜索层产出的基础数据）"""

    # ── 唯一标识 ────────────────────────────────────────────────
    paper_id: str = ""             # Semantic Scholar paperId（主键）
    arxiv_id: Optional[str] = None
    doi:      Optional[str] = None
    s2_corpus_id: Optional[str] = None

    # ── 论文元数据 ───────────────────────────────────────────────
    title:    str = ""
    authors:  List[str] = Field(default_factory=list)
    year:     Optional[int] = None
    abstract: Optional[str] = None

    # ── 发表信息 ─────────────────────────────────────────────────
    venue:          Optional[str] = None   # 期刊/会议简称，如 "IEEE TPAMI"
    venue_full:     Optional[str] = None   # 全称
    ccf_rank:       Optional[str] = None   # "A" / "B" / "C" / None
    sci_tier:       Optional[str] = None   # "Q1" / "Q2" / None
    impact_factor:  Optional[float] = None

    # ── 链接 ─────────────────────────────────────────────────────
    paper_url:  Optional[str] = None   # arXiv 或官方 DOI 链接
    pdf_url:    Optional[str] = None   # 可直接下载的 PDF 链接
    code_url:   Optional[str] = None   # GitHub 代码仓库
    project_url: Optional[str] = None  # 项目主页

    # ── 指标分数（Phase 3 填充，搜索层为空）───────────────────────
    scores: Dict[str, MetricScores] = Field(default_factory=dict)
    # key 为数据集名，如 "COD10K"、"CAMO"

    # ── 溯源信息 ─────────────────────────────────────────────────
    found_by:   List[PaperSource] = Field(default_factory=list)
    citation_count: Optional[int] = None
    fetched_at: Optional[datetime] = None
    pdf_fetched: bool = False
    scores_extracted: bool = False

    def get_primary_score(self, dataset: str, metric: str = "Sm") -> Optional[float]:
        """获取指定数据集上的主指标分数"""
        if dataset in self.scores:
            return getattr(self.scores[dataset], metric, None)
        return None

    def has_target_venue(self) -> bool:
        """判断该论文是否发表在目标顶会顶刊"""
        from config.knowledge_base import is_target_venue
        return is_target_venue(self.venue or "")


class SearchResult(BaseModel):
    """单次搜索的结果集"""
    source:     PaperSource
    domain:     str
    query_used: str
    papers:     List[PaperRecord] = Field(default_factory=list)
    total_found: int = 0
    search_time_seconds: float = 0.0
    errors:     List[str] = Field(default_factory=list)


class SOTALeaderboard(BaseModel):
    """某领域的 SOTA 排行榜（Agent1 最终输出）"""
    domain:         str
    generated_at:   datetime = Field(default_factory=datetime.now)
    version:        str = "2.0"
    papers:         List[PaperRecord] = Field(default_factory=list)
    total_papers:   int = 0
    # 每个数据集的论文排名（key = 数据集名）
    rankings:       Dict[str, List[str]] = Field(default_factory=dict)
    # 数据来源统计
    source_stats:   Dict[str, int] = Field(default_factory=dict)
    search_completed: bool = False
    fetch_completed:  bool = False
    parse_completed:  bool = False


# ─────────────────────────────────────────────────────────────────────
# Phase 3 解析失败报告模型（提前定义，Phase 3 实现时直接使用）
# ─────────────────────────────────────────────────────────────────────

class FailureReason(str, Enum):
    """PDF 表格解析失败原因枚举"""
    ROTATED_TABLE        = "rotated_table"        # 表格旋转 90° 排版
    NO_TABLE_FOUND       = "no_table_found"       # 未检测到任何表格
    PARSE_ERROR          = "parse_error"          # 提取工具报错崩溃
    METRIC_UNRECOGNIZED  = "metric_unrecognized"  # 指标名无法识别
    DATASET_UNRECOGNIZED = "dataset_unrecognized" # 数据集名无法识别
    NO_PDF               = "no_pdf"              # PDF 获取失败，无法进入解析
    LOW_CONFIDENCE       = "low_confidence"       # 所有指标置信度均为 LOW


class ExtractionFailureRecord(BaseModel):
    """Phase 3 解析层生成的单篇论文失败记录"""
    paper_id:           str
    title:              str
    venue:              Optional[str] = None
    year:               Optional[int] = None
    ccf_rank:           Optional[str] = None
    sci_tier:           Optional[str] = None
    paper_url:          Optional[str] = None
    pdf_url:            Optional[str] = None
    code_url:           Optional[str] = None
    failure_reason:     FailureReason
    failure_detail:     str = ""
    attempted_methods:  List[str] = Field(default_factory=list)
    manually_verified:  bool = False    # 用户手动核查后标记
    notes:              str = ""        # 用户备注


class ParseReport(BaseModel):
    """Phase 3 完成后的整体解析报告"""
    domain:        str
    generated_at:  datetime = Field(default_factory=datetime.now)
    total_papers:  int = 0
    success_count: int = 0
    failure_count: int = 0
    failures:      List[ExtractionFailureRecord] = Field(default_factory=list)

    def add_failure(
        self,
        paper: "PaperRecord",
        reason: FailureReason,
        detail: str = "",
        methods: Optional[List[str]] = None,
    ) -> None:
        """添加一条解析失败记录"""
        self.failures.append(ExtractionFailureRecord(
            paper_id=paper.paper_id,
            title=paper.title,
            venue=paper.venue,
            year=paper.year,
            ccf_rank=paper.ccf_rank,
            sci_tier=paper.sci_tier,
            paper_url=paper.paper_url,
            pdf_url=paper.pdf_url,
            code_url=paper.code_url,
            failure_reason=reason,
            failure_detail=detail,
            attempted_methods=methods or [],
        ))
        self.failure_count += 1

    def export_markdown(self, output_path: str) -> None:
        """将失败报告导出为 Markdown 文件，方便用户手动核查"""
        REASON_ZH = {
            "rotated_table":        "旋转表格",
            "no_table_found":       "未找到表格",
            "parse_error":          "解析报错",
            "metric_unrecognized":  "指标名无法识别",
            "dataset_unrecognized": "数据集名无法识别",
            "no_pdf":               "PDF 获取失败",
            "low_confidence":       "提取置信度过低",
        }

        lines = [
            "# SOD/COD 科研助手 — 解析失败论文列表",
            f"**领域**：{self.domain} | "
            f"**生成时间**：{self.generated_at.strftime('%Y-%m-%d %H:%M')} | "
            f"**共 {self.failure_count} 篇**",
            "",
            "> 以下论文的实验结果表格无法自动提取，"
            "建议手动查阅原文核对指标后填入系统。",
            "",
        ]

        for i, rec in enumerate(self.failures, 1):
            code_link = f"[GitHub]({rec.code_url})" if rec.code_url else "暂无"
            reason_zh = REASON_ZH.get(rec.failure_reason, rec.failure_reason)
            lines += [
                "---",
                f"## {i}. {rec.title}",
                "",
                "| 字段 | 内容 |",
                "|------|------|",
                f"| 期刊/会议 | {rec.venue or 'N/A'}"
                f"（CCF-{rec.ccf_rank or '?'}，{rec.sci_tier or 'N/A'}）|",
                f"| 发表年份 | {rec.year or 'N/A'} |",
                f"| 论文链接 | {'[点击查看](' + rec.paper_url + ')' if rec.paper_url else 'N/A'} |",
                f"| PDF 链接 | {'[下载 PDF](' + rec.pdf_url + ')' if rec.pdf_url else 'N/A'} |",
                f"| 代码仓库 | {code_link} |",
                f"| 失败原因 | **{reason_zh}**：{rec.failure_detail} |",
                f"| 已尝试方法 | {', '.join(rec.attempted_methods) or 'N/A'} |",
                "",
                "**建议操作**：打开 PDF，手动查找包含数据集对比表格的页面，"
                "记录各指标数值。",
                "",
            ]

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


# ── Agent2 专用数据结构 ──────────────────────────────────────────────

class RankEntry(BaseModel):
    """排行榜中的单条记录"""
    rank:      int
    paper_id:  str
    title:     str
    venue:     Optional[str] = None
    year:      Optional[int] = None
    ccf_rank:  Optional[str] = None
    value:     float
    paper_url: Optional[str] = None
    code_url:  Optional[str] = None


class DatasetRanking(BaseModel):
    """单数据集、单指标的排行榜"""
    dataset:   str
    metric:    str
    direction: str                              # "up" 越高越好 / "down" 越低越好
    entries:   List[RankEntry] = Field(default_factory=list)


class MethodProfile(BaseModel):
    """单篇论文的强弱特征画像"""
    paper_id:  str
    title:     str
    venue:     Optional[str] = None
    year:      Optional[int] = None

    # 在每个数据集上的排名百分位（0-1，越低越强）
    # {"COD10K": {"Sm": 0.05, "MAE": 0.12, ...}, ...}
    rank_percentiles: Dict[str, Dict[str, float]] = Field(default_factory=dict)

    strongest_dataset: Optional[str] = None
    strongest_metric:  Optional[str] = None
    weakest_dataset:   Optional[str] = None
    weakest_metric:    Optional[str] = None
    overall_score:     float = 0.0


class GapAnalysis(BaseModel):
    """差距与进步率分析"""
    domain:     str
    as_of_year: int
    dataset:    str

    # 历年各指标 SOTA 最优值 {year: {metric: value}}
    yearly_sota:  Dict[int, Dict[str, float]] = Field(default_factory=dict)
    # 年度进步量 {year: {metric: delta}}（正值=改善）
    yearly_delta: Dict[int, Dict[str, float]] = Field(default_factory=dict)
    # 饱和度评估 {metric: "saturating"/"active"/"rapid"/"insufficient_data"}
    saturation:   Dict[str, str] = Field(default_factory=dict)
    # 当前方法间差距（最强-最弱）{metric: range_value}
    current_range: Dict[str, float] = Field(default_factory=dict)


class Agent2Report(BaseModel):
    """Agent2 完整诊断报告"""
    domain:         str
    generated_at:   datetime = Field(default_factory=datetime.now)
    total_methods:  int = 0
    scored_methods: int = 0

    rankings:     List[DatasetRanking] = Field(default_factory=list)
    profiles:     List[MethodProfile]  = Field(default_factory=list)
    gap_analyses: List[GapAnalysis]    = Field(default_factory=list)
    narrative:    str = ""   # Claude 生成的自然语言洞察
    summary:      str = ""   # 精简摘要（供主控 Agent 使用）


# ── Agent3 专用数据结构 ──────────────────────────────────────────────

class Agent3InputMode(str, Enum):
    GITHUB = "github"   # 模式A：GitHub 链接
    UPLOAD = "upload"   # 模式B：本地上传
    BOTH   = "both"     # 两种模式同时使用


class ArchComponent(BaseModel):
    """模型架构中的单个组件"""
    component_type: str               # "backbone"/"neck"/"head"/"decoder"/"module"
    name:           str               # 标准化名称，如 "Swin-T"/"FPN"/"CAM"
    source_file:    str  = ""
    class_name:     str  = ""
    is_pretrained:  bool = False
    pretrained_on:  Optional[str] = None
    line_number:    Optional[int] = None


class LossConfig(BaseModel):
    """损失函数配置"""
    loss_name:    str
    weight:       float = 1.0
    source_file:  str   = ""
    is_auxiliary: bool  = False


class TrainConfig(BaseModel):
    """训练超参数"""
    batch_size:    Optional[int]   = None
    learning_rate: Optional[float] = None
    lr_scheduler:  Optional[str]   = None
    optimizer:     Optional[str]   = None
    epochs:        Optional[int]   = None
    warmup_epochs: Optional[int]   = None
    input_size:    Optional[int]   = None
    config_file:   str = ""


class ImprovementSuggestion(BaseModel):
    """单条改进建议"""
    category:   str         # "backbone"/"loss"/"training"/"architecture"/"data"
    priority:   str         # "high"/"medium"/"low"
    suggestion: str
    reference:  str = ""    # 参考的 SOTA 方法
    code_hint:  str = ""    # 代码层面的提示


class UserCodeAnalysis(BaseModel):
    """用户代码分析结果（Agent3 的核心输出）"""
    input_mode:     str = "unknown"
    github_url:     Optional[str] = None
    uploaded_files: List[str] = Field(default_factory=list)

    # Agent4 联动接口（预留）
    structure_hint: str = ""

    framework:        Optional[str] = None
    torch_version:    Optional[str] = None
    components:       List[ArchComponent]      = Field(default_factory=list)
    losses:           List[LossConfig]         = Field(default_factory=list)
    train_config:     Optional[TrainConfig]    = None
    key_innovations:  List[str]                = Field(default_factory=list)
    potential_issues: List[str]                = Field(default_factory=list)

    arch_summary:     str = ""
    suggestions:      List[ImprovementSuggestion] = Field(default_factory=list)
    sota_gap_summary: str = ""

    status:      str = "pending"
    fail_reason: str = ""


class Agent3Report(BaseModel):
    """Agent3 完整报告"""
    generated_at: datetime = Field(default_factory=datetime.now)
    domain:       str = ""
    analysis:     Optional[UserCodeAnalysis] = None
    narrative:    str = ""
    summary:      str = ""


# ── Agent4 专用数据结构 ──────────────────────────────────────────────

class ArchHint(BaseModel):
    """架构图解析结果（模式1输出，传给 Agent3）"""
    image_path:     str = ""
    image_desc:     str = ""

    backbone:       Optional[str] = None
    decoder_type:   Optional[str] = None
    key_modules:    List[str] = Field(default_factory=list)
    data_flow:      str = ""
    file_hints:     List[str] = Field(default_factory=list)
    structure_hint: str = ""
    confidence:     str = "medium"
    notes:          str = ""

    # 原始 Claude 响应（保留完整结构化字段，供报告写入和质量审查）
    raw_data:       Optional[dict] = Field(default=None, exclude=False)

    # Figure 溯源结果（TASK1）
    trace_result:          Optional[Any] = None   # FigureTraceResult
    # 学术创新性评估（TASK3）
    innovation_evaluation: str           = ""


class ColumnAnalysis(BaseModel):
    """可视化对比图中单列（单方法）的分析结果"""
    column_index:        int
    method_name:         str = ""

    edge_sharpness:      int = 0
    bg_cleanliness:      int = 0
    target_completeness: int = 0
    shape_accuracy:      int = 0

    strengths:    List[str] = Field(default_factory=list)
    weaknesses:   List[str] = Field(default_factory=list)
    overall_desc: str = ""


class VisualAnalysis(BaseModel):
    """可视化对比图分析结果（模式2输出）"""
    image_path:  str = ""
    image_count: int = 0
    row_count:   int = 0

    columns:     List[ColumnAnalysis] = Field(default_factory=list)

    best_method:       str = ""
    worst_method:      str = ""
    key_findings:      List[str] = Field(default_factory=list)
    user_method_rank:  Optional[int] = None
    improvement_focus: str = ""


class Agent4Report(BaseModel):
    """Agent4 完整报告"""
    generated_at: datetime = Field(default_factory=datetime.now)
    mode:         str = "unknown"

    arch_hint: Optional[ArchHint]      = None
    visual:    Optional[VisualAnalysis] = None

    structure_hint_for_agent3: str = ""
    summary_for_agent2:        str = ""

    status:     str = "pending"
    fail_reason: str = ""


# ── 主控 Agent 专用数据结构 ───────────────────────────────────────────

class WorkflowPlan(BaseModel):
    """工作流执行计划"""
    run_agent1:  bool = True    # 是否执行 SOTA 搜索
    run_agent2:  bool = True    # 是否执行指标诊断
    run_agent3:  bool = False   # 是否执行代码分析（需要有代码输入）
    run_agent4:  bool = False   # 是否执行图像分析（需要有图片输入）
    agent3_mode: str  = ""      # "github" / "upload" / "both"
    agent4_mode: str  = ""      # "arch" / "visual" / "both"
    reason:      str  = ""      # 规划原因（日志用）


class SharedContext(BaseModel):
    """跨 Agent 共享上下文"""
    # 基本信息
    session_id: str      = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    domain:     str      = "COD"
    created_at: datetime = Field(default_factory=datetime.now)

    # 用户输入
    github_url:        Optional[str]  = None
    uploaded_files:    Dict[str, Any] = Field(default_factory=dict)
    local_dir:         Optional[str]  = None   # 本地代码目录（替代 GitHub）
    arch_image_path:   Optional[str]  = None
    visual_image_path: Optional[str]  = None
    user_method_desc:  str            = ""

    # 工作流计划
    plan: Optional[WorkflowPlan] = None

    # Agent 执行状态
    agent1_done:  bool = False
    agent2_done:  bool = False
    agent3_done:  bool = False
    agent4_done:  bool = False
    agent1_error: str  = ""
    agent2_error: str  = ""
    agent3_error: str  = ""
    agent4_error: str  = ""

    # Agent 输出（核心数据）
    leaderboard:    Optional[Any] = None    # Agent1: SOTALeaderboard
    agent2_report:  Optional[Any] = None    # Agent2: Agent2Report
    agent2_summary: str           = ""      # Agent2 精简摘要
    agent3_report:  Optional[Any] = None    # Agent3: Agent3Report
    agent3_summary: str           = ""      # Agent3 精简摘要
    agent4_report:  Optional[Any] = None    # Agent4: Agent4Report
    structure_hint: str           = ""      # Agent4→Agent3 的结构提示

    # 最终输出
    master_narrative: str             = ""
    output_paths:     Dict[str, str]  = Field(default_factory=dict)

    # 架构-代码双向验证报告（TASK2）
    validation_report: Optional[Any] = None   # ArchCodeValidationReport


class MasterReport(BaseModel):
    """主控 Agent 最终输出报告"""
    session_id:   str      = ""
    domain:       str      = ""
    generated_at: datetime = Field(default_factory=datetime.now)

    # 执行摘要
    agents_run:   List[str] = Field(default_factory=list)
    total_time_s: float     = 0.0

    # 各部分内容
    sota_summary:      str = ""
    code_diagnosis:    str = ""
    visual_summary:    str = ""
    arch_hint_summary: str = ""

    # 核心输出：综合建议
    narrative:       str       = ""
    top_suggestions: List[str] = Field(default_factory=list)

    # 输出文件路径
    output_paths: Dict[str, str] = Field(default_factory=dict)

    # 所有子 Agent 的输出文件路径（键：agent1/agent2/agent3/agent4）
    all_sub_outputs: Dict[str, Any] = Field(default_factory=dict)


# ── Agent4 Figure 溯源数据结构 ────────────────────────────────────────

class PaperCandidate(BaseModel):
    """Figure 溯源的候选论文"""
    paper_id:       str           = ""
    title:          str           = ""
    year:           Optional[int] = None
    venue:          str           = ""
    authors:        List[str]     = Field(default_factory=list)
    citation_count: int           = 0
    abstract:       str           = ""
    pdf_url:        str           = ""     # 开放获取 PDF 链接（无则为空）
    arxiv_id:       str           = ""     # arXiv ID（无则为空）
    s2_url:         str           = ""     # Semantic Scholar 论文页面
    code_url:       str           = ""     # 代码链接（需从 PaperWithCode 补充）
    match_reason:   str           = ""     # 为什么认为这是原论文


class FigureTraceResult(BaseModel):
    """Figure 溯源完整结果"""
    arch_hint_summary: str                      = ""
    candidates:        List[PaperCandidate]     = Field(default_factory=list)
    best_match:        Optional[PaperCandidate] = None
    confidence:        str                      = "low"   # "high"/"medium"/"low"
    search_queries:    List[str]                = Field(default_factory=list)
    trace_summary:     str                      = ""      # 溯源结论的自然语言描述


# ── 架构-代码双向验证数据结构 ─────────────────────────────────────────

class ModuleMatchResult(BaseModel):
    """单个模块的匹配结果"""
    arch_module_name:  str   = ""
    arch_description:  str   = ""
    status:            str   = "missing"   # "verified"/"partial"/"missing"
    code_name:         str   = ""
    code_location:     str   = ""
    match_score:       float = 0.0
    match_method:      str   = ""
    verification_note: str   = ""


class ArchCodeValidationReport(BaseModel):
    """双向验证完整报告"""
    arch_to_code_matches: List[ModuleMatchResult] = Field(default_factory=list)
    code_only_modules:    List[dict]              = Field(default_factory=list)

    total_arch_modules: int   = 0
    verified_count:     int   = 0
    partial_count:      int   = 0
    missing_count:      int   = 0
    code_only_count:    int   = 0
    consistency_score:  float = 0.0

    conclusion: str = ""
