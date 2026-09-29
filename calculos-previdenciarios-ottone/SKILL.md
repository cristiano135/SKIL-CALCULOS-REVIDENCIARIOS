---
name: calculos-previdenciarios-ottone
description: Faz cálculos previdenciários do escritório Cristiano Ottone Advocacia (Betim/MG) a partir do extrato CNIS e dos dados pessoais do segurado. Calcula tempo de contribuição, carência, conversão de tempo especial, regras de aposentadoria (direito adquirido, transições da EC 103/2019 e regra permanente), RMI, atrasados e liquidação de sentença contra o INSS pelo Manual de Cálculos da Justiça Federal (Res. CJF 990/2026 e anteriores), honorários, IR (RRA) e valor da causa. Entrega uma planilha .xlsx no modelo de cálculo do escritório, com fórmulas. Use sempre que o usuário enviar um CNIS ou pedir cálculo de tempo, de RMI, de atrasados, de liquidação ou cumprimento de sentença, de valor da causa, de honorários sobre atrasados, conferência de cálculo do INSS ou da contadoria, ou "planilha de cálculo" previdenciária, mesmo sem usar a palavra "cálculo". Não use para redigir a petição em si (peticao-aposentadoria-ottone, peticao-previdenciaria-ottone), só para os números que ela usa.
---

# Cálculos previdenciários (modelo Ottone)

Esta skill transforma o **extrato CNIS e os dados pessoais** do segurado em uma planilha de
cálculo no modelo do escritório. O modelo é "Cálculo de NOME.pdf" (Resumo, Competências sem
salários, Evolução da RMI, Diferenças não recebidas e Honorários). A planilha também traz as
abas de tempo de contribuição, regras da EC 103/2019 e salários/RMI.

Os números vêm dos scripts, e as contas ficam em fórmulas na planilha, para quem for conferir
(juiz, contadoria, INSS). Não calcule à mão o que o script calcula. Seu papel é montar o caso
corretamente, rodar, conferir os avisos e explicar o resultado.

## Dependências
```bash
pip install openpyxl pdfplumber   # se ainda não estiverem instalados
```

## Fluxo

### 1. Reunir os dados
Da **CNIS** (PDF do Meu INSS) vêm identificação, vínculos, remunerações e indicadores. Peça ao
usuário, ou tire dos documentos, só o que falta para o cálculo pedido:

| Para | Precisa de |
|---|---|
| Tempo, regras e RMI | sexo (o CNIS não traz), DER, períodos especiais reconhecidos (PPP/LTCAT/sentença) e seu tipo (15/20/25), períodos a excluir ou acrescentar (CTPS, rural, sentença) |
| Atrasados e liquidação | DIB e RMI (carta de concessão ou sentença; sem elas, usa a RMI calculada), nº do processo, ajuizamento, citação, data da atualização, fim das diferenças (véspera da DIP), valores já recebidos inacumuláveis, % de honorários e data da sentença ou acórdão (Súmula 111) |
| Fator previdenciário | expectativa de sobrevida da tábua IBGE vigente na DIB |

Não invente dados. Se faltar algo essencial, pergunte, com todas as perguntas numa mensagem só.
Para campos secundários, use o padrão do `assets/caso_modelo.json` e diga qual valor assumiu.

### 2. Montar o caso JSON
```bash
python scripts/cnis_para_json.py CNIS.pdf -o caso.json
```
O leitor é "melhor esforço". **Abra o PDF do CNIS e confira** vínculos, datas e remunerações
contra o JSON. Os alertas impressos indicam:
- vínculos sem data fim;
- indicadores `IEAN` (agente nocivo, candidato a tempo especial), `PEXT` e `PREC-MENOR-MIN`;
- benefícios por incapacidade.

Depois complete o caso usando `assets/caso_modelo.json` como guia de campos (cada bloco tem
`_obs`). Marque `especial` só em período reconhecido ou que o usuário mande considerar. Se ele
pedir as duas hipóteses (com e sem especial), rode duas vezes.

### 3. Calcular
A base `assets/series_indices.json` já traz as séries oficiais do BCB até 08/2026: INPC, IGP-DI e
IPCA-E desde 07/1994 (IPCA-E desde 2001) e SELIC mensal. A meta SELIC só está disponível para 10 e
11/2021; ela é usada nos juros da poupança de 05/2012 a 11/2021. Se o cálculo precisar de meses mais
novos ou de juros de poupança, atualize (INPC, IGP-DI, IPCA-E, SELIC e meta SELIC, desde 07/1994) direto do
Banco Central. O script valida cada ano do INPC contra o reajuste do INSS:
```bash
python scripts/atualizar_indices.py                       # direto do BCB (precisa de acesso a api.bcb.gov.br)
python scripts/atualizar_indices.py --csv bcdata.sgs.*.csv  # ou CSVs exportados do SGS
```
Depois calcule:
```bash
python scripts/calcular.py caso.json --xlsx "Calculo_de_NOME.xlsx" --json resultado.json
```
- Com o bloco `vinculos`, o script calcula o tempo, as regras e a RMI de cada regra e aponta a
  mais vantajosa.
- Com o bloco `liquidacao`, calcula os atrasados. Usa `beneficio.rmi` se informada; senão, a RMI
  da regra escolhida ou da mais vantajosa.
- Os índices vêm do cache `assets/series_indices.json` e, para os meses que faltam, da API do
  Banco Central.

Sem internet, a saída avisa **"CÁLCULO INCOMPLETO: faltam índices de ..."**. Nesse caso:
1. obtenha os percentuais mensais (INPC, SELIC mensal, meta SELIC, IGP-DI) no BCB/SGS, no IBGE
   ou na tabela do CJF, por busca na web ou pelo usuário;
2. informe-os em `caso.series`;
3. rode de novo.

Nunca entregue um cálculo com esse aviso sem dizer claramente o que falta.

### 4. Conferir antes de entregar
- Leia os `avisos` da saída. Valores de tabela não conferidos (salário mínimo, teto e reajuste
  de 2026) precisam ser validados.
- Confira a RMI e a evolução do benefício com a carta de concessão ou o histórico de créditos
  (HISCRE), quando houver.
- Faça uma checagem de coerência: nº de meses, prescrição, 13º nos meses certos e honorários só
  até a sentença.

### 5. Entregar
- A planilha `.xlsx` tem células amarelas editáveis: RMI, recebidos, índices e % de honorários.
- Mande também um resumo curto no chat:
  - tempo de contribuição e regra mais vantajosa (com a data em que cumpre, se for depois da DER);
  - RMI;
  - principal, correção, juros, total atualizado, honorários e total geral;
  - valor da causa e alçada (JEF ou Vara Federal);
  - pendências.
- Se o usuário pedir PDF, gere a partir da planilha.

## Critérios jurídicos
Leia a referência quando precisar justificar ou ajustar um critério:
- `references/manual_calculos_cjf.md`: correção e juros por período, com a SELIC de 12/2021 a
  08/2025 e o INPC + taxa legal a partir de 09/2025 (Res. CJF 990/2026, EC 136/2025, Tema 1.419/STF).
  Também traz as versões anteriores do Manual, pró-rata, 13º, prescrição, honorários, IR e valor da causa.
- `references/regras_ec103.md`: requisitos e coeficientes de cada regra, fator previdenciário e
  PBC, e limitações.

Se o título executivo fixar critério diferente do Manual, ele prevalece. Ajuste
`indices_por_competencia` ou `series` e registre isso no resumo.

## Teste de regressão
`python testes/testar.py` deve imprimir `OK`. O teste reproduz, linha a linha, o cálculo-modelo
do escritório (DIB 16/10/2019, atualização 08/05/2025, total geral R$ 489.111,43). Rode-o depois
de qualquer alteração no motor.
