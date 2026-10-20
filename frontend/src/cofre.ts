/**
 * Cofre — guarda a cópia das conversas no próprio aparelho.
 *
 * Por que isso existe: o servidor grátis (Render) apaga o disco toda vez que
 * reinicia. Então o histórico não pode morar só lá. O cofre fica no
 * navegador do usuário (IndexedDB, que aguenta arquivos grandes) e faz um
 * "espelho" do banco:
 *
 *   - ao usar o app, ele baixa a cópia mais nova do servidor e guarda aqui;
 *   - quando o servidor volta vazio (reiniciou), ele devolve esta cópia,
 *     recuperando as conversas.
 *
 * É automático: o usuário não precisa fazer nada.
 */

import { api } from "./api";

const BANCO = "nebula-cofre";
const LOJA = "copias";
const VERSAO = 1;

export interface CofreSalvo {
  dados: string;
  salvoEm: number;
  conversas: number;
  mensagens: number;
  memorias: number;
}

function abrir(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(BANCO, VERSAO);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(LOJA)) db.createObjectStore(LOJA);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function gravar(chave: string, valor: unknown): Promise<void> {
  const db = await abrir();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(LOJA, "readwrite");
    tx.objectStore(LOJA).put(valor, chave);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

async function ler<T>(chave: string): Promise<T | null> {
  const db = await abrir();
  const valor = await new Promise<T | null>((resolve, reject) => {
    const tx = db.transaction(LOJA, "readonly");
    const req = tx.objectStore(LOJA).get(chave);
    req.onsuccess = () => resolve((req.result as T) ?? null);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return valor;
}

const CHAVE = "principal";

export function lerCofre(): Promise<CofreSalvo | null> {
  return ler<CofreSalvo>(CHAVE);
}

/** Guarda a cópia atual do servidor no cofre do aparelho. */
export async function guardarCofre(): Promise<CofreSalvo | null> {
  try {
    const { dados, estatisticas } = await api.backupExport();
    const salvo: CofreSalvo = {
      dados,
      salvoEm: Date.now(),
      conversas: estatisticas.conversas,
      mensagens: estatisticas.mensagens,
      memorias: estatisticas.memorias,
    };
    await gravar(CHAVE, salvo);
    return salvo;
  } catch {
    return null;
  }
}

export interface ResultadoSincronia {
  acao: "nada" | "enviou" | "baixou";
  conversas: number;
}

/**
 * Mantém servidor e cofre iguais. Chamado ao abrir o app.
 *
 * - Servidor vazio + cofre com dados  -> devolve o cofre (restaura).
 * - Servidor com dados                -> atualiza o cofre (baixa).
 */
export async function sincronizar(): Promise<ResultadoSincronia> {
  const status = await api.backupStatus();
  const cofre = await lerCofre();

  const servidorTemDados =
    status.estatisticas.conversas > 0 || status.estatisticas.memorias > 0;

  if (!servidorTemDados && cofre && cofre.conversas + cofre.memorias > 0) {
    // O servidor reiniciou e perdeu tudo: devolvemos a cópia do aparelho.
    await api.backupImport(cofre.dados);
    return { acao: "enviou", conversas: cofre.conversas };
  }

  if (servidorTemDados) {
    const salvo = await guardarCofre();
    return { acao: "baixou", conversas: salvo?.conversas ?? 0 };
  }

  return { acao: "nada", conversas: 0 };
}

/** Apaga a cópia guardada no aparelho (botão de privacidade). */
export async function apagarCofre(): Promise<void> {
  const db = await abrir();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(LOJA, "readwrite");
    tx.objectStore(LOJA).delete(CHAVE);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}
