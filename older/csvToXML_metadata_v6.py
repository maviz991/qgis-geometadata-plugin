from lxml import etree as ET
import pandas as pd
import uuid
from datetime import datetime, timezone
import os

caminho_csv = 'Planilha_MGB2_Metadata_FIPE2.csv'
caminho_template_xml = 'tamplate_mgb20.xml'
pasta_saida = 'metadados_gerados'

def set_element_text(parent_element, xpath, text_value, ns_map):
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None:
        element.text = text_value

def set_element_attribute(parent_element, xpath, attr_name, attr_value, ns_map):
    element = parent_element.find(xpath, namespaces=ns_map)
    if element is not None:
        element.set(attr_name, attr_value)

def atualizar_bloco_de_contato(contato_node, csv_row, ns_map):
    if contato_node is None: return
    contato_node.set('uuid', str(uuid.uuid4()))
    set_element_text(contato_node, './/gmd:individualName/gco:CharacterString', csv_row.get('contact_individualName'), ns_map)
    set_element_text(contato_node, './/gmd:organisationName/gco:CharacterString', csv_row.get('contact_organisationName'), ns_map)
    set_element_text(contato_node, './/gmd:positionName/gco:CharacterString', csv_row.get('contact_positionName'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:voice/gco:CharacterString', csv_row.get('contact_phone'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:deliveryPoint/gco:CharacterString', csv_row.get('contact_deliveryPoint'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:city/gco:CharacterString', csv_row.get('contact_city'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:administrativeArea/gco:CharacterString', csv_row.get('contact_administrativeArea'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:postalCode/gco:CharacterString', str(csv_row.get('contact_postalCode', '')), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:country/gco:CharacterString', csv_row.get('contact_country'), ns_map)
    set_element_text(contato_node, './/gmd:contactInfo//gmd:electronicMailAddress/gco:CharacterString', csv_row.get('contact_email'), ns_map)

def gerar_metadados_xml(csv_path, template_path, output_dir):
    if not os.path.exists(csv_path):
        print(f"Erro: Arquivo CSV não encontrado em '{csv_path}'")
        return
    if not os.path.exists(template_path):
        print(f"Erro: Template XML não encontrado em '{template_path}'")
        return

    os.makedirs(output_dir, exist_ok=True)

    try:
        df = pd.read_csv(csv_path, sep=';', header=0, dtype=str).fillna('')
        df = df.loc[df['LanguageCode'] != '']
        print(f"Encontrados {len(df)} registros de metadados válidos no arquivo CSV.")

        for index, row in df.iterrows():
            parser = ET.XMLParser(remove_blank_text=True)
            tree = ET.parse(template_path, parser)
            root = tree.getroot()
            ns = root.nsmap
            
            set_element_text(root, './gmd:fileIdentifier/gco:CharacterString', str(uuid.uuid4()), ns)
            set_element_text(root, './gmd:dateStamp/gco:DateTime', row.get('dateStamp'), ns)
            
            set_element_attribute(root, './gmd:language/gmd:LanguageCode', 'codeListValue', row.get('LanguageCode'), ns)
            set_element_attribute(root, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', row.get('characterSet'), ns)
            set_element_attribute(root, './gmd:hierarchyLevel/gmd:MD_ScopeCode', 'codeListValue', row.get('hierarchyLevel'), ns)
            
            for party in root.findall('./gmd:contact/gmd:CI_ResponsibleParty', namespaces=ns):
                if party.find('.//gmd:role/gmd:CI_RoleCode', namespaces=ns).get('codeListValue') == 'author':
                    atualizar_bloco_de_contato(party, row, ns)
                    break
            
            id_info = root.find('.//gmd:identificationInfo/gmd:MD_DataIdentification', namespaces=ns)
            if id_info is not None:
                for party in id_info.findall('./gmd:pointOfContact/gmd:CI_ResponsibleParty', namespaces=ns):
                    if party.find('.//gmd:role/gmd:CI_RoleCode', namespaces=ns).get('codeListValue') == 'author':
                        atualizar_bloco_de_contato(party, row, ns)
                        break

                set_element_text(id_info, './/gmd:citation//gmd:title/gco:CharacterString', row.get('title'), ns)
                
                # --- LÓGICA DE DATA ADAPTATIVA ---
                date_value_from_csv = row.get('date_creation', '')
                # Usa * para encontrar a tag de data, seja ela <gco:Date> ou <gco:DateTime>
                date_element = id_info.find('.//gmd:citation//gmd:date/gmd:CI_Date/gmd:date/*', namespaces=ns)
                
                if date_element is not None:
                    if 'T' in date_value_from_csv:
                        date_element.tag = f"{{{ns['gco']}}}DateTime"
                    else:
                        date_element.tag = f"{{{ns['gco']}}}Date"
                    
                    date_element.text = date_value_from_csv
                
                set_element_text(id_info, './gmd:abstract/gco:CharacterString', row.get('abstract'), ns)
                set_element_attribute(id_info, './gmd:status/gmd:MD_ProgressCode', 'codeListValue', row.get('status_codeListValue'), ns)
                set_element_attribute(id_info, './gmd:language/gmd:LanguageCode', 'codeListValue', row.get('LanguageCode'), ns)
                set_element_attribute(id_info, './gmd:characterSet/gmd:MD_CharacterSetCode', 'codeListValue', row.get('characterSet'), ns)
                
                keyword_container = id_info.find('./gmd:descriptiveKeywords', namespaces=ns)
                if keyword_container is not None:
                    keyword_container.clear()
                    md_keywords_node = ET.SubElement(keyword_container, f"{{{ns['gmd']}}}MD_Keywords")
                    keywords_found = False
                    for col in ['MD_Keywords1', 'MD_Keywords2', 'MD_Keywords3', 'MD_Keywords4']:
                        if col in row and row[col]:
                            keywords_found = True
                            keyword_node = ET.SubElement(md_keywords_node, f"{{{ns['gmd']}}}keyword")
                            char_string = ET.SubElement(keyword_node, f"{{{ns['gco']}}}CharacterString")
                            char_string.text = row[col]
                    if not keywords_found:
                        keyword_container.remove(md_keywords_node)

                set_element_attribute(id_info, './/gmd:spatialRepresentationType/gmd:MD_SpatialRepresentationTypeCode', 'codeListValue', row.get('MD_SpatialRepresentationTypeCode_codeListValue'), ns)
                set_element_text(id_info, './/gmd:spatialResolution//gmd:denominator/gco:Integer', str(int(float(row.get('spatialResolution_denominator', 0)))), ns)
                set_element_text(id_info, './/gmd:topicCategory/gmd:MD_TopicCategoryCode', row.get('topicCategory'), ns)
                
                set_element_text(id_info, './/gmd:extent//gmd:westBoundLongitude/gco:Decimal', str(row.get('westBoundLongitude')), ns)
                set_element_text(id_info, './/gmd:extent//gmd:eastBoundLongitude/gco:Decimal', str(row.get('eastBoundLongitude')), ns)
                set_element_text(id_info, './/gmd:extent//gmd:southBoundLatitude/gco:Decimal', str(row.get('southBoundLatitude')), ns)
                set_element_text(id_info, './/gmd:extent//gmd:northBoundLatitude/gco:Decimal', str(row.get('northBoundLatitude')), ns)

            safe_title = "".join([c for c in row.get('title', '') if c.isalnum() or c in (' ', '-')]).rstrip().replace(' ', '_')
            output_filename = os.path.join(output_dir, f"metadado_{index}_{safe_title}.xml")
            
            tree.write(output_filename, pretty_print=True, xml_declaration=True, encoding='utf-8')
            print(f"--> Arquivo XML '{output_filename}' gerado com sucesso.")

    except Exception as e:
        print(f"ERRO CRÍTICO: Ocorreu um erro inesperado: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    gerar_metadados_xml(caminho_csv, caminho_template_xml, pasta_saida)