"""Lo que comparten los tres motores: el error tipado y el ensamblado de texto por lámina."""


class MotorError(RuntimeError):
    """El motor no pudo producir. Quien llama decide si eso dice `pendiente` (inténtalo
    después, o que lo haga la Mac) o `fallo` (algo está mal de verdad) — el motor nunca
    decide por sí mismo cuál de los dos es: sólo reporta qué pasó."""

    def __init__(self, mensaje, intermitente=False):
        super().__init__(mensaje)
        # intermitente=True: «no me tocó esta vez» (cuota, servicio ocupado) — sala_ejecutor
        # lo deja 'pendiente' para la Mac o para el siguiente intento, NUNCA 'fallo'.
        self.intermitente = intermitente
