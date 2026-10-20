/* Sala 2.0 · capa de interfaz (20-oct-2026, Claude · Buzón CL-SALA2-EN-LINEA-20261020).
   Misma Sala: usa el mismo motor de turno (pasos, idx, decidir, pedirNota, pintarCartas),
   el mismo guardado (cola + Apps Script) y las mismas llaves. Sólo cambia la interfaz:
   - entra directo a decidir, una pieza a la vez (láminas y cortes de video en la misma fila);
   - video vertical grande, sin cajas encima;
   - tres botones fijos: Aprobar · Pedir cambio · No va;
   - la nota de un video puede llevar el segundo exacto;
   - navegación: Te toca · Cómo va · Ajustes.
   Vista anterior: ?clasica=1 */
(function(){
  'use strict';
  var qs = new URLSearchParams(location.search);
  if (qs.has('clasica')) return;
  var B = document.body;
  B.classList.add('sala2');

  /* ---------- utilidades ---------- */
  function paso(){ try { return (typeof pasos !== 'undefined' && pasos[idx]) || null; } catch(e){ return null; } }
  function carta(){ return document.querySelector('#zona .carta'); }
  function puedeDecidir(){ try { return typeof DECIDE === 'function' && DECIDE(); } catch(e){ return false; } }
  var tAviso = 0;
  function aviso(txt){
    var el = document.getElementById('s2aviso');
    if (!el){ el = document.createElement('div'); el.id = 's2aviso'; el.setAttribute('role','status'); B.appendChild(el); }
    el.textContent = txt; el.hidden = false;
    clearTimeout(tAviso); tAviso = setTimeout(function(){ el.hidden = true; }, 2600);
  }

  /* ---------- entrar directo a decidir ---------- */
  function aTurno(){
    if (!B.classList.contains('sala-tablero') || !puedeDecidir() || !paso()) return;
    if (B.dataset.vista && B.dataset.vista !== 'hoy') return;
    try { if (typeof cerrarCapas === 'function') cerrarCapas(); } catch(e){}
    B.classList.remove('sala-tablero'); B.classList.add('sala-turno');
    try { if (typeof pintarCartas === 'function') pintarCartas(); } catch(e){}
    pintar();
  }

  /* ---------- navegación ---------- */
  function nav(){
    var n = document.getElementById('puertas'); if (!n || n.dataset.s2) return;
    n.dataset.s2 = '1';
    var b = function(v){ return n.querySelector('[data-v="' + v + '"]'); };
    var poner = function(v, t){ var x = b(v); if (x) { var label = Array.from(x.childNodes).find(function(n){ return n.nodeType === 3 && n.nodeValue.trim(); }); if (label) label.nodeValue = t; } };
    poner('hoy', 'Te toca'); poner('prod', 'Cómo va');
    ['pub', 'arbol'].forEach(function(v){ var x = b(v); if (x) x.classList.add('s2-oculto'); });
    var prod = b('prod'), aj = b('aj');
    if (prod && aj) n.insertBefore(prod, aj);
  }

  /* ---------- tres botones ---------- */
  var dock = document.createElement('div');
  dock.id = 's2dock';
  dock.setAttribute('role', 'group');
  dock.setAttribute('aria-label', 'Decidir esta pieza');
  dock.innerHTML = '<button id="s2ok" type="button"><span aria-hidden="true">✓</span>Aprobar</button>'
                 + '<button id="s2chg" type="button"><span aria-hidden="true">✎</span>Pedir cambio</button>'
                 + '<button id="s2no" type="button"><span aria-hidden="true">✕</span>No va</button>';
  B.appendChild(dock);
  // La navegación nativa ocupa el borde inferior en móvil.
  function ajustarDock(){
    var n = document.getElementById('puertas'), h = 0;
    if (n && getComputedStyle(n).position === 'fixed' && getComputedStyle(n).bottom !== 'auto') h = n.getBoundingClientRect().height;
    dock.style.bottom = h + 'px';
    var v = document.getElementById('vHoy');
    if (v) v.style.paddingBottom = (112 + h) + 'px';
  }
  window.addEventListener('resize', ajustarDock);
  ajustarDock();

  var prefijo = '';            // «NO VA —» cuando se usa No va
  function abrirNota(pref){
    var x = paso(); if (!x || !puedeDecidir() || document.querySelector('.velo, .hoja-velo')) return;
    prefijo = pref || '';
    if (x.tipo === 'lamina'){ if (typeof decidir === 'function') decidir('no'); }
    else { var ning = carta() && carta().querySelector('[data-ning]'); if (ning) ning.click(); }
  }
  function aprobar(){
    var x = paso(); if (!x || !puedeDecidir() || document.querySelector('.velo, .hoja-velo')) return;
    if (x.tipo === 'lamina'){ if (typeof decidir === 'function') decidir('si'); return; }
    var c = carta(), ops = c ? c.querySelectorAll('[data-op]') : [];
    if (ops.length === 1){ ops[0].click(); return; }
    if (ops.length > 1){
      aviso('Esta pieza tiene ' + ops.length + ' opciones: toca la que apruebas.');
      var o = c.querySelector('.opciones'); if (o) o.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  document.getElementById('s2ok').onclick = aprobar;
  document.getElementById('s2chg').onclick = function(){ abrirNota(''); };
  document.getElementById('s2no').onclick = function(){ abrirNota('NO VA —'); };

  /* ---------- hoja de nota: prefijo y segundo del video ---------- */
  function prepararNota(){
    var ta = document.getElementById('notaT'); if (!ta || ta.dataset.s2) return;
    ta.dataset.s2 = '1';
    var x = paso(), esVideo = !!(x && x.p && typeof VIDEO_REVISION !== 'undefined' && VIDEO_REVISION.resolver(x.p.video));
    var titulo = ta.parentElement && ta.parentElement.querySelector('h3');
    if (prefijo){
      if (titulo) titulo.textContent = '¿Por qué no va?';
      ta.value = prefijo + ' ' + ta.value; ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
    }
    if (esVideo){
      var s = document.createElement('label');
      s.id = 's2seg';
      s.innerHTML = 'Segundo del video (opcional) <input id="s2segIn" inputmode="numeric" placeholder="0:12" maxlength="6">';
      ta.parentElement.insertBefore(s, ta);
      var ok = document.getElementById('notaOk');
      if (ok) ok.addEventListener('click', ponerSegundo, true);
    }
    prefijo = '';
  }
  function ponerSegundo(){
    var inp = document.getElementById('s2segIn'), ta = document.getElementById('notaT');
    if (!inp || !ta || ta.dataset.s2seg) return;
    var v = inp.value.trim(); if (!v) return;
    if (/^\d+$/.test(v)) v = Math.floor(v / 60) + ':' + String(v % 60).padStart(2, '0');
    if (!/^\d{1,2}:[0-5]\d$/.test(v)) return;
    ta.value = '[' + v + '] ' + ta.value; ta.dataset.s2seg = '1';
  }

  /* ---------- pintar estado ---------- */
  function marcarCarta(){
    var c = carta(); if (!c) return;
    var ops = c.querySelectorAll('[data-op]');
    if (c.classList.contains('s2-una') !== (ops.length === 1)) c.classList.toggle('s2-una', ops.length === 1);
    if (!document.getElementById('s2clasica')){
      var a = document.createElement('a');
      a.id = 's2clasica'; var url = new URL(location.href); url.searchParams.set('clasica','1'); a.href = url.href; a.textContent = 'Ver la Sala anterior';
      var z = document.getElementById('zona'); if (z && z.parentElement) z.parentElement.appendChild(a);
    }
  }
  function pintar(){
    nav();
    var enHoy = (!B.dataset.vista || B.dataset.vista === 'hoy') && B.classList.contains('sala-turno');
    var x = paso();
    var hay = enHoy && !!x && !!carta() && puedeDecidir() && !document.querySelector('.velo, .hoja-velo');
    if (B.classList.contains('s2-dock') !== hay) B.classList.toggle('s2-dock', hay);
    if (hay){
      marcarCarta();
      var c = carta(), ops = c ? c.querySelectorAll('[data-op]').length : 0;
      document.getElementById('s2ok').disabled = (x.tipo !== 'lamina' && ops === 0);
    }
  }

  /* ---------- observar la Sala ---------- */
  new MutationObserver(function(){
    if (B.classList.contains('sala-tablero')) aTurno();
    pintar();
  }).observe(B, { attributes: true, attributeFilter: ['class', 'data-vista'] });
  new MutationObserver(function(){ aTurno(); prepararNota(); pintar(); }).observe(B, { childList: true, subtree: true });

  /* teclas: A aprobar · C pedir cambio · X no va (sólo en turno y sin hoja abierta) */
  document.addEventListener('keydown', function(e){
    if (!B.classList.contains('s2-dock') || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest && e.target.closest('textarea,input,select')) return;
    var k = (e.key || '').toLowerCase();
    if (k === 'a'){ e.preventDefault(); aprobar(); }
    else if (k === 'c'){ e.preventDefault(); abrirNota(''); }
    else if (k === 'x'){ e.preventDefault(); abrirNota('NO VA —'); }
  }, true);

  var volver = document.querySelector('.bt-return'); if (volver) volver.hidden = true;
  nav(); aTurno(); pintar();
})();
