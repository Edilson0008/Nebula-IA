/**
 * Cofre — guarda a cópia das conversas no próprio aparelho.
 *
 * Por que isso existe: o servidor grátis (Render) apaga o disco toda vez que
 * reinicia. Então o histórico não pode morar só lá.
 *
 * Para não perder nada, guardamos em DOIS lugares do aparelho:
 *   1. IndexedDB  — aguenta arquivos grandes (é o principal).
 *   2. localStorage — reserva menor (só o essencial, se o IndexedDB sumir).
 *
 * E ainda pedimos ao navegador "armazenamento persistente", para ele não
 * apagar os dados sozinho quando faltar espaço.
 *
 * Também dá para BAIXAR um arquivo .nebula com a cópia (você guarda onde
 * quiser) e RESTAURAR esse arquivo depois. É a salvação garantida.
 */

import { api } from "./api";

const BANCO = "nebula-cofre";
const LOJA = "copias";
const VERSAO = 1;
const CHAVE = "principal";
const CHAVE_RESERVA = "nebula:cofre-reserva";

export interface CofreSalvo {
  dados: string;
  salvoEm: number;
  conversas: number;
  mensagens: number;
  memorias: number;
}

/** Pede ao navegador para não apagar os dados deste site. */
export async function pedirPersistencia(): Promise<boolean> {
  try {
    if (navigator.storage?.persist) {
      if (await navigator.storage.persisted()) return true;
      return await navigator.storage.persist();
    }
  } catch {
    /* alguns navegadores não têm: segue sem */
  }
  return false;
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

export async function lerCofre(): Promise<CofreSalvo | null> {
  // Tenta o principal (IndexedDB) e, se falhar, a reserva (localStorage).
  try {
    const principal = await ler<CofreSalvo>(CHAVE);
    if (principal?.dados) return principal;
  } catch {
    /* IndexedDB indisponível: tenta a reserva */
  }
  try {
    const bruto = localStorage.getItem(CHAVE_RESERVA);
    if (bruto) return JSON.parse(bruto) as CofreSalvo;
  } catch {
    /* nada guardado */
  }
  return null;
}

/**
 * Guarda a cópia atual do servidor no aparelho.
 * Salva nos dois lugares: IndexedDB (principal) e localStorage (reserva,
 * se couber — o localStorage tem limite de ~5 MB).
 */
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

    // 1) Principal: IndexedDB (aguenta tamanho grande).
    try {
      await gravar(CHAVE, salvo);
    } catch {
      /* segue para a reserva */
    }

    // 2) Reserva: localStorage, só se o dado couber (senão o navegador
    //    lança QuotaExceededError e a cópia principal continua valendo).
    try {
      localStorage.setItem(CHAVE_RESERVA, JSON.stringify(salvo));
    } catch {
      /* grande demais para a reserva: tudo bem, o principal já foi salvo */
    }

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
 * Guarda uma cópia JÁ RECEBIDA (vem no fim do streaming).
 * Evita uma segunda requisição e garante que a cópia seja salva no exato
 * momento em que a resposta termina.
 */
export async function salvarDadosRecebidos(dados: string): Promise<void> {
  if (!dados) return;
  const salvo: CofreSalvo = {
    dados,
    salvoEm: Date.now(),
    conversas: 0,
    mensagens: 0,
    memorias: 0,
  };
  try {
    await gravar(CHAVE, salvo);
  } catch {
    /* tenta a reserva */
  }
  try {
    localStorage.setItem(CHAVE_RESERVA, JSON.stringify(salvo));
  } catch {
    /* grande demais para a reserva: o principal já foi salvo */
  }
}

/**
 * Mantém servidor e cofre iguais. Chamado ao abrir o app.
 *
 * - Servidor vazio + cofre com dados  -> devolve o cofre (restaura).
 * - Servidor com dados                -> atualiza o cofre (baixa).
 */
export async function sincronizar(): Promise<ResultadoSincronia> {
  await pedirPersistencia();

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

/** Apaga as cópias guardadas no aparelho (botão de privacidade). */
export async function apagarCofre(): Promise<void> {
  try {
    const db = await abrir();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(LOJA, "readwrite");
      tx.objectStore(LOJA).delete(CHAVE);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* nada a apagar */
  }
  try {
    localStorage.removeItem(CHAVE_RESERVA);
  } catch {
    /* nada a apagar */
  }
}

/**
 * Baixa a cópia como arquivo .nebula — para guardar onde quiser
 * (Drive, cartão SD, enviar para si mesmo). É a salvação garantida.
 */
export async function baixarArquivo(): Promise<boolean> {
  try {
    const { dados, estatisticas } = await api.backupExport();
    const conteudo = JSON.stringify({
      app: "nebula",
      versao: 1,
      salvoEm: new Date().toISOString(),
      estatisticas,
      dados,
    });
    const blob = new Blob([conteudo], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const data = new Date().toISOString().slice(0, 10);
    a.href = url;
    a.download = `nebula-conversas-${data}.nebula`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    return true;
  } catch {
    return false;
  }
}

/** Restaura a partir do conteúdo de um arquivo .nebula. */
export async function restaurarArquivo(texto: string): Promise<number> {
  const obj = JSON.parse(texto) as { app?: string; dados?: string };
  if (obj.app !== "nebula" || typeof obj.dados !== "string") {
    throw new Error("Este arquivo não é uma cópia da Nébula.");
  }
  const r = await api.backupImport(obj.dados);
  return r.restaurado.conversas;
}
