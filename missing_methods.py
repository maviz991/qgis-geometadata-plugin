def reject(self):
    """
        Sobrescreve o comportamento padr├úo da tecla ESC.
        
        Em vez de fechar a janela diretamente, este m├®todo chama self.close(),
        que por sua vez acionar├í o nosso closeEvent(). Isso garante que a
        verifica├º├úo de altera├º├Áes n├úo salvas seja executada tanto para a tecla ESC
        quanto para o bot├úo 'X' da janela.
        """
    self.close()