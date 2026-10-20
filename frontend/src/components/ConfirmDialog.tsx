import { useEffect, useId } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message?: string;
  /** Texto do botão que confirma (ação destrutiva). */
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Diálogo simples de confirmação para ações que não têm volta (ex.: excluir
 * uma conversa). Fecha no Esc e ao tocar fora; o botão "Cancelar" vem focado
 * para o toque acidental não apagar nada.
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Excluir",
  cancelLabel = "Cancelar",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <>
      <div
        onClick={onCancel}
        className="fixed inset-0 z-[60] bg-black/40 nebula-fade-in"
        aria-hidden="true"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="fixed left-1/2 top-1/2 z-[70] w-[calc(100%-2.5rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-3xl border border-zinc-200 bg-white p-5 shadow-xl nebula-scale-in dark:border-zinc-800 dark:bg-zinc-900"
      >
        <h2
          id={titleId}
          className="text-base font-semibold text-zinc-800 dark:text-zinc-100"
        >
          {title}
        </h2>

        {message && (
          <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
            {message}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            autoFocus
            onClick={onCancel}
            className="rounded-full px-4 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className="rounded-full bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </>
  );
}
