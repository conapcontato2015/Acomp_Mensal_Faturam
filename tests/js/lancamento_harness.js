// Executa app.js e lancamento.js num DOM mínimo (sem dependências) e imprime JSON com os resultados.
// Uso: node lancamento_harness.js <dir_js>
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dir = process.argv[2];

function el(extra = {}) {
  const handlers = {};
  const classes = new Set();
  const attrs = {};
  return Object.assign({
    dataset: {}, style: {}, value: '', textContent: '', hidden: false, disabled: false, readOnly: false,
    checked: false,
    classList: { add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
                 toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)) },
    addEventListener: (ev, fn) => { (handlers[ev] = handlers[ev] || []).push(fn); },
    disparar: (ev, obj) => (handlers[ev] || []).forEach(fn => fn(obj || { target: null })),
    setAttribute: (k, v) => { attrs[k] = String(v); }, removeAttribute: k => { delete attrs[k]; },
    getAttribute: k => attrs[k], querySelector: () => null, querySelectorAll: () => [],
  }, extra);
}

const inputs = {};
['qtde_autor', 'valor_autor', 'qtde_canc', 'valor_canc'].forEach(n => {
  inputs[n] = el({ name: n });
  inputs[n].classList.add('celula');
});
inputs.qtde_autor.value = '10';
inputs.valor_autor.value = '1.234,56';
const chk = el();
Object.defineProperty(chk, 'title', { get() { return this.getAttribute('title') || ''; }, set(v) { this.setAttribute('title', v); } });
const td = el();
const msg = el({ querySelector: () => td });
const btns = { AUTOR: el(), CANC: el() };
const totais = { autor: el(), canc: el() };
const tr = el({
  dataset: { tipoId: '1', tipo: 'NF-e Entradas', sentido: 'E', lancId: '5', bateu: '0' },
  nextElementSibling: msg,
  querySelector: sel => {
    let m = sel.match(/^\[name="(.+)"\]$/);
    if (m) return inputs[m[1]];
    if (sel === '.chk-bateu') return chk;
    m = sel.match(/data-total="(\w+)"/);
    if (m) return totais[m[1]];
    m = sel.match(/data-grupo="(\w+)"/);
    if (m) return btns[m[1]];
    return null;
  },
  querySelectorAll: sel => (sel === 'input.celula' ? Object.values(inputs) : []),
});
const form = el({
  dataset: { empresa: '1', comp: '2026-08', editavel: '1' },
  querySelectorAll: sel => (sel === 'tr.linha' ? [tr] : sel === '.chk-bateu' ? [chk] : []),
});
const ids = {
  'form-lanc': form, 'dados-ajustes': el({ textContent: '{}' }), 'btn-salvar': el(), 'dlg-ajuste': el(),
  'form-ajuste': el(), 't-ent': el(), 't-sai': el(), 't-canc': el(), 't-ok': el(), toast: el(),
};
const document = {
  body: { dataset: { api: '/api/faturamento/v1/' } },
  getElementById: id => ids[id] || null,
  querySelectorAll: sel => (sel.includes('#btn-salvar') ? [ids['btn-salvar']] : []),
};
const window = {};
const ctx = vm.createContext({ window, document, console, fetch: () => Promise.reject(new Error('sem rede')),
                               setTimeout, clearTimeout, location: { reload() {} } });
vm.runInContext(fs.readFileSync(path.join(dir, 'app.js'), 'utf8'), ctx);
vm.runInContext(fs.readFileSync(path.join(dir, 'lancamento.js'), 'utf8'), ctx);

const out = {};
const estado = () => ({ disabled: chk.disabled, title: chk.title, erro: msg.hidden ? '' : td.textContent });
out.inicial = estado();
inputs.valor_autor.value = '1.300,00';
form.disparar('input');
out.editado = estado();
inputs.valor_autor.value = '1234,56';   // mesmo número, outra grafia
form.disparar('input');
out.revertido = estado();
inputs.qtde_autor.value = '1.5';
form.disparar('input');
out.fracao = estado();
inputs.qtde_autor.value = '1.500';
form.disparar('input');
out.milhar = estado();
const P = window.FAT.parseNum, I = window.FAT.parseInteiro;
out.parseNum = { '0.125': P('0.125'), '6.370': P('6.370'), '01.250': P('01.250'), grande: P('99999999999999') };
out.parseInteiro = { '1.5': I('1.5'), '1,5': I('1,5'), '12.34': I('12.34'), '1.234': I('1.234'), abc: I('abc'), vazio: I('') };
console.log(JSON.stringify(out, (k, v) => (typeof v === 'number' && Number.isNaN(v) ? 'NaN' : v)));
