from lxml import etree as ET
import uuid
import os
from qgis.core import Qgis

# --- FONTE DE DADOS FIXA PARA O PRIMEIRO AUTOR ---
CDHU_CONTACT_DATA = {
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

# --- As funções de ajuda são perfeitas, mantemos como estão ---
def set_element_text(parent_element, xpath, text_value, ns_map):
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and text_value is not None:
        element.text = str(text_value) # Garantimos que o valor seja string

def set_element_attribute(parent_element, xpath, attr_name, attr_value, ns_map):
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and attr_value is not None:
        element.set(attr_name, str(attr_value))

def atualizar_bloco_de_contato(contato_node, data_dict, ns_map):
    if contato_node is None: return
    
    # Define um UUID único para este bloco de contato
    contato_node.set('uuid', str(uuid.uuid4()))
    
    # Preenche todos os campos de texto diretamente do dicionário
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
    
    # Atualiza o ATRIBUTO 'codeListValue' do papel (role) do contato
    set_element_attribute(contato_node, './/gmd:role/gmd:CI_RoleCode', 'codeListValue', data_dict.get('contact_role'), ns_map)


# ---------------------------- ESTA É A NOSSA NOVA FUNÇÃO PRINCIPAL ----------------------------
def generate_xml_from_template(data_dict, template_path):
    """
    Gera uma string XML a partir de um dicionário de dados e um template.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template XML não encontrado em '{template_path}'")

    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(template_path, parser)
    root = tree.getroot()
    ns = root.nsmap
    
    # --- PREENCHIMENTO DOS METADADOS GERAIS ---
    set_element_text(root, './gmd:fileIdentifier/gco:CharacterString', str(uuid.uuid4()), ns)
    set_element_text(root, './gmd:dateStamp/gco:DateTime', data_dict.get('dateStamp'), ns)
    set_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', data_dict.get('LanguageCode'), ns)
    set_element_attribute(root, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', data_dict.get('characterSet'), ns)
    set_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', data_dict.get('hierarchyLevel'), ns)

    # --- ATUALIZA O BLOCO DE CONTATO PRINCIPAL ---
    # Encontra o primeiro bloco de contato no nível raiz e o atualiza
    main_contact = root.find('./gmd:contact/gmd:CI_ResponsibleParty', namespaces=ns)
    if main_contact is not None:
        atualizar_bloco_de_contato(main_contact, data_dict, ns)

    # --- PREENCHIMENTO DAS INFORMAÇÕES DE IDENTIFICAÇÃO ---
    id_info = root.find('.//gmd:identificationInfo/gmd:MD_DataIdentification', namespaces=ns)
    if id_info is not None:
        # Atualiza o bloco de contato DENTRO da seção de identificação
        id_contact = id_info.find('./gmd:pointOfContact/gmd:CI_ResponsibleParty', namespaces=ns)
        if id_contact is not None:
            atualizar_bloco_de_contato(id_contact, data_dict, ns)

        # Preenche os outros campos
        set_element_text(id_info, './/gmd:citation//gmd:title/gco:CharacterString', data_dict.get('title'), ns)
        set_element_text(id_info, './/gmd:citation//gmd:edition/gco:CharacterString', data_dict.get('edition'), ns)
        set_element_text(id_info, './/gmd:citation//gmd:date/gmd:CI_Date/gmd:date/gco:DateTime', data_dict.get('date_creation'), ns)
        set_element_text(id_info, './gmd:abstract/gco:CharacterString', data_dict.get('abstract'), ns)
        set_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', data_dict.get('status_codeListValue'), ns)
        
        # Lógica das Palavras-Chave
        keyword_container = id_info.find('./gmd:descriptiveKeywords', namespaces=ns)
        if keyword_container is not None:
            for node in keyword_container.findall('gmd:MD_Keywords', namespaces=ns):
                keyword_container.remove(node)
            keywords_list = data_dict.get('MD_Keywords', [])
            if keywords_list:
                md_keywords_node = ET.SubElement(keyword_container, f"{{{ns['gmd']}}}MD_Keywords")
                for keyword_text in keywords_list:
                    keyword_node = ET.SubElement(md_keywords_node, f"{{{ns['gmd']}}}keyword")
                    char_string = ET.SubElement(keyword_node, f"{{{ns['gco']}}}CharacterString")
                    char_string.text = keyword_text

        # Preenchimento final
        set_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', data_dict.get('MD_SpatialRepresentationTypeCode'), ns)
        set_element_text(id_info, './/gmd:spatialResolution//gmd:denominator/gco:Integer', data_dict.get('spatialResolution_denominator'), ns)
        set_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', data_dict.get('topicCategory'), ns)
        
        # BBOX
        set_element_text(id_info, './/gmd:extent//gmd:westBoundLongitude/gco:Decimal', data_dict.get('westBoundLongitude'), ns)
        set_element_text(id_info, './/gmd:extent//gmd:eastBoundLongitude/gco:Decimal', data_dict.get('eastBoundLongitude'), ns)
        set_element_text(id_info, './/gmd:extent//gmd:southBoundLatitude/gco:Decimal', data_dict.get('southBoundLatitude'), ns)
        set_element_text(id_info, './/gmd:extent//gmd:northBoundLatitude/gco:Decimal', data_dict.get('northBoundLatitude'), ns)

    # Converte a árvore XML final para uma string bonita e retorna
    xml_output_string = ET.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8').decode('utf-8')
    return xml_output_string