from lxml import etree as ET

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
    Lê um arquivo de metadados XML e o converte para um dicionário de dados.
    """
    try:
        parser = ET.XMLParser(remove_blank_text=True)
        tree = ET.parse(xml_path, parser)
        root = tree.getroot()
        ns = root.nsmap
        
        data = {}

        # --- PREENCHIMENTO DAS INFORMAÇÕES GERAIS ---
        data['LanguageCode'] = get_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', ns)
        data['characterSet'] = get_element_attribute(root, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', ns)
        data['hierarchyLevel'] = get_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', ns)
        # Nota: dateStamp não é carregado, pois geralmente é gerado no momento do salvamento.

        # --- PREENCHIMENTO DAS INFORMAÇÕES DE IDENTIFICAÇÃO ---
        id_info = root.find('.//gmd:identificationInfo/gmd:MD_DataIdentification', namespaces=ns)
        if id_info is not None:
            data['title'] = get_element_text(id_info, './/gmd:citation//gmd:title/gco:CharacterString', ns)
            data['edition'] = get_element_text(id_info, './/gmd:citation//gmd:edition/gco:CharacterString', ns)
            data['date_creation'] = get_element_text(id_info, './/gmd:citation//gmd:date/gmd:CI_Date/gmd:date/gco:DateTime', ns)
            data['abstract'] = get_element_text(id_info, './gmd:abstract/gco:CharacterString', ns)
            data['status_codeListValue'] = get_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', ns)
            
            # --- PALAVRAS-CHAVE ---
            keywords = []
            keyword_nodes = id_info.findall('.//gmd:descriptiveKeywords//gmd:keyword/gco:CharacterString', namespaces=ns)
            for node in keyword_nodes:
                if node.text:
                    keywords.append(node.text.strip())
            data['MD_Keywords'] = ', '.join(keywords)

            # --- PREENCHIMENTO FINAL ---
            data['MD_SpatialRepresentationTypeCode'] = get_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', ns)
            data['spatialResolution_denominator'] = get_element_text(id_info, './/gmd:spatialResolution//gmd:denominator/gco:Integer', ns)
            data['topicCategory'] = get_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', ns)
            
            # --- BBOX ---
            data['westBoundLongitude'] = get_element_text(id_info, './/gmd:extent//gmd:westBoundLongitude/gco:Decimal', ns)
            data['eastBoundLongitude'] = get_element_text(id_info, './/gmd:extent//gmd:eastBoundLongitude/gco:Decimal', ns)
            data['southBoundLatitude'] = get_element_text(id_info, './/gmd:extent//gmd:southBoundLatitude/gco:Decimal', ns)
            data['northBoundLatitude'] = get_element_text(id_info, './/gmd:extent//gmd:northBoundLatitude/gco:Decimal', ns)

        # --- CONTATO (pega o segundo contato, que corresponde ao formulário) ---
        # Isso busca em todo o documento e pega o segundo CI_ResponsibleParty encontrado
        all_contacts = root.findall('.//gmd:CI_ResponsibleParty', namespaces=ns)
        if len(all_contacts) > 1:
            form_contact = all_contacts[1] # Assume que o segundo contato é o do formulário
            
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
        return None