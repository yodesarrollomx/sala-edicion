/* Instrumento de auditoría de la Sala (8-sep-2026, pedido de Alejandro:
   «quiero todo tipo de reacción registrada con métricas: si le picas a esto, en el segundo 1 pasa esto…»).

   Cómo se usa, desde la consola de la Sala abierta con ?vista=editor:
     eval(await (await fetch('docs/auditoria/instrumento.js')).text())
   Después:
     T.marca('nombre del paso')      → reinicia el cronómetro y la traza
     U.clic(el,'nombre')             → clic real (pointer+mouse+click) registrado
     U.teclear(el,'texto')           → teclea carácter por carácter (keydown/input/keyup)
     U.pegar(el,'texto')             → pega de verdad (ClipboardEvent + DataTransfer)
     U.borrar(el,n) · U.enter(el)    → borra n caracteres · salto de renglón
     U.swipe(el,±px)                 → desliza la carta como en el teléfono
     U.est()                         → idx, pasos, lockeadas, capas, candado, bloqueo
     T.saca()                        → la traza con milisegundos
   La red al Sheet queda INTERCEPTADA: el sobre se registra y se responde ok simulado, así que
   la prueba nunca escribe en el Sheet real. Para probar contra el Sheet se usa un día aislado
   con ~/yod_audit/sala_sobre.py. window.__RED_CAIDA=true simula quedarse sin señal. */
(function () {
  window.T = {
    t0: performance.now(), ev: [], on: true, paso: '',
    log(tipo, det) { if (this.on) this.ev.push({ ms: Math.round(performance.now() - this.t0), tipo, det }); },
    marca(n) { this.t0 = performance.now(); this.ev = []; this.paso = n; this.log('PASO', n); },
    saca() { return this.ev.map(e => e.ms + 'ms ' + e.tipo + (e.det ? ' · ' + e.det : '')); }
  };
  const _f = window.fetch;
  window.fetch = async function (u, o) {
    const url = String(u).slice(0, 60);
    T.log('RED→', url + (o && o.method === 'POST' ? ' POST' : ''));
    if (o && o.method === 'POST' && /script\.google/.test(String(u))) {
      try { const b = JSON.parse(o.body); T.log('SOBRE', JSON.stringify(b.propuestas).slice(0, 300)); window.__ULT_SOBRE = b; } catch (e) {}
      if (window.__RED_CAIDA) { T.log('RED×', 'simulada caída'); throw new Error('red caída simulada'); }
      T.log('RED←', 'ok simulado');
      return new Response(JSON.stringify({ ok: true, guardado: new Date().toISOString() }), { status: 200 });
    }
    const r = await _f.apply(this, arguments); T.log('RED←', url + ' ' + r.status); return r;
  };
  const _set = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) { T.log('LS+', k + ' (' + String(v).length + ' b)'); return _set.apply(this, arguments); };
  const _rem = Storage.prototype.removeItem;
  Storage.prototype.removeItem = function (k) { T.log('LS−', k); return _rem.apply(this, arguments); };
  new MutationObserver(m => {
    const z = m.filter(x => x.target.closest && x.target.closest('#zona')).length;
    const c = m.filter(x => x.addedNodes[0] && x.addedNodes[0].className && /velo|zoom|tour/.test(String(x.addedNodes[0].className))).length;
    if (z) T.log('DOM', 'zona ×' + z); if (c) T.log('DOM', 'capa ×' + c);
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
  const tit = document.querySelector('#titulo');
  if (tit) new MutationObserver(() => T.log('DOM', 'título: ' + tit.innerText.slice(0, 24))).observe(tit, { childList: true, subtree: true, characterData: true });
  const est = document.querySelector('#estado');
  if (est) new MutationObserver(() => T.log('DOM', 'píldora: ' + est.innerText.slice(0, 30))).observe(est, { childList: true, subtree: true, characterData: true });
  window.U = {
    clic(el, nom) {
      if (!el) { T.log('CLIC×', nom + ' NO EXISTE'); return false; }
      T.log('CLIC', nom);
      ['pointerdown', 'mousedown', 'pointerup', 'mouseup'].forEach(t =>
        el.dispatchEvent(new (t.startsWith('pointer') ? PointerEvent : MouseEvent)(t, { bubbles: true, clientX: 10, clientY: 10 })));
      el.click(); return true;
    },
    teclear(el, txt) {
      el.focus();
      for (const ch of txt) {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true }));
        el.setRangeText(ch, el.selectionStart, el.selectionEnd, 'end');
        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: ch, inputType: 'insertText' }));
        el.dispatchEvent(new KeyboardEvent('keyup', { key: ch, bubbles: true }));
      }
      T.log('TECLEA', JSON.stringify(txt.slice(0, 30)) + ' → largo ' + el.value.length);
    },
    pegar(el, txt) {
      el.focus(); const dt = new DataTransfer(); dt.setData('text/plain', txt);
      const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
      if (el.dispatchEvent(ev)) { el.setRangeText(txt, el.selectionStart, el.selectionEnd, 'end'); el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertFromPaste' })); }
      T.log('PEGA', JSON.stringify(txt.slice(0, 30)) + ' → largo ' + el.value.length);
    },
    borrar(el, n) {
      el.focus();
      for (let i = 0; i < n; i++) {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }));
        const p = el.selectionStart;
        if (p > 0) { el.setRangeText('', p - 1, p, 'end'); el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward' })); }
      }
      T.log('BORRA', n + ' → largo ' + el.value.length);
    },
    enter(el) {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      el.setRangeText('\n', el.selectionStart, el.selectionEnd, 'end');
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertLineBreak' }));
      T.log('ENTER', 'renglones: ' + el.value.split('\n').length);
    },
    swipe(el, dx) {
      const y = 200;
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: 200, clientY: y }));
      for (let i = 1; i <= 6; i++) el.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: 200 + dx * i / 6, clientY: y }));
      el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, clientX: 200 + dx, clientY: y }));
      T.log('SWIPE', dx + 'px');
    },
    est() {
      return `idx=${idx} pasos=${pasos.length} lock=${lockeadas.length} capas=[${CAPAS.map(c => c.id)}] cand=${_decidiendo} blq=${document.body.classList.contains('bloqueado')}`;
    }
  };
  return 'instrumento listo';
})();
