# Plano: Reestabelecimento da Geração de XML ISO 19139 / MGB 2.0

## Contexto e Diagnóstico

A geração de XML atual usa `assets/tamplate_mgb20.xml` como esqueleto estático. O `xml_generator.py` navega por esse template via XPath e substitui valores. Esse modelo tem **4 problemas estruturais**:

1. **Engessamento por template**: campos faltando no template → campo ausente no XML gerado, silenciosamente.
2. **Contatos fixos (2 hardcoded)**: o template assume sempre exatamente 2 `gmd:contact` e 2 `gmd:pointOfContact`. Os novos contatos múltiplos do formulário são ignorados.
3. **Campos novos não mapeados**: campos adicionados no formulário (`credit`, `maintenanceFrequency`, `purpose`, `epsgCode`, `temporalExtent`, `licença`, `qualidade`) **não estão no template** e **não são gerados**.
4. **Incompatibilidade com QGIS/validadores**: o `codeList` de alguns atributos aponta para caminhos relativos (`./resources/codeList.xml`) em vez das URLs canônicas ISO 19139, causando erros ao importar em QGIS/GeoNetwork.

---

## Análise das Abordagens

### Opção A - Geração Programática Pura (sem template)
Construir o XML diretamente via `lxml.etree`, criando cada elemento com namespaces corretos.

| Prós | Contras |
|---|---|
| Controle total da estrutura | Mais código a escrever |
| Funciona 100% offline | - |
| Suporta N contatos, N keywords | - |
| CodeLists corretos desde a origem | - |
| Fácil adicionar novos campos | - |
| Sem dependência de arquivo externo | - |

### Opção B - Template XML Enriquecido (abordagem atual melhorada)
Ampliar o `tamplate_mgb20.xml` para incluir todos os novos campos, e ajustar o `xml_generator.py`.

| Prós | Contras |
|---|---|
| Menos refatoração | Continua frágil para N contatos |
| Mais fácil de visualizar a estrutura | Dois arquivos para manter em sincronia |
| - | Exige regenerar o template para novos campos |

### Opção C - Template + Geração Híbrida
Usar um template mínimo apenas para namespaces/cabeçalho e gerar o corpo programaticamente.

> [!TIP]
> **Recomendação: Opção A (Geração Programática Pura)**
> É o padrão adotado por implementações ISO 19139 maduras (ex: `pygeometa`, `OWSLib`). Elimina todos os problemas de uma vez, funciona offline, e é a base correta para um futuro validador. O esforço extra é justificado pela robustez.

---

## Open Questions

> [!IMPORTANT]
> **Decisão 1 - Abordagem:** Confirmar Opção A (geração programática) ou Opção B (ampliar template)?
> A Opção A é recomendada, mas a B é mais rápida para entregar no curto prazo.

> [!IMPORTANT]
> **Decisão 2 - Contatos múltiplos:** O formulário agora suporta N contatos do recurso e N contatos de metadado. No XML, cada um deve gerar um `<gmd:contact>` ou `<gmd:pointOfContact>` separado. Confirmar esse comportamento?

> [!WARNING]
> **MGB 2.0 vs ISO 19139 puro:** O "MGB 2.0" não tem esquema XSD oficial publicado. Na prática, os XMLs que o GeoNetwork aceita são **ISO 19139 com perfil MGB** (sem extensão de esquema formal). Isso significa que podemos gerar ISO 19139 puro com as CodeLists corretas e ele será válido tanto no QGIS quanto no GeoNetwork.

---

## Campos Atualmente Não Gerados (novos do formulário)

| Campo no Formulário | Elemento XML ISO 19139 | Situação |
|---|---|---|
| `credit` | `gmd:credit/gco:CharacterString` | ❌ Ausente |
| `maintenanceFrequency` | `gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode` | ❌ Ausente |
| `purpose` | `gmd:purpose/gco:CharacterString` | ❌ Ausente |
| `epsgCode` / `epsgTitle` | `gmd:referenceSystemInfo/gmd:MD_ReferenceSystem` | ❌ Ausente |
| `temporalFrom/To` | `gmd:EX_TemporalExtent` dentro de `gmd:extent` | ❌ Ausente |
| `statement` | `gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:lineage/gmd:LI_Lineage/gmd:statement` | ❌ Ausente |
| `processStep` | `gmd:LI_ProcessStep/gmd:description` | ❌ Ausente |
| `useLimitation` | `gmd:resourceConstraints/gmd:MD_Constraints/gmd:useLimitation` | ❌ Ausente |
| `accessConstraints` | `gmd:MD_LegalConstraints/gmd:accessConstraints/gmd:MD_RestrictionCode` | ❌ Ausente |
| `metadataLanguage` | `gmd:language` no nível raiz (metadado, não dado) | ⚠️ Confundido com `LanguageCode` |
| Contatos do Metadado | `gmd:contact` (raiz) | ⚠️ Fixo em 2 hardcoded |
| N contatos do recurso | `gmd:pointOfContact` | ⚠️ Fixo em 2 hardcoded |
| `dateType` | `gmd:CI_DateTypeCode/@codeListValue` | ⚠️ Hardcoded como "criation" no template |

---

## Problemas de CodeList (incompatibilidade QGIS)

O template usa caminhos relativos inválidos fora do GeoNetwork:
```xml
<!-- ERRADO (só funciona dentro do GeoNetwork) -->
<gmd:CI_RoleCode codeList="./resources/codeList.xml#CI_RoleCode" .../>

<!-- CORRETO (ISO 19139 canônico, funciona no QGIS e validadores) -->
<gmd:CI_RoleCode codeList="http://standards.iso.org/iso/19139/resources/gmxCodelists.xml#CI_RoleCode" .../>
```

---

## Proposed Changes

### Se aprovada Opção A (Programática Pura)

---

#### [MODIFY] [xml_generator.py](file:///c:/Users/mdaviz/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/qgis-geometadata-plugin/core/xml_generator.py)
- Reescrever `generate_xml_from_template()` → `generate_xml(data_dict, cdhu_data)` sem template.
- Construir programaticamente toda a estrutura `gmd:MD_Metadata`.
- Suportar N contatos do recurso e N contatos de metadado (iterando sobre listas).
- Mapear todos os campos novos listados acima.
- Usar CodeLists canônicas ISO 19139 em todos os elementos.
- Adicionar `gmd:metadataStandardName` = "ISO 19115" e `gmd:metadataStandardVersion` = "2003/Cor.1:2006".

#### [MODIFY] [GeoMetadata_dialog.py](file:///c:/Users/mdaviz/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/qgis-geometadata-plugin/GeoMetadata_dialog.py)
- Remover a passagem de `template_path` nas chamadas `exportar_to_xml`, `exportar_to_geo`, `save_metadata`.
- Adaptar assinatura de chamada para a nova função `generate_xml(data, cdhu_data)`.

#### [MODIFY] [tamplate_mgb20.xml](file:///c:/Users/mdaviz/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/qgis-geometadata-plugin/assets/tamplate_mgb20.xml) *(se Opção B)*
- Alternativa: ampliar o template com os campos faltantes e corrigir CodeLists.
- Manter como referência de estrutura mesmo com Opção A.

---

### Se aprovada Opção B (Template Enriquecido)

#### [MODIFY] [tamplate_mgb20.xml](file:///c:/Users/mdaviz/AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\qgis-geometadata-plugin\assets\tamplate_mgb20.xml)
- Adicionar todos os blocos faltantes (credit, maintenance, purpose, SRS, temporal, qualidade, licença).
- Corrigir todas as CodeLists para URLs canônicas.
- Expandir para suportar N contatos via blocos repetíveis.

#### [MODIFY] [xml_generator.py](file:///c:/Users/mdaviz/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/qgis-geometadata-plugin/core/xml_generator.py)
- Mapear novos campos no gerador.
- Implementar loop para N contatos (removendo a lógica de 2 fixos).
- Corrigir `dateType` para ser dinâmico em vez de hardcoded.

---

## Verification Plan

### Automated Tests
- Gerar um XML com o novo gerador e validar com `xmllint --schema iso19139.xsd` (offline).
- Importar o XML no QGIS via "Adicionar Camada" e verificar que os campos são lidos corretamente.
- Publicar no GeoNetwork de homologação e verificar que o registro aparece sem erros de validação.

### Manual Verification
- Verificar que todos os campos do formulário aparecem no XML gerado.
- Verificar que N contatos do recurso geram N `<gmd:pointOfContact>` no XML.
- Verificar compatibilidade com o QGIS Metadata Editor (importar o XML exportado).
