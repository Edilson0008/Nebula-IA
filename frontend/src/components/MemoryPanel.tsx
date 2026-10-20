import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { Memory } from "../api";
import { IconBrain, IconClose, IconTrash } from "../icons";

interface MemoryPanelProps {
  open: boolean;
  onClose: () => void;
  useMemory: boolean;
  onToggleMemory: (value: boolean) => void;
}

/**
 * Painel da memória de longo prazo: mostra o que a Nébula aprendeu sobre você,
 * permite apagar fatos e desligar a memória quando quiser.
 */
export function MemoryPanel({
  open,
  onClose,
  useMemory,
  onToggleMemory,
}: MemoryPanelProps) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMemories(await api.memories());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar a memória.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const remove = async (id: number) => {
    try {
      await api.removeMemory(id);
      setMemories((prev) => prev.filter((memory) => memory.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao apagar o fato.");
    }
  };

  if (!open) return null;

  return (
    <>
      <div onClick={onClose} className="fixed inset-0 z-40 bg-black/40 nebula-fade-in" />

      <div className="nebula-sheet fixed inset-x-0 bottom-0 z-50 flex max-h-[85vh] flex-col rounded-t-3xl border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-900 md:inset-x-auto md:right-6 md:bottom-6 md:w-[420px] md:rounded-3xl">
        <div className="flex items-center gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <span className="accent-gradient flex h-8 w-8 items-center justify-center rounded-full text-white">
            <IconBrain className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
              Memória da Nébula
            </p>
            <p className="text-xs text-zinc-400">
              Fatos que ela lembra entre conversas
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1.5 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="Fechar"
          >
            <IconClose className="h-5 w-5" />
          </button>
        </div>

        <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-2.5 dark:border-zinc-800">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
            <input
              type="checkbox"
              checked={useMemory}
              onChange={(event) => onToggleMemory(event.target.checked)}
              className="h-4 w-4 accent-blue-600"
            />
            Usar memória nas respostas
          </label>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {loading && <p className="text-sm text-zinc-400">Carregando…</p>}

          {error && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/60 dark:text-red-300">
              {error}
            </p>
          )}

          {!loading && !error && memories.length === 0 && (
            <p className="text-sm text-zinc-400">
              Ainda não aprendi nada sobre você. Converse normalmente — quando
              algo importante aparecer (nome, gostos, projetos), eu guardo aqui.
            </p>
          )}

          <ul className="flex flex-col gap-2">
            {memories.map((memory) => (
              <li
                key={memory.id}
                className="group flex items-start gap-2 rounded-2xl border border-zinc-200 px-3 py-2 dark:border-zinc-800"
              >
                <p className="min-w-0 flex-1 text-sm text-zinc-700 dark:text-zinc-200">
                  {memory.content}
                </p>
                <button
                  onClick={() => remove(memory.id)}
                  className="shrink-0 rounded-full p-1.5 text-zinc-400 transition hover:bg-zinc-100 hover:text-red-500 dark:hover:bg-zinc-800"
                  aria-label="Esquecer este fato"
                >
                  <IconTrash className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
