import { create } from 'zustand';
import type { AgentState, ReportFile } from '@/types';

interface PipelineStore {
  agents: Record<string, AgentState>;

  domain: string;
  githubUrl: string;
  uploadedFiles: File[];
  archImage: File | null;
  visualImage: File | null;
  userMethodDesc: string;

  reportFiles: Record<string, ReportFile[]>;
  activeReport: Record<string, string>;
  reportContent: Record<string, string>;

  structureHint: string;
  agent2Summary: string;

  setDomain: (d: string) => void;
  setGithubUrl: (url: string) => void;
  setUploadedFiles: (files: File[]) => void;
  setArchImage: (f: File | null) => void;
  setVisualImage: (f: File | null) => void;
  setUserMethodDesc: (desc: string) => void;
  setAgentStatus: (agentId: string, status: Partial<AgentState>) => void;
  setReportFiles: (agentId: string, files: ReportFile[]) => void;
  setActiveReport: (agentId: string, filename: string) => void;
  setReportContent: (filename: string, content: string) => void;
  setStructureHint: (hint: string) => void;
  setAgent2Summary: (summary: string) => void;
}

export const usePipelineStore = create<PipelineStore>((set) => ({
  agents: {
    agent1: { status: 'idle', progress: 0, currentStep: '', error: '' },
    agent2: { status: 'idle', progress: 0, currentStep: '', error: '' },
    agent3: { status: 'idle', progress: 0, currentStep: '', error: '' },
    agent4: { status: 'idle', progress: 0, currentStep: '', error: '' },
    master: { status: 'idle', progress: 0, currentStep: '', error: '' },
  },
  domain: 'COD',
  githubUrl: '',
  uploadedFiles: [],
  archImage: null,
  visualImage: null,
  userMethodDesc: '',
  reportFiles: {},
  activeReport: {},
  reportContent: {},
  structureHint: '',
  agent2Summary: '',

  setDomain: (d) => set({ domain: d }),
  setGithubUrl: (url) => set({ githubUrl: url }),
  setUploadedFiles: (files) => set({ uploadedFiles: files }),
  setArchImage: (f) => set({ archImage: f }),
  setVisualImage: (f) => set({ visualImage: f }),
  setUserMethodDesc: (desc) => set({ userMethodDesc: desc }),
  setAgentStatus: (agentId, status) =>
    set((s) => ({
      agents: {
        ...s.agents,
        [agentId]: { ...s.agents[agentId], ...status },
      },
    })),
  setReportFiles: (agentId, files) =>
    set((s) => ({ reportFiles: { ...s.reportFiles, [agentId]: files } })),
  setActiveReport: (agentId, filename) =>
    set((s) => ({ activeReport: { ...s.activeReport, [agentId]: filename } })),
  setReportContent: (filename, content) =>
    set((s) => ({ reportContent: { ...s.reportContent, [filename]: content } })),
  setStructureHint: (hint) => set({ structureHint: hint }),
  setAgent2Summary: (summary) => set({ agent2Summary: summary }),
}));
