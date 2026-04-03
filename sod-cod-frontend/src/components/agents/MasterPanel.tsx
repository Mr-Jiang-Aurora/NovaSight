'use client';
import { Cpu, Loader2, CheckCircle2, ChevronRight } from 'lucide-react';
import { usePipelineStore } from '@/store/pipelineStore';
import { useAgentRunner } from '@/hooks/useAgentRunner';

interface MasterPanelProps {
  onViewReport: () => void;
}

export default function MasterPanel({ onViewReport }: MasterPanelProps) {
  const { agents, githubUrl, uploadedFiles, archImage, visualImage } = usePipelineStore();
  const { runAgent1, runAgent2, runMaster } = useAgentRunner();
  const state = agents.master;

  const hasCode = !!githubUrl || uploadedFiles.length > 0;
  const hasImage = !!archImage || !!visualImage;

  const agentItems = [
    { id: 'agent1', label: 'Agent1 — SOTA 调研（读取缓存或重新搜索）', always: true },
    { id: 'agent2', label: 'Agent2 — 指标诊断', always: true },
    { id: 'agent3', label: 'Agent3 — 代码分析', extra: '需要输入 GitHub 链接或上传代码', active: hasCode },
    { id: 'agent4', label: 'Agent4 — 图像分析', extra: '需要上传图片', active: hasImage },
  ];

  const timeEstimates = [
    { label: '仅 A1+A2', time: '约 3-5 分钟' },
    { label: '含 A3 (GitHub)', time: '约 10-15 分钟' },
    { label: '完整流程', time: '约 15-20 分钟' },
  ];

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Cpu size={16} style={{ color: '#c8b560' }} />
        <span className="text-sm font-semibold" style={{ color: '#e8e6df' }}>主控输出</span>
        <span className="ml-auto text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(200,181,96,0.1)', color: '#c8b560' }}>
          Master
        </span>
      </div>

      {/* Run config */}
      <div className="rounded p-3 space-y-2" style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}>
        <div className="text-xs mb-2" style={{ color: '#888780' }}>运行配置</div>
        {agentItems.map(({ id, label, extra, always, active }) => {
          const checked = always || active;
          const status = agents[id]?.status;
          return (
            <div key={id} className="flex items-start gap-2">
              <span className="mt-0.5">
                {status === 'success' ? (
                  <CheckCircle2 size={13} style={{ color: '#10b981' }} />
                ) : (
                  <span
                    className="inline-block w-3.5 h-3.5 rounded border flex items-center justify-center"
                    style={{ borderColor: checked ? '#c8b560' : '#2a2a2a', background: checked ? 'rgba(200,181,96,0.12)' : 'transparent' }}
                  >
                    {checked && <span className="block w-1.5 h-1.5 rounded-sm" style={{ background: '#c8b560' }} />}
                  </span>
                )}
              </span>
              <div>
                <span className="text-xs" style={{ color: checked ? '#c2c0b6' : '#555450' }}>{label}</span>
                {extra && !active && (
                  <div className="text-xs mt-0.5" style={{ color: '#3d3d3a' }}>[{extra}]</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Master run progress */}
      {state.status === 'running' && (
        <div className="rounded p-3" style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}>
          <div className="flex justify-between mb-2">
            <span className="text-xs truncate pr-2" style={{ color: '#888780' }}>{state.currentStep}</span>
            <span className="text-xs flex-shrink-0" style={{ color: '#c8b560' }}>{state.progress}%</span>
          </div>
          <div className="h-1 rounded" style={{ background: '#2a2a2a' }}>
            <div className="h-full rounded transition-all duration-500" style={{ width: `${state.progress}%`, background: 'linear-gradient(90deg, #c8b560, #e8d070)' }} />
          </div>
          <div className="mt-2 space-y-1">
            {Object.entries(agents).filter(([id]) => id !== 'master').map(([id, s]) => (
              <div key={id} className="flex items-center gap-2 text-xs" style={{ color: '#555450' }}>
                {s.status === 'running' ? <Loader2 size={10} className="animate-spin" style={{ color: '#c8b560' }} />
                  : s.status === 'success' ? <CheckCircle2 size={10} style={{ color: '#10b981' }} />
                  : <span className="w-2.5 h-2.5 rounded-full inline-block border" style={{ borderColor: '#3a3a3a' }} />}
                <span>{id.toUpperCase()}</span>
                {s.status === 'running' && <span style={{ color: '#888780' }}>{s.currentStep.slice(0, 30)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Buttons */}
      <div className="flex flex-col gap-2">
        <button
          onClick={runMaster}
          disabled={state.status === 'running'}
          className="w-full py-2.5 text-sm rounded font-semibold"
          style={{
            background: state.status === 'running' ? '#2a2a2a' : '#c8b560',
            color: state.status === 'running' ? '#555450' : '#0f0f0f',
            border: 'none',
          }}
        >
          {state.status === 'running' ? (
            <span className="flex items-center justify-center gap-2"><Loader2 size={14} className="animate-spin" /> 全流程运行中...</span>
          ) : '运行完整流程'}
        </button>
        <button
          onClick={async () => {
            // 必须顺序执行：Agent2 依赖 Agent1 的缓存
            await runAgent1({ useCache: true });
            await runAgent2();
          }}
          disabled={state.status === 'running'}
          className="w-full py-2 text-sm rounded"
          style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#888780' }}
        >
          仅跑 Agent1+2
        </button>
      </div>

      {/* Time estimates */}
      <div className="rounded p-3" style={{ background: '#161616', border: '0.5px solid #222' }}>
        <div className="text-xs mb-2" style={{ color: '#555450' }}>预计用时</div>
        {timeEstimates.map(({ label, time }) => (
          <div key={label} className="flex justify-between text-xs py-0.5">
            <span style={{ color: '#3d3d3a' }}>{label}</span>
            <span style={{ color: '#555450' }}>{time}</span>
          </div>
        ))}
      </div>

      {/* Error */}
      {state.status === 'error' && (
        <div className="rounded p-3 text-xs" style={{ background: 'rgba(239,68,68,0.08)', border: '0.5px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>
          {state.error}
        </div>
      )}

      {/* Success */}
      {state.status === 'success' && (
        <div className="rounded p-3" style={{ background: 'rgba(200,181,96,0.06)', border: '0.5px solid rgba(200,181,96,0.2)' }}>
          <div className="text-xs mb-2" style={{ color: '#c8b560' }}>全部完成 — 综合报告已生成</div>
          <button onClick={onViewReport} className="flex items-center gap-1 text-xs" style={{ color: '#c8b560' }}>
            查看综合报告 <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
