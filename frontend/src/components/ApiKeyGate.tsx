import { useState } from "react";

import { setGeminiKeyValue } from "../api";

/**
 * Tela de bloqueio que pede a chave da API do Google (Gemini).
 *
 * Cada pessoa usa a PRÓPRIA chave — assim o custo é de quem usa e nenhuma
 * chave fica guardada no código do projeto. A chave é salva só no navegador
 * (localStorage) e vai em toda requisição pelo cabeçalho X-Gemini-Key.
 *
 * Enquanto não houver chave, o chat fica coberto por esta tela: é o "porteiro"
 * da Nébula.
 */
export function ApiKeyGate({ onReady }: { onReady: () => void }) {
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = () => {
    const clean = key.trim();
    if (clean.length < 20) {
      setError("A chave parece curta demais. Copie a chave inteira do AI Studio.");
      return;
    }
    setGeminiKeyValue(clean);
    onReady();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-slate-900 p-6 text-slate-100 shadow-2xl md:p-8">
        <div className="mb-1 text-2xl font-semibold">
          Bem-vindo à <span className="text-indigo-400">Nébula</span>
        </div>
        <p className="mb-5 text-sm text-slate-400">
          Para usar, cole a sua chave da API do Google Gemini. Ela fica salva
          apenas neste navegador — ninguém mais tem acesso a ela.
        </p>

        <label className="mb-1.5 block text-sm font-medium text-slate-300">
          Chave da API (Gemini)
        </label>
        <div className="flex items-stretch gap-2">
          <input
            type={show ? "text" : "password"}
            value={key}
            onChange={(event) => {
              setKey(event.target.value);
              setError(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") confirm();
            }}
            placeholder="AIza..."
            autoComplete="off"
            spellCheck={false}
            className="min-w-0 flex-1 rounded-xl border border-white/10 bg-slate-800 px-3.5 py-2.5 font-mono text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-indigo-500"
          />
          <button
            type="button"
            onClick={() => setShow((value) => !value)}
            className="rounded-xl border border-white/10 bg-slate-800 px-3 text-sm text-slate-300 hover:bg-slate-700"
            title={show ? "Esconder" : "Mostrar"}
          >
            {show ? "🙈" : "👁"}
          </button>
        </div>

        {error && (
          <p className="mt-2 text-sm text-rose-400">{error}</p>
        )}

        <button
          type="button"
          onClick={confirm}
          className="mt-5 w-full rounded-xl bg-indigo-600 px-4 py-3 font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
          disabled={!key.trim()}
        >
          Começar a usar
        </button>

        <div className="mt-4 rounded-xl bg-slate-800/60 px-4 py-3 text-xs leading-relaxed text-slate-400">
          Não tem uma chave? É <b>gratuita</b>:
          <ol className="mt-1.5 list-decimal space-y-0.5 pl-4">
            <li>
              Acesse{" "}
              <a
                href="https://aistudio.google.com/apikey"
                target="_blank"
                rel="noreferrer"
                className="text-indigo-400 underline"
              >
                aistudio.google.com/apikey
              </a>
            </li>
            <li>Entre com uma conta Google</li>
            <li>
              Clique em <b>Create API key</b> e copie o código
            </li>
            <li>Cole aqui em cima</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
