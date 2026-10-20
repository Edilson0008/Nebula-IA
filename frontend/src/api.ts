import { getSala } from "./sala";
import { getSettings } from "./settings";

export type Role = "user" | "model";

export interface Conversation {
  id: number;
  title: string;
  updated_at: string;
}

export interface Attachment {
  name: string;
  mime_type: string;
  data: string; // base64
}

/** Fonte da busca na web (chega no evento "sources" do streaming). */
export interface Source {
  title: string;
  url: string;
}

export interface Message {
  id?: number;
  role: Role;
  content: string;
  attachments?: Attachment[];
  /** Fontes citadas pela IA quando ela consultou a web. */
  sources?: Source[];
}

/** Projeto gerado (pasta de arquivos) — card da biblioteca. */
export interface ProjectInfo {
  project: string;
  title: string;
  conversation_id: number | null;
  files: { name: string; url: string }[];
}

/** Arquivo criado pela IA (vem no evento "files" do streaming). */
export interface FileInfo {
  name: string;
  url: string;
  lines: number;
}

/** Conteúdo de uma conversa: as mensagens e a pasta do projeto (se houver). */
export interface ConversationData {
  project: string | null;
  messages: Message[];
}

/** Fato guardado na memória de longo prazo. */
export interface Memory {
  id: number;
  content: string;
  created_at: string;
}

interface ChatResponse {
  conversation_id: number;
  reply: string;
  project: string | null;
  files: FileInfo[];
}

export interface Health {
  status: string;
  model: string;
  embedding_model: string;
  api_key_configured: boolean;
}

/** Estágio de andamento da resposta (enquanto o modelo trabalha). */
export type ProgressStage = "thinking" | "tool";

/** Ferramenta do agente no meio da resposta (evento "tool" do streaming). */
export interface ToolEntry {
  seq: number;
  name: string;
  detail: string;
  phase: "start" | "progress" | "end";
  ok?: boolean;
  seconds?: number;
  note?: string;
}

/** Comando fora do projeto esperando aprovação (evento "approval"). */
export interface ApprovalRequest {
  id: string;
  command: string;
  reason: string;
}

export interface StreamHandlers {
  onMeta?: (conversationId: number) => void;
  onDelta?: (text: string) => void;
  onFiles?: (files: FileInfo[], project: string | null) => void;
  onModel?: (model: string) => void;
  /** Avisos de andamento: "pensando…", "executando comando…". */
  onStatus?: (stage: ProgressStage, label?: string) => void;
  /** Cada passo das ferramentas da Nébula (ler, escrever, executar…). */
  onTool?: (entry: ToolEntry) => void;
  /** Pedido de aprovação de um comando que sai do projeto. */
  onApproval?: (request: ApprovalRequest) => void;
  /** Fontes da busca na web (chega antes do "done"). */
  onSources?: (sources: Source[]) => void;
  /** Cópia do banco (chega no fim): o site guarda no aparelho. */
  onCofre?: (dados: string) => void;
  onDone?: () => void;
}

/** "limit" = cota momentânea (passa sozinho); "error" = falha de verdade. */
export interface BackupStats {
  conversas: number;
  mensagens: number;
  memorias: number;
}

export interface BackupExport {
  dados: string;
  estatisticas: BackupStats;
}

export type ErrorKind = "limit" | "error";
/** Erro vindo do stream, com o tipo junto para a tela escolher o visual. */
export class StreamError extends Error {
  kind: ErrorKind;

  constructor(message: string, kind: ErrorKind = "error") {
    super(message);
    this.name = "StreamError";
    this.kind = kind;
  }
}

type StreamEvent =
  | { type: "meta"; conversation_id: number }
  | { type: "status"; stage: ProgressStage; label?: string }
  | {
      type: "tool";
      phase: "start" | "progress" | "end";
      seq: number;
      name: string;
      detail?: string;
      ok?: boolean;
      seconds?: number;
      note?: string;
    }
  | { type: "approval"; id: string; command: string; reason: string }
  | { type: "delta"; text: string }
  | { type: "sources"; sources: Source[] }
  | { type: "files"; files: FileInfo[]; project: string | null }
  | { type: "error"; message: string; kind?: ErrorKind }
  | { type: "done"; model?: string | null }
  | { type: "cofre"; dados: string };

interface ChatRequestBody {
  message: string;
  conversation_id: number | null;
  use_memory: boolean;
  /** Site gerado sem dependência de internet (modo off). */
  offline?: boolean;
  /** Personalidade (painel de Ajustes; vazio = padrão). */
  ai_name?: string;
  user_name?: string;
  tone?: string;
  reply_size?: string;
  attachments?: Attachment[];
  regenerate?: boolean;
  edit_message_id?: number;
  /** Pedido direto de imagem (botão "+" → "Gerar imagem"). */
  image?: boolean;
}

function getGeminiKey(): string {
  try {
    return localStorage.getItem("nebula:gemini-key") || "";
  } catch {
    return "";
  }
}

export function getGeminiKeyValue(): string {
  return getGeminiKey();
}

export function setGeminiKeyValue(key: string): void {
  try {
    localStorage.setItem("nebula:gemini-key", key.trim());
  } catch {}
}

export function clearGeminiKeyValue(): void {
  try {
    localStorage.removeItem("nebula:gemini-key");
  } catch {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const key = getGeminiKey();
  const headers = new Headers(init?.headers as HeadersInit);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (key) headers.set("X-Gemini-Key", key);
  const sala = getSala();
  if (sala) headers.set("X-Nebula-Sala", sala);
  const res = await fetch(`/api${path}`, {
    headers,
    ...init,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail =
      body && typeof body.detail === "string"
        ? body.detail
        : `Erro ${res.status} ao falar com o servidor.`;
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

/**
 * Envia a mensagem e recebe a resposta em pedaços (Server-Sent Events),
 * chamando onDelta a cada trecho de texto que chega.
 */
async function chatStream(
  message: string,
  conversationId: number | null,
  useMemory: boolean,
  handlers: StreamHandlers,
  siteOffline = false,
  attachments?: Attachment[],
  regenerate = false,
  editMessageId?: number,
  image = false
): Promise<void> {
  // Personalidade do painel de Ajustes (vai junto em toda mensagem).
  const style = getSettings();
  const body: ChatRequestBody = {
    message,
    conversation_id: conversationId,
    use_memory: useMemory,
    offline: siteOffline,
    ai_name: style.aiName || undefined,
    user_name: style.userName || undefined,
    tone: style.tone || undefined,
    reply_size: style.replySize || undefined,
    attachments,
    regenerate,
    edit_message_id: editMessageId,
    image: image || undefined,
  };

  const key = getGeminiKey();
  const headers = new Headers({ "Content-Type": "application/json" });
  if (key) headers.set("X-Gemini-Key", key);
  const sala = getSala();
  if (sala) headers.set("X-Nebula-Sala", sala);
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    const detail =
      body && typeof body.detail === "string"
        ? body.detail
        : `Erro ${res.status} ao falar com o servidor.`;
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamError: { message: string; kind: ErrorKind } | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const line = block.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;

      const event = JSON.parse(line.slice(5).trim()) as StreamEvent;

      if (event.type === "meta") handlers.onMeta?.(event.conversation_id);
      else if (event.type === "status")
        handlers.onStatus?.(event.stage, event.label);
      else if (event.type === "tool")
        handlers.onTool?.({
          seq: event.seq,
          name: event.name,
          detail: event.detail ?? "",
          phase: event.phase,
          ok: event.ok,
          seconds: event.seconds,
          note: event.note,
        });
      else if (event.type === "approval")
        handlers.onApproval?.({
          id: event.id,
          command: event.command,
          reason: event.reason,
        });
      else if (event.type === "delta") handlers.onDelta?.(event.text);
      else if (event.type === "sources") handlers.onSources?.(event.sources);
      else if (event.type === "files")
        handlers.onFiles?.(event.files, event.project);
      else if (event.type === "done") {
        if (event.model) handlers.onModel?.(event.model);
        handlers.onDone?.();
      } else if (event.type === "cofre") {
        handlers.onCofre?.(event.dados);
      } else if (event.type === "error") {
        streamError = { message: event.message, kind: event.kind ?? "error" };
      }
    }

    if (streamError) {
      await reader.cancel().catch(() => undefined);
      break;
    }
  }

  if (streamError) throw new StreamError(streamError.message, streamError.kind);
}

export const api = {
  health: () => request<Health>("/health"),

  chat: (message: string, conversationId: number | null, useMemory = true) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        use_memory: useMemory,
      }),
    }),

  chatStream,

  conversations: () => request<Conversation[]>("/conversations"),

  messages: (conversationId: number) =>
    request<ConversationData>(`/conversations/${conversationId}`),

  removeConversation: (conversationId: number) =>
    request<{ deleted: number }>(`/conversations/${conversationId}`, {
      method: "DELETE",
    }),

  renameConversation: (conversationId: number, title: string) =>
    request<{ id: number; title: string }>(
      `/conversations/${conversationId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ title }),
      }
    ),

  /** Biblioteca de projetos: pastas com os sites que a IA já gerou. */
  projects: () => request<ProjectInfo[]>("/files"),

  memories: () => request<Memory[]>("/memories"),

  /** Responde um cartão de aprovação (Permitir/Negar) de comando do agente. */
  approve: (id: string, approved: boolean) =>
    request<{ ok: boolean }>("/approvals", {
      method: "POST",
      body: JSON.stringify({ id, approved }),
    }),

  removeMemory: (memoryId: number) =>
    request<{ deleted: number }>(`/memories/${memoryId}`, { method: "DELETE" }),

  // ------- Cópia de segurança (o servidor grátis apaga o disco) -------

  backupStatus: () =>
    request<{ vazio: boolean; estatisticas: BackupStats }>("/backup/status"),

  backupExport: () => request<BackupExport>("/backup/export"),

  backupImport: (dados: string) =>
    request<{ ok: boolean; restaurado: BackupStats }>("/backup/import", {
      method: "POST",
      body: JSON.stringify({ dados }),
    }),
};
