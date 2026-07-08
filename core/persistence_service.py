import os
import re
import pathlib
import traceback
from qgis.core import Qgis, QgsApplication
from qgis.PyQt import QtWidgets, QtCore

try:
    import psycopg2
except ImportError:
    psycopg2 = None

from . import xml_generator
from .plugin_config import config_loader

class PersistenceService:
    """
    Serviço que consolida toda a manipulação de leitura e escrita de
    metadados, seja de banco de dados PostgreSQL ou de arquivos locais XML.
    """
    def __init__(self, iface):
        self.iface = iface

    def save(self, layer, metadata_dict, cdhu_data, is_automatic_resave=False, parent_widget=None):
        """
        Detecta o tipo de armazenamento da camada e delega a função de salvar.
        Retorna True se sucesso, False caso falhe ou o usuário cancele.
        """
        if not layer:
            if not is_automatic_resave and parent_widget:
                self._show_message("Nenhuma Camada Ativa", "Por favor, selecione uma camada no painel de camadas.", parent_widget, msg_type='warning')
            return False

        if self._is_postgres_layer(layer):
            return self._save_to_db(layer, metadata_dict, cdhu_data, is_automatic_resave, parent_widget)
        else:
            return self._save_to_sidecar_file(layer, metadata_dict, cdhu_data, is_automatic_resave, parent_widget)

    def load(self, layer):
        """
        Tenta resgatar os metadados brutos (string XML) caso existam no DB ou arquivo sidecar da camada.
        """
        if not layer:
            return None
        
        if self._is_postgres_layer(layer):
            return self._load_from_db(layer)
        else:
            # Não carrega o arquivo aqui, apenas retorna o path.
            # O load base de _load_metadata_from_db retorna string. Para manter a mesma assinatura,
            # retornarei a string xml e deixo o form popular
            path = self._get_sidecar_metadata_path(layer)
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            return None

    # --- Utilitários Privados ---
    def _is_postgres_layer(self, layer):
        if not layer: return False
        return layer.providerType() == 'postgres'

    def _get_postgres_connection_details(self, layer):
        uri = layer.source()
        details = {}
        pattern = re.compile(r"(\w+)='([^']*)'|(\w+)=([^\s]+)")
        matches = pattern.findall(uri)
        
        for key_quoted, val_quoted, key_unquoted, val_unquoted in matches:
            key = key_quoted or key_unquoted
            value = val_quoted or val_unquoted
            if key:
                details[key] = value

        details['f_table_catalog'] = details.get('dbname')
        full_table_identifier = details.get('table', '')
        clean_identifier = full_table_identifier.replace('"', '')

        if '.' in clean_identifier:
            parts = clean_identifier.split('.', 1)
            details['f_table_schema'] = parts[0]
            details['f_table_name'] = parts[1]
        else:
            details['f_table_schema'] = details.get('sschema', details.get('schema', 'public'))
            details['f_table_name'] = clean_identifier
            
        return details

    def _get_sidecar_metadata_path(self, layer):
        if not layer or not layer.source(): return None
        source_path = layer.source()
        base_path = source_path.split('|')[0] if '|' in source_path else source_path
        if 'vsizip' in source_path.lower():
            path_sem_vsizip = re.sub(r'^/vsizip/', '', source_path, flags=re.IGNORECASE)
            zip_index = path_sem_vsizip.lower().find('.zip')
            if zip_index != -1: base_path = path_sem_vsizip[:zip_index + 4]
        if os.path.isfile(base_path): return base_path + ".xml"
        return None

    def _check_auth_system(self, parent_widget=None):
        auth_manager = QgsApplication.authManager()
        if auth_manager.isDisabled():
            if parent_widget:
                title = "Sistema de Autenticação do QGIS Desabilitado"
                message = (
                    "Seu QGIS está com a autenticação desabilitada. Feche-o e inicie novamente."
                )
                self._show_message(title, message, parent_widget, msg_type='error')
            return False
        return True

    def _show_message(self, title, text, parent_widget, msg_type='info'):
        """Notifica o usuário no padrão visual HTML/CSS do projeto (via `parent_widget.show_toast`).
        Cai para QMessageBox nativo se o parent não expuser esse método."""
        if not parent_widget: return
        notify = getattr(parent_widget, 'show_toast', None)
        if callable(notify):
            notify(title, text, msg_type)
            return
        icon_map = {
            'error': QtWidgets.QMessageBox.Critical,
            'warning': QtWidgets.QMessageBox.Warning,
        }
        msg_box = QtWidgets.QMessageBox(parent_widget)
        msg_box.setIcon(icon_map.get(msg_type, QtWidgets.QMessageBox.Information))
        msg_box.setTextFormat(QtCore.Qt.RichText)
        msg_box.setText(text)
        msg_box.setWindowTitle(title)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg_box.exec_()
        
    def _save_to_db(self, layer, metadata_dict, cdhu_data, is_automatic_resave=False, parent_widget=None):
        if not self._check_auth_system(parent_widget): return False
        if not psycopg2:
            self._show_message("Erro de Dependência", "A biblioteca psycopg2 não foi encontrada.", parent_widget, msg_type='error')
            return False

        conn_details = self._get_postgres_connection_details(layer)
        if not conn_details.get('f_table_name'):
            self._show_message("Erro", "Não foi possível identificar a tabela da camada.", parent_widget, msg_type='warning')
            return False
            
        # A confirmação agora é feita pela interface HTML/JS antes de chamar este método.
        pass

        try:
            db_user = conn_details.get('user')
            db_password = conn_details.get('password')
            
            if not db_password and conn_details.get('authcfg'):
                auth_manager = QgsApplication.authManager()
                auth_cfg_id = conn_details['authcfg']
                config = auth_manager.availableAuthMethodConfigs().get(auth_cfg_id)
                if config and auth_manager.loadAuthenticationConfig(auth_cfg_id, config, True):
                    db_user = config.configMap().get('username')
                    db_password = config.configMap().get('password')
                else:
                    self._show_message("Erro de Auth", f"Não foi possível carregar config '{auth_cfg_id}'.", parent_widget, msg_type='error')
                    return False
                                
            xml_content = xml_generator.generate_xml(metadata_dict, cdhu_data)
            conn = psycopg2.connect(
                dbname=conn_details.get('dbname'),
                user=db_user,
                password=db_password,
                host=conn_details.get('host'),
                port=conn_details.get('port', 5432)
            )
            cursor = conn.cursor()
            sql = """
                INSERT INTO public.qgis_geometadata_plugin (f_table_catalog, f_table_schema, f_table_name, metadata_xml)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT qgis_geometadata_plugin_unique_layer
                DO UPDATE SET 
                    metadata_xml = EXCLUDED.metadata_xml,
                    owner = DEFAULT,
                    update_time = DEFAULT;
            """
            cursor.execute(sql, (conn_details.get('f_table_catalog'), conn_details['f_table_schema'], conn_details['f_table_name'], xml_content))
            conn.commit()
            cursor.close()
            conn.close()
            
            if not is_automatic_resave:
                self.iface.messageBar().pushMessage("Sucesso", f"Metadado salvo para a camada '{layer.name()}'.", level=Qgis.Success, duration=5)
                success_text = (f"<p style='font-size:14px; font-weight: bold;'>Metadado Salvo no Banco!</p>")
                self._show_message("Sucesso!", success_text, parent_widget, msg_type='success')
            return True

        except psycopg2.errors.UndefinedTable:
            traceback.print_exc()
            message = (
                "A tabela de metadados ainda não existe neste banco de dados.<br><br>"
                f"Por favor, abra um ticket no <a href='{config_loader.get_cda_url()}'>CDA</a> "
                "solicitando a criação da tabela <b>public.qgis_geometadata_plugin</b>."
            )
            self._show_message("Erro DB", message, parent_widget, msg_type='error')
            return False
        except Exception as e:
            traceback.print_exc()
            self._show_message("Erro DB", f"Não foi possível salvar:<br><br>{e}", parent_widget, msg_type='error')
            return False

    def _save_to_sidecar_file(self, layer, metadata_dict, cdhu_data, is_automatic_resave=False, parent_widget=None):
        metadata_path = self._get_sidecar_metadata_path(layer)
        if not metadata_path:
            if not is_automatic_resave:
                layer_name = layer.name() if layer else "A camada"
                self._show_message("Impossível salvar local", f"<p>A camada {layer_name} não está salva num arquivo.</p>", parent_widget, msg_type='warning')
            return False

        if not is_automatic_resave and parent_widget:
            question = f"<p>Salvar arquivo sidecar em:<br>{metadata_path}</p>"
            reply = QtWidgets.QMessageBox.question(parent_widget, 'Confirmar', question, QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
            if reply != QtWidgets.QMessageBox.Ok:
                return False
        
        try:
            xml_content = xml_generator.generate_xml(metadata_dict, cdhu_data)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            if not is_automatic_resave:
                self.iface.messageBar().pushMessage("Sucesso", "Arquivo salvo.", level=Qgis.Success)
                self._show_message("Sucesso!", f"<p>Salvo em:<br>{metadata_path}</p>", parent_widget, msg_type='success')
            return True
        except Exception as e:
            traceback.print_exc()
            self._show_message("Erro IO", f"Falha ao escrever XML:<br>{e}", parent_widget, msg_type='error')
            return False

    def _load_from_db(self, layer):
        if not self._check_auth_system(): return None
        if not psycopg2: return None

        conn_details = self._get_postgres_connection_details(layer)
        if not conn_details.get('f_table_name'): return None

        xml_content = None
        try:
            db_user = conn_details.get('user')
            db_password = conn_details.get('password')
            
            if not db_password and conn_details.get('authcfg'):
                auth_manager = QgsApplication.authManager()
                auth_cfg_id = conn_details['authcfg']
                config = auth_manager.availableAuthMethodConfigs().get(auth_cfg_id)
                if config and auth_manager.loadAuthenticationConfig(auth_cfg_id, config, True):
                    db_user = config.configMap().get('username')
                    db_password = config.configMap().get('password')
                
            conn = psycopg2.connect(
                dbname=conn_details.get('dbname'),
                user=db_user,
                password=db_password,
                host=conn_details.get('host'),
                port=conn_details.get('port', 5432)
            )
            cursor = conn.cursor()
            sql = "SELECT metadata_xml FROM public.qgis_geometadata_plugin WHERE f_table_catalog = %s AND f_table_schema = %s AND f_table_name = %s;"
            cursor.execute(sql, (conn_details.get('f_table_catalog'), conn_details['f_table_schema'], conn_details['f_table_name']))
            result = cursor.fetchone()
            if result:
                xml_content = result[0]
            cursor.close()
            conn.close()
        except Exception as e:
            traceback.print_exc()
        return xml_content
