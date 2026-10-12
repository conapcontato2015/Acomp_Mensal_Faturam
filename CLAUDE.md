# CLAUDE.md — instruções para o Claude neste repositório

Sistema de Acompanhamento Mensal de Faturamento da CONAP (Flask + SQLAlchemy). Visão geral, uso e
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
   Se mudou `faturamento/models.py`, gerar a migração (`flask --app app db migrate -m "..."`) e conferir
   com `flask --app app db check`.
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

- Toda regra de negócio fica em `faturamento/services/`; telas (`views/`) e API (`api/`) só chamam os serviços.
- Interface, mensagens e comentários em português do Brasil; valores monetários em `Decimal`, nunca float.
- Entradas e saídas nunca se somam; subtotais só dentro do mesmo sentido.
- Formulários HTML com POST levam `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- Identidade visual: laranja `#ED6325`, azul-marinho `#202F5A` (variáveis em `static/faturamento/css/app.css`).
- Cada correção ou funcionalidade nova vem com teste em `tests/`.
