"use client";

import * as React from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CodeBlockProps extends React.HTMLAttributes<HTMLDivElement> {
  language?: string;
  filename?: string;
  copyValue?: string;
  showLineNumbers?: boolean;
  children: React.ReactNode;
}

export function CodeBlock({
  language,
  filename,
  copyValue,
  showLineNumbers = false,
  className,
  children,
  ...rest
}: CodeBlockProps) {
  const [copied, setCopied] = React.useState(false);
  const ref = React.useRef<HTMLPreElement>(null);

  const onCopy = async () => {
    const text = copyValue ?? ref.current?.innerText ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  const lines = React.Children.toArray(children);

  return (
    <div
      className={cn(
        "rounded-md border border-hairline bg-canvas overflow-hidden",
        className
      )}
      {...rest}
    >
      {(filename || language) && (
        <div className="flex items-center justify-between border-b border-hairline bg-canvas-soft px-4 py-2 text-caption text-mute">
          <div className="flex items-center gap-3 font-mono">
            {filename && <span className="text-canvas-text-soft">{filename}</span>}
            {language && <span className="uppercase tracking-wider">{language}</span>}
          </div>
          <button
            type="button"
            onClick={onCopy}
            aria-label={copied ? "Copied" : "Copy code"}
            className="inline-flex items-center gap-1.5 rounded-xs px-2 py-1 text-mute hover:text-ink"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-brand" />
                <span className="text-caption">copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span className="text-caption">copy</span>
              </>
            )}
          </button>
        </div>
      )}
      <pre
        ref={ref}
        className={cn(
          "overflow-x-auto px-5 py-4 text-code text-canvas-text-soft font-mono",
          showLineNumbers && "pl-2"
        )}
      >
        {showLineNumbers ? (
          <code className="block">
            {lines.map((line, i) => (
              <span key={i} className="flex">
                <span className="select-none pr-4 pl-1 text-right text-mute opacity-60 w-10">
                  {i + 1}
                </span>
                <span className="flex-1">{line}</span>
              </span>
            ))}
          </code>
        ) : (
          <code>{children}</code>
        )}
      </pre>
    </div>
  );
}
