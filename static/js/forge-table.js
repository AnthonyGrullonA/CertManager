/* Forge UI — ForgeTable
 * ---------------------------------------------------------------------------
 * Componente de tabla propio, SIN dependencias externas (adiós DataTables).
 * Inspirado en el DataTable.jsx del design system (Template/components/data).
 *
 * Mejora cualquier <table> dentro de un wrapper [data-forge-table]:
 *   · header sticky (se queda fijo mientras el cuerpo hace scroll);
 *   · cuerpo con scroll interno de ALTO FIJO, anclado al page-size por defecto:
 *     cambiar las filas por página NO cambia el tamaño de la tarjeta;
 *   · footer único: "X–Y de Z" + selector "por página" + paginador;
 *   · orden por columna si el wrapper declara data-forge-sortable
 *     (las columnas con data-no-sort quedan excluidas).
 *
 * Atributos del wrapper:
 *   data-page-size="8"     filas por página por defecto (ancla la altura)
 *   data-forge-sortable    habilita el orden por columna
 *   data-row-h, data-rows  (opcionales) override del cálculo de altura
 *
 * Markup esperado (ya presente en los templates):
 *   <div data-forge-table data-page-size="8" data-forge-sortable>
 *     <div class="forge-table-scroll">
 *       <table> <thead>…</thead> <tbody>…filas…</tbody> </table>
 *     </div>
 *   </div>
 * Si falta .forge-table-scroll, el componente lo crea.
 * ------------------------------------------------------------------------- */
(function () {
  "use strict";

  // i18n: textos inyectados por la plantilla (window.CF_TABLE_I18N) con fallback es.
  var _I18N = (typeof window !== "undefined" && window.CF_TABLE_I18N) || {};
  function T(key, def) { return _I18N[key] || def; }

  var SVG = {
    left: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>',
    right: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>',
    first: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/></svg>',
    last: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 17 5-5-5-5"/><path d="m13 17 5-5-5-5"/></svg>',
    sort: '<span class="forge-sort-wrap" aria-hidden="true"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg></span>'
  };

  // Estado por wrapper (no contaminamos el DOM con propiedades sueltas).
  var store = new WeakMap();

  // ---- utilidades ---------------------------------------------------------
  function dataRows(tbody) {
    return Array.prototype.filter.call(tbody.children, function (tr) {
      return tr.tagName === "TR" && !tr.hasAttribute("data-empty-row");
    });
  }

  function intAttr(el, name, fallback) {
    var n = parseInt(el.getAttribute(name), 10);
    return n > 0 ? n : fallback;
  }

  function sizeOptions(defSize, total) {
    var base = [8, 15, 30];
    if (total > 30) base.push(50);
    if (base.indexOf(defSize) === -1) {
      base.push(defSize);
      base.sort(function (a, b) { return a - b; });
    }
    return base;
  }

  // ---- construcción del footer -------------------------------------------
  function pageBtn(svg, label) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "forge-table-pagebtn";
    b.setAttribute("aria-label", label);
    b.innerHTML = svg;
    return b;
  }

  function buildFooter(st) {
    var foot = document.createElement("div");
    foot.className = "forge-table-foot";

    var start = document.createElement("div");
    start.className = "forge-table-foot__start";

    st.info = document.createElement("span");
    st.info.className = "forge-table-info";

    var label = document.createElement("label");
    label.className = "forge-table-pagesize";
    var labelText = document.createElement("span");
    labelText.textContent = T("perPage", "por página");
    st.select = document.createElement("select");
    st.select.setAttribute("aria-label", T("rowsPerPage", "Filas por página"));
    label.appendChild(labelText);
    label.appendChild(st.select);

    start.appendChild(st.info);
    start.appendChild(label);

    var pager = document.createElement("div");
    pager.className = "forge-table-pager";
    st.btnFirst = pageBtn(SVG.first, T("first", "Primera página"));
    st.btnPrev = pageBtn(SVG.left, T("prev", "Página anterior"));
    st.ind = document.createElement("span");
    st.ind.className = "forge-table-pageind";
    st.btnNext = pageBtn(SVG.right, T("next", "Página siguiente"));
    st.btnLast = pageBtn(SVG.last, T("last", "Última página"));
    pager.appendChild(st.btnFirst);
    pager.appendChild(st.btnPrev);
    pager.appendChild(st.ind);
    pager.appendChild(st.btnNext);
    pager.appendChild(st.btnLast);

    foot.appendChild(start);
    foot.appendChild(pager);
    return foot;
  }

  function fillSizeOptions(st) {
    var opts = sizeOptions(st.defSize, st.baseRows.length);
    st.select.innerHTML = "";
    opts.forEach(function (n) {
      var o = document.createElement("option");
      o.value = n;
      o.textContent = n;
      if (n === st.size) o.selected = true;
      st.select.appendChild(o);
    });
  }

  function wireFooter(st) {
    st.select.addEventListener("change", function () {
      st.size = parseInt(st.select.value, 10) || st.defSize;
      st.page = 0;
      render(st); // la ALTURA no cambia: solo el scroll interno
    });
    st.btnFirst.addEventListener("click", function () { st.page = 0; render(st); });
    st.btnPrev.addEventListener("click", function () { st.page -= 1; render(st); });
    st.btnNext.addEventListener("click", function () { st.page += 1; render(st); });
    st.btnLast.addEventListener("click", function () { st.page = 1e9; render(st); });
  }

  // ---- orden por columna --------------------------------------------------
  function setupSort(st) {
    if (!st.wrap.hasAttribute("data-forge-sortable") || !st.table.tHead) return;
    var cells = st.table.tHead.rows[0].cells;
    Array.prototype.forEach.call(cells, function (th) {
      if (th.hasAttribute("data-no-sort")) return;
      th.setAttribute("data-sortable", "");
      if (!th.querySelector(".forge-sort-wrap")) th.insertAdjacentHTML("beforeend", SVG.sort);
    });
    st.onHeadClick = function (e) {
      var th = e.target.closest("th[data-sortable]");
      if (!th || !cells) return;
      var idx = Array.prototype.indexOf.call(cells, th);
      if (idx < 0) return;
      onSort(st, idx);
    };
    st.table.tHead.addEventListener("click", st.onHeadClick);
  }

  function onSort(st, idx) {
    if (st.sort && st.sort.idx === idx) {
      if (st.sort.dir === "asc") st.sort.dir = "desc";
      else st.sort = null;          // tercer clic = sin orden
    } else {
      st.sort = { idx: idx, dir: "asc" };
    }
    applySort(st);
    updateSortGlyphs(st);
    st.page = 0;
    render(st);
  }

  function cellValue(tr, idx) {
    var td = tr.children[idx];
    if (!td) return "";
    var v = td.getAttribute("data-sort");
    return v != null ? v : (td.textContent || "").trim();
  }

  function applySort(st) {
    if (!st.sort) { st.rows = st.baseRows.slice(); return; }
    var idx = st.sort.idx, dir = st.sort.dir;
    st.rows = st.baseRows.slice().sort(function (a, b) {
      var va = cellValue(a, idx), vb = cellValue(b, idx);
      var na = parseFloat(va.replace(/[^0-9.\-]/g, ""));
      var nb = parseFloat(vb.replace(/[^0-9.\-]/g, ""));
      var bothNum = !isNaN(na) && !isNaN(nb) && /\d/.test(va) && /\d/.test(vb);
      var r = bothNum ? (na - nb) : va.localeCompare(vb, "es", { numeric: true, sensitivity: "base" });
      return dir === "desc" ? -r : r;
    });
  }

  function updateSortGlyphs(st) {
    if (!st.table.tHead) return;
    var cells = st.table.tHead.rows[0].cells;
    Array.prototype.forEach.call(cells, function (th, i) {
      th.classList.remove("is-asc", "is-desc");
      if (st.sort && st.sort.idx === i) th.classList.add(st.sort.dir === "asc" ? "is-asc" : "is-desc");
    });
  }

  // ---- altura fija --------------------------------------------------------
  // Mide el alto natural mostrando exactamente `defSize` filas y lo congela.
  // Así la tarjeta mide siempre lo mismo, sin importar el page-size elegido.
  function lockHeight(st) {
    var scroll = st.scroll;
    scroll.style.height = "auto";
    scroll.style.maxHeight = "none";
    var def = st.defSize;
    st.baseRows.forEach(function (tr, i) { tr.style.display = i < def ? "" : "none"; });
    var h = Math.ceil(scroll.scrollHeight);
    scroll.style.height = h + "px";
    scroll.style.maxHeight = h + "px";
  }

  // ---- render -------------------------------------------------------------
  function render(st) {
    var rows = st.rows;
    var total = rows.length;

    // Reordena el DOM al orden actual (barato para cientos de filas).
    var frag = document.createDocumentFragment();
    rows.forEach(function (tr) { frag.appendChild(tr); });
    st.tbody.appendChild(frag);

    var size = st.size;
    var pages = Math.max(1, Math.ceil(total / size));
    if (st.page > pages - 1) st.page = pages - 1;
    if (st.page < 0) st.page = 0;
    var start = st.page * size;
    var end = start + size;

    rows.forEach(function (tr, i) { tr.style.display = (i >= start && i < end) ? "" : "none"; });

    st.info.innerHTML = total
      ? ("<b>" + (start + 1) + "–" + Math.min(end, total) + "</b> " + T("of", "de") + " <b>" + total + "</b>")
      : "Sin registros";
    st.ind.textContent = (st.page + 1) + " / " + pages;
    st.btnFirst.disabled = st.btnPrev.disabled = (st.page === 0);
    st.btnLast.disabled = st.btnNext.disabled = (st.page >= pages - 1);

    if (st.scroll) st.scroll.scrollTop = 0;
  }

  // ---- ciclo de vida ------------------------------------------------------
  function enhance(wrap) {
    if (store.has(wrap)) return;
    var table = wrap.querySelector("table");
    if (!table || !table.tBodies || !table.tBodies[0]) return;

    var scroll = wrap.querySelector(".forge-table-scroll");
    if (!scroll) {
      scroll = document.createElement("div");
      scroll.className = "forge-table-scroll";
      table.parentNode.insertBefore(scroll, table);
      scroll.appendChild(table);
    }

    var defSize = intAttr(wrap, "data-page-size", 8);
    var st = {
      wrap: wrap, table: table, tbody: table.tBodies[0], scroll: scroll,
      defSize: defSize, size: defSize, page: 0, sort: null
    };
    st.baseRows = dataRows(st.tbody);
    st.rows = st.baseRows.slice();
    store.set(wrap, st);
    wrap.classList.add("forge-table-ready");

    // Sin filas de datos: solo dejamos el estado vacío y fijamos altura.
    if (st.baseRows.length === 0) {
      lockHeight(st);
      return;
    }

    setupSort(st);
    st.foot = buildFooter(st);
    wrap.appendChild(st.foot);
    fillSizeOptions(st);
    wireFooter(st);

    lockHeight(st);
    render(st);
  }

  function teardown(wrap) {
    var st = store.get(wrap);
    if (!st) return;
    if (st.onHeadClick && st.table.tHead) st.table.tHead.removeEventListener("click", st.onHeadClick);
    if (st.foot && st.foot.parentNode) st.foot.parentNode.removeChild(st.foot);
    if (st.scroll) { st.scroll.style.height = ""; st.scroll.style.maxHeight = ""; }
    st.baseRows.forEach(function (tr) { tr.style.display = ""; });
    if (st.table.tHead) {
      Array.prototype.forEach.call(st.table.tHead.rows[0].cells, function (th) {
        th.removeAttribute("data-sortable");
        th.classList.remove("is-asc", "is-desc");
        var g = th.querySelector(".forge-sort-wrap");
        if (g) g.remove();
      });
    }
    wrap.classList.remove("forge-table-ready");
    store.delete(wrap);
  }

  function reset(wrap) { teardown(wrap); enhance(wrap); }

  function scan(scope) {
    (scope || document).querySelectorAll("[data-forge-table]").forEach(enhance);
  }

  function affected(node) {
    return node && node.closest ? node.closest("[data-forge-table]") : null;
  }

  // ---- arranque y eventos -------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () { scan(document); });

  // Resize: re-mide la altura conservando page/size/orden del usuario.
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      document.querySelectorAll("[data-forge-table].forge-table-ready").forEach(function (wrap) {
        var prev = store.get(wrap);
        if (!prev) return;
        var keep = { size: prev.size, page: prev.page, sort: prev.sort };
        teardown(wrap);
        enhance(wrap);
        var st = store.get(wrap);
        if (!st || !st.baseRows.length) return;
        st.size = keep.size;
        st.sort = keep.sort;
        if (st.select) st.select.value = keep.size;
        applySort(st);
        updateSortGlyphs(st);
        st.page = keep.page;
        render(st);
      });
    }, 140);
  });

  // HTMX: tras un swap que toque una tabla, reconstruimos (filas nuevas).
  if (document.body) {
    document.body.addEventListener("htmx:afterSwap", function (e) {
      var wrap = affected(e.target);
      if (wrap) reset(wrap);
      else scan(e.target);
    });
    document.body.addEventListener("htmx:oobAfterSwap", function (e) {
      var wrap = affected(e.target);
      if (wrap) reset(wrap);
    });
  }

  window.ForgeTable = { scan: scan, reset: reset, enhance: enhance, teardown: teardown };
})();
