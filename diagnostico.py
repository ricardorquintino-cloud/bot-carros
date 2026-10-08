#!/usr/bin/env python3
"""
Diagnóstico — corre uma vez, mostra como está estruturada a página.
Não envia emails nem altera nada. Serve só para perceber porque é que
o bot leu 0 anúncios.
"""

import json
import re

import requests

URL = "https://www.standvirtual.com/carros/toyota/yaris"
TIMEOUT = 40

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9",
}


def percorrer(obj, caminho=""):
    if isinstance(obj, dict):
        yield caminho, obj
        for k, v in obj.items():
            yield from percorrer(v, f"{caminho}.{k}" if caminho else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5]):
            yield from percorrer(v, f"{caminho}[{i}]")


def main():
    print(f"A pedir: {URL}\n")
    r = requests.get(URL, headers=HEADERS, timeout=TIMEOUT)
    html = r.text

    print(f"Estado HTTP .......... {r.status_code}")
    print(f"Endereço final ....... {r.url}")
    print(f"Tamanho da pagina .... {len(html)} caracteres")

    titulo = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
    print(f"Titulo da pagina ..... {titulo.group(1).strip()[:90] if titulo else 'nenhum'}")

    print("\n--- SINAIS DE BLOQUEIO ---")
    for palavra in ["captcha", "cloudflare", "access denied", "acesso negado",
                    "consent", "cookie", "robot", "unusual traffic"]:
        n = html.lower().count(palavra)
        if n:
            print(f"  «{palavra}» aparece {n}x")

    print("\n--- ONDE ESTAO OS DADOS ---")
    print(f"  __NEXT_DATA__ presente ... {'sim' if '__NEXT_DATA__' in html else 'NAO'}")
    print(f"  __next_f presente ........ {'sim' if '__next_f' in html else 'NAO'}")
    print(f"  ocorrencias de /anuncio/ . {html.count('/anuncio/')}")
    print(f"  ocorrencias de /oferta/ .. {html.count('/oferta/')}")

    ligacoes = re.findall(r'href="([^"]*(?:anuncio|oferta|item)[^"]*)"', html)[:8]
    if ligacoes:
        print("\n  Exemplos de endereços de anúncio encontrados no HTML:")
        for l in ligacoes:
            print(f"    {l[:120]}")

    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        print("\n  Sem __NEXT_DATA__ — os dados devem vir por __next_f.")
        for i, bloco in enumerate(re.findall(r'self\.__next_f\.push\((.*?)\)</script>',
                                             html, re.DOTALL)[:3]):
            print(f"\n  __next_f bloco {i} (300 caracteres):")
            print("   ", bloco[:300].replace("\\n", " "))
        return

    try:
        dados = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f"\n  __NEXT_DATA__ existe mas nao e JSON valido: {e}")
        return

    print(f"\n  __NEXT_DATA__ lido. Chaves de topo: {list(dados.keys())}")

    candidatos = []
    for caminho, no in percorrer(dados):
        chaves = set(no.keys())
        if {"id"} & chaves and ({"title"} & chaves or {"name"} & chaves):
            candidatos.append((caminho, no))

    print(f"\n--- OBJETOS COM id+title ENCONTRADOS: {len(candidatos)} ---")
    for caminho, no in candidatos[:3]:
        print(f"\n  Caminho: {caminho}")
        print(f"  Chaves:  {sorted(no.keys())}")
        amostra = {k: v for k, v in no.items()
                   if k in ("id", "title", "name", "url", "slug", "price",
                            "params", "parameters", "category")}
        texto = json.dumps(amostra, ensure_ascii=False)[:900]
        print(f"  Amostra: {texto}")

    if not candidatos:
        print("\n  Nenhum. Chaves dos 15 maiores objetos do __NEXT_DATA__:")
        todos = [(len(json.dumps(n, ensure_ascii=False)), c, sorted(n.keys())[:14])
                 for c, n in percorrer(dados)]
        todos.sort(reverse=True)
        for tamanho, caminho, chaves in todos[:15]:
            print(f"    [{tamanho:>7}] {caminho[:70]}")
            print(f"              {chaves}")


if __name__ == "__main__":
    main()
