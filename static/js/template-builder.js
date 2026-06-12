/* Builder de plantillas de correo (vanilla, sin dependencias).
 * Paleta -> lienzo (arrastrar o clic), reordenar por handle, editar inline.
 * Serializa los bloques a #id_blocks_json. Los campos de dato obligatorios se
 * colocan bloqueados (no se pueden quitar). */
(function () {
  "use strict";
  var form = document.getElementById("tpl-form");
  if (!form) return;

  var hidden = document.getElementById("id_blocks_json");
  var kindSel = document.getElementById("id_kind");
  var canvas = document.getElementById("tpl-canvas");
  var empty = document.getElementById("tpl-empty");
  var paletteEl = document.getElementById("tpl-palette-items");
  var dataEl = document.getElementById("tpl-data-items");

  var VARS = JSON.parse((document.getElementById("tpl-vars") || {}).textContent || "{}");
  var MAND = JSON.parse((document.getElementById("tpl-mandatory") || {}).textContent || "{}");

  var STRUCT = [
    { type: "heading", label: "Encabezado" },
    { type: "text", label: "Texto" },
    { type: "button", label: "Botón/enlace" },
    { type: "divider", label: "Separador" },
    { type: "spacer", label: "Espaciador" },
    { type: "footer", label: "Pie" },
  ];

  var blocks = [];
  var dragIndex = null;

  function kind() { return kindSel ? kindSel.value : "CERT"; }
  function vars() { return VARS[kind()] || {}; }
  function mandatory() { return MAND[kind()] || []; }
  function isMandatory(field) { return mandatory().indexOf(field) !== -1; }

  function defaultProps(type) {
    if (type === "heading") return { text: "Título" };
    if (type === "text") return { text: "Escribe el mensaje. Usa {{variable}} para insertar datos." };
    if (type === "footer") return { text: "CertManager · notificación automática" };
    if (type === "button") return { label: "Abrir", href: "https://" };
    return {};
  }

  function newBlock(type, field) {
    var b = { type: type, props: defaultProps(type) };
    if (type === "data") { b.field = field; b.locked = isMandatory(field); }
    return b;
  }

  function serialize() {
    if (hidden) hidden.value = JSON.stringify(blocks);
    if (empty) empty.style.display = blocks.length ? "none" : "block";
  }

  function label(field) {
    var v = vars()[field];
    return v ? v.label : field;
  }

  function editor(b, idx) {
    var wrap = document.createElement("div");
    wrap.className = "tpl-block__edit";
    if (b.type === "heading" || b.type === "text" || b.type === "footer") {
      var ta = document.createElement("textarea");
      ta.className = "input"; ta.rows = b.type === "text" ? 2 : 1; ta.value = b.props.text || "";
      ta.addEventListener("input", function () { blocks[idx].props.text = ta.value; serialize(); });
      wrap.appendChild(ta);
    } else if (b.type === "button") {
      ["label", "href"].forEach(function (k) {
        var inp = document.createElement("input");
        inp.className = "input"; inp.placeholder = k === "label" ? "Texto del botón" : "URL";
        inp.value = b.props[k] || "";
        inp.addEventListener("input", function () { blocks[idx].props[k] = inp.value; serialize(); });
        wrap.appendChild(inp);
      });
    } else if (b.type === "data") {
      var span = document.createElement("span");
      span.className = "tpl-block__data";
      span.textContent = "{{" + b.field + "}} — " + label(b.field) + (b.locked ? "  🔒" : "");
      wrap.appendChild(span);
    } else {
      var note = document.createElement("span");
      note.className = "tpl-block__data";
      note.textContent = b.type === "divider" ? "──────────" : (b.type === "spacer" ? "(espacio)" : "");
      wrap.appendChild(note);
    }
    return wrap;
  }

  function blockTypeLabel(b) {
    if (b.type === "data") return "Dato";
    var f = STRUCT.filter(function (s) { return s.type === b.type; })[0];
    return f ? f.label : b.type;
  }

  function render() {
    canvas.innerHTML = "";
    blocks.forEach(function (b, idx) {
      var el = document.createElement("div");
      el.className = "tpl-block" + (b.locked ? " tpl-block--locked" : "");
      el.setAttribute("draggable", "true");
      el.dataset.idx = idx;
      el.addEventListener("dragstart", function () { dragIndex = idx; el.classList.add("tpl-block--dragging"); });
      el.addEventListener("dragend", function () { dragIndex = null; el.classList.remove("tpl-block--dragging"); });
      el.addEventListener("dragover", function (e) { e.preventDefault(); });
      el.addEventListener("drop", function (e) {
        e.preventDefault();
        if (dragIndex === null || dragIndex === idx) return;
        var moved = blocks.splice(dragIndex, 1)[0];
        blocks.splice(idx, 0, moved);
        serialize(); render();
      });

      var head = document.createElement("div");
      head.className = "tpl-block__head";
      head.innerHTML = '<span class="tpl-handle" aria-hidden="true">⋮⋮</span><span class="tpl-block__type">' + blockTypeLabel(b) + "</span>";
      if (!b.locked) {
        var del = document.createElement("button");
        del.type = "button"; del.className = "tpl-block__del"; del.textContent = "✕"; del.title = "Quitar";
        del.addEventListener("click", function () { blocks.splice(idx, 1); serialize(); render(); });
        head.appendChild(del);
      } else {
        var lock = document.createElement("span"); lock.className = "tpl-block__lock"; lock.textContent = "🔒"; head.appendChild(lock);
      }
      el.appendChild(head);
      el.appendChild(editor(b, idx));
      canvas.appendChild(el);
    });
    serialize();
  }

  function addBlock(b) { blocks.push(b); render(); }

  function renderPalette() {
    paletteEl.innerHTML = "";
    STRUCT.forEach(function (s) {
      var item = paletteItem(s.label, function () { addBlock(newBlock(s.type)); });
      item.addEventListener("dragstart", function (e) { e.dataTransfer.setData("text/plain", "struct:" + s.type); });
      paletteEl.appendChild(item);
    });
    dataEl.innerHTML = "";
    Object.keys(vars()).forEach(function (field) {
      var v = vars()[field];
      var item = paletteItem((v.mandatory ? "🔒 " : "") + v.label, function () {
        if (hasData(field)) return;
        addBlock(newBlock("data", field));
      });
      item.addEventListener("dragstart", function (e) { e.dataTransfer.setData("text/plain", "data:" + field); });
      dataEl.appendChild(item);
    });
  }

  function hasData(field) {
    return blocks.some(function (b) { return b.type === "data" && b.field === field; });
  }

  function paletteItem(text, onAdd) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "tpl-pal-item"; b.setAttribute("draggable", "true");
    b.textContent = text;
    b.addEventListener("click", onAdd);
    return b;
  }

  // Drop desde la paleta al lienzo.
  canvas.addEventListener("dragover", function (e) { e.preventDefault(); canvas.classList.add("tpl-canvas--over"); });
  canvas.addEventListener("dragleave", function () { canvas.classList.remove("tpl-canvas--over"); });
  canvas.addEventListener("drop", function (e) {
    canvas.classList.remove("tpl-canvas--over");
    var data = e.dataTransfer.getData("text/plain") || "";
    if (data.indexOf("struct:") === 0) { addBlock(newBlock(data.slice(7))); }
    else if (data.indexOf("data:") === 0) {
      var f = data.slice(5);
      if (!hasData(f)) addBlock(newBlock("data", f));
    }
  });

  function ensureMandatory() {
    mandatory().forEach(function (field) {
      if (!hasData(field)) blocks.push(newBlock("data", field));
    });
  }

  function onKindChange() {
    // Quita los datos que no pertenecen al nuevo tipo y asegura los obligatorios.
    blocks = blocks.filter(function (b) { return b.type !== "data" || vars()[b.field]; });
    blocks.forEach(function (b) { if (b.type === "data") b.locked = isMandatory(b.field); });
    ensureMandatory();
    renderPalette(); render();
  }

  if (kindSel) kindSel.addEventListener("change", onKindChange);
  form.addEventListener("submit", serialize);

  // Init: carga bloques existentes o siembra los obligatorios.
  try { blocks = JSON.parse((hidden && hidden.value) || "[]"); if (!Array.isArray(blocks)) blocks = []; }
  catch (e) { blocks = []; }
  blocks.forEach(function (b) { if (b.type === "data") b.locked = isMandatory(b.field); });
  ensureMandatory();
  renderPalette();
  render();
})();
