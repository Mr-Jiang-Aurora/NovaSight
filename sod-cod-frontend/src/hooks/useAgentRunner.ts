'use client';
import { useCallback } from 'react';
import { usePipelineStore } from '@/store/pipelineStore';
import { api } from '@/lib/api';

// ── 进度条平滑 ticker ──────────────────────────────────────────────────
/**
 * 在 API 调用期间缓慢推进进度条（每 2s +1%，上限 88%），避免进度"卡死"的假象。
 * 返回 cancel 函数，在 API 调用结束后立即调用。
 */
function startProgressTicker(
  agentId: string,
  fromPct: number,
  setStatus: (s: Partial<{ progress: number }>) => void
): () => void {
  let current = fromPct;
  const id = setInterval(() => {
    current = Math.min(current + 1, 88);
    setStatus({ progress: current });
  }, 2000);
  return () => clearInterval(id);
}

// ── 运行结束后刷新列表并预加载最新报告内容 ─────────────────────────────
async function refreshAndSelectLatest(agentId: string) {
  const store = usePipelineStore.getState();
  try {
    const reportData = await api.listReports(agentId);
    const files = reportData.files || [];
    store.setReportFiles(agentId, files);
    if (files.length === 0) return;

    const newest = files[0];
    store.setActiveReport(agentId, newest.name);

    // 立即预加载内容，避免 ReportViewer 需要等额外一次请求
    if (!store.reportContent[newest.name]) {
      const content = await api.getReport(agentId, newest.path);
      store.setReportContent(newest.name, content);
    }
  } catch (e) {
    console.error(`[refreshAndSelectLatest] ${agentId}:`, e);
  }
}

// ── Hook ──────────────────────────────────────────────────────────────

export function useAgentRunner() {
  const store = usePipelineStore();

  // ── Agent1 ──────────────────────────────────────────────────────────
  const runAgent1 = useCallback(async (params?: {
    useCache?: boolean; startYear?: number; endYear?: number;
  }) => {
    const set = (s: Parameters<typeof store.setAgentStatus>[1]) =>
      store.setAgentStatus('agent1', s);

    set({ status: 'running', progress: 10, currentStep: '初始化搜索...' });
    const stopTicker = startProgressTicker('agent1', 10, set);
    try {
      set({ progress: 20, currentStep: '多源并发搜索（Semantic Scholar / DBLP / CVF）...' });
      const result = await api.runAgent1({
        domain: store.domain,
        use_cache: params?.useCache ?? true,
        start_year: params?.startYear ?? 2024,
        end_year: params?.endYear ?? 2025,
      });
      stopTicker();
      set({ progress: 95, currentStep: '生成论文信息卡片...' });
      await new Promise(r => setTimeout(r, 300));
      set({ status: 'success', progress: 100, currentStep: `完成：${result.scored_papers} 篇有指标 / ${result.total_papers} 篇` });
      await refreshAndSelectLatest('agent1');
    } catch (e: unknown) {
      stopTicker();
      set({ status: 'error', error: e instanceof Error ? e.message : '未知错误' });
    }
  }, [store]);

  // ── Agent2 ──────────────────────────────────────────────────────────
  const runAgent2 = useCallback(async () => {
    const set = (s: Parameters<typeof store.setAgentStatus>[1]) =>
      store.setAgentStatus('agent2', s);

    set({ status: 'running', progress: 8, currentStep: '加载 Agent1 缓存数据...' });
    const stopTicker = startProgressTicker('agent2', 8, set);
    try {
      set({ progress: 15, currentStep: '构建排行榜（12 维度）...' });
      const result = await api.runAgent2({
        domain: store.domain,
        user_method_desc: store.userMethodDesc,
      });
      stopTicker();
      set({ progress: 92, currentStep: 'Claude 生成深度诊断报告（6 章节）...' });
      await new Promise(r => setTimeout(r, 400));
      set({ status: 'success', progress: 100, currentStep: `完成：${result.scored_methods} 个方法已分析` });

      // 获取 agent2_summary 供 Agent3 使用
      const summaryData = await api.listReports('agent2');
      const sf = summaryData.files?.find((f) => f.name.includes('summary'));
      if (sf) {
        const c = await api.getReport('agent2', sf.path);
        store.setAgent2Summary(c);
      }
      await refreshAndSelectLatest('agent2');
    } catch (e: unknown) {
      stopTicker();
      set({ status: 'error', error: e instanceof Error ? e.message : '未知错误' });
    }
  }, [store]);

  // ── Agent3 GitHub ────────────────────────────────────────────────────
  const runAgent3Github = useCallback(async (githubUrl: string) => {
    const set = (s: Parameters<typeof store.setAgentStatus>[1]) =>
      store.setAgentStatus('agent3', s);

    set({ status: 'running', progress: 8, currentStep: '连接 GitHub 仓库...' });
    const stopTicker = startProgressTicker('agent3', 8, set);
    try {
      set({ progress: 18, currentStep: '下载关键代码文件（最多 12 个）...' });
      const result = await api.runAgent3Github({
        domain: store.domain,
        github_url: githubUrl,
        structure_hint: store.structureHint,
        agent2_summary: store.agent2Summary,
      });
      stopTicker();
      set({ status: 'success', progress: 100, currentStep: '完成：' + ((result.arch_summary?.slice(0, 40)) || '分析完成') });
      await refreshAndSelectLatest('agent3');
    } catch (e: unknown) {
      stopTicker();
      set({ status: 'error', error: e instanceof Error ? e.message : '未知错误' });
    }
  }, [store]);

  // ── Agent3 Upload ────────────────────────────────────────────────────
  const runAgent3Upload = useCallback(async (files: File[]) => {
    const set = (s: Parameters<typeof store.setAgentStatus>[1]) =>
      store.setAgentStatus('agent3', s);

    set({ status: 'running', progress: 10, currentStep: '上传代码文件...' });
    const stopTicker = startProgressTicker('agent3', 10, set);
    try {
      const formData = new FormData();
      files.forEach(f => formData.append('files', f));
      formData.append('domain', store.domain);
      formData.append('structure_hint', store.structureHint);
      formData.append('agent2_summary', store.agent2Summary);
      set({ progress: 20, currentStep: 'AST 静态分析 + Claude 语义分析...' });
      await api.runAgent3Upload(formData);
      stopTicker();
      set({ status: 'success', progress: 100, currentStep: '分析完成' });
      await refreshAndSelectLatest('agent3');
    } catch (e: unknown) {
      stopTicker();
      set({ status: 'error', error: e instanceof Error ? e.message : '未知错误' });
    }
  }, [store]);

  // ── Agent4 ───────────────────────────────────────────────────────────
  const runAgent4 = useCallback(async (params: {
    mode: 'arch' | 'visual'; image: File; userHint?: string; userMethod?: string;
  }) => {
    const set = (s: Parameters<typeof store.setAgentStatus>[1]) =>
      store.setAgentStatus('agent4', s);

    set({ status: 'running', progress: 8, currentStep: '上传图片到 Claude Vision...' });
    const stopTicker = startProgressTicker('agent4', 8, set);
    try {
      set({
        progress: 15,
        currentStep: params.mode === 'arch'
          ? '六维度架构解析 + Figure 溯源 + 创新性评估...'
          : '可视化对比分析中...',
      });
      const result = await api.runAgent4(params.image, {
        mode: params.mode,
        user_hint: params.userHint || '',
        user_method: params.userMethod || '',
      });
      stopTicker();
      if (params.mode === 'arch' && result.structure_hint) {
        store.setStructureHint(result.structure_hint);
      }
      set({ status: 'success', progress: 100, currentStep: '完成' });
      await refreshAndSelectLatest('agent4');
    } catch (e: unknown) {
      stopTicker();
      set({ status: 'error', error: e instanceof Error ? e.message : '未知错误' });
    }
  }, [store]);

  // ── Master ───────────────────────────────────────────────────────────
  const runMaster = useCallback(async () => {
    const set = (s: Parameters<typeof store.setAgentStatus>[1]) =>
      store.setAgentStatus('master', s);

    set({ status: 'running', progress: 5, currentStep: '规划工作流...' });
    const stopTicker = startProgressTicker('master', 5, set);
    try {
      const hasCode = !!store.githubUrl || store.uploadedFiles.length > 0;
      const hasImage = !!store.archImage || !!store.visualImage;

      stopTicker(); // master 自己管理阶段进度

      set({ progress: 10, currentStep: 'Agent1: 加载 SOTA 数据...' });
      await runAgent1({ useCache: true });

      set({ progress: 35, currentStep: 'Agent2: 指标诊断...' });
      await runAgent2();

      if (hasImage && store.archImage) {
        set({ progress: 55, currentStep: 'Agent4: 图像分析...' });
        await runAgent4({ mode: 'arch', image: store.archImage });
      }

      if (hasCode) {
        set({ progress: 70, currentStep: 'Agent3: 代码分析...' });
        if (store.githubUrl) {
          await runAgent3Github(store.githubUrl);
        } else {
          await runAgent3Upload(store.uploadedFiles);
        }
      }

      set({ progress: 90, currentStep: '生成综合报告（6 章节）...' });
      await api.runMaster({
        domain: store.domain,
        github_url: store.githubUrl || undefined,
        user_method_desc: store.userMethodDesc,
        run_agent3: hasCode,
        run_agent4: hasImage,
      });

      set({ status: 'success', progress: 100, currentStep: '全部完成' });
      await refreshAndSelectLatest('master');
    } catch (e: unknown) {
      set({ status: 'error', error: e instanceof Error ? e.message : '未知错误' });
    }
  }, [store, runAgent1, runAgent2, runAgent3Github, runAgent3Upload, runAgent4]);

  return { runAgent1, runAgent2, runAgent3Github, runAgent3Upload, runAgent4, runMaster };
}
