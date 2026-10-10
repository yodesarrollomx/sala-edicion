import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nube'))
from activar_regla_contenido import activar
from contenido_reglas import REGLA


def respuesta(valor):
    return {'ok': True, 'reglas': {REGLA: valor}}


class ActivacionTests(TestCase):
    def test_admite_vetos_adicionales_sin_duplicar(self):
        cliente = Mock()
        cliente.get.side_effect = [respuesta('Hermosillo,Sonora,México')] * 2 + [respuesta('Hermosillo,Sonora,México,Otra Ciudad')]
        cliente.post.return_value = {'ok': True, 'editadas': 1}
        activar(cliente, 'MEXICO,Otra Ciudad,otra ciudad')
        cliente.post.assert_called_once_with('regla', set={REGLA: 'Hermosillo,Sonora,México,Otra Ciudad'})

    def test_conserva_vetos_previos_y_verifica_lectura(self):
        cliente = Mock()
        cliente.get.side_effect = [respuesta('Otra Ciudad,MEXICO')] * 2 + [respuesta('Otra Ciudad,MEXICO,Hermosillo,Sonora')]
        cliente.post.return_value = {'ok': True, 'editadas': 1}
        self.assertTrue(activar(cliente)['verificada'])
        cliente.post.assert_called_once_with('regla', set={REGLA: 'Otra Ciudad,MEXICO,Hermosillo,Sonora'})

    def test_ya_activa_no_escribe(self):
        cliente = Mock()
        cliente.get.return_value = respuesta('hermosillo,SONORA,MEXICO,Otra Ciudad')
        self.assertFalse(activar(cliente)['modificada'])
        cliente.post.assert_not_called()

    def test_no_sobrescribe_cambio_concurrente(self):
        cliente = Mock()
        cliente.get.side_effect = [respuesta(''), respuesta('Otra Ciudad')]
        with self.assertRaises(RuntimeError):
            activar(cliente)
        cliente.post.assert_not_called()

    def test_no_confirma_lectura_posterior_distinta(self):
        cliente = Mock()
        cliente.get.side_effect = [respuesta(''), respuesta(''), respuesta('')]
        cliente.post.return_value = {'ok': True, 'editadas': 1}
        with self.assertRaises(RuntimeError):
            activar(cliente)

    def test_no_escribe_si_lectura_falla(self):
        for r in ({'ok': False}, respuesta(123)):
            cliente = Mock()
            cliente.get.return_value = r
            with self.assertRaises(RuntimeError):
                activar(cliente)
            cliente.post.assert_not_called()


if __name__ == '__main__':
    main()
