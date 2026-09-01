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

import logging
import warnings
import requests
import urllib3

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget
from qgis.PyQt.QtCore import Qt, QUrl, QTimer, QThread, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QPen, QColor

try:
    from qgis.PyQt.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage
except ImportError:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage

try:
    from ..core.ca_installer import get_ca_bundle as _get_ca_bundle
except Exception:
    def _get_ca_bundle():
        return False

log = logging.getLogger(__name__)

try:
    from contextlib import nullcontext as _nullcontext  # Python 3.7+
except ImportError:
    from contextlib import contextmanager
    @contextmanager
    def _nullcontext(*_a, **_kw):
        yield


_OIDC_REGISTRATION_ID = "entraid"


class _InsecurePage(QWebEnginePage):
    """QWebEnginePage que ignora erros de certificado - mesmo motivo do
    verify=False usado em toda chamada requests do plugin (certificado
    corporativo do ambiente GeoOrchestra não é confiável por padrão)."""

    def certificateError(self, error):
        log.debug("GeoMetadata [GatewaySSOWidget] certificado corporativo aceito: %s", error.description())
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


class _VerifySessionWorker(QThread):
    """Confere a sessão do gateway em background (mesmo padrão RNF02 de
    _GsSyncCheckWorker, ui/geoserver_workers.py) - a chamada requests.get aqui
    rodava direto em GatewaySSOWidget._try_verify, na thread principal do Qt,
    bloqueando o event loop inteiro (inclusive o QTimer que anima
    _SpinnerWidget - por isso ele "travava" durante cada tentativa) pelos até
    10s do timeout, repetido a cada 1.5s de retry."""
    done = pyqtSignal(object)  # dict: {'ok': bool, 'status':, 'content_type':, 'cookies':, 'data':, 'session':} ou {'ok': False, 'error':}

    def __init__(self, verify_url, cookies_snapshot, parent=None):
        super().__init__(parent)
        self._verify_url = verify_url
        self._cookies = cookies_snapshot  # cópia feita na thread principal antes do start() - ver _try_verify

    def run(self):
        ca_bundle = _get_ca_bundle()
        try:
            session = requests.Session()
            session.verify = ca_bundle
            for (name, domain, path), value in self._cookies.items():
                session.cookies.set(name, value, domain=domain, path=path or '/')

            # Supressão de aviso de certificado com escopo restrito a esta chamada:
            # só ativa quando a CA corporativa não está disponível (fallback legado).
            ctx_mgr = (
                warnings.catch_warnings() if not ca_bundle else _nullcontext()
            )
            with ctx_mgr:
                if not ca_bundle:
                    warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
                resp = session.get(
                    self._verify_url, timeout=10,
                    headers={'Accept': 'application/json'}
                )
            content_type = resp.headers.get('Content-Type', '')
            result = {
                'ok': True, 'status': resp.status_code, 'content_type': content_type,
                'cookies': list(session.cookies.keys()), 'session': session, 'data': None
            }
            if resp.status_code == 200 and 'json' in content_type:
                try:
                    result['data'] = resp.json() or {}
                except ValueError:
                    pass
            self.done.emit(result)
        except requests.exceptions.RequestException as exc:
            self.done.emit({'ok': False, 'error': str(exc)})


class _ChevronBackButton(QWidget):
    """Botão "‹ Voltar" com o chevron maior que o texto. Rich text (font-size
    inline em QLabel) não deu contraste suficiente - isso usa dois QLabel
    separados com QFont.setPointSize() explícito (mais confiável/determinístico
    que CSS font-size dentro de texto rico), lado a lado num container clicável."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChevronBackButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 2, 16, 2)
        layout.setSpacing(2)

        chevron = QLabel("❮")
        chevron_font = chevron.font()
        chevron_font.setPointSize(chevron_font.pointSize() + 2)
        chevron.setFont(chevron_font)
        layout.addWidget(chevron)

        text = QLabel("Voltar")
        text_font = text.font()
        text_font.setPointSize(text_font.pointSize() + 1)
        text.setFont(text_font)
        layout.addWidget(text)

        self.setStyleSheet(
            "#ChevronBackButton {"
            "  border-radius: 10px; border: 1px solid rgba(0,0,0,0.25);"
            "  background: rgba(255,255,255,0.92);"
            "}"
            "#ChevronBackButton QLabel { color: #363636; background: transparent; }"
            "#ChevronBackButton:hover { background: #363636; border-color: #363636; }"
            "#ChevronBackButton:hover QLabel { color: white; }"
        )

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


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
        self._verify_worker  = None
        self._cookies = {}  # (name, domain, path) -> value

        self._build_ui()
        self._start_login()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Profile isolado (não persiste em disco) - evita misturar cookies
        # dessa tentativa de login com o resto da UI do plugin.
        self._profile = QWebEngineProfile(self)
        self._profile.cookieStore().cookieAdded.connect(self._on_cookie_added)
        # QWebEngineView embutida não herda o idioma do sistema como o navegador
        # padrão faz (Accept-Language) - sem isso a página do Azure AD vem em
        # inglês mesmo com o Windows/navegador em pt-BR.
        try:
            self._profile.setHttpAcceptLanguage("pt-BR,pt;q=0.9,en;q=0.8")
        except AttributeError:
            pass

        self._view = QWebEngineView(self)
        self._view.setPage(_InsecurePage(self._profile, self._view))
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

        # Sem barra de header dedicada - Voltar flutua por cima do navegador
        # embutido (reposicionado em _position_overlays/resizeEvent). Sem label
        # de status - mensagens de diagnóstico vão só pro console do Python.
        self._btn_cancel = _ChevronBackButton(self)
        self._btn_cancel.clicked.connect(self._on_cancel)

        self._position_overlays()
        self._btn_cancel.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlays()

    def _position_overlays(self):
        margin = 10
        self._btn_cancel.adjustSize()
        self._btn_cancel.move(self.width() - self._btn_cancel.width() - margin, margin)

    def _set_status(self, text: str):
        print(f"GeoMetadata [GatewaySSOWidget] status: {text}")

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
            log.debug("GeoMetadata [GatewaySSOWidget] falha ao carregar: %s", self._view.url().toString())
            self._set_status("Falha ao carregar a página de login.")
            return
        current_host = self._view.url().host()
        # Só faz sentido validar depois de termos saído pro Azure AD e voltado -
        # o load inicial (navegação pro próprio /oauth2/authorization/...) também
        # acontece no host do gateway, antes do redirect pra Microsoft.
        if not self._left_for_idp or current_host != self._base_host:
            return
        self._browser_stack.setCurrentWidget(self._finishing_widget)
        self._set_status("Validando sessão...")
        self._try_verify()

    def _try_verify(self):
        # A requisição em si roda em _VerifySessionWorker (QThread) - rodar direto aqui
        # (como antes) travava o event loop do Qt inteiro pelos até 10s do timeout,
        # inclusive o QTimer que anima _SpinnerWidget (por isso ele "travava" durante
        # cada tentativa - não era só a QWebEngineView que ficava sem resposta). Passa
        # uma CÓPIA de self._cookies (não a referência) - _on_cookie_added continua
        # rodando na thread principal enquanto o worker roda, e dict não é thread-safe
        # pra leitura concorrente com escrita.
        self._verifying = True
        self._verify_worker = _VerifySessionWorker(self._verify_url, dict(self._cookies), self)
        self._verify_worker.done.connect(self._on_verify_result)
        self._verify_worker.start()

    def _on_verify_result(self, result):
        self._verifying = False
        if self._done:
            return  # cancelado (_on_cancel) enquanto o worker estava em vôo - ignora a resposta atrasada
        if result.get('ok'):
            status = result.get('status')
            # Não logar nomes de cookies (dados de sessão) - apenas status HTTP
            log.debug(
                "GeoMetadata [GatewaySSOWidget] verify %s -> status=%s content-type=%s",
                self._verify_url, status, result.get('content_type')
            )
            data = result.get('data')
            if status == 200 and data is not None:
                # GeoNetwork separa nome/sobrenome em campos distintos (name/surname) -
                # junta os dois pra exibir o nome completo em vez de só o primeiro nome.
                full_name = f"{data.get('name') or ''} {data.get('surname') or ''}".strip()
                username = (
                    full_name
                    or data.get('username')
                    or data.get('email')
                    or data.get('id')
                    or "Usuário CDHU"
                )
                self._done = True
                self.login_succeeded.emit(result.get('session'), str(username))
                return
            self._set_status(f"Sessão ainda não confirmada (HTTP {status}) - tentando de novo...")
        else:
            log.warning("GeoMetadata [GatewaySSOWidget] erro ao verificar sessão: %s", result.get('error'))
            self._set_status(f"Erro ao verificar sessão: {result.get('error')}")
        # Ainda pode ser um hop intermediário do redirect, ou o cookie de sessão
        # ter chegado um instante depois do load - tenta de novo em 1.5s em vez de
        # ficar parado esperando outro loadFinished que pode não vir mais. Limitado
        # pra não martelar o servidor pra sempre se for uma falha genuína.
        self._retry_count += 1
        if self._retry_count > 15:
            self._set_status(
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
        # _verify_worker tem parent=self (QThread filha deste widget) - se ainda estiver
        # rodando (clique em "Voltar" durante "Validando sessão..."), o login_failed abaixo
        # dispara _leave_sso_widget() (main_bridge.py) -> deleteLater() neste widget, o que
        # destruiria a QThread ainda em execução: Qt chama std::terminate(), fecha o QGIS
        # inteiro sem crash dump (mesma causa raiz de GeoMetadataDialog.closeEvent).
        if self._verify_worker and self._verify_worker.isRunning():
            self._verify_worker.quit()
            self._verify_worker.wait(2000)
        self.login_failed.emit("Login cancelado.")
