import { memo, useState } from "react";

import type { FileSegment } from "../segments";
import { fileUrl } from "../segments";
import { openPreview } from "../previewStore";
import {
  IconCheck,
  IconCode,
  IconCopy,
  IconDownload,
  IconExternal,
  IconEye,
  IconFile,
} from "../icons";

/**
 * Cartão de um arquivo criado pela Nébula.
 *
 * Mostra o nome, deixa pré-visualizar (HTML), abrir no navegador, baixar e
 * copiar o código. É o que transforma "código no chat" em "site pronto".
 */
export const Artifact = memo(function Artifact({
  file,
  project,
  streaming,
}: {
  file: FileSegment;
  project: string | null;
  streaming?: boolean;
}) {
  const [showPreview, setShowPreview] = useState(false);
  const [copied, setCopied] = useState(false);

  const url = fileUrl(project, file.name);
  const isHtml = /\.html?$/i.test(file.name);
  const canPreview = isHtml && !!url;
  const lines = file.content ? file.content.split("\n").length : 0;
  const ready = file.complete && !streaming;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(file.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard indisponível */
    }
  };

  return (
    <div
      className={`my-3 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900 ${
        streaming ? "nebula-rise" : ""
      }`}
    >
      <div className="relative flex items-center gap-2 border-b border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-800/60">
        <span className="accent-soft-bg accent-text flex h-7 w-7 shrink-0 items-center justify-center rounded-lg">
          <IconFile className="h-4 w-4" />
        </span>

        <span className="min-w-0 flex-1 truncate font-mono text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {file.name}
        </span>

        <span
          className={`shrink-0 text-xs ${
            ready
              ? "text-zinc-400"
              : "animate-pulse font-medium accent-text"
          }`}
        >
          {ready ? `${lines} linhas` : "escrevendo…"}
        </span>

        {/* barra de progresso deslizante enquanto o arquivo é escrito */}
        {!ready && <span className="nebula-progress-line" />}
      </div>

      {showPreview && url && canPreview && (
        <iframe
          src={url}
          title={`Pré-visualização de ${file.name}`}
          className="h-80 w-full border-0 bg-white"
          referrerPolicy="no-referrer"
        />
      )}

      {!showPreview && (
        <pre className="max-h-60 overflow-auto bg-zinc-50 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
          {file.content || "\n"}
          {/* cursor piscando no fim: mostra que o código ainda está sendo escrito */}
          {!ready && <span className="nebula-caret" aria-hidden="true" />}
        </pre>
      )}

      <div className="flex flex-wrap items-center gap-1 border-t border-zinc-200 px-2 py-1.5 dark:border-zinc-700">
        {canPreview && (
          <Action
            onClick={() => setShowPreview((value) => !value)}
            icon={showPreview ? <IconCode className="h-3.5 w-3.5" /> : <IconEye className="h-3.5 w-3.5" />}
            label={showPreview ? "Ver código" : "Pré-visualizar"}
            primary={!showPreview}
          />
        )}

        {url && (
          <Action
            onClick={() => openPreview({ url, name: file.name })}
            icon={<IconExternal className="h-3.5 w-3.5" />}
            label="Abrir"
          />
        )}

        {url && (
          <Action
            href={url}
            download={file.name.split("/").pop()}
            icon={<IconDownload className="h-3.5 w-3.5" />}
            label="Baixar"
          />
        )}

        <Action
          onClick={copy}
          icon={copied ? <IconCheck className="h-3.5 w-3.5" /> : <IconCopy className="h-3.5 w-3.5" />}
          label={copied ? "Copiado" : "Copiar"}
        />
      </div>
    </div>
  );
});

function Action({
  icon,
  label,
  primary,
  href,
  onClick,
  target,
  download,
}: {
  icon: React.ReactNode;
  label: string;
  primary?: boolean;
  href?: string;
  onClick?: () => void;
  target?: string;
  download?: string;
}) {
  const className = `flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition ${
    primary
      ? "accent-soft-bg accent-text"
      : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
  }`;

  if (href) {
    return (
      <a href={href} target={target} download={download} className={className}>
        {icon}
        {label}
      </a>
    );
  }

  return (
    <button onClick={onClick} className={className}>
      {icon}
      {label}
    </button>
  );
}
