/** "gemini-3.8-flash" -> "Gemini 3.8 Flash" */
export function prettyModel(id: string): string {
  const name = id.includes("/") ? id.split("/").slice(1).join("/") : id;
  return name
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
