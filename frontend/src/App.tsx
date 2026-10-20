import { useCallback, useEffect, useRef, useState } from "react";

import { api, StreamError, getGeminiKeyValue } from "./api";
import { ApiKeyGate } from "./components/ApiKeyGate";
import { guardarCofre, sincronizar } from "./cofre";
import type {
  ApprovalRequest,
  Attachment,
  Conversation,
  ErrorKind,
  Message,
  ProgressStage,
  ToolEntry,
} from "./api";
import { prettyModel } from "./modelLabel";
import { Sidebar } from "./components/Sidebar";
import { Chat } from "./components/Chat";
import { MemoryPanel } from "./components/MemoryPanel";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { PreviewOverlay } from "./components/PreviewOverlay";
import { ProjectsOverlay } from "./components/ProjectsOverlay";
import { SettingsOverlay } from "./components/SettingsOverlay";
import { Backdrop } from "./components/Backdrop";
import { getSettings, useSettings } from "./settings";
import { speakText } from "./voice";
import { useVoiceCall, useCallActive } from "./call";
import { VoiceCall } from "./components/VoiceCall";

const MODEL_FALLBACK = "Gemini";

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [project, setProject] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorKind, setErrorKind] = useState<ErrorKind>("error");
  // Guarda o texto da última tentativa que falhou, para o botão "Tentar de novo".
  const [retryText, setRetryText] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  // Biblioteca de projetos gerados e painel de Ajustes.
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Conversa esperando confirmação: só apagamos depois que o usuário confirmar.
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  // Conversa em edição de título (diálogo "Renomear").
  const [pendingRename, setPendingRename] = useState<Conversation | null>(null);
  const [renameText, setRenameText] = useState("");
  const [useMemory, setUseMemory] = useState(
    () => localStorage.getItem("useMemory") !== "off"
  );
  const [dark, setDark] = useState(
    () => localStorage.getItem("theme") === "dark"
  );
  const [modelName, setModelName] = useState(MODEL_FALLBACK);
  const [keyMissing, setKeyMissing] = useState(false);
  // Modo off: o site gerado não pode depender de internet (sem CDN nenhum).
  const [offlineSite, setOfflineSite] = useState(
    () => localStorage.getItem("siteOffline") === "on"
  );
  // Estágio atual da resposta ("pensando…", "criando arquivos…").
  const [stage, setStage] = useState<ProgressStage | null>(null);
  // Painel do agente: ferramentas executadas, rótulo do estágio e o pedido
  // de aprovação de um comando que sai da pasta do projeto.
  const [stageLabel, setStageLabel] = useState<string | null>(null);
  const [toolLog, setToolLog] = useState<ToolEntry[]>([]);
  const [pendingApproval, setPendingApproval] =
    useState<ApprovalRequest | null>(null);
  const pendingApprovalRef = useRef<ApprovalRequest | null>(null);
  pendingApprovalRef.current = pendingApproval;

  const activeIdRef = useRef<number | null>(null);
  activeIdRef.current = activeId;

  // Espelho das mensagens: o loop da conversa por voz lê a última resposta
  // sem ficar com closure velha.
  const messagesRef = useRef<Message[]>(messages);
  messagesRef.current = messages;

  useEffect(() => {
    localStorage.setItem("useMemory", useMemory ? "on" : "off");
  }, [useMemory]);

  useEffect(() => {
    localStorage.setItem("siteOffline", offlineSite ? "on" : "off");
  }, [offlineSite]);

  // Ajuste "falar respostas": quando o streaming termina, ela lê o que chegou.
  // (Lê do store global da chamada — evita usar `callActive`, declarado mais
  // abaixo, que o TypeScript acusaria de "usado antes de declarado".)
  const inCall = useCallActive();
  const wasSendingRef = useRef(false);
  useEffect(() => {
    const finished = wasSendingRef.current && !sending;
    wasSendingRef.current = sending;
    // Na conversa por voz, o próprio loop fala a resposta — não duplica.
    if (!finished || inCall || !getSettings().speak) return;
    const last = messages[messages.length - 1];
    if (last?.role === "model" && last.content.trim()) speakText(last.content);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sending, messages, inCall]);

  useEffect(() => {
    api
      .health()
      .then((health) => {
        // Só cobra a chave se o usuário ainda não colou a dele.
        setKeyMissing(!health.api_key_configured && !getGeminiKeyValue());
        setModelName(prettyModel(health.model));
      })
      .catch(() => {
        /* backend fora do ar: o erro aparece ao enviar */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.conversations());
    } catch {
      /* o erro já aparece ao enviar/receber mensagens */
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  // Cofre: mantém uma cópia das conversas no aparelho. Se o servidor grátis
  // reiniciar e perder tudo, a cópia é devolvida automaticamente.
  //
  // Roda também a cada mudança na lista de conversas, para a cópia nunca
  // ficar desatualizada (o servidor grátis apaga o disco quando quer).
  useEffect(() => {
    let ativo = true;
    (async () => {
      try {
        const r = await sincronizar();
        if (!ativo) return;
        if (r.acao === "enviou") {
          await refreshConversations();
        }
      } catch {
        /* servidor fora do ar: tenta de novo na próxima abertura */
      }
    })();
    return () => {
      ativo = false;
    };
  }, [refreshConversations]);

  // Vigia do cofre: a cada 30s confere se o servidor ainda tem as conversas.
  // Se ele reiniciou e voltou vazio, devolve a cópia do aparelho na hora —
  // o usuário nem percebe a perda.
  useEffect(() => {
    let ativo = true;
    const id = window.setInterval(async () => {
      try {
        const r = await sincronizar();
        if (ativo && r.acao === "enviou") {
          await refreshConversations();
        }
      } catch {
        /* servidor dormindo: tenta no próximo ciclo */
      }
    }, 30000);
    return () => {
      ativo = false;
      window.clearInterval(id);
    };
  }, [refreshConversations]);
  const handleNew = () => {
    setActiveId(null);
    setMessages([]);
    setProject(null);
    setError(null);
    setSidebarOpen(false);
    resetAgentPanel();
  };

  const handleSelect = async (id: number) => {
    setActiveId(id);
    setError(null);
    setSidebarOpen(false);
    resetAgentPanel();
    try {
      const data = await api.messages(id);
      setMessages(data.messages);
      setProject(data.project);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar conversa.");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.removeConversation(id);
      if (activeIdRef.current === id) {
        setActiveId(null);
        setMessages([]);
        setProject(null);
      }
      await refreshConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao excluir conversa.");
    }
  };

  // Pede confirmação antes de apagar (como no app do Gemini).
  const requestDelete = (id: number) => {
    setPendingDelete(conversations.find((item) => item.id === id) ?? null);
  };

  // Abre o diálogo de renomear com o título atual já preenchido.
  const requestRename = (id: number) => {
    const alvo = conversations.find((item) => item.id === id);
    if (!alvo) return;
    setPendingRename(alvo);
    setRenameText(alvo.title);
  };

  const confirmRename = async () => {
    const alvo = pendingRename;
    const titulo = renameText.trim();
    setPendingRename(null);
    if (!alvo || !titulo || titulo === alvo.title) return;

    // Atualiza na hora (otimista) e manda para o servidor em paralelo.
    setConversations((prev) =>
      prev.map((item) =>
        item.id === alvo.id ? { ...item, title: titulo } : item
      )
    );
    try {
      await api.renameConversation(alvo.id, titulo);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Erro ao renomear conversa."
      );
      await refreshConversations();
    }
  };

  const confirmDelete = async () => {
    const target = pendingDelete;
    setPendingDelete(null);
    if (target) await handleDelete(target.id);
  };

  // Aborta a geração atual (botão "Parar"). O servidor guarda o texto parcial.
  const abortRef = useRef<AbortController | null>(null);

  const handleStop = () => {
    abortRef.current?.abort();
  };

  // Um passo de ferramenta chegou: atualiza (ou acrescenta) a linha no painel.
  const handleTool = useCallback((entry: ToolEntry) => {
    setToolLog((prev) => {
      const index = prev.findIndex((item) => item.seq === entry.seq);
      if (index === -1) return [...prev, entry];
      const next = [...prev];
      next[index] = { ...next[index], ...entry };
      return next;
    });
  }, []);

  const handleApproval = useCallback((request: ApprovalRequest) => {
    setPendingApproval(request);
  }, []);

  // Resposta ao cartão "Permitir/Negar": o backend destrava o comando na hora.
  const handleApprove = useCallback(async (approved: boolean) => {
    const request = pendingApprovalRef.current;
    setPendingApproval(null);
    if (!request) return;
    try {
      await api.approve(request.id, approved);
    } catch {
      /* se expirou, o backend já nega sozinho */
    }
  }, []);

  // Começo de uma nova resposta: o painel de ferramentas recomeça do zero.
  const resetAgentPanel = () => {
    setStageLabel(null);
    setToolLog([]);
    setPendingApproval(null);
  };

  const handleSend = async (
    text: string,
    attachments: Attachment[] = [],
    image = false
  ) => {
    const content = text.trim();
    if ((!content && attachments.length === 0) || sending) return;

    setError(null);
    setRetryText(null);
    setSending(true);
    setStage(null);
    resetAgentPanel();

    // Mensagem do usuário + um "espaço" para a resposta que vai chegar aos poucos.
    setMessages((prev) => [
      ...prev,
      { role: "user", content, attachments },
      { role: "model", content: "" },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    let targetId = activeIdRef.current;
    let received = false;

    try {
      await api.chatStream(
        content,
        targetId,
        useMemory,
        {
          onMeta: (conversationId) => {
            targetId = conversationId;
            setActiveId(conversationId);
            activeIdRef.current = conversationId;
          },
          onDelta: (chunk) => {
            received = true;
            if (activeIdRef.current !== targetId) return;

            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (!last || last.role !== "model") return prev;
              next[next.length - 1] = { ...last, content: last.content + chunk };
              return next;
            });
          },
          onFiles: (_files, fileProject) => {
            // Só atualiza se ainda estamos na conversa que pediu os arquivos.
            if (activeIdRef.current !== targetId) return;
            if (fileProject) setProject(fileProject);
          },
          onModel: (model) => setModelName(prettyModel(model)),
          onStatus: (value, label) => {
            if (activeIdRef.current !== targetId) return;
            setStage(value);
            setStageLabel(label ?? null);
          },
          onTool: (entry) => {
            if (activeIdRef.current !== targetId) return;
            handleTool(entry);
          },
          onApproval: (request) => {
            if (activeIdRef.current !== targetId) return;
            handleApproval(request);
          },
          onSources: (sources) => {
            if (activeIdRef.current !== targetId) return;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (!last || last.role !== "model") return prev;
              next[next.length - 1] = { ...last, sources };
              return next;
            });
          },
        },
        offlineSite,
        attachments,
        false,
        undefined,
        image
      );

      await refreshConversations();
    } catch (err) {
      // Parada manual: não é erro — fica com o que já chegou e mostra a barra
      // de novo (o servidor já gravou o trecho gerado).
      if (err instanceof DOMException && err.name === "AbortError") {
        await refreshConversations();
        return;
      }

      const msg = err instanceof Error ? err.message : "Erro ao enviar mensagem.";
      // Chave ausente/inválida: reabre o portão para a pessoa colar de novo.
      if (msg.startsWith("chave-api:")) {
        setKeyMissing(true);
        setError(msg.replace(/^chave-api:\s*/, ""));
      } else {
        setError(msg);
      }
      setErrorKind(err instanceof StreamError ? err.kind : "error");
      setRetryText(content);

      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        // tira a resposta vazia
        if (last?.role === "model" && last.content === "") next.pop();
        // se nada foi salvo no servidor, tira também a pergunta
        if (!received && next[next.length - 1]?.role === "user") next.pop();
        return next;
      });

      await refreshConversations();
    } finally {
      abortRef.current = null;
      setSending(false);
      setStage(null);
      // Guarda a cópia no aparelho logo após a resposta (protege do reinício
      // do servidor grátis). Não trava a interface.
      void guardarCofre();
    }
  };

  const handleRetry = () => {
    if (retryText) void handleSend(retryText);
  };

  // Pede a mesma resposta de novo, apagando a anterior (server-side).
  const handleRegenerate = async () => {
    if (sending || activeIdRef.current === null) return;

    setError(null);
    setRetryText(null);
    setSending(true);
    setStage(null);
    resetAgentPanel();

    // Some com a resposta antiga na hora e abre o "espaço" da nova.
    setMessages((prev) => {
      const next = [...prev];
      if (next[next.length - 1]?.role === "model") next.pop();
      next.push({ role: "model", content: "" });
      return next;
    });

    const controller = new AbortController();
    abortRef.current = controller;

    let received = false;

    try {
      await api.chatStream(
        "",
        activeIdRef.current,
        useMemory,
        {
          onDelta: (chunk) => {
            received = true;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (!last || last.role !== "model") return prev;
              next[next.length - 1] = { ...last, content: last.content + chunk };
              return next;
            });
          },
          onModel: (model) => setModelName(prettyModel(model)),
          onStatus: (value, label) => {
            setStage(value);
            setStageLabel(label ?? null);
          },
          onTool: handleTool,
          onApproval: handleApproval,
          onSources: (sources) => {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (!last || last.role !== "model") return prev;
              next[next.length - 1] = { ...last, sources };
              return next;
            });
          },
        },
        offlineSite,
        [],
        true
      );
      await refreshConversations();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        await refreshConversations();
        return;
      }
      setError(err instanceof Error ? err.message : "Erro ao regerar resposta.");
      setErrorKind(err instanceof StreamError ? err.kind : "error");
      setMessages((prev) => {
        const next = [...prev];
        if (next[next.length - 1]?.role === "model" && !received) next.pop();
        return next;
      });
      await refreshConversations();
    } finally {
      abortRef.current = null;
      setSending(false);
      setStage(null);
      // Guarda a cópia no aparelho logo após a resposta (protege do reinício
      // do servidor grátis). Não trava a interface.
      void guardarCofre();
    }
  };

  // Edita a pergunta do usuário e gera outra resposta a partir dela.
  const handleEditMessage = async (index: number) => {
    if (sending || activeIdRef.current === null) return;
    const alvo = messages[index];
    if (!alvo || alvo.role !== "user" || alvo.id === undefined) return;

    const novo = window.prompt("Editar mensagem", alvo.content);
    if (novo === null) return;
    const texto = novo.trim();
    if (!texto || texto === alvo.content) return;

    setError(null);
    setRetryText(null);
    setSending(true);
    setStage(null);
    resetAgentPanel();

    // Recorta a conversa: a mensagem editada vira a última e a resposta antiga
    // some (o servidor também apaga o resto).
    setMessages((prev) => [
      ...prev.slice(0, index + 1).map((m, i) =>
        i === index ? { ...m, content: texto } : m
      ),
      { role: "model", content: "" },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    let received = false;

    try {
      await api.chatStream(
        texto,
        activeIdRef.current,
        useMemory,
        {
          onDelta: (chunk) => {
            received = true;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (!last || last.role !== "model") return prev;
              next[next.length - 1] = { ...last, content: last.content + chunk };
              return next;
            });
          },
          onModel: (model) => setModelName(prettyModel(model)),
          onStatus: (value, label) => {
            setStage(value);
            setStageLabel(label ?? null);
          },
          onTool: handleTool,
          onApproval: handleApproval,
          onSources: (sources) => {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (!last || last.role !== "model") return prev;
              next[next.length - 1] = { ...last, sources };
              return next;
            });
          },
        },
        offlineSite,
        [],
        false,
        alvo.id
      );
      await refreshConversations();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        await refreshConversations();
        return;
      }
      setError(err instanceof Error ? err.message : "Erro ao editar mensagem.");
      setErrorKind(err instanceof StreamError ? err.kind : "error");
      setMessages((prev) => {
        const next = [...prev];
        if (next[next.length - 1]?.role === "model" && !received) next.pop();
        return next;
      });
      await refreshConversations();
    } finally {
      abortRef.current = null;
      setSending(false);
      setStage(null);
      // Guarda a cópia no aparelho logo após a resposta (protege do reinício
      // do servidor grátis). Não trava a interface.
      void guardarCofre();
    }
  };

  // Conversa por voz (hands-free): ouve → manda → fala → volta a ouvir.
  const sendViaVoice = useCallback(
    (text: string) => handleSend(text),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [handleSend]
  );
  const lastReply = useCallback(() => {
    const msgs = messagesRef.current;
    const last = msgs[msgs.length - 1];
    return last?.role === "model" ? last.content : "";
  }, []);
  const voiceCall = useVoiceCall({ send: sendViaVoice, lastReply });
  const { start: startCall, stop: stopCall } = voiceCall;

  const { accent } = useSettings();

  // Cor de destaque escolhida nos Ajustes: vira variável CSS global
  // (botões, gradientes, fundo aurora e cursor seguem ela).
  useEffect(() => {
    document.documentElement.style.setProperty("--accent", accent);
  }, [accent]);

  return (
    <div className="flex h-full w-full overflow-hidden bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      {/* Fundo animado (aurora/estrelas) atrás de todo o conteúdo. */}
      <Backdrop />

      <Sidebar
        conversations={conversations}
        activeId={activeId}
        open={sidebarOpen}
        onSelect={handleSelect}
        onNew={handleNew}
        onDelete={requestDelete}
        onRename={requestRename}
        onOpenMemory={() => setMemoryOpen(true)}
        onOpenProjects={() => setProjectsOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
        onClose={() => setSidebarOpen(false)}
      />

      <MemoryPanel
        open={memoryOpen}
        onClose={() => setMemoryOpen(false)}
        useMemory={useMemory}
        onToggleMemory={setUseMemory}
      />

      {/* Biblioteca dos sites gerados (abrir, conversa, baixar .zip). */}
      <ProjectsOverlay
        open={projectsOpen}
        onClose={() => setProjectsOpen(false)}
        onSelect={(conversationId) => {
          setProjectsOpen(false);
          void handleSelect(conversationId);
        }}
      />

      {/* Personalidade, voz e outros ajustes da Nébula. */}
      <SettingsOverlay
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />

      {/* Visor em tela cheia do botão "Abrir" (volta com o gesto do celular). */}
      <PreviewOverlay />

      {/* Conversa por voz hands-free (orb + ouvir/falar em loop). */}
      {voiceCall.active && (
        <VoiceCall
          phase={voiceCall.phase}
          heard={voiceCall.heard}
          lastUser={voiceCall.lastUser}
          lastAi={voiceCall.lastAi}
          fatal={voiceCall.fatal}
          onHangup={stopCall}
        />
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Excluir conversa?"
        message={
          pendingDelete
            ? `"${pendingDelete.title}" será apagada para sempre. Não dá para desfazer.`
            : ""
        }
        confirmLabel="Excluir"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />

      {pendingRename !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setPendingRename(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Renomear conversa"
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl dark:bg-zinc-900"
          >
            <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
              Renomear conversa
            </h2>
            <input
              autoFocus
              value={renameText}
              onChange={(event) => setRenameText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void confirmRename();
                if (event.key === "Escape") setPendingRename(null);
              }}
              className="mt-3 w-full rounded-xl bg-zinc-100 px-3 py-2.5 text-sm text-zinc-900 outline-none ring-1 ring-transparent focus:ring-blue-400 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder="Título da conversa"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setPendingRename(null)}
                className="rounded-full px-4 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                Cancelar
              </button>
              <button
                onClick={() => void confirmRename()}
                className="accent-gradient rounded-full px-4 py-2 text-sm font-medium text-white transition nebula-tap hover:brightness-110"
              >
                Salvar
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="relative flex min-w-0 flex-1 flex-col">
        <Chat
          messages={messages}
          project={project}
          sending={sending}
          stage={stage}
          stageLabel={stageLabel}
          toolLog={toolLog}
          approval={pendingApproval}
          onApprove={handleApprove}
          error={error}
          errorKind={errorKind}
          canRetry={retryText !== null}
          onRetry={handleRetry}
          modelName={modelName}
          offlineSite={offlineSite}
          onToggleOffline={() => setOfflineSite((value) => !value)}
          keyMissing={keyMissing}
          dark={dark}
          onToggleTheme={() => setDark((value) => !value)}
          onSend={handleSend}
          onStop={handleStop}
          onRegenerate={handleRegenerate}
          onEdit={handleEditMessage}
          onOpenSidebar={() => setSidebarOpen(true)}
          onOpenProjects={() => setProjectsOpen(true)}
          onStartCall={startCall}
        />
      </main>

      {keyMissing && (
        <ApiKeyGate
          onReady={() => {
            setKeyMissing(false);
            setError(null);
          }}
        />
      )}
    </div>
  );
}
