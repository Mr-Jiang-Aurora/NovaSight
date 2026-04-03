'use client';
import { useState } from 'react';
import { Search, BarChart2, Code2, Image, Cpu, Settings, Info, GitBranch } from 'lucide-react';
import type { AgentId } from '@/types';
import { AGENT_LABELS } from '@/types';
import { usePipelineStore } from '@/store/pipelineStore';
import { AGENT_COLORS } from '@/types';

const navItems = [
  { id: 'agent1' as AgentId, icon: Search,    color: '#3b82f6' },
  { id: 'agent2' as AgentId, icon: BarChart2, color: '#10b981' },
  { id: 'agent3' as AgentId, icon: Code2,     color: '#f59e0b' },
  { id: 'agent4' as AgentId, icon: Image,     color: '#8b5cf6' },
  { id: 'master' as AgentId, icon: Cpu,       color: '#c8b560' },
];

interface SidebarProps {
  active: AgentId;
  onChange: (id: AgentId) => void;
}

export default function Sidebar({ active, onChange }: SidebarProps) {
  const [hovered, setHovered] = useState(false);
  const { agents } = usePipelineStore();

  const getStatusDot = (id: string) => {
    const s = agents[id]?.status;
    if (s === 'running') return '#c8b560';
    if (s === 'success') return '#10b981';
    if (s === 'error') return '#ef4444';
    return 'transparent';
  };

  return (
    <div
      className="relative flex flex-col h-screen border-r transition-all duration-200 ease-in-out flex-shrink-0 z-10"
      style={{
        width: hovered ? '200px' : '60px',
        background: '#0f0f0f',
        borderColor: '#2a2a2a',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Logo area */}
      <div className="flex items-center h-14 px-4 border-b" style={{ borderColor: '#2a2a2a' }}>
        <div
          className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0 text-xs font-bold"
          style={{ background: '#c8b560', color: '#0f0f0f' }}
        >
          RC
        </div>
        {hovered && (
          <span className="ml-3 text-sm font-semibold whitespace-nowrap overflow-hidden" style={{ color: '#e8e6df' }}>
            Research Agent
          </span>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex flex-col pt-2 flex-1">
        {navItems.map(({ id, icon: Icon, color }) => {
          const isActive = active === id;
          const dotColor = getStatusDot(id);
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className="relative flex items-center px-4 py-3 cursor-pointer transition-colors duration-150 text-left"
              style={{
                background: isActive ? `rgba(${hexToRgb(color)}, 0.08)` : 'transparent',
                borderLeft: isActive ? `2px solid ${color}` : '2px solid transparent',
              }}
            >
              <div className="relative flex-shrink-0">
                <Icon size={18} style={{ color: isActive ? color : '#888780' }} />
                {dotColor !== 'transparent' && (
                  <span
                    className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full"
                    style={{ background: dotColor }}
                  />
                )}
              </div>
              {hovered && (
                <span
                  className="ml-3 text-sm whitespace-nowrap overflow-hidden"
                  style={{ color: isActive ? '#e8e6df' : '#888780' }}
                >
                  {AGENT_LABELS[id]}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom icons */}
      <div className="border-t pb-2" style={{ borderColor: '#2a2a2a' }}>
        {/* 数据流演示入口 */}
        <a
          href="/pipeline"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center px-4 py-3 w-full transition-colors duration-150 hover:bg-white/5"
          style={{ color: '#c8b560', textDecoration: 'none' }}
          title="数据流演示 / Pipeline Demo"
        >
          <GitBranch size={16} />
          {hovered && (
            <span className="ml-3 text-sm whitespace-nowrap">数据流演示</span>
          )}
        </a>
        <button className="flex items-center px-4 py-3 w-full" style={{ color: '#555450' }}>
          <Settings size={16} />
          {hovered && <span className="ml-3 text-sm">设置</span>}
        </button>
        <button className="flex items-center px-4 py-2 w-full" style={{ color: '#555450' }}>
          <Info size={16} />
          {hovered && <span className="ml-3 text-sm">关于</span>}
        </button>
      </div>
    </div>
  );
}

function hexToRgb(hex: string) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r}, ${g}, ${b}`;
}
