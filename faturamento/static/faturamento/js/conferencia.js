/* Conferência: marcar "Bateu" por linha ou por empresa, sem recarregar a página. */
(function () {
  const raiz = document.querySelector('[data-conferencia]');
  if (!raiz) return;
  const comp = raiz.dataset.competencia;
  const resumo = document.getElementById('conf-resumo');

  // --- estado de um cartão (lido do DOM: a área simples tem um selo por linha)
  function estado(card) {
    const selos = card.querySelectorAll('.simples-area .selo');
    let n = 0;
    selos.forEach(s => { if (s.getAttribute('aria-pressed') === 'true') n++; });
    return { total: selos.length, bateram: n, tudo: selos.length > 0 && n === selos.length };
  }

  function aplicarLinha(card, id, on) {
    card.querySelectorAll('.selo[data-lanc="' + id + '"]').forEach(b => {
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.setAttribute('aria-label', b.dataset.tipo + (on ? ': bateu (clique para desmarcar)' : ': a conferir (clique quando bater)'));
    });
    card.querySelectorAll('[data-linha="' + id + '"]').forEach(r => r.classList.toggle('batida', on));
  }

  function pintarCartao(card) {
    const e = estado(card);
    const falta = e.total - e.bateram;
    const v = card.querySelector('[data-veredito]');
    v.className = 'veredito ' + (e.tudo ? 'ok' : 'falta');
    v.textContent = e.tudo ? '✓ Tudo bateu' : (falta === 1 ? 'Falta 1' : 'Faltam ' + falta);
    card.classList.toggle('pendente', !e.tudo);
    card.querySelector('[data-acao="marcar"]').textContent = e.tudo ? 'Desmarcar todas' : 'Marcar todas';
    return e;
  }

  // --- contadores do topo: ajustados pela diferença antes/depois
  function atualizarResumo(antes, depois) {
    if (!resumo) return;
    const d = resumo.dataset;
    d.bateram = Number(d.bateram) + (depois.bateram - antes.bateram);
    if (antes.tudo !== depois.tudo) {
      d.ok = Number(d.ok) + (depois.tudo ? 1 : -1);
      d.pendentes = Number(d.pendentes) + (depois.tudo ? -1 : 1);
    }
    const linhas = Number(d.linhas);
    const pct = linhas ? Math.round(Number(d.bateram) / linhas * 100) : 0;
    resumo.querySelector('[data-k="bateram"]').textContent = FAT.inteiro(Number(d.bateram));
    resumo.querySelector('[data-k="ok"]').textContent = FAT.inteiro(Number(d.ok));
    resumo.querySelector('[data-k="pendentes"]').textContent = FAT.inteiro(Number(d.pendentes));
    const barra = resumo.querySelector('[data-k="barra"]');
    barra.setAttribute('aria-valuenow', pct);
    barra.firstElementChild.style.width = pct + '%';
  }

  // Aplica uma mudança local, chama a API e desfaz se der erro.
  async function mudar(card, mudancas, chamada) {
    if (card.dataset.ocupado) return;
    card.dataset.ocupado = '1';
    const antes = estado(card);
    const anteriores = mudancas.map(([id]) => [id, card.querySelector('.selo[data-lanc="' + id + '"]').getAttribute('aria-pressed') === 'true']);
    mudancas.forEach(([id, on]) => aplicarLinha(card, id, on));
    atualizarResumo(antes, pintarCartao(card));
    try {
      await chamada();
      if (!antes.tudo && estado(card).tudo && FAT.confete) FAT.confete(card.querySelector('.veredito') || card);
    } catch (err) {
      const meio = estado(card);
      anteriores.forEach(([id, on]) => aplicarLinha(card, id, on));
      atualizarResumo(meio, pintarCartao(card));
      FAT.aviso(err.message || 'Não foi possível salvar a conferência.', 'erro');
    } finally {
      delete card.dataset.ocupado;
    }
  }

  raiz.addEventListener('click', ev => {
    const alvo = ev.target.closest('button');
    if (!alvo || alvo.disabled) return;
    const card = alvo.closest('.emp');
    if (!card) return;

    if (alvo.classList.contains('selo')) {
      const id = alvo.dataset.lanc;
      const novo = alvo.getAttribute('aria-pressed') !== 'true';
      mudar(card, [[id, novo]], () => FAT.api('/lancamentos/' + id + '/bateu', 'PUT', { bateu: novo }));
      return;
    }

    if (alvo.dataset.acao === 'marcar') {
      const novo = !estado(card).tudo;
      const ids = Array.from(card.querySelectorAll('.simples-area .selo')).map(s => s.dataset.lanc);
      mudar(card, ids.map(id => [id, novo]),
        () => FAT.api('/conferencia/' + card.dataset.empresa + '/' + comp, 'PUT', { bateu: novo }));
      return;
    }

    if (alvo.dataset.acao === 'detalhes') {
      const det = card.classList.toggle('detalhado');
      alvo.querySelector('[data-rotulo]').textContent = det ? 'Ocultar detalhes' : 'Ver detalhes';
      alvo.querySelector('[data-longo]').hidden = det;
      alvo.setAttribute('aria-expanded', det ? 'true' : 'false');
    }
  });
})();
