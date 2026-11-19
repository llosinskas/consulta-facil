# CLAUDE.md — Guia do projeto para assistentes de IA

> Leia este arquivo **antes** de alterar qualquer código. Ele descreve a arquitetura, o fluxo de
> dados, os contratos entre módulos e as regras que mantêm o sistema funcionando.
> (`AGENTS.md` aponta para cá, para outras ferramentas de IA.)

## 1. O que o sistema faz

Aplicativo **Streamlit** de **estudo de viabilidade de terrenos em São Paulo**. Ele:

1. **Localiza o terreno** no GeoSampa (Prefeitura de SP) por SQL (Setor.Quadra.Lote — um ou vários
   lotes), endereço/CEP (geocodificação) ou coordenada; também por clique no mapa.
2. **Analisa a geometria** (Shapely + PyProj em SIRGAS 2000 UTM 23S, EPSG:31983): área, perímetro,
   arestas com azimute, testada/profundidade, unificação de lotes (remembramento).
3. **Cruza com camadas legais**: zoneamento (LPUOS), macrozona, macroárea, perímetro de
   qualificação ambiental (PA), curvas de nível (cotas/desnível) e tombamento.
4. **Calcula os índices urbanísticos** (CA básico/máximo, TO, permeabilidade, gabarito, recuos,
   cota-parte) e as **contas de aproveitamento** (outorga onerosa, cota de solidariedade, EHIS/EHMP).
5. **Reproduz a planilha `QUADRO_DE_ÁREAS-R01.xlsx`** (abas Q. ÁREAS, Q. LUOPS, Q. ANEXOS,
   CALC. ÁGUA, ELEVADOR, DADOS, DESNÍVEL): quadro de áreas por pavimento, LUOPS, anexos
   (reúso, retardo, acessibilidade, vagas), população/reservatórios, tráfego de elevadores
   (NBR 5665) e desnível hidráulico.
6. **Estima viabilidade econômica**: VGV, custos, cronograma físico-financeiro/Gantt, TIR, VPL,
   payback (página separada) e prévia de engenharia elétrica (demanda, subestação, custos).
7. **Exporta** tudo para `.xlsx` (gerador OpenXML próprio, sem openpyxl).

Executar: `streamlit run app.py` (Windows: `executar_sistema.bat`, que usa `.venv`).
Testes: `python -m pytest -q` (69 testes, todos passando; dependências em `requirements.txt`).

## 2. Arquitetura em camadas (REGRA PRINCIPAL)

```
app.py, pages/      →  orquestração Streamlit (sidebar, mapa, session_state)
ui/                 →  renderização (Streamlit/Folium/Altair). Chama services, NUNCA calcula regra de negócio
services/           →  cálculos e integrações. SEM Streamlit, SEM ui
domain/             →  dataclasses e tabelas legais. SEM services, SEM ui, SEM Streamlit
config.py           →  URLs do GeoSampa, CRS, nomes de camadas, timeouts
```

Dependências permitidas: `ui → services → domain`, todos podem importar `config`.
**Proibido**: `domain` importar `services`/`ui`; `services` importar `ui`/`streamlit`/`folium`/`altair`.
Isso é verificado por `tests/test_arquitetura.py` — rode-o após qualquer mudança.

## 3. Mapa dos arquivos

### domain/ (dados puros)
| Arquivo | Conteúdo |
|---|---|
| `models.py` | `ResultadoTerreno` (objeto central da parte geoespacial), `LoteIndividual`, `SegmentoAresta`, `DadosTopografia`, `InfoTerritorial`, `ParametrosZoneamento` |
| `viabilidade_models.py` | Dataclasses que espelham a planilha (comentários indicam a célula): `EntradaGeo`, `IndicesLegais`, `Pavimento`, `QuadroAreas`, `LinhaLimite`, `LinhaQuadro`, `ResultadoAnexos`, `ResultadoAgua`, `ResultadoElevador`, `ResultadoDesnivel`, `ResultadoFinanceiroCronograma`, `ResultadoPreviaEletrica`, `TipologiaPavimento`, `CapacidadePavimento`… e as constantes `COLUNAS_UNIDADES`, `COLUNAS_COMPUTAVEIS`, `COLUNAS_NAO_COMPUTAVEIS`, `MODALIDADES`, `CATEGORIAS_TIPOLOGIA` (categoria → coluna de UH, coluna de área, computável?) |
| `legislacao_sp.py` | **Fonte legal "oficial" conferida**: Quadro 3/3A LPUOS (Lei 16.402 + 18.081/24) em `QUADRO_3: Dict[str, ParametrosZonaLei]`, taxa de permeabilidade, PA, fatores Fs, Fp (Quadro 6), `macrozona_da_macroarea` (PDE arts. 10 e 16) |
| `zoning_rules.py` | Converte `legislacao_sp.QUADRO_3` em `ParametrosZoneamento` (`obter_parametros_zoneamento`) para painel/mapa |
| `lotes_exemplo.py` | **Gerado** a partir do GeoSampa: `LOTES_EXEMPLO_SP` (lotes **reais**; o 1º é o terreno inicial do app) e `LOTES_VIZINHOS_DEMO_UTM` (vizinhos reais, clicáveis offline). Reexportados por `geosampa_client` |
| `tabelas_dados.py` | **Gerado automaticamente** da aba DADOS da planilha (`QUADRO_2_RAW`, `QUADRO_3_RAW`, `QUADRO_4_RAW`, notas, listas). Valores em texto bruto (`'NA'`, `'28 (c)'`). Não editar à mão sem conferir a planilha |

### services/ (lógica)
| Arquivo | Etapa | Entrada principal → Saída |
|---|---|---|
| `geosampa_client.py` | 1 | `GeoSampaWFSClient` (WFS/WMS, auto-descoberta de camadas/schema, busca por SQL e por ponto); validadores `validar_sql_input`, `extrair_multiplos_sqls`, `validar_coordenadas_sp`; dados demo `LOTES_EXEMPLO_SP`, `LOTES_VIZINHOS_DEMO_UTM` |
| `geocoder.py` | 1 | `geocodificar_endereco_sp(texto) → (latlon, endereco_fmt, erro)` |
| `spatial_analyzer.py` | 1 | `processar_terreno_completo(features, client, ..., progresso=None) → ResultadoTerreno`; `alternar_lote_na_selecao`; `consultar_enquadramento_pelo_ponto_do_lote`; `encontrar_feicao_no_ponto(feats, lat, lon)` (clique sem rede); `bbox_utm_com_margem` |
| `viabilidade_bridge.py` | 2–4 | `extrair_entrada_geo(ResultadoTerreno, area_doacao, zona_override, pa_override) → EntradaGeo`; `calcular_indices_legais(EntradaGeo, modalidade, ca_customizado) → IndicesLegais` |
| `quadro_areas_engine.py` | 6–8 | `gerar_pavimentos_padrao`, `distribuir_areas_automaticas_por_terreno(IndicesLegais, ...) → List[Pavimento]`; `calcular_quadro_areas(pavs, indices, ...) → QuadroAreas`; tipologias da Etapa 5: `tipologias_padrao`, `validar_tipologias`, `aplicar_tipologias_aos_pavimentos(pavs, tipologias, pct_circ…) → List[Pavimento]`, `limites_pavimento_tipo`, `maximo_unidades_por_pavimento`, `calcular_capacidade_pavimentos(pavs, indices) → List[CapacidadePavimento]`; `calcular_quadro_luops(indices, quadro, ...) → List[LinhaQuadro]`; `calcular_anexos(indices, quadro, ...) → ResultadoAnexos` |
| `agua_elevador_engine.py` | 9–10 | `calcular_agua_e_populacao(List[PavimentoPopulacao], ...) → ResultadoAgua`; `calcular_trafego_elevadores(populacao, ...) → ResultadoElevador` |
| `desnivel_engine.py` | 11 | `calcular_desnivel_reservatorios(cotas, trechos, ...) → ResultadoDesnivel` |
| `financeiro_cronograma_engine.py` | 13 | `calcular_retorno_financeiro_e_cronograma(EntradaGeo, IndicesLegais, QuadroAreas, preços/custos...) → ResultadoFinanceiroCronograma` |
| `eletrica_engine.py` | 14 | `calcular_previa_eletrica(QuadroAreas, ...) → ResultadoPreviaEletrica` |
| `aproveitamento.py` | — | `calcular_aproveitamento(EntradaAproveitamento) → ResultadoAproveitamento` (memória de cálculo com base legal; usa `legislacao_sp`) |
| `payback.py` | — | `calcular_payback(EntradaPayback) → ResultadoPayback`; `sensibilidade_payback` |
| `excel_exporter.py` | 12 | `gerar_xlsx_bytes(List[(nome_aba, linhas)]) → bytes`. Cores por tipologia automáticas: colunas cujo **cabeçalho** cita uma tipologia (`familia_tipologia`) e linhas de tabelas com coluna **"CATEGORIA"** recebem a cor de `CORES_TIPOLOGIA` |

### ui/ e entrada
| Arquivo | Papel |
|---|---|
| `app.py` | Página principal: sidebar de busca, mapa (`st_folium`), seleção multi-lote com clique em vizinhos, botão Desfazer (`historico_selecoes`), toda consulta dentro de `tela_de_carregamento`; chama os renderizadores na ordem: resumo → painel de viabilidade → unitário×unificado → estudo completo da planilha → tabelas geométricas |
| `pages/2_Payback.py` | Página de payback (`ui/payback_ui.renderizar_pagina_payback`) |
| `ui/viabilidade_ui.py` | (≈1700 linhas) Etapas 2–14 na tela: entradas, data_editor de pavimentos, todos os motores, Gantt, montagem das abas do `.xlsx` (`_montar_abas_xlsx`) |
| `ui/dashboard_cards.py` | Resumo do terreno, painel de índices, tabela unitário×unificado, tabelas geométricas; chama `aproveitamento_ui` |
| `ui/aproveitamento_ui.py` | Formulário/resultado de `calcular_aproveitamento`; grava `session_state["aproveitamento_atual"]` |
| `ui/payback_ui.py` | Premissas, indicadores e gráficos Altair do payback |
| `ui/map_component.py` | `construir_mapa_terreno(..., lotes_vizinhos=None, aviso_carregando_ao_clicar=False)` (Folium: cotas, vértices, legenda, WMS, vizinhos clicáveis, aviso "Carregando…" no clique) |
| `ui/carregamento.py` | `reservar_area_carregamento()` (1ª linha do `main`) e `with tela_de_carregamento(titulo) as progresso:` — camada que bloqueia a página com barra de progresso; `sub_progresso` mapeia subetapas |
| `ui/styles.py` | CSS global e componentes HTML: `titulo_secao`, `grade_cards`, `tabela`, `nota(texto, tipo)`, `cabecalho_terreno` |

## 4. Fluxo de dados (pipeline)

```
Busca (SQL/endereço/coord/clique)
  └─ GeoSampaWFSClient → features GeoJSON
       └─ processar_terreno_completo → ResultadoTerreno  (session_state["resultado_terreno"])
            ├─ dashboard_cards / map_component (exibição; zoneamento via legislacao_sp)
            ├─ aproveitamento_ui → calcular_aproveitamento → session_state["aproveitamento_atual"] → página Payback
            └─ viabilidade_ui:
                 extrair_entrada_geo → EntradaGeo
                 calcular_indices_legais → IndicesLegais        (usa tabelas_dados / planilha)
                 Etapa 5: tipologias (editor) → aplicar_tipologias_aos_pavimentos(distribuir_areas_automaticas_por_terreno(...))
                 Etapa 6: matriz List[Pavimento] (editável, session_state["viab_df_pavimentos"]) → calcular_capacidade_pavimentos
                 calcular_quadro_areas → QuadroAreas
                 ├─ calcular_quadro_luops, calcular_anexos
                 ├─ calcular_agua_e_populacao → calcular_trafego_elevadores
                 ├─ calcular_desnivel_reservatorios
                 ├─ calcular_retorno_financeiro_e_cronograma
                 ├─ calcular_previa_eletrica
                 └─ gerar_xlsx_bytes (download)
```

Detalhamento célula a célula da planilha: `PLANO_CONEXAO_GEOSAMPA_CALCULOS.md` e
`PLANO_IMPLEMENTACAO_PLANILHA.md`.

### Chaves de `st.session_state`
`resultado_terreno`, `ultimo_erro`, `aviso_selecao_mapa`, `ultimo_clique_processado`,
`ponto_clicado_latlon`, `filtro_ativo`, `ultimo_endereco_buscado`, `viab_df_pavimentos`,
`viab_ultima_assinatura_fa`, `aproveitamento_atual`, `historico_selecoes` (Desfazer: pares
`(ResultadoTerreno, vizinhos)`), `lotes_vizinhos` (feições reais ao redor; `None` = demo),
`acao_clique_mapa`, `viab_df_tipologias`, `viab_tipologias_assinatura`, `viab_versao_matriz`,
`viab_versao_tipologias`.
**Matriz/tipologias**: troque a matriz sempre por `_definir_matriz(df)` em `viabilidade_ui` — ela incrementa
`viab_versao_matriz`, que faz parte da `key` do `data_editor`; sem isso o editor reaplica edições antigas
(por índice de linha) sobre a matriz nova. A matriz é refeita quando a assinatura das tipologias muda.
Ao trocar de terreno, `app.py` (`_limpar_estado_do_terreno`) remove `viab_df_pavimentos`, `viab_ultima_assinatura_fa`
e `viab_tipologias_assinatura`
(senão a tabela de pavimentos do terreno anterior é reaproveitada). Mantenha isso ao criar
novos caches por terreno.

## 5. Armadilhas conhecidas (leia antes de mexer)

1. **Duas fontes de tabela legal coexistem, de propósito:**
   - `domain/legislacao_sp.py` (LPUOS atualizada pela Lei 18.081/24, conferida) → usada por
     `zoning_rules`, `ResultadoTerreno.zoneamento`, `aproveitamento.py`.
   - `domain/tabelas_dados.py` (cópia da aba DADOS da planilha) → usada por `viabilidade_bridge`
     e `viabilidade_ui`, para bater com a planilha célula a célula.
   Os números podem divergir. Não unifique nem "corrija" uma pela outra sem pedido explícito.
2. **Funções homônimas com contratos diferentes:**
   - `legislacao_sp.normalizar_zona` × `viabilidade_bridge.normalizar_zona` (chaves de tabelas diferentes).
   - `legislacao_sp.extrair_pa(texto) → Optional[str]` × `viabilidade_bridge.extrair_pa(texto, macroarea) → str`
     (a da bridge aplica a regra do PA 13 pela macroárea). Importe sempre do módulo da mesma camada/fonte.
3. **Limite de 500 m²**: TO usa `< 500` vs `>= 500` (lote de exatamente 500 m² muda TO, não TP). Há teste.
4. **Unidades**: áreas em m², cotas em m, taxas como fração (`0.70` = 70%), exceto parâmetros
   explicitamente `_pct` (ex.: `pct_projetos_aprovacoes=5.0` = 5%). Valores monetários em R$ com sufixo `_rs`.
5. **CRS**: cálculo métrico sempre em `config.CRS_UTM_SP` (EPSG:31983); exibição em WGS84 (EPSG:4326).
   Use os transformers já existentes (`_TO_UTM`, `_TO_WGS`) em vez de criar novos.
6. **`None` significa "NA/sem limite"** em gabarito, CA, cota-parte. Não troque por 0.
7. **Rede**: o GeoSampa é instável; o cliente tenta várias URLs/camadas (`config.LAYER_CANDIDATES`,
   `LAYER_KEYWORDS`) e há modo demo (`LOTES_EXEMPLO_SP`). Testes não devem depender da rede
   (para simular offline, faça mock de `client._request_wfs` **e** de `client.session.get`, usado pelo WMS).
   Camadas no GeoSampa (conferido em 19/11/2026): o **GetCapabilities não lista tudo** —
   `zoneamento_2016_map3` (PA) só responde via **WMS** GetFeatureInfo; não há camada de macrozona
   (é deduzida da macroárea). O cliente guarda a camada que respondeu (`_camada_preferida`) e as recusadas
   por serviço (`_inexistentes_wfs` / `_inexistentes_wms`); não descarte nomes só por faltarem no catálogo.
   Camadas `*_aiu` são excluídas (não são PA). Primeira consulta ≈ 6 s, seguintes ≈ 1–2 s.
11. **Progresso**: serviços longos aceitam `progresso: Callable[[float, str], None]` (fração 0–1, mensagem)
    e nunca importam Streamlit; a UI passa o callback de `tela_de_carregamento`. Toda nova consulta
    ao GeoSampa disparada pela UI deve rodar dentro de `tela_de_carregamento`.
12. **Cliques no mapa**: `folium.Marker` não repassa o clique ao mapa (Leaflet `bubblingMouseEvents=false`).
    Etiquetas (cotas, vértices, SQL) usam `interactive=False`; senão o clique "some" sobre elas.
13. **Exemplos**: são lotes reais; para trocar/adicionar, gere `domain/lotes_exemplo.py` de novo a partir do
    GeoSampa (mesma estrutura) e atualize os nomes usados nos testes (`EX_*`).
8. **Nunca use `importlib.reload` no `app.py`/páginas.** O Streamlit já descarrega e reimporta os
   módulos do projeto quando um arquivo muda. O reload manual a cada execução trocava módulos no meio
   da execução de outras sessões e quebrava o deploy no Streamlit Cloud (KeyError/ImportError/
   AttributeError). Estado por sessão nunca em variável global de módulo (use `st.session_state`
   ou `threading.local`, como em `ui/carregamento.py`).
9. **Cache do cliente**: `obter_cliente_geosampa(versao=...)` usa `st.cache_resource`; mude a string
   `versao` se alterar o `__init__` do `GeoSampaWFSClient`.
10. Funções de cálculo **retornam dataclasses** e acumulam avisos em `alertas`/`avisos`/`notas`
    em vez de lançar exceção na UI. Siga o padrão.

## 6. Receitas para mudanças comuns

- **Novo cálculo/etapa**: dataclass de resultado em `domain/viabilidade_models.py` → função pura em
  `services/<tema>_engine.py` recebendo dataclasses existentes (`IndicesLegais`, `QuadroAreas`…) →
  teste em `tests/` → renderização em `ui/viabilidade_ui.py` (seção com `titulo_secao`) → se for
  exportado, nova aba em `_montar_abas_xlsx` (e cor em `excel_exporter.TAB_COLORS`).
- **Novo campo em dataclass**: adicione **com valor default** no final (os construtores são
  posicionais em vários pontos e nos testes). Procure todos os usos: `grep -rn "NomeDaClasse(" .`
- **Alterar parâmetro legal**: edite `legislacao_sp.py` (cite lei/artigo no comentário) e/ou
  `tabelas_dados.py` (manter fiel à planilha). Rode `tests/test_aproveitamento.py` e
  `tests/test_viabilidade_bridge.py` — eles contêm casos de referência da planilha (ZM, PA 6, < 500 m²).
- **Nova camada GeoSampa**: nome em `config.LAYER_CANDIDATES` (+ palavras em `LAYER_KEYWORDS`),
  consulta via `client.consultar_camada_no_ponto(tema, x_utm, y_utm)`, campo em `ResultadoTerreno`
  com default.
- **Nova página**: arquivo `pages/N_Nome.py` chamando uma função `renderizar_*` de `ui/`.
- **Texto/estilo de UI**: use os componentes de `ui/styles.py`; não espalhe CSS inline.
- **Nova categoria de unidade**: coluna em `COLUNAS_UNIDADES` e de área em `COLUNAS_*COMPUTAVEIS`,
  entrada em `CATEGORIAS_TIPOLOGIA` e cor em `excel_exporter.CORES_TIPOLOGIA` (variantes antes da base).
- **Testar no navegador (container sem CDN)**: o folium carrega Leaflet de CDNs; em ambiente sem acesso,
  sirva os arquivos via `npm i leaflet leaflet.fullscreen leaflet-measure leaflet-minimap jquery` e
  `page.route` do Playwright.

## 7. Checklist antes de concluir

1. `python -m pytest -q` — tudo verde (inclui `tests/test_arquitetura.py`).
2. Nenhum import de `streamlit`/`ui` em `domain/` ou `services/`.
3. Assinaturas públicas listadas na seção 3 preservadas (ou todos os chamadores atualizados).
4. Novos campos de dataclass com default; unidades e `None` = NA respeitados.
5. Se mudou o pipeline, atualizar este arquivo (seções 3–5).

## 8. Convenções

- Código, nomes e textos em **português**, `snake_case`, type hints, docstrings curtas.
- Constantes em MAIÚSCULAS no topo do módulo; helpers privados com prefixo `_`.
- Comentários de células da planilha no formato `# Q. ÁREAS!D38`.
- Pontos fracos conhecidos (poucos testes): `financeiro_cronograma_engine`, `eletrica_engine`,
  `desnivel_engine`. Ao alterá-los, escreva testes primeiro.
- `__pycache__/`, `.venv/` e `.pytest_cache/` estão no `.gitignore`.
