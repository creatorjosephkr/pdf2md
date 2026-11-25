import React, { useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeRaw from "rehype-raw";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { AlertTriangle, BookmarkCheck, Info, Lightbulb } from "lucide-react";
import { jobAssetUrl } from "../api/client";

interface MarkdownPreviewProps {
  markdown: string;
  jobId: string;
  baseUrl: string;
}

type CalloutKind = "NOTE" | "IMPORTANT" | "TIP" | "WARNING" | "CAUTION";

const CALLOUT_STYLES: Record<
  CalloutKind,
  {
    label: string;
    wrapClass: string;
    titleClass: string;
    Icon: React.ComponentType<{ className?: string }>;
  }
> = {
  NOTE: {
    label: "NOTE",
    wrapClass: "border-l-4 border-l-blue-500 border-slate-200 bg-blue-50/60",
    titleClass: "text-blue-800",
    Icon: Info,
  },
  IMPORTANT: {
    label: "IMPORTANT",
    wrapClass: "border-l-4 border-l-violet-500 border-slate-200 bg-violet-50/60",
    titleClass: "text-violet-800",
    Icon: BookmarkCheck,
  },
  TIP: {
    label: "TIP",
    wrapClass: "border-l-4 border-l-emerald-500 border-slate-200 bg-emerald-50/60",
    titleClass: "text-emerald-800",
    Icon: Lightbulb,
  },
  WARNING: {
    label: "WARNING",
    wrapClass: "border-l-4 border-l-amber-500 border-slate-200 bg-amber-50/70",
    titleClass: "text-amber-800",
    Icon: AlertTriangle,
  },
  CAUTION: {
    label: "CAUTION",
    wrapClass: "border-l-4 border-l-amber-600 border-slate-200 bg-amber-50/80",
    titleClass: "text-amber-900",
    Icon: AlertTriangle,
  },
};

const CALLOUT_RE = /^\[!(NOTE|IMPORTANT|TIP|WARNING|CAUTION)\][ \t]*([^\n]*)\n?/i;

function parseFrontmatter(raw: string): { meta: Record<string, string>; body: string } {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!match) {
    return { meta: {}, body: raw };
  }
  const meta: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const colonIdx = line.indexOf(":");
    if (colonIdx <= 0) continue;
    const key = line.slice(0, colonIdx).trim();
    let val = line.slice(colonIdx + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (key) meta[key] = val;
  }
  return { meta, body: raw.slice(match[0].length) };
}

function extractCalloutFromBlockquote(children: React.ReactNode): {
  kind: CalloutKind;
  customTitle: string;
  bodyChildren: React.ReactNode[];
} | null {
  const items = React.Children.toArray(children);
  const firstIdx = items.findIndex((item) => !(typeof item === "string" && !item.trim()));
  if (firstIdx < 0) return null;

  const firstEl = items[firstIdx];
  if (!React.isValidElement<{ children?: React.ReactNode }>(firstEl)) {
    return null;
  }

  const pChildren = React.Children.toArray(firstEl.props.children);
  if (pChildren.length === 0 || typeof pChildren[0] !== "string") {
    return null;
  }

  const m = pChildren[0].match(CALLOUT_RE);
  if (!m) return null;

  const kind = m[1].toUpperCase() as CalloutKind;
  const customTitle = (m[2] || "").trim();
  const remainder = pChildren[0].slice(m[0].length);
  const nextPChildren = remainder
    ? [remainder, ...pChildren.slice(1)]
    : pChildren.slice(1);

  const bodyChildren = [...items];
  if (nextPChildren.length > 0) {
    bodyChildren[firstIdx] = React.cloneElement(firstEl, {
      children: nextPChildren,
    });
  } else {
    bodyChildren.splice(firstIdx, 1);
  }

  return { kind, customTitle, bodyChildren };
}

export const MarkdownPreview: React.FC<MarkdownPreviewProps> = ({
  markdown,
  jobId,
  baseUrl,
}) => {
  const { meta, body } = useMemo(() => parseFrontmatter(markdown), [markdown]);

  const components: Components = useMemo(
    () => ({
      img: ({ src, alt, ...props }) => {
        const resolved = src ? jobAssetUrl(baseUrl, jobId, src) : "";
        return (
          <img
            src={resolved}
            alt={alt || "Document figure"}
            loading="lazy"
            {...props}
          />
        );
      },
      table: ({ children, ...props }) => (
        <div className="md-table-wrap">
          <table {...props}>{children}</table>
        </div>
      ),
      blockquote: ({ children, ...props }) => {
        const callout = extractCalloutFromBlockquote(children);
        if (!callout) {
          return <blockquote {...props}>{children}</blockquote>;
        }
        const style = CALLOUT_STYLES[callout.kind];
        const Icon = style.Icon;
        return (
          <div
            className={`my-4 rounded-xl border px-4 py-3 text-[13.5px] leading-relaxed ${style.wrapClass}`}
          >
            <div className={`mb-1.5 flex items-center gap-1.5 text-xs font-bold ${style.titleClass}`}>
              <Icon className="h-4 w-4 shrink-0" />
              <span>{callout.customTitle || style.label}</span>
            </div>
            <div className="md-callout-body text-slate-800">{callout.bodyChildren}</div>
          </div>
        );
      },
      a: ({ href, children, ...props }) => (
        <a href={href} target="_blank" rel="noreferrer" {...props}>
          {children}
        </a>
      ),
      script: () => null,
      iframe: () => null,
    }),
    [baseUrl, jobId]
  );

  if (!markdown.trim()) {
    return (
      <div className="flex h-full items-center justify-center rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500 shadow-xs">
        미리볼 마크다운 내용이 없습니다.
      </div>
    );
  }

  const metaPills: { label: string; value: string }[] = [];
  if (meta.source) metaPills.push({ label: "원본", value: meta.source });
  if (meta.pages) metaPills.push({ label: "페이지", value: `${meta.pages}p` });
  if (meta.language) metaPills.push({ label: "언어", value: meta.language.toUpperCase() });
  if (meta.columns) metaPills.push({ label: "단 구성", value: `${meta.columns}단` });

  return (
    <div className="h-full overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-xs">
      {metaPills.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50/80 px-6 py-3">
          {meta.title && (
            <span className="mr-1 text-xs font-semibold text-slate-700 truncate max-w-[360px]" title={meta.title}>
              {meta.title}
            </span>
          )}
          {metaPills.map((pill) => (
            <span
              key={pill.label}
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600"
            >
              <span className="text-slate-400">{pill.label}</span>
              <span className="font-semibold text-slate-800">{pill.value}</span>
            </span>
          ))}
        </div>
      )}

      <article className="md-preview px-7 py-6">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeRaw, [rehypeKatex, { strict: false, throwOnError: false }]]}
          components={components}
        >
          {body}
        </ReactMarkdown>
      </article>
    </div>
  );
};
