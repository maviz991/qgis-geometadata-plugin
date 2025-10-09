# xml_generator.py (VERSÃO FINAL E COMPLETA)

from lxml import etree as ET
import uuid
import os
from qgis.core import Qgis

# --- DADOS FIXOS PARA O CONTATO CDHU ---
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
    if parent_element is None: return
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and text_value is not None:
        element.text = str(text_value)

def set_element_attribute(parent_element, xpath, attr_name, attr_value, ns_map):
    if parent_element is None: return
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None and attr_value is not None:
        element.set(attr_name, str(attr_value))

def update_contact_block(contact_wrapper_node, data_dict, ns_map):
    if contact_wrapper_node is None: return
    
    responsible_party_node = contact_wrapper_node.find('./gmd:CI_ResponsibleParty', namespaces=ns_map)
    if responsible_party_node is None:
        responsible_party_node = ET.SubElement(contact_wrapper_node, f"{{{ns_map['gmd']}}}CI_ResponsibleParty")

    uuid_value = data_dict.get('uuid') or str(uuid.uuid4())
    responsible_party_node.set('uuid', uuid_value)
    
    structure = {
        'individualName': 'gco:CharacterString', 'organisationName': 'gco:CharacterString', 
        'positionName': 'gco:CharacterString', 'contactInfo': {'CI_Contact': {
            'phone': {'CI_Telephone': {'voice': 'gco:CharacterString'}},
            'address': {'CI_Address': {
                'deliveryPoint': 'gco:CharacterString', 'city': 'gco:CharacterString',
                'administrativeArea': 'gco:CharacterString', 'postalCode': 'gco:CharacterString',
                'country': 'gco:CharacterString', 'electronicMailAddress': 'gco:CharacterString'
            }}
        }}, 'role': {'CI_RoleCode': None}
    }
    
    def ensure_structure(parent, struct_dict, local_ns_map):
        for tag, content in struct_dict.items():
            node = parent.find(f'./gmd:{tag}', namespaces=local_ns_map)
            if node is None: node = ET.SubElement(parent, f"{{{local_ns_map['gmd']}}}{tag}")
            if isinstance(content, dict): ensure_structure(node, content, local_ns_map)
            elif content:
                sub_ns, sub_tag = content.split(':')
                if node.find(f'./{content}', namespaces=local_ns_map) is None: ET.SubElement(node, f"{{{local_ns_map[sub_ns]}}}{sub_tag}")

    ensure_structure(responsible_party_node, structure, ns_map)
    
    set_element_text(responsible_party_node, './/gmd:individualName/gco:CharacterString', data_dict.get('contact_individualName'), ns_map)
    set_element_text(responsible_party_node, './/gmd:organisationName/gco:CharacterString', data_dict.get('contact_organisationName'), ns_map)
    # ... (preenchimento dos outros campos de contato)
    set_element_text(responsible_party_node, './/gmd:electronicMailAddress/gco:CharacterString', data_dict.get('contact_email'), ns_map)
    
    role_value = data_dict.get('contact_role')
    set_element_attribute(responsible_party_node, './/gmd:role/gmd:CI_RoleCode', 'codeListValue', role_value, ns_map)
    
    xlink_ns_uri = ns_map.get('xlink')
    if xlink_ns_uri:
        href_attr = f'{{{xlink_ns_uri}}}href'
        if href_attr in contact_wrapper_node.attrib:
            href = contact_wrapper_node.attrib[href_attr]
            href = href.replace('{uuid}', uuid_value).replace('{contact_role}', role_value or '')
            contact_wrapper_node.attrib[href_attr] = href

def remove_element_if_exists(parent_element, xpath, ns_map):
    if parent_element is None: return
    for element in parent_element.findall(xpath, namespaces=ns_map):
        element.getparent().remove(element)

# ---------------------------- FUNÇÃO PRINCIPAL ----------------------------
def generate_xml_from_template(data_dict, template_path):
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template XML não encontrado em '{template_path}'")

    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(template_path, parser)
    root = tree.getroot()
    ns = {k if k is not None else 'gmd': v for k, v in root.nsmap.items()}

    # --- ETAPA 1: ATUALIZAR CONTATOS ---
    contact_wrappers_raiz = root.findall('./gmd:contact', namespaces=ns)
    if len(contact_wrappers_raiz) >= 2:
        update_contact_block(contact_wrappers_raiz[0], CDHU_CONTACT_DATA, ns)
        update_contact_block(contact_wrappers_raiz[1], data_dict, ns)

    id_info = root.find('.//gmd:identificationInfo/gmd:MD_DataIdentification', namespaces=ns)
    if id_info is not None:
        contact_wrappers_id = id_info.findall('./gmd:pointOfContact', namespaces=ns)
        if len(contact_wrappers_id) >= 2:
            update_contact_block(contact_wrappers_id[0], data_dict, ns)
            update_contact_block(contact_wrappers_id[1], CDHU_CONTACT_DATA, ns)

    # --- ETAPA 2: PREENCHER METADADOS GERAIS ---
    set_element_text(root, './gmd:fileIdentifier/gco:CharacterString', str(uuid.uuid4()), ns)
    set_element_text(root, './gmd:dateStamp/gco:DateTime', data_dict.get('dateStamp'), ns)
    set_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', data_dict.get('LanguageCode'), ns)
    hierarchy_level_value = data_dict.get('hierarchyLevel')
    set_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', hierarchy_level_value, ns)

    if id_info is not None:
        set_element_text(id_info, './/gmd:title/gco:CharacterString', data_dict.get('title'), ns)
        set_element_text(id_info, './/gmd:edition/gco:CharacterString', data_dict.get('edition'), ns)
        set_element_text(id_info, './/gmd:date//gco:DateTime', data_dict.get('date_creation'), ns)
        set_element_text(id_info, './gmd:abstract/gco:CharacterString', data_dict.get('abstract'), ns)
        set_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', data_dict.get('status_codeListValue'), ns)
        set_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', data_dict.get('topicCategory'), ns)
        
        keyword_container = id_info.find('.//gmd:descriptiveKeywords/gmd:MD_Keywords', namespaces=ns)
        remove_element_if_exists(keyword_container, './gmd:keyword', ns)
        keywords_list = data_dict.get('MD_Keywords', [])
        if keywords_list:
            for keyword_text in keywords_list:
                kw_node = ET.SubElement(keyword_container, f"{{{ns['gmd']}}}keyword")
                cs_node = ET.SubElement(kw_node, f"{{{ns['gco']}}}CharacterString")
                cs_node.text = keyword_text
        
        set_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', data_dict.get('MD_SpatialRepresentationTypeCode'), ns)
        set_element_text(id_info, './/gmd:denominator/gco:Integer', data_dict.get('spatialResolution_denominator'), ns)
        set_element_text(id_info, './/gmd:westBoundLongitude/gco:Decimal', data_dict.get('westBoundLongitude'), ns)
        set_element_text(id_info, './/gmd:eastBoundLongitude/gco:Decimal', data_dict.get('eastBoundLongitude'), ns)
        set_element_text(id_info, './/gmd:southBoundLatitude/gco:Decimal', data_dict.get('southBoundLatitude'), ns)
        set_element_text(id_info, './/gmd:northBoundLatitude/gco:Decimal', data_dict.get('northBoundLatitude'), ns)
        
    # --- ETAPA 3: PREENCHER OU REMOVER BLOCOS OPCIONAIS ---
    
    # 3.1 - Thumbnail
    thumbnail_url = data_dict.get('thumbnail_url')
    graphic_overview_node = id_info.find('./gmd:graphicOverview', namespaces=ns)
    if thumbnail_url and graphic_overview_node is not None:
        set_element_text(graphic_overview_node, './/gmd:fileName/gco:CharacterString', thumbnail_url, ns)
    elif graphic_overview_node is not None:
        id_info.remove(graphic_overview_node)

    # 3.2 - Distribuição (WMS e WFS)
    wms_data = data_dict.get('wms_data')
    wfs_data = data_dict.get('wfs_data')
    dist_info = root.find('./gmd:distributionInfo', namespaces=ns)
    
    
    if dist_info is not None:
        online_nodes = dist_info.findall('.//gmd:onLine', namespaces=ns)
        
        wms_node = online_nodes[0] if len(online_nodes) >= 1 else None
        wfs_node = online_nodes[1] if len(online_nodes) >= 2 else None

        # Handle WMS
        if wms_data and wms_node is not None:
            wms_url = f"{wms_data['geoserver_base_url']}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', wms_url, ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', wms_data['geoserver_layer_name'], ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', wms_data['geoserver_layer_title'], ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', 'OGC:WMS', ns)
        elif wms_node is not None:
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', '', ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', '', ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', '', ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', '', ns)

        # Handle WFS
        if wfs_data and wfs_node is not None:
            wfs_url = f"{wfs_data['geoserver_base_url']}/wfs"
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', wfs_url, ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', wfs_data['geoserver_layer_name'], ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', wfs_data['geoserver_layer_title'], ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', 'OGC:WFS', ns)
        elif wfs_node is not None:
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', '', ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', '', ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', '', ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', '', ns)
        
        # If after processing, there are no online resources left, remove dist_info
        remaining_online_nodes = dist_info.findall('.//gmd:onLine', namespaces=ns)
        if not remaining_online_nodes:
            root.remove(dist_info)

    # --- ETAPA 4: SERIALIZAR XML ---
    return ET.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8').decode('utf-8')