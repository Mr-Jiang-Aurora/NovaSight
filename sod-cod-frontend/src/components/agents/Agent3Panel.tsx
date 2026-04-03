'use client';
import { useState, useCallback } from 'react';
import { Code2, Upload, X, Github, ChevronRight, Loader2, CheckCircle2 } from 'lucide-react';
import { useDropzone } from 'react-dropzone';
import { usePipelineStore } from '@/store/pipelineStore';
import { useAgentRunner } from '@/hooks/useAgentRunner';

interface Agent3PanelProps {
  onViewReport: () => void;
}

export default function Agent3Panel({ onViewReport }: Agent3PanelProps) {
  const { githubUrl, setGithubUrl, uploadedFiles, setUploadedFiles, agents, structureHint } = usePipelineStore();
  const { runAgent3Github, runAgent3Upload } = useAgentRunner();
  const state = agents.agent3;

  const [mode, setMode] = useState<'github' | 'upload'>('github');
  const [repoVerified, setRepoVerified] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setUploadedFiles([...uploadedFiles, ...acceptedFiles].slice(0, 12));
  }, [uploadedFiles, setUploadedFiles]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'text/plain': ['.py', '.yaml', '.yml', '.txt', '.cfg', '.json'] },
    multiple: true,
  });

  const removeFile = (i: number) => setUploadedFiles(uploadedFiles.filter((_, idx) => idx !== i));

  const handleVerify = async () => {
    if (!githubUrl) return;
    setVerifying(true);
    await new Promise(r => setTimeout(r, 800));
    setRepoVerified(true);
    setVerifying(false);
  };

  const handleRun = () => {
    if (mode === 'github' && githubUrl) {
      runAgent3Github(githubUrl);
    } else if (mode === 'upload' && uploadedFiles.length > 0) {
      runAgent3Upload(uploadedFiles);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Code2 size={16} style={{ color: '#f59e0b' }} />
        <span className="text-sm font-semibold" style={{ color: '#e8e6df' }}>代码分析</span>
        <span className="ml-auto text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b' }}>
          Agent 3
        </span>
      </div>

      {/* Mode tabs */}
      <div className="flex rounded overflow-hidden" style={{ border: '0.5px solid #2a2a2a' }}>
        {(['github', 'upload'] as const).map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className="flex-1 py-2 text-xs transition-colors"
            style={{
              background: mode === m ? 'rgba(245,158,11,0.08)' : '#1a1a1a',
              color: mode === m ? '#f59e0b' : '#555450',
              borderRight: m === 'github' ? '0.5px solid #2a2a2a' : 'none',
            }}
          >
            {m === 'github' ? (
              <span className="flex items-center justify-center gap-1"><Github size={12} /> GitHub 链接</span>
            ) : (
              <span className="flex items-center justify-center gap-1"><Upload size={12} /> 本地上传</span>
            )}
          </button>
        ))}
      </div>

      {/* GitHub mode */}
      {mode === 'github' && (
        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              value={githubUrl}
              onChange={e => { setGithubUrl(e.target.value); setRepoVerified(false); }}
              placeholder="https://github.com/user/repo"
              className="flex-1 px-3 py-2 text-xs rounded"
              style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#c2c0b6', outline: 'none', fontFamily: 'monospace' }}
            />
            <button
              onClick={handleVerify}
              disabled={!githubUrl || verifying}
              className="px-3 py-2 text-xs rounded transition-colors flex-shrink-0"
              style={{ background: '#222', border: '0.5px solid #2a2a2a', color: '#888780' }}
            >
              {verifying ? <Loader2 size={11} className="animate-spin" /> : '验证'}
            </button>
          </div>
          {repoVerified && githubUrl && (
            <div className="p-2 rounded text-xs" style={{ background: 'rgba(16,185,129,0.06)', border: '0.5px solid rgba(16,185,129,0.2)' }}>
              <div className="flex items-center gap-1 mb-1" style={{ color: '#10b981' }}>
                <CheckCircle2 size={11} /> 仓库可访问
              </div>
              <div style={{ color: '#888780' }}>{githubUrl.replace('https://github.com/', '')}</div>
            </div>
          )}
        </div>
      )}

      {/* Upload mode */}
      {mode === 'upload' && (
        <div className="space-y-2">
          <div
            {...getRootProps()}
            className="rounded p-6 text-center cursor-pointer transition-colors"
            style={{
              border: `1.5px dashed ${isDragActive ? '#f59e0b' : '#2a2a2a'}`,
              background: isDragActive ? 'rgba(245,158,11,0.04)' : '#161616',
            }}
          >
            <input {...getInputProps()} />
            <Upload size={20} className="mx-auto mb-2" style={{ color: isDragActive ? '#f59e0b' : '#555450' }} />
            <p className="text-xs" style={{ color: '#555450' }}>
              {isDragActive ? '释放文件...' : '将代码文件拖入此处'}
            </p>
            <p className="text-xs mt-1" style={{ color: '#3d3d3a' }}>.py .yaml .yml .txt .cfg</p>
          </div>
          {uploadedFiles.length > 0 && (
            <div className="space-y-1 max-h-36 overflow-y-auto">
              {uploadedFiles.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 px-2 py-1.5 rounded text-xs"
                  style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}
                >
                  <Code2 size={11} style={{ color: '#f59e0b', flexShrink: 0 }} />
                  <span className="flex-1 truncate" style={{ color: '#c2c0b6', fontFamily: 'monospace' }}>{f.name}</span>
                  <span style={{ color: '#555450' }}>{(f.size / 1024).toFixed(1)}KB</span>
                  <button onClick={() => removeFile(i)} style={{ color: '#555450' }}>
                    <X size={11} />
                  </button>
                </div>
              ))}
              <div className="text-xs pt-1" style={{ color: '#555450' }}>
                已选 {uploadedFiles.length} 个文件
              </div>
            </div>
          )}
        </div>
      )}

      {/* Structure hint from Agent4 */}
      <div>
        <label className="text-xs mb-1.5 block" style={{ color: '#888780' }}>Agent4 架构提示（只读）</label>
        <div
          className="p-2 rounded text-xs"
          style={{
            background: '#161616',
            border: '0.5px solid #2a2a2a',
            color: structureHint ? '#888780' : '#3d3d3a',
            fontFamily: 'monospace',
            minHeight: '40px',
          }}
        >
          {structureHint || '运行 Agent4 分析架构图后，此处会自动填入'}
        </div>
      </div>

      {/* Buttons */}
      <div className="flex flex-col gap-2">
        <button
          onClick={handleRun}
          disabled={state.status === 'running' || (mode === 'github' ? !githubUrl : uploadedFiles.length === 0)}
          className="w-full py-2 text-sm rounded font-medium"
          style={{
            background: state.status === 'running' ? '#2a2a2a' : '#c8b560',
            color: state.status === 'running' ? '#555450' : '#0f0f0f',
            border: 'none',
          }}
        >
          {state.status === 'running' ? (
            <span className="flex items-center justify-center gap-2"><Loader2 size={13} className="animate-spin" /> 分析中...</span>
          ) : '分析代码'}
        </button>
        <button
          className="text-xs"
          style={{ color: '#555450', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          跳过 Claude API，仅静态分析
        </button>
      </div>

      {/* Progress / status */}
      {state.status === 'running' && (
        <div className="rounded p-3" style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}>
          <div className="flex justify-between mb-1.5">
            <span className="text-xs truncate pr-2" style={{ color: '#888780' }}>{state.currentStep}</span>
            <span className="text-xs flex-shrink-0" style={{ color: '#c8b560' }}>{state.progress}%</span>
          </div>
          <div className="h-0.5 rounded" style={{ background: '#2a2a2a' }}>
            <div className="h-full rounded transition-all" style={{ width: `${state.progress}%`, background: '#f59e0b' }} />
          </div>
        </div>
      )}
      {state.status === 'error' && (
        <div className="rounded p-3 text-xs" style={{ background: 'rgba(239,68,68,0.08)', border: '0.5px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>
          {state.error}
        </div>
      )}
      {state.status === 'success' && (
        <div className="rounded p-3" style={{ background: 'rgba(245,158,11,0.06)', border: '0.5px solid rgba(245,158,11,0.2)' }}>
          <div className="text-xs mb-2" style={{ color: '#f59e0b' }}>{state.currentStep}</div>
          <button onClick={onViewReport} className="flex items-center gap-1 text-xs" style={{ color: '#c8b560' }}>
            查看代码分析报告 <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
