module.exports = {
  plugins: {
    // Inlinea los @import (tokens/fuentes) antes de que Tailwind procese el CSS.
    "postcss-import": {},
    tailwindcss: {},
    autoprefixer: {},
  },
};
