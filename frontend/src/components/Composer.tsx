import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import type { Attachment } from "../api";
import {
  IconClose,
  IconFolder,
  IconImage,
  IconMic,
  IconPaperclip,
  IconPlus,
  IconSend,
  IconStop,
  IconWaveform,
} from "../icons";

function readAsBase64(file: File): Promise<{ name: string; mime_type: string; data: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const comma = result.indexOf(",");
      const data = comma >= 0 ? result.slice(comma + 1) : result;
      resolve({ name: file.name, mime_type: file.type || "application/octet-stream", data });
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

interface ComposerProps {
  sending: boolean;
  onSend: (text: string, attachments?: Attachment[], image?: boolean) => void;
  onStop?: () => void;
  /** Item "Projetos" do menu "+". */
  onOpenProjects?: () => void;
  /** Inicia a conversa por voz hands-free. */
  onStartCall?: () => void;
}

/**
 * Caixa onde o usuário escreve.
 *
 * Ditado por voz (pt-BR) com dedupe: o texto provisório (interim) aparece só
 * como "ouvi: ..." abaixo da caixa, e só o resultado final entra no input —
 * assim não há repetição (o problema de duplicar vinha de acumular o interim).
 */
export function Composer({
  sending,
  onSend,
  onStop,
  onOpenProjects,
  onStartCall,
}: ComposerProps) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  /** Menu "+" aberto (arquivo / gerar imagem / projetos). */
  const [menuOpen, setMenuOpen] = useState(false);
  /** Modo "Gerar imagem": a próxima mensagem vira pedido de desenho. */
  const [imageMode, setImageMode] = useState(false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [micError, setMicError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Attachment | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<any>(null);
  const silentTimerRef = useRef<number | null>(null);

  const clearSilentTimer = () => {
    if (silentTimerRef.current !== null) {
      window.clearTimeout(silentTimerRef.current);
      silentTimerRef.current = null;
    }
  };

  // Para o ditado sozinho após um tempo sem falar (evita ficar "preso" ouvindo).
  const resetSilentTimer = () => {
    clearSilentTimer();
    silentTimerRef.current = window.setTimeout(() => {
      try {
        recognitionRef.current?.stop();
      } catch {}
    }, 6000);
  };

  const stopListening = () => {
    clearSilentTimer();
    const rec = recognitionRef.current;
    if (!rec) return;
    try {
      rec.abort();
    } catch {
      try {
        rec.stop();
      } catch {}
    }
    setListening(false);
    setInterim("");
  };

  // Inicializa o reconhecimento de voz (webkitSpeechRecognition).
  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const rec = new SpeechRecognition();
    rec.lang = "pt-BR";
    // Uma única sessão por clique: para sozinho ao terminar a frase, então o
    // navegador não re-dispara o mesmo trecho várias vezes (causa da cópia).
    rec.continuous = false;
    // O interim fica só na pré-visualização "ouvi: ...", nunca no input.
    rec.interimResults = true;

    rec.onresult = (event: any) => {
      resetSilentTimer();
      let finalText = "";
      let interimText = "";
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalText += result[0].transcript;
        } else {
          interimText += result[0].transcript;
        }
      }
      setInterim(interimText.trim());

      const add = finalText.trim();
      if (!add) return;
      setInterim("");
      setInput((prev) => {
        const base = prev.trimEnd();
        if (!base) return add;
        return `${base} ${add}`;
      });
    };

    rec.onerror = (event: any) => {
      setListening(false);
      setInterim("");
      clearSilentTimer();
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setMicError("Permissão do microfone negada. Libere nas configurações do navegador.");
      } else if (event.error === "no-speech") {
        setMicError("Não escutei nada. Toque no microfone e fale novamente.");
      } else {
        setMicError("Não consegui usar o microfone agora. Tente de novo.");
      }
    };

    rec.onend = () => {
      setListening(false);
      setInterim("");
      clearSilentTimer();
    };

    recognitionRef.current = rec;

    return () => {
      clearSilentTimer();
      try {
        rec.abort();
      } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cresce conforme o texto, até um limite.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [input]);

  const startListening = () => {
    const rec = recognitionRef.current;
    if (!rec) {
      setMicError("Este navegador não suporta ditado por voz (use Chrome).");
      return;
    }
    setMicError(null);
    setInterim("");
    try {
      rec.start();
      setListening(true);
      resetSilentTimer();
    } catch {
      setListening(false);
    }
  };

  const submit = () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || sending) return;
    stopListening(); // não fica gravando depois de enviar
    onSend(text, attachments, imageMode && text.length > 0);
    setInput("");
    setAttachments([]);
    setImageMode(false); // volta ao modo normal após enviar
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const pickFiles = () => {
    fileInputRef.current?.click();
  };

  const onFilesPicked = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
    const picked: Attachment[] = [];
    for (const file of files.slice(0, 4 - attachments.length)) {
      try {
        const res = await readAsBase64(file);
        picked.push(res);
      } catch {}
    }
    if (picked.length > 0) {
      setAttachments((prev) => [...prev, ...picked].slice(0, 4));
    }
    event.target.value = "";
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="relative flex flex-col gap-2"
    >
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1">
          {attachments.map((att, i) => (
            <span
              key={`${att.name}-${i}`}
              className="group relative flex items-center gap-1.5 rounded-xl bg-zinc-100 py-1 pl-1 pr-7 text-xs text-zinc-700 shadow-sm dark:bg-zinc-700 dark:text-zinc-100"
            >
              {/* Miniatura clicável (preview). */}
              <button
                type="button"
                onClick={() => setPreview(att)}
                className="flex items-center gap-1.5"
                title="Pré-visualizar"
              >
                {att.mime_type.startsWith("image/") ? (
                  <img
                    src={`data:${att.mime_type};base64,${att.data}`}
                    alt={att.name}
                    className="h-8 w-8 rounded-lg object-cover"
                  />
                ) : (
                  <IconPaperclip className="h-4 w-4" />
                )}
                <span className="max-w-[120px] truncate">{att.name}</span>
              </button>
              <button
                type="button"
                onClick={() => removeAttachment(i)}
                title="Remover anexo"
                className="absolute right-1 top-1/2 -translate-y-1/2 rounded-full p-0.5 text-zinc-400 hover:text-red-500"
                aria-label={`Remover ${att.name}`}
              >
                <IconClose className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Modo "Gerar imagem" ligado pelo "+": avisa e muda o placeholder. */}
      {imageMode && (
        <div className="flex items-center gap-2 self-start rounded-full bg-purple-50 py-1.5 pl-3 pr-1.5 text-xs font-medium text-purple-700 ring-1 ring-purple-200 dark:bg-purple-500/15 dark:text-purple-300 dark:ring-purple-500/40">
          <IconImage className="h-4 w-4" />
          Gerando imagem — descreva abaixo
          <button
            type="button"
            onClick={() => {
              setImageMode(false);
              textareaRef.current?.focus();
            }}
            title="Cancelar modo imagem"
            className="rounded-full p-0.5 transition hover:bg-purple-100 dark:hover:bg-purple-500/25"
            aria-label="Cancelar modo imagem"
          >
            <IconClose className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Ditado: pré-visualização do que foi ouvido + erro de permissão. */}
      {(interim || micError) && (
        <div className="px-1 text-xs">
          {interim && (
            <span className="text-zinc-400">
              ouvi: <span className="italic text-zinc-500">{interim}</span>
            </span>
          )}
          {micError && <span className="text-red-500">{micError}</span>}
        </div>
      )}

      <div className="flex items-end gap-2 rounded-[28px] border border-zinc-200 bg-white px-3 py-2 shadow-sm focus-within:border-zinc-300 dark:border-zinc-700 dark:bg-zinc-800 dark:focus-within:border-zinc-600 sm:px-4 sm:py-3">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,application/pdf,text/plain"
          multiple
          onChange={onFilesPicked}
          className="hidden"
        />

        {/* "+" estilo Gemini: abre arquivo, gera imagem ou mostra projetos. */}
        <button
          type="button"
          onClick={() => setMenuOpen((value) => !value)}
          disabled={sending}
          title="Mais opções (arquivo, imagem, projetos)"
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-40 sm:h-9 sm:w-9 ${
            menuOpen
              ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-700 dark:text-white"
              : "text-zinc-500 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
          }`}
          aria-label="Mais opções"
          aria-expanded={menuOpen}
        >
          {/* Vira um "×" enquanto o menu está aberto. */}
          <IconPlus
            className={`h-4.5 w-4.5 transition-transform duration-200 ${
              menuOpen ? "rotate-45" : ""
            }`}
          />
        </button>

        {menuOpen && (
          <>
            {/* Camada invisível: tocar fora fecha o menu. */}
            <div
              className="fixed inset-0 z-20"
              onClick={() => setMenuOpen(false)}
              aria-hidden="true"
            />
            <div className="absolute bottom-full left-0 z-30 mb-2 w-60 rounded-2xl border border-zinc-200 bg-white p-1.5 shadow-xl nebula-scale-in dark:border-zinc-700 dark:bg-zinc-800">
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  if (attachments.length < 4) pickFiles();
                }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-zinc-700 transition hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                <IconPaperclip className="h-4.5 w-4.5 shrink-0 text-zinc-400" />
                <span>
                  <span className="block font-medium">Enviar arquivo</span>
                  <span className="block text-xs text-zinc-400">
                    imagem, PDF ou texto
                  </span>
                </span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  setImageMode(true);
                  textareaRef.current?.focus();
                }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-zinc-700 transition hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                <IconImage className="h-4.5 w-4.5 shrink-0 text-purple-400" />
                <span>
                  <span className="block font-medium">Gerar imagem</span>
                  <span className="block text-xs text-zinc-400">
                    descreva e a IA desenha
                  </span>
                </span>
              </button>

              {onOpenProjects && (
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    onOpenProjects();
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-zinc-700 transition hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-700"
                >
                  <IconFolder className="h-4.5 w-4.5 shrink-0 text-blue-400" />
                  <span>
                    <span className="block font-medium">Projetos</span>
                    <span className="block text-xs text-zinc-400">
                      sites já gerados
                    </span>
                  </span>
                </button>
              )}
            </div>
          </>
        )}

        {/* Conversa por voz (hands-free): ouve, responde falando e continua. */}
        {onStartCall && (
          <button
            type="button"
            onClick={onStartCall}
            disabled={sending}
            title="Conversar por voz (hands-free)"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-zinc-500 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-zinc-300 dark:hover:bg-zinc-700 sm:h-9 sm:w-9"
            aria-label="Conversar por voz"
          >
            <IconWaveform className="h-4 w-4" />
          </button>
        )}

        <button
          type="button"
          onClick={listening ? stopListening : startListening}
          disabled={sending}
          title={listening ? "Ouvindo… (toque para parar)" : "Ditado por voz (pt-BR)"}
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-40 ${
            listening
              ? "animate-pulse bg-red-500 text-white hover:bg-red-600"
              : "text-zinc-500 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
          } sm:h-9 sm:w-9`}
          aria-label={listening ? "Ouvindo… toque para parar" : "Ditado por voz"}
        >
          <IconMic className="h-4 w-4" />
        </button>

        <textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={
            listening
              ? "Ouvindo…"
              : imageMode
                ? "Descreva a imagem…"
                : "Pergunte alguma coisa"
          }
          /* py-1/sm:py-1.5 = mesma altura dos botões (32/36px), então o texto
             fica centradinho com o "+" e o enviar em vez de mais baixo. */
          className="max-h-44 min-h-6 flex-1 resize-none bg-transparent py-1 text-[15px] leading-6 outline-none placeholder:text-zinc-400 sm:py-1.5"
        />

        {/* Limpar o campo (só aparece se houver texto). */}
        {input && !sending && (
          <button
            type="button"
            onClick={() => {
              setInput("");
              textareaRef.current?.focus();
            }}
            title="Limpar mensagem"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-700 dark:hover:text-zinc-200 sm:h-9 sm:w-9"
            aria-label="Limpar mensagem"
          >
            <IconClose className="h-4 w-4" />
          </button>
        )}

        {sending && onStop ? (
          <button
            type="button"
            onClick={() => {
              stopListening(); // parar geração também para o ditado
              onStop();
            }}
            title="Parar geração"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-500 text-white transition hover:bg-red-600 sm:h-9 sm:w-9"
            aria-label="Parar geração"
          >
            <IconStop className="h-4 w-4" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim() && attachments.length === 0}
            className="accent-gradient flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-white transition nebula-tap hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 sm:h-9 sm:w-9"
            aria-label="Enviar mensagem"
          >
            <IconSend className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Preview em tela cheia de anexo (imagem ampliada / nome do arquivo). */}
      {preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setPreview(null)}
        >
          <div
            className="relative max-h-full max-w-full"
            onClick={(event) => event.stopPropagation()}
          >
            {preview.mime_type.startsWith("image/") ? (
              <img
                src={`data:${preview.mime_type};base64,${preview.data}`}
                alt={preview.name}
                className="max-h-[85vh] max-w-full rounded-xl object-contain"
              />
            ) : (
              <div className="rounded-xl bg-white px-6 py-8 text-center text-zinc-800">
                <IconPaperclip className="mx-auto mb-2 h-8 w-8 text-zinc-400" />
                <p className="max-w-xs truncate font-medium">{preview.name}</p>
                <p className="mt-1 text-sm text-zinc-500">
                  {preview.mime_type.startsWith("application/pdf")
                    ? "PDF"
                    : "arquivo de texto"}
                </p>
              </div>
            )}
            <button
              type="button"
              onClick={() => setPreview(null)}
              className="absolute -top-3 -right-3 rounded-full bg-white p-1.5 text-zinc-700 shadow-lg"
              aria-label="Fechar pré-visualização"
            >
              <IconClose className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </form>
  );
}
