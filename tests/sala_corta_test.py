"""Sala corta (9-nov-2026): pausas por regla y latidos declarados, sin red.

Lo que se prueba:
  · el generador de ideas calla con REGLAS semillero_activo = 0, lo lance quien lo lance, y
    sigue sembrando sin la regla (el interruptor es reversible y por omisión no cambia nada);
  · la tabla de rutinas que lee la Sala dice los mismos horarios que los workflows: un
    proceso «sólo a mano» no conserva horario escondido y uno con horario lo tiene escrito.
"""
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
import revision_diaria as revision
import sala_arranque as arranque

WORKFLOWS = ROOT / '.github' / 'workflows'
PUERTAS = ('sala-cada-hora.yml', 'sala-diario.yml', 'sala-plan.yml')


def horarios(nombre):
    texto = (WORKFLOWS / nombre).read_text(encoding='utf-8')
    return re.findall(r'''^\s*-\s*cron:\s*['"]([^'"]+)['"]''', texto, flags=re.M)


def trabajo(nombre, proceso):
    """El bloque del job `proceso` dentro de una puerta."""
    texto = (WORKFLOWS / nombre).read_text(encoding='utf-8')
    m = re.search(r'^  %s:[^\n]*\n(.*?)(?=^  \S|\Z)' % re.escape(proceso), texto, flags=re.M | re.S)
    return m.group(1) if m else ''


class SemilleroEnPausaTests(unittest.TestCase):
    def test_con_la_regla_en_cero_no_lee_ni_escribe(self):
        prohibido = AssertionError('el semillero en pausa no debe leer hojas, pensar ni escribir')
        with patch.object(arranque, 'leer_hoja', side_effect=prohibido), \
                patch.object(arranque, 'pensar', side_effect=prohibido), \
                patch.object(arranque.sala, 'post', side_effect=prohibido), \
                patch.object(arranque.sala, 'avisar') as avisar:
            for valor in ('0', ' 0 ', 'no', 'pausa', 'False'):
                with self.subTest(valor=valor):
                    self.assertEqual(arranque.semillero(False, {'semillero_activo': valor}, []), 0)
        self.assertIn('pausa', avisar.call_args[0][0])

    def test_sin_la_regla_sigue_sembrando(self):
        # Cinco premisas vivas: así el semillero no busca además una premisa candidata.
        arbol = [{'nivel': 'tema', 'id': 'tema-%d' % n, 'titulo': 'Premisa sintética %d' % n, 'estado': 'viva'}
                 for n in range(1, 6)]
        pensado = {'ideas': [{'titulo': 'Idea sintética uno', 'bajada': 'x', 'formato': 'Lámina'}]}
        for reglas in ({}, {'semillero_activo': '1'}, {'semillero_activo': ''}):
            with self.subTest(reglas=reglas), \
                    patch.object(arranque, 'leer_hoja', side_effect=[(arbol, 'sheet'), ([], 'sheet')]), \
                    patch.object(arranque, 'pensar', return_value=pensado), \
                    patch.object(arranque.sala, 'hoy_hermosillo', return_value='2026-11-09'), \
                    patch.object(arranque.sala, 'avisar'), \
                    patch.object(arranque.sala, 'post') as post:
                self.assertEqual(arranque.semillero(False, reglas, []), 0)
                self.assertEqual([c.args[0] for c in post.call_args_list], ['ideas'])
                self.assertEqual(post.call_args.kwargs['filas'][0]['estado'], 'propuesta')

    def test_el_arranque_de_ideas_elegidas_no_depende_de_la_pausa(self):
        # La pausa calla al generador; las ideas ya elegidas siguen arrancando.
        self.assertTrue(arranque.semillero_en_pausa({'semillero_activo': '0'}))
        self.assertFalse(arranque.semillero_en_pausa({}))
        self.assertFalse(arranque.semillero_en_pausa(None))
        codigo = arranque.arranque.__code__
        self.assertNotIn('semillero_en_pausa', codigo.co_names)
        self.assertNotIn('semillero_activo', [c for c in codigo.co_consts if isinstance(c, str)])


class LatidosDeclaradosTests(unittest.TestCase):
    def test_cada_horario_de_la_tabla_existe_en_una_puerta(self):
        escritos = {c for puerta in PUERTAS for c in horarios(puerta)}
        for ident, _nombre, _frecuencia, veces, cron in revision.ROUTINES:
            with self.subTest(rutina=ident):
                if not cron:
                    self.assertEqual(veces, 0, 'una rutina sin horario declara 0 corridas diarias')
                    continue
                for expresion in [c.strip() for c in cron.split(';')]:
                    self.assertIn(expresion, escritos)

    def test_lo_que_quedo_a_mano_no_conserva_horario(self):
        for ident, _nombre, _frecuencia, veces, cron in revision.ROUTINES:
            if cron:
                continue
            with self.subTest(rutina=ident):
                bloque = trabajo('sala-cada-hora.yml', ident)
                self.assertTrue(bloque, 'el proceso conserva su botón en la puerta')
                condicion = re.search(r'^\s*if:\s*(.+)$', bloque, flags=re.M).group(1)
                self.assertNotIn('github.event.schedule', condicion)
                self.assertIn("inputs.proceso == '%s'" % ident, condicion)

    def test_cada_horario_de_una_puerta_tiene_quien_lo_atienda(self):
        # Un cron sin job que lo espere sólo despierta la puerta para nada.
        for puerta in ('sala-cada-hora.yml', 'sala-diario.yml'):
            texto = (WORKFLOWS / puerta).read_text(encoding='utf-8')
            for cron in horarios(puerta):
                with self.subTest(puerta=puerta, cron=cron):
                    self.assertIn(cron, texto.split('jobs:', 1)[1])

    def test_las_veces_al_dia_cuadran_con_el_horario(self):
        def veces_al_dia(expresion):
            minuto, hora = expresion.split()[:2]
            n_min = len(minuto.split(','))
            if hora == '*':
                n_hora = 24
            elif hora.startswith('*/'):
                n_hora = 24 // int(hora[2:])
            else:
                n_hora = len(hora.split(','))
            return n_min * n_hora
        for ident, _nombre, _frecuencia, veces, cron in revision.ROUTINES:
            if cron:
                with self.subTest(rutina=ident):
                    self.assertEqual(veces, sum(veces_al_dia(c.strip()) for c in cron.split(';')))


if __name__ == '__main__':
    unittest.main()
