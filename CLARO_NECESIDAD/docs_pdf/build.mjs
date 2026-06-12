// Convierte cada .md de CLARO_NECESIDAD a PDF con la plantilla de marca.
// Usa markdown-it (render) + puppeteer-core con el Chrome del sistema (impresión).
import MarkdownIt from "markdown-it";
import puppeteer from "puppeteer-core";
import { readFileSync, writeFileSync, readdirSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const here = path.dirname(fileURLToPath(import.meta.url));
const parent = path.resolve(here, "..");
const CHROME =
  process.env.CHROME ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const css = readFileSync(path.join(here, "_template.css"), "utf8");
const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
const date = process.env.DOCDATE || "";

const footer = `<div style="font-size:8px;color:#9aa3ad;width:100%;padding:0 14mm;
  display:flex;justify-content:space-between;">
  <span>CertManager — Paquete de entrega v1.0.0 · Confidencial</span>
  <span>Pág. <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`;

function page(body) {
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><style>${css}</style></head>
<body><div class="doc-head"><span class="brand">CertManager &middot; Claro</span>
<span class="meta">Paquete de entrega v1.0.0${date ? " &middot; " + date : ""}<br>Confidencial — uso interno</span></div>
${body}</body></html>`;
}

const files = readdirSync(parent).filter((f) => f.endsWith(".md")).sort();
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--disable-gpu"],
});
for (const f of files) {
  const html = page(md.render(readFileSync(path.join(parent, f), "utf8")));
  const pg = await browser.newPage();
  await pg.setContent(html, { waitUntil: "load" });
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
  console.log("   " + f.replace(/\.md$/, ".pdf"));
}
await browser.close();
console.log(">> Listo.");
