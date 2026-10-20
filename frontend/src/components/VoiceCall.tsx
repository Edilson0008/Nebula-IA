import { IconClose, IconHangup } from "../icons";
import type { CallPhase } from "../call";

interface VoiceCallProps {
  phase: CallPhase;
  heard: string;
  lastUser: string;
  lastAi: string;
  fatal: string | null;
  onHangup: () => void;
}

const PHASE_LABEL: Record<CallPhase, string> = {
  listening: "Ouvindo…",
  thinking: "Pensando…",
  speaking: "Falando…",
};

/**
 * Tela de conversa por voz (hands-free). Um orb que muda de cor/ritmo conforme
 * a fase, o que você falou, o que ela respondeu e um botão grande de encerrar.
 * Fica acima de tudo (z-[90]) enquanto a chamada estiver ativa.
 */
export function VoiceCall({
  phase,
  heard,
  lastUser,
  lastAi,
  fatal,
  onHangup,
}: VoiceCallProps) {
  return (
    <div className="fixed inset-0 z-[90] flex flex-col items-center justify-between bg-gradient-to-b from-zinc-900 via-zinc-950 to-black px-6 py-10 text-white nebula-fade-in">
      {/* topo: nome + fechar */}
      <div className="flex w-full max-w-md items-center justify-between">
        <div>
          <p className="text-lg font-semibold">Nébula</p>
          <p className="text-xs text-zinc-400">Conversa por voz</p>
        </div>
        <button
          onClick={onHangup}
          className="rounded-full p-2 text-zinc-400 transition hover:bg-white/10 hover:text-white"
          aria-label="Encerrar conversa"
        >
          <IconClose className="h-6 w-6" />
        </button>
      </div>

      {/* orb central */}
      <div className="flex flex-1 flex-col items-center justify-center gap-6">
        <div className="relative flex h-44 w-44 items-center justify-center">
          {/* anéis pulsantes (só ouvindo e falando) */}
          {phase !== "thinking" && (
            <>
              <span className={`orb-ring ${phase === "speaking" ? "orb-ring-speak" : "orb-ring-listen"}`} />
              <span className={`orb-ring orb-ring-delay ${phase === "speaking" ? "orb-ring-speak" : "orb-ring-listen"}`} />
            </>
          )}
          <span
            className={`orb-core ${
              phase === "listening"
                ? "orb-listen"
                : phase === "thinking"
                  ? "orb-think"
                  : "orb-speak"
            }`}
          />
          {/* ícone de micro quando ouvindo */}
          {phase === "listening" && !fatal && (
            <span className="absolute text-white/90">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-10 w-10" aria-hidden="true">
                <rect x="9" y="2" width="6" height="12" rx="3" />
                <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8.5 21h7" />
              </svg>
            </span>
          )}
        </div>

        <p className="text-base font-medium text-zinc-100">
          {fatal ? "Conversa encerrada" : PHASE_LABEL[phase]}
        </p>

        {fatal && (
          <p className="max-w-sm text-center text-sm text-zinc-400">{fatal}</p>
        )}

        {/* transcrição ao vivo do microfone */}
        {!fatal && phase === "listening" && heard && (
          <p className="max-w-sm text-center text-sm italic text-zinc-500">
            “{heard}”
          </p>
        )}

        {/* últimas falas (contexto) */}
        {!fatal && (lastUser || lastAi) && (
          <div className="mt-2 flex w-full max-w-sm flex-col gap-2">
            {lastUser && (
              <p className="self-end rounded-2xl rounded-br-sm bg-white/10 px-3 py-1.5 text-sm text-zinc-100">
                {lastUser}
              </p>
            )}
            {lastAi && (
              <p className="self-start rounded-2xl rounded-bl-sm bg-[var(--accent)]/25 px-3 py-1.5 text-sm text-zinc-100">
                {lastAi.slice(0, 180)}
                {lastAi.length > 180 ? "…" : ""}
              </p>
            )}
          </div>
        )}
      </div>

      {/* botão de desligar */}
      <button
        onClick={onHangup}
        className="flex h-16 w-16 items-center justify-center rounded-full bg-red-600 text-white shadow-lg transition nebula-tap hover:bg-red-500 active:scale-95"
        aria-label="Encerrar"
      >
        <IconHangup className="h-7 w-7" />
      </button>
    </div>
  );
}
