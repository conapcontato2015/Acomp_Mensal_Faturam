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
    else if (/^[-+]?[1-9]\d*\.\d{3}$/.test(t)) t = t.replace('.', '');  // "6.370" é milhar; "0.125" é decimal
    const n = Number(t);
    if (isNaN(n)) return NaN;
    if (Math.abs(n) >= 1e13) return NaN;  // mais de 13 dígitos inteiros: grande demais
    return n;
  }

  // Quantidade: só inteiro (pontos apenas como milhar, ex.: "1.234"). Devolve null, número, NaN ou
  // 'fracao' quando é um número válido porém com casas decimais ("1.5", "1,5", "12.34").
  function parseInteiro(texto) {
    if (texto === null || texto === undefined) return null;
    let t = String(texto).trim().replace(/\s/g, '');
    if (t === '') return null;
    if (/^[-+]?\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, '');
    if (/^[-+]?\d+$/.test(t)) {
      const n = Number(t);
      return Math.abs(n) > 2147483647 ? NaN : n;
    }
    return Number.isNaN(parseNum(t)) ? NaN : 'fracao';
  }

  const moeda = v => (v === null || v === undefined || isNaN(v)) ? '—'
    : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const inteiro = v => (v === null || v === undefined || isNaN(v)) ? '—' : Number(v).toLocaleString('pt-BR');

  window.FAT = { api, aviso, parseNum, parseInteiro, moeda, inteiro };

  // Formulários de filtro que navegam ao trocar um select
  document.querySelectorAll('form[data-navegar]').forEach(form => {
    form.querySelectorAll('select').forEach(s => s.addEventListener('change', () => form.submit()));
  });
})();
