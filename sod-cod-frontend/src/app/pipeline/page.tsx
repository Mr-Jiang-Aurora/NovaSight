"use client";

import { useState } from "react";
import { Globe, Languages } from "lucide-react";

export default function PipelinePage() {
  const [lang, setLang] = useState<"zh" | "en">("zh");

  const src = lang === "zh"
    ? "/pipeline_demo_zh.html"
    : "/pipeline_demo_en.html";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#f1efe8" }}>
      {/* 顶部工具栏 */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "8px 20px",
        background: "#ffffff",
        borderBottom: "1px solid rgba(0,0,0,0.10)",
        flexShrink: 0,
      }}>
        <Globe size={15} style={{ color: "#5f5e5a" }} />
        <span style={{ fontSize: 13, fontWeight: 500, color: "#1a1a18" }}>
          数据流演示 / Pipeline Demo
        </span>

        {/* 中英切换 */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 0 }}>
          {(["zh", "en"] as const).map(l => (
            <button
              key={l}
              onClick={() => setLang(l)}
              style={{
                fontSize: 12,
                padding: "4px 14px",
                border: "0.5px solid rgba(0,0,0,0.2)",
                borderRadius: l === "zh" ? "6px 0 0 6px" : "0 6px 6px 0",
                background: lang === l ? "#e6f1fb" : "#f8f7f4",
                color: lang === l ? "#185fa5" : "#5f5e5a",
                cursor: "pointer",
                fontFamily: "inherit",
                transition: "all 0.15s",
                display: "flex", alignItems: "center", gap: 5,
              }}
            >
              {l === "zh" ? (
                <><Languages size={12} /> 中文</>
              ) : (
                <><Languages size={12} /> English</>
              )}
            </button>
          ))}
        </div>

        <a
          href="/workspace"
          style={{
            fontSize: 12, color: "#888780",
            textDecoration: "none",
            padding: "4px 10px",
            borderRadius: 6,
            border: "0.5px solid rgba(0,0,0,0.12)",
          }}
        >
          ← 返回工作台
        </a>
      </div>

      {/* iframe 主体 */}
      <iframe
        key={lang}
        src={src}
        style={{
          flex: 1,
          width: "100%",
          border: "none",
        }}
        title={lang === "zh" ? "数据流演示（中文）" : "Pipeline Demo (English)"}
      />
    </div>
  );
}
