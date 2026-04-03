'use client';
import { useState } from 'react';
import { BarChart2, ChevronDown, ChevronUp, ChevronRight, Loader2 } from 'lucide-react';
import { usePipelineStore } from '@/store/pipelineStore';
import { useAgentRunner } from '@/hooks/useAgentRunner';

interface Agent2PanelProps {
  onViewReport: () => void;
}

export default function Agent2Panel({ onViewReport }: Agent2PanelProps) {
  const { userMethodDesc, setUserMethodDesc, agents } = usePipelineStore();
  const { runAgent2 } = useAgentRunner();
  const state = agents.agent2;
  const [manualOpen, setManualOpen] = useState(false);

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <BarChart2 size={16} style={{ color: '#10b981' }} />
        <span className="text-sm font-semibold" style={{ color: '#e8e6df' }}>指标诊断</span>
        <span className="ml-auto text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(16,185,129,0.1)', color: '#10b981' }}>
          Agent 2
        </span>
      </div>

      {/* Auto note */}
      <div className="text-xs p-3 rounded" style={{ background: '#1a1a1a', color: '#888780', border: '0.5px solid #2a2a2a' }}>
        Agent2 自动读取 Agent1 的搜索结果，无需额外输入。
      </div>

      {/* User method desc */}
      <div>
        <label className="text-xs mb-2 block" style={{ color: '#888780' }}>当前研究方案描述（可选）</label>
        <textarea
          value={userMethodDesc}
          onChange={e => setUserMethodDesc(e.target.value)}
          placeholder="描述你的模型架构（可选，填写后报告会包含针对性建议）&#10;例：基于 Mamba 骨干网络的 COD 方法，引入判别器驱动的自适应路由模块"
          rows={4}
          className="w-full px-3 py-2 text-xs rounded resize-none"
          style={{
            background: '#1a1a1a',
            border: '0.5px solid #2a2a2a',
            color: '#c2c0b6',
            outline: 'none',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        />
      </div>

      {/* Manual supplement (collapsible) */}
      <div className="rounded overflow-hidden" style={{ border: '0.5px solid #2a2a2a' }}>
        <button
          onClick={() => setManualOpen(!manualOpen)}
          className="flex items-center justify-between w-full px-3 py-2 text-xs"
          style={{ background: '#1a1a1a', color: '#888780' }}
        >
          <span>▶ 手动补录论文分数</span>
          {manualOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
        {manualOpen && (
          <div className="p-3 text-xs" style={{ background: '#161616', color: '#555450' }}>
            <p className="mb-2">如有无法自动提取的论文数据，可在此手动输入</p>
            <button
              className="px-3 py-1.5 rounded text-xs"
              style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#888780' }}
            >
              上传 Excel 文件
            </button>
          </div>
        )}
      </div>

      {/* Run button */}
      <button
        onClick={runAgent2}
        disabled={state.status === 'running'}
        className="w-full py-2 text-sm rounded font-medium transition-colors"
        style={{
          background: state.status === 'running' ? '#2a2a2a' : '#c8b560',
          color: state.status === 'running' ? '#555450' : '#0f0f0f',
          border: 'none',
        }}
      >
        {state.status === 'running' ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 size={13} className="animate-spin" /> 诊断中...
          </span>
        ) : '运行指标诊断'}
      </button>

      {/* Progress */}
      {state.status === 'running' && (
        <div className="rounded p-3" style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs" style={{ color: '#888780' }}>{state.currentStep}</span>
            <span className="text-xs" style={{ color: '#c8b560' }}>{state.progress}%</span>
          </div>
          <div className="h-0.5 rounded" style={{ background: '#2a2a2a' }}>
            <div
              className="h-full rounded transition-all duration-500"
              style={{ width: `${state.progress}%`, background: '#c8b560' }}
            />
          </div>
        </div>
      )}

      {/* Error */}
      {state.status === 'error' && (
        <div className="rounded p-3 text-xs" style={{ background: 'rgba(239,68,68,0.08)', border: '0.5px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>
          {state.error}
        </div>
      )}

      {/* Success */}
      {state.status === 'success' && (
        <div className="rounded p-3" style={{ background: 'rgba(16,185,129,0.06)', border: '0.5px solid rgba(16,185,129,0.2)' }}>
          <div className="text-xs mb-2" style={{ color: '#10b981' }}>{state.currentStep}</div>
          <button
            onClick={onViewReport}
            className="flex items-center gap-1 text-xs"
            style={{ color: '#c8b560' }}
          >
            查看完整 6 章节报告 <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
