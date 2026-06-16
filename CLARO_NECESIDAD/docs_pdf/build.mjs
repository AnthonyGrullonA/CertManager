// Convierte cada .md de CLARO_NECESIDAD a PDF con la plantilla de marca.
// Usa markdown-it (render) + puppeteer-core con el Chrome del sistema (impresión).
// Los bloques ```mermaid se rasterizan a SVG vectorial embebido y se escalan
// para caber en la página; el ASCII de respaldo (nota "si tu visor…" + bloque)
// se omite en el PDF para no duplicar el diagrama.
// Uso:  node build.mjs              -> todos los .md
//       node build.mjs 06_arquitectura.md  -> solo ese documento
import MarkdownIt from "markdown-it";
import puppeteer from "puppeteer-core";
import { readFileSync, readdirSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const here = path.dirname(fileURLToPath(import.meta.url));
const parent = path.resolve(here, "..");
const CHROME =
  process.env.CHROME ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const mermaidPath = path.join(here, "node_modules/mermaid/dist/mermaid.min.js");
const css = readFileSync(path.join(here, "_template.css"), "utf8");
const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
const date = process.env.DOCDATE || "";

// Caja útil (px CSS) para escalar diagramas dentro de A4 con los márgenes de abajo.
const FIT_W = 690; // ancho de contenido (≈186mm)
const FIT_H = 760; // alto razonable que deja sitio a encabezado/texto

const footer = `<div style="font-size:8px;color:#9aa3ad;width:100%;padding:0 14mm;
  display:flex;justify-content:space-between;">
  <span>CertManager — Paquete de entrega v1.0.0 · Confidencial</span>
  <span>Pág. <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`;

function pageHtml(body) {
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><style>${css}</style></head>
<body><div class="doc-head"><span class="brand">CertManager &middot; Claro</span>
<span class="meta">Paquete de entrega v1.0.0${date ? " &middot; " + date : ""}<br>Confidencial — uso interno</span></div>
${body}</body></html>`;
}

// Saca los bloques mermaid (deja un token) y descarta la nota + ASCII de respaldo
// que los acompaña, para que en el PDF solo quede la imagen.
function extractMermaid(src) {
  const codes = [];
  let out = src.replace(/```mermaid\r?\n([\s\S]*?)```/g, (_, code) => {
    const i = codes.push(code.trim()) - 1;
    return `@@MERMAIDFIG${i}@@`;
  });
  out = out.replace(
    /(@@MERMAIDFIG\d+@@)\n+>[^\n]*(?:Mermaid|ASCII)[^\n]*\n+```[\s\S]*?```/g,
    "$1"
  );
  return { md: out, codes };
}

// Renderiza un diagrama mermaid a SVG con el Chrome del sistema.
async function renderMermaid(browser, code, id) {
  const pg = await browser.newPage();
  await pg.setContent("<!doctype html><html><body></body></html>", {
    waitUntil: "load",
  });
  await pg.addScriptTag({ path: mermaidPath });
  const svg = await pg.evaluate(
    async (def, gid) => {
      // saltos de línea en etiquetas: "\n" del .md -> <br/>
      const src = def.replace(/\\n/g, "<br/>");
      window.mermaid.initialize({
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "loose",
        flowchart: { htmlLabels: true, useMaxWidth: true },
      });
      const { svg } = await window.mermaid.render(gid, src);
      return svg;
    },
    code,
    id
  );
  await pg.close();
  return fitSvg(svg);
}

// Escala el SVG a la caja útil conservando proporción (vectorial: sin pixelar)
// y lo deja centrado. Toca solo la etiqueta <svg> raíz.
function fitSvg(svg) {
  const vb = svg.match(/viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"/i);
  let widthPx = FIT_W;
  if (vb) {
    const w = parseFloat(vb[1]);
    const h = parseFloat(vb[2]);
    widthPx = Math.round(w * Math.min(FIT_W / w, FIT_H / h));
  }
  return svg.replace(/<svg\b([^>]*)>/i, (_, attrs) => {
    const clean = attrs
      .replace(/\swidth="[^"]*"/i, "")
      .replace(/\sheight="[^"]*"/i, "")
      .replace(/\sstyle="[^"]*"/i, "");
    return `<svg${clean} width="${widthPx}" style="height:auto;max-width:100%;display:block;margin:0 auto;">`;
  });
}

let only = process.argv[2];
if (only && !only.endsWith(".md")) only += ".md";
const files = readdirSync(parent)
  .filter((f) => f.endsWith(".md"))
  .filter((f) => !only || f === only)
  .sort();

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--disable-gpu"],
});
for (const f of files) {
  const { md: src, codes } = extractMermaid(readFileSync(path.join(parent, f), "utf8"));
  const figs = [];
  for (let i = 0; i < codes.length; i++) {
    figs.push(await renderMermaid(browser, codes[i], `mmd-${i}`));
  }
  let body = md.render(src);
  body = body.replace(
    /<p>@@MERMAIDFIG(\d+)@@<\/p>/g,
    (_, i) =>
      `<figure style="margin:16px 0;text-align:center;break-inside:avoid;page-break-inside:avoid;">${figs[Number(i)]}</figure>`
  );
  body = body.replace(/@@MERMAIDFIG(\d+)@@/g, (_, i) => figs[Number(i)] || "");

  const pg = await browser.newPage();
  await pg.setContent(pageHtml(body), { waitUntil: "load" });
  await pg.pdf({
    path: path.join(here, f.replace(/\.md$/, ".pdf")),
    format: "A4",
    printBackground: true,
    margin: { top: "16mm", bottom: "16mm", left: "12mm", right: "12mm" },
    displayHeaderFooter: true,
    headerTemplate: "<div></div>",
    footerTemplate: footer,
  });
  await pg.close();
  console.log("   " + f.replace(/\.md$/, ".pdf") + (codes.length ? `  (${codes.length} diagrama/s)` : ""));
}
await browser.close();
console.log(">> Listo.");
