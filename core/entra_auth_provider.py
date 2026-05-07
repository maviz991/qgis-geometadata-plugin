# -*- coding: utf-8 -*-
"""
entra_auth_provider.py — GeoMetadata Plugin
============================================
Provedor de autenticação via Microsoft Entra ID (Azure AD).

Fluxo: OAuth2 Authorization Code + PKCE (Public Client)
Biblioteca: msal (Microsoft Authentication Library for Python)

O plugin abre o navegador padrão do usuário para login com conta corporativa.
Após a autenticação, o token Bearer é injetado automaticamente em todas as
requisições via BearerTokenAuth (requests.AuthBase).

Autor: GeoMetadata Plugin | CDHU
"""

import requests
from requests.auth import AuthBase


# ---------------------------------------------------------------------------
# Verificação de dependência: msal
# ---------------------------------------------------------------------------
try:
    import msal
    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False


def is_msal_available():
    """Retorna True se a biblioteca msal estiver instalada."""
    return MSAL_AVAILABLE


def get_msal_install_instructions():
    """Retorna instruções de instalação do msal para o ambiente QGIS."""
    return (
        "<p><b>A biblioteca <code>msal</code> não está instalada.</b></p>"
        "<p>Para instalar, abra o <b>OSGeo4W Shell</b> e execute:</p>"
        "<pre>pip install msal</pre>"
        "<p>Depois reinicie o QGIS.</p>"
    )


# ---------------------------------------------------------------------------
# BearerTokenAuth — injeta o token Bearer em cada requisição
# ---------------------------------------------------------------------------
class BearerTokenAuth(AuthBase):
    """
    Implementação de requests.AuthBase que injeta o header
    'Authorization: Bearer <token>' em cada chamada HTTP.

    Responsabilidades:
    - Verificar se o token em cache ainda é válido
    - Solicitar um novo token silenciosamente (refresh) quando possível
    - Deixar o provider decidir quando interação do usuário é necessária
    """

    def __init__(self, provider):
        """
        :param provider: Instância de EntraAuthProvider
        """
        self._provider = provider

    def __call__(self, r):
        """Chamado pelo requests antes de cada requisição."""
        token = self._provider.get_valid_token()
        if token:
            r.headers["Authorization"] = f"Bearer {token}"
        return r


# ---------------------------------------------------------------------------
# EntraAuthProvider — gerenciador principal da autenticação Entra ID
# ---------------------------------------------------------------------------
class EntraAuthProvider:
    """
    Gerencia o ciclo de vida da autenticação via Microsoft Entra ID.

    Uso básico:
        provider = EntraAuthProvider(client_id, tenant_id, scopes)
        success = provider.authenticate_interactive()
        if success:
            session = provider.get_session()
            username = provider.get_username()
    """

    def __init__(self, client_id: str, tenant_id: str, scopes: list):
        """
        :param client_id: Application (Client) ID do App Registration no Azure
        :param tenant_id: Directory (Tenant) ID do Azure AD
        :param scopes: Lista de escopos OAuth2, ex: ["openid", "profile", "email"]
        """
        if not MSAL_AVAILABLE:
            raise RuntimeError(
                "A biblioteca 'msal' não está disponível. "
                "Instale via: pip install msal"
            )

        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes = scopes
        self._authority = f"https://login.microsoftonline.com/{tenant_id}"

        # Cache de token em memória (sem persistência em disco por ora)
        self._token_cache = msal.SerializableTokenCache()

        # Instância da aplicação MSAL (Public Client — sem client_secret)
        self._app = msal.PublicClientApplication(
            client_id=self._client_id,
            authority=self._authority,
            token_cache=self._token_cache
        )

        # Resultado do último acquire_token (dict com access_token, id_token, etc.)
        self._token_result = None

    # ------------------------------------------------------------------
    # Autenticação
    # ------------------------------------------------------------------

    def authenticate_interactive(self) -> bool:
        """
        Inicia o fluxo OAuth2 + PKCE abrindo o navegador padrão do sistema.

        1. Tenta primeiro um acquire silencioso (token em cache / refresh)
        2. Se não houver conta em cache, abre o browser para login interativo
        3. O Azure redireciona para http://localhost após autenticação

        :returns: True se autenticação bem-sucedida, False caso contrário.
        """
        # Passo 1: Tenta usar conta já em cache para refresh silencioso
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(
                scopes=self._scopes,
                account=accounts[0]
            )
            if result and "access_token" in result:
                self._token_result = result
                return True

        # Passo 2: Nenhum token em cache — abre browser para login interativo
        # O msal gerencia o listener localhost automaticamente (PKCE)
        result = self._app.acquire_token_interactive(scopes=self._scopes)

        if result and "access_token" in result:
            self._token_result = result
            return True

        # Falhou — armazena o erro para inspeção
        self._token_result = result or {}
        return False

    def logout(self):
        """Remove todos os tokens do cache e limpa o estado."""
        accounts = self._app.get_accounts()
        for account in accounts:
            self._app.remove_account(account)
        self._token_result = None

    # ------------------------------------------------------------------
    # Acesso aos dados do token
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        """Retorna True se há um token válido em memória."""
        return (
            self._token_result is not None
            and "access_token" in self._token_result
        )

    def get_valid_token(self) -> str:
        """
        Retorna um access_token válido.
        Tenta refresh silencioso se o token em cache expirou.
        Retorna string vazia se não autenticado.
        """
        if not self.is_authenticated():
            return ""

        # Tenta refresh silencioso se houver conta em cache
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(
                scopes=self._scopes,
                account=accounts[0]
            )
            if result and "access_token" in result:
                self._token_result = result

        return self._token_result.get("access_token", "")

    def get_username(self) -> str:
        """
        Extrai o nome/e-mail do usuário a partir dos claims do token.
        Ordem de preferência: preferred_username > name > upn > email
        """
        if not self.is_authenticated():
            return ""

        # Claims do ID Token (OpenID Connect)
        id_token_claims = self._token_result.get("id_token_claims", {})

        username = (
            id_token_claims.get("name")
            or id_token_claims.get("preferred_username")
            or id_token_claims.get("upn")
            or id_token_claims.get("email")
            or "Usuário Conectado"
        )
        return username

    def get_access_token(self) -> str:
        """Retorna o access token raw. Útil para debug."""
        if not self.is_authenticated():
            return ""
        return self._token_result.get("access_token", "")

    def get_error(self) -> str:
        """Retorna a descrição do erro em caso de falha de autenticação."""
        if not self._token_result:
            return "Nenhuma tentativa de autenticação realizada."
        error = self._token_result.get("error", "")
        desc = self._token_result.get("error_description", "")
        return f"{error}: {desc}" if error else ""

    # ------------------------------------------------------------------
    # Sessão requests
    # ------------------------------------------------------------------

    def get_session(self) -> requests.Session:
        """
        Cria e retorna uma requests.Session configurada com BearerTokenAuth.

        O BearerTokenAuth injeta o header Authorization: Bearer <token>
        em cada requisição, com refresh automático quando necessário.

        verify=False é mantido por compatibilidade com o certificado
        corporativo do ambiente GeoOrchestra (mesmo comportamento atual).
        """
        session = requests.Session()
        session.verify = False
        session.auth = BearerTokenAuth(self)
        return session
