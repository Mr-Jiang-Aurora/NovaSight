import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SOD/COD 科研助手",
  description: "多 Agent 科研辅助系统 — SOTA 调研 · 指标诊断 · 代码分析 · 图像理解",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="h-full overflow-hidden">{children}</body>
    </html>
  );
}
