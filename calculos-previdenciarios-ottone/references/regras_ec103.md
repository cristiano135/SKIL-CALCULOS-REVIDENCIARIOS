# Tempo de contribuição, regras de aposentadoria e RMI

Esta página mostra como o motor aplica cada regra. Use-a para explicar o resultado ao cliente ou ao juízo.

## Tempo de contribuição e carência
- **Fonte:** vínculos do CNIS. Os períodos concomitantes contam uma vez só. Quando se sobrepõem,
  prevalece o período com o maior fator.
- **Contagem:** anos, meses e dias pelo calendário, somados em base 360/30. É a apresentação usual
  das contagens do INSS.
- **Conversão especial → comum** (art. 70 do Decreto 3.048/99), só até 13/11/2019
  (art. 25, § 2º, da EC 103/2019):

  | Tempo especial | Homem | Mulher |
  |---|---|---|
  | 25 anos | 1,40 | 1,20 |
  | 20 anos | 1,75 | 1,50 |
  | 15 anos | 2,33 | 2,00 |

- **Carência:** meses com vínculo ou contribuição. O campo `carencia: false` exclui um período,
  por exemplo auxílio-doença não intercalado (Tema 1.125/STF) ou recolhimento abaixo do mínimo
  não complementado.

## Regras avaliadas

"Cumpre em" é a primeira data em que os requisitos são preenchidos. Depois da DER, o motor supõe
que as contribuições continuam (reafirmação da DER, Tema 995/STJ).

| Regra | Requisitos (H / M) | Cálculo da RMI |
|---|---|---|
| Direito adquirido: ATC (EC 103, art. 3º) | 35 / 30 anos até 13/11/2019 + 180 meses de carência | 80% maiores salários × fator previdenciário (sem fator se pontos ≥ 96/86 e o fator for < 1) |
| Direito adquirido: idade | 65 / 60 anos até 13/11/2019 + 180 meses | 70% + 1% a cada 12 contribuições (máximo 100%); fator só se > 1 |
| Direito adquirido: especial | 25 / 20 / 15 anos especiais até 13/11/2019 | 100% da média dos 80% maiores |
| Transição por pontos (art. 15) | 35 / 30 anos de TC + pontos: 96 / 86 em 2019, +1 por ano, até 105 / 100 | 60% + 2% por ano acima de 20 / 15 |
| Idade mínima progressiva (art. 16) | 35 / 30 anos de TC + idade: 61 / 56 em 2019, +6 meses por ano, até 65 / 62 | 60% + 2% por ano acima de 20 / 15 |
| Pedágio de 50% (art. 17) | mais de 33 / 28 anos em 13/11/2019; 35 / 30 anos + 50% do tempo que faltava | 100% × fator previdenciário |
| Pedágio de 100% (art. 20) | 60 / 57 anos de idade; 35 / 30 anos + 100% do tempo que faltava | 100% da média |
| Idade: transição (art. 18) | 65 anos / 60 anos em 2019 com +6 meses por ano até 62; 15 anos de TC | 60% + 2% por ano acima de 20 / 15 |
| Especial: transição (art. 21) | 15 / 20 / 25 anos especiais + pontos 66 / 76 / 86 | 60% + 2% por ano acima de 20 (acima de 15 para mulher e para especial de 15 anos) |
| Regra permanente (art. 19) | 65 / 62 anos de idade; 20 / 15 anos de TC | 60% + 2% por ano acima de 20 / 15 |

## Média e RMI
- **Período básico de cálculo (PBC):** de 07/1994 ao mês anterior à DIB. Os salários da mesma
  competência são somados, e a soma é limitada ao teto.
- **Correção dos salários:** INPC, com IGP-DI de 05/1996 a 08/2006, do mês da competência até o
  mês anterior à DIB. Se houver carta de concessão ou memória de cálculo do INSS, prefira os
  valores corrigidos que ela traz: informe `valor_corrigido` em cada remuneração.
- **Média pós-reforma:** 100% dos salários (art. 26 da EC 103/2019).
- **Direito adquirido:** média dos 80% maiores salários, com o PBC encerrado em 10/2019. É uma
  aproximação, e a conta do INSS deve ser conferida.
- **Fator previdenciário:** `f = (Tc × 0,31 / Es) × [1 + (Id + Tc × 0,31) / 100]`, com +5 anos de
  Tc para mulher. `Es` é a expectativa de sobrevida da tábua do IBGE vigente na DIB. Informe
  `beneficio.expectativa_sobrevida`; sem ela, as regras com fator ficam pendentes.
- **Limites:** a RMI fica entre o salário mínimo e o teto da DIB.

## Limitações
Estes pontos exigem revisão humana:
- aposentadoria da pessoa com deficiência;
- aposentadoria do professor;
- aposentadoria rural;
- aposentadoria proporcional (EC 20/98);
- descarte de contribuições (art. 26, § 6º);
- divisor mínimo;
- atividades concomitantes antes de 06/2019;
- teto dos salários de contribuição anteriores a 2015 (a tabela de teto começa em 2015; informe outros anos em `caso.tabelas.teto`);
- o valor definitivo da RMI, que deve ser conferido com a carta de concessão.
