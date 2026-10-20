import { memo, useEffect, useMemo, useRef, useState } from "react";

import type {
  ApprovalRequest,
  Attachment,
  ErrorKind,
  Message,
  ProgressStage,
  ToolEntry,
} from "../api";
import { parseSegments } from "../segments";
import { stopSpeaking, toggleSpeak, useSpeaking } from "../voice";
import { Artifact } from "./Artifact";
import { Composer } from "./Composer";
import { Markdown } from "./Markdown";
import {
  IconCheck,
  IconCopy,
  IconGlobe,
  IconGlobeOff,
  IconMenu,
  IconMoon,
  IconPencil,
  IconRefresh,
  IconSparkle,
  IconSpeaker,
  IconStop,
  IconSun,
} from "../icons";

const SUGGESTIONS = [
  {
    label: "Planejar",
    text: "Monte um roteiro de viagem de 5 dias para Paris com orçamento enxuto.",
  },
  {
    label: "Aprender",
    text: "Explique como funciona uma API REST para quem está começando.",
  },
  {
    label: "Escrever",
    text: "Escreva um e-mail profissional agradecendo por uma reunião.",
  },
  {
    label: "Criar site",
    text: "Crie um site de portfólio simples com index.html e style.css, com fundo escuro e um cartão de contato.",
  },
];

interface ChatProps {
  messages: Message[];
  project: string | null;
  sending: boolean;
  stage: ProgressStage | null;
  /** Rótulo do estágio vindo do backend ("Executando comando", "Lendo"...). */
  stageLabel?: string | null;
  /** Passos das ferramentas da Nébula (painel de atividade da resposta). */
  toolLog?: ToolEntry[];
  /** Comando fora do projeto esperando o "Permitir/Negar" do usuário. */
  approval?: ApprovalRequest | null;
  onApprove?: (approved: boolean) => void;
  error: string | null;
  errorKind: ErrorKind;
  canRetry: boolean;
  onRetry: () => void;
  modelName: string;
  /** Modo off ligado: o site gerado sai sem CDN nem internet. */
  offlineSite: boolean;
  onToggleOffline: () => void;
  keyMissing: boolean;
  dark: boolean;
  onToggleTheme: () => void;
  onSend: (text: string, attachments?: Attachment[], image?: boolean) => void;
  onStop?: () => void;
  onRegenerate?: () => void;
  onEdit?: (index: number) => void;
  onOpenSidebar: () => void;
  /** Abre a biblioteca de projetos (itens do "+" do composer). */
  onOpenProjects: () => void;
  /** Inicia a conversa por voz hands-free. */
  onStartCall: () => void;
}

export function Chat({
  messages,
  project,
  sending,
  stage,
  stageLabel,
  toolLog,
  approval,
  onApprove,
  error,
  errorKind,
  canRetry,
  onRetry,
  modelName,
  offlineSite,
  onToggleOffline,
  keyMissing,
  dark,
  onToggleTheme,
  onSend,
  onStop,
  onRegenerate,
  onEdit,
  onOpenSidebar,
  onOpenProjects,
  onStartCall,
}: ChatProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // Só rola para o fim se o usuário já estava lá (não empurra quem está lendo).
  const nearBottomRef = useRef(true);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    nearBottomRef.current = dist < 120;
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (el && nearBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [messages, sending, toolLog, approval]);

  // Ao trocar de conversa, volta a rolar automático e para a voz.
  useEffect(() => {
    nearBottomRef.current = true;
    stopSpeaking();
  }, [messages[0]?.id]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 px-4 py-3 md:px-6">
        <button
          onClick={onOpenSidebar}
          className="rounded-full p-2 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 md:hidden"
          aria-label="Abrir menu"
        >
          <IconMenu className="h-5 w-5" />
        </button>

        <span className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-zinc-600 dark:text-zinc-300">
          <span className="max-w-[46vw] truncate sm:max-w-none">{modelName}</span>
          <IconSparkle className="accent-text h-4 w-4 shrink-0" />
        </span>

        <span className="ml-auto flex items-center gap-1">
          <button
            onClick={onToggleOffline}
            aria-pressed={offlineSite}
            aria-label={
              offlineSite
                ? "Modo offline ligado: sites abrem sem internet"
                : "Modo online: sites usam CDN (precisa de internet)"
            }
            title={
              offlineSite
                ? "Modo offline: sites abrem sem internet"
                : "Modo online: sites usam CDN"
            }
            /* azul/destaque = online (padrão); sem cor = modo off */
            className={`rounded-full p-2 transition ${
              offlineSite
                ? "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                : "accent-soft-bg accent-text"
            }`}
          >
            {offlineSite ? (
              <IconGlobeOff className="h-5 w-5" />
            ) : (
              <IconGlobe className="h-5 w-5" />
            )}
          </button>

          <button
            onClick={onToggleTheme}
            className="rounded-full p-2 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            aria-label="Alternar tema claro/escuro"
          >
            {dark ? <IconSun className="h-5 w-5" /> : <IconMoon className="h-5 w-5" />}
          </button>
        </span>
      </header>

      {keyMissing && (
        <div className="mx-4 mb-1 rounded-2xl bg-amber-50 px-4 py-2.5 text-sm text-amber-800 dark:bg-amber-950/50 dark:text-amber-200 md:mx-6">
          Nenhuma chave configurada. Abra o arquivo <code>backend/.env</code> e
          preencha <code>GEMINI_API_KEY</code> (instruções no README).
        </div>
      )}

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 md:px-6"
      >
        {isEmpty ? (
          <Welcome onPick={onSend} />
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-7 py-4">
            {messages.map((message, index) => {
              const isLast = index === messages.length - 1;
              const streaming = sending && isLast;

              // Ainda não chegou nenhum pedaço da resposta: mostra os pontinhos.
              if (streaming && message.role === "model" && message.content === "") {
                return (
                  <Typing
                    key={`typing-${index}`}
                    stage={stage}
                    label={stageLabel}
                  />
                );
              }

              return (
                <Bubble
                  key={message.id ?? `${message.role}-${index}`}
                  message={message}
                  project={project}
                  streaming={streaming}
                  onRegenerate={
                    isLast && message.role === "model" && !sending
                      ? onRegenerate
                      : undefined
                  }
                  onEdit={
                    message.role === "user" && index !== messages.length - 1
                      ? () => onEdit?.(index)
                      : undefined
                  }
                />
              );
            })}
          </div>
        )}

        <ToolPanel
          entries={toolLog ?? []}
          approval={approval ?? null}
          onApprove={onApprove}
        />
      </div>

      <div className="px-4 pb-4 md:px-6">
        <div className="mx-auto w-full max-w-3xl">
          {error && (
            <div
              className={`nebula-pop mb-2 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl px-4 py-2.5 text-sm ${
                errorKind === "limit"
                  ? "bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200"
                  : "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300"
              }`}
            >
              <span className="min-w-0 flex-1">{error}</span>

              {canRetry && !sending && (
                <button
                  onClick={onRetry}
                  className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold transition ${
                    errorKind === "limit"
                      ? "bg-amber-100 text-amber-900 hover:bg-amber-200 dark:bg-amber-500/20 dark:text-amber-100 dark:hover:bg-amber-500/30"
                      : "bg-red-100 text-red-800 hover:bg-red-200 dark:bg-red-500/20 dark:text-red-100 dark:hover:bg-red-500/30"
                  }`}
                >
                  Tentar de novo
                </button>
              )}
            </div>
          )}

          <Composer
            sending={sending}
            onSend={onSend}
            onStop={onStop}
            onOpenProjects={onOpenProjects}
            onStartCall={onStartCall}
          />

          <p className="mt-2 text-center text-xs text-zinc-400">
            Nébula pode cometer erros. Confira informações importantes.
          </p>
        </div>
      </div>
    </div>
  );
}

function Welcome({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col justify-center py-6">
      <h1 className="accent-gradient bg-clip-text text-4xl font-semibold leading-tight text-transparent md:text-5xl">
        Olá 👋
        <br />
        Como posso ajudar hoje?
      </h1>

      <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion.label}
            onClick={() => onPick(suggestion.text)}
            className="rounded-2xl border border-zinc-200 bg-zinc-50 p-4 text-left transition hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            <span className="block text-sm font-semibold text-zinc-800 dark:text-zinc-100">
              {suggestion.label}
            </span>
            <span className="mt-1 block text-sm text-zinc-500 dark:text-zinc-400">
              {suggestion.text}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * memo evita redesenhar bolhas que não mudaram. Sem isso, cada tecla digitada
 * (e cada pedacinho que chega no streaming) reprocessava todo o markdown da
 * conversa — era isso que deixava a digitação travada.
 */
const Bubble = memo(function Bubble({
  message,
  project,
  streaming,
  onRegenerate,
  onEdit,
}: {
  message: Message;
  project: string | null;
  streaming?: boolean;
  onRegenerate?: () => void;
  onEdit?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  // Qual mensagem está na boca da Nébula agora (só ela mostra "Parar").
  const speakingText = useSpeaking();
  const speakingThis = speakingText !== null && speakingText === message.content;

  // Só reinterpreta o texto quando ele muda de verdade.
  const segments = useMemo(
    () => parseSegments(message.content),
    [message.content]
  );

  // Último bloco de TEXTO: o "Copiar" dele vai pro rodapé, na mesma linha
  // do "Ouvir" (um do lado do outro, mesma altura) — os blocos anteriores
  // continuam com o botão próprio embaixo de cada um.
  let lastTextIndex = -1;
  segments.forEach((segment, index) => {
    if (segment.type === "text") lastTextIndex = index;
  });

  const footerCopyText =
    lastTextIndex >= 0 &&
    lastTextIndex === segments.length - 1 && // mensagem termina em texto
    segments[lastTextIndex].type === "text"
      ? segments[lastTextIndex].content
      : "";

  const copy = async () => {
    if (!footerCopyText) return;
    try {
      await navigator.clipboard.writeText(footerCopyText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard indisponível */
    }
  };

  if (message.role === "user") {
    return (
      <div className="nebula-rise flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl accent-soft-bg px-4 py-3 text-[15px] leading-relaxed text-zinc-800 dark:text-zinc-100">
          {message.attachments?.map((att, i) => (
            <div key={`${att.name}-${i}`} className="mb-2 flex items-center gap-2 rounded-2xl bg-white/70 px-2 py-1 text-xs dark:bg-zinc-900/50">
              {att.mime_type.startsWith("image/") ? "🖼️" : "📎"} {att.name}
            </div>
          ))}
          {message.content}
          {onEdit && (
            <button
              onClick={onEdit}
              className="mt-2 flex items-center gap-1.5 rounded-full px-2 py-1 text-xs text-zinc-500 transition hover:bg-white/70 dark:hover:bg-zinc-900/60"
            >
              <IconPencil className="h-3.5 w-3.5" /> Editar
            </button>
          )}
        </div>
      </div>
    );
  }

  const lastIndex = segments.length - 1;

  return (
    <div className="nebula-rise flex gap-3">
      <span className="accent-gradient mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white">
        <IconSparkle className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        {segments.map((segment, index) => {
          if (segment.type === "file") {
            return (
              <Artifact
                key={`file-${index}`}
                file={segment}
                project={project}
                streaming={streaming && index === lastIndex}
              />
            );
          }

          // O cursor só pisca no último pedaço de texto enquanto a resposta chega.
          const cursor = streaming && index === lastIndex ? " ▍" : "";
          return (
            <Markdown
              key={`text-${index}`}
              content={segment.content + cursor}
              streaming={streaming && index === lastIndex}
              copyable={index !== lastTextIndex || !footerCopyText}
            />
          );
        })}

        {!streaming && message.content.trim() !== "" && (
          <div className="mt-2 flex flex-wrap items-center gap-1">
            {footerCopyText && (
              <button
                onClick={copy}
                className="flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-1 text-xs leading-none text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
              >
                {copied ? (
                  <IconCheck className="h-3.5 w-3.5" />
                ) : (
                  <IconCopy className="h-3.5 w-3.5" />
                )}
                {copied ? "Copiado" : "Copiar"}
              </button>
            )}
            <button
              onClick={() => toggleSpeak(message.content)}
              className="flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-1 text-xs leading-none text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
            >
              {speakingThis ? (
                <IconStop className="h-3.5 w-3.5" />
              ) : (
                <IconSpeaker className="h-3.5 w-3.5" />
              )}
              {speakingThis ? "Parar" : "Ouvir"}
            </button>
            {onRegenerate && (
              <button
                onClick={onRegenerate}
                className="flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-1 text-xs leading-none text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
              >
                <IconRefresh className="h-3.5 w-3.5" /> Regerar
              </button>
            )}
          </div>
        )}

        {!streaming && message.sources && message.sources.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-zinc-400">Fontes:</span>
            {message.sources.slice(0, 6).map((source) => (
              <a
                key={source.url}
                href={source.url}
                target="_blank"
                rel="noreferrer"
                title={source.url}
                className="max-w-[220px] truncate rounded-full border border-zinc-200 px-2 py-0.5 text-xs text-zinc-500 transition hover:border-[var(--accent)] hover:text-[var(--accent)] dark:border-zinc-700 dark:text-zinc-400"
              >
                {source.title}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});

function Typing({
  stage,
  label,
}: {
  stage: ProgressStage | null;
  label?: string | null;
}) {
  // Conta os segundos: o modelo pode levar alguns segundos antes de falar, e
  // ver o tempo passando deixa claro que ele está trabalhando (não travado).
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(
      () => setSeconds(Math.floor((Date.now() - started) / 1000)),
      1000
    );
    return () => window.clearInterval(timer);
  }, []);

  // Rótulo do backend ("Executando comando…") quando chega; senão o padrão.
  const text = label || (stage === "tool" ? "Criando os arquivos" : "Pensando");

  return (
    <div className="nebula-rise flex gap-3">
      <span className="accent-gradient mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white">
        <IconSparkle className="h-3.5 w-3.5" />
      </span>
      <div className="flex items-center gap-2 py-2">
        <div className="flex items-center gap-1">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="accent-gradient h-2 w-2 animate-bounce rounded-full"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
        <span className="text-sm text-zinc-400">
          {text}…{seconds >= 3 ? ` ${seconds}s` : ""}
        </span>
      </div>
    </div>
  );
}

/**
 * Deixa URLs clicáveis dentro das notas das ferramentas (a URL do servidor
 * de teste precisa abrir direto no navegador do usuário).
 */
function Linkified({ text }: { text: string }) {
  const parts = text.split(/(https?:\/\/[^\s]+)/g);
  return (
    <>
      {parts.map((part, index) =>
        /^https?:\/\//.test(part) ? (
          <a
            key={index}
            href={part}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-sky-600 underline dark:text-sky-400"
          >
            {part}
          </a>
        ) : (
          <span key={index}>{part}</span>
        )
      )}
    </>
  );
}

/**
 * Painel de atividade da Nébula: lista cada ferramenta usada (ler, escrever,
 * executar…) e, quando um comando sai da pasta do projeto, mostra o cartão
 * "Permitir/Negar" — o comando só roda depois que o usuário responder.
 */
function ToolPanel({
  entries,
  approval,
  onApprove,
}: {
  entries: ToolEntry[];
  approval: ApprovalRequest | null;
  onApprove?: (approved: boolean) => void;
}) {
  if (entries.length === 0 && !approval) return null;

  return (
    <div className="nebula-rise mx-auto mt-3 w-full max-w-3xl rounded-2xl border border-zinc-200 bg-zinc-50/80 px-3 py-2.5 text-xs dark:border-zinc-800 dark:bg-zinc-900/70">
      <div className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
        Ferramentas
      </div>

      <ul className="flex flex-col gap-1">
        {entries.map((entry) => (
          <li
            key={entry.seq}
            className="flex items-start gap-2 rounded-lg px-1.5 py-1"
          >
            <span className="mt-px shrink-0" aria-hidden>
              {entry.phase !== "end"
                ? "⏳"
                : entry.ok === false
                  ? "❌"
                  : "✅"}
            </span>
            <div className="min-w-0 flex-1">
              <span className="block break-all font-mono text-[11px] leading-relaxed text-zinc-600 dark:text-zinc-300">
                <span className="font-semibold text-zinc-700 dark:text-zinc-200">
                  {entry.name}
                </span>
                {entry.detail ? ` · ${entry.detail}` : ""}
                {entry.phase === "end" && entry.seconds !== undefined
                  ? ` · ${entry.seconds}s`
                  : ""}
              </span>
              {entry.phase === "end" &&
                entry.note &&
                entry.note !== "ok" &&
                !/^exit \d+$/.test(entry.note) && (
                  <span className="block break-all font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
                    {entry.ok === false ? "— " : "· "}
                    <Linkified text={entry.note} />
                  </span>
                )}
            </div>
          </li>
        ))}
      </ul>

      {approval && (
        <div className="mt-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-950/50">
          <p className="text-[11px] font-semibold text-amber-800 dark:text-amber-200">
            A Nébula quer rodar um comando fora da pasta do projeto
            <span className="font-normal"> — {approval.reason}</span>
          </p>
          <code className="mt-1 block break-all rounded-lg bg-white/80 px-2 py-1 font-mono text-[11px] text-zinc-700 dark:bg-black/40 dark:text-zinc-200">
            {approval.command}
          </code>
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => onApprove?.(true)}
              className="rounded-full bg-emerald-600 px-3 py-1 text-[11px] font-semibold text-white transition hover:bg-emerald-500 nebula-tap"
            >
              Permitir
            </button>
            <button
              onClick={() => onApprove?.(false)}
              className="rounded-full border border-zinc-300 px-3 py-1 text-[11px] font-semibold text-zinc-600 transition hover:bg-zinc-100 nebula-tap dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Negar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
