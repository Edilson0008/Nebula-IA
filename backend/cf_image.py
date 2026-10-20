"""Geração de imagem pela Cloudflare Workers AI (FLUX-1-schnell).

A conta gratuita entrega 10.000 "neurônios" por dia (reseta 00:00 UTC) —
dezenas de imagens grátis por dia, em ~1-4 segundos por imagem.

Como usar:
    1. Crie uma conta grátis em dash.cloudflare.com (plano Free, sem cartão).
    2. Workers & Pages → Workers AI → crie um token de API com permissão
       "Workers AI: Read" (My Profile → API Tokens → Create Token).
    3. Preencha no backend/.env:
         CLOUDFLARE_ACCOUNT_ID=...
         CLOUDFLARE_API_TOKEN=...

O token fica SÓ no servidor — o navegador nunca vê. Sem as variáveis, este
módulo não faz nada e o app segue para os modelos de imagem do Gemini.
"""

import base64
import json
import os
import urllib.request

API_URL = (
    "https://api.cloudflare.com/client/v4/accounts/"
    "{account}/ai/run/@cf/black-forest-labs/flux-1-schnell"
)
# FLUX schnell: 4 passos = bom, rápido e cabe com folga na cota diária.
STEPS = 4
TIMEOUT_SECONDS = 60


def configured() -> bool:
    """True quando há conta + token no .env."""
    return bool(
        os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        and os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    )


def generate(prompt: str) -> tuple[bytes, str] | None:
    """Gera uma imagem e devolve (bytes, mime) em JPEG.

    Levanta exceção em erro de rede/API (quem chama decide o fallback);
    devolve None quando não está configurado.
    """
    if not configured():
        return None

    account = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
    token = os.environ["CLOUDFLARE_API_TOKEN"].strip()
    body = json.dumps(
        {"prompt": prompt[:2048], "steps": STEPS}  # limite do modelo: 2048
    ).encode("utf-8")

    request = urllib.request.Request(
        API_URL.format(account=account),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    # REST embrula em {"result": {...}}; a binding devolve o resultado direto.
    result = payload.get("result", payload)
    image_b64 = result.get("image") if isinstance(result, dict) else None
    if not image_b64:
        raise RuntimeError(f"sem imagem na resposta: {str(payload)[:160]}")
    return base64.b64decode(image_b64), "image/jpeg"
