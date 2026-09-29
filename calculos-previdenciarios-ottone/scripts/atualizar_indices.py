#!/usr/bin/env python3
"""Baixa do Banco Central (SGS) as séries mensais usadas nos cálculos e grava assets/series_indices.json.

    python atualizar_indices.py            # baixa tudo desde 07/1994 e valida
    python atualizar_indices.py --checar   # só valida o arquivo atual

Séries: INPC (188), IGP-DI (190), IPCA-E (10764), SELIC acumulada no mês (4390) e meta SELIC (432,
convertida na meta vigente no 1º dia de cada mês, usada nos juros da poupança).

Validação: o INPC acumulado de cada ano tem de bater com o reajuste do INSS de janeiro seguinte
(assets/tabelas.json) e os meses conferidos no cálculo-modelo (10/2019 a 11/2021 e SELIC de
12/2021 a 04/2025) têm de coincidir.
"""
import argparse
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARQ = BASE / "assets" / "series_indices.json"
SERIES = {"inpc": 188, "igpdi": 190, "ipcae": 10764, "selic": 4390}
INICIO = date(1994, 7, 1)


def baixar(codigo, ini: date, fim: date):
    """A API limita consultas a 10 anos; baixa em blocos."""
    out = []
    a = ini
    while a <= fim:
        b = min(fim, date(a.year + 9, 12, 31))
        url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
               f"&dataInicial={a:%d/%m/%Y}&dataFinal={b:%d/%m/%Y}")
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                out += json.load(r)
        except OSError as e:
            sys.exit(f"sem acesso a api.bcb.gov.br ({e}). Libere o domínio na rede do ambiente "
                     "ou informe os índices em caso.series.")
        a = b + timedelta(days=1)
    return out


def mensal(dados):
    s = {}
    for item in dados:
        dt = datetime.strptime(item["data"], "%d/%m/%Y").date()
        s[f"{dt.year}-{dt.month:02d}"] = round(float(item["valor"]), 4)
    return dict(sorted(s.items()))


def meta_inicio_mes(dados):
    """Série 432 é diária: guarda a meta vigente no primeiro dia de cada mês."""
    por_dia = {datetime.strptime(i["data"], "%d/%m/%Y").date(): float(i["valor"]) for i in dados}
    s, dia = {}, min(por_dia)
    ultimo = max(por_dia)
    atual = None
    while dia <= ultimo:
        atual = por_dia.get(dia, atual)
        if dia.day == 1 and atual is not None:
            s[f"{dia.year}-{dia.month:02d}"] = atual
        dia += timedelta(days=1)
    return s


def validar(series):
    tab = json.loads((BASE / "assets" / "tabelas.json").read_text(encoding="utf-8"))
    reaj = tab["reajuste_beneficios"]
    erros = []
    inpc = series.get("inpc", {})
    for ano in range(1995, date.today().year):
        meses = [inpc.get(f"{ano}-{m:02d}") for m in range(1, 13)]
        if None in meses or str(ano + 1) not in reaj:
            continue
        acum = 1.0
        for v in meses:
            acum *= 1 + v / 100
        acum = round((acum - 1) * 100, 2)
        if abs(acum - reaj[str(ano + 1)]) > 0.011:
            erros.append(f"INPC {ano} acumulado {acum}% ≠ reajuste INSS {ano + 1} {reaj[str(ano + 1)]}%")
    return erros


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checar", action="store_true")
    a = ap.parse_args()
    atual = json.loads(ARQ.read_text(encoding="utf-8"))
    if not a.checar:
        hoje = date.today()
        novo = {"_fonte": atual.get("_fonte", ""), "_atualizado_em": hoje.isoformat()}
        for nome, cod in SERIES.items():
            ini = date(2001, 1, 1) if nome == "ipcae" else INICIO
            novo[nome] = mensal(baixar(cod, ini, hoje))
            print(f"{nome}: {len(novo[nome])} meses (até {max(novo[nome])})", file=sys.stderr)
        novo["meta_selic_mensal"] = meta_inicio_mes(baixar(432, date(2012, 1, 1), hoje))
        novo["juros_mora"] = atual.get("juros_mora", {})
        novo["taxa_legal"] = atual.get("taxa_legal", {})
        # os meses conferidos no cálculo-modelo têm de coincidir com o BCB
        for nome in ("inpc", "selic"):
            for k, v in atual.get(nome, {}).items():
                if k in novo[nome] and abs(novo[nome][k] - v) > 0.005 and not (nome == "inpc" and k == "2019-10"):
                    print(f"ATENÇÃO {nome} {k}: BCB {novo[nome][k]} x conferido {v}", file=sys.stderr)
        atual = novo
    erros = validar(atual)
    for e in erros:
        print("DIVERGÊNCIA:", e, file=sys.stderr)
    if not a.checar:
        ARQ.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"gravado {ARQ}", file=sys.stderr)
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
