#!/usr/bin/env python3
"""
Bot de Procura de Carros
------------------------
Corre no GitHub Actions três vezes por dia. Percorre os endereços de pesquisa
definidos em config.json, aplica os filtros do bloco a que cada pesquisa
pertence, e envia um email só com os anúncios ainda não vistos.

Os motores de risco não são escondidos — aparecem no email com aviso a
vermelho, para decidires tu.
"""

import json
import os
import re
import smtplib
import sys
import time
import unicodedata
from datetime import datetime
from email.message import EmailMessage

import requests

CONFIG_FILE = "config.json"
SEEN_FILE = "seen.json"
MAX_SEEN = 5000
PAUSA = 2.5
TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9",
}


# --------------------------------------------------------------- utilitarios
def sem_acentos(texto):
    txt = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in txt if not unicodedata.combining(c)).lower()


def carregar_json(caminho, omissao):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return omissao


def primeiro_numero(valor):
    """Extrai o primeiro numero de algo que pode ser int, str ou dict."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    if isinstance(valor, dict):
        for chave in ("value", "key", "label", "amount", "units", "displayValue"):
            if chave in valor:
                n = primeiro_numero(valor[chave])
                if n is not None:
                    return n
        return None
    texto = str(valor).replace("\u00a0", " ")
    texto = re.sub(r"[.\s](?=\d{3}\b)", "", texto)      # 175.000 -> 175000
    m = re.search(r"\d+", texto.replace(",", "."))
    return int(m.group()) if m else None


def euros(n):
    return f"{n:,}".replace(",", ".") + " €" if n else "s/ preço"


def formatar_data(bruto):
    """
    Transforma a data do anuncio em algo legivel: «hoje», «ontem», «ha 5 dias»
    ou a data propriamente dita. Um anuncio antigo negoceia-se melhor que um
    acabado de publicar, por isso vale a pena ver isto de relance.
    """
    if not bruto:
        return ""
    texto = str(bruto)[:19].replace("T", " ")
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(texto, formato)
            break
        except ValueError:
            d = None
    if d is None:
        return str(bruto)[:10]

    dias = (datetime.now() - d).days
    if dias <= 0:
        return "hoje"
    if dias == 1:
        return "ontem"
    if dias < 30:
        return f"há {dias} dias"
    if dias < 365:
        return f"há {dias // 30} meses · {d:%d/%m}"
    return f"{d:%d/%m/%Y}"


# --------------------------------------------------------------- extracao
def extrair_next_data(html):
    """
    Encontra o bloco de dados da pagina. Tenta os formatos mais usados, por
    ordem: __NEXT_DATA__ (Standvirtual, OLX), __NUXT_DATA__, __APOLLO_STATE__
    e, em ultimo recurso, os blocos ld+json que muitos sites publicam.
    """
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    for ident in ("__NUXT_DATA__", "__APOLLO_STATE__", "__INITIAL_STATE__"):
        m = re.search(ident + r'\s*=\s*(\{.*?\})\s*;?\s*</script>', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue

    blocos = []
    for bruto in re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL):
        try:
            blocos.append(json.loads(bruto))
        except json.JSONDecodeError:
            continue
    return {"ldjson": blocos} if blocos else None


def percorrer(obj, _prof=0):
    """
    Percorre a estrutura JSON. Quando encontra uma string que e ela propria
    JSON, abre-a e continua la dentro — e assim que o Standvirtual guarda os
    anuncios, dentro da cache de GraphQL em props.pageProps.urqlState.
    """
    if _prof > 60:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from percorrer(v, _prof + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from percorrer(v, _prof + 1)
    elif isinstance(obj, str) and len(obj) > 80:
        texto = obj.lstrip()
        if texto[:1] in "{[":
            try:
                yield from percorrer(json.loads(obj), _prof + 1)
            except json.JSONDecodeError:
                return


def ler_parametros(no):
    """Le ano, km, preco, combustivel e data de publicacao do anuncio."""
    ano = km = preco = None
    combustivel = None
    params = no.get("params") or no.get("parameters") or []
    if isinstance(params, list):
        for p in params:
            if not isinstance(p, dict):
                continue
            chave = str(p.get("key") or p.get("name") or "").lower()
            valor = p.get("value")
            if valor in (None, "", []):
                valor = p.get("displayValue")
            if chave in ("motor_year", "year", "ano", "first_registration_year",
                         "production_year", "rok_produkcji"):
                ano = primeiro_numero(valor)
            elif chave in ("motor_mileage", "mileage", "quilometros", "przebieg"):
                km = primeiro_numero(valor)
            elif chave in ("price", "preco"):
                preco = primeiro_numero(valor)
            elif chave in ("fuel_type", "combustivel", "fuel", "petrol"):
                bruto = p.get("displayValue") or p.get("value")
                if isinstance(bruto, dict):
                    bruto = bruto.get("label") or bruto.get("key") or bruto.get("value")
                if isinstance(bruto, str):
                    combustivel = bruto

    if preco is None:
        preco = primeiro_numero(no.get("price"))
    if ano is None:
        ano = primeiro_numero(no.get("year"))
    if km is None:
        km = primeiro_numero(no.get("mileage"))
    if combustivel is None and isinstance(no.get("fuelType"), str):
        combustivel = no["fuelType"]

    # ano, se nada resultou: tenta o titulo (ex.: "Yaris 2014") ou a data
    if ano is None:
        import re as _re
        m = _re.search(r"\b(19[89]\d|20[0-3]\d)\b", str(no.get("title") or ""))
        if m:
            ano = int(m.group())

    data = None
    for campo in ("createdAt", "created_at", "publishedAt", "lastRefreshTime",
                  "validToDate", "date"):
        v = no.get(campo)
        if isinstance(v, str) and len(v) >= 8:
            data = v
            break

    return ano, km, preco, combustivel, data


def extrair_anuncios(html, site=None):
    """
    `site` diz como reconhecer um anuncio naquele site: `marca_url` e o pedaco
    que aparece no endereco de qualquer anuncio, e `base` serve para completar
    enderecos relativos. Sem `site`, assume Standvirtual.
    """
    site = site or {}
    marca = site.get("marca_url", "/anuncio/")
    base = site.get("base", "https://www.standvirtual.com")

    dados = extrair_next_data(html)
    if not dados:
        return None                      # sinaliza falha de leitura

    anuncios, ja_visto = [], set()
    for no in percorrer(dados):
        if not isinstance(no, dict):
            continue
        url = no.get("url") or no.get("link")
        titulo = no.get("title") or no.get("name")
        if not isinstance(url, str) or not isinstance(titulo, str):
            continue
        if len(titulo) < 8 or marca not in url:
            continue
        if url in ja_visto:
            continue
        ja_visto.add(url)

        ano, km, preco, combustivel, data = ler_parametros(no)
        if not url.startswith("http"):
            url = base + url

        anuncios.append({
            "id": str(no.get("id") or url),
            "titulo": titulo.strip(),
            "url": url,
            "ano": ano,
            "km": km,
            "preco": preco,
            "combustivel": combustivel,
            "data": data,
            "site": site.get("nome", "Standvirtual"),
        })
    return anuncios


# --------------------------------------------------------------- filtragem
def avaliar(anuncio, bloco, cfg):
    """Devolve (aceite, motivo, lista_de_avisos)."""
    texto = sem_acentos(anuncio["titulo"])

    for palavra in cfg.get("excluir", []):
        if sem_acentos(palavra) in texto:
            return False, f"excluido: {palavra}", []

    preco = anuncio["preco"]
    if preco is None:
        return False, "sem preco", []
    if preco < cfg.get("preco_minimo_absoluto", 400):
        return False, "preco irrealista", []
    if preco > bloco["preco_filtro"]:
        return False, "acima do filtro de preco", []

    if anuncio["ano"] is not None and anuncio["ano"] < bloco["ano_min"]:
        return False, "ano abaixo do minimo", []
    if anuncio["km"] is not None and anuncio["km"] > bloco["km_max"]:
        return False, "km acima do maximo", []

    # Escaloes so de gasoleo (Megane). Se o combustivel for desconhecido o
    # anuncio passa na mesma — mais vale ver um a mais do que perder um bom.
    if bloco.get("so_gasoleo"):
        combustivel = sem_acentos(anuncio.get("combustivel") or "")
        if combustivel and not any(p in combustivel for p in ("diesel", "gasoleo")):
            return False, "nao e gasoleo", []
        if not combustivel and not any(p in texto for p in ("dci", "diesel", "gasoleo")):
            pass  # titulo sem indicacao: deixa passar e vai assinalado no email

    avisos = []
    for m in cfg.get("motores_alerta", []):
        if sem_acentos(m["termo"]) in texto and m["aviso"] not in avisos:
            avisos.append(m["aviso"])
    return True, "ok", avisos


# ------------------------------------------------------------------ email
def montar_email(novos, cfg, cortados=0):
    total = sum(len(v) for v in novos.values())
    p = ['<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px">',
         f'<h2 style="margin:0 0 4px">{total} anúncios novos</h2>',
         f'<p style="color:#777;margin:0 0 18px">{datetime.now():%d/%m/%Y %H:%M}</p>']

    for nome_bloco, itens in novos.items():
        if not itens:
            continue
        teto = cfg["blocos"][nome_bloco]["preco_max"]
        p.append(
            f'<h3 style="background:#1F3864;color:#fff;padding:6px 10px;margin:18px 0 8px">'
            f'Bloco {nome_bloco} &nbsp;·&nbsp; {len(itens)} &nbsp;·&nbsp; '
            f'teto {euros(teto)}</h3>'
        )
        for a in itens:
            det = []
            det.append(str(a["ano"]) if a["ano"] else "ano ?")
            if a["km"]:
                det.append(f"{a['km']:,}".replace(",", ".") + " km")
            if a.get("combustivel"):
                det.append(a["combustivel"])
            if a.get("data"):
                det.append("publicado " + formatar_data(a["data"]))
            det.append(f'<b>{a.get("site", "?")}</b>')

            acima = a["preco"] and a["preco"] > teto
            nota_teto = (' <span style="color:#B26B00">· acima do teto, só com '
                         'negociação</span>') if acima else ""

            p.append(
                f'<p style="margin:0 0 12px">'
                f'<a href="{a["url"]}" style="font-weight:bold;color:#1F3864;'
                f'text-decoration:none">{a["titulo"]}</a><br>'
                f'<span style="color:#C00000;font-weight:bold">{euros(a["preco"])}</span> '
                f'<span style="color:#777">· {" · ".join(det)}</span>{nota_teto}'
            )
            for aviso in a["avisos"]:
                p.append(f'<br><span style="color:#C00000">⚠ {aviso}</span>')
            p.append("</p>")

    if cortados:
        p.append(
            f'<p style="color:#B26B00;margin:18px 0 0">Mais {cortados} anúncios '
            f'passaram os filtros mas ficaram de fora deste email. Vão aparecer '
            f'os mais baratos de cada bloco; o resto vê-se no site.</p>'
        )

    p.append(
        '<hr style="border:none;border-top:1px solid #ddd;margin:22px 0 10px">'
        '<p style="color:#999;font-size:12px">Este bot encontra carros, não os avalia. '
        'Fóruns de proprietários primeiro, mercado depois, contas no fim. '
        'InfoMatrícula e Certidão Permanente antes de qualquer deslocação.</p>'
        '</body></html>'
    )
    return "\n".join(p)


def enviar_email(corpo, total):
    remetente = os.environ.get("EMAIL_REMETENTE")
    palavra_passe = os.environ.get("EMAIL_PALAVRA_PASSE")
    destinatario = os.environ.get("EMAIL_DESTINATARIO")

    if not (remetente and palavra_passe and destinatario):
        print("!! Faltam secrets de email. Email nao enviado.")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"Bot de carros — {total} anúncios novos"
    msg["From"] = remetente
    msg["To"] = destinatario
    msg.set_content("Este email precisa de um cliente com HTML.")
    msg.add_alternative(corpo, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(remetente, palavra_passe)
        smtp.send_message(msg)
    return True


# ------------------------------------------------------------------- main
def main():
    cfg = carregar_json(CONFIG_FILE, None)
    if not cfg:
        sys.exit("config.json em falta ou invalido.")

    vistos = set(carregar_json(SEEN_FILE, []))
    # (a primeira execucao passou a enviar email tambem)
    novos = {nome: [] for nome in cfg["blocos"]}
    falhas_leitura = 0
    balanco = {}

    sessao = requests.Session()
    sessao.headers.update(HEADERS)

    for pesquisa in cfg["pesquisas"]:
        # Uma pesquisa pode alimentar varios escaloes (o Megane alimenta o 4A
        # e o 4B). Cada anuncio fica no PRIMEIRO escalao cujos criterios cumpra.
        nomes_bloco = pesquisa.get("blocos") or [pesquisa.get("bloco")]
        nomes_bloco = [n for n in nomes_bloco if n]
        desconhecidos = [n for n in nomes_bloco if n not in cfg["blocos"]]
        if desconhecidos:
            print(f"!! Escalao desconhecido em «{pesquisa['nome']}»: {desconhecidos}")
        nomes_bloco = [n for n in nomes_bloco if n in cfg["blocos"]]
        if not nomes_bloco:
            continue

        try:
            resposta = sessao.get(pesquisa["url"], timeout=TIMEOUT)
            resposta.raise_for_status()
        except requests.RequestException as erro:
            print(f"   {pesquisa['nome']}: falhou o pedido — {erro}")
            time.sleep(PAUSA)
            continue

        nome_site = pesquisa.get("site", "Standvirtual")
        site = dict(cfg.get("sites", {}).get(nome_site, {}), nome=nome_site)
        anuncios = extrair_anuncios(resposta.text, site)
        if anuncios is None:
            falhas_leitura += 1
            balanco.setdefault(nome_site, {"lidos": 0, "novos": 0, "falhas": 0})
            balanco[nome_site]["falhas"] += 1
            print(f"   [{nome_site}] {pesquisa['nome']}: nao encontrei os dados na pagina")
            time.sleep(PAUSA)
            continue

        aceites = 0
        for a in anuncios:
            if a["id"] in vistos:
                continue
            vistos.add(a["id"])
            for nome_bloco in nomes_bloco:
                # Paginas de marca (Auto SAPO) trazem todos os modelos juntos.
                # `modelos` limita quais contam para este escalao.
                modelos = (pesquisa.get("modelos_por_bloco", {}).get(nome_bloco)
                           or pesquisa.get("modelos"))
                if modelos:
                    titulo = sem_acentos(a["titulo"])
                    if not any(sem_acentos(mod) in titulo for mod in modelos):
                        continue
                ok, _motivo, avisos = avaliar(a, cfg["blocos"][nome_bloco], cfg)
                if ok:
                    a["avisos"] = avisos
                    a["pesquisa"] = pesquisa["nome"]
                    novos[nome_bloco].append(a)
                    aceites += 1
                    break

        balanco.setdefault(nome_site, {"lidos": 0, "novos": 0, "falhas": 0})
        balanco[nome_site]["lidos"] += len(anuncios)
        balanco[nome_site]["novos"] += aceites
        print(f"   [{nome_site}] {pesquisa['nome']}: {len(anuncios)} lidos, {aceites} novos")
        time.sleep(PAUSA)

    print("\n--- BALANCO POR SITE ---")
    for nome_site, b in balanco.items():
        estado = "OK" if b["lidos"] else "NAO LEU NADA — estrutura por decifrar"
        print(f"   {nome_site:<14} {b['lidos']:>4} lidos · {b['novos']:>3} novos · "
              f"{b['falhas']} paginas ilegiveis   {estado}")

    for nome in novos:
        novos[nome].sort(key=lambda x: x["preco"] or 0)

    total = sum(len(v) for v in novos.values())
    print(f"\nTotal de novos: {total}")

    if falhas_leitura == len(cfg["pesquisas"]):
        print("!! Nenhuma pagina foi lida. O site mudou de estrutura.")

    if total:
        # Trava de seguranca: se por algum motivo aparecerem centenas de
        # anuncios de uma vez, manda os mais baratos de cada bloco e diz
        # quantos ficaram de fora, em vez de um email interminavel.
        limite = cfg.get("max_por_email", 80)
        cortados = 0
        if total > limite:
            por_bloco = max(5, limite // max(1, len([v for v in novos.values() if v])))
            for nome, itens in novos.items():
                if len(itens) > por_bloco:
                    cortados += len(itens) - por_bloco
                    novos[nome] = itens[:por_bloco]
            print(f"Lista grande: {cortados} anuncios ficaram de fora do email.")

        enviados = sum(len(v) for v in novos.values())
        if enviar_email(montar_email(novos, cfg, cortados), enviados):
            print(f"Email enviado com {enviados} anuncios.")
    else:
        print("Nada novo — email nao enviado.")

    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(vistos)[-MAX_SEEN:], f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
