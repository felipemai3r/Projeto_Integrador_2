#!/usr/bin/env python3
"""Verifica WCAG AA dos pares texto/fundo declarados nos tokens do Farol DS.
Uso: python3 .claude/skills/farol-system/scripts/verificar-contraste.py
Sai com código 1 se algum par falhar."""
import re, sys, pathlib

base = pathlib.Path(__file__).resolve().parent.parent / "assets" / "tokens"
css = (base / "color.css").read_text() + (base / "risk.css").read_text()

def blocos():
    # separa os blocos por seletor; ignora @media (duplicata do modo noite)
    css_sem_media = re.sub(r"@media[^{]*\{.*?\n\}\n", "", css, flags=re.S)
    partes = re.split(r"(:root\[data-theme=\"dark\"\],\s*:root\.dark|:root)\s*\{", css_sem_media)
    out = {"dia": {}, "noite": {}}
    for i in range(1, len(partes), 2):
        modo = "noite" if "dark" in partes[i] else "dia"
        corpo = partes[i + 1].split("\n}")[0]
        for nome, valor in re.findall(r"(--fa-[\w-]+):\s*([^;]+);", corpo):
            out[modo][nome] = valor.strip()
    return out

B = blocos()

def resolve(modo, nome, prof=0):
    tabela = dict(B["dia"]); tabela.update(B[modo] if modo == "noite" else {})
    v = tabela[nome]
    m = re.fullmatch(r"var\((--fa-[\w-]+)\)", v)
    if m and prof < 8: return resolve(modo, m.group(1), prof + 1)
    return v

def lum(hx):
    c = [int(hx[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]

def cr(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)

pares = []  # (descrição, fg, bg, mínimo)
for modo in ("dia", "noite"):
    for fundo in ("surface-base", "surface-subtle"):
        for texto in ("primary", "secondary", "tertiary", "link"):
            pares.append((f"{modo}: content-{texto} sobre {fundo}", f"--fa-color-content-{texto}", f"--fa-color-{fundo}", 4.5, modo))
    pares.append((f"{modo}: action-on sobre action-primary", "--fa-color-action-on", "--fa-color-action-primary", 4.5, modo))
    pares.append((f"{modo}: accent-on sobre accent", "--fa-color-accent-on", "--fa-color-accent", 4.5, modo))
    pares.append((f"{modo}: border-strong sobre surface-base (3:1)", "--fa-color-border-strong", "--fa-color-surface-base", 3.0, modo))
    pares.append((f"{modo}: focus-ring sobre surface-base (3:1)", "--fa-color-state-focus-ring", "--fa-color-surface-base", 3.0, modo))
    for f in ("info", "success", "warning", "danger"):
        pares.append((f"{modo}: feedback-{f} content sobre surface", f"--fa-color-feedback-{f}-content", f"--fa-color-feedback-{f}-surface", 4.5, modo))
        pares.append((f"{modo}: feedback-{f} border sobre surface (3:1)", f"--fa-color-feedback-{f}-border", f"--fa-color-feedback-{f}-surface", 3.0, modo))
    for r in ("normal", "observacao", "atencao", "alerta", "desatualizado", "indisponivel"):
        pares.append((f"{modo}: risco {r} on-solid sobre solid", f"--fa-risk-{r}-on-solid", f"--fa-risk-{r}-solid", 4.5, modo))
        pares.append((f"{modo}: risco {r} content sobre surface", f"--fa-risk-{r}-content", f"--fa-risk-{r}-surface", 4.5, modo))
        pares.append((f"{modo}: risco {r} border sobre surface (3:1)", f"--fa-risk-{r}-border", f"--fa-risk-{r}-surface", 3.0, modo))
    pares.append((f"{modo}: marca, texto sobre surface-brand", "--fa-color-content-on-brand", "--fa-color-surface-brand", 4.5, modo))

falhas = 0
for desc, fg, bg, minimo, modo in pares:
    r = cr(resolve(modo, fg), resolve(modo, bg))
    ok = r >= minimo
    falhas += not ok
    if not ok:
        print(f"FALHA {r:5.2f} < {minimo}  {desc}")
print(f"{len(pares)} pares verificados, {falhas} falha(s)")
sys.exit(1 if falhas else 0)
