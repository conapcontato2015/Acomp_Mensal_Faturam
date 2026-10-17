# CLAUDE.md — instruções para o Claude neste repositório

Sistema de Acompanhamento Mensal de Faturamento da CONAP, no formato do Conap Ferramentas: API FastAPI +
SQLAlchemy (`faturamento/`), telas Next.js (`web/`), e `servidor.py` para rodar sozinho no PC. Visão geral, uso e
estrutura estão no [README.md](README.md); a API em [docs/API.md](docs/API.md).

## Fluxo de trabalho com git (definido pelo dono do repositório)

O Claude trabalha **sempre na branch `claude/trabalho`** e publica **direto no `main`**, sem pedir
aprovação nem abrir pull request. A mesma branch é reaproveitada em todos os pedidos.

A cada alteração pedida:

1. **Começar da versão mais recente do `main`** (recicla a branch, descartando o estado anterior dela):
   ```bash
   git fetch origin
   git checkout -B claude/trabalho origin/main
   ```
2. Fazer a alteração.
3. **Testar** — só publica com tudo verde:
   ```bash
   python -m pytest -q
   ```
   Se mudou `faturamento/models.py`, gerar a migração (`python -m faturamento.migracoes revision -m "..."`) e conferir
   com `python -m faturamento.migracoes check`. Se a migração nova cria tabela, acrescentar
   `(revisão, tabela)` em `MARCOS_MIGRACOES` (`faturamento/bootstrap.py`) — é o que reconhece bancos antigos sem registro de versão.
   Se mudou algo em `web/`: `cd web && npm run check && npm run build` e **commitar `web/out`** junto (o PC do
   usuário não tem Node; o `servidor.py` serve as telas já compiladas). Nunca commitar `web/node_modules` nem `web/.next`.
4. **Commitar** na `claude/trabalho` com mensagem em português, curta, dizendo o que mudou e por quê.
5. **Levar para o `main` e publicar** (fast-forward, sem merge commit):
   ```bash
   git checkout main
   git merge --ff-only claude/trabalho
   git push origin main
   git push -f origin claude/trabalho
   git checkout claude/trabalho
   ```
   Se o `merge --ff-only` falhar (o `main` andou), voltar à branch, `git rebase origin/main`, testar de novo
   e repetir o passo 5.

Regras:
- Nunca publicar com testes falhando; se não for possível corrigir, parar e avisar o usuário.
- Nunca reescrever o histórico do `main` (sem `push -f` no `main`). O `push -f` é só na `claude/trabalho`.
- Nunca commitar dados de clientes (planilhas reais, bancos `.db`, pasta `dados/`) nem o arquivo `.env`.
- Ao terminar, dizer ao usuário em uma ou duas frases o que mudou e que já está no `main`.

## Convenções do código

- Toda regra de negócio fica em `faturamento/services/` (sem framework web); a API (`faturamento/http/rotas/`)
  só chama os serviços; as telas (`web/`) só chamam a API (`web/lib/api.ts`).
- API em `/api/faturamento/*` com JSON em **camelCase**; Python em snake_case. A conversão fica só em
  `faturamento/http/json.py` (rotas devolvem dicts snake_case; entradas herdam de `Entrada`). Documentar rota nova em `docs/API.md`.
- Integração atual com o cruzamento Domínio × SEFAZ é a versão do **Manus, em camelCase**
  (`faturamento/services/cruzamento.py`) — não mudar esse contrato sem combinar.
- Telas em `web/app/ferramentas/faturamento/` (rota `/ferramentas/faturamento/`, igual à da plataforma),
  componentes em `web/components/`. Nada de topo/login próprio fora de `Topo.tsx`/`Sessao.tsx` (na plataforma somem).
- Interface, mensagens e comentários em português do Brasil; valores monetários em `Decimal`, nunca float
  (na API, texto decimal).
- Entradas e saídas nunca se somam; subtotais só dentro do mesmo sentido.
- Escrita na API só em JSON (ou upload com `X-Requested-With`) — é a proteção CSRF; não criar rota que aceite formulário.
- Identidade visual do Conap Ferramentas: tokens em `web/app/globals.css` (`--brand` #ff6a00, `--ink`, `--line`…),
  fontes Space Grotesk / Inter / JetBrains Mono, classes `card`, `btn`, `chip`, `badge`, `tabela`.
- Cada correção ou funcionalidade nova vem com teste em `tests/`.
