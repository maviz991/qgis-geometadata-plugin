# xml_generator.py (VERSÃO FINAL E COMPLETA)

from lxml import etree as ET
import uuid
import os
from qgis.core import Qgis

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
    set_element_text(responsible_party_node, './/gmd:positionName/gco:CharacterString', data_dict.get('contact_positionName'), ns_map)
    
    # Ensure CI_Contact, CI_Telephone, CI_Address exist
    contact_info_node = responsible_party_node.find('./gmd:contactInfo', namespaces=ns_map)
    if contact_info_node is None:
        contact_info_node = ET.SubElement(responsible_party_node, f"{{{ns_map['gmd']}}}contactInfo")
    ci_contact_node = contact_info_node.find('./gmd:CI_Contact', namespaces=ns_map)
    if ci_contact_node is None:
        ci_contact_node = ET.SubElement(contact_info_node, f"{{{ns_map['gmd']}}}CI_Contact")

    # Phone
    phone_node = ci_contact_node.find('./gmd:phone', namespaces=ns_map)
    if phone_node is None:
        phone_node = ET.SubElement(ci_contact_node, f"{{{ns_map['gmd']}}}phone")
    ci_telephone_node = phone_node.find('./gmd:CI_Telephone', namespaces=ns_map)
    if ci_telephone_node is None:
        ci_telephone_node = ET.SubElement(phone_node, f"{{{ns_map['gmd']}}}CI_Telephone")
    voice_node = ci_telephone_node.find('./gmd:voice', namespaces=ns_map)
    if voice_node is None:
        voice_node = ET.SubElement(ci_telephone_node, f"{{{ns_map['gmd']}}}voice")
        ET.SubElement(voice_node, f"{{{ns_map['gco']}}}CharacterString")
    set_element_text(ci_telephone_node, './gmd:voice/gco:CharacterString', data_dict.get('contact_phone'), ns_map)

    # Address
    address_node = ci_contact_node.find('./gmd:address', namespaces=ns_map)
    if address_node is None:
        address_node = ET.SubElement(ci_contact_node, f"{{{ns_map['gmd']}}}address")
    ci_address_node = address_node.find('./gmd:CI_Address', namespaces=ns_map)
    if ci_address_node is None:
        ci_address_node = ET.SubElement(address_node, f"{{{ns_map['gmd']}}}CI_Address")
    
    # Ensure all address sub-elements exist
    for tag in ['deliveryPoint', 'city', 'administrativeArea', 'postalCode', 'country', 'electronicMailAddress']:
        element_node = ci_address_node.find(f'./gmd:{tag}', namespaces=ns_map)
        if element_node is None:
            element_node = ET.SubElement(ci_address_node, f"{{{ns_map['gmd']}}}{tag}")
        char_string_node = element_node.find(f'./gco:CharacterString', namespaces=ns_map)
        if char_string_node is None:
            ET.SubElement(element_node, f"{{{ns_map['gco']}}}CharacterString")

    set_element_text(ci_address_node, './gmd:deliveryPoint/gco:CharacterString', data_dict.get('contact_deliveryPoint'), ns_map)
    set_element_text(ci_address_node, './gmd:city/gco:CharacterString', data_dict.get('contact_city'), ns_map)
    set_element_text(ci_address_node, './gmd:administrativeArea/gco:CharacterString', data_dict.get('contact_administrativeArea'), ns_map)
    set_element_text(ci_address_node, './gmd:postalCode/gco:CharacterString', data_dict.get('contact_postalCode'), ns_map)
    set_element_text(ci_address_node, './gmd:country/gco:CharacterString', data_dict.get('contact_country'), ns_map)
    set_element_text(ci_address_node, './gmd:electronicMailAddress/gco:CharacterString', data_dict.get('contact_email'), ns_map)
    
    role_node = responsible_party_node.find('./gmd:role', namespaces=ns_map)
    if role_node is None:
        role_node = ET.SubElement(responsible_party_node, f"{{{ns_map['gmd']}}}role")
    ci_role_code_node = role_node.find('./gmd:CI_RoleCode', namespaces=ns_map)
    if ci_role_code_node is None:
        ci_role_code_node = ET.SubElement(role_node, f"{{{ns_map['gmd']}}}CI_RoleCode")

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
def generate_xml_from_template(data_dict, template_path, cdhu_contact_data):
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template XML não encontrado em '{template_path}'")

    parser = ET.XMLParser(remove_blank_text=True)
    tree = ET.parse(template_path, parser)
    root = tree.getroot()
    ns = {k if k is not None else 'gmd': v for k, v in root.nsmap.items()}

     # --- LÓGICA DE VERIFICAÇÃO DE DUPLICATA ---
    # Compara o UUID do contato selecionado com o UUID do contato padrão CDHU.
    is_duplicate_contact = (data_dict.get('uuid') and 
                            cdhu_contact_data.get('uuid') and
                            data_dict['uuid'] == cdhu_contact_data['uuid'])
    
    if is_duplicate_contact:
        print("Gerador XML: Contato selecionado é o CDHU. Evitando duplicata.")

    # --- ETAPA 1: ATUALIZAR CONTATOS ---
    contact_wrappers_raiz = root.findall('./gmd:contact', namespaces=ns)
    if len(contact_wrappers_raiz) >= 2:
        # Bloco 1: Sempre preenchido com os dados CDHU
        update_contact_block(contact_wrappers_raiz[0], cdhu_contact_data, ns)
        
        # Bloco 2: Preenchido com dados do usuário OU removido se for duplicata
        if is_duplicate_contact:
            contact_to_remove = contact_wrappers_raiz[1]
            contact_to_remove.getparent().remove(contact_to_remove)
        else:
            update_contact_block(contact_wrappers_raiz[1], data_dict, ns)

    # Ensure identificationInfo and MD_DataIdentification exist
    identification_info_node = root.find('./gmd:identificationInfo', namespaces=ns)
    if identification_info_node is None:
        identification_info_node = ET.SubElement(root, f"{{{ns['gmd']}}}identificationInfo")
    
    id_info = identification_info_node.find('./gmd:MD_DataIdentification', namespaces=ns)
    if id_info is None:
        id_info = ET.SubElement(identification_info_node, f"{{{ns['gmd']}}}MD_DataIdentification")

    contact_wrappers_id = id_info.findall('./gmd:pointOfContact', namespaces=ns)
    if len(contact_wrappers_id) >= 2:
        # Bloco 1: Preenchido com dados do usuário (ou removido se for CDHU)
        if is_duplicate_contact:
            # Neste caso, o "contato do usuário" é o CDHU, que já está no outro bloco.
            # Então, o primeiro pointOfContact pode ser removido ou limpo. Remover é mais limpo.
            contact_to_remove = contact_wrappers_id[0]
            contact_to_remove.getparent().remove(contact_to_remove)
        else:
            update_contact_block(contact_wrappers_id[0], data_dict, ns)

        # Bloco 2: Sempre preenchido com os dados CDHU
        update_contact_block(contact_wrappers_id[1], cdhu_contact_data, ns)

    # Verifica se um UUID já existe no dicionário de dados (vindo de um XML carregado)
    existing_uuid = data_dict.get('metadata_uuid')
    
    if existing_uuid:
        # Se existe, usa esse UUID. Isso garante que estamos ATUALIZANDO o metadado.
        final_uuid = existing_uuid
        print(f"Gerador XML: Usando UUID existente para atualização: {final_uuid}")
    else:
        # Se não existe, gera um novo. Isso acontece na CRIAÇÃO de um novo metadado.
        final_uuid = str(uuid.uuid4())
        print(f"Gerador XML: Gerando novo UUID para criação: {final_uuid}")
        
    set_element_text(root, './gmd:fileIdentifier/gco:CharacterString', final_uuid, ns)

    # --- ETAPA 2: PREENCHER METADADOS GERAIS ---
    set_element_text(root, './gmd:dateStamp/gco:DateTime', data_dict.get('dateStamp'), ns)
    set_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', data_dict.get('LanguageCode'), ns)
    hierarchy_level_value = data_dict.get('hierarchyLevel')
    set_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', hierarchy_level_value, ns)

    # Now id_info is guaranteed to exist
    set_element_text(id_info, './/gmd:title/gco:CharacterString', data_dict.get('title'), ns)
    set_element_text(id_info, './/gmd:edition/gco:CharacterString', data_dict.get('edition'), ns)
    
    # Ensure citation and date elements exist before setting their text
    citation_node = id_info.find('.//gmd:citation/gmd:CI_Citation', namespaces=ns)
    if citation_node is None:
        citation_node = ET.SubElement(id_info, f"{{{ns['gmd']}}}citation")
        citation_node = ET.SubElement(citation_node, f"{{{ns['gmd']}}}CI_Citation")
    
    date_parent_node = citation_node.find('./gmd:date/gmd:CI_Date', namespaces=ns)
    if date_parent_node is None:
        date_parent_node = ET.SubElement(citation_node, f"{{{ns['gmd']}}}date")
        date_parent_node = ET.SubElement(date_parent_node, f"{{{ns['gmd']}}}CI_Date")
    
    date_node = date_parent_node.find('./gmd:date/gco:DateTime', namespaces=ns)
    if date_node is None:
        date_node = ET.SubElement(date_parent_node, f"{{{ns['gmd']}}}date")
        ET.SubElement(date_node, f"{{{ns['gco']}}}CharacterString") # Changed to CharacterString as per template

    set_element_text(id_info, './/gmd:date//gco:DateTime', data_dict.get('date_creation'), ns) # Changed to CharacterString
    set_element_text(id_info, './gmd:abstract/gco:CharacterString', data_dict.get('abstract'), ns)
    set_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', data_dict.get('status_codeListValue'), ns)
    set_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', data_dict.get('topicCategory'), ns)
    
    # Ensure descriptiveKeywords and MD_Keywords exist
    descriptive_keywords_node = id_info.find('./gmd:descriptiveKeywords', namespaces=ns)
    if descriptive_keywords_node is None:
        descriptive_keywords_node = ET.SubElement(id_info, f"{{{ns['gmd']}}}descriptiveKeywords")
    
    keyword_container = descriptive_keywords_node.find('./gmd:MD_Keywords', namespaces=ns)
    if keyword_container is None:
        keyword_container = ET.SubElement(descriptive_keywords_node, f"{{{ns['gmd']}}}MD_Keywords")

    remove_element_if_exists(keyword_container, './gmd:keyword', ns)
    keywords_list = data_dict.get('MD_Keywords', [])
    if keywords_list:
        for keyword_text in keywords_list:
            kw_node = ET.SubElement(keyword_container, f"{{{ns['gmd']}}}keyword")
            cs_node = ET.SubElement(kw_node, f"{{{ns['gco']}}}CharacterString")
            cs_node.text = keyword_text
    
    set_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', data_dict.get('MD_SpatialRepresentationTypeCode'), ns)
    try:
        scale_value = int(data_dict.get('spatialResolution_denominator'))
    except (ValueError, TypeError):
        scale_value = None  # Or a default value like 1 if appropriate
    set_element_text(id_info, './/gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer', scale_value, ns)
    set_element_text(id_info, './/gmd:westBoundLongitude/gco:Decimal', data_dict.get('westBoundLongitude'), ns)
    set_element_text(id_info, './/gmd:eastBoundLongitude/gco:Decimal', data_dict.get('eastBoundLongitude'), ns)
    set_element_text(id_info, './/gmd:southBoundLatitude/gco:Decimal', data_dict.get('southBoundLatitude'), ns)
    set_element_text(id_info, './/gmd:northBoundLatitude/gco:Decimal', data_dict.get('northBoundLatitude'), ns)
    
    # --- ETAPA 3: PREENCHER OU REMOVER BLOCOS OPCIONAIS ---
    
    # 3.1 - Thumbnail
    thumbnail_url = data_dict.get('thumbnail_url')
    graphic_overview_node = id_info.find('./gmd:graphicOverview', namespaces=ns)
    
    if thumbnail_url:
        if graphic_overview_node is None:
            graphic_overview_node = ET.SubElement(id_info, f"{{{ns['gmd']}}}graphicOverview")
            md_browse_graphic_node = ET.SubElement(graphic_overview_node, f"{{{ns['gmd']}}}MD_BrowseGraphic")
            file_name_node = ET.SubElement(md_browse_graphic_node, f"{{{ns['gmd']}}}fileName")
            ET.SubElement(file_name_node, f"{{{ns['gco']}}}CharacterString")
        set_element_text(graphic_overview_node, './/gmd:fileName/gco:CharacterString', thumbnail_url, ns)
    elif graphic_overview_node is not None:
        id_info.remove(graphic_overview_node)

    # 3.2 - Distribuição (WMS e WFS)
    wms_data = data_dict.get('wms_data')
    wfs_data = data_dict.get('wfs_data')
    
    dist_info = root.find('./gmd:distributionInfo', namespaces=ns)
    
    if wms_data or wfs_data:
        if dist_info is None:
            dist_info = ET.SubElement(root, f"{{{ns['gmd']}}}distributionInfo")
        
        md_distribution_node = dist_info.find('./gmd:MD_Distribution', namespaces=ns)
        if md_distribution_node is None:
            md_distribution_node = ET.SubElement(dist_info, f"{{{ns['gmd']}}}MD_Distribution")
        
        transfer_options_node = md_distribution_node.find('./gmd:transferOptions', namespaces=ns)
        if transfer_options_node is None:
            transfer_options_node = ET.SubElement(md_distribution_node, f"{{{ns['gmd']}}}transferOptions")
        
        md_digital_transfer_options_node = transfer_options_node.find('./gmd:MD_DigitalTransferOptions', namespaces=ns)
        if md_digital_transfer_options_node is None:
            md_digital_transfer_options_node = ET.SubElement(transfer_options_node, f"{{{ns['gmd']}}}MD_DigitalTransferOptions")
        
        online_nodes = md_digital_transfer_options_node.findall('./gmd:onLine', namespaces=ns)
        
        # Ensure we have at least two online nodes for WMS and WFS
        while len(online_nodes) < 2:
            on_line_node = ET.SubElement(md_digital_transfer_options_node, f"{{{ns['gmd']}}}onLine")
            ci_online_resource_node = ET.SubElement(on_line_node, f"{{{ns['gmd']}}}CI_OnlineResource")
            ET.SubElement(ci_online_resource_node, f"{{{ns['gmd']}}}linkage")
            ET.SubElement(ci_online_resource_node, f"{{{ns['gmd']}}}name")
            ET.SubElement(ci_online_resource_node, f"{{{ns['gmd']}}}description")
            ET.SubElement(ci_online_resource_node, f"{{{ns['gmd']}}}protocol")
            ET.SubElement(ci_online_resource_node.find(f"{{{ns['gmd']}}}linkage"), f"{{{ns['gmd']}}}URL")
            ET.SubElement(ci_online_resource_node.find(f"{{{ns['gmd']}}}name"), f"{{{ns['gco']}}}CharacterString")
            ET.SubElement(ci_online_resource_node.find(f"{{{ns['gmd']}}}description"), f"{{{ns['gco']}}}CharacterString")
            ET.SubElement(ci_online_resource_node.find(f"{{{ns['gmd']}}}protocol"), f"{{{ns['gco']}}}CharacterString")
            online_nodes = md_digital_transfer_options_node.findall('./gmd:onLine', namespaces=ns) # Re-find nodes after adding

        wms_node = online_nodes[0]
        wfs_node = online_nodes[1]

        # Handle WMS
        if wms_data:
            wms_url = f"{wms_data['geoserver_base_url']}/ows?service=WMS&version=1.3.0&request=GetCapabilities"
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', wms_url, ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', wms_data['geoserver_layer_name'], ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', wms_data['geoserver_layer_title'], ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', 'OGC:WMS', ns)
        else:
            # Clear WMS data if not present
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', '', ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', '', ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', '', ns)
            set_element_text(wms_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', '', ns)

        # Handle WFS
        if wfs_data:
            wfs_url = f"{wfs_data['geoserver_base_url']}/wfs"
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', wfs_url, ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', wfs_data['geoserver_layer_name'], ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', wfs_data['geoserver_layer_title'], ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', 'OGC:WFS', ns)
        else:
            # Clear WFS data if not present
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:linkage/gmd:URL', '', ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:name/gco:CharacterString', '', ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:description/gco:CharacterString', '', ns)
            set_element_text(wfs_node, './gmd:CI_OnlineResource/gmd:protocol/gco:CharacterString', '', ns)
        
        # If after processing, there are no online resources left, remove dist_info
        # This logic needs to be careful. If we cleared both WMS and WFS, we should remove the parent.
        # But if the template always has them, we just clear their content.
        # For now, let's assume the template might not have them, and we create them.
        # If both wms_data and wfs_data are None, we should remove the dist_info block if it was created by us.
        # If it was in the template, we just clear its content.
        # For now, let's rely on clearing the content.
        
        # Check if both WMS and WFS data are empty, and if so, remove the distributionInfo block
        if not wms_data and not wfs_data and dist_info is not None:
            root.remove(dist_info)
    elif dist_info is not None: # If no WMS/WFS data and dist_info exists, remove it
        root.remove(dist_info)

    # --- ETAPA 4: SERIALIZAR XML ---
    return ET.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8').decode('utf-8')