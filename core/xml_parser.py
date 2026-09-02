# xml_parser.py (VERSÃO FINAL COM LEITURA DE UUID)

from lxml import etree as ET
from datetime import datetime, timedelta, timezone
import traceback

# Brasil não observa horário de verão desde 2019 - offset fixo evita depender do pacote
# tzdata (zoneinfo) estar instalado no Python do QGIS.
_BR_TZ = timezone(timedelta(hours=-3))


def _to_local_datetime_str(value):
    """Converte um gmd:date (gco:Date ou gco:DateTime, com ou sem timezone) pro formato
    exato que <input type="datetime-local"> aceita (YYYY-MM-DDTHH:MM, sem timezone) - sem
    essa normalização o navegador REJEITA SILENCIOSAMENTE (campo fica vazio) tanto um
    gco:Date puro (sem componente de hora, ex: "2019-05-14") quanto um gco:DateTime com
    offset (ex: "2019-05-14T00:00:00-03:00") - era essa a causa de "não baixa a data e
    hora de criação" pra registros não criados por este plugin (que só grava DateTime sem
    timezone). Datas com offset são CONVERTIDAS (não truncadas) pro horário de Brasília -
    truncar às cegas mostraria a hora errada sempre que a origem não usar -03:00 (ex: 'Z'/UTC)."""
    if not value:
        return None
    value = value.strip()
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_BR_TZ).replace(tzinfo=None)
    return dt.strftime('%Y-%m-%dT%H:%M')


# --- As funções de ajuda (get_element_text, get_element_attribute) estão perfeitas ---
def get_element_text(parent_element, xpath, ns_map):
    if parent_element is None: return None
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and element.text:
        return element.text.strip()
    return None

def get_element_attribute(parent_element, xpath, attr_name, ns_map):
    if parent_element is None: return None
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None:
        return element.get(attr_name)
    return None

def _parse_responsible_party(rp_node, ns_map):
    """Converte um nó gmd:CI_ResponsibleParty no formato {isManual, data:{...}}
    esperado pelos arrays contacts/metadataAuthorContacts/processorContacts do JS
    (mesmo shape gravado por _build_contact_block em core/xml_generator.py)."""
    if rp_node is None:
        return None
    uuid = rp_node.get('uuid')
    contact = {
        'sigla':    get_element_text(rp_node, './gmd:individualName/gco:CharacterString', ns_map),
        'org':      get_element_text(rp_node, './gmd:organisationName/gco:CharacterString', ns_map),
        'position': get_element_text(rp_node, './gmd:positionName/gco:CharacterString', ns_map),
        'phone':    get_element_text(rp_node, './/gmd:voice/gco:CharacterString', ns_map),
        'address':  get_element_text(rp_node, './/gmd:deliveryPoint/gco:CharacterString', ns_map),
        'city':     get_element_text(rp_node, './/gmd:city/gco:CharacterString', ns_map),
        'state':    get_element_text(rp_node, './/gmd:administrativeArea/gco:CharacterString', ns_map),
        'zip':      get_element_text(rp_node, './/gmd:postalCode/gco:CharacterString', ns_map),
        'country':  get_element_text(rp_node, './/gmd:country/gco:CharacterString', ns_map) or 'Brasil',
        'email':    get_element_text(rp_node, './/gmd:electronicMailAddress/gco:CharacterString', ns_map),
        'role':     get_element_attribute(rp_node, './gmd:role/gmd:CI_RoleCode', 'codeListValue', ns_map) or 'pointOfContact',
    }
    if uuid:
        contact['uuid'] = uuid
    if not contact['org'] and not contact['email'] and not contact['sigla']:
        return None
    # Contato com uuid real veio vinculado ao diretório do GN (xlink:href apontando pra
    # registry) - 'gn' faz o JS mostrar a badge "Catálogo Online" e tratar como não-manual
    # (mesma lógica de _srcToIsManual/hasCatalogContact em app.js). Sem uuid, é manual mesmo.
    return {'isManual': ('gn' if uuid else True), 'data': contact}

def _parse_responsible_party_list(rp_nodes, ns_map):
    result = []
    for node in rp_nodes:
        parsed = _parse_responsible_party(node, ns_map)
        if parsed:
            result.append(parsed)
    return result

# --- A função principal ---
def parse_xml_to_dict(source, is_string=False):
    """
    Lê metadados XML (de um arquivo ou de uma string) e os converte para um dicionário.
    """
    try:
        # --- ETAPA 1: Parsing Único ---
        if is_string:
            # lxml recusa `str` com declaração <?xml ... encoding="..."?> (só aceita
            # bytes nesse caso, pra respeitar o encoding declarado). Praticamente todo
            # XML MGB 2.0 real tem essa declaração - convertendo pra bytes evita o erro
            # "Unicode strings with encoding declaration are not supported".
            if isinstance(source, str):
                source = source.encode('utf-8')
            root = ET.fromstring(source)
        else: # caminho de arquivo
            tree = ET.parse(source)
            root = tree.getroot()

        # --- ETAPA 2: Definição Manual de Namespaces ---
        ns = {
            'gmd': 'http://www.isotc211.org/2005/gmd',
            'gco': 'http://www.isotc211.org/2005/gco',
            'gts': 'http://www.isotc211.org/2005/gts',
            'srv': 'http://www.isotc211.org/2005/srv',
            'gml': 'http://www.opengis.net/gml/3.2',  # tem que bater com o NS usado em xml_generator.py
            'xlink': 'http://www.w3.org/1999/xlink'
        }

        data = {}

        # --- PREENCHIMENTO DAS INFORMAÇÕES GERAIS ---
        # gmd:language na raiz é o idioma do METADADO (campo metadataLanguage do form) -
        # o idioma do DADO (LanguageCode) é um gmd:language separado, dentro de id_info.
        data['metadataLanguage'] = get_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', ns)
        data['characterSet'] = get_element_attribute(root, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', ns)
        data['hierarchyLevel'] = get_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', ns)

        # Sistema de Referência (EPSG)
        ref_id = root.find('.//gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier', namespaces=ns)
        if ref_id is not None:
            data['epsgCode'] = get_element_text(ref_id, './gmd:code/gco:CharacterString', ns)
            data['epsgTitle'] = get_element_text(ref_id, './gmd:codeSpace/gco:CharacterString', ns)

        # <<< NOVA SEÇÃO: Extrai o UUID do próprio metadado para permitir atualizações >>>
        data['metadata_uuid'] = get_element_text(root, './gmd:fileIdentifier/gco:CharacterString', ns)
        if data.get('metadata_uuid'):
            pass
            #print(f"UUID oficial do metadado encontrado no arquivo XML: {data['metadata_uuid']}")

        # Data do próprio metadado (não do dado) - usada para comparar versão local vs. GN
        # e exibida em "Data e hora de criação do metadado" (datetime-local).
        data['dateStamp'] = _to_local_datetime_str(
            get_element_text(root, './gmd:dateStamp/gco:DateTime', ns)
            or get_element_text(root, './gmd:dateStamp/gco:Date', ns)
        )

        # Contatos de metadado (gmd:contact no nível raiz) - array no formato que o
        # form/populateForm espera, espelhando o que _build_contact_block escreve.
        meta_contact_rps = [c.find('./gmd:CI_ResponsibleParty', namespaces=ns)
                             for c in root.findall('./gmd:contact', namespaces=ns)]
        data['metadataAuthorContacts'] = _parse_responsible_party_list(meta_contact_rps, ns)

        # --- PREENCHIMENTO DAS INFORMAÇÕES DE IDENTIFICAÇÃO ---
        id_info = root.find('.//gmd:identificationInfo/gmd:MD_DataIdentification', namespaces=ns)
        if id_info is not None:
            data['title'] = get_element_text(id_info, './/gmd:title/gco:CharacterString', ns)
            data['edition'] = get_element_text(id_info, './/gmd:edition/gco:CharacterString', ns)
            data['date_edition'] = _to_local_datetime_str(
                get_element_text(id_info, './/gmd:editionDate/gco:DateTime', ns)
                or get_element_text(id_info, './/gmd:editionDate/gco:Date', ns)
            )
            # A citação pode ter mais de um gmd:CI_Date (criação/publicação/revisão) - um
            # find() solto e separado pra date/dateType (como antes) pega os dois de nós
            # DIFERENTES quando há mais de uma entrada, podendo misturar por ex. a data de
            # revisão com o rótulo "Criação". Busca todos os CI_Date e prioriza
            # explicitamente o de tipo 'creation'; sem essa entrada, cai no primeiro (caso
            # mais comum: só existe uma data mesmo). Campo do form é "date" (não
            # "date_creation" - mantido também por compat legada).
            ci_dates = id_info.findall('.//gmd:citation//gmd:date/gmd:CI_Date', namespaces=ns)
            ci_date = next(
                (cd for cd in ci_dates if get_element_attribute(
                    cd, './gmd:dateType/gmd:CI_DateTypeCode', 'codeListValue', ns
                ) == 'creation'),
                ci_dates[0] if ci_dates else None
            )
            if ci_date is not None:
                raw_date = get_element_text(ci_date, './gmd:date/gco:DateTime', ns) \
                    or get_element_text(ci_date, './gmd:date/gco:Date', ns)
                data['date'] = _to_local_datetime_str(raw_date)
                data['date_creation'] = data['date']
                data['dateType'] = get_element_attribute(ci_date, './gmd:dateType/gmd:CI_DateTypeCode', 'codeListValue', ns)
            data['abstract'] = get_element_text(id_info, './gmd:abstract/gco:CharacterString', ns)
            data['purpose'] = get_element_text(id_info, './gmd:purpose/gco:CharacterString', ns)
            data['credit'] = get_element_text(id_info, './gmd:credit/gco:CharacterString', ns)
            data['status_codeListValue'] = get_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', ns)

            # Contatos do recurso (gmd:pointOfContact) - array no formato que o form espera.
            resource_contact_rps = [c.find('./gmd:CI_ResponsibleParty', namespaces=ns)
                                     for c in id_info.findall('./gmd:pointOfContact', namespaces=ns)]
            data['contacts'] = _parse_responsible_party_list(resource_contact_rps, ns)

            keywords_list = [node.text.strip() for node in id_info.findall('.//gmd:descriptiveKeywords//gmd:keyword/gco:CharacterString', ns) if node.text]
            data['MD_Keywords'] = keywords_list

            data['MD_SpatialRepresentationTypeCode'] = get_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', ns)
            data['spatialResolution_denominator'] = get_element_text(id_info, './/gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer', ns)
            data['topicCategory'] = get_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', ns)
            
            data['westBoundLongitude'] = get_element_text(id_info, './/gmd:westBoundLongitude/gco:Decimal', ns)
            data['eastBoundLongitude'] = get_element_text(id_info, './/gmd:eastBoundLongitude/gco:Decimal', ns)
            data['southBoundLatitude'] = get_element_text(id_info, './/gmd:southBoundLatitude/gco:Decimal', ns)
            data['northBoundLatitude'] = get_element_text(id_info, './/gmd:northBoundLatitude/gco:Decimal', ns)

            # Extensão temporal (gml:TimePeriod)
            data['temporalFrom'] = get_element_text(id_info, './/gmd:temporalElement//gml:TimePeriod/gml:beginPosition', ns)
            data['temporalTo'] = get_element_text(id_info, './/gmd:temporalElement//gml:TimePeriod/gml:endPosition', ns)

            # Idioma do DADO (distinto do idioma do metadado, extraído lá em cima da raiz).
            data['LanguageCode'] = get_element_attribute(id_info, './gmd:language/gmd:LanguageCode', 'codeListValue', ns)

            # Manutenção (frequência de atualização / próxima atualização)
            maint = id_info.find('./gmd:resourceMaintenance/gmd:MD_MaintenanceInformation', namespaces=ns)
            if maint is not None:
                data['maintenanceFrequency'] = get_element_attribute(maint, './gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode', 'codeListValue', ns)
                # Campo do form é <input type="date"> (sem hora) - se a origem gravou
                # gco:DateTime, corta pra YYYY-MM-DD via _to_local_datetime_str (o valor
                # completo com hora/timezone seria rejeitado silenciosamente pelo navegador
                # num campo type="date", mesma causa raiz dos outros campos de data).
                raw_next_update = get_element_text(maint, './gmd:dateOfNextUpdate/gco:DateTime', ns) \
                    or get_element_text(maint, './gmd:dateOfNextUpdate/gco:Date', ns)
                normalized_next_update = _to_local_datetime_str(raw_next_update)
                data['dateOfNextUpdate'] = normalized_next_update[:10] if normalized_next_update else None

            # Restrições de acesso / uso / licença
            md_legal = id_info.find('./gmd:resourceConstraints/gmd:MD_LegalConstraints', namespaces=ns)
            if md_legal is not None:
                data['useLimitation'] = get_element_text(md_legal, './gmd:useLimitation/gco:CharacterString', ns)
                data['accessConstraints'] = get_element_attribute(md_legal, './gmd:accessConstraints/gmd:MD_RestrictionCode', 'codeListValue', ns)
                data['useConstraints'] = get_element_attribute(md_legal, './gmd:useConstraints/gmd:MD_RestrictionCode', 'codeListValue', ns)
                data['otherConstraints'] = get_element_text(md_legal, './gmd:otherConstraints/gco:CharacterString', ns)

            data['thumbnail_url'] = get_element_text(id_info, './gmd:graphicOverview/gmd:MD_BrowseGraphic/gmd:fileName/gco:CharacterString', ns)

        # --- QUALIDADE / LINHAGEM (gmd:dataQualityInfo) ────────────────────────
        lineage = root.find('.//gmd:dataQualityInfo/gmd:DQ_DataQuality/gmd:lineage/gmd:LI_Lineage', namespaces=ns)
        if lineage is not None:
            data['statement'] = get_element_text(lineage, './gmd:statement/gco:CharacterString', ns)
            li_proc = lineage.find('./gmd:processStep/gmd:LI_ProcessStep', namespaces=ns)
            if li_proc is not None:
                data['processStep'] = get_element_text(li_proc, './gmd:description/gco:CharacterString', ns)
                proc_rps = [c.find('./gmd:CI_ResponsibleParty', namespaces=ns)
                            for c in li_proc.findall('./gmd:processor', namespaces=ns)]
                data['processorContacts'] = _parse_responsible_party_list(proc_rps, ns)
            data['sourceDescription'] = get_element_text(lineage, './gmd:source/gmd:LI_Source/gmd:description/gco:CharacterString', ns)

        # --- LEITURA DOS DADOS DA CAMADA ---
        dist_info = root.find('./gmd:distributionInfo/gmd:MD_Distribution', namespaces=ns)
        if dist_info is not None:
            online_resources = dist_info.findall('.//gmd:onLine/gmd:CI_OnlineResource', namespaces=ns)

            # Array no formato esperado por distResources/collectFormData (onlineResources).
            resources_list = []
            wms_data = {}
            wfs_data = {}

            for online_resource in online_resources:
                protocol = get_element_text(online_resource, './gmd:protocol/gco:CharacterString', ns)
                url = get_element_text(online_resource, './gmd:linkage/gmd:URL', ns)
                name = get_element_text(online_resource, './gmd:name/gco:CharacterString', ns)
                description = get_element_text(online_resource, './gmd:description/gco:CharacterString', ns)
                if url:
                    resources_list.append({
                        'url': url, 'protocol': protocol or '',
                        'name': name or '', 'description': description or ''
                    })

                # Mantido por compatibilidade com código legado que ainda lê wms_data/wfs_data.
                if protocol == 'OGC:WMS':
                    wms_data['geoserver_layer_name'] = name
                    wms_data['geoserver_layer_title'] = description
                    wms_data['online_protocol'] = protocol
                    if url and '/ows?' in url:
                        wms_data['geoserver_base_url'] = url.split('/ows?')[0]
                elif protocol == 'OGC:WFS':
                    wfs_data['geoserver_layer_name'] = name
                    wfs_data['geoserver_layer_title'] = description
                    wfs_data['online_protocol'] = protocol
                    if url and '/wfs' in url:
                        wfs_data['geoserver_base_url'] = url.split('/wfs')[0]

            data['onlineResources'] = resources_list
            data['wms_data'] = wms_data
            data['wfs_data'] = wfs_data

        all_contacts = root.findall('.//gmd:CI_ResponsibleParty', namespaces=ns)
        user_contact_node = None # Usando um nome mais claro que 'form_contact'

        # ETAPA 1: Tenta encontrar um contato que NÃO seja o padrão (CDHU).
        for contact in all_contacts:
            org_name = get_element_text(contact, './gmd:organisationName/gco:CharacterString', ns)
            if org_name and 'Companhia de Desenvolvimento Habitacional e Urbano' not in org_name:
                user_contact_node = contact
                break # Encontramos o contato do usuário (ex: DPDU), podemos parar.

        # ETAPA 2: Se não encontrou um contato distinto (PLANO B).
        if user_contact_node is None:
            # ...significa que ou não há contatos, ou o único contato é o da CDHU.
            # Neste caso, simplesmente pegamos o primeiro contato que encontrarmos.
            if all_contacts: # Verifica se a lista não está vazia.
                user_contact_node = all_contacts[0]

        # ETAPA 3: Preenche os dados se um contato foi encontrado (seja o do usuário ou o fallback).
        if user_contact_node is not None:
            data['contact_individualName'] = get_element_text(user_contact_node, './/gmd:individualName/gco:CharacterString', ns)
            data['contact_organisationName'] = get_element_text(user_contact_node, './/gmd:organisationName/gco:CharacterString', ns)
            data['contact_positionName'] = get_element_text(user_contact_node, './/gmd:positionName/gco:CharacterString', ns)
            data['contact_phone'] = get_element_text(user_contact_node, './/gmd:contactInfo//gmd:voice/gco:CharacterString', ns)
            data['contact_deliveryPoint'] = get_element_text(user_contact_node, './/gmd:contactInfo//gmd:deliveryPoint/gco:CharacterString', ns)
            data['contact_city'] = get_element_text(user_contact_node, './/gmd:contactInfo//gmd:city/gco:CharacterString', ns)
            data['contact_administrativeArea'] = get_element_text(user_contact_node, './/gmd:contactInfo//gmd:administrativeArea/gco:CharacterString', ns)
            data['contact_postalCode'] = get_element_text(user_contact_node, './/gmd:contactInfo//gmd:postalCode/gco:CharacterString', ns)
            data['contact_country'] = get_element_text(user_contact_node, './/gmd:contactInfo//gmd:country/gco:CharacterString', ns)
            data['contact_email'] = get_element_text(user_contact_node, './/gmd:contactInfo//gmd:electronicMailAddress/gco:CharacterString', ns)
            data['contact_role'] = get_element_attribute(user_contact_node, './/gmd:role/gmd:CI_RoleCode', 'codeListValue', ns)

        return data

    except Exception as e:
        print(f"Não foi possível parsear o arquivo XML: {e}")
        traceback.print_exc()
        return None
    