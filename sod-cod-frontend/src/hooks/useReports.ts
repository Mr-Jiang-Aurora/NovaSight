'use client';
import { useState, useEffect, useCallback, useRef } from 'react';
import { usePipelineStore } from '@/store/pipelineStore';
import { api } from '@/lib/api';
import type { ReportFile } from '@/types';

export function useReports(agentId: string) {
  const {
    reportFiles, activeReport, reportContent,
    setReportFiles, setActiveReport, setReportContent,
  } = usePipelineStore();

  const [isLoadingContent, setIsLoadingContent] = useState(false);
  // Prevent concurrent loads for the same filename
  const loadingRef = useRef<Set<string>>(new Set());

  // ── 加载报告列表 ──────────────────────────────────────────────────────
  const loadReportList = useCallback(async () => {
    try {
      const data = await api.listReports(agentId);
      const files: ReportFile[] = data.files || [];
      setReportFiles(agentId, files);
      // 仅在没有活跃报告时才自动选中第一个（避免覆盖用户手动选择）
      if (files.length > 0 && !activeReport[agentId]) {
        setActiveReport(agentId, files[0].name);
      }
    } catch (e) {
      console.error(`[useReports] 加载 ${agentId} 报告列表失败`, e);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  // ── 加载报告内容 ──────────────────────────────────────────────────────
  const loadReportContent = useCallback(async (
    filename: string,
    filepath: string,
    forceReload = false,
  ): Promise<string> => {
    // 已缓存且不强制刷新则直接返回
    const cached = usePipelineStore.getState().reportContent[filename];
    if (cached && !forceReload) return cached;
    // 防止同一文件并发加载
    if (loadingRef.current.has(filename)) return cached || '';
    loadingRef.current.add(filename);
    setIsLoadingContent(true);
    try {
      const content = await api.getReport(agentId, filepath);
      setReportContent(filename, content);
      return content;
    } catch (e) {
      console.error(`[useReports] 加载报告内容失败: ${filename}`, e);
      return '';
    } finally {
      loadingRef.current.delete(filename);
      setIsLoadingContent(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, setReportContent]);

  // ── 选中报告 ──────────────────────────────────────────────────────────
  const selectReport = useCallback(async (file: ReportFile) => {
    setActiveReport(agentId, file.name);
    // 强制从服务器重新加载，确保内容是最新的
    await loadReportContent(file.name, file.path, false);
  }, [agentId, loadReportContent, setActiveReport]);

  // ── 挂载时加载列表 ────────────────────────────────────────────────────
  useEffect(() => {
    loadReportList();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  // ── 当外部（useAgentRunner）直接更新 store 的 reportFiles 后自动选中 ──
  const filesForAgent = reportFiles[agentId];
  useEffect(() => {
    if ((filesForAgent?.length ?? 0) > 0 && !activeReport[agentId]) {
      setActiveReport(agentId, filesForAgent![0].name);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filesForAgent?.length, agentId]);

  // ── 当活跃文件名变化时加载内容 ───────────────────────────────────────
  const currentFilename = activeReport[agentId];
  useEffect(() => {
    if (!currentFilename) return;
    const files = usePipelineStore.getState().reportFiles[agentId] || [];
    const currentFile = files.find((f) => f.name === currentFilename);
    if (!currentFile) return;
    const alreadyCached = !!usePipelineStore.getState().reportContent[currentFilename];
    if (!alreadyCached) {
      loadReportContent(currentFilename, currentFile.path);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentFilename, agentId]);

  return {
    files: reportFiles[agentId] || [],
    activeFilename: activeReport[agentId] || '',
    currentContent: reportContent[activeReport[agentId] || ''] || '',
    isLoadingContent,
    loadReportList,
    selectReport,
    loadReportContent,
  };
}
