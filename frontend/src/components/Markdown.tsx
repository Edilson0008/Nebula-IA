import { memo, useRef, useState } from "react";
import type { ReactNode } from "react";

import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

import { IconCheck, IconCopy, IconDownload } from "../icons";

/**
 * Renderiza a resposta do modelo como markdown
 * (negrito, listas, tabelas, links e blocos de código com realce).
 * O visual fica em `.md`, definido em src/index.css.
 *
 * É memo: converter markdown + realce de código é caro, então só refaz quando
 * o texto realmente muda.
 *
 * `streaming` anima a entrada dos blocos de código enquanto a resposta chega
 * (o bloco "sobe" e a barra de progresso desliza até o texto terminar).
 */
export const Markdown = memo(function Markdown({
  content,
  streaming,
  copyable,
}: {
  content: string;
  streaming?: boolean;
  /** Cada bloco de texto tem o próprio "Copiar" (o da ponta copia tudo). */
  copyable?: boolean;
}) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: (props) => <CodeBlock {...props} streaming={streaming} />,
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          img: ({ src, alt }) => <ChatImage src={src} alt={alt} />,
        }}
      >
        {content}
      </ReactMarkdown>

      {copyable && !streaming && <CopyTextButton text={content} />}
    </div>
  );
});

/**
 * "Copiar" de cada bloco de texto: copia SÓ aquele pedaço da resposta,
 * não a mensagem inteira. Some enquanto a resposta ainda chega.
 */
function CopyTextButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard indisponível */
    }
  };

  return (
    <button
      onClick={copy}
      className="mt-1 flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-1 text-xs leading-none text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
      aria-label="Copiar bloco de texto"
    >
      {copied ? (
        <IconCheck className="h-3.5 w-3.5" />
      ) : (
        <IconCopy className="h-3.5 w-3.5" />
      )}
      {copied ? "Copiado" : "Copiar"}
    </button>
  );
}

/**
 * Imagem da resposta (foto gerada pela IA).
 *
 * Se o arquivo não existir mais, mostra um aviso discreto no lugar do
 * "quadrado quebrado" com o texto alternativo do navegador.
 */
function ChatImage({ src, alt }: { src?: string; alt?: string }) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <span className="my-2 block rounded-xl border border-dashed border-zinc-300 bg-zinc-50 px-3 py-2 text-xs text-zinc-500 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-400">
        Essa imagem não ficou salva. Me pede de novo que eu gero outra. 🎨
      </span>
    );
  }

  return (
    <span className="group relative my-2 inline-block max-w-full">
      <img
        src={src}
        alt={alt ?? ""}
        loading="lazy"
        onError={() => setFailed(true)}
      />

      {/* Baixar: SEMPRE visível (em toque não existe hover). Mesmo origem
          (/files/ via proxy), então o download é direto. */}
      <button
        onClick={() => downloadImage(src, alt)}
        className="absolute bottom-2 right-2 flex items-center gap-1 rounded-lg bg-black/60 px-2.5 py-1.5 text-xs font-medium text-white backdrop-blur transition active:scale-95 hover:bg-black/80"
        aria-label="Baixar imagem"
      >
        <IconDownload className="h-4 w-4" />
        Baixar
      </button>
    </span>
  );
}

/**
 * Baixa a imagem pra galeria do celular/PC.
 *
 * Usa fetch + blob (em vez de um link simples) pra garantir que o navegador
 * SALVE o arquivo em vez de abrir a imagem numa aba nova, e pra nomear o
 * arquivo direitinho a partir do alt/URL.
 */
async function downloadImage(src: string, alt?: string) {
  try {
    const response = await fetch(src);
    if (!response.ok) throw new Error("falha ao baixar");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filenameFor(src, alt);
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch {
    /* rede/offline: abre na aba como plano B */
    window.open(src, "_blank", "noopener");
  }
}

/** Nome de arquivo amigável: "imagem-1792381944.jpg" ou o alt + extensão. */
function filenameFor(src: string, alt?: string): string {
  const clean = (alt ?? "").trim().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
  const fromUrl = (src.split("/").pop() ?? "").split("?")[0];
  const ext = (fromUrl.match(/\.[a-z0-9]+$/i)?.[0] ?? ".jpg").toLowerCase();
  if (fromUrl) return clean ? `${clean}${ext}` : fromUrl;
  return `imagem${ext}`;
}

/** Bloco de código com botão de copiar (+ animação enquanto é escrito). */
function CodeBlock({
  children,
  streaming,
}: {
  children?: ReactNode;
  streaming?: boolean;
}) {
  const ref = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const text = ref.current?.innerText ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard indisponível */
    }
  };

  return (
    <div className={`group relative my-3 ${streaming ? "nebula-rise" : ""}`}>
      <pre ref={ref}>{children}</pre>

      {/* barra de progresso deslizante: o bloco ainda está sendo escrito */}
      {streaming && <span className="nebula-progress-line" />}

      {/* SEMPRE visível: em toque não existe hover, e a pessoa precisa copiar
          só este bloco sem levar a resposta inteira junto. */}
      <button
        onClick={copy}
        className="absolute right-2 top-2 flex items-center gap-1 rounded-lg bg-black/55 px-2 py-1 text-xs font-medium text-white backdrop-blur transition active:scale-95 hover:bg-black/80"
        aria-label="Copiar código"
      >
        {copied ? (
          <IconCheck className="h-3.5 w-3.5" />
        ) : (
          <IconCopy className="h-3.5 w-3.5" />
        )}
        {copied ? "Copiado" : "Copiar"}
      </button>
    </div>
  );
}
