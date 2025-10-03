from lxml import etree as ET

# As funções de ajuda (get_element_text, get_element_attribute) continuam perfeitas.
def get_element_text(parent_element, xpath, ns_map):
    """Encontra um elemento via XPath e retorna seu texto, ou None se não encontrar."""
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and element.text:
        return element.text.strip()
    return None

def get_element_attribute(parent_element, xpath, attr_name, ns_map):
    """Encontra um elemento e retorna o valor de um de seus atributos."""
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None:
        return element.get(attr_name)
    return None


def parse_xml_to_dict(xml_path):
    """
    Lê um arquivo de metadados XML e o converte para um dicionário de dados,
    incluindo informações de distribuição e thumbnail.
    """
    try:
        parser = ET.XMLParser(remove_blank_text=True)
        tree = ET.parse(xml_path, parser)
        root = tree.getroot()
        # <<<< MUDANÇA: Lógica de namespace mais robusta para evitar problemas com namespaces padrão >>>>
        ns = {k if k is not None else 'gmd': v for k, v in root.nsmap.items()}
        
        data = {}

        # --- PREENCHIMENTO DAS INFORMAÇÕES GERAIS ---
        data['LanguageCode'] = get_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', ns)
        data['characterSet'] = get_element_attribute(root, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', ns)
        data['hierarchyLevel'] = get_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', ns)

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
            data['spatialResolution_denominator'] = get_element_text(id_info, './/gmd:spatialResolution//gmd:denominator/gco:Integer', ns)
            data['topicCategory'] = get_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', ns)
            
            data['westBoundLongitude'] = get_element_text(id_info, './/gmd:extent//gmd:westBoundLongitude/gco:Decimal', ns)
            data['eastBoundLongitude'] = get_element_text(id_info, './/gmd:extent//gmd:eastBoundLongitude/gco:Decimal', ns)
            data['southBoundLatitude'] = get_element_text(id_info, './/gmd:extent//gmd:southBoundLatitude/gco:Decimal', ns)
            data['northBoundLatitude'] = get_element_text(id_info, './/gmd:extent//gmd:northBoundLatitude/gco:Decimal', ns)

            # <<<< NOVO: Extrai a URL da thumbnail se ela existir >>>>
            data['thumbnail_url'] = get_element_text(id_info, './/gmd:graphicOverview/gmd:MD_BrowseGraphic/gmd:fileName/gco:CharacterString', ns)

        # <<<< NOVO: Extrai informações de distribuição se existirem >>>>
        dist_info = root.find('.//gmd:distributionInfo/gmd:MD_Distribution', namespaces=ns)
        if dist_info:
            online_resource = dist_info.find('.//gmd:onLine/gmd:CI_OnlineResource', namespaces=ns)
            if online_resource:
                data['geoserver_layer_name'] = get_element_text(online_resource, './gmd:name/gco:CharacterString', ns)
                data['online_protocol'] = get_element_text(online_resource, './gmd:protocol/gco:CharacterString', ns)

        # <<<< MUDANÇA: Lógica de busca de contato mais robusta >>>>
        # Em vez de pegar o segundo contato, procuramos por um que NÃO seja o da CDHU.
        all_contacts = root.findall('.//gmd:CI_ResponsibleParty', namespaces=ns)
        form_contact = None
        for contact in all_contacts:
            org_name = get_element_text(contact, './gmd:organisationName/gco:CharacterString', ns)
            if org_name and 'Companhia de Desenvolvimento Habitacional e Urbano' not in org_name:
                form_contact = contact
                break 
        
        # Fallback para o método antigo se a lógica acima falhar
        if form_contact is None and len(all_contacts) > 1:
            form_contact = all_contacts[1]

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