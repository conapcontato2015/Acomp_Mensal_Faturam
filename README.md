# Acompanhamento Mensal de Faturamento · CONAP

Substitui a planilha **FATURAMENTO_V2**. Cada pessoa (Hellen, Jaísa, Mariana, Natan) lança, por empresa e
competência, a quantidade e o valor dos documentos fiscais do relatório da SEFAZ (CT-e, NF-e, NFC-e,
NFS-e, entradas e saídas). Na conferência, marca **Bateu** em cada linha que confere com o sistema contábil.

## Usar no seu computador (Windows)

1. Instale o Python 3.11 ou superior (python.org; marque **Add python.exe to PATH**).
2. Baixe este repositório (botão *Code › Download ZIP*) e descompacte numa pasta, ex.: `C:\Faturamento`.
3. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele prepara tudo (1–2 minutos) e abre o navegador
   em `http://localhost:5000`.
4. Escolha seu nome na tela **Quem está usando?**.
5. Para trazer os dados antigos: menu **Importar planilha** → envie o `FATURAMENTO_V2.xlsx` → confira a
   prévia (avisos em laranja) → **Confirmar importação**. Dá para desfazer depois.

Dados ficam em `dados/faturamento.db`, com backup automático diário em `dados/backups/` (30 cópias).
Para encerrar, feche a janela preta do sistema.

## Liberar para as colegas na rede do escritório

Use **`iniciar_rede.bat`** no lugar do `iniciar.bat`. Ele mostra o IP do computador; as colegas abrem
`http://IP-DO-SEU-PC:5000`. Na primeira vez o Windows pergunta sobre o Firewall: permita em *Redes privadas*.
O seu computador precisa estar ligado com o sistema aberto.

## O que o sistema faz

| Tela | Para quê |
| --- | --- |
| Painel do mês | Status de cada empresa da carteira (pendente, preenchida, sem movimento), progresso, alerta de variação das saídas (≥ 50% contra a média dos 3 meses anteriores) |
| Lançamento | Números do relatório SEFAZ por tipo; ajustes com motivo; totais ao vivo; colar bloco do Excel; Enter avança; gráfico de entradas × saídas por mês com a parte de ajuste destacada |
| Conferência | Um cartão por empresa com o veredito ("Tudo bateu" / "Faltam N"); um clique marca a linha; filtro "Só com pendência"; detalhes (cancelados, ajustes, subtotais por sentido); Excel e impressão/PDF |
| Empresas | CNPJ, tipos usados, ativa; **responsável editável por qualquer usuário**, com histórico e origem (manual, planilha, integração); importação de responsáveis por planilha |
| Importar planilha | Importa a planilha antiga com prévia, avisos e "desfazer" |
| Histórico | Quem mudou o quê e quando |

Regras principais: quantidade e valor sempre juntos; sem contas digitadas nos campos (diferença = ajuste
com motivo); linha que bateu fica travada; carteiras das colegas são só leitura (com opção "lançar como
substituto"); entradas e saídas nunca se somam.

## Responsáveis vindos de outro sistema

Hoje a carteira é editada à mão ou por planilha (Empresas › Importar responsáveis; o modelo CSV já vem
preenchido). O encaixe do sistema externo está pronto em `faturamento/responsaveis.py`
(`ProvedorApi.buscar`): basta implementar a leitura e configurar `RESPONSAVEIS_PROVEDOR=api` no `.env`.

### Controle Fiscal (mesmo PC)

O Faturamento lê **direto do PostgreSQL do Controle Fiscal, só leitura** (sessão em modo somente leitura,
apenas `SELECT`; nada é gravado lá). No `.env` do Faturamento:

```
FOLHA_DATABASE_URL=postgresql://usuario:senha@localhost:5432/controle_fiscal
# opcional, quando o nome do responsável difere entre os sistemas (NomeLá=NomeAqui;...)
FOLHA_MAPA_RESPONSAVEIS=Natan Lima=Natan;Jaisa Souza=Jaísa
```

Com isso, Empresas mostra **Sincronizar com o Controle Fiscal**: escolhe-se a competência a partir da qual as
trocas valem, vê-se a prévia e aplica-se. Regras (`faturamento/services/controle_fiscal.py`):

- Casa as empresas pelo CNPJ; depois pelo código já vinculado (`external_id = cf:<código>`); por último pelo
  nome — essas aparecem como "casada pelo nome — confira".
- Responsável: troca a partir da competência escolhida, origem "Integração" (sem mudança se já for a mesma pessoa).
  Empresa sem responsável lá e nome sem correspondência aqui só são listados.
- CNPJ é preenchido só quando está vazio aqui (CNPJ diferente é listado, nunca sobrescrito); o código vira
  `external_id = cf:<código>`. Ativa/inativa diferente só é listada; "sem movimento" não é importado.
- Empresas que só existem no Controle Fiscal são contadas, não criadas. Tudo fica no Histórico ("Controle Fiscal").
- `RESPONSAVEIS_PROVEDOR=controle_fiscal` faz dele o provedor de responsáveis do sistema.

## Números vindos do cruzamento Domínio × SEFAZ

O sistema de cruzamento (online, no Manus) já tem as notas da SEFAZ e do Domínio. O Faturamento **só lê** de lá,
por uma rota com chave, os números do mês de cada empresa:

1. No Manus, cadastre o segredo `FATURAMENTO_API_KEY` (texto longo e aleatório) e publique o cruzamento.
2. No `.env` do Faturamento:
   ```
   CRUZAMENTO_URL=https://endereço-do-cruzamento
   CRUZAMENTO_API_KEY=a mesma chave cadastrada no Manus
   ```
3. Reinicie o Faturamento.

Onde usar: **Importar planilha › Importar do cruzamento**, **Lançamento › Buscar no cruzamento** (só a empresa
aberta) e **Painel › Verificar cruzamento**. A prévia mostra, por empresa e tipo, a **versão anterior** (o que veio
na última importação), a **nova versão** (o que está lá agora) e o **atual aqui**; você marca as linhas e importa.
Regras (`faturamento/services/cruzamento.py`):

- Empresas casadas pelo **CNPJ** (empresa sem CNPJ aqui não casa; as que só existem lá não são criadas).
- Vêm NF-e Entradas, NF-e Saídas e NFC-e (autorizadas e canceladas, pela data de emissão). CT-e e NFS-e continuam manuais.
- **Ajuste sugerido** = notas que estão no Domínio e não no relatório da SEFAZ, com o motivo
  "… (cruzamento)" e a lista das notas na observação. Reimportar troca só esse ajuste; os digitados à mão ficam.
- Tipo sem relatório da SEFAZ importado lá para o mês não traz nada (zero lá não vira zero aqui).
- Linha "Bateu" nunca é alterada; se mudou lá depois, a prévia avisa. Carteira de outra pessoa só "como substituto".
- Cada importação é uma **versão** (`fat_fonte_versao`) e aparece em Importar planilha, com **Desfazer**.

## Subir num servidor / na plataforma do escritório

- **Banco**: `DATABASE_URL=postgresql://...` (instale `requirements-servidor.txt`). As migrações rodam sozinhas.
- **Login**: `MODO_AUTH=plataforma` — o usuário vem do cabeçalho `X-Remote-User` (configurável em
  `AUTH_HEADER`), casado pelo nome ou por `external_id` do usuário.
- **Plugado em outra app Flask**: `from faturamento import init_app; init_app(app, url_prefix="/faturamento")`.
- **Serviço separado**: `docker build` com o `Dockerfile` (gunicorn em `wsgi:app`); `docker-compose.yml` sobe
  junto um PostgreSQL de teste.
- **API JSON**: `/api/faturamento/v1` — ver [docs/API.md](docs/API.md).
- Tabelas com prefixo `fat_`; empresas ligáveis ao cadastro central por **CNPJ** ou `external_id`.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
python -m pytest -q
flask --app app db migrate -m "descrição"   # após mudar faturamento/models.py
```

Estrutura: `faturamento/services/` concentra todas as regras; `views/` (telas) e `api/` só chamam os serviços.
