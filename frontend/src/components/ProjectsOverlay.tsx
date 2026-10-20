import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { ProjectInfo } from "../api";
import {
  IconClose,
  IconDownload,
  IconExternal,
  IconFile,
  IconFolder,
} from "../icons";
import { openPreview } from "../previewStore";

interface ProjectsOverlayProps {
  open: boolean;
  onClose: () => void;
  /** Abre a conversa de onde o projeto saiu. */
  onSelect: (conversationId: number) => void;
}

function indexFile(project: ProjectInfo) {
  return project.files.find(
    (file) => file.name === "index.html" || file.name === "index.htm"
  );
}

/**
 * Biblioteca de projetos: todos os sites/apps que a Nébula já gerou.
 * Dá para abrir na hora, voltar pra conversa ou baixar tudo em .zip.
 */
export function ProjectsOverlay({
  open,
  onClose,
  onSelect,
}: ProjectsOverlayProps) {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProjects(await api.projects());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Erro ao carregar os projetos."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (!open) return null;

  const openSite = (project: ProjectInfo) => {
    const file = indexFile(project);
    if (!file) return;
    openPreview({ url: file.url, name: project.title });
    onClose();
  };

  return (
    <>
      <div
        className="fixed inset-0 z-[60] bg-black/50 nebula-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Biblioteca de projetos"
        className="fixed left-1/2 top-1/2 z-[70] max-h-[85vh] w-[min(94vw,40rem)]
          -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-3xl
          border border-zinc-200 bg-white p-5 shadow-xl nebula-scale-in
          dark:border-zinc-800 dark:bg-zinc-900"
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <IconFolder className="accent-text h-5 w-5" />
            <h2 className="text-base font-semibold">Projetos</h2>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs
              text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              {loading ? "…" : projects.length}
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-zinc-500 transition
              hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="Fechar projetos"
          >
            <IconClose className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <p className="mb-3 rounded-2xl bg-red-50 px-4 py-2.5 text-sm
            text-red-700 dark:bg-red-950/50 dark:text-red-300">
            {error}
          </p>
        )}

        {!loading && !error && projects.length === 0 && (
          <p className="rounded-2xl bg-zinc-100 px-4 py-8 text-center text-sm
            text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
            Nenhum projeto ainda — peça um site e ele aparece aqui.
          </p>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {projects.map((project) => {
            const hasIndex = Boolean(indexFile(project));
            return (
              <div
                key={project.project}
                className="flex flex-col gap-2 rounded-2xl border
                  border-zinc-200 p-3.5 transition hover:border-blue-300
                  dark:border-zinc-700 dark:hover:border-blue-500/50"
              >
                <div>
                  <h3 className="truncate text-sm font-semibold" title={project.title}>
                    {project.title}
                  </h3>
                  <p className="mt-0.5 flex items-center gap-1 text-xs text-zinc-400">
                    <IconFile className="h-3.5 w-3.5" />
                    {project.files.length} arquivo
                    {project.files.length === 1 ? "" : "s"}
                  </p>
                </div>

                <div className="flex flex-wrap gap-1">
                  {project.files.slice(0, 3).map((file) => (
                    <span
                      key={file.name}
                      className="max-w-[130px] truncate rounded-md bg-zinc-100
                        px-1.5 py-0.5 font-mono text-[11px] text-zinc-500
                        dark:bg-zinc-800 dark:text-zinc-400"
                    >
                      {file.name}
                    </span>
                  ))}
                  {project.files.length > 3 && (
                    <span className="rounded-md px-1.5 py-0.5 text-[11px]
                      text-zinc-400">
                      +{project.files.length - 3}
                    </span>
                  )}
                </div>

                <div className="mt-auto flex flex-wrap gap-2">
                  {hasIndex && (
                    <button
                      onClick={() => openSite(project)}
                      className="flex items-center gap-1.5 rounded-full
                        accent-gradient px-3 py-1.5 text-xs font-medium
                        text-white transition nebula-tap hover:brightness-110"
                    >
                      <IconExternal className="h-3.5 w-3.5" />
                      Abrir site
                    </button>
                  )}
                  {project.conversation_id !== null && (
                    <button
                      onClick={() => {
                        onSelect(project.conversation_id as number);
                      }}
                      className="rounded-full bg-zinc-100 px-3 py-1.5
                        text-xs font-medium text-zinc-600 transition
                        hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300
                        dark:hover:bg-zinc-700"
                    >
                      Conversa
                    </button>
                  )}
                  <a
                    href={`/api/files/${encodeURIComponent(project.project)}/zip`}
                    className="flex items-center gap-1.5 rounded-full
                      bg-zinc-100 px-3 py-1.5 text-xs font-medium
                      text-zinc-600 transition hover:bg-zinc-200
                      dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                    download
                  >
                    <IconDownload className="h-3.5 w-3.5" />
                    .zip
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
