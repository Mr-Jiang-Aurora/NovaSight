# SOD/COD 科研助手

面向显著性目标检测（SOD）和伪装目标检测（COD）方向的多 Agent 科研辅助系统。

## 系统概览

本系统由五个 Agent 协作完成科研调研与诊断任务：

| Agent | 名称 | 功能 |
|-------|------|------|
| 主控 Agent | Master Orchestrator | 调度各 Agent，生成最终诊断报告 |
| Agent1 | SOTA 调研 Agent | 自动调研 CCF-A/SCI Q1 顶会顶刊，构建 SOTA 排行榜 |
| Agent2 | 指标对比诊断 Agent | 对比用户模型与 SOTA，输出差距分析 |
| Agent3 | 代码架构分析 Agent | 分析 PyTorch 代码，给出改进建议 |
| Agent4 | 论文图识别 Agent | 校验论文图文一致性 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Keys

复制 `.env.example` 为 `.env`，填入真实的 API Keys：

```bash
cp .env.example .env
# 编辑 .env 文件
```

- **Semantic Scholar API Key**：[申请地址](https://www.semanticscholar.org/product/api#api-key-form)（免费）
- **OpenAlex API Key**：[申请地址](https://openalex.org/settings/api)（免费，2026年2月起必须）

### 3. 运行搜索测试

```bash
python scripts/run_search_test.py
```

## Agent1 四层管线

```
第一层  搜索层    → 四源并联发现论文（Phase 1 已实现）
第二层  获取层    → PDF 下载（Phase 2）
第三层  解析层    → 表格提取（Phase 3）
第四层  缓存层    → 增量更新（Phase 4）
```

## 调研范围

- 仅收录 **CCF-A** 评级会议和 **SCI Q1** 分区期刊
- COD/SOD 方向约 50-80 篇核心论文
- 覆盖：CVPR、ICCV、ECCV、NeurIPS、AAAI、ICML、IEEE TPAMI、IEEE TIP、IJCV 等

## 项目结构

```
sod_cod_assistant/
├── config/           # 配置与领域知识库
├── shared/           # 跨 Agent 共用模块（数据模型、工具函数）
├── agents/
│   ├── master/       # 主控 Agent
│   ├── agent1_sota/  # SOTA 调研 Agent（含四层管线）
│   ├── agent2_gap/   # 指标对比诊断 Agent
│   ├── agent3_code/  # 代码架构分析 Agent
│   └── agent4_figure/# 论文图识别 Agent
├── cache/            # 运行时缓存
├── tests/            # 单元测试
└── scripts/          # 独立运行脚本
```

## 技术栈

- Python 3.10+
- asyncio + aiohttp（并行搜索）
- Pydantic v2（数据模型）
- BeautifulSoup4（HTML 解析）
- PyMuPDF（PDF 处理，Phase 2+）
