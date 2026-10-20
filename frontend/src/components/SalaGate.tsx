import { useState } from "react";

import { definirSala } from "../sala";

/**
 * Tela de boas-vindas que pede o apelido (a "sala") da pessoa.
 *
 * As conversas ficam separadas por apelido no servidor: quem entra como
 * "maria" só vê as conversas da maria. O apelido fica salvo no aparelho e é
 * enviado em todo pedido. Não tem senha — serve para separar pessoas de
 * confiança (uma senha pode ser somada depois).
 */
export function SalaGate({ onReady }: { onReady: () => void }) {
  const [apelido, setApelido] = useState("");
  const [error, setError] = useState<string | null>(null);

  const confirmar = () => {
    const limpo = apelido.trim().toLowerCase();
    if (limpo.length < 2) {
      setError("Escolha um apelido com pelo menos 2 letras.");
      return;
    }
    if (!/^[a-z0-9._-]+$/.test(limpo)) {
      setError("Use só letras, números, ponto, hífen ou underline.");
      return;
    }
    definirSala(limpo);
    onReady();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-slate-900 p-6 text-slate-100 shadow-2xl md:p-8">
        <div className="mb-1 text-2xl font-semibold">
          Bem-vindo à <span className="text-indigo-400">Nébula</span>
        </div>
        <p className="mb-5 text-sm text-slate-400">
          Escolha um apelido para começar. Suas conversas ficam guardadas numa
          sala só sua — ninguém mais vê.
        </p>

        <label className="mb-1.5 block text-sm font-medium text-slate-300">
          Seu apelido
        </label>
        <input
          type="text"
          value={apelido}
          onChange={(event) => {
            setApelido(event.target.value);
            setError(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") confirmar();
          }}
          placeholder="ex.: edilson"
          autoComplete="off"
          spellCheck={false}
          className="w-full rounded-xl border border-white/10 bg-slate-800 px-3.5 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-indigo-500"
        />

        {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}

        <button
          type="button"
          onClick={confirmar}
          className="mt-5 w-full rounded-xl bg-indigo-600 px-4 py-3 font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
          disabled={!apelido.trim()}
        >
          Entrar
        </button>

        <div className="mt-4 rounded-xl bg-slate-800/60 px-4 py-3 text-xs leading-relaxed text-slate-400">
          O apelido separa as conversas por pessoa. Não tem senha: use um nome
          que só você conheça se quiser mais privacidade.
        </div>
      </div>
    </div>
  );
}
