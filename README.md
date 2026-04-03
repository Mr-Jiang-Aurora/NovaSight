<div align="center">

# NovaSight · 星探智研

**AI-Powered Multi-Agent Research Assistant for COD/SOD**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16.2-black?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](#overview) · [功能演示](#screenshots) · [快速开始](#quick-start)

</div>

---

## Overview

**NovaSight (星探智研)** is an AI-powered multi-agent system designed to assist researchers in the fields of **Camouflaged Object Detection (COD)** and **Salient Object Detection (SOD)**. It automates literature survey, metric diagnosis, code analysis, architecture image understanding, and comprehensive report generation through five specialized collaborative agents.

> Built for researchers who want deep, actionable insights — not generic summaries.

---

## ✨ Key Features

| Agent | Role | Capabilities |
|-------|------|-------------|
| **Agent 1** · SOTA Survey | Literature Intelligence | Multi-source academic search (Semantic Scholar / OpenAlex / DBLP / CVF), automated score extraction, SOTA leaderboard generation |
| **Agent 2** · Metric Diagnosis | Quantitative Analysis | 6-dimensional deep analysis: score distribution, annual trends, method comparison, saturation detection, Top-5 breakdown |
| **Agent 3** · Code Analysis | Architecture Inspection | Deep semantic code analysis via GitHub URL or local upload; integrates Agent 4 architecture hints for enhanced insight |
| **Agent 4** · Vision Analysis | Image Understanding | Architecture diagram parsing (6 dimensions), Figure provenance tracing, architecture-code cross-validation, 5-dimension innovation evaluation |
| **Master** · Orchestrator | Report Synthesis | Full pipeline coordination; generates a structured 6-chapter comprehensive research report |

---

## Screenshots

> _The pipeline overview (interactive demo available at `/pipeline` in the running app)._

```
User Interface (Next.js Frontend)
         │  HTTP REST API
         ▼
 FastAPI Backend  (:8000)
 ┌───────┬────────┬────────┬────────┐
 │       │        │        │        │
Agent1  Agent2  Agent3  Agent4      │
SOTA    Metric   Code    Vision     │
Survey  Diag.   Analysis Analysis   │
 │       │        │        │        │
 ▼       ▼        ▼        ▼        │
S.Scholar Claude GitHub  Claude     │
OpenAlex        API     VLM         │
DBLP                               │
CVF                                │
 └───────┴────────┴────────┴───────┘
                  │
           Master Agent
        6-Chapter Report (MD)
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- An API key from [Anthropic](https://console.anthropic.com/) or [OpenAI](https://platform.openai.com/) (relay services supported)

### 1. Clone the repository

```bash
git clone https://github.com/Mr-Jiang-Aurora/NovaSight.git
cd NovaSight
```

### 2. Backend setup

```bash
cd sod_cod_assistant
pip install -r requirements.txt

# Copy the example env file and fill in your keys
cp .env.example .env
```

Edit `.env` with your API credentials (see [Configuration](#configuration)).

### 3. Frontend setup

```bash
cd sod-cod-frontend
npm install
npm run build        # Build production bundle (required before first run)
```

### 4. Start services

**Option A — BAT scripts (Windows, recommended):**
```
Double-click: start_backend.bat
Double-click: start_frontend.bat
```

**Option B — Manual:**
```powershell
# Terminal 1 — Backend
cd sod_cod_assistant
python fastapi_server.py

# Terminal 2 — Frontend (production mode, NOT npm run dev)
cd sod-cod-frontend
npx next start
```

Open **http://localhost:3000** in your browser.

> ⚠️ Always use `npx next start` (production mode). Using `npm run dev` will cause extremely high memory usage.

---

## Configuration

Copy `sod_cod_assistant/.env.example` to `sod_cod_assistant/.env` and configure:

```env
# ── AI Provider (choose one or both) ──────────────────────────
ACTIVE_AI_PROVIDER=openai          # "claude" or "openai"

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
# ANTHROPIC_BASE_URL=              # Leave blank for official API

# OpenAI / Relay Service
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1   # Must end with /v1

# ── Optional ───────────────────────────────────────────────────
SEMANTIC_SCHOLAR_API_KEY=          # Improves rate limits (free key available)
GITHUB_TOKEN=                      # Increases GitHub API rate limit for Agent 3
```

> ⚠️ **Never commit your `.env` file.** It is listed in `.gitignore`.

---

## Usage

### Recommended Pipeline Order

```
Agent 1 → Agent 2 → Agent 4 → Agent 3 → Master
```

### Agent Descriptions

**Agent 1 — SOTA Survey**
- Select domain: COD or SOD
- Set year range (e.g., 2023–2025)
- "Load from cache" for instant results, or "Start Search" for fresh data
- Outputs: SOTA leaderboard, paper cards, score rankings

**Agent 2 — Metric Diagnosis**
- Optionally describe your current method for personalized advice
- Reads Agent 1 output automatically
- Outputs: 6-dimension analysis report with charts and trend data

**Agent 4 — Vision Analysis**
- Upload your architecture diagram for 6-dimension parsing
- Enable Figure Provenance Tracing to find original paper sources
- Enable Innovation Evaluation for a 5-dimension academic scoring
- Outputs: 4 separate report tabs

**Agent 3 — Code Analysis**
- Input a GitHub URL (e.g., `https://github.com/user/repo`) or upload local files
- Architecture hints from Agent 4 are auto-loaded to enhance analysis
- Supports up to 30 files / 10,000 lines of code
- Outputs: detailed semantic code analysis report

**Master — Full Report**
- "Run Full Pipeline": executes all available agents and generates a comprehensive report
- Outputs: 6-chapter structured Markdown report

---

## Agent 4 Report Types

The vision agent generates four distinct reports, accessible via tabs in the report viewer:

| Tab | Content |
|-----|---------|
| Architecture Analysis | 6-dimension deep parsing of the architecture diagram |
| Figure Provenance | Automated paper source search for the uploaded figure |
| Arch-Code Validation | Cross-validates architecture modules against actual code |
| Innovation Evaluation | 5-dimension academic novelty scoring |

---

## Tech Stack

### Backend
- **Python 3.10+** · FastAPI 0.115 · Uvicorn
- **Anthropic SDK** · **OpenAI SDK** — dual-provider AI calls
- **aiohttp** · **httpx** — async HTTP
- **PyMuPDF** · **Docling** · **RapidOCR** — PDF parsing
- **BeautifulSoup4** · **lxml** — HTML parsing
- **Pydantic v2** — data validation

### Frontend
- **Next.js 16.2** · **React 19** · **TypeScript**
- **Zustand 5** — global state
- **Framer Motion** — animations
- **ReactMarkdown** · **remark-gfm** — Markdown rendering
- **react-dropzone** — file upload
- **lucide-react** — icons

---

## Project Structure

```
NovaSight/
├── sod_cod_assistant/           # Python backend (FastAPI)
│   ├── fastapi_server.py        # Entry point (:8000)
│   ├── agents/
│   │   ├── agent1_sota/         # SOTA survey pipeline
│   │   ├── agent2_gap/          # Metric diagnosis
│   │   ├── agent3_code/         # Code analysis
│   │   ├── agent4_vision/       # Vision & architecture analysis
│   │   └── master/              # Orchestration & report synthesis
│   ├── shared/
│   │   └── ai_caller.py         # Unified AI client (Claude + OpenAI)
│   ├── config/
│   ├── cache/                   # SOTA cache, PDFs, agent outputs
│   ├── .env.example             # Environment variable template
│   └── requirements.txt
│
├── sod-cod-frontend/            # Next.js frontend
│   ├── src/
│   │   ├── app/workspace/       # Main workspace page
│   │   ├── components/
│   │   │   ├── agents/          # Agent control panels
│   │   │   ├── reports/         # Report viewer with navigation
│   │   │   └── layout/          # Sidebar, banners
│   │   ├── store/               # Zustand global state
│   │   └── lib/                 # API client, theme utils
│   └── package.json
│
├── start_backend.bat            # Windows: start backend
├── start_frontend.bat           # Windows: build + start frontend
├── kill_backend.bat             # Windows: stop backend
├── pipeline_demo.html           # Interactive pipeline demo (EN)
├── pipeline_demo_zh.html        # Interactive pipeline demo (ZH)
└── README.md
```

---

## FAQ

**Q: Frontend shows connection error / spinning?**  
A: Verify the backend is running at http://localhost:8000/docs. Check your `.env` API keys.

**Q: "API call failed 503"?**  
A: Temporary rate limiting by the AI provider. The system retries automatically. You can also switch providers in the top status bar.

**Q: Agent 1 returns very few papers?**  
A: Academic APIs (especially DBLP) can time out. Use "Load from cache" first — the cached data is a curated set of 65+ papers.

**Q: Agent 4 arch-code validation report is empty?**  
A: Run Agent 3 code analysis first. The validation feature depends on Agent 3's output JSON.

**Q: Computer freezes / high memory usage?**  
A: You must use `npx next start` (production build). Never use `npm run dev` for this project.

**Q: Port already in use (EADDRINUSE)?**
```powershell
netstat -ano | findstr ":8000"
Stop-Process -Id <PID> -Force

netstat -ano | findstr ":3000"
Stop-Process -Id <PID> -Force
```

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

*NovaSight · 星探智研 — v1.0 · March 2026*

</div>
