    def closeEvent(self, event):
        """
        Executado quando o usu├írio tenta fechar a janela.
        Verifica se h├í altera├º├Áes n├úo salvas.
        """
        if self.form_is_dirty:
            reply = QMessageBox.question(self, 
                                        'Altera├º├Áes n├úo Salvas',
                                        "Voc├¬ tem altera├º├Áes que n├úo foram salvas.\nDeseja realmente sair?",
                                        QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No)

            if reply == QMessageBox.Yes:
                event.accept()  # Permite que a janela feche
            else:
                event.ignore()  # Cancela o evento de fechamento
        else:
            event.accept() # Se n├úo h├í altera├º├Áes, apenas fecha normalmente

    def populate_comboboxes(self):
        def populate(combo, options):
            combo.clear()
            for text, data in options:
                combo.addItem(text, data)
        
        populate(self.ui.comboBox_status_codeListValue, [('Arquivo Antigo', 'historicalArchive'), ('Conclu├¡do', 'completed'), ('Cont├¡nuo', 'onGoing'), ('Em Desenvolvimento', 'underDevelopment'), ('Necess├írio', 'required'), ('Obsoleto', 'obsolete'), ('Planejado', 'planned')])
        populate(self.ui.comboBox_contact_presets, [('CDHU', 'cdhu'), ('DPDU', 'dpdu'), ('SPHU', 'sphu'), ('SSARU', 'ssaru'), ('TERRAS', 'terras')])
        populate(self.ui.comboBox_MD_SpatialRepresentationTypeCode, [('Vetor', 'vector'), ('Grid | Raster', 'grid'), ('Tabela de texto', 'textTable'), ('Rede triangular irregular (TIN)', 'tin'), ('Modelo estereof├│nico', 'stereoscopicModel'), ('V├¡deo', 'video')])
        populate(self.ui.comboBox_LanguageCode, [('­ƒçº­ƒçÀ Portugu├¬s', 'por'), ('­ƒç║­ƒç© Ingl├¬s', 'eng'), ('­ƒç¬­ƒç© Espanhol', 'spa'), ('­ƒç½­ƒçÀ Fran├º├¬s', 'fra'), ('­ƒç®­ƒç¬ Alem├úo', 'ger')])
        populate(self.ui.comboBox_characterSet, [('UTF-8', 'utf8')])
        populate(self.ui.comboBox_topicCategory, [  ('Limites Administrativos', 'boundaries'),
                                                    ('Planejamento e Cadastro', 'planningCadastre'),
                                                    ('Sociedade e Cultura', 'society'),
                                                    ('Infraestrutura ou Edifica├º├úo', 'structure'),
                                                    ('Transportes', 'transportation'),
                                                    ('Localiza├º├úo', 'location'),
                                                    ('Mapas ou imagens de Sat├®lite', 'imageryBaseMapsEarthCover'),
                                                    ('Altimetria, Batimetria ou Topografia', 'elevation'),
                                                    ('Sa├║de', 'health'), ('├üguas Interiores', 'inlandWaters'),
                                                    ('Econ├┤mia', 'economy'),
                                                    ('Biotipos', 'biota'),
                                                    ('Climatologia ou Meteorologia', 'climatologyMeteorologyAtmosphere'),
                                                    ('Informa├º├úo GeoCient├¡fica', 'geoscientificInformation'), 
                                                    ('Informa├º├úo Militar', 'intelligenceMilitary'),
                                                    ('Ambiente', 'environment'),
                                                    ('Oceanos', 'oceans'), 
                                                    ('Infraestruturas de Comunica├º├úo', 'utilitiesCommunication'), 
                                                    ('Agricultura, pesca ou pecu├íria', 'farming')])
        populate(self.ui.comboBox_hierarchyLevel, [('Conjunto de dados', 'dataset')])
        populate(self.ui.comboBox_contact_role, [('Dono', 'owner'), ('Autor', 'author'), ('Organizador', 'processor'), ('Distribuidor', 'distributor'), ('Deposit├írio', 'custodian'), ('Fornecedor de recurso', 'resourceProvider'), ('Investigador principal', 'principalInvestigator'), ('Originador', 'originator'), ('Ponto de contato', 'pointOfContact'), ('Publicador', 'publisher'), ('Utilizador', 'user')])
        populate(self.ui.comboBox_contact_administrativeArea, [('S├úo Paulo', 'SP'), ('Acre', 'AC'), ('Alagoas', 'AL'), ('Amap├í', 'AP'), ('Amazonas', 'AM'), ('Bahia', 'BA'), ('Cear├í', 'CE'), ('Distrito Federal', 'DF'), ('Esp├¡rito Santo', 'ES'), ('Goi├ís', 'GO'), ('Maranh├úo', 'MA'), ('Mato Grosso', 'MT'), ('Mato Grosso do Sul', 'MS'), ('Minas Gerais', 'MG'), ('Par├í', 'PA'), ('Para├¡ba', 'PB'), ('Paran├í', 'PR'), ('Pernambuco', 'PE'), ('Piau├¡', 'PI'), ('Rio de Janeiro', 'RJ'), ('Rio Grande do Norte', 'RN'), ('Rio Grande do Sul', 'RS'), ('Rond├┤nia', 'RO'), ('Roraima', 'RR'), ('Santa Catarina', 'SC'), ('Sergipe', 'SE'), ('Tocantins', 'TO')])

    def reject(self):
        """
        Sobrescreve o comportamento padr├úo da tecla ESC.
        
        Em vez de fechar a janela diretamente, este m├®todo chama self.close(),
        que por sua vez acionar├í o nosso closeEvent(). Isso garante que a
        verifica├º├úo de altera├º├Áes n├úo salvas seja executada tanto para a tecla ESC
        quanto para o bot├úo 'X' da janela.
        """
        self.close()

