import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      // Arquivos gerados pela IA (/files/<projeto>/<arquivo>): servidos pelo
      // backend para o usuário abrir e pré-visualizar direto na conversa.
      "/files": "http://localhost:8000",
    },
  },
});
