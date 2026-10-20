import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { speakAsync, stopSpeaking } from "./voice";

/**
 * Modo conversa por voz (hands-free), estilo Gemini Live.
 *
 * Fica num loop estritamente sequencial — nunca ouve enquanto fala, então não
 * escuta a própria voz:
 *
 *     OUVIR → (pega a frase) → MANDAR → (espera a resposta) → FALAR → OUVIR…
 *
 * O loop só para quando o usuário toca em "Encerrar" ou diz uma palavra de
 * fim ("pare", "chega", "tchau", "obrigado"…). Tudo roda no navegador
 * (SpeechRecognition + SpeechSynthesis), sem servidor nem dependência.
 */

export type CallPhase = "listening" | "thinking" | "speaking";

/** Fim de conversa: falado ou dito. Cuidado com "para" (falso positivo). */
const STOP_PATTERN =
  /\b(pare|chega|tchau|obrigad[oa]|até mais|encerrar|finalizar|suficiente|já chega|deu|pode parar|desculpe? pare)\b/i;

function isStopWord(text: string): boolean {
  const t = text.toLowerCase().trim().replace(/[.!?…]+$/g, "");
  // "para" sozinho encerra; no meio de frase, não (evita "para onde é…").
  if (/^(para|pare|chega|deu|basta)$/.test(t)) return true;
  return STOP_PATTERN.test(t);
}

function recognitionSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
  );
}

interface VoiceCallOptions {
  /** Envia a frase como mensagem e resolve quando a resposta terminar. */
  send: (text: string) => Promise<void>;
  /** Conteúdo da última resposta da Nébula (pra ela falar). */
  lastReply: () => string;
}

// Estado externo compartilhado (assinado por useSyncExternalStore) para o
// botão do Composer saber se a chamada está ativa, mesmo montado à parte.
let callActiveStore = false;
const callListeners = new Set<() => void>();
function setCallActiveStore(value: boolean) {
  callActiveStore = value;
  for (const l of callListeners) l();
}
export function useCallActive(): boolean {
  return useSyncExternalStore(
    (l) => {
      callListeners.add(l);
      return () => callListeners.delete(l);
    },
    () => callActiveStore,
    () => callActiveStore
  );
}

export function useVoiceCall({ send, lastReply }: VoiceCallOptions) {
  const [active, setActive] = useState(false);
  const [phase, setPhase] = useState<CallPhase>("listening");
  const [heard, setHeard] = useState(""); // trecho provisório do microfone
  const [lastUser, _setLastUser] = useState(""); // o que você falou
  const [lastAi, _setLastAi] = useState(""); // o que ela respondeu
  const lastUserRef = useRef("");
  const lastAiRef = useRef("");
  const setLastUser = (v: string) => { lastUserRef.current = v; _setLastUser(v); };
  const setLastAi = (v: string) => { lastAiRef.current = v; _setLastAi(v); };
  const [fatal, setFatal] = useState<string | null>(null); // erro que encerra

  // Sempre atual: o loop (async) enxerga a versão mais nova de send/lastReply.
  const optRef = useRef({ send, lastReply });
  optRef.current = { send, lastReply };

  const activeRef = useRef(false);
  const stopRef = useRef(false);
  const fatalRef = useRef(false);
  const recRef = useRef<any>(null);

  // Cria o reconhecedor uma única vez (continuous=false: uma frase por volta).
  useEffect(() => {
    if (!recognitionSupported()) return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = "pt-BR";
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    recRef.current = rec;
    return () => {
      try {
        rec.abort();
      } catch {}
      stopSpeaking();
    };
  }, []);

  /** Uma "escutada": resolve com a frase final, ou null se não ouviu nada. */
  const listenOnce = useCallback((): Promise<string | null> => {
    return new Promise((resolve) => {
      const rec = recRef.current;
      if (!rec || fatalRef.current) {
        resolve(null);
        return;
      }
      let settled = false;
      const finish = (value: string | null) => {
        if (settled) return;
        settled = true;
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        resolve(value);
      };

      rec.onresult = (event: any) => {
        let finalText = "";
        let interimText = "";
        for (let i = 0; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) finalText += result[0].transcript;
          else interimText += result[0].transcript;
        }
        setHeard(interimText.trim());
        const text = finalText.trim();
        if (text) {
          setHeard("");
          finish(text);
        }
      };

      rec.onerror = (event: any) => {
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          fatalRef.current = true;
          setFatal("Permissão do microfone negada. Libere nas configurações do navegador.");
          finish(null);
        }
        // "no-speech"/"network"/"audio-capture": o onend dispara e tentamos de novo.
      };

      rec.onend = () => {
        // Terminou sem frase final: tenta ouvir de novo (a menos que tenha parado).
        finish(null);
      };

      try {
        rec.start();
      } catch {
        finish(null);
      }
    });
  }, []);

  const finishCall = useCallback(() => {
    activeRef.current = false;
    setCallActiveStore(false);
    stopSpeaking();
    try {
      recRef.current?.abort();
    } catch {}
    setActive(false);
    setPhase("listening");
    setHeard("");
  }, []);

  // O loop de verdade (uma corrente que dura a chamada inteira).
  const runLoop = useCallback(async () => {
    while (activeRef.current && !stopRef.current && !fatalRef.current) {
      setPhase("listening");
      setHeard("");
      const text = await listenOnce();
      if (!activeRef.current || stopRef.current || fatalRef.current) break;
      if (!text) continue; // não escutou nada: volta a ouvir

      if (isStopWord(text)) break; // falou "pare"/"tchau": encerra
      // Evita repetir a mesma frase duas vezes seguidas no loop (muitas vezes
      // o SpeechRecognition pega o mesmo trecho do microfone)
      if (text.trim().toLowerCase() === lastUserRef.current.trim().toLowerCase()) {
        continue; // volta a ouvir sem reenviar
      }

      setLastUser(text);
      setPhase("thinking");
      try {
        await optRef.current.send(text);
      } catch {
        break; // erro no envio: encerra em vez de travar ouvindo
      }

      // Respiro curto: garante que a última parte da resposta já entrou no
      // estado (messagesRef) antes de ler — senão a fala perde o final.
      await new Promise((resolve) => setTimeout(resolve, 120));

      const reply = optRef.current.lastReply();
      // Evita loop: se a resposta for vazia (erro já tratado pelo backend), encerra
      if (!reply.trim()) break;
      if (reply) {
        setLastAi(reply);
        setPhase("speaking");
        await speakAsync(reply);
      }
      if (!activeRef.current || stopRef.current) break;
    }
    finishCall();
  }, [listenOnce, finishCall]);

  const start = useCallback(() => {
    if (activeRef.current) return;
    if (!recognitionSupported()) {
      setFatal("Este navegador não suporta conversa por voz (use Chrome).");
      setActive(true); // mostra o aviso na tela
      return;
    }
    stopRef.current = false;
    fatalRef.current = false;
    setFatal(null);
    setLastUser("");
    setLastAi("");
    activeRef.current = true;
    setCallActiveStore(true);
    setActive(true);
    setPhase("listening");
    void runLoop();
  }, [runLoop]);

  const stop = useCallback(() => {
    stopRef.current = true;
    finishCall();
  }, [finishCall]);

  return { active, phase, heard, lastUser, lastAi, fatal, start, stop };
}
