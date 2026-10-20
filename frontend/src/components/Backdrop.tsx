import { useSettings } from "../settings";

/**
 * Fundo animado atrás do chat (camada fixa, sem clique).
 *
 * - aurora: três orbes gigantes borradas flutuando (cor de destaque + roxo + rosa);
 * - stars:  campo de estrelas cintilando;
 * - limpo:  nada (só o fundo liso do tema).
 */
export function Backdrop() {
  const { bgStyle } = useSettings();

  if (bgStyle === "clean") return null;

  if (bgStyle === "stars") {
    return (
      <div className="nebula-backdrop" aria-hidden="true">
        <div className="nebula-stars" />
      </div>
    );
  }

  return (
    <div className="nebula-backdrop" aria-hidden="true">
      <div className="nebula-orb nebula-orb-a" />
      <div className="nebula-orb nebula-orb-b" />
      <div className="nebula-orb nebula-orb-c" />
    </div>
  );
}
