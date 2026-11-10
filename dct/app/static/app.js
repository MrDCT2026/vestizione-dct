"use strict";
const S = { gruppo: false, stato: null, anno: null, mese: null, nn: null, sett_anno: null, sel: [], tasti: null };
const $ = (s, r = document) => r.querySelector(s);
const el = (t, a = {}, ...f) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v); } for (const x of f.flat()) if (x != null) e.append(x.nodeType ? x : document.createTextNode(x)); return e; };
const MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
const dmy = iso => iso.split("-").reverse().join("/");
/* "gg/mm/aaaa" (anche con - o .) -> "aaaa-mm-gg", oppure null se non è una data valida */
function leggiData(t) {
  const m = /^\s*(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{4})\s*$/.exec(t || ""); if (!m) return null;
  const g = +m[1], me = +m[2], a = +m[3], d = new Date(Date.UTC(a, me - 1, g));
  if (d.getUTCFullYear() !== a || d.getUTCMonth() !== me - 1 || d.getUTCDate() !== g) return null;
  return a + "-" + String(me).padStart(2, "0") + "-" + String(g).padStart(2, "0");
}

async function api(url, corpo) {
  const opz = corpo === undefined ? {} : { method: "POST", body: corpo instanceof Blob ? corpo : JSON.stringify(corpo) };
  const r = await fetch(url, opz);
  const j = await r.json();
  if (!r.ok) throw new Error(j.errore || "Errore");
  return j;
}
function messaggio(t, tipo) {
  S.msg = [t, tipo];
  const m = $("#messaggio"); m.textContent = t || ""; m.className = tipo || "";
  const a = $("#avviso"); if (a) { a.textContent = t || ""; a.className = "avviso " + (tipo || ""); a.hidden = !t; }
}
function dialogo(titolo, testo, opzioni) {
  return new Promise(ris => {
    const v = $("#dialogo"); v.innerHTML = ""; v.hidden = false;
    const chiudi = x => { v.hidden = true; ris(x); };
    const azioni = el("div", { class: "azioni" });
    let scelte = null;
    if (opzioni.scelte) scelte = el("div", { class: "scelte" }, opzioni.scelte.map(s => el("button", { onclick: () => chiudi(s) }, s)));
    let ta = null;
    if (opzioni.testo !== undefined) ta = el("textarea", {}, opzioni.testo);
    if (opzioni.ok) azioni.append(el("button", { class: "primario", onclick: () => chiudi(ta ? ta.value : true) }, opzioni.ok));
    azioni.prepend(el("button", { onclick: () => chiudi(null) }, opzioni.annulla || "Annulla"));
    v.append(el("div", { class: "dlg", role: "dialog", "aria-modal": "true" }, el("h2", {}, titolo), el("p", {}, testo || ""), scelte, ta, azioni));
    if (ta) ta.focus();
  });
}
/* finestra con campi: campi = [{id, label, tipo: "text"|"date"|"select"|"number", valore, opzioni}] */
function modulo(titolo, testo, campi, ok) {
  return new Promise(ris => {
    const v = $("#dialogo"); v.innerHTML = ""; v.hidden = false;
    const chiudi = x => { v.hidden = true; ris(x); };
    const ctrl = {};
    const righe = campi.map(c => {
      let i;
      if (c.tipo === "date") i = el("input", { type: "text", inputmode: "numeric", placeholder: "gg/mm/aaaa", maxlength: 10, value: c.valore ? dmy(c.valore) : "", style: "width:100%" });
      else if (c.tipo === "select") i = el("select", {}, (c.opzioni || []).map(o => el("option", { value: o, selected: o === c.valore }, o)));
      else i = el("input", { type: c.tipo === "number" ? "number" : c.tipo, value: c.valore ?? "", min: c.tipo === "number" ? 1 : null, style: "width:100%" });
      ctrl[c.id] = i;
      return el("label", { style: "display:block;margin-bottom:10px" }, el("div", { class: "piccolo", style: "margin-bottom:3px" }, c.label), i);
    });
    const invia = () => {
      const o = {};
      for (const c of campi) {
        let x = ctrl[c.id].value;
        if (c.tipo === "date") { x = leggiData(x); if (!x) { ctrl[c.id].style.borderColor = "#B42318"; ctrl[c.id].focus(); return; } }
        o[c.id] = x;
      }
      chiudi(o);
    };
    v.append(el("div", { class: "dlg", role: "dialog", "aria-modal": "true" }, el("h2", {}, titolo), el("p", {}, testo || ""), righe,
      el("div", { class: "azioni" }, el("button", { onclick: () => chiudi(null) }, "Annulla"), el("button", { class: "primario", onclick: invia }, ok || "Conferma"))));
    const primo = Object.values(ctrl)[0]; if (primo) primo.focus();
  });
}
function segnaStato() {
  const s = S.stato;
  $("#stato-salvataggio").textContent = s && s.aperto ? "Anno " + (S.anno || "") + (s.salvato ? " · salvato alle " + s.salvato : "") : "";
  const b = $("#annulla-modifica");
  if (b) {
    b.hidden = !(s && s.annulla);
    if (s && s.annulla) b.title = "Annulla: " + s.annulla.descr + " (" + s.annulla.ora + ")";
  }
}
async function annullaModifica() {
  const a = S.stato && S.stato.annulla;
  if (!a) return;
  if (!await dialogo("Annulla l'ultima modifica", "Si torna a com'era prima di: " + a.descr + " (" + a.ora + "). Si può ripetere per tornare ancora più indietro.", { ok: "Annulla la modifica", annulla: "Lascia com'è" })) return;
  try { const r = await api("/api/annulla", {}); S.anno = S.anno || null; await aggiornaStato(); messaggio("Annullato: " + r.annullato + ".", "ok"); await vistaCorrente(true); }
  catch (e) { messaggio(e.message, "err"); }
}
async function aggiornaStato() {
  S.stato = await api("/api/stato");
  if (S.stato.aperto && !S.anno) {
    const oggi = new Date(S.stato.oggi);
    const ms = S.stato.mesi;
    let m = ms.find(x => x[0] === oggi.getFullYear() && x[1] === oggi.getMonth() + 1) || ms[0];
    S.anno = m[0]; S.mese = m[1];
  }
  segnaStato();
}

/* ---------------- Home ---------------- */
async function vistaHome(v) {
  v.append(el("h1", {}, "Home"));
  const s = S.stato;
  if (!s.aperto) {
    const f = el("input", { type: "file", accept: ".xlsm,.xlsx", id: "file" });
    v.append(el("div", { class: "scheda", style: "margin-top:14px;max-width:640px" },
      el("h2", {}, "Primo avvio"),
      el("p", {}, "Scegli il file VESTIZIONE_DCT (.xlsm): il programma ne legge persone, orari, rotazione, assenze e note, e li tiene in un archivio suo. Il file originale non viene modificato."),
      f, " ",
      el("button", { class: "primario", onclick: async () => {
        if (!f.files[0]) { messaggio("Scegli prima il file.", "err"); return; }
        messaggio("Importazione in corso…");
        try { await api("/api/importa", f.files[0]); S.anno = null; await aggiornaStato(); messaggio("Importazione completata.", "ok"); vai("anno"); }
        catch (e) { messaggio(e.message, "err"); }
      } }, "Importa")));
    return;
  }
  const anni = el("div", { class: "griglia2", style: "margin-top:14px" });
  for (const a of s.anni) {
    anni.append(el("div", { class: "scheda" }, el("h2", {}, "Anno " + a),
      el("div", { class: "riga" },
        el("button", { onclick: () => { S.anno = a; S.mese = s.mesi.find(m => m[0] === a)[1]; vai("anno"); } }, "Apri"),
        el("a", { class: "bottone", href: "/api/esporta/rotazione?anno=" + a }, "Esporta Rotazione_" + a + ".xlsm"))));
  }
  const prossimo = Math.max(...s.anni) + 1;
  anni.append(el("div", { class: "scheda" }, el("h2", {}, "Nuovo anno"),
    el("p", {}, "Crea la rotazione del " + prossimo + " dal calendario e dalle regole. Non sovrascrive anni esistenti."),
    el("button", { onclick: async () => {
      if (!await dialogo("Crea il " + prossimo, "Vuoi creare la rotazione del " + prossimo + "?", { ok: "Crea" })) return;
      try { await api("/api/genera_anno", { anno: prossimo }); await aggiornaStato(); messaggio("Anno " + prossimo + " creato.", "ok"); vistaCorrente(); }
      catch (e) { messaggio(e.message, "err"); }
    } }, "Crea " + prossimo)));
  v.append(anni);
}

/* ---------------- tabella (anno e settimana) ---------------- */
function tabella(dati, interattiva) {
  const t = el("table", { class: "cal" });
  const testa = el("tr", {}, el("th", { class: "pos" }, "Pos"), el("th", { class: "nome" }, "Nome"), el("th", { class: "gr" }, "Gr."));
  dati.giorni.forEach((g, i) => testa.append(el("th", { style: "background:#" + g.fill }, el("div", {}, g.g), el("div", { class: "dow" }, g.dow))));
  if (dati.mancanti !== undefined) testa.append(el("th", {}, "Manc."));
  t.append(el("thead", {}, testa));
  const tb = el("tbody");
  for (const r of dati.righe) {
    const tr = el("tr", {}, el("td", { class: "pos" }, r.pos), el("td", { class: "nome" }, r.nome), el("td", { class: "gr" }, r.gruppo));
    r.celle.forEach((c, i) => {
      const scuro = ["008000", "0070C0", "9966CC", "000000"].includes(c.fill);
      let st = "background:#" + c.fill + ";" + (scuro ? "color:#fff;" : "");
      if (c.diag) { const dc = "#" + (c.dfill || "000000"); st += "background:linear-gradient(to top right,transparent 38%," + dc + " 40%," + dc + " 60%,transparent 62%),#" + c.fill + ";"; }
      const td = el("td", { class: "c" + (c.v === "R" ? " r" : ""), style: st, title: c.nota || null, "data-i": i, "data-p": r.pos }, c.v || "");
      if (c.nota) td.append(el("span", { class: "nt" }));
      tr.append(td);
    });
    if (dati.mancanti !== undefined) tr.append(el("td", {}));
    tb.append(tr);
  }
  const d = el("tr", { class: "dct" }, el("td", { class: "pos" }), el("td", { class: "nome" }, "DCT IN SERVIZIO"), el("td", { class: "gr" }));
  dati.dct.forEach(x => d.append(el("td", { class: x.sotto ? "sotto" : "" }, x.n)));
  if (dati.mancanti !== undefined) d.append(el("td", { class: "tot" }, dati.mancanti || ""));
  tb.append(d);
  t.append(tb);
  if (interattiva) selezione(t, dati);
  return el("div", { class: "tab-sc" + (S.gruppo ? " gruppo" : "") }, t);
}
window.addEventListener("pointerup", () => { if (S.rilascia) S.rilascia(); });
window.addEventListener("pointercancel", () => { if (S.rilascia) S.rilascia(); });
function selezione(t, dati) {
  let ancora = null, premuto = false;
  const cella = e => e.target.closest("td.c");
  const disegna = () => {
    t.querySelectorAll("td.c.sel").forEach(x => x.classList.remove("sel"));
    S.sel.forEach(([i, p]) => { const x = t.querySelector(`td.c[data-i="${i}"][data-p="${p}"]`); if (x) x.classList.add("sel"); });
    aggiornaTasti();
  };
  const rettangolo = (a, b) => {
    const i0 = Math.min(a[0], b[0]), i1 = Math.max(a[0], b[0]), p0 = Math.min(a[1], b[1]), p1 = Math.max(a[1], b[1]);
    const out = []; for (let p = p0; p <= p1; p++) for (let i = i0; i <= i1; i++) out.push([i, p]); return out;
  };
  const pt = c => [+c.dataset.i, +c.dataset.p];
  t.addEventListener("pointerdown", e => { const c = cella(e); if (!c) return; premuto = true;
    if (e.shiftKey && ancora) S.sel = rettangolo(ancora, pt(c)); else if (e.metaKey || e.ctrlKey) { ancora = pt(c); const k = S.sel.findIndex(x => x[0] === ancora[0] && x[1] === ancora[1]); if (k >= 0) S.sel.splice(k, 1); else S.sel.push(ancora); } else { ancora = pt(c); S.sel = [ancora]; }
    disegna(); });
  t.addEventListener("pointermove", e => {
    if (!premuto) return;
    const x = document.elementFromPoint(e.clientX, e.clientY); const c = x && x.closest && x.closest("td.c");
    if (c && ancora && t.contains(c)) { const n = rettangolo(ancora, pt(c)); if (n.length !== S.sel.length || n[n.length - 1][0] !== S.sel[S.sel.length - 1][0] || n[n.length - 1][1] !== S.sel[S.sel.length - 1][1]) { S.sel = n; disegna(); } }
  });
  S.rilascia = () => { premuto = false; };   // un solo ascoltatore sulla finestra (vedi sotto), non uno per tabella
  S.disegna = disegna;
  S.sel = S.sel.filter(([i, p]) => i < dati.giorni.length);
  disegna();
}
const TASTI = [["CONG_FEST", "Cong./Fest.", "FFFF00", "#000"], ["ASS_MAL", "Ass./Mal.", "FFC0C0", "#000"], ["104", "104", "FF9900", "#000"], ["CORSI", "Corsi", "008000", "#fff"], ["SIND", "Sind.", "0070C0", "#fff"]];
function aggiornaTasti() { document.querySelectorAll(".barra-tasti button").forEach(b => { b.disabled = S.sel.length === 0 && b.dataset.serve !== "no"; }); }
function celleSelezionate() { return S.sel.map(([i, p]) => [S.dati.giorni[i].data, p]); }
async function esegui(url, corpo, ricarica) {
  try {
    const e = await api(url, corpo);
    if (e.chiede_cancellazione) return e;
    if (!e.ok) { messaggio(e.msg || "Operazione non eseguita.", "err"); return e; }
    const p = [];
    if (e.colorate) p.push(e.colorate + " colorate");
    if (e.ripristinate) p.push(e.ripristinate + " ripristinate");
    if (e.saltate) p.push(e.saltate + " saltate (" + e.motivi.join("; ") + ")");
    messaggio(p.join(", ") || "Fatto.", e.saltate && !e.colorate && !e.ripristinate ? "err" : "ok");
    await aggiornaStato(); await ricarica(); return e;
  } catch (x) { messaggio(x.message, "err"); }
}
function barraTasti(ricarica) {
  const b = el("div", { class: "barra-tasti" });
  for (const [k, nome, fill, col] of TASTI)
    b.append(el("button", { class: "tasto", style: `background:#${fill};color:${col}`, onclick: () => { if (k !== "ASS_MAL" && k !== "CONG_FEST" && S.sel.length > 1) { messaggio("Questo tasto funziona su una cella alla volta.", "err"); return; } esegui("/api/tasto", { tasto: k, celle: celleSelezionate() }, ricarica); } }, nome));
  b.append(el("button", { class: "tasto", style: "background:#00B0F0", onclick: () => rl(ricarica) }, "RL"));
  b.append(el("button", { class: "tasto", style: "background:#CC99FF", title: "Cambio riposo di servizio", onclick: () => cambioServizio(ricarica) }, "C. Rip. serv."));
  b.append(el("button", { class: "tasto", style: "background:#FF00FF;color:#fff", title: "Cambio riposo personale: due celle dello stesso giorno, un turno e un riposo", onclick: () => cambioPersonale(ricarica) }, "C. Rip. pers."));
  b.append(el("button", { class: "tasto", style: "background:#D9D9D9", onclick: () => cancella(ricarica) }, "Cancella"));
  b.append(el("button", { onclick: () => nota(ricarica) }, "Nota…"));
  const g = el("button", { id: "modo-gruppo", "aria-pressed": S.gruppo ? "true" : "false", style: S.gruppo ? "background:#1F3A5F;color:#fff" : "", onclick: () => { S.gruppo = !S.gruppo; document.querySelector(".tab-sc").classList.toggle("gruppo", S.gruppo); g.setAttribute("aria-pressed", S.gruppo); g.style.cssText = S.gruppo ? "background:#1F3A5F;color:#fff" : ""; g.textContent = S.gruppo ? "Gruppo: attivo" : "Selezione a gruppo"; } }, S.gruppo ? "Gruppo: attivo" : "Selezione a gruppo");
  g.dataset.serve = "no";
  b.append(g);
  return b;
}
function unaCella() { if (S.sel.length !== 1) { messaggio("Seleziona una sola cella.", "err"); return null; } const [i, p] = S.sel[0]; return [S.dati.giorni[i].data, p]; }
async function rl(ric) {
  const c = unaCella(); if (!c) return;
  try {
    const r = await api(`/api/rl_turni?data=${c[0]}&pos=${c[1]}`);
    if (r.tipo === "RL" || r.tipo === "MIS") {
      if (await dialogo("Rientro già presente", "Questa cella ha già un " + r.tipo + ". Vuoi cancellarlo?", { ok: "Cancella" })) await esegui("/api/cancella", { data: c[0], pos: c[1] }, ric);
      return;
    }
    if (!r.riposo) { messaggio("L'RL si applica solo sui riposi (R).", "err"); return; }
    if (!r.turni.length) { messaggio("Nessun turno scoperto in questa data.", "err"); return; }
    const t = await dialogo("RL del " + dmy(c[0]), "Quale turno deve coprire?", { scelte: r.turni });
    if (t) await esegui("/api/rl", { data: c[0], pos: c[1], turno: t }, ric);
  } catch (x) { messaggio(x.message, "err"); }
}
async function cambioServizio(ric) {
  const c = unaCella(); if (!c) return;
  const [i, p] = S.sel[0]; const cel = S.dati.righe[p - 1].celle[i];
  try {
    if (cel.t === "RL" || cel.t === "MIS") {
      if (await dialogo("Rientro già presente", "Questa cella ha già un " + cel.t + ". Vuoi cancellarlo?", { ok: "Cancella" })) await esegui("/api/cancella", { data: c[0], pos: c[1] }, ric);
      return;
    }
    let turno = null;
    if (cel.v === "R" && !cel.t) {
      const r = await api(`/api/rl_turni?data=${c[0]}&pos=${c[1]}`);
      const CORSO = "FOR – solo corso";
      turno = await dialogo("Cambio riposo di servizio del " + dmy(c[0]),
        (r.turni.length ? "Quale turno deve coprire chi rientra?" : "Nessun turno scoperto in questa data.") +
        " Scegli \"" + CORSO + "\" se il collega rientra solo per un corso, senza turno da coprire.", { scelte: [...r.turni, CORSO] });
      if (!turno) return;
      if (turno === CORSO) turno = "FOR";
    } else if (cel.v && cel.v !== "R" && !cel.t) {
      if (!await dialogo("Cambio riposo di servizio", "Il turno " + cel.v + " del " + dmy(c[0]) + " diventa un riposo per esigenze di servizio (RU). Confermi?", { ok: "Conferma" })) return;
    }
    await esegui("/api/cambio_servizio", { data: c[0], pos: c[1], turno }, ric);
  } catch (x) { messaggio(x.message, "err"); }
}
async function cambioPersonale(ric) {
  if (S.sel.length !== 2) { messaggio("Seleziona due celle dello stesso giorno: un turno e un riposo (Cmd/Ctrl+clic, oppure Selezione a gruppo).", "err"); return; }
  const [a, b] = S.sel;
  if (a[0] !== b[0]) { messaggio("Le due celle devono essere dello stesso giorno.", "err"); return; }
  const data = S.dati.giorni[a[0]].data;
  const va = S.dati.righe[a[1] - 1].celle[a[0]].v, vb = S.dati.righe[b[1] - 1].celle[b[0]].v;
  if (!await dialogo("Cambio riposo personale del " + dmy(data), `Scambio tra posizione ${a[1]} (${va || "vuota"}) e posizione ${b[1]} (${vb || "vuota"}). Confermi?`, { ok: "Conferma" })) return;
  await esegui("/api/cambio_personale", { data, pos1: a[1], pos2: b[1] }, ric);
}
async function cancella(ric) {
  const c = unaCella(); if (!c) return;
  const [i, p] = S.sel[0]; const t = S.dati.righe[p - 1].celle[i].t;
  if (["CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND"].includes(t)) { await esegui("/api/tasto", { tasto: t, celle: [c] }, ric); return; }
  await esegui("/api/cancella", { data: c[0], pos: c[1] }, ric);
}
async function nota(ric) {
  const c = unaCella(); if (!c) return;
  const [i, p] = S.sel[0]; const attuale = S.dati.righe[p - 1].celle[i].nota || "";
  const t = await dialogo("Nota del " + dmy(c[0]), "Lascia vuoto per togliere la nota.", { testo: attuale, ok: "Salva" });
  if (t === null) return;
  try { await api("/api/nota", { data: c[0], pos: c[1], testo: t }); messaggio("Nota salvata.", "ok"); await aggiornaStato(); await ric(); } catch (x) { messaggio(x.message, "err"); }
}
function legenda() {
  const L = [["Cong./Fest.", "FFFF00"], ["Ass./Mal.", "FFC0C0"], ["104", "FF9900"], ["Corsi", "008000"], ["Sind.", "0070C0"], ["RL", "00B0F0"], ["Cambio riposo", "FF00FF"], ["MIS", "CC99FF"], ["RU", "9966CC"], ["Sabato", "C6EFCE"], ["Domenica/festivo", "FF6C5D"]];
  return el("div", { class: "legenda" }, L.map(([n, c]) => el("span", {}, el("i", { style: "background:#" + c }), n)));
}

/* ---------------- Anno ---------------- */
async function vistaAnno(v) {
  if (!S.stato.aperto) { v.append(el("div", { class: "vuoto" }, "Importa prima il file dalla Home.")); return; }
  const ms = S.stato.mesi;
  let k = ms.findIndex(m => m[0] === S.anno && m[1] === S.mese); if (k < 0) k = 0;
  const vai_ = d => { const n = k + d; if (n >= 0 && n < ms.length) { S.anno = ms[n][0]; S.mese = ms[n][1]; S.sel = []; vistaCorrente(); } };
  const sel = el("select", { "aria-label": "Mese", onchange: e => { const [a, m] = e.target.value.split("-"); S.anno = +a; S.mese = +m; S.sel = []; vistaCorrente(); } },
    ms.map(m => el("option", { value: m[0] + "-" + m[1], selected: m[0] === S.anno && m[1] === S.mese }, MESI[m[1]] + " " + m[0])));
  v.append(el("div", { class: "riga" }, el("h1", {}, "Anno"),
    el("button", { class: "freccia", "aria-label": "Mese precedente", onclick: () => vai_(-1), disabled: k === 0 }, "‹"), sel,
    el("button", { class: "freccia", "aria-label": "Mese successivo", onclick: () => vai_(1), disabled: k === ms.length - 1 }, "›"),
    el("span", { style: "flex:1" }),
    el("button", { onclick: () => { const c = S.sel.length ? S.dati && S.dati.giorni[S.sel[0][0]].data : null; apriSettimana(c || S.dati.giorni[0].data); } }, "Apri la settimana")));
  try { S.dati = await api(`/api/anno?anno=${S.anno}&mese=${S.mese}`); } catch (e) { v.append(el("div", { class: "vuoto" }, e.message)); return; }
  v.append(tabella(S.dati, true));
  v.append(barraTasti(() => vistaCorrente(true)));
  v.append(el("div", { id: "avviso", class: "avviso", hidden: true, role: "status" }));
  v.append(legenda());
  v.append(el("p", { class: "piccolo" }, "Clic su una cella per selezionarla; trascina o Maiusc+clic per un gruppo di celle; Cmd/Ctrl+clic per aggiungerne. Un secondo clic sullo stesso tasto ripristina."));
}

/* ---------------- Settimana ---------------- */
const MESI_MIN = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
function intervallo(dal, al) {
  const [a1, m1, g1] = dal.split("-").map(Number), [a2, m2, g2] = al.split("-").map(Number);
  if (m1 === m2) return g1 + " – " + g2 + " " + MESI_MIN[m2] + " " + a2;
  return g1 + " " + MESI_MIN[m1] + (a1 !== a2 ? " " + a1 : "") + " – " + g2 + " " + MESI_MIN[m2] + " " + a2;
}
async function apriSettimana(iso) { const r = await api("/api/settimana_di?data=" + iso); S.nn = r.nn; S.sett_anno = r.anno; vai("settimana"); }
function leggiSettimane(t) {
  const m = /^\s*(\d{1,2})\s*(?:[-–]\s*(\d{1,2}))?\s*$/.exec(t || ""); if (!m) return null;
  const da = +m[1], a = m[2] ? +m[2] : da; return da >= 1 && a <= 53 && a >= da && a - da <= 8 ? [da, a] : null;
}
async function vistaSettimana(v) {
  if (!S.stato.aperto) { v.append(el("div", { class: "vuoto" }, "Importa prima il file dalla Home.")); return; }
  if (!S.nn) { const r = await api("/api/settimana_di?data=" + S.stato.oggi); S.nn = r.nn; S.sett_anno = r.anno; }
  let dati;
  try { dati = await api(`/api/settimana?anno=${S.sett_anno}&nn=${S.nn}`); } catch (e) {
    v.append(el("h1", {}, "Settimana"), el("div", { class: "vuoto" }, e.message), el("button", { onclick: () => { S.nn = null; vistaCorrente(); } }, "Torna a oggi")); return; }
  S.dati = dati;
  const cambia = async d => { const dal = new Date(dati.dal); dal.setDate(dal.getDate() + 7 * d); const r = await api("/api/settimana_di?data=" + dal.toISOString().slice(0, 10)); S.nn = r.nn; S.sett_anno = r.anno; vistaCorrente(); };
  v.append(el("div", { class: "riga" }, el("h1", {}, "Settimana " + dati.nn),
    el("button", { class: "freccia", "aria-label": "Settimana precedente", onclick: () => cambia(-1) }, "‹"),
    el("b", { style: "color:var(--grigio)" }, intervallo(dati.dal, dati.al)),
    el("button", { class: "freccia", "aria-label": "Settimana successiva", onclick: () => cambia(1) }, "›"),
    el("span", { style: "flex:1" }),
    el("button", { class: "grande", onclick: async () => { await vistaCorrente(true); messaggio("Servizio della settimana " + dati.nn + " aggiornato.", "ok"); } }, "2 · Servizio Sett."),
    el("a", { class: "bottone grande", style: "background:#D9D9D9", href: `/api/esporta/settimana?anno=${dati.anno}&nn=${dati.nn}` }, "3 · Esporta settimana")));
  // 1 · importa dalla Rotazione
  const nomeFile = el("input", { type: "text", readonly: "", placeholder: "Scegli la Rotazione tornata dai colleghi", value: S.impFile ? S.impFile.name : "", style: "width:100%" });
  const scelta = el("input", { type: "file", accept: ".xlsm,.xlsx", style: "display:none", onchange: e => { S.impFile = e.target.files[0] || null; nomeFile.value = S.impFile ? S.impFile.name : ""; } });
  const sett = el("input", { type: "text", value: S.impSett || String(dati.nn), style: "width:100%", placeholder: "45-47" });
  v.append(el("section", { class: "importa", "aria-label": "Importa dalla Rotazione" },
    el("div", { class: "passo" }, "1 · Importa dalla Rotazione"),
    el("label", { class: "campo", style: "flex:1" }, "File Rotazione", nomeFile),
    el("button", { onclick: () => scelta.click() }, "Sfoglia…"), scelta,
    el("label", { class: "campo", style: "width:170px" }, "Settimane (es. 45-47, max 9)", sett),
    el("button", { class: "primario", onclick: async () => {
      const w = leggiSettimane(sett.value);
      if (!S.impFile) { messaggio("Scegli prima il file della Rotazione.", "err"); return; }
      if (!w) { messaggio("Scrivi le settimane così: 45 oppure 45-47 (al massimo 9).", "err"); return; }
      S.impSett = sett.value; messaggio("Analisi in corso…");
      try {
        const r = await fetch(`/api/import/analizza?anno=${dati.anno}&da=${w[0]}&a=${w[1]}&nome=${encodeURIComponent(S.impFile.name)}`, { method: "POST", body: S.impFile });
        const j = await r.json(); if (!r.ok) throw new Error(j.errore);
        messaggio(""); S.vaiAnteprima = true; vistaCorrente();
      } catch (e) { messaggio(e.message, "err"); }
    } }, "Importa settimana")));
  v.append(el("div", { id: "avviso", class: "avviso", hidden: true, role: "status", style: "margin:0 0 10px" }));
  // giorni + tabella MV
  const g = el("section", { class: "giorni3", "aria-label": "Giorni della settimana" });
  dati.blocchi.forEach((b, i) => {
    const t = el("div", { class: "gcorpo" });
    for (const r of b.righe.filter(x => x.tipo !== "A")) t.append(el("div", { class: "grig" + (r.scoperto ? " sc" : "") }, el("b", {}, r.cod), el("span", {}, r.nome), el("span", { class: "nt" }, r.nota)));
    const ass = b.righe.filter(x => x.tipo === "A");
    if (ass.length) t.append(el("div", { class: "ass" }, ass.map(r => el("div", { class: "grig" }, el("span", {}, r.nome), el("b", { class: "nt" }, r.nota)))));
    const dct = dati.dct[i];
    g.append(el("div", { class: "gio2" }, el("div", { class: "gtesta", style: "background:#" + b.fill }, el("b", {}, b.titolo.replace("  ", " ")), el("span", { class: "dctn" + (dct.sotto ? " sotto" : "") }, "DCT " + dct.n)), t));
  });
  const nb = el("div", { class: "gio2 regole" }, el("div", { class: "gtesta", style: "background:#F2F2F2" }, el("b", {}, "Note della settimana")));
  if (!dati.note.length) nb.append(el("div", { class: "gcorpo piccolo" }, "Nessuna nota in questa settimana. Le note si scrivono nell'Anno, con il tasto Nota…"));
  else nb.append(el("div", { class: "gcorpo" }, dati.note.map(n => el("div", { class: "nota-riga" }, el("b", {}, n.giorno), el("span", { class: "n" }, n.nome), el("span", {}, n.testo)))));
  g.append(nb);
  const mv = tabella(dati, false); mv.classList.add("compatta");
  v.append(el("div", { class: "sett2" }, g, el("aside", { class: "scheda mv" }, el("div", { style: "font-weight:700;color:var(--blu);margin-bottom:6px" }, "Tabella MV"), mv)));
  const imp = await api("/api/import/anteprima");
  v.append(pannelloAnteprima(imp));
  if (S.vaiAnteprima && imp.anteprima) { S.vaiAnteprima = false; setTimeout(() => { const x = $("#pannello-anteprima"); if (x) x.scrollIntoView({ behavior: "smooth", block: "start" }); }, 50); }
  v.append(el("p", { class: "piccolo", style: "margin-top:10px" }, "Settimana " + dati.nn + " generata alle " + dati.generata + " · " + (dati.scoperti ? dati.scoperti + (dati.scoperti === 1 ? " turno scoperto da assegnare" : " turni scoperti da assegnare") : "nessun turno scoperto")));
}

/* ---------------- Personale ---------------- */
async function azionePers(az, corpo, ok) {
  try { await api("/api/personale/" + az, corpo); await aggiornaStato(); messaggio(ok || "Fatto.", "ok"); await vistaCorrente(true); }
  catch (e) { messaggio(e.message, "err"); }
}
async function vistaPersonale(v) {
  if (!S.stato.aperto) { v.append(el("div", { class: "vuoto" }, "Importa prima il file dalla Home.")); return; }
  const d = await api("/api/personale");
  const domani = new Date(d.data); domani.setDate(domani.getDate() + 1);
  const iso = x => x.toISOString().slice(0, 10);
  v.append(el("div", { class: "riga" }, el("h1", {}, "Personale"), el("span", { class: "piccolo" }, "Situazione al " + dmy(d.data))));
  v.append(el("div", { id: "avviso", class: "avviso", hidden: true, role: "status" }));
  const t = el("table", { class: "elenco" }, el("thead", {}, el("tr", {}, ["Pos", "Gr.", "Nome", "In servizio dal", "Fino al", ""].map(x => el("th", {}, x)))));
  const tb = el("tbody");
  for (const r of d.elenco) {
    const az = el("td", { class: "az" });
    if (r.nome) {
      az.append(el("button", { onclick: () => sostituisci(r, d) }, "Sostituisci…"), " ");
      az.append(el("button", { onclick: async () => {
        const o = r.al
          ? await modulo("Cambia uscita – posizione " + r.pos, r.nome + " ha l'uscita programmata: ultimo giorno " + dmy(r.al) + ". Scrivi la nuova data (prima o dopo).", [{ id: "data", label: "Ultimo giorno di servizio", tipo: "date", valore: r.al }], "Cambia uscita")
          : await modulo("Uscita – posizione " + r.pos, r.nome + " smette di prestare servizio. Indica l'ultimo giorno di servizio: da quella data in poi la posizione resta libera.", [{ id: "data", label: "Ultimo giorno di servizio", tipo: "date", valore: iso(domani) }], "Registra uscita");
        if (o) azionePers("uscita", { pos: r.pos, data: o.data }, r.al ? "Uscita cambiata." : "Uscita registrata.");
      } }, r.al ? "Cambia uscita…" : "Uscita…"));
    } else {
      az.append(el("button", { onclick: () => ingresso(r.pos, d) }, "Nuovo ingresso…"));
    }
    tb.append(el("tr", { class: r.nome ? "" : "libera" }, el("td", {}, r.pos), el("td", {}, r.gruppo), el("td", { class: "n" }, r.nome || "libera"), el("td", {}, r.dal ? dmy(r.dal) : ""), el("td", {}, r.al ? dmy(r.al) : ""), az));
  }
  t.append(tb);
  const sx = el("div", {}, el("div", { class: "scheda" }, t));
  if (d.programmati.length) {
    const li = el("div", { class: "scheda", style: "margin-top:14px" }, el("h2", {}, "Modifiche programmate"));
    for (const p of d.programmati) {
      li.append(el("div", { class: "riga", style: "margin:4px 0" },
        el("span", {}, (p.tipo === "ingresso" ? "Ingresso di " : "Uscita di ") + p.nome + " – posizione " + p.pos + ", " + (p.tipo === "ingresso" ? "dal " : "ultimo giorno ") + dmy(p.data)),
        el("span", { style: "flex:1" }),
        el("button", { onclick: () => azionePers(p.tipo === "ingresso" ? "annulla_ingresso" : "annulla_uscita", { pos: p.pos, data: p.data }, "Annullato.") }, "Annulla")));
    }
    sx.append(li);
  }
  const gr = el("div", { class: "scheda" }, el("h2", {}, "Graduatoria (in attesa di entrare)"));
  if (!d.graduatoria.length) gr.append(el("p", { class: "piccolo" }, "Vuota."));
  d.graduatoria.forEach((n, i) => gr.append(el("div", { class: "grad" },
    el("span", { class: "num" }, i + 1), el("span", { class: "n" }, n),
    el("button", { class: "freccia", "aria-label": "Su", disabled: i === 0, onclick: () => azionePers("sposta", { nome: n, posto: i }, "Spostato.") }, "↑"),
    el("button", { class: "freccia", "aria-label": "Giù", disabled: i === d.graduatoria.length - 1, onclick: () => azionePers("sposta", { nome: n, posto: i + 2 }, "Spostato.") }, "↓"),
    el("button", { onclick: async () => { if (await dialogo("Togli dalla graduatoria", n + " esce dalla graduatoria.", { ok: "Togli" })) azionePers("togli", { nome: n }, "Tolto."); } }, "Togli"))));
  gr.append(el("div", { class: "riga", style: "margin-top:10px" },
    el("button", { onclick: async () => {
      const o = await modulo("Aggiungi in graduatoria", "", [{ id: "nome", label: "Nome", tipo: "text" }, { id: "posto", label: "Posto (vuoto = in fondo)", tipo: "number" }], "Aggiungi");
      if (o && o.nome.trim()) azionePers("aggiungi", { nome: o.nome, posto: o.posto ? +o.posto : null }, "Aggiunto.");
    } }, "Aggiungi…")));
  v.append(el("div", { class: "pers", style: "margin-top:12px" }, sx, gr));
}
async function sostituisci(r, d) {
  const dom = new Date(d.data); dom.setDate(dom.getDate() + 1);
  const campi = [];
  if (d.graduatoria.length) campi.push({ id: "scelta", label: "Chi entra", tipo: "select", valore: d.graduatoria[0], opzioni: [...d.graduatoria, "Altro nome (non in graduatoria)"] });
  campi.push({ id: "altro", label: "Nome (solo se non è in graduatoria)", tipo: "text" });
  campi.push({ id: "data", label: "Primo giorno di servizio del nuovo", tipo: "date", valore: (r.al ? new Date(new Date(r.al).getTime() + 86400000) : dom).toISOString().slice(0, 10) });
  const o = await modulo("Sostituisci – posizione " + r.pos, r.nome + " esce il giorno prima della data scelta; dalla data scelta nella stessa posizione entra il nuovo.", campi, "Registra sostituzione");
  if (!o) return;
  const inGrad = o.scelta && o.scelta !== "Altro nome (non in graduatoria)";
  const nome = inGrad ? o.scelta : (o.altro || "").trim();
  if (!nome) { messaggio("Scrivi il nome.", "err"); return; }
  azionePers("sostituisci", { pos: r.pos, nome, data: o.data, da_graduatoria: inGrad }, "Sostituzione registrata.");
}
async function ingresso(pos, d) {
  const dom = new Date(d.data); dom.setDate(dom.getDate() + 1);
  const campi = [];
  if (d.graduatoria.length) campi.push({ id: "scelta", label: "Chi entra", tipo: "select", valore: d.graduatoria[0], opzioni: [...d.graduatoria, "Altro nome (non in graduatoria)"] });
  campi.push({ id: "altro", label: "Nome (solo se non è in graduatoria)", tipo: "text" });
  campi.push({ id: "data", label: "Primo giorno di servizio", tipo: "date", valore: dom.toISOString().slice(0, 10) });
  const o = await modulo("Nuovo ingresso – posizione " + pos, "La posizione deve essere libera dalla data scelta.", campi, "Registra ingresso");
  if (!o) return;
  const inGrad = o.scelta && o.scelta !== "Altro nome (non in graduatoria)";
  const nome = inGrad ? o.scelta : (o.altro || "").trim();
  if (!nome) { messaggio("Scrivi il nome.", "err"); return; }
  azionePers("ingresso", { pos, nome, data: o.data, da_graduatoria: inGrad }, "Ingresso registrato.");
}

/* ---------------- Anagrafica ---------------- */
const NOMI_SUSS = { Feriale: "Sussidiari – feriale", Sabato: "Sussidiari – sabato", Domenica: "Sussidiari – domenica/festivo",
  Lun_CasoA: "Sussidiari – primo feriale dopo domenica/festivo, caso A (6 o meno in servizio)", Lun_CasoB: "Sussidiari – primo feriale dopo domenica/festivo, caso B" };
const NOMI_DISP = { Feriale: "Disponibilità – feriale", Sabato: "Disponibilità – sabato", Domenica: "Disponibilità – domenica/festivo" };
async function azioneAnag(az, corpo, ok) {
  try { await api("/api/anagrafica/" + az, corpo); await aggiornaStato(); messaggio(ok || "Salvato.", "ok"); await vistaCorrente(true); }
  catch (e) { messaggio(e.message, "err"); }
}
async function vistaAnagrafica(v) {
  if (!S.stato.aperto) { v.append(el("div", { class: "vuoto" }, "Importa prima il file dalla Home.")); return; }
  if (!S.anagDal) { const d = new Date(S.stato.oggi); d.setDate(d.getDate() + 1); S.anagDal = d.toISOString().slice(0, 10); }
  const a = await api("/api/anagrafica?data=" + S.anagDal);
  const dalIn = el("input", { type: "text", inputmode: "numeric", placeholder: "gg/mm/aaaa", maxlength: 10, style: "width:110px", value: dmy(S.anagDal), "aria-label": "Valido dal",
    onchange: e => { const x = leggiData(e.target.value); if (x) { S.anagDal = x; vistaCorrente(); } else { e.target.style.borderColor = "#B42318"; messaggio("Scrivi la data come gg/mm/aaaa.", "err"); } } });
  v.append(el("div", { class: "riga" }, el("h1", {}, "Anagrafica"), el("span", { style: "flex:1" }),
    el("label", { class: "piccolo" }, "Le modifiche valgono dal ", dalIn)));
  v.append(el("p", { class: "piccolo" }, "Qui si cambiano orari e priorità. Ogni modifica vale dal giorno scelto in poi: i giorni passati non cambiano. I codici dei turni non si modificano. " +
    "Situazione in vigore al " + dmy(S.anagDal) + (a.valida_dal > "2000-01-01" ? " (ultima modifica dal " + dmy(a.valida_dal) + ")." : " (nessuna modifica fatta finora).")));
  v.append(el("div", { id: "avviso", class: "avviso", hidden: true, role: "status", style: "margin:0 0 12px" }));
  const dal = S.anagDal;
  if (a.programmate.length) {
    const c = el("div", { class: "scheda", style: "margin-bottom:14px" }, el("h2", {}, "Modifiche programmate"));
    for (const p of a.programmate) c.append(el("div", { class: "riga", style: "margin:4px 0" }, el("span", {}, "Dal " + dmy(p)), el("span", { style: "flex:1" }),
      el("button", { onclick: async () => { if (await dialogo("Elimina modifica", "Elimini tutte le modifiche di orari e priorità programmate dal " + dmy(p) + "?", { ok: "Elimina" })) azioneAnag("elimina", { dal: p }, "Modifica eliminata."); } }, "Elimina")));
    v.append(c);
  }
  // turni
  const tt = el("table", { class: "elenco" }, el("thead", {}, el("tr", {}, ["Turno", "Feriale", "Sabato", "Domenica/festivo", ""].map(x => el("th", {}, x)))));
  const tb = el("tbody");
  for (const t of a.turni) {
    const campi = {};
    const tr = el("tr", {}, el("td", { class: "n" }, t.codice));
    for (const m of ["Feriale", "Sabato", "Domenica"]) {
      const [i, f] = t.orari[m];
      if (!i) { tr.append(el("td", { class: "piccolo" }, "—")); continue; }
      const ii = el("input", { class: "ora", type: "text", inputmode: "numeric", maxlength: 5, placeholder: "hh:mm", value: i }), ff = el("input", { class: "ora", type: "text", inputmode: "numeric", maxlength: 5, placeholder: "hh:mm", value: f });
      campi[m] = [ii, ff];
      tr.append(el("td", {}, ii, " – ", ff));
    }
    tr.append(el("td", { class: "az" }, el("button", { onclick: () => {
      const orari = {}; for (const [m, [ii, ff]] of Object.entries(campi)) orari[m] = [ii.value, ff.value];
      azioneAnag("turno", { codice: t.codice, orari, dal }, "Orari del " + t.codice + " salvati dal " + dmy(dal) + ".");
    } }, "Salva")));
    tb.append(tr);
  }
  tt.append(tb);
  v.append(el("div", { class: "scheda" }, el("h2", {}, "Orari dei turni"), tt));
  // sussidiari
  const gs = el("div", { class: "griglia2", style: "margin-top:14px" });
  for (const [k, lista] of Object.entries(a.sussidiari)) {
    let righe = lista.map(x => ({ ...x }));
    const corpo = el("div");
    const disegna = () => {
      corpo.innerHTML = "";
      righe.forEach((r, i) => {
        const ii = el("input", { class: "ora", type: "text", inputmode: "numeric", maxlength: 5, value: r.inizio, onchange: e => { r.inizio = e.target.value; } });
        const ff = el("input", { class: "ora", type: "text", inputmode: "numeric", maxlength: 5, value: r.fine, onchange: e => { r.fine = e.target.value; } });
        corpo.append(el("div", { class: "grad" }, el("span", { class: "num" }, i + 1), el("span", { class: "n", style: "max-width:60px" }, r.codice), ii, " – ", ff,
          el("button", { class: "freccia", disabled: i === 0, "aria-label": "Su", onclick: () => { [righe[i - 1], righe[i]] = [righe[i], righe[i - 1]]; disegna(); } }, "↑"),
          el("button", { class: "freccia", disabled: i === righe.length - 1, "aria-label": "Giù", onclick: () => { [righe[i + 1], righe[i]] = [righe[i], righe[i + 1]]; disegna(); } }, "↓")));
      });
    };
    disegna();
    gs.append(el("div", { class: "scheda" }, el("h2", {}, NOMI_SUSS[k] || k), el("p", { class: "piccolo" }, "In ordine di priorità, dalla prima."), corpo,
      el("div", { class: "riga", style: "margin-top:10px" }, el("button", { onclick: () => azioneAnag("sussidiari", { chiave: k, righe, dal }, "Sussidiari salvati dal " + dmy(dal) + ".") }, "Salva"))));
  }
  // disponibilita'
  for (const [m, lista] of Object.entries(a.disponibilita)) {
    let ordine = [...lista];
    const corpo = el("div");
    const disegna = () => {
      corpo.innerHTML = "";
      ordine.forEach((c, i) => corpo.append(el("div", { class: "grad" }, el("span", { class: "num" }, i + 1), el("span", { class: "n" }, c),
        el("button", { class: "freccia", disabled: i === 0, "aria-label": "Su", onclick: () => { [ordine[i - 1], ordine[i]] = [ordine[i], ordine[i - 1]]; disegna(); } }, "↑"),
        el("button", { class: "freccia", disabled: i === ordine.length - 1, "aria-label": "Giù", onclick: () => { [ordine[i + 1], ordine[i]] = [ordine[i], ordine[i + 1]]; disegna(); } }, "↓"))));
    };
    disegna();
    gs.append(el("div", { class: "scheda" }, el("h2", {}, NOMI_DISP[m] || m), el("p", { class: "piccolo" }, "Chi copre per primo i turni scoperti, in ordine."), corpo,
      el("div", { class: "riga", style: "margin-top:10px" }, el("button", { onclick: () => azioneAnag("disponibilita", { modalita: m, ordine, dal }, "Disponibilità salvate dal " + dmy(dal) + ".") }, "Salva"))));
  }
  v.append(gs);
  // turni di Natale (25/12): orari propri, il resto come i festivi
  if (a.natale) {
    const n = a.natale, campi = [];
    const tb = el("tbody");
    const riga = (tipo, [c, i, f]) => {
      const ii = el("input", { class: "ora", type: "text", inputmode: "numeric", maxlength: 5, placeholder: "hh:mm", value: i });
      const ff = el("input", { class: "ora", type: "text", inputmode: "numeric", maxlength: 5, placeholder: "hh:mm", value: f });
      campi.push([c, ii, ff]);
      tb.append(el("tr", {}, el("td", { class: "n" }, c), el("td", { class: "piccolo" }, tipo), el("td", {}, ii, " – ", ff)));
    };
    n.turni.forEach(x => riga("principale", x));
    n.sussidiari.forEach(x => riga("sussidiario", x));
    v.append(el("div", { class: "scheda", style: "margin-top:14px" },
      el("h2", {}, "Turni di Natale (25 dicembre)"),
      el("p", { class: "piccolo" }, "Valgono solo il 25/12, qualunque giorno della settimana; il 26/12 è un festivo normale. Si coprono " + n.turni_coperti +
        " turni; dal presente successivo, eccedenti in FU come nei festivi. Disponibili, in ordine: " + n.disponibili.join(", ") +
        " (l'ultimo copre il turno che inizia più tardi). Versione del " + dmy(n.valida_dal) + (n.programmate.length ? "; cambiamenti programmati dal " + n.programmate.map(dmy).join(", ") : "") + ". Una modifica vale dal primo 25 dicembre dalla data scelta in alto."),
      el("table", { class: "elenco" }, el("thead", {}, el("tr", {}, ["Turno", "", "Orario"].map(x => el("th", {}, x)))), tb),
      el("div", { class: "riga", style: "margin-top:10px" }, el("button", { onclick: () => azioneAnag("natale",
        { righe: campi.map(([c, ii, ff]) => ({ codice: c, inizio: ii.value, fine: ff.value })), dal },
        "Orari di Natale salvati: valgono dal primo 25 dicembre dal " + dmy(dal) + " in poi.") }, "Salva"))));
  }
}

/* ---------------- Anteprima importazione (in fondo alla pagina Settimana) ---------------- */
const STATI = { APPLICA: ["Da applicare", "#1E7B46"], CONFLITTO: ["Conflitto", "#B42318"], MANUALE: ["A mano", "#B54708"], MANTENUTA: ["Resta com'è", "#5B6675"], SALTATA: ["Saltata", "#5B6675"] };
function pannelloAnteprima(r) {
  const ultima = r.ultima ? "Ultima importazione: " + r.ultima.file + ", " + dmy(r.ultima.quando.slice(0, 10)) + " " + r.ultima.quando.slice(11) : "Nessuna importazione fatta finora.";
  const sez = el("section", { id: "pannello-anteprima", class: "scheda", style: "margin-top:14px", "aria-label": "Anteprima importazione" });
  sez.append(el("h2", {}, "Anteprima importazione"));
  if (!r.anteprima) {
    sez.append(el("p", { class: "piccolo" }, "Nessuna importazione in corso. Scegli il file e le settimane nel riquadro 1 · Importa dalla Rotazione: qui vedrai cosa cambierebbe, prima di applicarlo."), el("p", { class: "piccolo" }, ultima));
    return sez;
  }
  const p = r.anteprima, ri = p.riepilogo;
  const chips = el("div", { class: "riga" });
  for (const [k, [nome, col]] of Object.entries(STATI)) chips.append(el("span", { class: "chip", style: "border-color:" + col + ";color:" + col }, (ri[k] || 0) + " " + nome.toLowerCase()));
  const filtro = el("select", { "aria-label": "Mostra", onchange: () => disegna() }, el("option", { value: "" }, "Mostra tutti"), ...Object.entries(STATI).map(([k, [n]]) => el("option", { value: k }, n)));
  const tb = el("tbody");
  const disegna = () => {
    tb.innerHTML = "";
    for (const x of p.righe) {
      if (filtro.value && x.stato !== filtro.value) continue;
      const [sn, sc] = STATI[x.stato] || [x.stato, "#000"];
      tb.append(el("tr", {}, el("td", {}, dmy(x.data)), el("td", { class: "n" }, x.nome), el("td", {}, x.tipo === "NOTA" ? "Nota" : "Colore"),
        el("td", { class: "tr" }, x.vecchio), el("td", { class: "tr" }, x.nuovo), el("td", { style: "color:" + sc + ";font-weight:700" }, sn), el("td", { class: "piccolo" }, x.motivo)));
    }
  };
  disegna();
  const applicabili = ri.APPLICA || 0;
  sez.append(el("p", { style: "margin:0 0 8px;font-weight:600" }, p.nome + " (anno " + p.anno + ")"), chips,
    p.fuori ? el("p", { class: "piccolo" }, p.fuori + " giorni delle settimane scelte sono fuori dall'anno e non vengono letti.") : null,
    !p.righe.length ? el("p", {}, "Nessuna differenza trovata nelle settimane indicate.") : null,
    el("div", { class: "riga", style: "margin:10px 0" }, filtro, el("span", { style: "flex:1" }),
      el("button", { onclick: async () => { await api("/api/import/annulla", {}); vistaCorrente(); } }, "Scarta"),
      el("button", { class: "primario", disabled: !applicabili, onclick: async () => {
        if (!await dialogo("Applica i cambiamenti", "Vengono applicati " + applicabili + " cambiamenti. Conflitti, celle da gestire a mano e cambiamenti già presenti restano come sono. Prima del salvataggio il programma fa una copia di sicurezza.", { ok: "Applica" })) return;
        try { const x = await api("/api/import/applica", {}); await aggiornaStato(); await vistaCorrente(); messaggio("Applicati " + x.colori + " colori e " + x.note + " note. Il servizio della settimana è aggiornato.", "ok"); }
        catch (e) { messaggio(e.message, "err"); }
      } }, "Applica " + applicabili)),
    p.righe.length ? el("div", { class: "tab-sc", style: "margin-top:0" }, el("table", { class: "elenco" }, el("thead", {}, el("tr", {}, ["Data", "Collega", "Cosa", "Nel programma", "Nel file", "Esito", "Motivo"].map(x => el("th", {}, x)))), tb)) : null,
    el("p", { class: "piccolo", style: "margin-top:10px" }, ultima));
  return sez;
}


/* ---------------- RL ---------------- */
async function vistaRL(v) {
  if (!S.stato.aperto) { v.append(el("div", { class: "vuoto" }, "Importa prima il file dalla Home.")); return; }
  const anni = S.stato.anni;
  if (!S.rlAnno || !anni.includes(S.rlAnno)) S.rlAnno = S.anno || anni[0];
  const d = await api("/api/rl?anno=" + S.rlAnno);
  const i = anni.indexOf(S.rlAnno);
  const colleghi = [...new Set(d.righe.map(r => r.nome))].sort();
  const fc = el("select", { "aria-label": "Collega", onchange: () => disegna() }, el("option", { value: "" }, "Tutti"), ...colleghi.map(n => el("option", { value: n }, n)));
  const fm = el("select", { "aria-label": "Mese", onchange: () => disegna() }, el("option", { value: "" }, "Tutti"), ...d.mesi.map(m => el("option", { value: m.mese }, m.nome)));
  v.append(el("div", { class: "riga" }, el("h1", {}, "RL " + d.anno),
    el("button", { class: "freccia", "aria-label": "Anno precedente", disabled: i <= 0, onclick: () => { S.rlAnno = anni[i - 1]; vistaCorrente(); } }, "‹"),
    el("button", { class: "freccia", "aria-label": "Anno successivo", disabled: i >= anni.length - 1, onclick: () => { S.rlAnno = anni[i + 1]; vistaCorrente(); } }, "›"),
    el("span", { style: "flex:1" }),
    el("label", { class: "piccolo" }, "Collega ", fc), el("label", { class: "piccolo" }, "Mese ", fm),
    el("a", { class: "bottone", style: "background:#D9D9D9", href: "/api/esporta/rl?anno=" + d.anno }, "Esporta elenco")));
  const tb = el("tbody");
  const disegna = () => {
    tb.innerHTML = "";
    const rr = d.righe.filter(r => (!fc.value || r.nome === fc.value) && (!fm.value || +r.data.slice(5, 7) === +fm.value));
    for (const r of rr) tb.append(el("tr", {}, el("td", {}, dmy(r.data)), el("td", { class: "n" }, el("span", { class: "quad" }), r.nome), el("td", { class: "n" }, r.turno)));
    if (!rr.length) tb.append(el("tr", {}, el("td", { colspan: 3, class: "piccolo", style: "padding:14px" }, "Nessun RL.")));
  };
  disegna();
  const max = Math.max(1, ...d.mesi.map(m => m.n));
  const per_mese = el("div", { class: "scheda" }, el("h2", {}, "Riepilogo per mese"),
    ...d.mesi.map(m => el("div", { class: "barra-m" }, el("span", {}, m.nome), el("div", { class: "pista" }, el("div", { class: "riemp", style: "width:" + (m.n / max * 100) + "%" })), el("b", {}, m.n))),
    el("div", { class: "riga sp", style: "border-top:1px solid var(--bordo);padding-top:8px;margin-top:6px;font-weight:700" }, el("span", {}, "Totale anno"), el("span", {}, d.totale)));
  const per_c = el("div", { class: "scheda" }, el("h2", {}, "Per collega"),
    ...(d.colleghi.length ? d.colleghi.map(c => el("div", { class: "riga sp", style: "font-size:12px;margin:3px 0" }, el("span", {}, c.nome), el("b", {}, c.n))) : [el("p", { class: "piccolo" }, "Nessun RL.")]));
  v.append(el("div", { class: "pers", style: "margin-top:12px;grid-template-columns:minmax(0,1.6fr) minmax(260px,1fr)" },
    el("div", { class: "scheda" }, el("table", { class: "elenco" }, el("thead", {}, el("tr", {}, ["Data", "Collega", "Turno coperto"].map(x => el("th", {}, x)))), tb)),
    el("div", { style: "display:flex;flex-direction:column;gap:14px" }, per_mese, per_c)));
  v.append(el("p", { class: "piccolo" }, "L'elenco si aggiorna da solo quando si assegna o si cancella un RL nell'Anno."));
}

/* ---------------- navigazione ---------------- */
const VISTE = { home: vistaHome, anno: vistaAnno, settimana: vistaSettimana, personale: vistaPersonale, anagrafica: vistaAnagrafica, anteprima: vistaSettimana, rl: vistaRL };
function vai(n) { location.hash = "#" + n; if (location.hash === "#" + n) vistaCorrente(); }
async function vistaCorrente(mantieniMsg) {
  const tok = S.tok = (S.tok || 0) + 1;                 // se parte un'altra visualizzazione, questa viene scartata
  const n = (location.hash || "#home").slice(1);
  const f = VISTE[n] || vistaHome;
  document.querySelectorAll("#menu a").forEach(a => a.classList.toggle("attiva", a.dataset.v === (n === "anteprima" ? "settimana" : n)));
  const vecchio = $("#vista"); const y = vecchio.scrollTop, x = vecchio.scrollLeft;
  const v = el("main", { id: "vista", tabindex: "-1" });
  if (!mantieniMsg) messaggio("");
  try { await f(v); } catch (e) { v.append(el("div", { class: "vuoto" }, "Errore: " + e.message)); }
  if (tok !== S.tok) return;
  vecchio.replaceWith(v);
  v.scrollTop = y; v.scrollLeft = x;
  if (mantieniMsg && S.msg) messaggio(S.msg[0], S.msg[1]);
  if (document.querySelector(".barra-tasti")) aggiornaTasti();
}
window.addEventListener("hashchange", () => vistaCorrente());
(async () => { try { await aggiornaStato(); } catch (e) { messaggio(e.message, "err"); } vistaCorrente(); })();
