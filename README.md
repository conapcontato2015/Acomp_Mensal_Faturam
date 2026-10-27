# Acompanhamento Mensal de Faturamento · CONAP

Substitui a planilha **FATURAMENTO_V2**. Cada pessoa (Hellen, Jaísa, Mariana, Natan) lança, por empresa e
competência, a quantidade e o valor dos documentos fiscais do relatório da SEFAZ (CT-e, NF-e, NFC-e,
NFS-e, entradas e saídas). Na conferência, marca **Bateu** em cada linha que confere com o sistema contábil.

Já segue o formato das ferramentas do **Conap Ferramentas** (backend Python/FastAPI, telas em Next.js,
PostgreSQL, login por JWT da plataforma) e continua rodando sozinho no seu computador.

## Usar no seu computador (Windows)

1. Instale o Python 3.11 ou superior (python.org; marque **Add python.exe to PATH**).
2. Baixe este repositório (botão *Code › Download ZIP*) e descompacte numa pasta, ex.: `C:\Faturamento`.
3. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele prepara tudo (1–2 minutos) e abre o navegador
   em `http://localhost:5000/ferramentas/faturamento/`. Depois de um `git pull`, o `iniciar.bat` instala sozinho
   o que tiver de novo.
4. Escolha seu nome na tela **Quem está usando?**.
5. Os dados antigos (planilhas) não são importados pela tela: a carga inicial é feita fora do sistema. O menu
   **Importações** traz o cruzamento Domínio × SEFAZ e o histórico, com **Desfazer**.

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
| Empresas | CNPJ, tipos usados, ativa; **responsável editável por qualquer usuário**, com histórico e origem (manual, planilha, integração) |
| Importações | Cruzamento Domínio × SEFAZ (com prévia e "desfazer") e histórico das importações. Não há importação de XLSX |
| Histórico | Quem mudou o quê e quando |

Regras principais: quantidade e valor sempre juntos; sem contas digitadas nos campos (diferença = ajuste
com motivo); linha que bateu fica travada; carteiras das colegas são só leitura (com opção "lançar como
substituto"); entradas e saídas nunca se somam.

## Responsáveis vindos de outro sistema

Hoje a carteira é editada à mão ou trazida do Controle Fiscal. O encaixe do sistema externo está pronto em `faturamento/responsaveis.py`
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

Onde usar: **Importações › Importar do cruzamento**, **Lançamento › Buscar no cruzamento** (só a empresa
aberta) e **Painel › Verificar cruzamento**. A prévia mostra, por empresa e tipo, a **versão anterior** (o que veio
na última importação), a **nova versão** (o que está lá agora) e o **atual aqui**; você marca as linhas e importa.
Regras (`faturamento/services/cruzamento.py`):

- Empresas casadas pelo **CNPJ** (empresa sem CNPJ aqui não casa; as que só existem lá não são criadas).
- Vêm NF-e Entradas, NF-e Saídas e NFC-e (autorizadas e canceladas, pela data de emissão). CT-e e NFS-e continuam manuais.
- **Ajuste sugerido** = notas que estão no Domínio e não no relatório da SEFAZ, com o motivo
  "… (cruzamento)" e a lista das notas na observação. Reimportar troca só esse ajuste; os digitados à mão ficam.
- Tipo sem relatório da SEFAZ importado lá para o mês não traz nada (zero lá não vira zero aqui).
- Linha "Bateu" nunca é alterada; se mudou lá depois, a prévia avisa. Carteira de outra pessoa só "como substituto".
- Cada importação é uma **versão** (`fat_fonte_versao`) e aparece em Importações, com **Desfazer**.

## No Conap Ferramentas

O sistema já está no formato das ferramentas da plataforma:

| Parte | Aqui | Na plataforma |
| --- | --- | --- |
| Backend | FastAPI, `faturamento.http.router` em `/api/faturamento/*` ([docs/API.md](docs/API.md)) | `app.include_router(router)` no backend dela |
| Telas | Next.js em `web/`, rota `/ferramentas/faturamento/` | as páginas de `web/app/ferramentas/faturamento/` entram no front dela; `NEXT_PUBLIC_DENTRO_DA_PLATAFORMA=1` esconde o topo próprio |
| Banco | SQLite (PC) ou PostgreSQL (`DATABASE_URL`); tabelas `fat_*` | PostgreSQL da plataforma |
| Login | "Quem está usando?" (`MODO_AUTH=local`) | JWT da plataforma: `MODO_AUTH=plataforma` + `JWT_SEGREDO` ou `JWT_CHAVE_PUBLICA`, `JWT_COOKIE`, `JWT_CAMPO_ID`, `JWT_CAMPO_NOME` |
| Empresas | Cadastro próprio (`EMPRESAS_FONTE=local`) | Cadastro geral (`EMPRESAS_FONTE=plataforma` + `PLATAFORMA_DATABASE_URL`, `PLATAFORMA_EMPRESAS_TABELA`, `PLATAFORMA_EMPRESAS_COLUNAS`), só leitura; tela **Empresas › Cadastro do Conap Ferramentas** liga as empresas pelo CNPJ |

Permissões: por enquanto todos têm acesso total (carteira de outra pessoa é só leitura, com "substituto").
A API sai em **camelCase** (como o resto da plataforma); o código Python segue em snake_case — a troca está
num ponto só (`faturamento/http/json.py`).

## Subir num servidor

- **Banco**: `DATABASE_URL=postgresql://...` (instale `requirements-servidor.txt`). As migrações rodam sozinhas ao subir.
- **Serviço**: `uvicorn servidor:criar_app --factory --host 0.0.0.0 --port 8000`, ou `docker build` com o
  `Dockerfile`; `docker-compose.yml` sobe junto um PostgreSQL de teste.
- **API JSON**: `/api/faturamento` — ver [docs/API.md](docs/API.md).
- Tabelas com prefixo `fat_`; empresas ligáveis ao cadastro central por **CNPJ** ou `external_id`.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m faturamento.migracoes revision -m "descrição"   # após mudar faturamento/models.py

cd web && npm ci            # telas (Node 20+)
npm run dev                 # http://localhost:3000/ferramentas/faturamento/ (API em 127.0.0.1:5000: rode python servidor.py)
npm run check && npm run build   # gera web/out, que vai no repositório (o PC não precisa de Node)
```

Estrutura: `faturamento/services/` concentra todas as regras; `faturamento/http/` (API) só chama os serviços;
`web/` são as telas; `servidor.py` junta API + telas para rodar sozinho.
