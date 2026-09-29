# SKIL-CALCULOS-REVIDENCIARIOS

Skill `calculos-previdenciarios-ottone` (pasta [`calculos-previdenciarios-ottone/`](calculos-previdenciarios-ottone/SKILL.md)):
planilha de cálculos previdenciários do escritório Cristiano Ottone Advocacia a partir do **extrato CNIS e dos dados pessoais**.

- Tempo de contribuição, carência e conversão de tempo especial
- Regras de aposentadoria: direito adquirido, transições da EC 103/2019 (arts. 15 a 21) e regra permanente, com a RMI de cada uma
- Liquidação dos atrasados no modelo do escritório (Resumo, Evolução da RMI, Diferenças, Honorários, IR/RRA)
  pelo Manual de Cálculos da Justiça Federal (Res. CJF 990/2026 e anteriores: INPC + juros, SELIC 12/2021–08/2025, INPC + taxa legal desde 09/2025)
- Valor da causa (art. 292 do CPC) e alçada do JEF

```bash
pip install openpyxl pdfplumber
cd calculos-previdenciarios-ottone
python scripts/cnis_para_json.py CNIS.pdf -o caso.json        # depois completar o caso (assets/caso_modelo.json)
python scripts/calcular.py caso.json --xlsx Calculo_de_NOME.xlsx
python testes/testar.py                                        # regressão contra o cálculo-modelo em PDF
```

`exemplos/Calculo_modelo_exemplo.xlsx` é o cálculo-modelo reproduzido (dados pessoais fictícios).
