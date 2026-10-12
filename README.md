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
