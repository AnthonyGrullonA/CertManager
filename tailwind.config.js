/** @type {import('tailwindcss').Config} */
module.exports = {
  // Forge UI: base neutral + acentos por estado de certificado.
  // El chrome se entrega solo en claro; dark vive a nivel de tokens.
  // Unificado a data-theme (el riesgo de doble dark mode .dark vs [data-theme]
  // queda resuelto: una sola estrategia).
  darkMode: ["selector", '[data-theme="dark"]'],
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
  ],
  // Clases construidas dinámicamente en plantillas (badge--{{ status|lower }}).
  safelist: [
    // Estados de certificado (nombres en español).
    "badge--vigente",
    "badge--por_vencer",
    "badge--critico",
    "badge--vencido",
    "badge--error",
    "badge--sin_chequear",
    // Familias de severidad Forge (alertas usan badge--{{ family }} dinámico).
    "badge--ok",
    "badge--warn",
    "badge--crit",
    "badge--exp",
    "badge--err",
    "badge--none",
    // Tamaños de badge.
    "badge--sm",
    "badge--md",
    "badge--lg",
    // Aplicada desde Python (widget Select del panel Organización); no aparece
    // literal en plantillas, así que el safelist evita que el purgador la borre.
    "forge-select",
    // Aplicada desde Python a selects compactos de Settings.
    "settings-select-compact",
  ],
  theme: {
    extend: {
      // Mapeo de tokens del design system (variables CSS de tokens/colors.css,
      // typography.css, spacing.css, elevation.css). Permite usar utilidades
      // Tailwind (bg-surface-card, text-status-ok-fg, rounded-md, shadow-sm...)
      // resueltas a las custom properties → temables por data-theme.
      colors: {
        surface: {
          page: "var(--surface-page)",
          card: "var(--surface-card)",
          raised: "var(--surface-raised)",
          sunken: "var(--surface-sunken)",
          inverse: "var(--surface-inverse)",
          hover: "var(--surface-hover)",
          active: "var(--surface-active)",
        },
        border: {
          subtle: "var(--border-subtle)",
          DEFAULT: "var(--border-default)",
          strong: "var(--border-strong)",
        },
        content: {
          DEFAULT: "var(--text-primary)",
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
          disabled: "var(--text-disabled)",
          inverse: "var(--text-inverse)",
          link: "var(--text-link)",
          brand: "var(--text-brand)",
        },
        brand: {
          50: "var(--brand-50)",
          100: "var(--brand-100)",
          200: "var(--brand-200)",
          300: "var(--brand-300)",
          400: "var(--brand-400)",
          500: "var(--brand-500)",
          600: "var(--brand-600)",
          700: "var(--brand-700)",
          800: "var(--brand-800)",
          900: "var(--brand-900)",
          DEFAULT: "var(--action-primary)",
        },
        status: {
          // ok · warn · crit · exp · err · none (familias semánticas)
          ok: {
            bg: "var(--status-ok-bg)",
            "bg-soft": "var(--status-ok-bg-soft)",
            border: "var(--status-ok-border)",
            solid: "var(--status-ok-solid)",
            fg: "var(--status-ok-fg)",
          },
          warn: {
            bg: "var(--status-warn-bg)",
            "bg-soft": "var(--status-warn-bg-soft)",
            border: "var(--status-warn-border)",
            solid: "var(--status-warn-solid)",
            fg: "var(--status-warn-fg)",
          },
          crit: {
            bg: "var(--status-crit-bg)",
            "bg-soft": "var(--status-crit-bg-soft)",
            border: "var(--status-crit-border)",
            solid: "var(--status-crit-solid)",
            fg: "var(--status-crit-fg)",
          },
          exp: {
            bg: "var(--status-exp-bg)",
            "bg-soft": "var(--status-exp-bg-soft)",
            border: "var(--status-exp-border)",
            solid: "var(--status-exp-solid)",
            fg: "var(--status-exp-fg)",
          },
          err: {
            bg: "var(--status-err-bg)",
            "bg-soft": "var(--status-err-bg-soft)",
            border: "var(--status-err-border)",
            solid: "var(--status-err-solid)",
            fg: "var(--status-err-fg)",
          },
          none: {
            bg: "var(--status-none-bg)",
            "bg-soft": "var(--status-none-bg-soft)",
            border: "var(--status-none-border)",
            solid: "var(--status-none-solid)",
            fg: "var(--status-none-fg)",
          },
        },
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        pill: "var(--radius-pill)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
        inset: "var(--shadow-inset)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
    },
  },
  plugins: [],
};
