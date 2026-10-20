import { useSyncExternalStore } from "react";

/**
 * Ajustes da Nébula guardados no aparelho (localStorage).
 *
 * Vão a cada mensagem no pedido de chat; o backend transforma os campos em
 * uma instrução de personalidade no prompt (nome, tom, tamanho da resposta).
 */
export interface Settings {
  /** Como a IA se chama (padrão: o que estiver escrito lá). */
  aiName: string;
  /** Como ela te chama. */
  userName: string;
  /** Tom das respostas: "" = normal. */
  tone: "" | "direto" | "detalhado";
  /** Tamanho das respostas: "" = normal. */
  replySize: "" | "curto" | "longo";
  /** Falar as respostas em voz alta assim que chegarem. */
  speak: boolean;
  /** Cor de destaque da interface (hex). */
  accent: string;
  /** Fundo animado do chat. */
  bgStyle: "aurora" | "stars" | "clean";
}

const DEFAULTS: Settings = {
  aiName: "",
  userName: "",
  tone: "",
  replySize: "",
  speak: false,
  accent: "#3b82f6",
  bgStyle: "aurora",
};

const STORAGE_KEY = "nebulaSettings";

function load(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Settings>) };
  } catch {
    /* dados corrompidos ou sem armazenamento: fica no padrão */
  }
  return DEFAULTS;
}

let current: Settings = load();
const listeners = new Set<() => void>();

export function getSettings(): Settings {
  return current;
}

export function updateSettings(patch: Partial<Settings>): void {
  current = { ...current, ...patch };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    /* sem armazenamento: vale nesta sessão */
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useSettings(): Settings {
  return useSyncExternalStore(subscribe, getSettings, getSettings);
}
