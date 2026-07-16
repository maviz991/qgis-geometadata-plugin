# -*- coding: utf-8 -*-
"""
gateway_login_dialog.py - GeoMetadata Plugin
=============================================
Login SSO corporativo via sessão do gateway geOrchestra (não via Bearer JWT
direto do Azure AD).

O gateway geOrchestra só está configurado como OAuth2 Client (login por
navegador + sessão/cookie) - não existe um Resource Server que valide um
Bearer JWT obtido fora do fluxo dele. Por isso o plugin precisa navegar pelo
mesmo caminho que um navegador faria: abrir o endpoint de login do próprio
gateway numa QWebEngineView embutida, deixar o redirect completo rodar
(gateway -> Azure AD -> volta pro gateway) e capturar o cookie de sessão
resultante - é essa sessão que o gateway usa pra injetar os headers
sec-username/sec-roles nas chamadas proxied pro GeoServer e GeoNetwork.

GatewaySSOWidget é um QWidget (não QDialog): é inserido no content_stack da
janela principal do plugin no lugar do web_view normal enquanto o login
acontece, em vez de abrir uma janela popup separada.

Autor: GeoMetadata Plugin | CDHU
"""

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget
from qgis.PyQt.QtCore import Qt, QUrl, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QPen, QColor

try:
    from qgis.PyQt.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage
except ImportError:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage


_OIDC_REGISTRATION_ID = "entraid"


class _InsecurePage(QWebEnginePage):
    """QWebEnginePage que ignora erros de certificado - mesmo motivo do
    verify=False usado em toda chamada requests do plugin (certificado
    corporativo do ambiente GeoOrchestra não é confiável por padrão)."""

    def certificateError(self, error):
        print(f"GeoMetadata [GatewaySSOWidget] certificado ignorado: {error.description()}")
        try:
            error.acceptCertificate()
        except AttributeError:
            pass
        return True


class _SpinnerWidget(QWidget):
    """Spinner circular nativo - mesmo estilo visual do spinner CSS usado no
    resto do plugin (anel cinza com segmento vermelho de accent girando, ver
    .search-spinner em ui/templates/css/geonetwork.css: border cinza +
    border-top-color #e5222d, animação de rotação)."""

    _RING_COLOR   = QColor("#bfc3c9")
    _ACCENT_COLOR = QColor("#e5222d")

    def __init__(self, parent=None, diameter=36):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)

    def _rotate(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen_width = max(2, self.width() // 12)
        rect = self.rect().adjusted(pen_width, pen_width, -pen_width, -pen_width)

        pen = QPen(self._RING_COLOR)
        pen.setWidth(pen_width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)

        pen.setColor(self._ACCENT_COLOR)
        painter.setPen(pen)
        painter.drawArc(rect, -self._angle * 16, 90 * 16)


class GatewaySSOWidget(QWidget):
    """
    Widget de login SSO via sessão do gateway geOrchestra, pra ser trocado no
    content_stack da janela principal (não é uma janela separada).

    Uso:
        widget = GatewaySSOWidget(base_url, verify_url, parent=stack)
        widget.login_succeeded.connect(lambda session, username: ...)
        widget.login_failed.connect(lambda msg: ...)
        stack.addWidget(widget)
        stack.setCurrentWidget(widget)
    """

    login_succeeded = pyqtSignal(object, str)  # session, username
    login_failed    = pyqtSignal(str)          # mensagem de erro/cancelamento

    def __init__(self, base_url: str, verify_url: str, parent=None):
        super().__init__(parent)
        self._base_url   = base_url.rstrip('/')
        self._base_host  = QUrl(self._base_url).host()
        self._verify_url = verify_url

        self._left_for_idp = False
        self._verifying     = False
        self._done           = False
        self._retry_count    = 0
        self._cookies = {}  # (name, domain, path) -> value

        self._build_ui()
        self._start_login()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(12, 8, 12, 0)
        self._status_label = QLabel("Aguardando login...")
        header.addWidget(self._status_label)
        header.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(
            "QPushButton {"
            "  padding: 4px 14px; border-radius: 4px;"
            "  border: 1px solid rgba(0,0,0,0.2); background: transparent;"
            "}"
            "QPushButton:hover { background: rgba(229,34,45,0.1); border-color: #e5222d; color: #e5222d; }"
        )
        btn_cancel.clicked.connect(self._on_cancel)
        header.addWidget(btn_cancel)
        layout.addLayout(header)

        # Profile isolado (não persiste em disco) - evita misturar cookies
        # dessa tentativa de login com o resto da UI do plugin.
        self._profile = QWebEngineProfile(self)
        self._profile.cookieStore().cookieAdded.connect(self._on_cookie_added)

        self._view = QWebEngineView(self)
        self._view.setPage(_InsecurePage(self._profile, self._view))
        self._view.loadStarted.connect(lambda: self._status_label.setText("Carregando..."))
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.urlChanged.connect(self._on_url_changed)

        # Assim que voltamos pro domínio do gateway (login concluído no Azure AD),
        # a QWebEngineView chega a renderizar a página do próprio sistema Geohab por
        # um instante antes da gente confirmar a sessão e voltar pra UI do plugin -
        # esse "flash" é escondido trocando pra esse placeholder nesse meio-tempo.
        self._finishing_widget = QWidget()
        finishing_layout = QVBoxLayout(self._finishing_widget)
        finishing_layout.setAlignment(Qt.AlignCenter)
        finishing_layout.setSpacing(14)
        finishing_layout.addWidget(_SpinnerWidget(diameter=36), alignment=Qt.AlignCenter)
        finishing_text = QLabel("Finalizando login...")
        finishing_text.setAlignment(Qt.AlignCenter)
        finishing_layout.addWidget(finishing_text)

        self._browser_stack = QStackedWidget()
        self._browser_stack.addWidget(self._view)
        self._browser_stack.addWidget(self._finishing_widget)
        layout.addWidget(self._browser_stack)

    # ------------------------------------------------------------------
    # Fluxo de login
    # ------------------------------------------------------------------

    def _start_login(self):
        login_url = f"{self._base_url}/oauth2/authorization/{_OIDC_REGISTRATION_ID}"
        self._view.load(QUrl(login_url))

    def _on_cookie_added(self, cookie):
        name   = bytes(cookie.name()).decode('utf-8', 'ignore')
        value  = bytes(cookie.value()).decode('utf-8', 'ignore')
        domain = cookie.domain()
        path   = cookie.path()
        self._cookies[(name, domain, path)] = value

    def _on_url_changed(self, url: QUrl):
        if url.host() and url.host() != self._base_host:
            self._left_for_idp = True
        elif self._left_for_idp:
            # Voltamos pro domínio do gateway - esconde a view ANTES dela
            # renderizar a página do sistema (troca no urlChanged, não no
            # loadFinished, pra pegar antes do primeiro paint).
            self._browser_stack.setCurrentWidget(self._finishing_widget)

    def _on_load_finished(self, ok: bool):
        if self._done or self._verifying:
            return
        if not ok:
            print(f"GeoMetadata [GatewaySSOWidget] falha ao carregar: {self._view.url().toString()}")
            self._status_label.setText("Falha ao carregar a página de login.")
            return
        current_host = self._view.url().host()
        # Só faz sentido validar depois de termos saído pro Azure AD e voltado -
        # o load inicial (navegação pro próprio /oauth2/authorization/...) também
        # acontece no host do gateway, antes do redirect pra Microsoft.
        if not self._left_for_idp or current_host != self._base_host:
            return
        self._browser_stack.setCurrentWidget(self._finishing_widget)
        self._status_label.setText("Validando sessão...")
        self._try_verify()

    def _try_verify(self):
        self._verifying = True
        try:
            session = requests.Session()
            session.verify = False
            for (name, domain, path), value in self._cookies.items():
                session.cookies.set(name, value, domain=domain, path=path or '/')

            resp = session.get(
                self._verify_url, timeout=10,
                headers={'Accept': 'application/json'}
            )
            content_type = resp.headers.get('Content-Type', '')
            print(f"GeoMetadata [GatewaySSOWidget] verify {self._verify_url} -> "
                  f"status={resp.status_code} content-type={content_type} "
                  f"cookies={list(session.cookies.keys())}")
            if resp.status_code == 200 and 'json' in content_type:
                data = resp.json() or {}
                username = (
                    data.get('name')
                    or data.get('username')
                    or data.get('email')
                    or data.get('id')
                    or "Usuário CDHU"
                )
                self._done = True
                self.login_succeeded.emit(session, str(username))
                return
            self._status_label.setText(
                f"Sessão ainda não confirmada (HTTP {resp.status_code}) - tentando de novo..."
            )
        except requests.exceptions.RequestException as exc:
            print(f"GeoMetadata [GatewaySSOWidget] erro ao verificar sessão: {exc}")
            self._status_label.setText(f"Erro ao verificar sessão: {exc}")
        finally:
            self._verifying = False
        # Ainda pode ser um hop intermediário do redirect, ou o cookie de sessão
        # ter chegado um instante depois do load - tenta de novo em 1.5s em vez de
        # ficar parado esperando outro loadFinished que pode não vir mais. Limitado
        # pra não martelar o servidor pra sempre se for uma falha genuína.
        self._retry_count += 1
        if self._retry_count > 15:
            self._status_label.setText(
                "Não foi possível confirmar o login (veja o console do Python)."
            )
            return
        QTimer.singleShot(1500, self._retry_verify)

    def _retry_verify(self):
        if self._done or self._verifying:
            return
        self._try_verify()

    def _on_cancel(self):
        if self._done:
            return
        self._done = True
        self.login_failed.emit("Login cancelado.")
