# Manual de Cálculos da Justiça Federal: critérios aplicados

Referência para a liquidação dos atrasados. Ela resume o *Manual de Orientação de Procedimentos
para os Cálculos na Justiça Federal*, capítulo 4 (liquidação de sentença, benefícios
previdenciários), e mostra onde cada critério entra no motor (`scripts/motor.py`).

## Sumário
1. Versões do Manual
2. Linha do tempo de correção e juros (benefícios previdenciários)
3. Detalhes de cada fase
4. Parcelas: pró-rata, 13º, reajustes, teto e mínimo
5. Prescrição, honorários, IR, valor da causa
6. Pontos de atenção e temas pendentes

## 1. Versões do Manual

| Resolução CJF | O que mudou (em resumo) |
|---|---|
| 134/2010 | Aprova o Manual consolidado. |
| 267/2013 | Nova versão após as ADIs 4.357/4.425: afasta a TR como índice de correção. |
| 658/2020 | Adequação ao Tema 810/STF e ao Tema 905/STJ: INPC para benefícios previdenciários, IPCA-E para assistenciais. |
| 784/2022 | Adequação à EC 113/2021: SELIC única (correção + juros) a partir de 12/2021. |
| 963/2025 | Atualização geral. Mantém a SELIC a partir de 12/2021. |
| **990/2026** | Adequação à **EC 136/2025**, ao **Tema 1.419/STF** e à taxa legal do Código Civil (Lei 14.905/2024). A SELIC isolada vale até 08/2025. **A partir de 09/2025: INPC + juros de mora pela taxa legal** (SELIC com dedução do INPC) na fase pré-requisitório. Publicada em julho de 2026 (DOU de 03/07/2026). |

O cálculo deve seguir a versão que o título executivo ou o juízo mandar aplicar. Na falta de
determinação, use a versão vigente na data da conta. Hoje, isso significa a Res. 990/2026.

## 2. Linha do tempo (benefícios previdenciários)

| Período da incidência | Correção monetária | Juros de mora | No motor |
|---|---|---|---|
| até 04/1996 | Tabela JF (ORTN, OTN, BTN, IPC, INPC, IRSM, URV, IPC-r, INPC) | 1% a.m. | só INPC disponível; conferir parcelas anteriores a 1996 |
| 05/1996 a 08/2006 | IGP-DI | 1% a.m. | série `igpdi` |
| 09/2006 a 06/2009 | INPC (Lei 11.430/2006; Tema 905/STJ) | 1% a.m. | `inpc` |
| 07/2009 a 04/2012 | INPC | 0,5% a.m. (Lei 11.960/2009) | `juros_mora` |
| 05/2012 a 11/2021 | INPC | poupança: 0,5% a.m. se a meta SELIC > 8,5% a.a.; senão 70% da meta mensalizada (Lei 12.703/2012) | `juros_mora` (meta SELIC do 1º dia do mês) |
| 12/2021 a 08/2025 | **SELIC** (correção + juros, uma vez só) | inclusa na SELIC | `selic` (soma simples) |
| a partir de 09/2025 | **INPC** | **taxa legal**: SELIC do mês − INPC do mês, zero se negativa | `inpc` + `taxa_legal` |

Para benefícios assistenciais (BPC/LOAS), use `"indice_correcao": "IPCA-E"` (Tema 810/STF).

## 3. Detalhes de cada fase

Todas as fases usam os índices até o **mês anterior à data da atualização**, como no modelo do escritório.

**Fase A (até 11/2021).**
- Índice de correção: produto `Π(1 + i)` dos índices do mês da parcela até 11/2021, com pró-rata
  pelos dias corridos no primeiro mês do cálculo.
- Valor atualizado: `ROUND(diferença × índice, 2)`.
- Juros: soma simples das taxas mensais do mês de início até 11/2021, sem capitalização. O mês de
  início é o maior entre o mês da parcela e o mês da citação (Súmula 204/STJ). Os juros incidem
  sobre o valor atualizado.

**Fase B (12/2021 a 08/2025).**
- `% SELIC` é a soma simples da SELIC mensal (BCB 4390) do maior entre o mês da parcela e 12/2021
  até 08/2025.
- Incide sobre o valor atualizado mais os juros da fase A.
- Pelo Tema 1.419/STF, a SELIC isolada vale para todas as parcelas no período, sem modulação.

**Fase C (a partir de 09/2025, Res. 990/2026).**
- O saldo ao fim de 08/2025 (ou a diferença, para parcelas posteriores) é corrigido pelo INPC acumulado.
- Os juros de mora são a soma simples da taxa legal mensal, contada a partir do maior entre a
  parcela, 09/2025 e a citação.
- As colunas próprias da planilha só aparecem quando a atualização é posterior a 09/2025.
- **Confira a taxa legal** com a tabela publicada pelo CJF ou pelo BCB. A Lei 14.905/2024 define
  a taxa legal como SELIC − IPCA, e o Manual 2026 usa, para benefícios, SELIC com dedução do INPC.
  Se a tabela oficial for diferente, informe `series.taxa_legal` no caso ou edite a coluna
  "% Taxa Legal" na planilha.

## 4. Parcelas

- **Pró-rata:** no mês inicial (DIB ou data da prescrição) e no mês final, pelos dias devidos num
  mês comercial de 30 dias. Exemplo: DIB em 16/10 dá 15/30 do benefício.
- **Truncamento:** benefício, reajustes e 13º são truncados em centavos, como na conta do INSS.
  Valores atualizados, juros e SELIC são arredondados.
- **Reajustes:** percentual integral em janeiro (tabela `reajuste_beneficios`). O primeiro reajuste
  após a DIB é proporcional ao INPC acumulado do mês da DIB a dezembro. Por exemplo, DIB em
  10/2019 dá 1,81% em 01/2020.
- **Limites:** o valor mensal fica entre o salário mínimo e o teto da competência.
- **13º (abono anual, art. 40 da Lei 8.213/91):**
  - No ano de início, se o benefício começou depois do mês da 1ª parcela, há uma parcela única em
    dezembro, proporcional aos meses com 15 dias ou mais.
  - Nos demais anos, 1ª metade e 2ª metade nos meses em que o INSS pagou, conforme a tabela
    `calendario_13` (antecipações de 2020 a 2025 em abril/maio ou maio/junho).

## 5. Prescrição, honorários, IR e valor da causa

- **Prescrição quinquenal** (art. 103, parágrafo único, Lei 8.213/91): parcelas anteriores a
  5 anos do ajuizamento. Data da prescrição = maior entre a DIB e o ajuizamento menos 5 anos.
- **Honorários de sucumbência:** percentual sobre a base atualizada e sobre os juros, somente
  das parcelas até a sentença ou o acórdão que reconheceu o direito (Súmula 111/STJ e
  Tema 1.105/STJ). Informe `honorarios_ate`, pois sem ele o cálculo usa todas as parcelas.
  Há ainda campo para valor fixo.
- **Imposto de renda (RRA, art. 12-A da Lei 7.713/88):** total separado entre anos-base
  anteriores e ano-base atual. O número de meses conta as competências mensais mais 1 mês por
  ano com 13º.
- **Valor da causa (art. 292, §§ 1º e 2º, CPC):** parcelas vencidas atualizadas mais 12 parcelas
  vincendas (12 × RMA).
  - Alçada do JEF: 60 salários mínimos na data do ajuizamento (art. 3º, Lei 10.259/2001).
    Acima disso, cabe Vara Federal ou renúncia expressa ao excedente (Tema 1.030/STJ).
  - O modelo também mostra "Total geral ÷ salário mínimo", que é o mesmo número do rodapé do PDF.

## 6. Pontos de atenção

- **Tema 1.484/STF** (critérios dos atrasados contra o INSS) estava em julgamento em setembro de 2026.
  Verifique se há tese firmada antes de protocolar.
- **ADI 7.873** (constitucionalidade da EC 136/2025) estava pendente.
- Um título executivo com critério expresso prevalece sobre o Manual, salvo coisa julgada inconstitucional.
- **Descarte de contribuições** (art. 26, § 6º, EC 103/2019) não é aplicado automaticamente. Avalie à parte.
- **Salários anteriores a 07/1994** e **índices anteriores a 1996** não fazem parte do motor.
