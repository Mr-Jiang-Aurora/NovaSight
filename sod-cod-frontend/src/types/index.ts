export type AgentId = 'agent1' | 'agent2' | 'agent3' | 'agent4' | 'master';

export type AgentStatus = 'idle' | 'running' | 'success' | 'error' | 'skipped';

export interface AgentState {
  status: AgentStatus;
  progress: number;
  currentStep: string;
  error: string;
}

export interface ReportFile {
  name: string;
  path: string;
  size_kb: number;
  modified: string;
  agentId?: string;
  /** Agent4 专属分类标签 */
  report_type?: 'figure_trace' | 'innovation' | 'arch_validation' | 'arch_analysis' | 'other';
}

export interface Agent1Params {
  domain: string;
  use_cache: boolean;
  start_year?: number;
  end_year?: number;
}

export interface Agent2Params {
  domain: string;
  user_method_desc: string;
}

export interface Agent3GithubParams {
  domain: string;
  github_url: string;
  structure_hint: string;
  agent2_summary: string;
}

export interface Agent4Params {
  mode: 'arch' | 'visual';
  user_hint: string;
  user_method: string;
}

export interface MasterParams {
  domain: string;
  github_url?: string;
  user_method_desc: string;
  run_agent3: boolean;
  run_agent4: boolean;
}

export const AGENT_COLORS: Record<string, string> = {
  agent1: '#3b82f6',
  agent2: '#10b981',
  agent3: '#f59e0b',
  agent4: '#8b5cf6',
  master: '#c8b560',
};

export const AGENT_LABELS: Record<string, string> = {
  agent1: 'SOTA 调研',
  agent2: '指标诊断',
  agent3: '代码分析',
  agent4: '图像分析',
  master: '主控输出',
};
