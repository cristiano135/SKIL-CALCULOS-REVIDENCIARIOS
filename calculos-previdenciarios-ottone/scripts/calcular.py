#!/usr/bin/env python3
"""Cálculo previdenciário completo a partir de um caso JSON (CNIS + dados pessoais).

Uso:
    python calcular.py caso.json --xlsx Calculo_NOME.xlsx [--json resultado.json] [--sem-bcb]

O caso pode ter só o bloco de benefício (vínculos/remunerações), só a liquidação (RMI informada)
ou os dois. Veja assets/caso_modelo.json.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from motor import Series, Tabelas, avaliar_beneficio, d, d_fmt, liquidar  # noqa: E402
import planilha  # noqa: E402


def faixas(meses):
    """['2020-01','2020-02','2020-05'] -> '2020-01 a 2020-02, 2020-05'."""
    idx = sorted(int(m[:4]) * 12 + int(m[5:]) - 1 for m in meses)
    fmt = lambda i: f"{i // 12}-{i % 12 + 1:02d}"
    out, ini = [], None
    for j, i in enumerate(idx):
        ini = i if ini is None else ini
        if j + 1 == len(idx) or idx[j + 1] != i + 1:
            out.append(fmt(ini) if ini == i else f"{fmt(ini)} a {fmt(i)}")
            ini = None
    return ", ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caso")
    ap.add_argument("--xlsx")
    ap.add_argument("--json")
    ap.add_argument("--sem-bcb", action="store_true", help="não consultar a API do Banco Central")
    a = ap.parse_args()

    caso = json.loads(Path(a.caso).read_text(encoding="utf-8"))
    tab = Tabelas(caso.get("tabelas"))
    series = Series(caso.get("series"), usar_bcb=not a.sem_bcb)
    saida, avisos = {}, []

    ben = None
    if caso.get("vinculos"):
        ben = avaliar_beneficio(caso, tab, series)
        saida["beneficio"] = {k: v for k, v in ben.items() if k not in ("tempo_obj", "pbc")}
        saida["beneficio"]["qtd_salarios_pbc"] = len(ben["pbc"])

    liq = None
    b = caso.get("beneficio", {})
    if caso.get("liquidacao"):
        rmi, dib = b.get("rmi"), d(b.get("dib"))
        if rmi is None:
            if not ben:
                sys.exit("informe beneficio.rmi ou os vínculos/remunerações do CNIS")
            nome = b.get("regra") or ben["melhor_regra"]
            escolhida = next((x for x in ben["regras"] if nome and nome.lower() in x["regra"].lower() and x.get("rmi")), None)
            if not escolhida:
                sys.exit(f"regra '{nome}' sem RMI calculada")
            rmi, dib = escolhida["rmi"], dib or d(escolhida["dib"])
            avisos.append(f"RMI calculada pela regra '{escolhida['regra']}' (DIB {escolhida['dib']}); confira com a carta de concessão.")
        dib = dib or d(b.get("der"))
        if dib > d(caso["liquidacao"]["data_atualizacao"]):
            avisos.append(f"DIB {d_fmt(dib)} posterior à data da atualização: não há atrasados a liquidar.")
    if caso.get("liquidacao") and dib <= d(caso["liquidacao"]["data_atualizacao"]):
        liq = liquidar(caso, tab, series, float(rmi), dib)
        avisos += liq["avisos"]
        saida["liquidacao"] = {
            "dib": d_fmt(liq["dib"]), "rmi": liq["rmi"], "rma": liq["rma"], "prescricao": d_fmt(liq["prescricao"]),
            "diferencas": f"{d_fmt(liq['inicio'])} a {d_fmt(liq['fim'])}", "data_atualizacao": d_fmt(liq["atual"]),
            "totais": liq["totais"], "honorarios": liq["honorarios"], "valor_causa": liq["causa"], "ir": liq["ir"],
            "linhas": len(liq["linhas"]),
        }

    if series.faltantes:
        for nome, meses in sorted(series.faltantes.items()):
            avisos.insert(0, f"CÁLCULO INCOMPLETO: faltam índices de {nome.upper()} para {faixas(meses)} "
                             f"(informe em caso.series.{nome} no formato {{'AAAA-MM': percentual}})")
    avisos += sorted(tab.avisos)
    saida["avisos"] = avisos

    if a.xlsx:
        planilha.gerar(a.xlsx, caso, ben, liq, series, avisos)
        saida["planilha"] = a.xlsx
    txt = json.dumps(saida, ensure_ascii=False, indent=2, default=str)
    if a.json:
        Path(a.json).write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
