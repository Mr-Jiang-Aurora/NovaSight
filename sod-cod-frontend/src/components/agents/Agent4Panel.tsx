'use client';
import { useState, useCallback } from 'react';
import { Image as ImageIcon, Upload, X, ChevronRight, Loader2 } from 'lucide-react';
import { useDropzone } from 'react-dropzone';
import { usePipelineStore } from '@/store/pipelineStore';
import { useAgentRunner } from '@/hooks/useAgentRunner';

interface Agent4PanelProps {
  onViewReport: () => void;
}

export default function Agent4Panel({ onViewReport }: Agent4PanelProps) {
  const { archImage, setArchImage, visualImage, setVisualImage, agents } = usePipelineStore();
  const { runAgent4 } = useAgentRunner();
  const state = agents.agent4;

  const [mode, setMode] = useState<'arch' | 'visual'>('arch');
  const [userHint, setUserHint] = useState('');
  const [userMethod, setUserMethod] = useState('');
  const [options, setOptions] = useState({ arch: true, trace: true, innovation: true });

  const currentImage = mode === 'arch' ? archImage : visualImage;
  const setCurrentImage = mode === 'arch' ? setArchImage : setVisualImage;

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles[0]) setCurrentImage(acceptedFiles[0]);
  }, [setCurrentImage]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.png', '.jpg', '.jpeg', '.webp'] },
    multiple: false,
    maxSize: 20 * 1024 * 1024,
  });

  const imagePreviewUrl = currentImage ? URL.createObjectURL(currentImage) : null;

  const handleRun = () => {
    if (!currentImage) return;
    runAgent4({ mode, image: currentImage, userHint, userMethod });
  };

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <ImageIcon size={16} style={{ color: '#8b5cf6' }} />
        <span className="text-sm font-semibold" style={{ color: '#e8e6df' }}>图像分析</span>
        <span className="ml-auto text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(139,92,246,0.1)', color: '#8b5cf6' }}>
          Agent 4
        </span>
      </div>

      {/* Mode tabs */}
      <div className="flex rounded overflow-hidden" style={{ border: '0.5px solid #2a2a2a' }}>
        {(['arch', 'visual'] as const).map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className="flex-1 py-2 text-xs transition-colors"
            style={{
              background: mode === m ? 'rgba(139,92,246,0.08)' : '#1a1a1a',
              color: mode === m ? '#8b5cf6' : '#555450',
              borderRight: m === 'arch' ? '0.5px solid #2a2a2a' : 'none',
            }}
          >
            {m === 'arch' ? '架构图分析' : '对比图分析'}
          </button>
        ))}
      </div>

      {/* Image upload */}
      {!currentImage ? (
        <div
          {...getRootProps()}
          className="rounded p-8 text-center cursor-pointer transition-colors"
          style={{
            border: `1.5px dashed ${isDragActive ? '#8b5cf6' : '#2a2a2a'}`,
            background: isDragActive ? 'rgba(139,92,246,0.04)' : '#161616',
          }}
        >
          <input {...getInputProps()} />
          <Upload size={22} className="mx-auto mb-2" style={{ color: isDragActive ? '#8b5cf6' : '#555450' }} />
          <p className="text-xs" style={{ color: '#555450' }}>
            {isDragActive ? '释放图片...' : '将图片拖入此处或点击选择'}
          </p>
          <p className="text-xs mt-1" style={{ color: '#3d3d3a' }}>PNG / JPG / WebP — 最大 20MB</p>
        </div>
      ) : (
        <div className="relative rounded overflow-hidden" style={{ border: '0.5px solid #2a2a2a' }}>
          {imagePreviewUrl && (
            <img
              src={imagePreviewUrl}
              alt="预览"
              className="w-full object-contain"
              style={{ maxHeight: '200px', background: '#161616' }}
            />
          )}
          <button
            onClick={() => setCurrentImage(null)}
            className="absolute top-2 right-2 w-6 h-6 rounded flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.7)' }}
          >
            <X size={12} style={{ color: '#e8e6df' }} />
          </button>
          <div className="px-3 py-2 text-xs" style={{ background: '#1a1a1a', color: '#888780' }}>
            {currentImage.name} — {(currentImage.size / 1024 / 1024).toFixed(2)} MB
          </div>
        </div>
      )}

      {/* Mode-specific options */}
      {mode === 'arch' && (
        <div className="space-y-2">
          <label className="text-xs" style={{ color: '#888780' }}>分析选项</label>
          {Object.entries(options).map(([key, val]) => {
            const labels: Record<string, string> = {
              arch: '六维度架构解析',
              trace: 'Figure 自动溯源（搜索论文出处）',
              innovation: '学术创新性评估',
            };
            return (
              <label key={key} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={val}
                  onChange={e => setOptions(prev => ({ ...prev, [key]: e.target.checked }))}
                  style={{ accentColor: '#8b5cf6' }}
                />
                <span className="text-xs" style={{ color: '#c2c0b6' }}>{labels[key]}</span>
              </label>
            );
          })}
          <input
            value={userHint}
            onChange={e => setUserHint(e.target.value)}
            placeholder="可填写论文标题或背景信息（帮助提升识别准确度）"
            className="w-full px-3 py-2 text-xs rounded mt-2"
            style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#888780', outline: 'none' }}
          />
        </div>
      )}

      {mode === 'visual' && (
        <div className="space-y-2">
          <label className="text-xs mb-1 block" style={{ color: '#888780' }}>用户方法列名（可选）</label>
          <input
            value={userMethod}
            onChange={e => setUserMethod(e.target.value)}
            placeholder='如：Ours'
            className="w-full px-3 py-2 text-xs rounded"
            style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a', color: '#c2c0b6', outline: 'none' }}
          />
          <p className="text-xs" style={{ color: '#555450' }}>用于在对比分析中重点关注用户的方法</p>
        </div>
      )}

      {/* Run button */}
      <button
        onClick={handleRun}
        disabled={!currentImage || state.status === 'running'}
        className="w-full py-2 text-sm rounded font-medium"
        style={{
          background: (!currentImage || state.status === 'running') ? '#2a2a2a' : '#c8b560',
          color: (!currentImage || state.status === 'running') ? '#555450' : '#0f0f0f',
          border: 'none',
        }}
      >
        {state.status === 'running' ? (
          <span className="flex items-center justify-center gap-2"><Loader2 size={13} className="animate-spin" /> 分析中...</span>
        ) : '运行图像分析'}
      </button>

      {/* Progress */}
      {state.status === 'running' && (
        <div className="rounded p-3" style={{ background: '#1a1a1a', border: '0.5px solid #2a2a2a' }}>
          <div className="flex justify-between mb-1.5">
            <span className="text-xs truncate pr-2" style={{ color: '#888780' }}>{state.currentStep}</span>
            <span className="text-xs flex-shrink-0" style={{ color: '#8b5cf6' }}>{state.progress}%</span>
          </div>
          <div className="h-0.5 rounded" style={{ background: '#2a2a2a' }}>
            <div className="h-full rounded transition-all" style={{ width: `${state.progress}%`, background: '#8b5cf6' }} />
          </div>
        </div>
      )}
      {state.status === 'error' && (
        <div className="rounded p-3 text-xs" style={{ background: 'rgba(239,68,68,0.08)', border: '0.5px solid rgba(239,68,68,0.3)', color: '#ef4444' }}>
          {state.error}
        </div>
      )}
      {state.status === 'success' && (
        <div className="rounded p-3" style={{ background: 'rgba(139,92,246,0.06)', border: '0.5px solid rgba(139,92,246,0.2)' }}>
          <div className="text-xs mb-2" style={{ color: '#8b5cf6' }}>图像分析完成</div>
          <button onClick={onViewReport} className="flex items-center gap-1 text-xs" style={{ color: '#c8b560' }}>
            查看图像分析报告 <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
