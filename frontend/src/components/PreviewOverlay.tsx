import { useEffect } from "react";

import { IconChevronDown, IconExternal } from "../icons";
import { backFromPreview, closePreview, usePreview } from "../previewStore";

/**
 * Visor de arquivo em tela cheia — é o que o botão "Abrir" abre.
 *
 * Fica dentro do app (iframe) em vez de abrir aba nova, então:
 *  - o gesto "voltar" do celular fecha o visor e devolve o chat;
 *  - tem botão "Voltar" para quem prefere toque;
 *  - "Nova aba" continua disponível para quem quer a página fora do app.
 */
export function PreviewOverlay() {
  const target = usePreview();

  // Gesto de voltar do sistema (arraste na borda / botão físico).
  useEffect(() => {
    const onPopState = () => backFromPreview();
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Esc fecha o visor (mesmo comportamento de diálogo).
  useEffect(() => {
    if (!target) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePreview();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [target]);

  if (!target) return null;

  return (
    <div className="nebula-rise fixed inset-0 z-[80] flex flex-col bg-white dark:bg-zinc-950">
      <header className="flex items-center gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
        <button
          onClick={closePreview}
          className="flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5 text-sm font-medium text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          <IconChevronDown className="h-4 w-4 rotate-90" />
          Voltar
        </button>

        <span className="min-w-0 flex-1 truncate text-center font-mono text-xs text-zinc-500 dark:text-zinc-400">
          {target.name}
        </span>

        <a
          href={target.url}
          target="_blank"
          rel="noreferrer"
          className="flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        >
          <IconExternal className="h-3.5 w-3.5" />
          Nova aba
        </a>
      </header>

      <iframe
        src={target.url}
        title={`Pré-visualização de ${target.name}`}
        className="min-h-0 flex-1 border-0 bg-white"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
