import { useCallback, useEffect, useRef, useState } from "react";

import { IconClose, IconSpeaker, IconSparkle } from "../icons";
import {
  lerCofre,
  guardarCofre,
  apagarCofre,
  baixarArquivo,
  restaurarArquivo,
  type CofreSalvo,
} from "../cofre";
import { updateSettings, useSettings } from "../settings";
import { speakText } from "../voice";
import { definirSala, getSala } from "../sala";

interface SettingsOverlayProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Painel de Ajustes: personalidade da Nébula (nome, tom, tamanho das
 * respostas), voz (falar as respostas) e a cópia das conversas no aparelho.
 * Tudo salvo no aparelho e enviado a cada mensagem.
 */
export function SettingsOverlay({ open, onClose }: SettingsOverlayProps) {
  const settings = useSettings();
  const [cofre, setCofre] = useState<CofreSalvo | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState("");
  const [apelido, setApelido] = useState(() => getSala());
  const [avisoSala, setAvisoSala] = useState("");
  const arquivoRef = useRef<HTMLInputElement>(null);

  const lerEstado = useCallback(async () => {
    try {
      setCofre(await lerCofre());
    } catch {
      setCofre(null);
    }
  }, []);

  useEffect(() => {
    if (open) void lerEstado();
  }, [open, lerEstado]);

  if (!open) return null;

  const salvarAgora = async () => {
    setSalvando(true);
    try {
      setCofre(await guardarCofre());
      setAviso("Cópia salva neste aparelho.");
    } finally {
      setSalvando(false);
    }
  };

  const baixar = async () => {
    setSalvando(true);
    try {
      setAviso(
        (await baixarArquivo())
          ? "Arquivo baixado. Guarde-o em local seguro."
          : "Não consegui baixar o arquivo."
      );
    } finally {
      setSalvando(false);
    }
  };

  const escolherArquivo = () => arquivoRef.current?.click();

  const restaurar = async (file: File) => {
    setSalvando(true);
    try {
      const texto = await file.text();
      const conversas = await restaurarArquivo(texto);
      await lerEstado();
      setAviso(`Restaurado: ${conversas} conversa(s).`);
    } catch (erro) {
      setAviso(erro instanceof Error ? erro.message : "Falha ao restaurar.");
    } finally {
      setSalvando(false);
      if (arquivoRef.current) arquivoRef.current.value = "";
    }
  };

  const quando = (ms: number) =>
    new Date(ms).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });

  const inputClass =
    "w-full rounded-xl bg-zinc-100 px-3 py-2.5 text-sm text-zinc-800 " +
    "outline-none transition focus:ring-2 focus:ring-blue-500 " +
    "dark:bg-zinc-800 dark:text-zinc-100";
  const pill = (active: boolean) =>
    `rounded-full px-3 py-1.5 text-sm font-medium transition ${
      active
        ? "accent-gradient text-white shadow"
        : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 " +
          "dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
    }`;

  const sectionTitle =
    "mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400 " +
    "dark:text-zinc-500";

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
        aria-label="Ajustes"
        className="fixed left-1/2 top-1/2 z-[70] max-h-[85vh] w-[min(94vw,28rem)]
          -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-3xl
          border border-zinc-200 bg-white p-5 shadow-xl nebula-scale-in
          dark:border-zinc-800 dark:bg-zinc-900"
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <IconSparkle className="accent-text h-5 w-5" />
            <h2 className="text-base font-semibold">Ajustes</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-zinc-500 transition
              hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="Fechar ajustes"
          >
            <IconClose className="h-5 w-5" />
          </button>
        </div>

        {/* ----------------------------------------------------------- sala */}
        <section className="mb-5">
          <h3 className={sectionTitle}>Sua sala</h3>
          <p className="mb-2 text-sm text-zinc-600 dark:text-zinc-300">
            As conversas ficam guardadas com este apelido. Quem usar outro
            apelido vê uma lista diferente.
          </p>
          <div className="flex items-stretch gap-2">
            <input
              type="text"
              value={apelido}
              onChange={(event) => {
                setApelido(event.target.value);
                setAvisoSala("");
              }}
              autoComplete="off"
              spellCheck={false}
              className="min-w-0 flex-1 rounded-xl border border-zinc-200 bg-white
                px-3 py-2 text-sm text-zinc-800 outline-none
                focus:border-indigo-500 dark:border-zinc-700 dark:bg-zinc-800
                dark:text-zinc-100"
            />
            <button
              onClick={() => {
                const limpo = apelido.trim().toLowerCase();
                if (!/^[a-z0-9._-]{2,40}$/.test(limpo)) {
                  setAvisoSala("Use 2 a 40 caracteres: letras, números, . _ -");
                  return;
                }
                definirSala(limpo);
                setApelido(limpo);
                setAvisoSala("Apelido salvo. As conversas vão recarregar.");
                window.setTimeout(() => window.location.reload(), 900);
              }}
              className="rounded-xl bg-zinc-200 px-4 text-sm font-medium text-zinc-700
                transition hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-200
                dark:hover:bg-zinc-600"
            >
              Salvar
            </button>
          </div>
          {avisoSala && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {avisoSala}
            </p>
          )}
        </section>

        {/* ------------------------------------------------ personalidade */}
        <section className="mb-5">
          <h3 className={sectionTitle}>Personalidade</h3>

          <label className="mb-3 block">
            <span className="mb-1 block text-sm text-zinc-600 dark:text-zinc-300">
              Como ela se chama
            </span>
            <input
              className={inputClass}
              value={settings.aiName}
              maxLength={40}
              placeholder="Nébula"
              onChange={(event) => updateSettings({ aiName: event.target.value })}
            />
          </label>

          <label className="mb-3 block">
            <span className="mb-1 block text-sm text-zinc-600 dark:text-zinc-300">
              Como ela te chama
            </span>
            <input
              className={inputClass}
              value={settings.userName}
              maxLength={40}
              placeholder="seu nome"
              onChange={(event) =>
                updateSettings({ userName: event.target.value })
              }
            />
          </label>

          <div className="mb-3">
            <span className="mb-1.5 block text-sm text-zinc-600 dark:text-zinc-300">
              Tom
            </span>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["direto", "Direto"],
                  ["", "Normal"],
                  ["detalhado", "Detalhado"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => updateSettings({ tone: value })}
                  className={pill(settings.tone === value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="mb-1.5 block text-sm text-zinc-600 dark:text-zinc-300">
              Respostas
            </span>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["curto", "Curtas"],
                  ["", "Normais"],
                  ["longo", "Longas"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => updateSettings({ replySize: value })}
                  className={pill(settings.replySize === value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------- aparência */}
        <section className="mb-5">
          <h3 className={sectionTitle}>Aparência</h3>

          <div className="mb-3">
            <span className="mb-1.5 block text-sm text-zinc-600 dark:text-zinc-300">
              Cor de destaque
            </span>
            <div className="flex flex-wrap items-center gap-2.5">
              {(
                [
                  ["#3b82f6", "Azul"],
                  ["#8b5cf6", "Roxo"],
                  ["#ec4899", "Rosa"],
                  ["#10b981", "Verde"],
                  ["#f59e0b", "Laranja"],
                  ["#ef4444", "Vermelho"],
                  ["#06b6d4", "Turquesa"],
                  ["#64748b", "Grafite"],
                ] as const
              ).map(([color, label]) => (
                <button
                  key={color}
                  onClick={() => updateSettings({ accent: color })}
                  title={label}
                  aria-label={`Cor ${label}`}
                  style={{ backgroundColor: color }}
                  className={`h-8 w-8 rounded-full transition nebula-tap ${
                    settings.accent === color
                      ? "ring-2 ring-zinc-400 ring-offset-2 ring-offset-white dark:ring-zinc-500 dark:ring-offset-zinc-900"
                      : "hover:scale-110"
                  }`}
                />
              ))}
            </div>
          </div>

          <div>
            <span className="mb-1.5 block text-sm text-zinc-600 dark:text-zinc-300">
              Fundo do chat
            </span>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["aurora", "Aurora"],
                  ["stars", "Estrelas"],
                  ["clean", "Limpo"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => updateSettings({ bgStyle: value })}
                  className={pill(settings.bgStyle === value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------ voz */}
        <section>
          <h3 className={sectionTitle}>Voz</h3>

          <label
            className="mb-3 flex cursor-pointer items-center justify-between
              rounded-xl bg-zinc-100 px-3 py-2.5 dark:bg-zinc-800"
          >
            <span className="text-sm text-zinc-700 dark:text-zinc-200">
              Ela fala as respostas em voz alta
            </span>
            <input
              type="checkbox"
              checked={settings.speak}
              onChange={(event) => updateSettings({ speak: event.target.checked })}
              className="h-5 w-5 accent-blue-600"
            />
          </label>

          <div className="flex items-center justify-between gap-3">
            <button
              onClick={() =>
                speakText("Oi! Eu sou a Nébula. É assim que eu falo.")
              }
              className="flex items-center gap-2 rounded-full bg-zinc-100
                px-4 py-2 text-sm font-medium text-zinc-700 transition
                hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-200
                dark:hover:bg-zinc-700"
            >
              <IconSpeaker className="h-4 w-4" />
              Testar voz
            </button>
            <span className="text-right text-xs text-zinc-400">
              Usa a voz do próprio celular (pt-BR).
            </span>
          </div>
        </section>

        {/* -------------------------------------------- conversas salvas */}
        <section className="mt-5">
          <h3 className={sectionTitle}>Conversas salvas</h3>

          <div
            className="rounded-xl bg-zinc-100 p-3 text-sm
              dark:bg-zinc-800"
          >
            <p className="text-zinc-600 dark:text-zinc-300">
              O histórico fica guardado <strong>também neste aparelho</strong>.
              Se o servidor reiniciar e esquecer tudo, a cópia daqui devolve
              suas conversas automaticamente.
            </p>

            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {cofre
                ? `Cópia de ${quando(cofre.salvoEm)} — ${cofre.conversas} conversa(s), ${cofre.memorias} memória(s).`
                : "Ainda não há cópia neste aparelho."}
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                onClick={salvarAgora}
                disabled={salvando}
                className="rounded-full bg-zinc-200 px-4 py-2 text-sm font-medium
                  text-zinc-700 transition hover:bg-zinc-300 disabled:opacity-50
                  dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
              >
                {salvando ? "Aguarde..." : "Salvar cópia agora"}
              </button>
              <button
                onClick={baixar}
                disabled={salvando}
                className="rounded-full bg-zinc-200 px-4 py-2 text-sm font-medium
                  text-zinc-700 transition hover:bg-zinc-300 disabled:opacity-50
                  dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
              >
                Baixar arquivo
              </button>
              <button
                onClick={escolherArquivo}
                disabled={salvando}
                className="rounded-full bg-zinc-200 px-4 py-2 text-sm font-medium
                  text-zinc-700 transition hover:bg-zinc-300 disabled:opacity-50
                  dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
              >
                Restaurar arquivo
              </button>
              <button
                onClick={async () => {
                  await apagarCofre();
                  setCofre(null);
                  setAviso("Cópia apagada deste aparelho.");
                }}
                className="rounded-full px-4 py-2 text-sm font-medium text-red-600
                  transition hover:bg-red-50 dark:hover:bg-red-950/40"
              >
                Apagar cópia
              </button>
            </div>

            <input
              ref={arquivoRef}
              type="file"
              accept=".nebula,application/json"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void restaurar(file);
              }}
            />

            {aviso && (
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                {aviso}
              </p>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
