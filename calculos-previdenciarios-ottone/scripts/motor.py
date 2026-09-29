"""Motor de cálculo previdenciário (Cristiano Ottone Advocacia).

Três blocos, todos alimentados pelo mesmo caso JSON (extrato CNIS + dados pessoais):
  1. tempo de contribuição e carência (com conversão de tempo especial até 13/11/2019);
  2. regras de aposentadoria (direito adquirido, transições da EC 103/2019, regra permanente) e RMI;
  3. liquidação dos atrasados no modelo do escritório, com correção e juros do
     Manual de Cálculos da Justiça Federal (Res. CJF 267/2013, 658/2020, 784/2022, 963/2025 e 990/2026).

Os valores monetários seguem a convenção do modelo: benefícios truncados em centavos,
valores atualizados e juros arredondados (ROUND) em centavos.
"""
from __future__ import annotations

import calendar
import json
import math
import urllib.request
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
REFORMA = date(2019, 11, 13)          # publicação e vigência da EC 103/2019
FIM_POUPANCA = (2021, 11)             # último mês de INPC + juros de poupança (antes da EC 113/2021)
INICIO_SELIC = (2021, 12)             # EC 113/2021, art. 3º
FIM_SELIC = (2025, 8)                 # Tema 1.419/STF e EC 136/2025: SELIC isolada até 08/2025
INICIO_TAXA_LEGAL = (2025, 9)         # Manual CJF 2026 (Res. 990/2026): INPC + juros pela taxa legal


# --------------------------------------------------------------------------- utilidades

def d(texto) -> date | None:
    """Aceita 'DD/MM/AAAA', 'AAAA-MM-DD' ou date."""
    if texto in (None, ""):
        return None
    if isinstance(texto, date):
        return texto
    texto = str(texto).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"data inválida: {texto!r}")


def comp(texto) -> tuple[int, int]:
    """Competência 'MM/AAAA' ou 'AAAA-MM' -> (ano, mês)."""
    if isinstance(texto, tuple):
        return texto
    texto = str(texto).strip()
    if "/" in texto:
        m, a = texto.split("/")[-2:]
    else:
        a, m = texto.split("-")[:2]
    return int(a), int(m)


def c_fmt(c) -> str:
    return f"{c[1]:02d}/{c[0]}"


def c_key(c) -> str:
    return f"{c[0]}-{c[1]:02d}"


def c_add(c, n):
    i = c[0] * 12 + c[1] - 1 + n
    return i // 12, i % 12 + 1


def c_range(a, b):
    c = a
    while c <= b:
        yield c
        c = c_add(c, 1)


def c_of(dt: date):
    return dt.year, dt.month


def dias_no_mes(c) -> int:
    return calendar.monthrange(c[0], c[1])[1]


def ultimo_dia(c) -> date:
    return date(c[0], c[1], dias_no_mes(c))


def d_fmt(dt: date | None) -> str:
    return dt.strftime("%d/%m/%Y") if dt else ""


def trunc2(x) -> float:
    return float(Decimal(repr(x)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def round2(x) -> float:
    return float(Decimal(repr(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def roundn(x, n) -> float:
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def truncn(x, n) -> float:
    """Truncamento em n casas (a Tabela da Justiça Federal trunca o índice acumulado em 6 casas)."""
    return float(Decimal(repr(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_DOWN))


def menos_anos(dt: date, anos: int) -> date:
    try:
        return dt.replace(year=dt.year - anos)
    except ValueError:  # 29/02
        return dt.replace(year=dt.year - anos, day=28)


def ymd(inicio: date, fim_exclusivo: date):
    """Diferença civil em anos, meses e dias (fim exclusivo)."""
    y = fim_exclusivo.year - inicio.year
    m = fim_exclusivo.month - inicio.month
    dd = fim_exclusivo.day - inicio.day
    if dd < 0:
        m -= 1
        anterior = c_add(c_of(fim_exclusivo), -1)
        dd += dias_no_mes(anterior)
    if m < 0:
        y -= 1
        m += 12
    return y, m, dd


def dias360(inicio: date, fim_inclusivo: date) -> int:
    """Período em 'dias comerciais' (ano de 360, mês de 30), contagem inclusiva."""
    if fim_inclusivo < inicio:
        return 0
    y, m, dd = ymd(inicio, fim_inclusivo + timedelta(days=1))
    return y * 360 + m * 30 + dd


def amd(dias: float) -> str:
    dias = int(round(dias))
    return f"{dias // 360}a {dias % 360 // 30}m {dias % 30}d"


# --------------------------------------------------------------------------- tabelas e séries

def carregar_json(nome):
    with open(BASE / "assets" / nome, encoding="utf-8") as f:
        return json.load(f)


class Tabelas:
    def __init__(self, extra: dict | None = None):
        self.t = carregar_json("tabelas.json")
        for k, v in (extra or {}).items():
            if not k.startswith("_"):
                self.t.setdefault(k, {}).update(v)
        self.avisos: set[str] = set()

    def _vigente(self, nome, c):
        chaves = sorted(k for k in self.t[nome] if not k.startswith("_") and k <= c_key(c))
        if not chaves:
            raise KeyError(f"tabela {nome} sem valor para {c_fmt(c)}")
        k = chaves[-1]
        if f"{nome}:{k}" in self.t.get("_nao_conferidos", []):
            self.avisos.add(f"{nome} de {k} ({self.t[nome][k]}) não foi conferido na fonte oficial")
        return self.t[nome][k]

    def salario_minimo(self, c):
        return self._vigente("salario_minimo", c)

    def teto(self, c):
        try:
            return self._vigente("teto", c)
        except KeyError:
            return None

    def reajuste(self, ano):
        v = self.t["reajuste_beneficios"].get(str(ano))
        if v is not None and f"reajuste_beneficios:{ano}" in self.t.get("_nao_conferidos", []):
            self.avisos.add(f"reajuste de {ano} ({v}%) não foi conferido na fonte oficial")
        return v

    def calendario_13(self, ano):
        cal = self.t["calendario_13"]
        return cal.get(str(ano), cal["padrao"])


SGS = {"inpc": 188, "igpdi": 190, "ipcae": 10764, "selic": 4390, "meta_selic": 432}


class Series:
    """Séries mensais em % (INPC, IGP-DI, IPCA-E, SELIC, juros de mora, taxa legal).

    Ordem de precedência: valores do caso > cache do skill (assets/series_indices.json) > API do BCB.
    """

    def __init__(self, do_caso: dict | None = None, usar_bcb=True):
        cache = carregar_json("series_indices.json")
        self.s = {k: dict(v) for k, v in cache.items() if not k.startswith("_")}
        for k, v in (do_caso or {}).items():
            if k.startswith("_"):
                continue
            self.s.setdefault(k, {}).update({c_key(comp(m)): float(x) for m, x in v.items()})
        self.usar_bcb = usar_bcb
        self.faltantes: dict[str, set] = {}
        self.baixadas: set[str] = set()
        self.usadas: dict[str, dict] = {}

    def _bcb(self, nome, a, b):
        if not self.usar_bcb or nome in self.baixadas or nome not in SGS:
            return
        self.baixadas.add(nome)
        url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{SGS[nome]}/dados?formato=json"
               f"&dataInicial=01/{a[1]:02d}/{a[0]}&dataFinal={dias_no_mes(b)}/{b[1]:02d}/{b[0]}")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                dados = json.load(r)
        except Exception:
            return
        serie = self.s.setdefault(nome, {})
        if nome == "meta_selic":  # diária: guarda a meta vigente no 1º dia de cada mês
            for item in dados:
                dt = d(item["data"])
                serie.setdefault(c_key(c_of(dt)) + "@" + str(dt.day), float(item["valor"]))
        else:
            for item in dados:
                dt = d(item["data"])
                serie.setdefault(c_key(c_of(dt)), float(item["valor"]))

    def get(self, nome, c, a_baixar=None):
        k = c_key(c)
        v = self.s.get(nome, {}).get(k)
        if v is None and a_baixar:
            self._bcb(nome, *a_baixar)
            v = self.s.get(nome, {}).get(k)
        if v is None:
            self.faltantes.setdefault(nome, set()).add(k)
            return 0.0
        self.usadas.setdefault(nome, {})[k] = v
        return v

    def meta_selic_inicio_mes(self, c, janela):
        k = c_key(c)
        if k in self.s.get("meta_selic_mensal", {}):
            return self.s["meta_selic_mensal"][k]
        self._bcb("meta_selic", *janela)
        dias = sorted((int(x.split("@")[1]), v) for x, v in self.s.get("meta_selic", {}).items()
                      if x.startswith(k + "@"))
        if dias:
            return dias[0][1]
        return None


def juros_mora_mes(series: Series, c, janela) -> float:
    """Juros de mora mensais (%) pelo Manual CJF para condenações previdenciárias até 11/2021.

    Até 06/2009: 1% a.m.; 07/2009 a 04/2012: 0,5% a.m. (Lei 11.960/2009);
    a partir de 05/2012: juros da poupança (Lei 12.703/2012): 0,5% a.m. se a meta SELIC > 8,5% a.a.,
    senão 70% da meta SELIC mensalizada.
    """
    k = c_key(c)
    if k in series.s.get("juros_mora", {}):
        series.usadas.setdefault("juros_mora", {})[k] = series.s["juros_mora"][k]
        return series.s["juros_mora"][k]
    if c < (2009, 7):
        v = 1.0
    elif c < (2012, 5):
        v = 0.5
    else:
        meta = series.meta_selic_inicio_mes(c, janela)
        if meta is None:
            series.faltantes.setdefault("juros_mora", set()).add(k)
            return 0.0
        v = 0.5 if meta > 8.5 else roundn(((1 + 0.7 * meta / 100) ** (1 / 12) - 1) * 100, 4)
    series.usadas.setdefault("juros_mora", {})[k] = v
    return v


def taxa_legal_mes(series: Series, c, janela) -> float:
    """Taxa legal mensal (%) a partir de 09/2025 (Manual CJF 2026): SELIC do mês menos INPC do mês,
    considerada zero quando negativa (art. 406, §§ 1º e 3º, do Código Civil, red. Lei 14.905/2024)."""
    k = c_key(c)
    if k in series.s.get("taxa_legal", {}):
        series.usadas.setdefault("taxa_legal", {})[k] = series.s["taxa_legal"][k]
        return series.s["taxa_legal"][k]
    selic = series.get("selic", c, janela)
    inpc = series.get("inpc", c, janela)
    v = roundn(max(0.0, selic - inpc), 4)
    series.usadas.setdefault("taxa_legal", {})[k] = v
    return v


def indice_correcao_nome(c, criterio="INPC"):
    """Índice de correção do Manual CJF para benefícios (tabela 'previdenciário')."""
    if criterio.upper().replace("-", "") == "IPCAE" and c >= (2001, 1):
        return "ipcae"
    if (1996, 5) <= c <= (2006, 8):
        return "igpdi"
    return "inpc"


# --------------------------------------------------------------------------- tempo de contribuição

FATORES = {  # conversão especial -> comum até 13/11/2019 (Decreto 3.048/99, art. 70)
    "M": {"15": 2.33, "20": 1.75, "25": 1.40},
    "F": {"15": 2.00, "20": 1.50, "25": 1.20},
}


class Tempo:
    def __init__(self, vinculos, sexo, projetar_de: date | None = None, projetar_ate: date | None = None):
        self.sexo = sexo
        dia_fator: dict[date, float] = {}
        dia_especial: dict[date, str] = {}
        self.meses_carencia: set = set()
        vs = [v for v in vinculos if v.get("computar", True)]
        if projetar_de and projetar_ate and projetar_ate >= projetar_de:
            vs = vs + [{"inicio": projetar_de, "fim": projetar_ate, "especial": None, "projecao": True}]
        for v in vs:
            ini, fim = d(v["inicio"]), d(v["fim"])
            esp = str(v["especial"]) if v.get("especial") else None
            fator = FATORES[sexo][esp] if esp else 1.0
            dia = ini
            while dia <= fim:
                if dia_fator.get(dia, 0) < fator:
                    dia_fator[dia] = fator
                if esp:
                    atual = dia_especial.get(dia)
                    if atual is None or int(esp) < int(atual):
                        dia_especial[dia] = esp
                dia += timedelta(days=1)
            if v.get("carencia", True):
                self.meses_carencia.update(c_range(c_of(ini), c_of(fim)))
        self.segmentos = self._segmentos(dia_fator)
        self.seg_especial = self._segmentos({k: 1.0 for k in dia_especial})
        tipos: dict[str, int] = {}
        for t in dia_especial.values():
            tipos[t] = tipos.get(t, 0) + 1
        self.tipo_especial = max(tipos, key=tipos.get) if tipos else None

    @staticmethod
    def _segmentos(mapa):
        segs = []
        for dia in sorted(mapa):
            f = mapa[dia] if dia <= REFORMA else 1.0
            if segs and segs[-1][1] + timedelta(days=1) == dia and segs[-1][2] == f:
                segs[-1][1] = dia
            else:
                segs.append([dia, dia, f])
        return segs

    @staticmethod
    def _soma(segs, ate: date, converter=True):
        total = 0.0
        for ini, fim, f in segs:
            if ini > ate:
                break
            dd = dias360(ini, min(fim, ate))
            total += dd * (f if converter else 1.0)
        return total

    def tc(self, ate: date, converter=True) -> float:
        """Tempo de contribuição até a data (dias comerciais)."""
        return self._soma(self.segmentos, ate, converter)

    def especial(self, ate: date) -> float:
        return self._soma(self.seg_especial, ate, False)

    def carencia(self, ate: date) -> int:
        return sum(1 for c in self.meses_carencia if c <= c_of(ate))


def completa_idade(nasc: date, em: date, anos: float) -> bool:
    """Idade mínima (anos, aceita frações de 6 meses) atingida na data do aniversário."""
    meses = round(anos * 12)
    c = c_add(c_of(nasc), meses)
    alvo = date(c[0], c[1], min(nasc.day, dias_no_mes(c)))
    return em >= alvo


def idade360(nasc: date, em: date) -> float:
    y, m, dd = ymd(nasc, em)
    return y * 360 + m * 30 + dd


# --------------------------------------------------------------------------- regras de aposentadoria

def _prog(ano, base, passo, teto, ano_base=2019):
    return min(teto, base + passo * max(0, ano - ano_base))


def regras(caso, tempo: Tempo, nasc: date):
    """Avalia cada regra numa data e devolve dicionário {cumpre, detalhes, coeficiente...}."""
    s = tempo.sexo
    H = s == "M"
    A = 360
    tc_reforma = tempo.tc(REFORMA)
    req_tc = (35 if H else 30) * A
    falta = max(0.0, req_tc - tc_reforma)

    def base(dt):
        return tempo.tc(dt), idade360(nasc, dt), tempo.carencia(dt)

    def coef_60(tc, limiar):
        return 60 + 2 * max(0, int(tc // A) - limiar)

    lim_h = 20 if H else 15
    out = []

    def r(nome, fundamento, teste, coef, media="100%", fator=False, so_ate_reforma=False):
        out.append(dict(nome=nome, fundamento=fundamento, teste=teste, coef=coef, media=media,
                        fator=fator, so_ate_reforma=so_ate_reforma))

    # Direito adquirido (requisitos até 13/11/2019)
    r("Direito adquirido - ATC (Lei 8.213/91, art. 52 e ss.)", "EC 103/2019, art. 3º",
      lambda dt: (lambda tc, id_, car: (tc >= req_tc and car >= 180,
                  f"TC {amd(tc)} (mín. {35 if H else 30}a); carência {car}/180"))(*base(min(dt, REFORMA))),
      lambda dt: 100, media="80% maiores", fator="se_pontos", so_ate_reforma=True)
    r("Direito adquirido - aposentadoria por idade", "EC 103/2019, art. 3º; Lei 8.213/91, art. 48",
      lambda dt: (lambda tc, id_, car: (completa_idade(nasc, min(dt, REFORMA), 65 if H else 60) and car >= 180,
                  f"idade {amd(id_)} (mín. {65 if H else 60}a); carência {car}/180"))(*base(min(dt, REFORMA))),
      lambda dt: min(100, 70 + tempo.carencia(min(dt, REFORMA)) // 12), media="80% maiores",
      fator="opcional", so_ate_reforma=True)
    if tempo.tipo_especial:
        t = int(tempo.tipo_especial)
        r(f"Direito adquirido - aposentadoria especial ({t} anos)", "EC 103/2019, art. 3º; Lei 8.213/91, art. 57",
          lambda dt: (lambda esp, car: (esp >= t * A and car >= 180,
                      f"tempo especial {amd(esp)} (mín. {t}a); carência {car}/180"))(
              tempo.especial(min(dt, REFORMA)), tempo.carencia(min(dt, REFORMA))),
          lambda dt: 100, media="80% maiores", so_ate_reforma=True)

    # Transições
    r("Transição - pontos", "EC 103/2019, art. 15",
      lambda dt: (lambda tc, id_, car, pts: (tc >= req_tc and (tc + id_) / A >= pts and car >= 180,
                  f"TC {amd(tc)}; pontos {(tc + id_) / A:.2f} (mín. {pts}); carência {car}/180"))(
          *base(dt), _prog(dt.year, 96 if H else 86, 1, 105 if H else 100)),
      lambda dt: coef_60(tempo.tc(dt), lim_h))
    r("Transição - idade mínima progressiva", "EC 103/2019, art. 16",
      lambda dt: (lambda tc, id_, car, idm: (tc >= req_tc and completa_idade(nasc, dt, idm) and car >= 180,
                  f"TC {amd(tc)}; idade {amd(id_)} (mín. {idm}); carência {car}/180"))(
          *base(dt), _prog(dt.year, 61 if H else 56, 0.5, 65 if H else 62)),
      lambda dt: coef_60(tempo.tc(dt), lim_h))
    r("Transição - pedágio 50%", "EC 103/2019, art. 17",
      lambda dt: (lambda tc, id_, car: (tc_reforma > req_tc - 2 * A and tc >= req_tc + falta / 2 and car >= 180,
                  f"TC em 13/11/2019 {amd(tc_reforma)} (precisa > {33 if H else 28}a); "
                  f"TC {amd(tc)} (mín. {amd(req_tc + falta / 2)}); carência {car}/180"))(*base(dt)),
      lambda dt: 100, fator=True)
    r("Transição - pedágio 100%", "EC 103/2019, art. 20",
      lambda dt: (lambda tc, id_, car: (completa_idade(nasc, dt, 60 if H else 57) and tc >= req_tc + falta and car >= 180,
                  f"idade {amd(id_)} (mín. {60 if H else 57}a); TC {amd(tc)} (mín. {amd(req_tc + falta)}); "
                  f"carência {car}/180"))(*base(dt)),
      lambda dt: 100)
    r("Transição - aposentadoria por idade", "EC 103/2019, art. 18",
      lambda dt: (lambda tc, id_, car, idm: (completa_idade(nasc, dt, idm) and tc >= 15 * A and car >= 180,
                  f"idade {amd(id_)} (mín. {idm}); TC {amd(tc)} (mín. 15a); carência {car}/180"))(
          *base(dt), 65 if H else _prog(dt.year, 60, 0.5, 62)),
      lambda dt: coef_60(tempo.tc(dt), lim_h))
    if tempo.tipo_especial:
        t = int(tempo.tipo_especial)
        pts = {15: 66, 20: 76, 25: 86}[t]
        lim_esp = 15 if (t == 15 or not H) else 20
        r(f"Transição - aposentadoria especial ({t} anos)", "EC 103/2019, art. 21",
          lambda dt: (lambda esp, tc, id_, car: (esp >= t * A and (tc + id_) / A >= pts and car >= 180,
                      f"tempo especial {amd(esp)} (mín. {t}a); pontos {(tc + id_) / A:.2f} (mín. {pts}); "
                      f"carência {car}/180"))(
              tempo.especial(dt), tempo.tc(dt, converter=False), idade360(nasc, dt), tempo.carencia(dt)),
          lambda dt: coef_60(tempo.tc(dt), lim_esp))
    r("Regra permanente (programada)", "EC 103/2019, art. 19",
      lambda dt: (lambda tc, id_, car: (completa_idade(nasc, dt, 65 if H else 62) and tc >= (20 if H else 15) * A and car >= 180,
                  f"idade {amd(id_)} (mín. {65 if H else 62}a); TC {amd(tc)} (mín. {20 if H else 15}a); "
                  f"carência {car}/180"))(*base(dt)),
      lambda dt: coef_60(tempo.tc(dt), lim_h))
    return out


def fator_previdenciario(tc_anos, idade_anos, es, sexo):
    a = 0.31
    tc = tc_anos + (5 if sexo == "F" else 0)
    return roundn((tc * a / es) * (1 + (idade_anos + tc * a) / 100), 4)


def salarios_pbc(caso, tab: Tabelas, series: Series, dib: date, ate_comp=None):
    """Salários de contribuição do PBC (07/1994 até o mês anterior à DIB), somados por competência,
    limitados ao teto e corrigidos até o mês anterior à DIB."""
    fim = ate_comp or c_add(c_of(dib), -1)
    por_comp: dict = {}
    corrigidos: dict = {}
    for r_ in caso.get("remuneracoes", []):
        c = comp(r_["competencia"])
        if (1994, 7) <= c <= fim:
            por_comp[c] = por_comp.get(c, 0.0) + float(r_["valor"])
            if r_.get("valor_corrigido") is not None:
                corrigidos[c] = corrigidos.get(c, 0.0) + float(r_["valor_corrigido"])
    # DIB projetada no futuro: corrige só até o mês anterior ao atual (RMI a valores de hoje)
    fim_corr = min(c_add(c_of(dib), -1), c_add(c_of(date.today()), -1))
    janela = ((1994, 7), fim_corr)
    linhas = []
    for c in sorted(por_comp):
        valor = por_comp[c]
        teto = tab.teto(c)
        limitado = min(valor, teto) if teto else valor
        if c in corrigidos:
            fator, corr = None, corrigidos[c]
        else:
            fator = 1.0
            for k in c_range(c, fim_corr):
                fator *= 1 + series.get(indice_correcao_nome(k), k, janela) / 100
            fator = roundn(fator, 6)
            corr = round2(limitado * fator)
        linhas.append(dict(competencia=c_fmt(c), valor=valor, teto=teto, limitado=limitado, fator=fator,
                           corrigido=corr))
    return linhas


def media(linhas, criterio):
    vals = sorted((x["corrigido"] for x in linhas), reverse=True)
    if not vals:
        return 0.0, 0
    if criterio == "80% maiores":
        n = max(1, int(len(vals) * 0.8))
        vals = vals[:n]
    return round2(sum(vals) / len(vals)), len(vals)


def avaliar_beneficio(caso, tab: Tabelas, series: Series):
    seg = caso["segurado"]
    nasc, sexo = d(seg["nascimento"]), seg["sexo"].upper()[0]
    ben = caso.get("beneficio", {})
    der = d(ben.get("der") or ben.get("dib"))
    vinculos = caso.get("vinculos", [])
    ultimo_fim = max((d(v["fim"]) for v in vinculos if v.get("computar", True)), default=der)
    proj_ini = max(ultimo_fim, der) + timedelta(days=1)
    limite = max(der, nasc.replace(year=nasc.year + 70))
    tempo_real = Tempo(vinculos, sexo)
    tempo_proj = Tempo(vinculos, sexo, proj_ini, limite) if caso.get("opcoes", {}).get("projetar", True) else tempo_real

    resultado = {
        "der": d_fmt(der),
        "tempo_ate_der": amd(tempo_real.tc(der)),
        "tempo_ate_reforma": amd(tempo_real.tc(REFORMA)),
        "tempo_sem_conversao_der": amd(tempo_real.tc(der, converter=False)),
        "tempo_especial_der": amd(tempo_real.especial(der)),
        "carencia_der": tempo_real.carencia(der),
        "idade_der": amd(idade360(nasc, der)),
        "regras": [],
    }
    es = caso.get("beneficio", {}).get("expectativa_sobrevida")
    for regra in regras(caso, tempo_real, nasc):
        ok, det = regra["teste"](der)
        data_ok = der if ok else None
        det_ok = det
        if not ok and not regra["so_ate_reforma"]:
            rp = [x for x in regras(caso, tempo_proj, nasc) if x["nome"] == regra["nome"]][0]
            dia = max(der, REFORMA)
            while dia <= limite:
                ok2, det2 = rp["teste"](dia)
                if ok2:
                    data_ok, det_ok = dia, det2
                    break
                dia += timedelta(days=1)
        item = dict(regra=regra["nome"], fundamento=regra["fundamento"], cumpre_na_der=ok,
                    data_cumprimento=d_fmt(data_ok), requisitos_na_der=det, requisitos_na_data=det_ok)
        if data_ok:
            dib = data_ok
            t = tempo_real if dib <= der else tempo_proj
            ate_comp = c_add(c_of(REFORMA), -1) if regra["so_ate_reforma"] else None
            linhas = salarios_pbc(caso, tab, series, dib, ate_comp)
            med, n = media(linhas, regra["media"])
            coef = regra["coef"](dib)
            tc_anos = t.tc(dib if not regra["so_ate_reforma"] else REFORMA) / 360
            id_anos = idade360(nasc, dib if not regra["so_ate_reforma"] else REFORMA) / 360
            f = None
            if regra["fator"]:
                if es:
                    f = fator_previdenciario(tc_anos, id_anos, float(es), sexo)
                    if regra["fator"] == "se_pontos":
                        pts_ok = tc_anos + id_anos >= (96 if sexo == "M" else 86)
                        f = max(f, 1.0) if pts_ok else f
                    elif regra["fator"] == "opcional":
                        f = max(f, 1.0)
                else:
                    item["aviso"] = "fator previdenciário pendente: informe beneficio.expectativa_sobrevida (tábua IBGE)"
            sb = round2(med * (f if f else 1.0))
            rmi = round2(sb * coef / 100)
            sm, teto = tab.salario_minimo(c_of(dib)), tab.teto(c_of(dib))
            rmi = max(sm, min(teto, rmi) if teto else rmi)
            item.update(dib=d_fmt(dib), media=med, qtd_salarios=n, criterio_media=regra["media"],
                        coeficiente=coef, fator_previdenciario=f, rmi=rmi,
                        reafirmacao_der=dib > der, projecao=dib > der)
        resultado["regras"].append(item)
    elegiveis = [x for x in resultado["regras"] if x.get("rmi") and x["cumpre_na_der"] and "aviso" not in x]
    if elegiveis:
        melhor = max(elegiveis, key=lambda x: x["rmi"])
    else:
        futuros = [x for x in resultado["regras"] if x.get("rmi")]
        melhor = min(futuros, key=lambda x: d(x["dib"])) if futuros else None
    resultado["melhor_regra"] = melhor["regra"] if melhor else None
    resultado["pbc"] = salarios_pbc(caso, tab, series, der)
    resultado["tempo_obj"] = tempo_real
    return resultado


def competencias_sem_salario(caso):
    rem = {(r_.get("seq"), comp(r_["competencia"])) for r_ in caso.get("remuneracoes", [])}
    rem_any = {c for _, c in rem}
    out = []
    for v in caso.get("vinculos", []):
        if not v.get("computar", True) or v.get("sem_remuneracoes"):
            continue
        for c in c_range(c_of(d(v["inicio"])), c_of(d(v["fim"]))):
            tem = (v.get("seq"), c) in rem if v.get("seq") is not None else c in rem_any
            if not tem:
                out.append(dict(competencia=c_fmt(c), empresa=v.get("empregador", ""),
                                data=d_fmt(date(c[0], c[1], 1))))
    return out


# --------------------------------------------------------------------------- liquidação (atrasados)

def fracao_mes(c, inicio: date, fim: date):
    """Fração do mês devida (mês comercial de 30 dias), como no modelo."""
    ini_d = inicio.day if c == c_of(inicio) else 1
    fim_d = 30 if (c != c_of(fim) or fim.day >= dias_no_mes(c)) else min(fim.day, 30)
    dias = max(0, fim_d - min(ini_d, 30) + 1)
    return min(1.0, dias / 30), dias


def liquidar(caso, tab: Tabelas, series: Series, rmi: float, dib: date):
    proc = caso.get("processo", {})
    liq = caso.get("liquidacao", {})
    atual = d(liq["data_atualizacao"])
    ajuiz = d(proc.get("ajuizamento")) or atual
    citacao = d(proc.get("citacao")) or ajuiz
    prescricao = max(dib, menos_anos(ajuiz, 5))
    inicio = d(liq.get("diferencas_desde")) or prescricao
    fim = d(liq.get("diferencas_ate")) or ultimo_dia(c_add(c_of(atual), -1))
    ult_indice = c_add(c_of(atual), -1)          # índices até o mês anterior à atualização
    janela = (c_add(c_of(dib), -1), ult_indice)
    criterio = liq.get("indice_correcao", "INPC")
    reaj_caso = {str(k): v for k, v in liq.get("reajustes", {}).items()}
    avisos = []

    # ---- evolução da renda mensal
    evol = []
    valor = rmi
    for c in c_range(c_of(dib), c_of(atual)):
        reaj = None
        if c[1] == 1 and c != c_of(dib):
            if str(c[0]) in reaj_caso:
                reaj = float(reaj_caso[str(c[0])])
            elif c[0] == dib.year + 1:  # primeiro reajuste proporcional: INPC do mês da DIB a dezembro
                f = 1.0
                for k in c_range(c_of(dib), (dib.year, 12)):
                    f *= 1 + series.get("inpc", k, janela) / 100
                reaj = roundn((f - 1) * 100, 2)
            else:
                reaj = tab.reajuste(c[0])
                if reaj is None:
                    avisos.append(f"reajuste de {c[0]} não cadastrado: informe liquidacao.reajustes")
                    reaj = 0.0
        teto, sm = tab.teto(c), tab.salario_minimo(c)
        anterior = valor
        mensal = trunc2(anterior * (1 + reaj / 100)) if reaj else anterior
        mensal = max(sm, min(teto, mensal) if teto else mensal)
        if inicio <= ultimo_dia(c) and date(c[0], c[1], 1) <= fim:
            frac, dias = fracao_mes(c, max(inicio, date(c[0], c[1], 1)), min(fim, ultimo_dia(c)))
        else:
            frac, dias = 1.0, 30
        evol.append(dict(c=c, competencia=c_fmt(c), anterior=anterior, reajuste=reaj, teto=teto, sm=sm,
                         mensal=mensal, fracao=frac, dias=dias, considerado=trunc2(mensal * frac)))
        valor = mensal
    ev = {e["c"]: e for e in evol}

    # ---- linhas de diferenças (mensais + 13º conforme calendário de pagamento do INSS)
    recebidos = {k: float(v) for k, v in liq.get("valores_recebidos", {}).items()}
    linhas = []
    c_ini, c_fim = c_of(inicio), c_of(fim)
    for c in c_range(c_ini, c_fim):
        e = ev[c]
        linhas.append(dict(tipo="mensal", c=c, rotulo=c_fmt(c), ref=c, beneficio=e["considerado"],
                           formula=("mes", c), recebido=recebidos.get(c_fmt(c), 0.0)))
        ano = c[0]
        p1, p2 = tab.calendario_13(ano)
        meses = [k for k in c_range(max(c_ini, (ano, 1)), min(c_fim, (ano, 12)))
                 if fracao_mes(k, max(inicio, date(k[0], k[1], 1)), min(fim, ultimo_dia(k)))[1] >= 15]
        n = len(meses)
        comeco_no_ano = c_ini > (ano, 1) and c_ini[0] == ano
        chave = f"13º {c_fmt(c)}"
        if comeco_no_ano and c_ini > (ano, p1):
            if c == (ano, 12) and n:
                linhas.append(dict(tipo="13", c=c, rotulo="13º", ref=c,
                                   beneficio=trunc2(ev[c]["mensal"] * n / 12), formula=("13u", c, n),
                                   recebido=recebidos.get(chave, 0.0)))
        else:
            if c == (ano, p1):
                linhas.append(dict(tipo="13", c=c, rotulo="13º", ref=c, beneficio=trunc2(ev[c]["mensal"] / 2),
                                   formula=("13a", c), recebido=recebidos.get(chave, 0.0)))
            elif c == (ano, p2) and (ano, p1) >= c_ini:
                v = trunc2(ev[c]["mensal"] * n / 12 - ev[(ano, p1)]["mensal"] / 2)
                linhas.append(dict(tipo="13", c=c, rotulo="13º", ref=c, beneficio=v,
                                   formula=("13b", c, n, (ano, p1)), recebido=recebidos.get(chave, 0.0)))

    # ---- índices por linha
    over = {k: v for k, v in liq.get("indices_por_competencia", {}).items()}
    fase_c = c_of(atual) > INICIO_TAXA_LEGAL
    cit_c = c_of(citacao)
    for ln in linhas:
        c = ln["c"]
        chave = ln["rotulo"] + ("" if ln["tipo"] == "mensal" else " " + c_fmt(c))
        # Fase A: correção (INPC/IGP-DI/IPCA-E) + juros de mora até 11/2021
        fim_a = min(FIM_POUPANCA, ult_indice)
        idx = 1.0
        for k in c_range(c, fim_a):
            taxa = series.get(indice_correcao_nome(k, criterio), k, janela)
            if k == c_ini and inicio.day > 1:
                taxa *= (dias_no_mes(k) - inicio.day + 1) / dias_no_mes(k)
            idx *= 1 + taxa / 100
        juros = sum(juros_mora_mes(series, k, janela) for k in c_range(max(c, cit_c), fim_a))
        # Fase B: SELIC simples de 12/2021 a 08/2025
        selic = sum(series.get("selic", k, janela)
                    for k in c_range(max(c, INICIO_SELIC), min(FIM_SELIC, ult_indice)))
        # Fase C: INPC + taxa legal a partir de 09/2025
        idx_c, tl = 1.0, 0.0
        if fase_c:
            for k in c_range(max(c, INICIO_TAXA_LEGAL), ult_indice):
                idx_c *= 1 + series.get(indice_correcao_nome(k, criterio), k, janela) / 100
            tl = sum(taxa_legal_mes(series, k, janela)
                     for k in c_range(max(c, INICIO_TAXA_LEGAL, cit_c), ult_indice))
        o = over.get(chave) or over.get(c_fmt(c) if ln["tipo"] == "mensal" else "")
        if o:
            idx = o.get("indice", idx)
            juros = o.get("juros", juros)
            selic = o.get("selic", selic)
            idx_c = o.get("indice_pos_09_2025", idx_c)
            tl = o.get("taxa_legal", tl)
        ln.update(indice=roundn(idx, 10), juros_pct=roundn(juros, 4), selic_pct=roundn(selic, 2),
                  indice_c=roundn(idx_c, 10), taxa_legal_pct=roundn(tl, 4))
        # valores (mesma fórmula da planilha)
        ln["diferenca"] = round2(ln["beneficio"] - ln["recebido"])
        ln["atualizado"] = round2(ln["diferenca"] * ln["indice"])
        ln["juros"] = round2(ln["atualizado"] * ln["juros_pct"] / 100)
        ln["atual_juros"] = round2(ln["atualizado"] + ln["juros"])
        ln["selic"] = round2(ln["atual_juros"] * ln["selic_pct"] / 100)
        ln["total_b"] = round2(ln["atual_juros"] + ln["selic"])
        ln["corrigido_c"] = round2(ln["total_b"] * ln["indice_c"])
        ln["juros_c"] = round2(ln["corrigido_c"] * ln["taxa_legal_pct"] / 100)
        ln["total"] = round2(ln["corrigido_c"] + ln["juros_c"]) if fase_c else ln["total_b"]
        ln["base_atualizada"] = round2(ln["atualizado"] + (ln["corrigido_c"] - ln["total_b"] if fase_c else 0))
        ln["juros_total"] = round2(ln["juros"] + ln["selic"] + (ln["juros_c"] if fase_c else 0))

    # ---- totais e honorários
    pct = float(liq.get("honorarios_percentual", 10))
    hon_ate = d(liq.get("honorarios_ate"))
    hon_linhas = [ln for ln in linhas if not hon_ate or ln["c"] <= c_of(hon_ate)]
    soma = lambda campo, ls=linhas: round2(sum(x[campo] for x in ls))
    tot = dict(principal=soma("diferenca"), base_atualizada=soma("base_atualizada"), juros=soma("juros_total"),
               total=soma("total"))
    tot["correcao"] = round2(tot["base_atualizada"] - tot["principal"])
    acordo = float(liq.get("acordo_desagio", 0))
    tot["total_menos_acordo"] = round2(tot["base_atualizada"] + tot["juros"] - acordo)
    hon = dict(sobre_base=round2(soma("base_atualizada", hon_linhas) * pct / 100),
               sobre_juros=round2(soma("juros_total", hon_linhas) * pct / 100),
               fixo=float(liq.get("honorarios_valor_fixo", 0)))
    hon["total"] = round2(hon["sobre_base"] + hon["sobre_juros"] + hon["fixo"])
    multa, dano = float(liq.get("multa", 0)), float(liq.get("dano_moral", 0))
    tot["total_geral"] = round2(tot["total_menos_acordo"] + hon["total"] + multa + dano)
    sm_atual = tab.salario_minimo(c_of(atual))
    rma = evol[-1]["mensal"]
    causa = dict(salario_minimo=sm_atual, total_geral_em_sm=roundn(tot["total_geral"] / sm_atual, 2),
                 vencidas=tot["total_menos_acordo"], vincendas=round2(12 * rma))
    causa["valor_causa"] = round2(causa["vencidas"] + causa["vincendas"])
    causa["limite_jef"] = round2(60 * sm_atual)
    causa["competencia"] = "JEF" if causa["valor_causa"] <= causa["limite_jef"] else \
        "Vara Federal (ou renúncia ao excedente de 60 SM para o JEF)"

    # ---- IR (rendimentos recebidos acumuladamente)
    ano_atual = atual.year
    ir = {"anteriores": [0.0, 0], "atual": [0.0, 0]}
    anos_13 = set()
    for ln in linhas:
        grupo = "atual" if ln["c"][0] == ano_atual else "anteriores"
        ir[grupo][0] += ln["total"]
        if ln["tipo"] == "mensal":
            ir[grupo][1] += 1
        elif ln["c"][0] not in anos_13:
            anos_13.add(ln["c"][0])
            ir[grupo][1] += 1
    ir = {k: [round2(v[0]), v[1]] for k, v in ir.items()}

    return dict(dib=dib, rmi=rmi, atual=atual, ajuizamento=ajuiz, citacao=citacao, prescricao=prescricao,
                inicio=inicio, fim=fim, evolucao=evol, linhas=linhas, hon_linhas=hon_linhas, totais=tot,
                honorarios=hon, pct=pct, multa=multa, dano=dano, acordo=acordo, causa=causa, ir=ir, rma=rma,
                fase_c=fase_c, avisos=avisos, criterio=criterio)
