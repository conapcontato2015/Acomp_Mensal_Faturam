/* Conferência: pesquisar e escolher quais empresas exibir (ex.: matriz e filial juntas). */
(function () {
  const form = document.querySelector('[data-sel-empresas]');
  if (!form) return;
  const busca = form.querySelector('[data-busca]');
  const painel = form.querySelector('[data-painel]');
  const opcoes = Array.from(form.querySelectorAll('.opcao'));
  const semResultado = form.querySelector('[data-sem-resultado]');

  const normalizar = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  function abrir() { painel.hidden = false; busca.setAttribute('aria-expanded', 'true'); }
  function fechar() { painel.hidden = true; busca.setAttribute('aria-expanded', 'false'); }

  function filtrar() {
    const termos = normalizar(busca.value).split(/\s+/).filter(Boolean);
    let visiveis = 0;
    opcoes.forEach(op => {
      const nome = normalizar(op.dataset.nome);
      const ok = termos.every(t => nome.includes(t));
      op.hidden = !ok;
      if (ok) visiveis++;
    });
    semResultado.hidden = visiveis > 0;
  }

  busca.addEventListener('focus', abrir);
  busca.addEventListener('input', () => { abrir(); filtrar(); });
  busca.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') { fechar(); busca.blur(); }
    if (ev.key === 'Enter') {
      ev.preventDefault();
      // Enter sem nada marcado: marca as encontradas e exibe
      if (!opcoes.some(op => op.querySelector('input').checked)) {
        opcoes.filter(op => !op.hidden).forEach(op => { op.querySelector('input').checked = true; });
      }
      form.submit();
    }
  });
  form.querySelector('[data-marcar-visiveis]').addEventListener('click', () => {
    opcoes.filter(op => !op.hidden).forEach(op => { op.querySelector('input').checked = true; });
  });
  form.querySelector('[data-limpar]').addEventListener('click', () => {
    opcoes.forEach(op => { op.querySelector('input').checked = false; });
  });
  document.addEventListener('click', ev => { if (!form.contains(ev.target)) fechar(); });
})();
