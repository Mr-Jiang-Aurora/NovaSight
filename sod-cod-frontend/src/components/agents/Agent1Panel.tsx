'use client';
import { useState } from 'react';
import { Search, CheckCircle2, Circle, Loader2, ChevronRight } from 'lucide-react';
import { usePipelineStore } from '@/store/pipelineStore';
import { useAgentRunner } from '@/hooks/useAgentRunner';

interface Agent1PanelProps {
  onViewReport: () => void;
}

export default function Agent1Panel({ onViewReport }: Agent1PanelProps) {
  const { domain, setDomain, agents } = usePipelineStore();
  const { runAgent1 } = useAgentRunner();
  const state = agents.agent1;

  const [startYear, setStartYear] = useState(2024);
  const [endYear, setEndYear] = useState(2025);
  const [tiers, setTiers] = useState<string[]>(['CCF-A', 'SCI Q1']);

  const tierOptions = ['CCF-A', 'CCF-B', 'SCI Q1', 'SCI Q2'];

  const toggleTier = (t: string) =>
    setTiers(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]);

  const phases = [
    { label: 'Phase 1: 多源搜索', done: state.progress >= 50 },
    { label: 'Phase 2: PDF 获取', done: state.progress >= 65 },
    { label: 'Phase 3: 表格解析', done: state.progress >= 80 },
    { label: 'Phase 4: 论文信息卡片', done: state.progress >= 100 },
  ];

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Search size={16} style={{ color: '#3b82f6' }} />
        <span className="text-sm font-semibold" style={{ color: '#e8e6df' }}>SOTA 调研</span>
        <span className="ml-auto text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(59,130,246,0.1)', color: '#3b82f6' }}>
          Agent 1
        </span>
      </div>

      {/* Domain */}
      <div>
        <label className="text-xs mb-2 block" style={{ color: '#888780' }}>研究领域</label>
        <div className="flex gap-2">
          {['COD', 'SOD'].map(d => (
            <button
              key={d}
              onClick={() => setDomain(d)}
              className="px-4 py-1.5 text-sm rounded transition-colors"
              style={{
                background: domain === d ? 'rgba(200,181,96,0.12)' : '#1a1a1a',
                color: domain === d ? '#c8b560' : '#888780',
                border: `0.5px solid ${domain === d ? '#c8b560' : '#2a2a2a'}`,
                borderBottom: domain === d ? '2px solid #c8b560' : '0.5px solid #2a2a2a',
              }}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      {/* Year range */}
      <div>
        <label className="text-xs mb-2 block" style={{ color: '#888780' }}>年份范围</label>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={startYear}
            onChange={e => setStartYear(Number(e.target.value))}
            className="w-20 px-2 py-1.5 text-sm rounded text-center"
            style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#e8e6df' }}
          />
          <span style={{ color: '#555450' }}>→</span>
          <input
            type="number"
            value={endYear}
            onChange={e => setEndYear(Number(e.target.value))}
            className="w-20 px-2 py-1.5 text-sm rounded text-center"
            style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#e8e6df' }}
          />
        </div>
      </div>

      {/* Tier filter */}
      <div>
        <label className="text-xs mb-2 block" style={{ color: '#888780' }}>期刊级别</label>
        <div className="flex flex-wrap gap-2">
          {tierOptions.map(t => (
            <button
              key={t}
              onClick={() => toggleTier(t)}
              className="px-2 py-1 text-xs rounded transition-colors"
              style={{
                background: tiers.includes(t) ? 'rgba(200,181,96,0.12)' : '#1a1a1a',
                color: tiers.includes(t) ? '#c8b560' : '#555450',
                border: `0.5px solid ${tiers.includes(t) ? '#c8b560' : '#2a2a2a'}`,
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => runAgent1({ useCache: true })}
          disabled={state.status === 'running'}
          className="flex-1 py-2 text-sm rounded transition-colors"
          style={{ background: '#1a1a1a', color: '#888780', border: '0.5px solid #2a2a2a' }}
        >
          从缓存加载
        </button>
        <button
          onClick={() => runAgent1({ useCache: false, startYear, endYear })}
          disabled={state.status === 'running'}
          className="flex-1 py-2 text-sm rounded font-medium transition-colors"
          style={{
            background: state.status === 'running' ? '#2a2a2a' : '#c8b560',
            color: state.status === 'running' ? '#555450' : '#0f0f0f',
            border: 'none',
          }}
        >
          {state.status === 'running' ? '搜索中...' : '开始搜索'}
        </button>
      </div>

      {/* Progress phases */}
      {(state.status === 'running' || state.status === 'success') && (
        <div className="rounded p-3" style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}>
          <div className="space-y-2">
            {phases.map((phase, i) => {
              const isActive = state.status === 'running' && !phase.done && (i === 0 || phases[i - 1].done);
              return (
                <div key={i} className="flex items-center gap-2">
                  {phase.done ? (
                    <CheckCircle2 size={13} style={{ color: '#10b981' }} />
                  ) : isActive ? (
                    <Loader2 size={13} className="animate-spin" style={{ color: '#c8b560' }} />
                  ) : (
                    <Circle size={13} style={{ color: '#555450' }} />
                  )}
                  <span className="text-xs" style={{ color: phase.done ? '#c2c0b6' : isActive ? '#c8b560' : '#555450' }}>
                    {phase.label}
                  </span>
                  {isActive && (
                    <span className="ml-auto text-xs" style={{ color: '#c8b560' }}>
                      {state.progress}%
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          {state.currentStep && (
            <div className="mt-2 text-xs truncate" style={{ color: '#888780' }}>{state.currentStep}</div>
          )}
        </div>
      )}

      {/* Error */}
      {state.status === 'error' && (
        <div className="rounded p-3 text-xs" style={{ background: 'rgba(239,68,68,0.08)', border: '0.5px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>
          {state.error}
        </div>
      )}

      {/* Success summary */}
      {state.status === 'success' && (
        <div className="rounded p-3" style={{ background: 'rgba(16,185,129,0.06)', border: '0.5px solid rgba(16,185,129,0.2)' }}>
          <div className="text-xs mb-2" style={{ color: '#10b981' }}>{state.currentStep}</div>
          <button
            onClick={onViewReport}
            className="flex items-center gap-1 text-xs"
            style={{ color: '#c8b560' }}
          >
            查看完整报告 <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
