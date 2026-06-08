import Link from "next/link";
import { ExternalLink } from "lucide-react";

type PhoenixDeepLinkProps = {
  spanId?: string;
  traceId?: string;
  promptId?: string;
  experimentId?: string;
  datasetId?: string;
  projectName?: string;
  path?: string;
  label?: string;
};

const PHOENIX_BASE_URL = process.env.NEXT_PUBLIC_PHOENIX_URL;

function buildPhoenixUrl(props: PhoenixDeepLinkProps): string | null {
  if (!PHOENIX_BASE_URL) return null;
  if (props.spanId && props.traceId) {
    return `${PHOENIX_BASE_URL}/traces/${props.traceId}?selectedSpan=${props.spanId}`;
  }
  if (props.traceId) {
    return `${PHOENIX_BASE_URL}/traces/${props.traceId}`;
  }
  if (props.promptId) {
    return `${PHOENIX_BASE_URL}/prompts/${props.promptId}`;
  }
  if (props.experimentId && !props.experimentId.startsWith("local-")) {
    return `${PHOENIX_BASE_URL}/experiments/${props.experimentId}`;
  }
  if (props.datasetId) {
    return `${PHOENIX_BASE_URL}/datasets/${props.datasetId}`;
  }
  if (props.projectName) {
    return `${PHOENIX_BASE_URL}/projects/${encodeURIComponent(props.projectName)}`;
  }
  if (props.path) {
    const normalized = props.path.startsWith("/") ? props.path : `/${props.path}`;
    return `${PHOENIX_BASE_URL}${normalized}`;
  }
  return null;
}

export function PhoenixDeepLink(props: PhoenixDeepLinkProps) {
  const url = buildPhoenixUrl(props);
  if (!url) {
    // Phoenix not configured — render an inert chip so the user knows the
    // surface exists but isn't wired. Better than a link to /traces/null.
    return (
      <span
        className="inline-flex items-center gap-1 text-caption text-mute"
        title="Set NEXT_PUBLIC_PHOENIX_URL to enable Phoenix deep-links."
      >
        <ExternalLink className="h-3 w-3" aria-hidden />
        Configure Phoenix
      </span>
    );
  }
  return (
    <Link
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-caption font-medium text-brand-soft hover:text-brand hover:underline"
      aria-label={props.label ? `${props.label} in Phoenix` : "Open in Phoenix"}
    >
      <ExternalLink className="h-3 w-3" aria-hidden />
      {props.label ?? "Phoenix"}
    </Link>
  );
}
