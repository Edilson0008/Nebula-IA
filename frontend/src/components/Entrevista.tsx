import { useMemo, useState } from "react";

import type { Entrevista as EntrevistaDados } from "../api";
import { IconCheck, IconSend } from "../icons";

/**
 * Entrevista de criação: uma etapa por vez, com opções clicáveis.
 *
 * Por que existe: pedir tudo em texto corrido ("quais seções? cores? ação?")
 * cansava e vinha sempre igual. Aqui a Nébula pergunta uma coisa por vez e o
 * usuário só toca nas opções — igual a uma conversa guiada. Cada etapa pode
 * aceitar UMA escolha (estilo, ação principal) ou VÁRIAS (seções, cores),
 * conforme o que faz sentido.
 *
 * Ao terminar, monta um texto com tudo o que foi escolhido e envia como
 * mensagem normal — o backend já cai no fluxo de criação.
 */
export function Entrevista({
  dados,
  onEnviar,
  enviando,
}: {
  dados: EntrevistaDados;
  onEnviar: (texto: string) => void;
  enviando?: boolean;
}) {
  const [passo, setPasso] = useState(0);
  /** Respostas por id de etapa: string (uma) ou string[] (várias). */
  const [respostas, setRespostas] = useState<Record<string, string | string[]>>({});
  /** Texto livre da etapa atual (quando a etapa é "livre"). */
  const [livre, setLivre] = useState("");
  const [concluida, setConcluida] = useState(false);

  const etapas = dados.etapas;
  const atual = etapas[passo];
  const ultima = passo >= etapas.length - 1;

  const escolhidas = useMemo(() => {
    if (!atual) return [] as string[];
    const valor = respostas[atual.id];
    if (Array.isArray(valor)) return valor;
    return valor ? [valor] : [];
  }, [atual, respostas]);

  const podeAvancar = useMemo(() => {
    if (!atual) return false;
    // Etapa livre (o nome): exige algo digitado ou uma opção escolhida.
    if (atual.livre) return livre.trim().length > 0 || escolhidas.length > 0;
    return escolhidas.length > 0;
  }, [atual, escolhidas, livre]);

  if (!etapas.length) return null;

  const alternar = (opcao: string) => {
    if (!atual) return;
    if (atual.multi) {
      setRespostas((prev) => {
        const valor = prev[atual.id];
        const lista = Array.isArray(valor) ? valor : [];
        const nova = lista.includes(opcao)
          ? lista.filter((item) => item !== opcao)
          : [...lista, opcao];
        return { ...prev, [atual.id]: nova };
      });
    } else {
      setRespostas((prev) => ({ ...prev, [atual.id]: opcao }));
    }
  };

  const avancar = () => {
    if (!atual || !podeAvancar) return;
    // Guarda o texto livre junto (o nome do negócio).
    if (atual.livre && livre.trim()) {
      setRespostas((prev) => ({ ...prev, [atual.id]: livre.trim() }));
    }
    const proximoLivre = atual.livre;
    setLivre("");
    if (ultima) {
      finalizar({ ...respostas, ...(proximoLivre && livre.trim() ? { [atual.id]: livre.trim() } : {}) });
      return;
    }
    setPasso((valor) => valor + 1);
  };

  const voltar = () => {
    if (passo === 0) return;
    setPasso((valor) => valor - 1);
  };

  const finalizar = (todas: Record<string, string | string[]>) => {
    const linhas: string[] = [];
    for (const etapa of etapas) {
      const valor = todas[etapa.id];
      if (!valor || (Array.isArray(valor) && !valor.length)) continue;
      const texto = Array.isArray(valor) ? valor.join(", ") : valor;
      linhas.push(`- ${etapa.pergunta.replace(/\s*\(pode marcar várias\)\s*/i, "")}: ${texto}`);
    }
    setConcluida(true);
    onEnviar(
      `Aqui estão as respostas:\n${linhas.join("\n")}\n\nPode criar o projeto com base nisso.`,
    );
  };

  if (concluida) {
    return (
      <div className="my-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
        <span className="inline-flex items-center gap-2 font-medium">
          <IconCheck className="h-4 w-4" />
          Prontinho! Estou criando com as suas escolhas…
        </span>
      </div>
    );
  }

  return (
    <div className="my-3 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900">
      {/* topo: progresso da entrevista */}
      <div className="flex items-center gap-2 border-b border-zinc-200 bg-zinc-50 px-4 py-2.5 dark:border-zinc-700 dark:bg-zinc-800/60">
        <span className="accent-soft-bg accent-text flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
          {passo + 1}
        </span>
        <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
          Pergunta {passo + 1} de {etapas.length}
        </span>
        <span className="ml-auto flex gap-1">
          {etapas.map((_, indice) => (
            <span
              key={indice}
              className={`h-1.5 w-4 rounded-full transition ${
                indice <= passo ? "accent-gradient" : "bg-zinc-200 dark:bg-zinc-700"
              }`}
            />
          ))}
        </span>
      </div>

      <div className="px-4 py-3">
        <p className="mb-3 text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {atual.pergunta}
        </p>

        {atual.livre && (
          <input
            value={livre}
            onChange={(evento) => setLivre(evento.target.value)}
            onKeyDown={(evento) => {
              if (evento.key === "Enter") avancar();
            }}
            placeholder="Digite aqui…"
            autoFocus
            className="mb-3 w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-800 outline-none focus:border-zinc-400 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
          />
        )}

        {atual.opcoes.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {atual.opcoes.map((opcao) => {
              const ativa = escolhidas.includes(opcao);
              return (
                <button
                  key={opcao}
                  onClick={() => alternar(opcao)}
                  className={`rounded-full border px-3 py-1.5 text-sm transition ${
                    ativa
                      ? "accent-soft-bg accent-text border-transparent font-medium"
                      : "border-zinc-300 text-zinc-600 hover:border-zinc-400 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  }`}
                >
                  {ativa && <IconCheck className="mr-1 inline h-3.5 w-3.5" />}
                  {opcao}
                </button>
              );
            })}
          </div>
        )}

        {atual.multi && (
          <p className="mt-2 text-xs text-zinc-400">
            Pode marcar quantas quiser.
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-zinc-200 px-3 py-2 dark:border-zinc-700">
        {passo > 0 && (
          <button
            onClick={voltar}
            className="rounded-full px-3 py-1.5 text-xs font-medium text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            Voltar
          </button>
        )}
        <button
          onClick={avancar}
          disabled={!podeAvancar || enviando}
          className={`ml-auto flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition ${
            podeAvancar && !enviando
              ? "accent-gradient text-white"
              : "cursor-not-allowed bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-600"
          }`}
        >
          {ultima ? (
            <>
              <IconSend className="h-3.5 w-3.5" />
              Criar agora
            </>
          ) : (
            "Próxima"
          )}
        </button>
      </div>
    </div>
  );
}
