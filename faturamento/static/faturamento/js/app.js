/* Utilidades comuns: chamada à API, avisos e formatação brasileira. Sem dependências. */
(function () {
  const base = document.body.dataset.api.replace(/\/$/, '');

  async function api(caminho, metodo = 'GET', corpo) {
    const resp = await fetch(base + caminho, {
      method: metodo,
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      credentials: 'same-origin',
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
    let dados = null;
    try { dados = await resp.json(); } catch (e) { /* sem corpo */ }
    if (!resp.ok) {
      const msgs = (dados && dados.mensagens) || [(dados && dados.mensagem) || 'Erro ao salvar (' + resp.status + ').'];
      const erro = new Error(msgs.join(' '));
      erro.mensagens = msgs;
      erro.status = resp.status;
      throw erro;
    }
    return dados;
  }

  let timer = null;
  function aviso(texto, tipo) {
    const el = document.getElementById('toast');
    el.textContent = texto;
    el.className = 'toast' + (tipo === 'erro' ? ' erro' : '');
    el.hidden = false;
    clearTimeout(timer);
    timer = setTimeout(() => { el.hidden = true; }, tipo === 'erro' ? 7000 : 3500);
  }

  function parseNum(texto) {
    if (texto === null || texto === undefined) return null;
    let t = String(texto).trim().replace(/R\$|\s/g, '');
    if (t === '') return null;
    if (!/^[-+]?[\d.,]+$/.test(t)) return NaN;
    if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
    else if ((t.match(/\./g) || []).length > 1) t = t.replace(/\./g, '');
    else if (/^[-+]?\d+\.\d{3}$/.test(t)) t = t.replace('.', '');
    const n = Number(t);
    return isNaN(n) ? NaN : n;
  }

  const moeda = v => (v === null || v === undefined || isNaN(v)) ? '—'
    : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const inteiro = v => (v === null || v === undefined || isNaN(v)) ? '—' : Number(v).toLocaleString('pt-BR');

  window.FAT = { api, aviso, parseNum, moeda, inteiro };

  // Formulários de filtro que navegam ao trocar um select
  document.querySelectorAll('form[data-navegar]').forEach(form => {
    form.querySelectorAll('select').forEach(s => s.addEventListener('change', () => form.submit()));
  });
})();
