/**
 * Separa a resposta do modelo em partes de texto e partes de arquivo.
 *
 * A Nébula marca os arquivos criados assim:
 *
 *     ```file:index.html
 *     <!doctype html>
 *     ...
 *     ```
 *
 * Assim o chat mostra um cartão para cada arquivo (com pré-visualização,
 * abrir, baixar e copiar) em vez de despejar o código na conversa.
 */

export interface TextSegment {
  type: "text";
  content: string;
}

export interface FileSegment {
  type: "file";
  name: string;
  content: string;
  /** false enquanto o arquivo ainda está sendo escrito (streaming). */
  complete: boolean;
}

export type Segment = TextSegment | FileSegment;

export function parseSegments(content: string): Segment[] {
  const segments: Segment[] = [];

  // Criado a cada chamada para não guardar estado entre mensagens.
  const pattern = /```(?:file|arquivo):\s*([^\n`]+?)\s*\n([\s\S]*?)(```|$)/g;

  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(content)) !== null) {
    const before = content.slice(last, match.index).trim();
    if (before) segments.push({ type: "text", content: before });

    segments.push({
      type: "file",
      name: match[1].trim(),
      content: match[2].replace(/\s+$/, ""),
      complete: match[3] === "```",
    });

    last = pattern.lastIndex;
  }

  const tail = content.slice(last).trim();
  if (tail) segments.push({ type: "text", content: tail });

  return segments;
}

/** true se a mensagem contém pelo menos um arquivo criado. */
export function hasFiles(content: string): boolean {
  return parseSegments(content).some((segment) => segment.type === "file");
}

/** Monta a URL de um arquivo gerado, escapando nomes com espaços/acentos. */
export function fileUrl(project: string | null, name: string): string | null {
  if (!project) return null;
  const safeName = name
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `/files/${encodeURIComponent(project)}/${safeName}`;
}
