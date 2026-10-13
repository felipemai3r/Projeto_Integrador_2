#!/usr/bin/env bash
# Gera assets/farol.css (arquivo único) a partir de assets/tokens/*.css.
# Uso: bash .claude/skills/farol-system/scripts/build.sh
set -euo pipefail
cd "$(dirname "$0")/../assets"
{
  echo "/* Farol DS — build agregado. GERADO a partir de tokens/*.css. Não editar. */"
  for f in color risk typography spacing shape elevation motion grid iconography; do
    echo; cat "tokens/$f.css"
  done
  echo
  cat <<'BASE'
/* ---------- Base mínima ---------- */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--fa-color-surface-base);
  color: var(--fa-color-content-primary);
  font: var(--fa-type-texto-md-weight) var(--fa-type-texto-md-size)/var(--fa-type-texto-md-line-height) var(--fa-font-family-base);
}
:focus-visible {
  outline: 3px solid var(--fa-color-state-focus-ring);
  outline-offset: 2px;
}
BASE
} > farol.css
echo "farol.css gerado: $(wc -c < farol.css) bytes"
