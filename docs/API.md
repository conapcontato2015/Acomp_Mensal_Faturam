# API JSON — `/api/faturamento/v1`

`GET /api/faturamento/v1/` lista as rotas disponíveis. Competência sempre `AAAA-MM`; valores monetários
como texto decimal (`"395464.73"`). Erros: `{"erro": "<codigo>", "mensagens": [...]}` com 400 (parâmetro
inválido), 401 (usuário não identificado), 403 `somente_leitura` (carteira de outra pessoa), 404, 422 (regra violada).

Identificação: modo local → sessão (`POST /sessao`); modo plataforma → cabeçalho `X-Remote-User`.
Escritas aceitam `"substituto": true` para lançar na carteira de outra pessoa.

| Método | Rota | Descrição |
| --- | --- | --- |
| GET | `/sessao` | Usuário atual e modo de autenticação |
| POST | `/sessao` | `{usuario_id}` — define o usuário (só modo local) |
| GET | `/usuarios` | Usuários ativos |
| GET | `/tipos-documento` | Tipos com `sentido` E/S |
| GET | `/empresas?responsavel=&competencia=&incluir_inativas=&busca=` | Empresas (com responsável e histórico) |
| POST | `/empresas` | `{nome, cnpj, responsavel_id, tipos:[ids]}` |
| GET/PUT | `/empresas/<id>` | Detalhe / `{nome, cnpj, ativa, tipos}` |
| POST | `/empresas/<id>/responsavel` | `{usuario_id, inicio:"AAAA-MM", origem}` — troca a carteira |
| GET | `/lancamentos?empresa=&competencia=` | Linhas do mês com ajustes e totais |
| PUT | `/lancamentos/<empresa>/<AAAA-MM>` | `{linhas:[{tipo_id, qtde_autor, valor_autor, qtde_canc, valor_canc}]}` (tudo ou nada) |
| POST | `/lancamentos/<empresa>/<AAAA-MM>/<tipo>/ajustes` | `{grupo: AUTOR\|CANC, qtde, valor, motivo, observacao}` |
| DELETE | `/ajustes/<id>` | Remove ajuste (fica no histórico) |
| PUT | `/lancamentos/<id>/bateu` | `{bateu: true\|false}` |
| PUT | `/conferencia/<empresa>/<AAAA-MM>` | `{bateu}` — marca/desmarca todas as linhas da empresa |
| PUT | `/fechamentos/<empresa>/<AAAA-MM>` | `{status: sem_movimento\|pendente}` |
| GET | `/painel?competencia=&responsavel=` | Status do mês por empresa, alertas de variação |
| GET | `/resumo?competencia=&responsavel=&sentido=&situacao=` | Cartões de conferência, subtotais por sentido, progresso |
| GET | `/evolucao?empresa=&ate=&meses=` | Série mensal entradas/saídas e parte de ajuste |
| GET | `/auditoria?empresa=&usuario=` | Histórico de alterações |
