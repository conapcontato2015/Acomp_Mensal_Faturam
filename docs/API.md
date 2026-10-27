# API JSON — `/api/faturamento`

FastAPI, no padrão das ferramentas do Conap Ferramentas. As telas (Next.js, em `/ferramentas/faturamento/`)
usam só esta API. Código: `faturamento/http/` (rotas em `faturamento/http/rotas/`); regras de negócio em
`faturamento/services/`.

## Convenções

- **JSON em camelCase** (`qtdeAutor`, `inicioPadrao`). O código Python continua em snake_case; a conversão é
  feita num ponto só (`faturamento/http/json.py`: `para_json` na saída, `Entrada` com `alias_generator=to_camel`
  na entrada — a entrada também aceita snake_case).
- Competência sempre `AAAA-MM`. Na resposta vem como `{valor, curta, extenso, rotulo}` (`"2026-08"`, `"08/2026"`,
  `"Agosto de 2026"`, `"Ago/26"`).
- Dinheiro como **texto decimal** (`"395464.73"`), nunca número de ponto flutuante. Datas/horas em ISO
  (hora de Fortaleza, sem fuso).
- Na entrada, números podem vir como digitados (`"1.234,56"`) ou já números.
- Erros: `{"erro": "<código>", "mensagens": [...]}` com 400 `parametro_invalido`, 401 `usuario_nao_identificado`,
  403 `somente_leitura` (carteira de outra pessoa), 404 `nao_encontrado`, 422 (regra violada).
- **CSRF**: escrita (POST/PUT/DELETE) só com `Content-Type: application/json`, ou upload/sem corpo com o
  cabeçalho `X-Requested-With`. Formulário de outro site é recusado.
- Escritas de lançamento aceitam `"substituto": true` para lançar na carteira de outra pessoa.

## Quem está usando

| `MODO_AUTH` | Como o usuário é identificado |
| --- | --- |
| `local` (PC) | Tela "Quem está usando?" → `POST /sessao` grava o cookie assinado `fat_usuario` |
| `plataforma` | **JWT do login do Conap Ferramentas** (cookie `JWT_COOKIE` ou `Authorization: Bearer`), validado com `JWT_SEGREDO` (HS*) ou `JWT_CHAVE_PUBLICA` (RS*/ES*). O usuário é ligado por `external_id` (claim `JWT_CAMPO_ID`, padrão `sub`), depois pelo nome (`JWT_CAMPO_NOME`); se não existir é criado (`JWT_CRIAR_USUARIO`). Sem chave de JWT: cabeçalho `AUTH_HEADER` posto por um proxy |

Todas as rotas exigem usuário, exceto `GET /saude` e `GET /sessao`.

## Rotas

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/saude` | `{status, banco}` |
| GET | `/sessao` | Usuário atual, modo de autenticação, usuários, versão e recursos ligados (`cruzamento`, `controleFiscal`, `empresasFonte`, `provedorResponsaveis`) |
| POST / DELETE | `/sessao` | `{usuarioId}` — entra (só modo local) / sai |
| GET | `/referencias?competencia=` | Competências do seletor, usuários, tipos, motivos de ajuste, sentidos, status |
| GET | `/painel?competencia=&carteira=&status=` | Status do mês por empresa, progresso, contagem, alertas de variação |
| GET | `/lancamento/inicio?competencia=` | Minha carteira (com status) e as outras empresas |
| GET | `/lancamento?empresa=&competencia=` | Linhas do mês (com ajustes e totais), status, permissão, próxima empresa, evolução e alturas do gráfico |
| PUT | `/lancamento/{empresa}/{AAAA-MM}` | `{linhas:[{tipoId, qtdeAutor, valorAutor, qtdeCanc, valorCanc}], substituto}` — tudo ou nada |
| POST | `/lancamento/{empresa}/{AAAA-MM}/{tipo}/ajustes` | `{grupo: AUTOR\|CANC, qtde, valor, motivo, observacao, substituto}` |
| DELETE | `/ajustes/{id}?substituto=` | Remove o ajuste (fica no histórico) |
| PUT | `/lancamentos/{id}/bateu` | `{bateu, substituto}` — devolve quantas linhas da empresa bateram |
| PUT | `/conferencia/{empresa}/{AAAA-MM}/bateu` | `{bateu}` — todas as linhas da empresa |
| PUT | `/fechamento/{empresa}/{AAAA-MM}` | `{status: sem_movimento\|pendente, substituto}` |
| GET | `/conferencia?competencia=&carteira=&vista=todas\|pendencia&empresa=1&empresa=4` | Cartões por empresa (blocos por sentido, subtotais), progresso, opções de empresas |
| GET | `/conferencia/excel?…` | Planilha `.xlsx` da conferência |
| GET / POST | `/empresas` | Lista (`carteira`, `busca`, `inativas`) / cria `{nome, cnpj, ativa, tipos, responsavelId}` |
| GET / PUT | `/empresas/{id}` | Detalhe com histórico / altera `{nome, cnpj, ativa, tipos, responsavelId, inicio}` |
| POST | `/empresas/{id}/responsavel` | `{usuarioId, inicio}` — troca a carteira a partir de `inicio` (origem `manual`) |
| POST | `/empresas/plataforma/sincronizar` | `{aplicar, criarNovas, responsavelId}` — prévia/aplicação do cadastro de empresas do Conap Ferramentas |
| GET / POST / PUT | `/tipos-documento[/{id}]` | Tipos (`?todos=true` com uso) / cria `{nome, sentido}` / altera `{nome, sentido, ordem, ativo, modelo}` |
| GET | `/importacoes` | Importações feitas (cruzamento e as antigas de planilha, já registradas) |
| POST | `/importacoes/{id}/desfazer` | Desfaz uma importação |
| GET / POST | `/controle-fiscal` | Configurado? · `{inicio, aplicar}` prévia/aplicação |
| GET | `/cruzamento?competencia=` | Configurado? e competências |
| GET | `/cruzamento/previa?competencia=&carteira=&empresa=` | Versão anterior × nova × atual por empresa e tipo, com `token` |
| POST | `/cruzamento/aplicar` · `/cruzamento/descartar` | `{token, linhas:[chaves], substituto}` · `{token}` |
| GET | `/historico?empresa=&usuario=&pagina=` | Alterações (50 por página) com as mudanças já formatadas |

## Plugar no backend da plataforma

```python
from faturamento.config import configurar
from faturamento.http import router

configurar(MinhaConfig)          # DATABASE_URL, MODO_AUTH=plataforma, JWT_*, EMPRESAS_FONTE=plataforma…
app.include_router(router)       # /api/faturamento/*
```

O router traz o próprio tratamento de erros, a sessão de banco por requisição e a proteção CSRF.
