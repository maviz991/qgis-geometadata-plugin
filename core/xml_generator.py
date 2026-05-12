# xml_generator.py — Geração Programática ISO 19139 / MGB 2.0
# Sem dependência de template estático. Construção via lxml.etree.

from lxml import etree as ET
import uuid as _uuid_mod
import datetime

# ── Namespaces canônicos ISO 19139 ──────────────────────────────────────────
NS = {
    'gmd': 'http://www.isotc211.org/2005/gmd',
    'gco': 'http://www.isotc211.org/2005/gco',
    'gmx': 'http://www.isotc211.org/2005/gmx',
    'gml': 'http://www.opengis.net/gml/3.2',
    'xlink': 'http://www.w3.org/1999/xlink',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'gts': 'http://www.isotc211.org/2005/gts',
    'srv': 'http://www.isotc211.org/2005/srv',
}

CL = 'http://standards.iso.org/iso/19139/resources/gmxCodelists.xml#'
LOC_CL = 'http://www.loc.gov/standards/iso639-2/'

def _ns(prefix, tag):
    return f'{{{NS[prefix]}}}{tag}'

def _sub(parent, prefix, tag, text=None, attrib=None):
    el = ET.SubElement(parent, _ns(prefix, tag), attrib or {})
    if text is not None:
        el.text = str(text)
    return el

def _char(parent, prefix, tag, text):
    """Adiciona <gmd:TAG><gco:CharacterString>text</gco:CharacterString></gmd:TAG>"""
    wrapper = _sub(parent, prefix, tag)
    if text:
        _sub(wrapper, 'gco', 'CharacterString', str(text))
    else:
        cs = _sub(wrapper, 'gco', 'CharacterString')
        cs.set(_ns('gco', 'nilReason'), 'missing')
    return wrapper

def _codelist(parent, prefix, wrapper_tag, cl_tag, cl_name, value):
    wrapper = _sub(parent, prefix, wrapper_tag)
    _sub(wrapper, prefix, cl_tag, attrib={
        'codeList': CL + cl_name,
        'codeListValue': value or ''
    })
    return wrapper

def _datetime_el(parent, prefix, wrapper_tag, value):
    wrapper = _sub(parent, prefix, wrapper_tag)
    if value:
        _sub(wrapper, 'gco', 'DateTime', str(value))
    else:
        dt = _sub(wrapper, 'gco', 'DateTime')
        dt.set(_ns('gco', 'nilReason'), 'missing')
    return wrapper

# ── Bloco de Contato CI_ResponsibleParty ────────────────────────────────────
def _build_contact_block(parent, wrapper_tag, contact_data):
    """
    contact_data pode vir do formato interno do JS:
      { sigla, org, position, phone, addr, city, state, zip, country, email, role, uuid }
    ou do formato legado flat:
      { contact_individualName, contact_organisationName, ... }
    """
    # Normaliza campos — suporta ambos os formatos
    def _f(key, alt=None):
        return contact_data.get(key) or (contact_data.get(alt) if alt else '') or ''

    sigla   = _f('sigla', 'contact_individualName')
    org     = _f('org', 'contact_organisationName')
    pos     = _f('position', 'contact_positionName')
    phone   = _f('phone', 'contact_phone')
    addr    = _f('addr', 'contact_deliveryPoint')
    city    = _f('city', 'contact_city')
    state   = _f('state', 'contact_administrativeArea')
    zipcode = _f('zip', 'contact_postalCode')
    country = _f('country', 'contact_country') or 'Brasil'
    email   = _f('email', 'contact_email')
    role    = _f('role', 'contact_role') or 'pointOfContact'
    c_uuid  = contact_data.get('uuid') or str(_uuid_mod.uuid4())

    # xlink href para integração GeoNetwork
    xlink_href = (
        f'local://srv/api/registries/entries/{c_uuid}'
        f'?lang=por&process=gmd:role/gmd:CI_RoleCode/@codeListValue~{role}&schema=iso19139'
    )
    wrapper = _sub(parent, 'gmd', wrapper_tag, attrib={
        _ns('xlink', 'href'): xlink_href
    })

    rp = ET.SubElement(wrapper, _ns('gmd', 'CI_ResponsibleParty'), {'uuid': c_uuid})

    if sigla:
        _char(rp, 'gmd', 'individualName', sigla)
    _char(rp, 'gmd', 'organisationName', org)
    if pos:
        _char(rp, 'gmd', 'positionName', pos)

    ci_contact = _sub(_sub(rp, 'gmd', 'contactInfo'), 'gmd', 'CI_Contact')

    if phone:
        _char(_sub(_sub(ci_contact, 'gmd', 'phone'), 'gmd', 'CI_Telephone'), 'gmd', 'voice', phone)

    ci_addr = _sub(_sub(ci_contact, 'gmd', 'address'), 'gmd', 'CI_Address')
    if addr:
        _char(ci_addr, 'gmd', 'deliveryPoint', addr)
    _char(ci_addr, 'gmd', 'city', city)
    if state:
        _char(ci_addr, 'gmd', 'administrativeArea', state)
    if zipcode:
        _char(ci_addr, 'gmd', 'postalCode', zipcode)
    _char(ci_addr, 'gmd', 'country', country)
    _char(ci_addr, 'gmd', 'electronicMailAddress', email)

    role_wrapper = _sub(rp, 'gmd', 'role')
    _sub(role_wrapper, 'gmd', 'CI_RoleCode', attrib={
        'codeList': CL + 'CI_RoleCode',
        'codeListValue': role
    })

    return wrapper

# ── Função Principal ─────────────────────────────────────────────────────────
def generate_xml(data_dict, cdhu_contact_data=None):
    """
    Gera XML ISO 19139 completo a partir do dicionário de dados do formulário.
    Não depende de nenhum arquivo template.
    Suporta N contatos do recurso e N contatos de metadado.
    """
    d = data_dict or {}
    cdhu = cdhu_contact_data or {}

    # ── Raiz ────────────────────────────────────────────────────────────────
    nsmap = {k: v for k, v in NS.items()}
    root = ET.Element(_ns('gmd', 'MD_Metadata'), nsmap=nsmap)

    # ── UUID / fileIdentifier ────────────────────────────────────────────────
    final_uuid = d.get('metadata_uuid') or d.get('metadataId') or str(_uuid_mod.uuid4())
    _char(root, 'gmd', 'fileIdentifier', final_uuid)

    # ── Idioma do Metadado ───────────────────────────────────────────────────
    meta_lang = d.get('metadataLanguage') or 'por'
    lang_wrapper = _sub(root, 'gmd', 'language')
    _sub(lang_wrapper, 'gmd', 'LanguageCode', attrib={
        'codeList': LOC_CL,
        'codeListValue': meta_lang
    })

    # ── CharacterSet ─────────────────────────────────────────────────────────
    charset = d.get('characterSet') or 'utf8'
    _codelist(root, 'gmd', 'characterSet', 'MD_CharacterSetCode', 'MD_CharacterSetCode', charset)

    # ── hierarchyLevel ───────────────────────────────────────────────────────
    hier = d.get('hierarchyLevel') or 'dataset'
    _codelist(root, 'gmd', 'hierarchyLevel', 'MD_ScopeCode', 'MD_ScopeCode', hier)
    _char(_sub(root, 'gmd', 'hierarchyLevelName'), 'gco', 'CharacterString', hier)

    # ── Contatos do Metadado (gmd:contact) ──────────────────────────────────
    meta_contacts = d.get('metadataAuthorContacts') or []
    if meta_contacts:
        for mc in meta_contacts:
            cd = mc.get('data', mc)
            _build_contact_block(root, 'contact', cd)
    else:
        # Fallback: usa CDHU como contato de metadado
        if cdhu:
            _build_contact_block(root, 'contact', cdhu)

    # ── dateStamp ────────────────────────────────────────────────────────────
    date_stamp = d.get('dateStamp') or datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    _datetime_el(root, 'gmd', 'dateStamp', date_stamp)

    # ── metadataStandardName / Version ───────────────────────────────────────
    _char(root, 'gmd', 'metadataStandardName', 'ISO 19115')
    _char(root, 'gmd', 'metadataStandardVersion', '2003/Cor.1:2006')

    # ── Sistema de Referência (EPSG) ─────────────────────────────────────────
    epsg_code  = d.get('epsgCode')
    epsg_title = d.get('epsgTitle')
    if epsg_code or epsg_title:
        ref_sys = _sub(_sub(root, 'gmd', 'referenceSystemInfo'), 'gmd', 'MD_ReferenceSystem')
        ref_id  = _sub(_sub(ref_sys, 'gmd', 'referenceSystemIdentifier'), 'gmd', 'RS_Identifier')
        if epsg_code:
            _char(ref_id, 'gmd', 'code', epsg_code)
        if epsg_title:
            _char(ref_id, 'gmd', 'codeSpace', epsg_title)

    # ── identificationInfo ───────────────────────────────────────────────────
    id_info_wrapper = _sub(root, 'gmd', 'identificationInfo')
    id_info = _sub(id_info_wrapper, 'gmd', 'MD_DataIdentification')

    # Citation
    citation = _sub(_sub(id_info, 'gmd', 'citation'), 'gmd', 'CI_Citation')
    _char(citation, 'gmd', 'title', d.get('title'))

    # Data do dado
    ci_date = _sub(_sub(citation, 'gmd', 'date'), 'gmd', 'CI_Date')
    date_val = d.get('date') or d.get('date_creation') or ''
    _datetime_el(ci_date, 'gmd', 'date', date_val)
    date_type = d.get('dateType') or 'creation'
    _codelist(ci_date, 'gmd', 'dateType', 'CI_DateTypeCode', 'CI_DateTypeCode', date_type)

    # Edição
    edition = d.get('edition')
    if edition and str(edition) not in ('', '0'):
        _char(citation, 'gmd', 'edition', edition)
        date_edition = d.get('date_edition')
        if date_edition:
            _datetime_el(citation, 'gmd', 'editionDate', date_edition)

    # Abstract
    _char(id_info, 'gmd', 'abstract', d.get('abstract') or '')

    # Purpose
    purpose = d.get('purpose')
    if purpose:
        _char(id_info, 'gmd', 'purpose', purpose)

    # Credit
    credit = d.get('credit')
    if credit:
        _char(id_info, 'gmd', 'credit', credit)

    # Status
    status = d.get('status_codeListValue')
    if status:
        _codelist(id_info, 'gmd', 'status', 'MD_ProgressCode', 'MD_ProgressCode', status)

    # ── Contatos do Recurso (pointOfContact) ─────────────────────────────────
    resource_contacts = d.get('contacts') or []
    if resource_contacts:
        for rc in resource_contacts:
            cd = rc.get('data', rc)
            _build_contact_block(id_info, 'pointOfContact', cd)
    else:
        # Fallback flat fields
        flat = {
            'sigla': d.get('contact_individualName', ''),
            'org':   d.get('contact_organisationName', ''),
            'email': d.get('contact_email', ''),
            'role':  d.get('contact_role', 'pointOfContact'),
        }
        if flat['org'] or flat['email']:
            _build_contact_block(id_info, 'pointOfContact', flat)
        if cdhu:
            _build_contact_block(id_info, 'pointOfContact', cdhu)

    # Manutenção
    freq = d.get('maintenanceFrequency')
    if freq:
        maint = _sub(_sub(id_info, 'gmd', 'resourceMaintenance'), 'gmd', 'MD_MaintenanceInformation')
        _codelist(maint, 'gmd', 'maintenanceAndUpdateFrequency',
                  'MD_MaintenanceFrequencyCode', 'MD_MaintenanceFrequencyCode', freq)
        next_update = d.get('dateOfNextUpdate')
        if next_update:
            _datetime_el(maint, 'gmd', 'dateOfNextUpdate', next_update)

    # Thumbnail
    thumb = d.get('thumbnail_url')
    if thumb:
        _char(
            _sub(_sub(id_info, 'gmd', 'graphicOverview'), 'gmd', 'MD_BrowseGraphic'),
            'gmd', 'fileName', thumb
        )

    # Palavras-chave
    keywords = d.get('MD_Keywords') or []
    if keywords:
        md_kw = _sub(_sub(id_info, 'gmd', 'descriptiveKeywords'), 'gmd', 'MD_Keywords')
        for kw in keywords:
            _char(md_kw, 'gmd', 'keyword', kw)

    # Restrições de acesso / uso / licença
    use_lim   = d.get('useLimitation')
    acc_con   = d.get('accessConstraints')
    use_con   = d.get('useConstraints')
    other_con = d.get('otherConstraints')
    if use_lim or acc_con or use_con or other_con:
        res_con = _sub(id_info, 'gmd', 'resourceConstraints')
        md_legal = _sub(res_con, 'gmd', 'MD_LegalConstraints')
        if use_lim:
            _char(md_legal, 'gmd', 'useLimitation', use_lim)
        if acc_con:
            _codelist(md_legal, 'gmd', 'accessConstraints',
                      'MD_RestrictionCode', 'MD_RestrictionCode', acc_con)
        if use_con:
            _codelist(md_legal, 'gmd', 'useConstraints',
                      'MD_RestrictionCode', 'MD_RestrictionCode', use_con)
        if other_con:
            _char(md_legal, 'gmd', 'otherConstraints', other_con)

    # Tipo de Representação Espacial
    spat = d.get('MD_SpatialRepresentationTypeCode')
    if spat:
        _codelist(id_info, 'gmd', 'spatialRepresentationType',
                  'MD_SpatialRepresentationTypeCode', 'MD_SpatialRepresentationTypeCode', spat)

    # Resolução espacial (escala denominador)
    denom = d.get('spatialResolution_denominator')
    if denom:
        try:
            denom_int = int(float(denom))
            frac = _sub(
                _sub(_sub(_sub(id_info, 'gmd', 'spatialResolution'),
                          'gmd', 'MD_Resolution'),
                     'gmd', 'equivalentScale'),
                'gmd', 'MD_RepresentativeFraction'
            )
            _sub(frac, 'gmd', 'denominator').append(
                ET.fromstring(f'<gco:Integer xmlns:gco="{NS["gco"]}">{denom_int}</gco:Integer>')
            )
        except (ValueError, TypeError):
            pass

    # Idioma do dado
    data_lang = d.get('LanguageCode') or 'por'
    data_lang_w = _sub(id_info, 'gmd', 'language')
    _sub(data_lang_w, 'gmd', 'LanguageCode', attrib={
        'codeList': LOC_CL,
        'codeListValue': data_lang
    })

    # CharacterSet do dado
    _codelist(id_info, 'gmd', 'characterSet', 'MD_CharacterSetCode', 'MD_CharacterSetCode',
              d.get('characterSet') or 'utf8')

    # Categoria Temática
    topic = d.get('topicCategory')
    if topic:
        _sub(_sub(id_info, 'gmd', 'topicCategory'), 'gmd', 'MD_TopicCategoryCode', topic)

    # Extensão Geográfica
    west  = d.get('westBoundLongitude')
    east  = d.get('eastBoundLongitude')
    south = d.get('southBoundLatitude')
    north = d.get('northBoundLatitude')
    t_from = d.get('temporalFrom')
    t_to   = d.get('temporalTo')

    if any([west, east, south, north, t_from, t_to]):
        ex_extent = _sub(_sub(id_info, 'gmd', 'extent'), 'gmd', 'EX_Extent')

        if any([west, east, south, north]):
            geo_el = _sub(_sub(ex_extent, 'gmd', 'geographicElement'), 'gmd', 'EX_GeographicBoundingBox')
            for tag, val in [('westBoundLongitude', west), ('eastBoundLongitude', east),
                              ('southBoundLatitude', south), ('northBoundLatitude', north)]:
                w = _sub(geo_el, 'gmd', tag)
                dec = ET.SubElement(w, _ns('gco', 'Decimal'))
                dec.text = str(val) if val else ''

        if t_from or t_to:
            temp_el = _sub(_sub(ex_extent, 'gmd', 'temporalElement'), 'gmd', 'EX_TemporalExtent')
            time_period = ET.SubElement(
                _sub(temp_el, 'gmd', 'extent'),
                _ns('gml', 'TimePeriod'),
                {_ns('gml', 'id'): 'tp1'}
            )
            ET.SubElement(time_period, _ns('gml', 'beginPosition')).text = str(t_from) if t_from else ''
            ET.SubElement(time_period, _ns('gml', 'endPosition')).text = str(t_to) if t_to else ''

    # ── Qualidade (dataQualityInfo) ──────────────────────────────────────────
    statement   = d.get('statement')
    proc_step   = d.get('processStep')
    source_desc = d.get('sourceDescription')
    proc_contacts = d.get('processorContacts') or []

    if statement or proc_step or source_desc:
        dq = _sub(_sub(root, 'gmd', 'dataQualityInfo'), 'gmd', 'DQ_DataQuality')
        scope = _sub(_sub(dq, 'gmd', 'scope'), 'gmd', 'DQ_Scope')
        _codelist(scope, 'gmd', 'level', 'MD_ScopeCode', 'MD_ScopeCode', hier)

        lineage = _sub(_sub(dq, 'gmd', 'lineage'), 'gmd', 'LI_Lineage')
        if statement:
            _char(lineage, 'gmd', 'statement', statement)

        if proc_step:
            li_proc = _sub(_sub(lineage, 'gmd', 'processStep'), 'gmd', 'LI_ProcessStep')
            _char(li_proc, 'gmd', 'description', proc_step)
            for pc in proc_contacts:
                cd = pc.get('data', pc)
                _build_contact_block(li_proc, 'processor', cd)

        if source_desc:
            _char(
                _sub(_sub(lineage, 'gmd', 'source'), 'gmd', 'LI_Source'),
                'gmd', 'description', source_desc
            )

    # ── Distribuição (WMS/WFS/Online resources) ──────────────────────────────
    online_resources = d.get('onlineResources') or []
    # Compatibilidade com formato legado wms_data/wfs_data
    wms_data = d.get('wms_data') or {}
    wfs_data = d.get('wfs_data') or {}
    if wms_data.get('geoserver_base_url'):
        online_resources = online_resources or []
        online_resources.append({
            'url': f"{wms_data['geoserver_base_url']}/ows?service=WMS&version=1.3.0&request=GetCapabilities",
            'name': wms_data.get('geoserver_layer_name', ''),
            'description': wms_data.get('geoserver_layer_title', ''),
            'protocol': 'OGC:WMS'
        })
    if wfs_data.get('geoserver_base_url'):
        online_resources.append({
            'url': f"{wfs_data['geoserver_base_url']}/wfs",
            'name': wfs_data.get('geoserver_layer_name', ''),
            'description': wfs_data.get('geoserver_layer_title', ''),
            'protocol': 'OGC:WFS'
        })

    if online_resources:
        md_dist = _sub(_sub(_sub(root, 'gmd', 'distributionInfo'),
                            'gmd', 'MD_Distribution'),
                       'gmd', 'transferOptions')
        md_dto = _sub(md_dist, 'gmd', 'MD_DigitalTransferOptions')
        for res in online_resources:
            ci_or = _sub(_sub(md_dto, 'gmd', 'onLine'), 'gmd', 'CI_OnlineResource')
            linkage = _sub(ci_or, 'gmd', 'linkage')
            ET.SubElement(linkage, _ns('gmd', 'URL')).text = res.get('url', '')
            protocol = res.get('protocol', '')
            if protocol:
                _char(ci_or, 'gmd', 'protocol', protocol)
            name = res.get('name', '')
            if name:
                _char(ci_or, 'gmd', 'name', name)
            desc = res.get('description', '')
            if desc:
                _char(ci_or, 'gmd', 'description', desc)

    return ET.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8').decode('utf-8')
