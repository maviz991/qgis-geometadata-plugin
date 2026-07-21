# -*- coding: utf-8 -*-
"""
ca_installer.py - GeoMetadata Plugin
======================================
Gerencia o certificado CA corporativo da CDHU (proxy reverso autoassinado).

Responsabilidades:
- Localizar o bundle cacert.pem do certifi usado pelo Python do QGIS
- Verificar se o certificado corporativo já está instalado (idempotente)
- Instalar o certificado no bundle de forma segura (append, sem sobrescrever)
- Exportar CA_BUNDLE: caminho a ser usado em session.verify no lugar de False

O certificado deve estar em assets/cdhu-ca.pem.
Se o arquivo não existir, CA_BUNDLE = False (comportamento legado – verify=False).

Autor: GeoMetadata Plugin | CDHU
"""

import os
import logging

log = logging.getLogger(__name__)

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(__file__))
_CERT_SOURCE = os.path.join(_PLUGIN_ROOT, "assets", "cdhu-ca.pem")

# Marcador único injetado antes do bloco do certificado no cacert.pem
# para verificação idempotente (não instalar duas vezes).
_MARKER = "# GeoMetadata Plugin - CDHU Corporate CA"


def _certifi_bundle_path() -> str:
    """Retorna o caminho do cacert.pem do certifi instalado no Python do QGIS.
    Levanta ImportError se o certifi não estiver disponível."""
    import certifi  # noqa: PLC0415 – import tardio intencional
    return certifi.where()


def is_ca_cert_available() -> bool:
    """True se o arquivo cdhu-ca.pem existe em assets/."""
    return os.path.isfile(_CERT_SOURCE)


def is_ca_cert_installed() -> bool:
    """True se o certificado corporativo já foi injetado no bundle do certifi.
    Verifica pela presença do marcador – operação de leitura apenas."""
    if not is_ca_cert_available():
        return False
    try:
        bundle = _certifi_bundle_path()
        if not os.path.isfile(bundle):
            return False
        with open(bundle, "r", encoding="utf-8", errors="ignore") as fh:
            return _MARKER in fh.read()
    except Exception as exc:
        log.warning("GeoMetadata [ca_installer] erro ao verificar bundle: %s", exc)
        return False


def install_ca_cert() -> bool:
    """Instala o certificado corporativo no bundle do certifi (append).

    - Idempotente: não instala se o marcador já estiver presente.
    - Não modifica nenhum arquivo fora do bundle do certifi.
    - Retorna True se a instalação foi realizada ou já estava presente.
    - Retorna False em caso de erro (sem levantar exceção – o plugin deve
      continuar funcionando em modo degradado com verify=False).
    """
    if not is_ca_cert_available():
        log.info(
            "GeoMetadata [ca_installer] cdhu-ca.pem não encontrado em assets/ "
            "– pulando instalação da CA corporativa."
        )
        return False

    if is_ca_cert_installed():
        log.debug("GeoMetadata [ca_installer] CA corporativa já instalada – nada a fazer.")
        return True

    try:
        bundle = _certifi_bundle_path()
        with open(_CERT_SOURCE, "r", encoding="utf-8", errors="ignore") as src:
            cert_pem = src.read().strip()

        with open(bundle, "a", encoding="utf-8") as dst:
            dst.write(f"\n{_MARKER}\n")
            dst.write(cert_pem)
            dst.write("\n")

        log.info("GeoMetadata [ca_installer] CA corporativa instalada em: %s", bundle)
        return True

    except Exception as exc:
        log.warning(
            "GeoMetadata [ca_installer] falha ao instalar CA corporativa: %s "
            "– o plugin continuará com verify=False como fallback.",
            exc,
        )
        return False


def get_ca_bundle():
    """Retorna o caminho do bundle certifi se o cert corporativo estiver
    instalado, ou False como fallback (comportamento legado verify=False).

    Uso em qualquer chamada requests/session:
        session.verify = get_ca_bundle()
    """
    if not is_ca_cert_available():
        return False
    try:
        if is_ca_cert_installed():
            return _certifi_bundle_path()
    except Exception:
        pass
    return False
