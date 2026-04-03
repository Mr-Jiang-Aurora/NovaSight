'use client';
import {
  useEffect, useRef, useState, useMemo, useCallback,
} from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  RefreshCw, FileText, ChevronDown,
  GitBranch, Microscope, Search, Layers,
} from 'lucide-react';
import { useReports } from '@/hooks/useReports';
import type { AgentId, ReportFile } from '@/types';

interface ReportViewerProps { agentId: AgentId; }

// ── 工具函数 ──────────────────────────────────────────────────────────

function slugify(text: string) {
  return String(text).toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-').replace(/(^-|-$)/g, '');
}

function extractSections(md: string) {
  return md.split('\n')
    .filter(l => l.startsWith('## '))
    .map(l => ({ title: l.replace(/^##\s+/, ''), id: slugify(l.replace(/^##\s+/, '')) }));
}

function formatDate(isoStr: string) {
  try {
    const d = new Date(isoStr);
    const isToday = d.toDateString() === new Date().toDateString();
    const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    if (isToday) return `今天 ${time}`;
    return `${d.getMonth() + 1}/${d.getDate()} ${time}`;
  } catch { return isoStr; }
}

// ── Agent 色系 ──────────────────────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  agent1: '#3b82f6', agent2: '#10b981', agent3: '#f59e0b',
  agent4: '#8b5cf6', master: '#c8b560',
};
const AGENT_LABELS: Record<string, string> = {
  agent1: 'AGENT1 · SOTA 调研',   agent2: 'AGENT2 · 指标诊断',
  agent3: 'AGENT3 · 代码分析',    agent4: 'AGENT4 · 图像分析',
  master: 'MASTER · 综合报告',
};
function hexToRgb(hex: string) {
  return `${parseInt(hex.slice(1, 3), 16)}, ${parseInt(hex.slice(3, 5), 16)}, ${parseInt(hex.slice(5, 7), 16)}`;
}

// ── Agent4 分类 ───────────────────────────────────────────────────────

type Agent4ReportType = 'arch_analysis' | 'figure_trace' | 'arch_validation' | 'innovation';
const AGENT4_TABS: Array<{
  type: Agent4ReportType; label: string;
  icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }>;
  color: string; desc: string;
}> = [
  { type: 'arch_analysis',   label: '架构图分析',    icon: Layers,     color: '#8b5cf6', desc: 'Claude 六维度解析架构图' },
  { type: 'figure_trace',    label: 'Figure 溯源',   icon: Search,     color: '#3b82f6', desc: '自动溯源论文出处' },
  { type: 'arch_validation', label: '架构-代码验证', icon: GitBranch,  color: '#f59e0b', desc: '架构图与代码双向比对' },
  { type: 'innovation',      label: '创新性评估',    icon: Microscope, color: '#10b981', desc: '五维度学术创新分析' },
];

// ── 滚动位置记忆（模块级 Map，会话内保持） ─────────────────────────────
const scrollPositions = new Map<string, number>();

// ── 自定义滚动条组件 ──────────────────────────────────────────────────

function CustomScrollbar({
  scrollRef, color,
}: {
  scrollRef: React.RefObject<HTMLDivElement | null>;
  color: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [thumbTop, setThumbTop] = useState(0);
  const [thumbHeight, setThumbHeight] = useState(60);
  const [visible, setVisible] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef({ startY: 0, startScroll: 0 });

  const updateThumb = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const viewH = el.clientHeight;
    const scrollH = el.scrollHeight;
    if (scrollH <= viewH + 1) { setVisible(false); return; }
    setVisible(true);
    const th = Math.max(28, viewH * (viewH / scrollH));
    const maxScroll = scrollH - viewH;
    const ratio = maxScroll > 0 ? el.scrollTop / maxScroll : 0;
    setThumbHeight(th);
    setThumbTop(ratio * (viewH - th));
  }, [scrollRef]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.addEventListener('scroll', updateThumb, { passive: true });
    const ro = new ResizeObserver(updateThumb);
    ro.observe(el);
    updateThumb();
    return () => { el.removeEventListener('scroll', updateThumb); ro.disconnect(); };
  }, [scrollRef, updateThumb]);

  const handleTrackClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = scrollRef.current;
    const track = trackRef.current;
    if (!el || !track) return;
    const rect = track.getBoundingClientRect();
    const clickY = e.clientY - rect.top;
    const ratio = Math.max(0, Math.min(1, (clickY - thumbHeight / 2) / (rect.height - thumbHeight)));
    el.scrollTop = ratio * (el.scrollHeight - el.clientHeight);
  }, [scrollRef, thumbHeight]);

  const handleThumbMouseDown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    dragRef.current = { startY: e.clientY, startScroll: scrollRef.current?.scrollTop ?? 0 };
    setIsDragging(true);
  }, [scrollRef]);

  useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: MouseEvent) => {
      const el = scrollRef.current;
      const track = trackRef.current;
      if (!el || !track) return;
      const dy = e.clientY - dragRef.current.startY;
      const ratio = dy / (track.clientHeight - thumbHeight);
      el.scrollTop = dragRef.current.startScroll + ratio * (el.scrollHeight - el.clientHeight);
    };
    const onUp = () => setIsDragging(false);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    return () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
  }, [isDragging, scrollRef, thumbHeight]);

  if (!visible) return null;
  return (
    <div
      ref={trackRef}
      onClick={handleTrackClick}
      className="flex-shrink-0 relative select-none"
      style={{ width: 7, background: '#141414', cursor: 'pointer', borderLeft: '0.5px solid #1f1f1f' }}
    >
      <div
        onMouseDown={handleThumbMouseDown}
        style={{
          position: 'absolute', top: thumbTop, left: 1,
          width: 'calc(100% - 2px)', height: thumbHeight,
          borderRadius: 4,
          background: isDragging ? color : `${color}50`,
          cursor: isDragging ? 'grabbing' : 'grab',
          transition: isDragging ? 'none' : 'background 0.15s',
          userSelect: 'none',
        }}
      />
    </div>
  );
}

// ── Markdown 内容 + 章节导航 + 滚动条 ────────────────────────────────

function MarkdownContent({
  content, color, memoryKey,
}: {
  content: string; color: string; memoryKey: string;
}) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [activeSection, setActiveSection] = useState('');
  const [clickedSection, setClickedSection] = useState('');
  const sections = useMemo(() => extractSections(content), [content]);

  // ── 恢复上次滚动位置
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const saved = scrollPositions.get(memoryKey) ?? 0;
    // 等 DOM 渲染完再恢复
    requestAnimationFrame(() => {
      if (contentRef.current) contentRef.current.scrollTop = saved;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memoryKey]);

  // ── 保存滚动位置
  const handleScroll = useCallback(() => {
    if (contentRef.current) {
      scrollPositions.set(memoryKey, contentRef.current.scrollTop);
    }
  }, [memoryKey]);

  // ── IntersectionObserver：滚动时自动高亮章节
  useEffect(() => {
    const el = contentRef.current;
    if (!el || sections.length === 0) return;
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(e => { if (e.isIntersecting) setActiveSection(e.target.id); });
      },
      { root: el, rootMargin: '-8% 0px -55% 0px' }
    );
    el.querySelectorAll('h2[id]').forEach(h => observer.observe(h));
    return () => observer.disconnect();
  }, [content, sections]);

  // ── 点击章节
  const scrollToSection = useCallback((id: string) => {
    const target = contentRef.current?.querySelector(`#${CSS.escape(id)}`);
    if (target) {
      // 手动计算滚动位置，避免 scrollIntoView 不精确
      const elTop = (target as HTMLElement).offsetTop;
      if (contentRef.current) contentRef.current.scrollTo({ top: elTop - 16, behavior: 'smooth' });
    }
    setActiveSection(id);
    // 点击反馈：亮色闪烁 500ms
    setClickedSection(id);
    setTimeout(() => setClickedSection(c => c === id ? '' : c), 500);
  }, []);

  return (
    <div className="flex flex-1 overflow-hidden min-h-0">
      {/* ── 左侧章节导航 ── */}
      {sections.length > 0 && (
        <div
          className="w-44 flex-shrink-0 border-r overflow-y-auto py-3 px-2 no-scrollbar"
          style={{ borderColor: '#2a2a2a' }}
        >
          <div className="text-xs mb-2 px-2" style={{ color: '#3d3d3a' }}>章节</div>
          {sections.map(({ title, id }) => {
            const isActive = activeSection === id;
            const isClicked = clickedSection === id;
            return (
              <button
                key={id}
                onClick={() => scrollToSection(id)}
                className="block w-full text-left px-2 py-1.5 rounded text-xs mb-0.5"
                style={{
                  color: isActive ? '#e8e6df' : '#888780',
                  background: isClicked
                    ? `rgba(${hexToRgb(color)}, 0.35)`  // 点击时明亮闪光
                    : isActive
                      ? `rgba(${hexToRgb(color)}, 0.10)`
                      : 'transparent',
                  borderLeft: isActive ? `2px solid ${color}` : '2px solid transparent',
                  transform: isActive ? 'translateX(2px)' : 'translateX(0)',
                  transition: 'all 0.15s ease',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={title}
              >
                {title}
              </button>
            );
          })}
        </div>
      )}

      {/* ── 内容区 + 自定义滚动条 ── */}
      <div className="flex flex-1 overflow-hidden min-h-0 min-w-0">
        <div
          ref={contentRef}
          className="flex-1 overflow-y-scroll no-scrollbar"
          onScroll={handleScroll}
        >
          <div className="md-content px-6 py-4" style={{ maxWidth: '100%' }}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => <h1 id={slugify(String(children))}>{children}</h1>,
                h2: ({ children }) => <h2 id={slugify(String(children))}>{children}</h2>,
                h3: ({ children }) => <h3 id={slugify(String(children))}>{children}</h3>,
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                ),
                table: ({ children }) => (
                  <div style={{ overflowX: 'auto' }}><table>{children}</table></div>
                ),
                code: ({ className, children, ...props }) => (
                  <code className={className} {...props}>{children}</code>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        </div>
        {/* 自定义滚动条 */}
        <CustomScrollbar scrollRef={contentRef} color={color} />
      </div>
    </div>
  );
}

// ── 报告文件下拉列表 ───────────────────────────────────────────────────

function FileDropdown({
  files, activeFilename, onSelect, onClose,
}: {
  files: ReportFile[];
  activeFilename: string;
  onSelect: (f: ReportFile) => void;
  onClose: () => void;
}) {
  return (
    <div
      className="absolute top-full left-0 mt-1 rounded z-20 overflow-y-auto no-scrollbar"
      style={{
        background: '#1a1a1a', border: '0.5px solid #3a3a3a',
        minWidth: 340, maxHeight: 220,
      }}
      onMouseLeave={onClose}
    >
      {files.length === 0 ? (
        <div className="px-3 py-3 text-xs" style={{ color: '#555450' }}>暂无报告</div>
      ) : files.map(f => (
        <button
          key={f.name}
          onClick={() => { onSelect(f); onClose(); }}
          className="flex items-center justify-between w-full px-3 py-2 text-xs gap-2"
          style={{
            color: f.name === activeFilename ? '#e8e6df' : '#888780',
            background: f.name === activeFilename ? '#222' : 'transparent',
          }}
        >
          <span className="truncate flex-1 text-left" title={f.name}>{f.name}</span>
          <span className="flex-shrink-0 font-mono text-right whitespace-nowrap" style={{ color: '#555450', fontSize: '0.68rem' }}>
            {formatDate(f.modified)}
          </span>
        </button>
      ))}
    </div>
  );
}

// ── Agent4 分类标签页 ──────────────────────────────────────────────────

function Agent4Tabs({
  files, activeTab, onTabChange, activeFilename, onSelectFile,
}: {
  files: ReportFile[];
  activeTab: Agent4ReportType;
  onTabChange: (t: Agent4ReportType) => void;
  activeFilename: string;
  onSelectFile: (f: ReportFile) => void;
}) {
  const [showDropdown, setShowDropdown] = useState(false);

  const tabFiles = useMemo(
    () => files.filter(f => (f.report_type || 'other') === activeTab),
    [files, activeTab]
  );
  const tabCounts = useMemo(() => {
    const c: Record<string, number> = {};
    AGENT4_TABS.forEach(t => { c[t.type] = files.filter(f => (f.report_type || 'other') === t.type).length; });
    return c;
  }, [files]);

  const activeTabCfg = AGENT4_TABS.find(t => t.type === activeTab)!;
  const activeFileInTab = tabFiles.find(f => f.name === activeFilename);
  const displayName = activeFileInTab ? activeFilename : (tabFiles[0]?.name || '');

  return (
    <div className="flex flex-col flex-shrink-0">
      {/* 标签行 */}
      <div className="flex border-b" style={{ borderColor: '#2a2a2a' }}>
        {AGENT4_TABS.map(({ type, label, icon: Icon, color }) => {
          const isActive = activeTab === type;
          const count = tabCounts[type] || 0;
          return (
            <button
              key={type}
              onClick={() => onTabChange(type)}
              className="flex items-center gap-1.5 px-3 py-2 text-xs flex-1 justify-center transition-colors relative"
              style={{
                color: isActive ? color : '#555450',
                background: isActive ? `rgba(${hexToRgb(color)}, 0.06)` : 'transparent',
                borderBottom: isActive ? `2px solid ${color}` : '2px solid transparent',
              }}
              title={label}
            >
              <Icon size={12} style={{ color: isActive ? color : '#555450' }} />
              <span className="hidden sm:inline">{label}</span>
              {count > 0 && (
                <span className="text-xs px-1 rounded" style={{ background: `rgba(${hexToRgb(color)}, 0.15)`, color }}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* 子工具栏：图标 + 说明 + 文件选择器（放在左侧）*/}
      <div
        className="flex items-center gap-2 px-3 py-1.5 border-b"
        style={{ borderColor: '#2a2a2a', background: '#111' }}
      >
        {/* 文件选择器放左边，方便看完整时间 */}
        {tabFiles.length > 0 ? (
          <div className="relative flex-shrink-0">
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="flex items-center gap-1.5 px-2 py-1 rounded text-xs"
              style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#888780', maxWidth: 260 }}
            >
              <FileText size={10} />
              <span className="truncate" style={{ maxWidth: 180 }}>{displayName || '选择报告'}</span>
              <ChevronDown size={9} />
            </button>
            {showDropdown && (
              <FileDropdown
                files={tabFiles}
                activeFilename={activeFilename}
                onSelect={onSelectFile}
                onClose={() => setShowDropdown(false)}
              />
            )}
          </div>
        ) : (
          <span className="text-xs" style={{ color: '#3d3d3a' }}>暂无此类报告</span>
        )}
        {/* 说明文字放右边 */}
        <div className="flex items-center gap-1.5 ml-auto">
          <activeTabCfg.icon size={11} style={{ color: activeTabCfg.color, flexShrink: 0 }} />
          <span className="text-xs hidden md:inline" style={{ color: '#555450' }}>{activeTabCfg.desc}</span>
        </div>
      </div>
    </div>
  );
}

// ── 标准文件选择器（独立组件，防止每次渲染重建类型） ────────────────────

function StandardSelector({
  activeFilename, files, showDropdown, onToggle, onSelect, onClose,
}: {
  activeFilename: string;
  files: ReportFile[];
  showDropdown: boolean;
  onToggle: () => void;
  onSelect: (f: ReportFile) => void;
  onClose: () => void;
}) {
  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="flex items-center gap-1.5 px-2 py-1 rounded text-xs"
        style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#888780' }}
      >
        <FileText size={11} />
        <span className="max-w-[220px] truncate">{activeFilename || '选择报告'}</span>
        <ChevronDown size={10} className="flex-shrink-0" />
      </button>
      {showDropdown && (
        <FileDropdown
          files={files}
          activeFilename={activeFilename}
          onSelect={onSelect}
          onClose={onClose}
        />
      )}
    </div>
  );
}

// ── 主组件 ─────────────────────────────────────────────────────────────

export default function ReportViewer({ agentId }: ReportViewerProps) {
  const {
    files, activeFilename, currentContent, isLoadingContent,
    loadReportList, selectReport,
  } = useReports(agentId);

  const [showDropdown, setShowDropdown] = useState(false);
  const [agent4Tab, setAgent4Tab] = useState<Agent4ReportType>('arch_analysis');

  const color = AGENT_COLORS[agentId] || '#c8b560';

  // 传给 MarkdownContent 的记忆 key = "agent:filename"
  const memoryKey = `${agentId}:${activeFilename}`;

  const wordCount = useMemo(() => {
    if (!currentContent) return 0;
    return currentContent.replace(/[#\-*`>[\]()!|]/g, '').replace(/\s+/g, '').length;
  }, [currentContent]);

  const activeFile = files.find(f => f.name === activeFilename);

  // Agent4 tab 切换时自动选中该类最新报告
  const handleAgent4TabChange = (tab: Agent4ReportType) => {
    setAgent4Tab(tab);
    const tabFiles = files.filter(f => (f.report_type || 'other') === tab);
    if (tabFiles.length > 0) selectReport(tabFiles[0]);
  };

  return (
    <div className="flex flex-col h-full" style={{ background: '#0f0f0f' }}>
      {/* ── 顶部工具栏 ── */}
      <div
        className="flex items-center gap-3 px-4 h-11 border-b flex-shrink-0"
        style={{ borderColor: '#2a2a2a' }}
      >
        <span className="text-xs font-mono font-semibold whitespace-nowrap" style={{ color }}>
          {AGENT_LABELS[agentId]}
        </span>
        {agentId !== 'agent4' && (
          <StandardSelector
            activeFilename={activeFilename}
            files={files}
            showDropdown={showDropdown}
            onToggle={() => setShowDropdown(v => !v)}
            onSelect={selectReport}
            onClose={() => setShowDropdown(false)}
          />
        )}

        <button
          onClick={loadReportList}
          className="p-1 rounded flex-shrink-0"
          style={{ color: '#555450' }}
          title="刷新报告列表"
        >
          <RefreshCw size={13} />
        </button>

        {activeFile && currentContent && (
          <div className="flex items-center gap-3 ml-auto text-xs flex-shrink-0" style={{ color: '#555450' }}>
            <span>{wordCount.toLocaleString()} 字</span>
            <span>{activeFile.size_kb} KB</span>
            <span className="hidden sm:inline">{formatDate(activeFile.modified)}</span>
          </div>
        )}
      </div>

      {/* ── Agent4 分类标签 ── */}
      {agentId === 'agent4' && (
        <Agent4Tabs
          files={files}
          activeTab={agent4Tab}
          onTabChange={handleAgent4TabChange}
          activeFilename={activeFilename}
          onSelectFile={selectReport}
        />
      )}

      {/* ── 内容区 ── */}
      {currentContent ? (
        <MarkdownContent content={currentContent} color={color} memoryKey={memoryKey} />
      ) : isLoadingContent ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <div
            className="w-10 h-10 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: `${color}40`, borderTopColor: color }}
          />
          <p className="text-xs" style={{ color: '#555450' }}>正在加载报告...</p>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center"
            style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}
          >
            <FileText size={28} style={{ color: '#3d3d3a' }} />
          </div>
          <div className="text-center">
            <p className="text-sm mb-1" style={{ color: '#555450' }}>
              {agentId === 'agent4'
                ? '上传图片并运行 Agent4 后，报告将在此处展示'
                : '运行对应 Agent 后，报告将在此处展示'}
            </p>
            {files.length > 0 && (
              <button
                onClick={() => selectReport(files[0])}
                className="text-xs mt-2 underline"
                style={{ color: '#c8b560' }}
              >
                加载最新报告 →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
