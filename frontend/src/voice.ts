import { useSyncExternalStore } from "react";

/**
 * Voz da Nébula: fala a resposta em pt-BR com o speechSynthesis do navegador
 * (a mesma voz do teclado do celular — sem servidor nem dependência).
 */

/** Texto bruto que está sendo falado agora (ou null). */
let speakingText: string | null = null;
const listeners = new Set<() => void>();

function setSpeaking(text: string | null) {
  speakingText = text;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** O texto que está na boca da Nébula agora (compara com o da mensagem). */
export function useSpeaking(): string | null {
  return useSyncExternalStore(
    subscribe,
    () => speakingText,
    () => speakingText
  );
}

function supported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((voice) => voice.lang.toLowerCase().startsWith("pt-br")) ??
    voices.find((voice) => voice.lang.toLowerCase().startsWith("pt")) ??
    null
  );
}

/** Markdown → fala: sem blocos de código, links viram o texto deles. */
export function forSpeech(raw: string): string {
  let text = raw;
  text = text.replace(/```[\s\S]*?```/g, " "); // blocos fechados
  text = text.replace(/```[\s\S]*$/g, " "); // bloco aberto no fim
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, " "); // imagens
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"); // link → texto
  text = text.replace(/^[#>\-*+]+\s*/gm, ""); // títulos/listas
  text = text.replace(/[*_`~]/g, ""); // ênfase
  text = text.replace(/\s+/g, " ").trim();
  return text.slice(0, 4000); // limite de fala do navegador
}

export function speakText(raw: string): void {
  if (!supported()) return;
  const speech = forSpeech(raw);
  if (!speech) return;
  stopSpeaking();
  const utterance = new SpeechSynthesisUtterance(speech);
  utterance.lang = "pt-BR";
  const voice = pickVoice();
  if (voice) utterance.voice = voice;
  utterance.rate = 1.05;
  utterance.onend = () => setSpeaking(null);
  utterance.onerror = () => setSpeaking(null);
  setSpeaking(raw);
  try {
    window.speechSynthesis.speak(utterance);
  } catch {
    setSpeaking(null);
  }
}

export function stopSpeaking(): void {
  if (!supported()) return;
  window.speechSynthesis.cancel();
  if (speakingText !== null) setSpeaking(null);
}

/** Um toque fala; outro toque para. */
export function toggleSpeak(raw: string): void {
  if (speakingText !== null) stopSpeaking();
  else speakText(raw);
}

/**
 * Fala o texto e devolve uma Promise que resolve quando a fala ACABAR.
 *
 * É o coração do modo hands-free: o loop ouve → manda → fala → volta a ouvir,
 * então precisa saber exatamente quando a Nébula calou a boca. O timeout de
 * segurança existe porque o Android, às vezes, nunca dispara o `onend`.
 */
export function speakAsync(raw: string): Promise<void> {
  return new Promise((resolve) => {
    if (!supported()) {
      resolve();
      return;
    }
    const speech = forSpeech(raw);
    if (!speech) {
      resolve();
      return;
    }
    stopSpeaking();
    const utterance = new SpeechSynthesisUtterance(speech);
    utterance.lang = "pt-BR";
    const voice = pickVoice();
    if (voice) utterance.voice = voice;
    utterance.rate = 1.05;

    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      setSpeaking(null);
      window.clearTimeout(guard);
      resolve();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    setSpeaking(raw);
    try {
      window.speechSynthesis.speak(utterance);
    } catch {
      finish();
      return;
    }
    // Alguns celulares não avisam o fim: garante o avanço do loop (~90ms/letra).
    const guard = window.setTimeout(finish, Math.min(60_000, 4000 + speech.length * 90));
  });
}

// No Chrome/Android a lista de vozes chega atrasada: aquece na abertura.
if (supported()) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.addEventListener?.("voiceschanged", () => {
    window.speechSynthesis.getVoices();
  });
}
