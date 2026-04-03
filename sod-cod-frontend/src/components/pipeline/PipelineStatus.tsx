'use client';
import { usePipelineStore } from '@/store/pipelineStore';
import { CheckCircle2, XCircle, Clock, Loader2 } from 'lucide-react';

const AGENT_LABELS: Record<string, string> = {
  agent1: 'A1', agent2: 'A2', agent3: 'A3', agent4: 'A4',
};

export default function PipelineStatus() {
  const { agents } = usePipelineStore();

  const runningAgent = Object.entries(agents).find(([, s]) => s.status === 'running');
  const hasRunning = !!runningAgent;

  const allDone = ['agent1', 'agent2', 'agent3', 'agent4'].every(
    id => agents[id]?.status === 'success' || agents[id]?.status === 'skipped'
  );

  const progress = runningAgent ? runningAgent[1].progress : (allDone ? 100 : 0);

  return (
    <div
      className="flex items-center h-11 px-4 border-b flex-shrink-0 gap-4"
      style={{ background: '#0f0f0f', borderColor: '#2a2a2a' }}
    >
      {/* Progress bar (1px, top edge) */}
      {hasRunning && (
        <div
          className="absolute top-0 left-0 h-[1px] transition-all duration-500"
          style={{ width: `${progress}%`, background: '#c8b560' }}
        />
      )}

      {/* Status indicator */}
      <div className="flex items-center gap-2">
        {hasRunning ? (
          <>
            <Loader2 size={12} className="animate-spin" style={{ color: '#c8b560' }} />
            <span className="text-xs" style={{ color: '#c8b560' }}>运行中</span>
          </>
        ) : allDone ? (
          <>
            <CheckCircle2 size={12} style={{ color: '#10b981' }} />
            <span className="text-xs" style={{ color: '#10b981' }}>完成</span>
          </>
        ) : (
          <>
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: '#555450' }} />
            <span className="text-xs" style={{ color: '#555450' }}>就绪</span>
          </>
        )}
      </div>

      {/* Current step */}
      {runningAgent && (
        <span className="text-xs flex-1 truncate" style={{ color: '#888780' }}>
          {runningAgent[1].currentStep}
        </span>
      )}

      {/* Agent status badges */}
      <div className="flex items-center gap-2 ml-auto">
        {['agent1', 'agent2', 'agent3', 'agent4'].map(id => {
          const s = agents[id]?.status;
          return (
            <div key={id} className="flex items-center gap-1">
              <span className="text-xs" style={{ color: '#555450' }}>{AGENT_LABELS[id]}</span>
              {s === 'success' ? (
                <CheckCircle2 size={11} style={{ color: '#10b981' }} />
              ) : s === 'error' ? (
                <XCircle size={11} style={{ color: '#ef4444' }} />
              ) : s === 'running' ? (
                <Loader2 size={11} className="animate-spin" style={{ color: '#c8b560' }} />
              ) : (
                <Clock size={11} style={{ color: '#555450' }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
