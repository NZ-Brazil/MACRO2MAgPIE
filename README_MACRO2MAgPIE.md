# MACRO2MAgPIE — Resumo de Flows e Conversão de Biomassa

Script Python que lê os resultados do modelo **MACRO** (arquivos `flows.csv` por
período) e produz dois relatórios agregados:

1. **`flows_summary.csv`** — soma do valor de todas as commodities, por ano.
2. **`flows_summary_biomass.csv`** — apenas os feedstocks de biomassa, em
   **base úmida (as-harvested)** e já somados à demanda de lenha (`firewood`) do
   modelo **EP** (Energy Planning), para uso como entrada no **MAgPIE**.

Este README documenta o funcionamento do script para facilitar sua integração
como um passo de pipeline na plataforma do NZB (Net Zero Brasil).

---

## 1. Visão geral do fluxo

```
results_001/
├── results_period_1/full_time_series/flows.csv   (ano 2025)
├── results_period_2/full_time_series/flows.csv   (ano 2030)
├── ...
└── results_period_6/full_time_series/flows.csv   (ano 2050)
```

Para cada período configurado em `PERIODS`, o script:

1. Localiza o arquivo de flows dentro de `<pasta_do_periodo>/full_time_series/`
   (aceita `.csv`, `.csv.gz`, `.csv.zip` ou `.zip`).
2. Lê o arquivo **em chunks** (`CHUNK_SIZE = 500_000` linhas) para não estourar
   memória em arquivos grandes, usando apenas as colunas `commodity` e `value`.
3. Agrupa e soma `value` por `commodity`, dentro do período.
4. Concatena todos os períodos em uma tabela única (`flows_summary.csv`).

Em seguida, a partir dessa tabela:

5. Filtra apenas os feedstocks de biomassa (`BIOMASS_FEEDSTOCKS`).
6. Faz *pivot* para uma tabela `ano x feedstock`, aplica valor absoluto (o MACRO
   reporta consumo como negativo) e preenche ausências com 0.
7. Converte a coluna `Biomass_wood` de **base seca** (como o MACRO reporta
   madeira) para **base úmida**, dividindo por `(1 - WOOD_MOISTURE_CONTENT)`.
   As demais colunas de biomassa (Corn, Macauba, RiceStraw, Soybean,
   Sugarcane) já chegam do MACRO em base úmida e são usadas como estão, sem
   conversão.
8. Lê os arquivos de demanda de lenha (`firewood`) do EP
   (`EP_DEMAND_FILES`) e soma por ano. Os valores do EP já vêm em base úmida e
   são usados como estão, sem conversão.
9. Soma a demanda de lenha do EP (base úmida) à coluna `Biomass_wood` (base
   úmida, já convertida no passo 7), linha a linha, por ano.
10. Salva `flows_summary_biomass.csv`, com todas as colunas em base úmida.

---

## 2. Requisitos

- Python 3.10+ (usa `Path | None`, sintaxe de union types)
- `pandas`
- (opcional) `openpyxl` / `xlrd`, exigidos pelo pandas caso os arquivos de
  demanda do EP estejam em `.xlsx`/`.xls`

```bash
pip install pandas openpyxl
```

O script não recebe argumentos de linha de comando — toda a configuração é
feita editando as variáveis no topo do arquivo (seção `CONFIGURATION`).

---

## 3. Parâmetros de configuração

| Variável | O que é | Observações |
|---|---|---|
| `RESULTS_DIR` | Pasta raiz com os resultados do MACRO | **Caminho absoluto do Windows, hardcoded.** Precisa virar parâmetro na integração (ver seção 6). |
| `PERIODS` | Mapa `{número do período: ano}` | Define quantos e quais períodos serão processados. |
| `FLOWS_SUBFOLDER` | Subpasta dentro de cada período onde está o `flows.csv` | Atualmente `"full_time_series"`. |
| `FLOWS_CANDIDATES` | Nomes de arquivo aceitos para os flows | Testa nesta ordem: `flows.csv`, `flows.csv.gz`, `flows.csv.zip`, `flows.zip`. |
| `OUTPUT_FILE` | Nome do CSV de saída (todas as commodities) | Salvo no diretório de trabalho, não em `RESULTS_DIR`. |
| `OUTPUT_FILE_BIOMASS` | Nome do CSV de saída (só biomassa, base úmida) | Idem. |
| `BIOMASS_FEEDSTOCKS` | Lista dos feedstocks tratados como biomassa | Define também a ordem das colunas na tabela final. |
| `CHUNK_SIZE` | Tamanho do chunk de leitura do `flows.csv` | Ajustar conforme memória disponível / tamanho dos arquivos. |
| `EP_DEMAND_FILES` | Lista de caminhos para os arquivos de demanda de lenha do EP (`firewood_mass`) | **Vazia por padrão** — se vazia, a demanda do EP é tratada como 0 e uma mensagem informativa é impressa. Aceita `.csv`, `.xlsx`, `.xls`. Os valores já vêm em base úmida e são usados sem conversão. |
| `EP_DEMAND_FEEDSTOCK` | A qual feedstock de `BIOMASS_FEEDSTOCKS` a demanda do EP deve ser somada | Precisa bater exatamente (case-sensitive) com um nome em `BIOMASS_FEEDSTOCKS`. Há uma validação no início do script que já barra valores inválidos. |
| `WOOD_MOISTURE_CONTENT` | Teor de umidade (as-harvested) da madeira, usado **só** para converter a coluna `Biomass_wood` do MACRO de base seca para base úmida (`wet = dry / (1 - WOOD_MOISTURE_CONTENT)`) | Valor atual: `0.51` (mesma figura usada anteriormente como `EP_MOISTURE_CONTENT`). Só se aplica à madeira do MACRO — os demais feedstocks de biomassa não passam por nenhuma conversão de umidade, pois já chegam em base úmida. |

---

## 4. Saídas

### `flows_summary.csv`
| coluna | descrição |
|---|---|
| `year` | ano do período (via `PERIODS`) |
| `commodity` | nome da commodity, como reportada pelo MACRO |
| `value` | soma de `value` para aquela commodity naquele ano (sinal original do MACRO, sem conversão) |

### `flows_summary_biomass.csv`
| coluna | descrição |
|---|---|
| `year` | ano do período |
| uma coluna por item de `BIOMASS_FEEDSTOCKS` | valor em **base úmida**; para `Biomass_wood`, já é a soma da madeira do MACRO (convertida de base seca para úmida) com a demanda de lenha (`firewood`) do EP (já em base úmida) |

Todos os valores de biomassa são convertidos para módulo (`abs()`) antes de
qualquer conversão de umidade, pois o MACRO reporta consumo como valor
negativo.

---

## 5. Mensagens de log relevantes

O script imprime no console (não gera arquivo de log) avisos que indicam
problemas de configuração ou de dados de entrada — importante mapear para o
sistema de logging/alertas da plataforma NZB:

- `[WARNING] No flows file found in ...` — período sem arquivo de flows encontrado (o período é pulado, não interrompe o script).
- `[INFO] EP_DEMAND_FILES is empty - EP wood demand treated as 0 for all years.` — nenhum arquivo de demanda do EP configurado.
- `[WARNING] EP demand file not found: ...` — caminho configurado em `EP_DEMAND_FILES` não existe.
- `[WARNING] Only N of M EP files were read ...` — leitura parcial dos arquivos de demanda do EP.
- `[WARNING] No EP demand found for years [...] ...` — anos de `PERIODS` sem correspondência na demanda do EP (tratados como 0).
- `ValueError` no início da execução se `EP_DEMAND_FEEDSTOCK` não estiver em `BIOMASS_FEEDSTOCKS`.

---

## 6. Pontos de atenção para integração na plataforma NZB

O script foi escrito para rodar localmente (Windows, caminho fixo, execução
via `python MACRO2MAgPIE.py`). Para integrá-lo como etapa de pipeline
recomenda-se:

1. **Parametrizar `RESULTS_DIR`, `EP_DEMAND_FILES`, `OUTPUT_FILE` e
   `OUTPUT_FILE_BIOMASS`** — hoje são constantes hardcoded no topo do arquivo.
   Sugestão: expor via argumentos de CLI (`argparse`) ou variáveis de
   ambiente, e transformar o corpo do script em uma função
   `run(results_dir, periods, ep_demand_files, output_dir) -> None` que a
   plataforma possa chamar diretamente, em vez de depender de execução como
   script top-level.
2. **Trocar `print()` por `logging`** — os `print()` de progresso e os
   `[WARNING]`/`[INFO]` deveriam virar chamadas de `logging`
   com níveis apropriados (`INFO`, `WARNING`), para se integrarem ao sistema
   de logs da plataforma.
3. **Falhas silenciosas a revisar**: hoje, período sem arquivo de flows é
   pulado (`continue`) — isso apenas avisa via `print`. Definir se a
   plataforma deve tratar isso como erro bloqueante, warning tolerável, ou
   exigir confirmação manual antes de publicar o resultado.
4. **Validação de `EP_DEMAND_FEEDSTOCK`** já existe (`ValueError` na
   inicialização) — pode ser reaproveitada como validação de contrato de
   configuração ao subir a etapa no pipeline.
5. **Caminho de saída**: os CSVs são salvos no diretório de trabalho atual
   (`Path.cwd()`), não em `RESULTS_DIR`. Definir explicitamente o diretório
   de saída ao integrar, para não depender do cwd do processo.
6. **Dependência de nomes exatos**: `flows.csv` precisa ter colunas
   `commodity` e `value`; feedstocks em `BIOMASS_FEEDSTOCKS`/
   `EP_DEMAND_FEEDSTOCK` precisam bater exatamente (case-sensitive). Vale
   documentar esse contrato de schema para quem for gerar os arquivos de
   entrada (MACRO e EP) do lado da plataforma.
7. **Arquivos de demanda do EP** aceitam layout largo (ano em colunas) ou
   longo (coluna de ano + coluna de valor), com detecção automática de
   nomes de coluna (`_sheet_to_year_totals`). Se a plataforma padronizar o
   formato de saída do EP, essa detecção heurística pode ser simplificada.
8. **Performance**: a leitura em chunks (`CHUNK_SIZE`) só se aplica ao
   `flows.csv` do MACRO. Se os arquivos de demanda do EP também puderem ficar
   grandes, considerar o mesmo tratamento.
9. **`WOOD_MOISTURE_CONTENT` é uma premissa de negócio** (0.51, herdada do
   valor antes usado como `EP_MOISTURE_CONTENT`) — vale confirmar essa figura
   com quem fornece os dados de madeira antes de publicar resultados em
   produção.

---

## 7. Como rodar localmente (uso atual)

```bash
# 1. Editar as constantes no topo do arquivo (RESULTS_DIR, PERIODS,
#    EP_DEMAND_FILES etc.) conforme o cenário desejado.
# 2. Rodar:
python MACRO2MAgPIE.py
```

Saída esperada no console: progresso por período, avisos de configuração, e
as duas tabelas finais impressas antes do tempo total de execução.

---

## 8. Histórico de mudanças

- **2026-08-28**: a demanda adicional de madeira proveniente do EP foi simplificada para considerar apenas o arquivo de lenha (`firewood_mass`). A soma à coluna `Biomass_wood` continua sendo feita por ano e em base úmida.
- **2026-08-14**: saída de `flows_summary_biomass.csv` passou de base seca
  para **base úmida**. A madeira do MACRO (que vem em base seca) agora é
  convertida para base úmida via `WOOD_MOISTURE_CONTENT` antes de ser somada
  à demanda de lenha (`firewood`) do EP (que já era, e continua sendo, em base úmida).
  Os demais feedstocks de biomassa deixaram de ser convertidos para base
  seca — permanecem como reportados pelo MACRO (base úmida). As variáveis
  `MOISTURE_CONTENT`, `PLACEHOLDER_MOISTURE_CONTENT`, `EP_MOISTURE_CONTENT` e
  `EP_DRY_FRACTION` foram removidas; `WOOD_MOISTURE_CONTENT` (0.51) as
  substitui, usada apenas para a conversão da madeira do MACRO.
