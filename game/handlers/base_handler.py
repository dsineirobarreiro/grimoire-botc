def generic_handler_template(role_name):
    from engine.night_registry import register_handler

    @register_handler(role_name)
    def handler(engine, pid, selection):
        """
        Lógica del rol.
        engine: NightEngine
        pid: id del jugador
        selection: datos de lo que seleccionó el jugador
        """
        pass

    return handler
