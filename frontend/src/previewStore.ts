import { useSyncExternalStore } from "react";

/** Arquivo que está aberto no visor em tela cheia. */
export interface PreviewTarget {
  url: string;
  name: string;
}

let current: PreviewTarget | null = null;
// true quando a gente mesmo empurrou uma entrada no histórico (para desfazer).
let pushed = false;

const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function snapshot() {
  return current;
}

export function usePreview(): PreviewTarget | null {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/**
 * Abre um arquivo em tela cheia DENTRO do app.
 *
 * A gente empurra uma entrada no histórico de navegação: assim o gesto de
 * "voltar" do celular (arraste na borda da tela) fecha o visor e devolve o
 * chat — em vez de fechar a aba, que era o que acontecia quando o "Abrir"
 * abria o arquivo numa aba nova.
 */
export function openPreview(target: PreviewTarget) {
  if (current) return;
  current = target;
  try {
    const base =
      history.state && typeof history.state === "object" ? history.state : {};
    history.pushState({ ...base, nebulaPreview: true }, "");
    pushed = true;
  } catch {
    pushed = false; // sem histórico: ainda dá para fechar pelo botão "Voltar"
  }
  emit();
}

/** Fecha pelo botão: desfaz a entrada do histórico (voltar = fecha). */
export function closePreview() {
  if (!current) return;
  if (pushed) {
    pushed = false;
    history.back(); // o popstate abaixo é quem realmente fecha
    return;
  }
  current = null;
  emit();
}

/** Chamado no popstate: gesto "voltar" do Android, Esc, botão do sistema. */
export function backFromPreview() {
  if (!current) return;
  current = null;
  pushed = false;
  emit();
}
