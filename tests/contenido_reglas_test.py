"""Regresiones #49: sólo datos sintéticos y motores/red reemplazados por dobles."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'nube'))
import contenido_reglas as contenido
import sala_arranque as arranque
import sala_cliente as cliente
import sala_guion as guion
import sala_mesa as mesa
from motores import cerebro, imagen, voz_gemini
from motores._comun import MotorError


class ContenidoReglasTests(unittest.TestCase):
    def test_acentos_capitalizacion_y_limites(self):
        for palabra in ('HERMOSILLO', 'sonora', 'MEXICO', 'MéXiCo', 'Me\u0301xico'):
            with self.subTest(palabra=palabra):
                self.assertTrue(contenido.prohibidas('En «%s», hoy.' % palabra))
                self.assertTrue(mesa.guardia(palabra, mesa.vetadas('sintetica')))
        self.assertFalse(contenido.prohibidas('Una cama sonoramente cálida.'))
        self.assertFalse(mesa.guardia('Una cama sonoramente cálida.', mesa.vetadas('sintetica')))

    def test_reglas_aditivas_sin_quitar_vetos(self):
        self.assertTrue(contenido.prohibidas('México', {contenido.REGLA: ''}))
        self.assertTrue(contenido.prohibidas('Sonora', {contenido.REGLA: 'Otra Ciudad'}))
        self.assertTrue(contenido.prohibidas('En OTRA CIUDAD.', {contenido.REGLA: 'Otra Ciudad'}))

    def test_campos_publicables_y_historicos(self):
        for campo in contenido.CAMPOS:
            with self.subTest(campo=campo):
                with self.assertRaises(contenido.ContenidoVetado):
                    contenido.exigir({'laminas': [{'candidatas': [{campo: 'MEXICO'}]}]})
        dato = {'id': 'mexico-001', 'src': 'laminas/Sonora/L1.jpg',
                'url': 'https://example.test/Hermosillo', 'nota': 'Quitar México',
                'origen': 'Hermosillo', 'versiones': [{'dice': 'Sonora'}],
                'historial': [{'titulo': 'México'}], 'dice': 'Un terreno con posibilidades.'}
        antes = json.dumps(dato, sort_keys=True)
        contenido.exigir(dato)
        self.assertEqual(antes, json.dumps(dato, sort_keys=True))

    def test_prompts_tienen_regla_y_no_contexto_que_induce_veto(self):
        from motores.estrategia import ESTRATEGIA, con_estrategia
        for texto in (ESTRATEGIA, arranque.INSTR_GUION, arranque.INSTR_IDEAS,
                      arranque.INSTR_PREMISA, cerebro.INSTRUCCION, cerebro.INSTRUCCION_LAMINA):
            self.assertFalse(contenido.prohibidas(texto))
        self.assertIn('nunca usar', con_estrategia(arranque.INSTR_GUION))
        self.assertIn('Otra Ciudad', con_estrategia('salida', {contenido.REGLA: 'Otra Ciudad'}))

    def test_arranque_reintenta_todo_guion_invalido(self):
        malo = {'promesa': 'Posibilidades', 'laminas': [{'dice': 'Un terreno'}, {'dice': 'En México'}]}
        bueno = {'promesa': 'Posibilidades', 'laminas': [{'dice': 'Un terreno'}, {'dice': 'Una decisión'}]}
        with patch.object(cerebro, '_gemini', side_effect=[json.dumps(malo), json.dumps(bueno)]) as motor:
            self.assertEqual(arranque.pensar('entrada', 'guion', {}, []), bueno)
            self.assertEqual(motor.call_count, 2)

    def test_semillero_rechaza_titulo_bajada_y_premisa(self):
        for dato in ({'ideas': [{'titulo': 'Sonora', 'bajada': 'Un terreno'}]},
                     {'ideas': [{'titulo': 'Un terreno', 'bajada': 'México'}]},
                     {'titulo': 'Una premisa', 'bajada': 'Hermosillo'}):
            with self.subTest(dato=dato):
                with patch.object(cerebro, '_gemini', return_value=json.dumps(dato)), \
                     patch.object(cerebro, '_openai', return_value=json.dumps(dato)):
                    with self.assertRaises(MotorError):
                        arranque.pensar('entrada', 'ideas', {}, [])

    def test_candidata_invalida_no_se_fija_y_usa_respaldo(self):
        bueno = {'texto': 'Un terreno con posibilidades', 'receta': 'A warm courtyard', 'porque': 'Más claro'}
        for campo in ('texto', 'receta', 'porque'):
            malo = dict(bueno, **{campo: 'MEXICO'})
            with self.subTest(campo=campo), \
                 patch.object(cerebro, '_gemini', return_value=json.dumps(malo)), \
                 patch.object(cerebro, '_openai', return_value=json.dumps(bueno)):
                result, motor, avisos = cerebro.lamina('Pieza', '', '', '', '', [], {}, [])
                self.assertEqual(result, bueno)
                self.assertEqual(motor, 'openai')
                self.assertTrue(avisos)

    def test_receta_base_no_evita_regla_y_rechazo_previo_a_imagen(self):
        with patch.object(cerebro, '_gemini', side_effect=MotorError('sin motor')), \
             patch.object(cerebro, '_openai', side_effect=MotorError('sin motor')):
            with self.assertRaises(MotorError):
                cerebro.receta('Scene in Mexico', '', '', '', {}, [])
        with patch.dict(imagen.MOTORES, {'sintetico': lambda *args: self.fail('se pidió imagen')}):
            with self.assertRaises(MotorError):
                imagen.generar('Scene in México', {'imagen_motores': 'sintetico'})

    def test_compositor_rechaza_antes_de_leer_o_escribir_imagen(self):
        import sala_compositor as compositor
        with patch.object(compositor.Image, 'open', side_effect=AssertionError('leyó imagen')):
            with self.assertRaises(contenido.ContenidoVetado):
                compositor.componer('/no-existe', 'MEXICO', '/no-escribir.png')

    def test_cliente_rechaza_lote_completo_antes_de_la_red(self):
        with patch.object(cliente, '_pedir', side_effect=AssertionError('llamada de red')):
            for accion in ('proponer', 'ideas', 'arbol'):
                with self.subTest(accion=accion), self.assertRaises(cliente.SalaError):
                    cliente.post(accion, filas=[{'titulo': 'Un terreno'}, {'bajada': 'Sonora'}])

    def test_montar_detecta_texto_oculto_en_tira_antes_del_post(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta)
            (ruta / 'sintetica.json').write_text(json.dumps({'titulo': 'Un terreno', 'laminas': [{'dice': 'MEXICO'}]}))
            plan = ruta / 'plan.json'
            plan.write_text(json.dumps({'fecha': '2026-10-01', 'cartas': [{'tira_id': 'sintetica', 'familia': 'sintetica', 'carta': {'id': 'sintetica', 'titulo': 'Un terreno'}}]}))
            for modulo in (mesa, arranque):
                with self.subTest(modulo=modulo.__name__), patch.object(modulo, 'PLAN', plan), \
                     patch.object(modulo, 'TIRAS', ruta), \
                     patch.object(cliente, 'post', side_effect=AssertionError('post de negocio')):
                    with self.assertRaises(cliente.SalaError):
                        modulo.montar()

    def test_voz_rechaza_toda_escena_antes_del_motor(self):
        g = {'escenas': [{'n': 1, 'partes': [{'rol': 'narrador', 'dice': 'Un terreno'}, {'rol': 'vecino', 'dice': 'México'}]}]}
        with self.assertRaises(MotorError):
            guion.partes_de(g, '1')
        with patch.object(guion, 'cargar', return_value=g), \
             patch.object(voz_gemini, '_pedir', side_effect=AssertionError('llamada TTS')):
            with self.assertRaises(MotorError):
                voz_gemini.producir({'pieza': 'sintetica', 'item': '1'}, {}, {}, Path('/no-escribir'))

    def test_escena_rechaza_antes_de_elegir_motor_o_subir(self):
        from types import ModuleType
        # Esta prueba nunca sintetiza voz: NumPy es un doble del motor no usado.
        with patch.dict(sys.modules, {'numpy': ModuleType('numpy')}):
            import sala_ejecutor as ejecutor
        trabajo = {'pieza': 'sintetica', 'etapa': 'escena', 'item': '1',
                   'evidencia': {'src': 'sintetica.jpg', 'dice': 'MEXICO'}}
        with patch.object(ejecutor.motores, 'elegir_motor', side_effect=AssertionError('eligió motor')), \
             patch.object(ejecutor, 'subir_producto', side_effect=AssertionError('subió producto')):
            estado, evidencia = ejecutor.ejecutar_uno(trabajo, {}, [], {}, None, [])
            self.assertEqual(estado, 'fallo')
            self.assertIn('ubicación vetada', evidencia['error'])

    def test_corte_existente_no_reusa_media_invalida(self):
        import sala_montador as montador
        trabajo = {'pieza': 'sintetica', 'evidencia': {'laminas': [{'item': '1', 'huella': 'huella'}]}}
        cola = [{'pieza': 'sintetica', 'etapa': etapa, 'item': '1', 'estado': 'hecho',
                 'evidencia': {'md5_insumo': 'huella', 'src': 'sintetica.jpg', 'dice': 'Sonora'}}
                for etapa in ('escena', 'voz')]
        with patch.object(montador, '_bajar_de_drive', side_effect=AssertionError('bajó media')), \
             patch.object(montador, '_job_de', side_effect=cola):
            with self.assertRaises(montador.MontadorError):
                montador.ensamblar(trabajo, {}, {}, Path('/no-escribir'), cola)


if __name__ == '__main__':
    unittest.main()
