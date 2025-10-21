# xml_parser.py (VERSÃO FINAL COM LEITURA DE UUID)

from lxml import etree as ET

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

# --- A função principal, agora limpa e corrigida ---
def parse_xml_to_dict(xml_path):
    """
    Lê um arquivo de metadados XML e o converte para um dicionário de dados,
    incluindo informações de distribuição e thumbnail.
    """
    try:
        parser = ET.XMLParser(remove_blank_text=True)
        tree = ET.parse(xml_path, parser)
        root = tree.getroot()
        ns = {k if k is not None else 'gmd': v for k, v in root.nsmap.items()}
        
        data = {}

        # --- PREENCHIMENTO DAS INFORMAÇÕES GERAIS ---
        data['LanguageCode'] = get_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', ns)
        data['characterSet'] = get_element_attribute(root, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', ns)
        data['hierarchyLevel'] = get_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', ns)

        # <<< NOVA SEÇÃO: Extrai o UUID do próprio metadado para permitir atualizações >>>
        data['metadata_uuid'] = get_element_text(root, './gmd:fileIdentifier/gco:CharacterString', ns)
        if data.get('metadata_uuid'):
            print(f"UUID oficial do metadado encontrado no arquivo XML: {data['metadata_uuid']}")
        
        # --- PREENCHIMENTO DAS INFORMAÇÕES DE IDENTIFICAÇÃO ---
        id_info = root.find('.//gmd:identificationInfo/gmd:MD_DataIdentification', namespaces=ns)
        if id_info is not None:
            data['title'] = get_element_text(id_info, './/gmd:title/gco:CharacterString', ns)
            data['edition'] = get_element_text(id_info, './/gmd:edition/gco:CharacterString', ns)
            data['date_creation'] = get_element_text(id_info, './/gmd:date//gmd:date/gco:DateTime', ns)
            data['abstract'] = get_element_text(id_info, './gmd:abstract/gco:CharacterString', ns)
            data['status_codeListValue'] = get_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', ns)
            
            keywords = [node.text.strip() for node in id_info.findall('.//gmd:descriptiveKeywords//gmd:keyword/gco:CharacterString', ns) if node.text]
            data['MD_Keywords'] = ', '.join(keywords)

            data['MD_SpatialRepresentationTypeCode'] = get_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', ns)
            data['spatialResolution_denominator'] = get_element_text(id_info, './/gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer', ns)
            data['topicCategory'] = get_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', ns)
            
            data['westBoundLongitude'] = get_element_text(id_info, './/gmd:westBoundLongitude/gco:Decimal', ns)
            data['eastBoundLongitude'] = get_element_text(id_info, './/gmd:eastBoundLongitude/gco:Decimal', ns)
            data['southBoundLatitude'] = get_element_text(id_info, './/gmd:southBoundLatitude/gco:Decimal', ns)
            data['northBoundLatitude'] = get_element_text(id_info, './/gmd:northBoundLatitude/gco:Decimal', ns)

            data['thumbnail_url'] = get_element_text(id_info, './gmd:graphicOverview/gmd:MD_BrowseGraphic/gmd:fileName/gco:CharacterString', ns)

        # --- LEITURA DOS DADOS DA CAMADA ---
        dist_info = root.find('./gmd:distributionInfo/gmd:MD_Distribution', namespaces=ns)
        if dist_info is not None:
            online_resources = dist_info.findall('.//gmd:onLine/gmd:CI_OnlineResource', namespaces=ns)
            
            wms_data = {}
            wfs_data = {}

            for online_resource in online_resources:
                protocol = get_element_text(online_resource, './gmd:protocol/gco:CharacterString', ns)
                if protocol == 'OGC:WMS':
                    wms_data['geoserver_layer_name'] = get_element_text(online_resource, './gmd:name/gco:CharacterString', ns)
                    wms_data['geoserver_layer_title'] = get_element_text(online_resource, './gmd:description/gco:CharacterString', ns)
                    wms_data['online_protocol'] = protocol
                    
                    linkage_url = get_element_text(online_resource, './gmd:linkage/gmd:URL', ns)
                    if linkage_url and '/ows?' in linkage_url:
                        wms_data['geoserver_base_url'] = linkage_url.split('/ows?')[0]
                elif protocol == 'OGC:WFS':
                    wfs_data['geoserver_layer_name'] = get_element_text(online_resource, './gmd:name/gco:CharacterString', ns)
                    wfs_data['geoserver_layer_title'] = get_element_text(online_resource, './gmd:description/gco:CharacterString', ns)
                    wfs_data['online_protocol'] = protocol
                    
                    linkage_url = get_element_text(online_resource, './gmd:linkage/gmd:URL', ns)
                    if linkage_url and '/wfs' in linkage_url:
                        wfs_data['geoserver_base_url'] = linkage_url.split('/wfs')[0]

            data['wms_data'] = wms_data
            data['wfs_data'] = wfs_data

        # --- LÓGICA DE CONTATO ---
        all_contacts = root.findall('.//gmd:CI_ResponsibleParty', namespaces=ns)
        form_contact = None
        for contact in all_contacts:
            org_name = get_element_text(contact, './gmd:organisationName/gco:CharacterString', ns)
            # Este critério de exclusão é específico do seu caso, parece correto.
            if org_name and 'Companhia de Desenvolvimento Habitacional e Urbano' not in org_name:
                form_contact = contact
                break 
        
        if form_contact is not None:
            data['contact_individualName'] = get_element_text(form_contact, './/gmd:individualName/gco:CharacterString', ns)
            data['contact_organisationName'] = get_element_text(form_contact, './/gmd:organisationName/gco:CharacterString', ns)
            data['contact_positionName'] = get_element_text(form_contact, './/gmd:positionName/gco:CharacterString', ns)
            data['contact_phone'] = get_element_text(form_contact, './/gmd:contactInfo//gmd:voice/gco:CharacterString', ns)
            data['contact_deliveryPoint'] = get_element_text(form_contact, './/gmd:contactInfo//gmd:deliveryPoint/gco:CharacterString', ns)
            data['contact_city'] = get_element_text(form_contact, './/gmd:contactInfo//gmd:city/gco:CharacterString', ns)
            data['contact_administrativeArea'] = get_element_text(form_contact, './/gmd:contactInfo//gmd:administrativeArea/gco:CharacterString', ns)
            data['contact_postalCode'] = get_element_text(form_contact, './/gmd:contactInfo//gmd:postalCode/gco:CharacterString', ns)
            data['contact_country'] = get_element_text(form_contact, './/gmd:contactInfo//gmd:country/gco:CharacterString', ns)
            data['contact_email'] = get_element_text(form_contact, './/gmd:contactInfo//gmd:electronicMailAddress/gco:CharacterString', ns)
            data['contact_role'] = get_element_attribute(form_contact, './/gmd:role/gmd:CI_RoleCode', 'codeListValue', ns)

        return data

    except Exception as e:
        print(f"Não foi possível parsear o arquivo XML: {e}")
        import traceback
        traceback.print_exc()
        return None
    