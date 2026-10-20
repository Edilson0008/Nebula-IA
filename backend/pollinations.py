"""Imagem pela Pollinations.ai — o provedor que NÃO pede chave nenhuma.

Endpoint antigo `image.pollinations.ai` (ainda oficial em 2026): aceita
pedido anônimo, sem cadastro e sem token, no modelo Flux (grátis para uso
anônimo). Contras conhecidos e aceitáveis aqui (é o ÚLTIMO antes do texto):
  - o plano anônimo aceita ~1 imagem a cada ~15 s (daí o retry curto);
  - sem SLA de disponibilidade;
  - qualidade/variedade boas, mas menores que os modelos premium.

Se um dia quiser mais volume: conta grátis em auth.pollinations.ai aumenta
o limite sem cartão — mas para começar, ninguém precisa de nada.
"""

import base64
import random
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width=1024&height=1024&model=flux&nologo=true&seed={seed}"
)
TIMEOUT_SECONDS = 60
# Anônimo responde 402 se a janela anterior ainda está quente: dois retries
# curtos cobrem o caso comum de pedidos de imagem em sequência.
RETRIES = 2
RETRY_DELAY_SECONDS = 10


def generate(prompt: str) -> bytes | None:
    """Uma imagem (JPEG/PNG); None quando o serviço não devolveu imagem.

    Erros de rede/limite são engolidos aqui (com log) — a imagem é bônus e
    nunca pode derrubar o chat.
    """
    url = API_URL.format(
        prompt=urllib.parse.quote(prompt[:900]),  # URL não infinita
        seed=random.randint(0, 999_999),  # pedidos repetidos variam
    )
    return _fetch(url)


def edit(image_bytes: bytes, prompt: str, mime: str = "image/jpeg") -> bytes | None:
    """Edita uma imagem existente (img2img) seguindo o prompt.

    Usa o parâmetro `image=` da Pollinations: manda a foto original + a
    instrução e devolve a versão editada. None quando não dá (rede/limite/
    serviço fora) — o chamador decide o próximo passo.
    """
    data_uri = f"data:{mime};base64," + base64.b64encode(image_bytes).decode()
    url = API_URL.format(
        prompt=urllib.parse.quote(prompt[:900]),
        seed=random.randint(0, 999_999),
    )
    url += "&image=" + urllib.parse.quote(data_uri[:6_000_000])
    return _fetch(url)


def _fetch(url: str) -> bytes | None:
    """Baixa uma imagem da URL; None em erro/limite/resposta curta."""
    for attempt in range(RETRIES + 1):
        if attempt:
            time.sleep(RETRY_DELAY_SECONDS)
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "nebula/1.0"}
            )
            with urllib.request.urlopen(
                request, timeout=TIMEOUT_SECONDS
            ) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            print(f"[pollinations] HTTP {exc.code} (limite anonimo ~1 img/15s)")
            continue
        except Exception as exc:  # noqa: BLE001 - rede instável não derruba
            print(f"[pollinations] {str(exc)[:140]}")
            continue
        if len(data) >= 1000:  # erro do serviço vem como página curta
            return data
        print(f"[pollinations] resposta curta ({len(data)} bytes)")
    return None
