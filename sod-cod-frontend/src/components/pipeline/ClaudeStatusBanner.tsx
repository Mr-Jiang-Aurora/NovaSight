'use client';
import { useState, useEffect } from 'react';
import { CheckCircle, Loader, X, Zap, AlertTriangle, ChevronDown } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

type TestState = 'idle' | 'testing' | 'ok' | 'error';

interface ProviderInfo {
  provider: string;
  claude_configured: boolean;
  openai_configured: boolean;
  claude_model: string;
  openai_model: string;
}

interface TestResult {
  ok: boolean;
  latency_ms?: number;
  model?: string;
  error?: string;
}

export default function ClaudeStatusBanner() {
  const [info, setInfo]           = useState<ProviderInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [open, setOpen]           = useState(false);
  const [claudeTest, setClaudeTest] = useState<TestState>('idle');
  const [openaiTest, setOpenaiTest] = useState<TestState>('idle');
  const [claudeResult, setClaudeResult] = useState<TestResult | null>(null);
  const [openaiResult, setOpenaiResult] = useState<TestResult | null>(null);
  const [switching, setSwitching] = useState(false);

  // 首次加载获取当前提供商信息
  useEffect(() => {
    fetch(`${API}/ai/provider`)
      .then(r => r.json())
      .then((d: ProviderInfo) => setInfo(d))
      .catch(() => {});
  }, []);

  const switchProvider = async (p: string) => {
    setSwitching(true);
    try {
      await fetch(`${API}/ai/provider`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: p }),
      });
      setInfo(prev => prev ? { ...prev, provider: p } : prev);
    } finally {
      setSwitching(false);
    }
  };

  const testProvider = async (p: 'claude' | 'openai') => {
    const setState  = p === 'claude' ? setClaudeTest  : setOpenaiTest;
    const setResult = p === 'claude' ? setClaudeResult : setOpenaiResult;
    setState('testing');
    setResult(null);
    try {
      const r = await fetch(`${API}/ai/test/${p}`);
      const d: TestResult = await r.json();
      setResult(d);
      setState(d.ok ? 'ok' : 'error');
    } catch {
      setResult({ ok: false, error: '后端未启动' });
      setState('error');
    }
  };

  if (dismissed) return null;

  const activeProvider = info?.provider ?? '—';
  const activeLabel    = activeProvider === 'openai' ? 'OpenAI' : 'Claude';
  const activeModel    = activeProvider === 'openai' ? info?.openai_model : info?.claude_model;
  const activeColor    = activeProvider === 'openai' ? '#60a5fa' : '#a78bfa';

  return (
    <div style={{ borderBottom: '1px solid #1f1f1f', flexShrink: 0 }}>
      {/* ── 折叠头 ───────────────────────────────────────────── */}
      <div
        className="flex items-center gap-2 px-4 py-1 cursor-pointer select-none"
        onClick={() => setOpen(v => !v)}
        style={{ color: '#555450' }}
      >
        <Zap size={10} style={{ color: activeColor }} />
        <span className="text-xs" style={{ color: activeColor }}>
          {activeLabel}
        </span>
        {activeModel && (
          <span className="text-xs" style={{ color: '#3a3a3a' }}>{activeModel}</span>
        )}
        <button
          className="ml-auto"
          style={{ color: '#333' }}
          title="展开 AI 提供商设置"
        >
          <ChevronDown
            size={11}
            style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}
          />
        </button>
        <button
          onClick={e => { e.stopPropagation(); setDismissed(true); }}
          style={{ color: '#2a2a2a' }}
        >
          <X size={11} />
        </button>
      </div>

      {/* ── 展开面板 ─────────────────────────────────────────── */}
      {open && (
        <div
          className="px-4 pb-3 pt-1 flex flex-col gap-2"
          style={{ background: '#131313', borderTop: '1px solid #1a1a1a' }}
        >
          {(['claude', 'openai'] as const).map(p => {
            const isActive   = info?.provider === p;
            const configured = p === 'claude' ? info?.claude_configured : info?.openai_configured;
            const model      = p === 'claude' ? info?.claude_model : info?.openai_model;
            const testState  = p === 'claude' ? claudeTest : openaiTest;
            const testResult = p === 'claude' ? claudeResult : openaiResult;
            const label      = p === 'claude' ? 'Claude' : 'OpenAI';
            const color      = p === 'claude' ? '#a78bfa' : '#60a5fa';

            return (
              <div
                key={p}
                className="flex items-center gap-2 px-2 py-1.5 rounded"
                style={{
                  background: isActive ? '#1e1e2e' : '#0f0f0f',
                  border: `0.5px solid ${isActive ? color + '44' : '#1f1f1f'}`,
                }}
              >
                {/* 激活指示 + 标签 */}
                <div
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: isActive ? color : '#333' }}
                />
                <span className="text-xs font-medium w-12" style={{ color: isActive ? color : '#555' }}>
                  {label}
                </span>

                {/* 模型名 */}
                <span className="text-xs flex-1 truncate" style={{ color: '#3a3a3a' }}>
                  {model || '未配置'}
                </span>

                {/* 测速按钮 */}
                <button
                  onClick={() => testProvider(p)}
                  disabled={testState === 'testing'}
                  className="text-xs px-1.5 py-0.5 rounded flex items-center gap-1"
                  style={{
                    background: '#1a1a1a',
                    border: '0.5px solid #2a2a2a',
                    color: testState === 'ok' ? '#4ade80'
                         : testState === 'error' ? '#f87171'
                         : '#555',
                  }}
                  title="测试连通性"
                >
                  {testState === 'testing' ? (
                    <Loader size={9} className="animate-spin" />
                  ) : testState === 'ok' ? (
                    <CheckCircle size={9} />
                  ) : testState === 'error' ? (
                    <AlertTriangle size={9} />
                  ) : (
                    <Zap size={9} />
                  )}
                  {testState === 'ok' && testResult?.latency_ms != null
                    ? `${testResult.latency_ms}ms`
                    : testState === 'error'
                    ? '失败'
                    : '测速'}
                </button>

                {/* 切换按钮 */}
                {!isActive && configured && (
                  <button
                    onClick={() => switchProvider(p)}
                    disabled={switching}
                    className="text-xs px-2 py-0.5 rounded"
                    style={{
                      background: color + '22',
                      border: `0.5px solid ${color}55`,
                      color,
                    }}
                  >
                    {switching ? '切换中…' : '切换'}
                  </button>
                )}
                {isActive && (
                  <span className="text-xs px-2 py-0.5 rounded" style={{ color: color + 'aa', background: color + '11' }}>
                    使用中
                  </span>
                )}
                {!configured && (
                  <span className="text-xs" style={{ color: '#333' }}>未配置</span>
                )}
              </div>
            );
          })}

          {/* 错误提示 */}
          {(claudeResult?.error || openaiResult?.error) && (
            <div className="text-xs mt-0.5" style={{ color: '#f8717166' }}>
              {claudeResult?.error && <div>Claude: {claudeResult.error.slice(0, 80)}</div>}
              {openaiResult?.error && <div>OpenAI: {openaiResult.error.slice(0, 80)}</div>}
            </div>
          )}

          <div className="text-xs mt-0.5" style={{ color: '#2a2a2a' }}>
            切换仅在本次服务运行期间有效，永久修改请编辑 <code style={{ color: '#333' }}>.env</code> 中的 ACTIVE_AI_PROVIDER
          </div>
        </div>
      )}
    </div>
  );
}
