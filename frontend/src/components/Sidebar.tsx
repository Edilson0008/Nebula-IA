import { useEffect, useMemo, useState } from "react";
import type { Conversation } from "../api";
import {
  IconBrain,
  IconClose,
  IconDownload,
  IconFolder,
  IconGear,
  IconPencil,
  IconPlus,
  IconSearch,
  IconSparkle,
  IconTrash,
} from "../icons";

interface SidebarProps {
  conversations: Conversation[];
  activeId: number | null;
  open: boolean;
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
  onRename: (id: number) => void;
  onOpenMemory: () => void;
  onOpenProjects: () => void;
  onOpenSettings: () => void;
  onClose: () => void;
}

export function Sidebar({
  conversations,
  activeId,
  open,
  onSelect,
  onNew,
  onDelete,
  onRename,
  onOpenMemory,
  onOpenProjects,
  onOpenSettings,
  onClose,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [canInstall, setCanInstall] = useState(false);

  // Captura o beforeinstallprompt para mostrar o botão "Instalar app".
  useEffect(() => {
    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setDeferredPrompt(event);
      setCanInstall(true);
    };
    const onAppInstalled = () => {
      setCanInstall(false);
      setDeferredPrompt(null);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt as any);
    window.addEventListener("appinstalled", onAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt as any);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  const installPwa = async () => {
    if (!deferredPrompt) return;
    try {
      await deferredPrompt.prompt();
      await deferredPrompt.userChoice;
    } catch {}
    setDeferredPrompt(null);
    setCanInstall(false);
  };

  // Busca simples por título (case-insensitive).
  const filtradas = useMemo(() => {
    const termo = query.trim().toLowerCase();
    if (!termo) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(termo));
  }, [conversations, query]);

  return (
    <>
      {open && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/40 nebula-fade-in md:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[272px] shrink-0 flex-col border-r border-zinc-200 bg-zinc-50 transition-transform duration-200 dark:border-zinc-800 dark:bg-zinc-900 md:relative md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2 px-4 py-4">
          <span className="accent-gradient flex h-8 w-8 items-center justify-center rounded-full text-white">
            <IconSparkle className="h-4 w-4" />
          </span>
          <span className="accent-gradient bg-clip-text text-lg font-semibold text-transparent">
            Nébula
          </span>
          <button
            onClick={onClose}
            className="ml-auto rounded-full p-1.5 text-zinc-500 hover:bg-zinc-200 dark:hover:bg-zinc-800 md:hidden"
            aria-label="Fechar menu"
          >
            <IconClose className="h-5 w-5" />
          </button>
        </div>

        <div className="px-3">
          <button
            onClick={onNew}
            className="flex w-full items-center gap-2 rounded-full bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 shadow-sm ring-1 ring-zinc-200 transition hover:bg-zinc-100 dark:bg-zinc-800 dark:text-zinc-200 dark:ring-zinc-700 dark:hover:bg-zinc-700"
          >
            <IconPlus className="h-4 w-4" />
            Novo chat
          </button>

          <button
            onClick={onOpenMemory}
            className="mt-2 flex w-full items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-200/70 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <IconBrain className="h-4 w-4" />
            Memória
          </button>

          <button
            onClick={onOpenProjects}
            className="mt-1 flex w-full items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-200/70 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <IconFolder className="h-4 w-4" />
            Projetos
          </button>

          <button
            onClick={onOpenSettings}
            className="mt-1 flex w-full items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-200/70 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <IconGear className="h-4 w-4" />
            Ajustes
          </button>

          {canInstall && (
            <button
              onClick={installPwa}
              className="mt-2 flex w-full items-center gap-2 rounded-full px-4 py-2 text-sm font-medium accent-text transition hover:bg-[var(--accent-soft)]"
            >
              <IconDownload className="h-4 w-4" />
              Instalar app
            </button>
          )}

          {conversations.length > 0 && (
            <div className="mt-3 flex items-center gap-2 rounded-full bg-white px-3 py-2 ring-1 ring-zinc-200 focus-within:ring-blue-400 dark:bg-zinc-800 dark:ring-zinc-700 dark:focus-within:ring-blue-500">
              <IconSearch className="h-4 w-4 shrink-0 text-zinc-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Buscar conversas"
                className="w-full bg-transparent text-sm text-zinc-700 outline-none placeholder:text-zinc-400 dark:text-zinc-200"
                aria-label="Buscar conversas"
              />
              {query && (
                <button
                  onClick={() => setQuery("")}
                  className="rounded-full p-0.5 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
                  aria-label="Limpar busca"
                >
                  <IconClose className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
        </div>

        <div className="mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-4">
          {conversations.length === 0 ? (
            <p className="px-2 text-xs text-zinc-400">
              Suas conversas aparecem aqui.
            </p>
          ) : filtradas.length === 0 ? (
            <p className="px-2 text-xs text-zinc-400">
              Nenhuma conversa com "{query.trim()}".
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {filtradas.map((conversation) => {
                const active = conversation.id === activeId;
                return (
                  <li key={conversation.id} className="group relative">
                    <button
                      onClick={() => onSelect(conversation.id)}
                      className={`w-full truncate rounded-full px-3 py-2 pr-[68px] text-left text-sm transition ${
                        active
                          ? "accent-soft-bg font-medium accent-text"
                          : "text-zinc-600 hover:bg-zinc-200/70 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      }`}
                    >
                      {conversation.title}
                    </button>

                    <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
                      <button
                        onClick={() => onRename(conversation.id)}
                        title="Renomear conversa"
                        className="rounded-full p-1.5 text-zinc-400 transition hover:bg-zinc-200 hover:text-zinc-700 focus-visible:opacity-100 dark:hover:bg-zinc-700 dark:hover:text-zinc-200 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
                        aria-label={`Renomear conversa ${conversation.title}`}
                      >
                        <IconPencil className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => onDelete(conversation.id)}
                        title="Excluir conversa"
                        className="rounded-full p-1.5 text-zinc-400 transition hover:bg-red-50 hover:text-red-500 focus-visible:opacity-100 dark:hover:bg-red-950/40 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
                        aria-label={`Excluir conversa ${conversation.title}`}
                      >
                        <IconTrash className="h-4 w-4" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
