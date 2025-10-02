from lxml import etree as ET
import uuid
import os
from qgis.core import Qgis

# --- FONTE DE DADOS FIXA PARA O PRIMEIRO AUTOR (CDHU) ---
CDHU_CONTACT_DATA = {
    'uuid': 'b98c4847-4d5c-43e1-a5eb-bd0228f6903a',
    'contact_individualName': 'CDHU',
    'contact_organisationName': 'Companhia de Desenvolvimento Habitacional e Urbano',
    'contact_positionName': '/',
    'contact_phone': '+55 11 2505-2479',
    'contact_deliveryPoint': 'Rua Boa Vista, 170 - Sé',
    'contact_city': 'São Paulo',
    'contact_postalCode': '01014-930',
    'contact_country': 'Brasil',
    'contact_email': 'geo@cdhu.sp.gov.br',
    'contact_administrativeArea': 'SP', 
    'contact_role': 'owner'            
}

# --- FUNÇÕES DE AJUDA ---
def set_element_text(parent_element, xpath, text_value, ns_map):
    """Encontra um elemento via XPath e define seu texto."""
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and text_value is not None:
        element.text = str(text_value)

def set_element_attribute(parent_element, xpath, attr_name, attr_value, ns_map):
    """Encontra um elemento via XPath e define um de seus atributos."""
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and attr_value is not None:
        element.set(attr_name, str(attr_value))

def atualizar_bloco_de_contato(contato_node, data_dict, ns_map):
    """Preenche um nó XML de CI_ResponsibleParty com dados de um dicionário."""
    if contato_node is None:
        return
    
    uuid_fornecido = data_dict.get('uuid')
    if uuid_fornecido:
        contato_node.set('uuid', uuid_fornecido)
    else:
        contato_node.set('uuid', str(uuid.uuid4()))
    
    set_element_text(contato_node, './/gmd:individualName/gco:CharacterString', data_dict.get('contact_individualName'), ns_map)
    set_element_text(contato_node, './/gmd:organisationName/gco:CharacterString', data_dict.get('contact_organisationName'), ns_map)
    set_element_text(contato_node, './/gmd:positionName/gco:CharacterString', data_dict.get('contact_positionName'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:voice/gco:CharacterString', data_dict.get('contact_phone'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:deliveryPoint/gco:CharacterString', data_dict.get('contact_deliveryPoint'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:city/gco:CharacterString', data_dict.get('contact_city'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:administrativeArea/gco:CharacterString', data_dict.get('contact_administrativeArea'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:postalCode/gco:CharacterString', data_dict.get('contact_postalCode'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:country/gco:CharacterString', data_dict.get('contact_country'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:electronicMailAddress/gco:CharacterString', data_dict.get('contact_email'), ns_map)
    set_element_attribute(contato_node, './/gmd:role/gmd:CI_RoleCode', 'codeListValue', data_dict.get('contact_role'), ns_map)

def remove_element_if_exists(parent_element, xpath, ns_map):
    """Encontra um elemento pelo XPath e o remove da árvore se ele existir."""
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None:
        element.getparent().remove(element)

# ---------------------------- FUNÇÃO PRINCIPAL ----------------------------
def generate_xml_from_template(data_dict, template_path):
    """
    Gera uma string XML a partir de um dicionário de dados e um template,
    preenchendo, removendo campos e ajustando os atributos xlink:href.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template XML não encontrado em '{template_path}'")

    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(template_path, parser)
    root = tree.getroot()
    
    # Define o mapa de namespaces de forma estática para garantir consistência
    ns = {
        'gmd': 'http://www.isotc211.org/2005/gmd',
        'gco': 'http://www.isotc211.org/2005/gco',
        'srv': 'http://www.isotc211.org/2005/srv',
        'gmx': 'http://www.isotc211.org/2005/gmx',
        'gts': 'http://www.isotc211.org/2005/gts',
        'gsr': 'http://www.isotc211.org/2005/gsr',
        'gmi': 'http://www.isotc211.org/2005/gmi',
        'xlink': 'http://www.w3.org/1999/xlink',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }

    # ETAPA 1: Preenche os dados nos blocos de contato
    contatos_raiz = root.findall('./gmd:contact/gmd:CI_ResponsibleParty', namespaces=ns)
    if len(contatos_raiz) >= 2:
        atualizar_bloco_de_contato(contatos_raiz[0], CDHU_CONTACT_DATA, ns)
        atualizar_bloco_de_contato(contatos_raiz[1], data_dict, ns)
        for extra_contact_wrapper in root.findall('./gmd:contact', namespaces=ns)[2:]:
             root.remove(extra_contact_wrapper)

    id_info = root.find('.//gmd:identificationInfo/gmd:MD_DataIdentification', namespaces=ns)
    if id_info is not None:
        contatos_id = id_info.findall('./gmd:pointOfContact/gmd:CI_ResponsibleParty', namespaces=ns)
        if len(contatos_id) >= 2:
            atualizar_bloco_de_contato(contatos_id[0], data_dict, ns)
            atualizar_bloco_de_contato(contatos_id[1], CDHU_CONTACT_DATA, ns)
            for extra_contact_wrapper in id_info.findall('./gmd:pointOfContact', namespaces=ns)[2:]:
                id_info.remove(extra_contact_wrapper)

    # ETAPA 2: Preenche os metadados gerais
    set_element_text(root, './gmd:fileIdentifier/gco:CharacterString', str(uuid.uuid4()), ns)
    set_element_text(root, './gmd:dateStamp/gco:DateTime', data_dict.get('dateStamp'), ns)
    set_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', data_dict.get('LanguageCode'), ns)
    set_element_attribute(root, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', data_dict.get('characterSet'), ns)
    hierarchy_level_value = data_dict.get('hierarchyLevel')
    set_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', hierarchy_level_value, ns)

    if id_info is not None:
        set_element_text(id_info, './/gmd:citation//gmd:title/gco:CharacterString', data_dict.get('title'), ns)
        set_element_text(id_info, './/gmd:citation//gmd:edition/gco:CharacterString', data_dict.get('edition'), ns)
        set_element_text(id_info, './/gmd:citation//gmd:date/gmd:CI_Date/gmd:date/gco:DateTime', data_dict.get('date_creation'), ns)
        set_element_text(id_info, './gmd:abstract/gco:CharacterString', data_dict.get('abstract'), ns)
        set_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', data_dict.get('status_codeListValue'), ns)
        
        keyword_container = id_info.find('./gmd:descriptiveKeywords/gmd:MD_Keywords', namespaces=ns)
        if keyword_container is not None:
            for kw_node in keyword_container.findall('gmd:keyword', namespaces=ns):
                keyword_container.remove(kw_node)
            keywords_list = data_dict.get('MD_Keywords', [])
            if keywords_list:
                for keyword_text in keywords_list:
                    keyword_node = ET.SubElement(keyword_container, f"{{{ns['gmd']}}}keyword")
                    char_string = ET.SubElement(keyword_node, f"{{{ns['gco']}}}CharacterString")
                    char_string.text = keyword_text

        spatial_levels = ['dataset', 'series', 'feature', 'service']
        if hierarchy_level_value in spatial_levels:
            set_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', data_dict.get('MD_SpatialRepresentationTypeCode'), ns)
            set_element_text(id_info, './/gmd:spatialResolution//gmd:denominator/gco:Integer', data_dict.get('spatialResolution_denominator'), ns)
            set_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', data_dict.get('topicCategory'), ns)
            set_element_text(id_info, './/gmd:extent//gmd:westBoundLongitude/gco:Decimal', data_dict.get('westBoundLongitude'), ns)
            set_element_text(id_info, './/gmd:extent//gmd:eastBoundLongitude/gco:Decimal', data_dict.get('eastBoundLongitude'), ns)
            set_element_text(id_info, './/gmd:extent//gmd:southBoundLatitude/gco:Decimal', data_dict.get('southBoundLatitude'), ns)
            set_element_text(id_info, './/gmd:extent//gmd:northBoundLatitude/gco:Decimal', data_dict.get('northBoundLatitude'), ns)
        else:
            remove_element_if_exists(id_info, './gmd:spatialRepresentationType', ns)
            remove_element_if_exists(id_info, './gmd:spatialResolution', ns)
            remove_element_if_exists(id_info, './gmd:topicCategory', ns)
            remove_element_if_exists(id_info, './gmd:extent', ns)

    # ETAPA 3: LÓGICA INTELIGENTE DE ATUALIZAÇÃO DOS LINKS xlink:href (Assosicar ao diretório de contatos)
    for el in root.xpath('.//*[@xlink:href]', namespaces=ns):
        responsible_party_node = el.find('.//gmd:CI_ResponsibleParty', namespaces=ns)
        if responsible_party_node is None:
            continue

        uuid_especifico = responsible_party_node.get('uuid')
        role_node = responsible_party_node.find('.//gmd:role/gmd:CI_RoleCode', namespaces=ns)
        role_especifico = role_node.get('codeListValue') if role_node is not None else None

        # Pega o link original
        xlink_href = el.attrib['{http://www.w3.org/1999/xlink}href']
        
        # Substitui os placeholders diretamente na string, onde quer que eles estejam
        if uuid_especifico:
            xlink_href = xlink_href.replace('{uuid}', uuid_especifico)
        if role_especifico:
            xlink_href = xlink_href.replace('{contact_role}', role_especifico)
        
        # Define o novo link, agora corrigido
        el.attrib['{http://www.w3.org/1999/xlink}href'] = xlink_href

    # ETAPA 4: Serializa o XML final para uma string
    xml_output_string = ET.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8').decode('utf-8')
    return xml_output_string