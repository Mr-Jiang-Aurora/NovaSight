'use client';
import { useState } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import PipelineStatus from '@/components/pipeline/PipelineStatus';
import Agent1Panel from '@/components/agents/Agent1Panel';
import Agent2Panel from '@/components/agents/Agent2Panel';
import Agent3Panel from '@/components/agents/Agent3Panel';
import Agent4Panel from '@/components/agents/Agent4Panel';
import MasterPanel from '@/components/agents/MasterPanel';
import ReportViewer from '@/components/reports/ReportViewer';
import ClaudeStatusBanner from '@/components/pipeline/ClaudeStatusBanner';
import { usePipelineStore } from '@/store/pipelineStore';
import type { AgentId } from '@/types';

export default function WorkspacePage() {
  const [activeAgent, setActiveAgent] = useState<AgentId>('agent1');
  const { reportFiles, setActiveReport } = usePipelineStore();

  const handleViewReport = (agentId: AgentId) => {
    setActiveAgent(agentId);
    // 强制选中并加载最新报告（即使已经在同一 Agent 页面也生效）
    const files = reportFiles[agentId];
    if (files?.length > 0) {
      setActiveReport(agentId, files[0].name);
    }
  };

  const renderPanel = () => {
    switch (activeAgent) {
      case 'agent1': return <Agent1Panel onViewReport={() => handleViewReport('agent1')} />;
      case 'agent2': return <Agent2Panel onViewReport={() => handleViewReport('agent2')} />;
      case 'agent3': return <Agent3Panel onViewReport={() => handleViewReport('agent3')} />;
      case 'agent4': return <Agent4Panel onViewReport={() => handleViewReport('agent4')} />;
      case 'master': return <MasterPanel onViewReport={() => handleViewReport('master')} />;

      default:       return null;
    }
  };

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#0f0f0f' }}>
      {/* Sidebar */}
      <Sidebar active={activeAgent} onChange={setActiveAgent} />

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Claude API 状态警告条 */}
        <ClaudeStatusBanner />
        {/* Top status bar */}
        <PipelineStatus />

        {/* Content: control panel + report viewer */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left panel — responsive: 25% of viewport, min 280px, max 420px */}
          <div
            className="flex-shrink-0 border-r overflow-hidden"
            style={{
              width: 'clamp(280px, 25vw, 420px)',
              borderColor: '#2a2a2a',
            }}
          >
            {renderPanel()}
          </div>

          {/* Right report viewer — takes all remaining space */}
          <div className="flex-1 min-w-0 overflow-hidden">
            <ReportViewer agentId={activeAgent} />
          </div>
        </div>
      </div>
    </div>
  );
}
