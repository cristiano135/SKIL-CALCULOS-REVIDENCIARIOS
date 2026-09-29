"""Teste de regressão: o motor deve reproduzir, linha a linha, o cálculo-modelo em PDF."""
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "scripts"))
from motor import Series, Tabelas, d, liquidar, truncn  # noqa: E402

caso = json.loads((AQUI / "caso_modelo_pdf.json").read_text(encoding="utf-8"))
esperado = json.loads((AQUI / "esperado_modelo_pdf.json").read_text(encoding="utf-8"))
liq = liquidar(caso, Tabelas(), Series(usar_bcb=False), caso["beneficio"]["rmi"], d(caso["beneficio"]["dib"]))
campos = {"beneficio": "beneficio", "diferenca": "diferenca", "indice": "indice", "atualizado": "atualizado",
          "juros_pct": "juros_pct", "juros": "juros", "atual_juros": "atual_juros", "selic_pct": "selic_pct",
          "selic": "selic", "total": "total"}
assert len(liq["linhas"]) == len(esperado), (len(liq["linhas"]), len(esperado))
erros = 0
for ln, e in zip(liq["linhas"], esperado):
    rot = ln["rotulo"] if ln["tipo"] == "mensal" else "13º " + e["comp"].split()[-1]
    for a, b in campos.items():
        obtido = truncn(ln[a], 6) if a == "indice" else ln[a]  # o PDF exibe o índice truncado
        if abs(obtido - e[b]) > (5e-7 if a == "indice" else 0.005):
            erros += 1
            print(f"{e['comp']:>12} {a}: obtido {obtido} esperado {e[b]}")
t = liq["totais"]
for k, v in {"principal": 334593.58, "base_atualizada": 347282.58, "juros": 97364.17, "total": 444646.75,
             "total_geral": 489111.43}.items():
    if abs(t[k] - v) > 0.005:
        erros += 1
        print(f"total {k}: obtido {t[k]} esperado {v}")
assert liq["honorarios"]["total"] == 44464.68
assert liq["causa"]["total_geral_em_sm"] == 322.21
assert liq["ir"] == {"anteriores": [433036.39, 69], "atual": [11610.36, 2]}
print("OK" if not erros else f"{erros} divergências")
sys.exit(1 if erros else 0)
