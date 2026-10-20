/**
 * Sala — o "nome de usuário" da Nébula.
 *
 * Cada pessoa escolhe um apelido. As conversas dela ficam guardadas numa
 * "sala" separada no servidor (Supabase), então ninguém vê as conversas dos
 * outros. O apelido é salvo no aparelho; o site manda em todo pedido no
 * cabeçalho X-Nebula-Sala.
 *
 * Não tem senha: quem digitar o mesmo apelido entra na mesma sala. Serve para
 * separar pessoas de confiança. (Uma senha pode ser somada depois.)
 */

const CHAVE = "nebula:sala";

let ouvintes = new Set<() => void>();

export function getSala(): string {
  try {
    return (localStorage.getItem(CHAVE) || "").trim();
  } catch {
    return "";
  }
}

/** O apelido já foi escolhido? */
export function temSala(): boolean {
  return getSala().length > 0;
}

export function definirSala(apelido: string): void {
  const limpo = apelido.trim().toLowerCase().slice(0, 40);
  try {
    localStorage.setItem(CHAVE, limpo);
  } catch {
    /* sem armazenamento: vale nesta sessão */
  }
  ouvintes.forEach((fn) => fn());
}

export function assinarSala(fn: () => void): () => void {
  ouvintes.add(fn);
  return () => {
    ouvintes.delete(fn);
  };
}
