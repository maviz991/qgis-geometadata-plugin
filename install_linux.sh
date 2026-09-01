#!/usr/bin/env bash
# =============================================================================
# install_linux.sh — GeoMetadata Plugin | CDHU
# =============================================================================
# Setup das dependências do plugin no Linux (Ubuntu/Debian com QGIS via apt).
#
# O que faz:
#   1. Instala pacotes Python do sistema via apt (PyQtWebEngine, lxml, psycopg2,
#      certifi) — mais confiável que pip no Python do sistema do QGIS.
#   2. Instala o certificado CA corporativo da CDHU em local gravável pelo usuário
#      (~/.config/GeoMetadata/cdhu-ca.pem) e configura REQUESTS_CA_BUNDLE no
#      ~/.bashrc — substitui o ca_installer.py que no Linux não tem permissão
#      de escrever no bundle do certifi do sistema.
#   3. Garante que ~/.local/lib/pythonX.Y/site-packages está no sys.path do
#      QGIS (patcheia o arquivo usercustomize.py do QGIS), resolvendo o mesmo
#      bug do env_checker.py que só corrigia o path no Windows.
#   4. Cria um atalho de shell para abrir o QGIS com as variáveis corretas.
#
# Uso:
#   chmod +x install_linux.sh
#   ./install_linux.sh
#
# Seguro para rodar mais de uma vez (idempotente).
# Requer: bash, sudo (apenas para apt), python3 (do sistema).
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Cores e helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✔${NC}  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✘${NC}  $*" >&2; }
info() { echo -e "${CYAN}→${NC}  $*"; }
sep()  { echo -e "${BOLD}──────────────────────────────────────────${NC}"; }

# ---------------------------------------------------------------------------
# Diretório do script (raiz do plugin)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$SCRIPT_DIR"
ASSETS_DIR="$PLUGIN_DIR/assets"
CA_CERT_SRC="$ASSETS_DIR/cdhu-ca.pem"

sep
echo -e "${BOLD}GeoMetadata Plugin — Instalação Linux${NC}"
echo "  Plugin: $PLUGIN_DIR"
sep

# ---------------------------------------------------------------------------
# 1. Detectar versão do Python do QGIS
# ---------------------------------------------------------------------------
info "Detectando Python do QGIS..."

# Tenta encontrar o Python associado ao QGIS (mesma lógica do dependency_installer.py)
PYTHON3=""
for candidate in python3 python3.12 python3.11 python3.10 python3.9; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON3="$(command -v "$candidate")"
        break
    fi
done

if [ -z "$PYTHON3" ]; then
    err "python3 não encontrado. Instale o QGIS antes de rodar este script."
    exit 1
fi

PY_VERSION="$("$PYTHON3" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
ok "Python: $PYTHON3 (versão $PY_VERSION)"

# ---------------------------------------------------------------------------
# 2. Detectar distro
# ---------------------------------------------------------------------------
info "Detectando distribuição Linux..."
DISTRO=""
if command -v apt-get &>/dev/null; then
    DISTRO="debian"
    ok "Distro: Debian/Ubuntu (apt)"
elif command -v dnf &>/dev/null; then
    DISTRO="fedora"
    warn "Distro: Fedora/RHEL — nomes de pacotes podem diferir. Verifique manualmente."
elif command -v pacman &>/dev/null; then
    DISTRO="arch"
    warn "Distro: Arch Linux — instale via pacman manualmente."
else
    DISTRO="unknown"
    warn "Distro não reconhecida — apenas a parte sem sudo será executada."
fi

# ---------------------------------------------------------------------------
# 3. Instalar dependências via apt (Debian/Ubuntu)
# ---------------------------------------------------------------------------
sep
echo -e "${BOLD}[1/4] Dependências do sistema${NC}"

if [ "$DISTRO" = "debian" ]; then
    # Mapeia versões do Python para nomes de pacote apt
    # Ubuntu 22.04 = python3.10, 24.04 = python3.12
    PY_SHORT="${PY_VERSION//./}"  # ex: "310", "312"

    APT_PACKAGES=(
        "python3-lxml"
        "python3-requests"
        "python3-certifi"
        "python3-psycopg2"
    )

    # PyQtWebEngine: nome varia por distro/versão
    WEBENGINE_PKG=""
    for pkg in "python3-pyqt5.qtwebengine" "python3-pyqtwebengine"; do
        if apt-cache show "$pkg" &>/dev/null 2>&1; then
            WEBENGINE_PKG="$pkg"
            break
        fi
    done
    [ -n "$WEBENGINE_PKG" ] && APT_PACKAGES+=("$WEBENGINE_PKG")

    info "Atualizando lista de pacotes (sudo)..."
    sudo apt-get update -qq

    for pkg in "${APT_PACKAGES[@]}"; do
        if dpkg -s "$pkg" &>/dev/null 2>&1; then
            ok "$pkg já instalado"
        else
            info "Instalando $pkg..."
            sudo apt-get install -y -qq "$pkg" && ok "$pkg instalado" || warn "Falha ao instalar $pkg — verifique manualmente"
        fi
    done

    # Verificar se pyqtwebengine foi instalado
    if [ -z "$WEBENGINE_PKG" ]; then
        warn "PyQtWebEngine não encontrado nos repositórios."
        warn "Tente: sudo apt-get install python3-pyqt5.qtwebengine"
        warn "Ou instale o QGIS via repositório oficial: https://qgis.org/install"
    fi

elif [ "$DISTRO" = "fedora" ]; then
    warn "Fedora/RHEL detectado. Instale manualmente:"
    echo "  sudo dnf install python3-lxml python3-requests python3-certifi python3-psycopg2"
    echo "  sudo dnf install python3-qt5-webengine  # ou equivalente"
elif [ "$DISTRO" = "arch" ]; then
    warn "Arch detectado. Instale manualmente:"
    echo "  sudo pacman -S python-lxml python-requests python-certifi python-psycopg2"
    echo "  sudo pacman -S python-pyqt5-webengine  # ou equivalente"
fi

# ---------------------------------------------------------------------------
# 4. Certificado CA corporativo CDHU
# ---------------------------------------------------------------------------
sep
echo -e "${BOLD}[2/4] Certificado CA corporativo${NC}"

CA_USER_DIR="$HOME/.config/GeoMetadata"
CA_USER_DEST="$CA_USER_DIR/cdhu-ca.pem"
BASHRC="$HOME/.bashrc"

mkdir -p "$CA_USER_DIR"

if [ -f "$CA_CERT_SRC" ]; then
    cp "$CA_CERT_SRC" "$CA_USER_DEST"
    ok "Certificado copiado para $CA_USER_DEST"

    # Verificar se o cert é válido (formato PEM básico)
    if grep -q "BEGIN CERTIFICATE" "$CA_USER_DEST"; then
        ok "Formato PEM verificado"
    else
        warn "O arquivo $CA_CERT_SRC não parece um PEM válido. Verifique com o TI."
    fi

    # Configurar REQUESTS_CA_BUNDLE no ~/.bashrc (idempotente)
    EXPORT_LINE="export REQUESTS_CA_BUNDLE=\"$CA_USER_DEST\""
    MARKER="# GeoMetadata Plugin - CDHU Corporate CA"

    if grep -qF "$MARKER" "$BASHRC" 2>/dev/null; then
        ok "REQUESTS_CA_BUNDLE já configurado em $BASHRC"
    else
        {
            echo ""
            echo "$MARKER"
            echo "$EXPORT_LINE"
        } >> "$BASHRC"
        ok "REQUESTS_CA_BUNDLE adicionado em $BASHRC"
    fi

    # Aplicar na sessão atual
    export REQUESTS_CA_BUNDLE="$CA_USER_DEST"
    ok "REQUESTS_CA_BUNDLE ativo nesta sessão"

    # Também configura SSL_CERT_FILE (usado por OpenSSL/urllib3 diretamente)
    SSL_LINE="export SSL_CERT_FILE=\"$CA_USER_DEST\""
    if ! grep -qF "SSL_CERT_FILE" "$BASHRC" 2>/dev/null; then
        echo "export SSL_CERT_FILE=\"$CA_USER_DEST\"" >> "$BASHRC"
    fi
    export SSL_CERT_FILE="$CA_USER_DEST"

else
    warn "assets/cdhu-ca.pem não encontrado."
    warn "Peça ao TI para exportar o certificado raiz do proxy reverso (geo.cdhu.sp.gov.br)"
    warn "e colocar em: $CA_CERT_SRC"
    warn "Enquanto isso, o plugin usará verify=False como fallback."
fi

# ---------------------------------------------------------------------------
# 5. Corrigir sys.path do QGIS para incluir pip --user no Linux
# ---------------------------------------------------------------------------
sep
echo -e "${BOLD}[3/4] Configuração do sys.path do QGIS (pip --user)${NC}"

USER_SITE="$("$PYTHON3" -m site --user-site 2>/dev/null || echo "")"
if [ -z "$USER_SITE" ]; then
    warn "Não foi possível determinar o user site-packages. Pulando."
else
    ok "User site-packages: $USER_SITE"
    mkdir -p "$USER_SITE"

    # usercustomize.py é executado automaticamente pelo Python antes de qualquer import,
    # incluindo quando o QGIS inicia — é o ponto correto para injetar o path no Linux.
    # No Windows o env_checker.py já faz isso, mas só com `if os.name == 'nt'`.
    CUSTOMIZE="$USER_SITE/usercustomize.py"
    MARKER_UC="# GeoMetadata Plugin - user site-packages path injection"

    if [ -f "$CUSTOMIZE" ] && grep -qF "$MARKER_UC" "$CUSTOMIZE"; then
        ok "usercustomize.py já configurado"
    else
        cat >> "$CUSTOMIZE" << PYEOF

$MARKER_UC
import sys, site as _site
_us = _site.getusersitepackages()
if _us not in sys.path:
    sys.path.insert(0, _us)
PYEOF
        ok "usercustomize.py atualizado em $CUSTOMIZE"
    fi
fi

# ---------------------------------------------------------------------------
# 6. Criar atalho qgis-cdhu no PATH do usuário
# ---------------------------------------------------------------------------
sep
echo -e "${BOLD}[4/4] Atalho de terminal para QGIS com variáveis CDHU${NC}"

BIN_DIR="$HOME/.local/bin"
QGIS_WRAPPER="$BIN_DIR/qgis-cdhu"
mkdir -p "$BIN_DIR"

# Detectar executável do QGIS
QGIS_BIN=""
for q in qgis qgis3 /usr/bin/qgis /usr/bin/qgis3; do
    if command -v "$q" &>/dev/null || [ -x "$q" ]; then
        QGIS_BIN="$(command -v "$q" 2>/dev/null || echo "$q")"
        break
    fi
done

if [ -n "$QGIS_BIN" ]; then
    cat > "$QGIS_WRAPPER" << WRAPEOF
#!/usr/bin/env bash
# Inicia o QGIS com as variáveis de ambiente do GeoMetadata Plugin CDHU
export REQUESTS_CA_BUNDLE="$CA_USER_DEST"
export SSL_CERT_FILE="$CA_USER_DEST"
exec "$QGIS_BIN" "\$@"
WRAPEOF
    chmod +x "$QGIS_WRAPPER"
    ok "Atalho criado: $QGIS_WRAPPER"
    info "Use 'qgis-cdhu' no terminal para abrir o QGIS com o certificado configurado."

    # Garantir que ~/.local/bin está no PATH
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$BASHRC"
        export PATH="$BIN_DIR:$PATH"
        ok "~/.local/bin adicionado ao PATH em $BASHRC"
    fi
else
    warn "Executável do QGIS não encontrado. Crie manualmente o wrapper se necessário."
fi

# ---------------------------------------------------------------------------
# Verificação final
# ---------------------------------------------------------------------------
sep
echo -e "${BOLD}Verificação final${NC}"

ERRORS=0

check_import() {
    local module="$1" label="$2"
    if "$PYTHON3" -c "import $module" &>/dev/null 2>&1; then
        ok "$label disponível"
    else
        warn "$label NÃO disponível — instale manualmente"
        ERRORS=$((ERRORS + 1))
    fi
}

check_import lxml        "lxml"
check_import requests    "requests"
check_import certifi     "certifi"
check_import psycopg2    "psycopg2"

# PyQtWebEngine — não pode ser testado fora do QGIS (precisa de display)
info "PyQtWebEngine: verificação só é possível dentro do QGIS (requer display Qt)"

if [ -f "$CA_USER_DEST" ]; then
    ok "Certificado CA: $CA_USER_DEST"
else
    warn "Certificado CA: não configurado (verificar com TI)"
    ERRORS=$((ERRORS + 1))
fi

sep
if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✔ Instalação concluída com sucesso!${NC}"
else
    echo -e "${YELLOW}${BOLD}⚠ Instalação concluída com $ERRORS aviso(s). Verifique os itens acima.${NC}"
fi

echo ""
echo -e "${BOLD}Próximos passos:${NC}"
echo "  1. Feche e reabra o terminal (ou execute: source ~/.bashrc)"
echo "  2. Abra o QGIS com: qgis-cdhu"
echo "  3. No QGIS, vá em Plugins → Gerir e Instalar Plugins → GeoMetadata"
echo ""
if [ -z "$QGIS_BIN" ]; then
    echo -e "${YELLOW}  ⚠ Instale o QGIS: sudo apt-get install qgis${NC}"
fi
sep
