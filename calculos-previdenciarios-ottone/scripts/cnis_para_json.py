#!/usr/bin/env python3
"""Extrai do Extrato Previdenciário (CNIS / Meu INSS) os dados pessoais, vínculos e remunerações
e monta o esqueleto do caso JSON usado por calcular.py.

Uso:
    python cnis_para_json.py CNIS.pdf -o caso.json
    python cnis_para_json.py CNIS.txt -o caso.json      # texto já extraído do PDF

A leitura é "melhor esforço": o layout do CNIS varia. Sempre confira o resultado com o PDF —
principalmente datas de fim ausentes, vínculos concomitantes e períodos especiais (indicador IEAN).
"""
import argparse
import json
import re
import sys
from pathlib import Path

NIT = r"\d{3}\.\d{5}\.\d{2}-\d"
DATA = r"\d{2}/\d{2}/\d{4}"
COMP = r"\d{2}/\d{4}"
VALOR = r"\d{1,3}(?:\.\d{3})*,\d{2}"
TIPOS = ["Empregado Doméstico", "Empregado ou Agente Público", "Empregado", "Contribuinte Individual",
         "Recolhimento", "Facultativo", "Segurado Especial", "Trabalhador Avulso", "Benefício",
         "Agente Público", "Microempreendedor"]
INDICADORES_ESPECIAIS = ("IEAN",)
ALERTA_INDICADORES = {
    "PEXT": "vínculo/remuneração extemporânea (PEXT) — pode exigir prova para contar",
    "AEXT": "remuneração extemporânea — conferir",
    "PREC-MENOR-MIN": "recolhimento abaixo do mínimo — competência pode não contar para tempo/carência sem complementação",
    "IREC-LC123": "recolhimento plano simplificado (LC 123) — não conta para aposentadoria por tempo sem complementação",
    "PRPPS": "vínculo de regime próprio",
    "IEAN": "exposição a agente nocivo informada pelo empregador — avaliar tempo especial (PPP/LTCAT)",
}


def texto_do_pdf(caminho: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(caminho) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(caminho)).pages)
    except ImportError:
        sys.exit("instale pdfplumber ou pypdf (pip install pdfplumber)")


def num(v: str) -> float:
    return float(v.replace(".", "").replace(",", "."))


def fim_do_mes(comp: str) -> str:
    import calendar
    m, a = map(int, comp.split("/"))
    return f"{calendar.monthrange(a, m)[1]:02d}/{m:02d}/{a}"


def extrair(texto: str) -> dict:
    seg = {}
    if m := re.search(r"NIT:\s*(" + NIT + ")", texto):
        seg["nit"] = m.group(1)
    if m := re.search(r"CPF:\s*([\d.]{11,14}-\d{2})", texto):
        seg["cpf"] = m.group(1)
    if m := re.search(r"Nome:\s*([A-ZÀ-Ü' ]+?)(?:\s{2,}|\n|Data de nascimento|$)", texto):
        seg["nome"] = m.group(1).strip()
    if m := re.search(r"Data de nascimento:\s*(" + DATA + ")", texto, re.I):
        seg["nascimento"] = m.group(1)
    if m := re.search(r"Nome da m[ãa]e:\s*([A-ZÀ-Ü' ]+)", texto, re.I):
        seg["nome_mae"] = m.group(1).strip()
    seg.setdefault("sexo", "")

    vinculos, remuneracoes, alertas = [], [], []
    atual = None
    for linha in texto.splitlines():
        linha = linha.strip()
        m = re.match(r"^(\d{1,3})\s+(" + NIT + r")\s+(.*)$", linha)
        if m:
            seq, resto = int(m.group(1)), m.group(3)
            datas = re.findall(DATA, resto)
            tipo = next((t for t in TIPOS if t.lower() in resto.lower()), "")
            ini = datas[0] if datas else ""
            fim = datas[1] if len(datas) > 1 else ""
            corpo = re.split(DATA, resto)[0]
            if tipo:
                corpo = re.split(re.escape(tipo), corpo, flags=re.I)[0]
            corpo = re.sub(r"^[\d./-]+\s*", "", corpo).strip()   # código do empregador (CNPJ/CEI)
            inds = [i for i in ALERTA_INDICADORES if i in resto]
            atual = dict(seq=seq, empregador=corpo, tipo=tipo, inicio=ini, fim=fim,
                         especial=None, computar=True, carencia=tipo != "Benefício", indicadores=inds)
            if tipo == "Benefício":
                alertas.append(f"seq {seq}: benefício por incapacidade — só conta como tempo/carência se "
                               "intercalado com contribuições (Tema 1.125/STF); ajuste 'computar'/'carencia'.")
            for i in inds:
                alertas.append(f"seq {seq}: {ALERTA_INDICADORES[i]}")
            vinculos.append(atual)
            continue
        if atual is None:
            continue
        # contribuinte individual/facultativo: competência, data pgto, contribuição, salário de contribuição
        achou = False
        for c, _pg, _contrib, sal in re.findall(r"(" + COMP + r")\s+(" + DATA + r")\s+(" + VALOR + r")\s+(" + VALOR + ")", linha):
            remuneracoes.append(dict(seq=atual["seq"], competencia=c, valor=num(sal)))
            achou = True
        if achou:
            continue
        for c, v in re.findall(r"(?<![\d/])(" + COMP + r")\s+(" + VALOR + ")", linha):
            remuneracoes.append(dict(seq=atual["seq"], competencia=c, valor=num(v)))

    for v in vinculos:
        comps = sorted((r["competencia"] for r in remuneracoes if r["seq"] == v["seq"]),
                       key=lambda c: (c[3:], c[:2]))
        if not v["fim"]:
            if comps:
                v["fim"] = fim_do_mes(comps[-1])
                alertas.append(f"seq {v['seq']} ({v['empregador']}): sem data fim no CNIS — usado o fim da última "
                               f"remuneração ({v['fim']}). Confirme (CTPS, TRCT).")
            else:
                alertas.append(f"seq {v['seq']} ({v['empregador']}): sem data fim e sem remunerações — preencha.")
        if not v["inicio"]:
            alertas.append(f"seq {v['seq']}: data de início não lida — preencha.")
    if not seg.get("sexo"):
        alertas.append("informe segurado.sexo ('M' ou 'F') — o CNIS não traz esse dado.")

    return {
        "segurado": seg,
        "beneficio": {"especie": "", "nb": "", "der": "", "expectativa_sobrevida": None},
        "vinculos": vinculos,
        "remuneracoes": remuneracoes,
        "_alertas_cnis": alertas,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("-o", "--saida")
    a = ap.parse_args()
    p = Path(a.arquivo)
    texto = texto_do_pdf(p) if p.suffix.lower() == ".pdf" else p.read_text(encoding="utf-8")
    caso = extrair(texto)
    txt = json.dumps(caso, ensure_ascii=False, indent=2)
    if a.saida:
        Path(a.saida).write_text(txt, encoding="utf-8")
    print(f"{len(caso['vinculos'])} vínculos, {len(caso['remuneracoes'])} remunerações", file=sys.stderr)
    for al in caso["_alertas_cnis"]:
        print("ALERTA:", al, file=sys.stderr)
    if not a.saida:
        print(txt)


if __name__ == "__main__":
    main()
