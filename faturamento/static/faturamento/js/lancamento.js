/* Tela de lançamento: totais ao vivo, validação na célula, salvar, ajustes e "bateu". */
(function () {
  const form = document.getElementById('form-lanc');
  if (!form) return;
  const { api, aviso, parseNum, parseInteiro, moeda, inteiro } = window.FAT;
  const empresa = form.dataset.empresa;
  const comp = form.dataset.comp;
  const chkSub = document.getElementById('substituto');
  const ajustes = JSON.parse(document.getElementById('dados-ajustes').textContent || '{}');
  const linhas = Array.from(form.querySelectorAll('tr.linha'));

  // Valores iniciais de cada linha: o "Bateu" fica bloqueado enquanto a linha tiver edição não salva.
  const CAMPOS = ['qtde_autor', 'valor_autor', 'qtde_canc', 'valor_canc'];
  const iniciais = new Map(linhas.map(tr => [tr, CAMPOS.map(n => parseNum(tr.querySelector(`[name="${n}"]`).value))]));
  const mesmoNumero = (a, b) => (Number.isNaN(a) || Number.isNaN(b)) ? false : a === b;
  function linhaAlterada(tr) {
    const ini = iniciais.get(tr) || [];
    return CAMPOS.some((n, i) => !mesmoNumero(parseNum(tr.querySelector(`[name="${n}"]`).value), ini[i]));
  }
  const DICA_SALVAR = 'Salve as alterações antes de marcar';
  function travarBateu(tr) {
    const chk = tr.querySelector('.chk-bateu');
    const suja = linhaAlterada(tr);
    chk.disabled = !editavel() || !tr.dataset.lancId || suja;
    if (suja) chk.title = DICA_SALVAR; else chk.removeAttribute('title');
  }

  const substituto = () => !!(chkSub && chkSub.checked);
  const editavel = () => form.dataset.editavel === '1' || substituto();

  function soma(lista, grupo, campo) {
    return lista.filter(a => a.grupo === grupo).reduce((s, a) => s + Number(a[campo] || 0), 0);
  }

  function aplicarTrava() {
    linhas.forEach(tr => {
      const travada = tr.dataset.bateu === '1';
      tr.querySelectorAll('input.celula').forEach(i => { i.readOnly = !editavel() || travada; });
      tr.querySelectorAll('.btn-ajuste').forEach(b => { b.dataset.travado = (!editavel() || travada) ? '1' : '0'; });
      travarBateu(tr);
    });
    document.querySelectorAll('#btn-salvar, #btn-sem-mov').forEach(b => { b.disabled = !editavel(); });
  }

  function validarLinha(tr) {
    const v = n => parseNum(tr.querySelector(`[name="${n}"]`).value);
    const q = n => parseInteiro(tr.querySelector(`[name="${n}"]`).value);
    const iqa = q('qtde_autor'), iqc = q('qtde_canc');
    const qa = iqa === 'fracao' ? NaN : iqa, va = v('valor_autor'), qc = iqc === 'fracao' ? NaN : iqc, vc = v('valor_canc');
    const nome = tr.dataset.tipo;
    let erro = '';
    if (iqa === 'fracao' || iqc === 'fracao') erro = 'Quantidade deve ser número inteiro';
    else if ([qa, va, qc, vc].some(x => Number.isNaN(x))) erro = 'Só números são aceitos. Para uma diferença, use o botão de ajuste.';
    else if ([qa, va, qc, vc].some(x => x !== null && x < 0)) erro = 'Números do relatório não podem ser negativos (use um ajuste negativo).';
    else if ((qa === null) !== (va === null)) erro = nome + ' autorizadas: informe quantidade e valor juntos (valor sem quantidade some do resumo).';
    else if ((qc === null) !== (vc === null)) erro = nome + ' canceladas: informe quantidade e valor juntos.';
    const msg = tr.nextElementSibling;
    msg.hidden = !erro;
    msg.querySelector('td').textContent = erro ? '⚠ ' + erro : '';
    tr.classList.toggle('erro', !!erro);
    let aviso2 = '';
    if (!erro && qc !== null && qa !== null && qc > qa) aviso2 = 'Atenção: mais canceladas que autorizadas (pode ser nota do mês anterior).';
    if (aviso2) { msg.hidden = false; msg.querySelector('td').textContent = 'ℹ ' + aviso2; }
    return { ok: !erro, qa, va, qc, vc };
  }

  function recalcular() {
    let ent = 0, sai = 0, canc = 0, ok = 0, comMov = 0;
    linhas.forEach(tr => {
      const r = validarLinha(tr);
      travarBateu(tr);
      const aj = ajustes[tr.dataset.tipoId] || [];
      const tqa = (r.qa || 0) + soma(aj, 'AUTOR', 'qtde');
      const tva = (r.va || 0) + soma(aj, 'AUTOR', 'valor');
      const tqc = (r.qc || 0) + soma(aj, 'CANC', 'qtde');
      const tvc = (r.vc || 0) + soma(aj, 'CANC', 'valor');
      const temA = r.qa !== null || aj.some(a => a.grupo === 'AUTOR');
      const temC = r.qc !== null || aj.some(a => a.grupo === 'CANC');
      tr.querySelector('[data-total="autor"]').textContent = temA ? inteiro(tqa) + ' · ' + moeda(tva) : '—';
      tr.querySelector('[data-total="canc"]').textContent = temC ? inteiro(tqc) + ' · ' + moeda(tvc) : '—';
      if (tr.dataset.sentido === 'E') ent += tva || 0; else sai += tva || 0;
      canc += tvc || 0;
      if (temA || temC) { comMov++; if (tr.dataset.bateu === '1') ok++; }
      ['AUTOR', 'CANC'].forEach(g => {
        const b = tr.querySelector(`.btn-ajuste[data-grupo="${g}"]`);
        const lista = aj.filter(a => a.grupo === g);
        if (lista.length) {
          const q = soma(lista, g, 'qtde');
          b.textContent = (q >= 0 ? '+' : '') + inteiro(q) + ' · ' + moeda(soma(lista, g, 'valor'));
          b.classList.add('tem');
        } else {
          b.textContent = 'Ajustar';
          b.classList.remove('tem');
        }
      });
    });
    document.getElementById('t-ent').textContent = moeda(ent);
    document.getElementById('t-sai').textContent = moeda(sai);
    document.getElementById('t-canc').textContent = moeda(canc);
    const tOk = document.getElementById('t-ok');
    tOk.textContent = ok + ' de ' + comMov;
    tOk.style.color = comMov && ok === comMov ? 'var(--marinho)' : 'var(--laranja-escuro)';
  }

  form.addEventListener('input', recalcular);
  // Enter avança para a próxima célula, como no Excel
  form.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && ev.target.classList.contains('celula')) {
      ev.preventDefault();
      const todas = Array.from(form.querySelectorAll('input.celula:not([readonly])'));
      const i = todas.indexOf(ev.target);
      if (todas[i + 1]) todas[i + 1].focus(); else document.getElementById('btn-salvar').focus();
    }
  });
  // Colar um bloco copiado do Excel (linhas x colunas) a partir da célula atual
  form.addEventListener('paste', ev => {
    const alvo = ev.target;
    if (!alvo.classList || !alvo.classList.contains('celula')) return;
    const texto = (ev.clipboardData || window.clipboardData).getData('text');
    if (!texto || (!texto.includes('\t') && !texto.includes('\n'))) return;
    ev.preventDefault();
    const grade = texto.replace(/\r/g, '').split('\n').filter(l => l.length).map(l => l.split('\t'));
    const trInicial = alvo.closest('tr');
    const cols = Array.from(trInicial.querySelectorAll('input.celula'));
    const c0 = cols.indexOf(alvo);
    let tr = trInicial;
    grade.forEach(lin => {
      if (!tr) return;
      const cels = Array.from(tr.querySelectorAll('input.celula'));
      lin.forEach((val, j) => { const c = cels[c0 + j]; if (c && !c.readOnly) c.value = val.trim(); });
      tr = tr.nextElementSibling && tr.nextElementSibling.nextElementSibling;
      while (tr && !tr.classList.contains('linha')) tr = tr.nextElementSibling;
    });
    recalcular();
  });

  if (chkSub) chkSub.addEventListener('change', aplicarTrava);

  document.getElementById('btn-salvar').addEventListener('click', async () => {
    const dados = linhas.map(tr => ({ tr, r: validarLinha(tr) }));
    if (dados.some(d => !d.r.ok)) { aviso('Corrija as linhas destacadas antes de salvar.', 'erro'); return; }
    const corpo = {
      substituto: substituto(),
      linhas: linhas.map(tr => {
        const val = n => tr.querySelector(`[name="${n}"]`).value;
        return { tipo_id: Number(tr.dataset.tipoId), qtde_autor: val('qtde_autor'), valor_autor: val('valor_autor'),
                 qtde_canc: val('qtde_canc'), valor_canc: val('valor_canc') };
      }),
    };
    try {
      const r = await api(`/lancamentos/${empresa}/${comp}`, 'PUT', corpo);
      aviso(r.alterados ? `Salvo: ${r.alterados} linha(s) alterada(s).` + (r.avisos.length ? ' ' + r.avisos.join(' ') : '') : 'Nada mudou.');
      setTimeout(() => location.reload(), 700);
    } catch (e) { aviso(e.message, 'erro'); }
  });

  const btnSemMov = document.getElementById('btn-sem-mov');
  if (btnSemMov) btnSemMov.addEventListener('click', async () => {
    try {
      await api(`/fechamentos/${empresa}/${comp}`, 'PUT', { status: btnSemMov.dataset.valor, substituto: substituto() });
      location.reload();
    } catch (e) { aviso(e.message, 'erro'); }
  });

  form.querySelectorAll('.chk-bateu').forEach(chk => chk.addEventListener('change', async () => {
    const tr = chk.closest('tr');
    try {
      await api(`/lancamentos/${tr.dataset.lancId}/bateu`, 'PUT', { bateu: chk.checked, substituto: substituto() });
      tr.dataset.bateu = chk.checked ? '1' : '0';
      aplicarTrava(); recalcular();
      aviso(chk.checked ? `${tr.dataset.tipo}: bateu.` : `${tr.dataset.tipo}: voltou para "a conferir".`);
    } catch (e) { chk.checked = !chk.checked; aviso(e.message, 'erro'); }
  }));

  // ---------------------------------------------------------------- ajustes
  const dlg = document.getElementById('dlg-ajuste');
  const fAj = document.getElementById('form-ajuste');
  let atual = null;

  function desenharLista() {
    const cont = document.getElementById('lista-ajustes');
    cont.innerHTML = '';
    const lista = (ajustes[atual.tipoId] || []).filter(a => a.grupo === atual.grupo);
    if (!lista.length) { cont.innerHTML = '<span class="muted small">Nenhum ajuste nesta linha.</span>'; return; }
    lista.forEach(a => {
      const div = document.createElement('div');
      div.className = 'item';
      const info = document.createElement('div');
      info.innerHTML = '<strong class="num"></strong><div class="muted small"></div>';
      info.querySelector('strong').textContent = `${a.qtde >= 0 ? '+' : ''}${inteiro(a.qtde)} docs · R$ ${moeda(Number(a.valor))}`;
      info.querySelector('div').textContent = `${a.motivo}${a.observacao ? ' — ' + a.observacao : ''} · ${a.por} em ${a.em}`;
      div.appendChild(info);
      if (!atual.travado) {
        const rm = document.createElement('button');
        rm.type = 'button'; rm.className = 'link-btn'; rm.textContent = 'Remover';
        rm.addEventListener('click', async () => {
          if (!window.confirm('Remover este ajuste? A remoção fica no histórico.')) return;
          try {
            await api(`/ajustes/${a.id}?substituto=${substituto() ? 1 : 0}`, 'DELETE');
            ajustes[atual.tipoId] = (ajustes[atual.tipoId] || []).filter(x => x.id !== a.id);
            desenharLista(); recalcular(); aviso('Ajuste removido.');
          } catch (e) { aviso(e.message, 'erro'); }
        });
        div.appendChild(rm);
      }
      cont.appendChild(div);
    });
  }

  form.querySelectorAll('.btn-ajuste').forEach(b => b.addEventListener('click', () => {
    const tr = b.closest('tr');
    atual = { tipoId: tr.dataset.tipoId, grupo: b.dataset.grupo, travado: b.dataset.travado === '1', tipo: tr.dataset.tipo };
    document.getElementById('dlg-titulo').textContent = `Ajuste · ${atual.tipo} · ${atual.grupo === 'AUTOR' ? 'Autorizadas' : 'Canceladas'}`;
    fAj.reset();
    fAj.querySelectorAll('input, select, textarea, #btn-salvar-ajuste').forEach(el => { el.disabled = atual.travado; });
    desenharLista();
    dlg.showModal();
  }));

  fAj.addEventListener('submit', async ev => {
    if (ev.submitter && ev.submitter.value !== 'salvar') return;
    ev.preventDefault();
    const fd = new FormData(fAj);
    try {
      const r = await api(`/lancamentos/${empresa}/${comp}/${atual.tipoId}/ajustes`, 'POST', {
        grupo: atual.grupo, qtde: fd.get('qtde'), valor: fd.get('valor'), motivo: fd.get('motivo'),
        observacao: fd.get('observacao'), substituto: substituto(),
      });
      const a = r.ajuste;
      (ajustes[atual.tipoId] = ajustes[atual.tipoId] || []).push({
        id: a.id, grupo: a.grupo, qtde: a.qtde, valor: a.valor, motivo: a.motivo, observacao: a.observacao || '',
        por: a.criado_por ? a.criado_por.nome : '', em: new Date().toLocaleDateString('pt-BR'),
      });
      const tr = form.querySelector(`tr.linha[data-tipo-id="${atual.tipoId}"]`);
      if (r.lancamento && r.lancamento.id) tr.dataset.lancId = r.lancamento.id;
      fAj.reset(); desenharLista(); recalcular(); aplicarTrava();
      aviso('Ajuste salvo.');
    } catch (e) { aviso(e.message, 'erro'); }
  });

  aplicarTrava();
  recalcular();
})();
