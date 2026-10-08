# Bot de Procura de Carros

Corre sozinho na nuvem, três vezes por dia, e envia um email só quando aparecem anúncios novos que passam os teus filtros.

**Custo: zero.** O GitHub Actions é gratuito para repositórios públicos.

---

## Como está configurado

Seis escalões. **Sem híbridos e sem elétricos.**

| Escalão | O que vigia | Ano mín. | Km máx. | Teto de compra |
|---|---|---|---|---|
| **1A** Toyota recente | Yaris, Auris, Aygo | 2010 | 175.000 | 4.000 € |
| **1B** Toyota km alto | Corolla, Avensis + Yaris/Auris/Aygo antigos | 2005 | 250.000 | 3.500 € |
| **2** Citadinos | qualquer marca | 2010 | 175.000 | 4.000 € |
| **3** Ford Focus | berlina e SW | 2012 | 175.000 | 6.000 € |
| **4A** Mégane recente | berlina e ST, só gasóleo | 2014 | 175.000 | 5.500 € |
| **4B** Mégane km alto | berlina e ST, só gasóleo | 2010 | 200.000 | 4.000 € |

> As pesquisas Toyota alimentam os dois escalões: o carro é testado primeiro no 1A e, se não couber por anos ou quilómetros, cai no 1B.

O bot procura um pouco acima de cada teto e **marca no email** os que ficaram acima, para veres se dá para negociar para dentro do limite.

**Frequência:** 3× por dia — 8h, 14h e 20h em Portugal.

**Motores marcados a vermelho no email:** PureTech, 1.6 THP, EcoBoost 1.0, PowerShift, EDC, caixas automáticas, D-4D e dCi. Não são escondidos — aparecem com aviso, para decidires.

---

## Onde procura, e porquê só aí

| Site | Estado | O que traz |
|---|---|---|
| **Standvirtual** | ✅ 25 pesquisas, **só particulares** | O grosso. É onde está a margem. |
| **Auto SAPO** | ✅ 9 pesquisas, filtradas por preço/ano/km | Pouco volume, quase tudo stands. |
| **OLX** | ❌ Recusa acesso automatizado (403) | — |
| **CustoJusto** | ❌ Proíbe no `robots.txt` | — |

O OLX e o CustoJusto não estão em falta nem avariados: **os próprios sites dizem que não querem acesso automatizado.** Não é coisa a contornar. Para esses dois, o caminho é criares **pesquisas guardadas com alerta** na conta de cada um — fazes a pesquisa com os filtros, guardas, e eles notificam-te no telemóvel.

Ficou um equilíbrio útil: **Standvirtual = particulares** (onde compras) e **Auto SAPO = stands** (onde confirmas o teto de revenda).

**O Facebook Marketplace não dá.** Exige sessão iniciada e bloqueia acesso automatizado; um bot a entrar na tua conta arrisca suspensão. Usa as pesquisas guardadas da app.

---

## Instalação de raiz — 20 minutos, uma única vez

### Passo 1 — Criar conta no GitHub
Vai a **github.com** e cria conta. É gratuito.

### Passo 2 — Criar o repositório
1. **+** no canto superior direito → **New repository**
2. Nome: `bot-carros`
3. Escolhe **Public** (é o que dá minutos gratuitos ilimitados)
4. **Create repository**

### Passo 3 — Carregar os ficheiros
**Add file** → **Upload files**, arrasta `bot.py`, `config.json` e `requirements.txt`, depois **Commit changes**.

Agora o workflow: **Add file** → **Create new file**, e no nome escreve exatamente:

```
.github/workflows/procurar.yml
```

Cola o conteúdo do `procurar.yml` e faz **Commit changes**.

### Passo 4 — Palavra-passe de aplicação do Gmail
1. Vai a **myaccount.google.com/apppasswords**
2. Se não abrir, ativa primeiro a **Verificação em duas etapas** em myaccount.google.com/security
3. Cria uma nova, chamada `bot-carros`
4. O Google mostra 16 letras — copia-as **sem espaços**. Só aparecem uma vez.

> Nunca partilhes essa palavra-passe nem a fotografes: dá acesso total à conta Google. Se escapar, revoga-a nessa mesma página e cria outra.

### Passo 5 — Guardar as palavras-passe no GitHub
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**. Cria três, um de cada vez:

| Nome | Valor |
|---|---|
| `EMAIL_REMETENTE` | o teu endereço Gmail |
| `EMAIL_PALAVRA_PASSE` | as 16 letras, sem espaços |
| `EMAIL_DESTINATARIO` | o email onde queres receber |

Os nomes têm de estar escritos exatamente assim. Os valores ficam encriptados — nem tu os voltas a ver.

### Passo 6 — Testar
**Actions** → **Procurar carros** (na coluna da esquerda) → **Run workflow** → **Run workflow**.

Espera dois a três minutos, abre a corrida e expande o passo **Correr o bot**.

---

## Como atualizar quando eu mandar ficheiros novos

1. **Add file** → **Upload files**, arrasta o ficheiro — substitui o antigo
2. **Commit changes**
3. Se os **critérios** mudaram (preço, ano, km, escalões), apaga o `seen.json`:
   abre-o → **⋯** no canto → **Delete file** → **Commit changes**
4. **Actions** → **Procurar carros** → **Run workflow**

> O `seen.json` é a memória de anúncios já vistos. Se os critérios mudarem e não o apagares, os anúncios que agora passariam continuam marcados como vistos e não recebes nada. O bot volta a criá-lo sozinho.

---

## Como alterar os critérios

Abre o `config.json` no GitHub, carrega no lápis, edita, **Commit changes**.

**Mudar preço, ano ou km:** altera os números do escalão em `blocos`. O `preco_filtro` deve ficar sempre acima do `preco_max`.

**Acrescentar um modelo:** faz a pesquisa no site com os filtros postos, copia o endereço da barra do browser, e acrescenta uma linha em `pesquisas` com esse endereço e o escalão.

**Receber menos emails:** em `.github/workflows/procurar.yml`, muda o `cron` para `'0 7 * * *'` (uma vez por dia).

---

## Como ler o registo

No fim de cada corrida há um balanço:

```
--- BALANCO POR SITE ---
   Standvirtual    210 lidos ·  8 novos · 0 paginas ilegiveis   OK
   AutoSAPO         16 lidos ·  0 novos · 0 paginas ilegiveis   OK
```

- **lidos** — anúncios que o bot conseguiu ler
- **novos** — os que passaram os filtros e ainda não tinham sido vistos
- **paginas ilegiveis** — se este número subir, o site mudou de estrutura

**«0 anuncios (pesquisa sem resultados)»** não é erro: é não haver carros nesses critérios.

---

## Se alguma coisa correr mal

**Não recebi email** — normal se não houver nada novo. O bot só escreve quando há novidade.

**«nao encontrei os dados na pagina»** em todas as pesquisas de um site — esse site mudou a estrutura interna. Acontece algumas vezes por ano. Manda-me o registo.

**«falhou o pedido — 403»** — o site passou a recusar acesso automatizado. Não há volta a dar; tira essas pesquisas do `config.json`.

**«falhou o pedido — 404»** no Auto SAPO — normalmente é a pesquisa sem resultados, e o bot já lida com isso sozinho.

**O email não sai** — quase sempre é a palavra-passe de aplicação. Gera outra e substitui o secret.

**Parou de correr passados uns meses** — o GitHub desativa workflows agendados em repositórios sem atividade. Vai a Actions e carrega em **Enable workflow**.

---

## Notas

**Isto vai partir mais cedo ou mais tarde.** O bot lê as páginas como se fosse um browser. Quando os sites mudarem a estrutura interna — e mudam — deixa de encontrar anúncios. Não é avaria tua; é a natureza de qualquer ferramenta deste género.

**Os filtros são aplicados duas vezes:** no endereço, quando o site permite, e outra vez em Python a partir dos dados de cada anúncio. É rede de segurança — já apanhámos um Corolla com 445.000 km que o filtro do próprio site deixou passar.

**A pausa de 2,5 segundos entre pedidos é intencional.** Não a reduzas. Uso pessoal moderado é uma coisa; martelar os servidores é outra, e é a forma mais rápida de apanhares um bloqueio.

**Este bot encontra carros. Não os avalia.**

Continua a valer a regra: fóruns de proprietários primeiro, mercado depois, contas no fim. E InfoMatrícula mais Certidão Permanente antes de meteres o carro na estrada para ir ver seja o que for.
