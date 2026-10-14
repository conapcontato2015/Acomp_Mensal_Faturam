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

  // Confetes de parabéns (empresa com tudo "bateu"). Curto, sem biblioteca, respeita "reduzir movimento".
  const CORES_CONFETE = ['#ED6325', '#202F5A', '#F6B08F', '#9DA9C9', '#F2C14E'];
  function confete(origem) {
    try {
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      if (!document.body.animate) return;
      const r = origem && origem.getBoundingClientRect ? origem.getBoundingClientRect() : null;
      const x0 = r ? r.left + r.width / 2 : window.innerWidth / 2;
      const y0 = r ? r.top + r.height / 2 : window.innerHeight / 3;
      const caixa = document.createElement('div');
      caixa.setAttribute('aria-hidden', 'true');
      caixa.style.cssText = 'position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:9999';
      document.body.appendChild(caixa);
      const n = 44;
      for (let i = 0; i < n; i++) {
        const p = document.createElement('i');
        const w = 6 + Math.random() * 6;
        p.style.cssText = 'position:absolute;display:block;left:' + x0 + 'px;top:' + y0 + 'px;width:' + w + 'px;height:' + (w * 0.5) +
          'px;border-radius:2px;background:' + CORES_CONFETE[i % CORES_CONFETE.length];
        caixa.appendChild(p);
        const ang = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 0.9;  // para cima, em leque
        const vel = 120 + Math.random() * 220;
        const dx = Math.cos(ang) * vel, dy = Math.sin(ang) * vel;
        const queda = 220 + Math.random() * 180;
        const giro = (Math.random() - 0.5) * 900;
        p.animate([
          { transform: 'translate(0,0) rotate(0deg)', opacity: 1, offset: 0 },
          { transform: 'translate(' + dx * 0.6 + 'px,' + dy * 0.6 + 'px) rotate(' + giro * 0.5 + 'deg)', opacity: 1, offset: 0.35 },
          { transform: 'translate(' + dx + 'px,' + (dy + queda) + 'px) rotate(' + giro + 'deg)', opacity: 0, offset: 1 },
        ], { duration: 900 + Math.random() * 500, easing: 'cubic-bezier(.2,.7,.4,1)', fill: 'forwards' });
      }
      setTimeout(() => caixa.remove(), 1600);
    } catch (e) { /* enfeite: nunca atrapalha o trabalho */ }
  }

  window.FAT = { api, aviso, parseNum, parseInteiro, moeda, inteiro, confete };

  // Formulários de filtro que navegam ao trocar um select
  document.querySelectorAll('form[data-navegar]').forEach(form => {
    form.querySelectorAll('select').forEach(s => s.addEventListener('change', () => form.submit()));
  });
})();
