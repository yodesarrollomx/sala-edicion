"""Un archivo por motor, misma firma: producir(trabajo, reglas, cat, salida_dir) -> ruta.

Cada motor sube su propio producto a Drive — no lo hace sala_ejecutor.py por ellos — porque
sólo el motor sabe si lo que generó es la pieza final o un intermedio que no se publica.
"""
