import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nube'))
import sala_productor as productor
import sala_vigencia as vigencia
import sala_cliente as sala


class VigenciaTests(unittest.TestCase):
    def test_historical_string_keeps_source_catalog_identity_and_engine_evidence(self):
        with patch.object(productor.catalogo, 'huella_de', return_value={'huella':'1234567890', 'serial':'SYN-1'}) as cat:
            self.assertEqual(productor.huella_insumo('laminas/sintetica.png', {}), ('12345678','catalogo:SYN-1'))
            cat.assert_called_once_with('laminas/sintetica.png', {})
        self.assertEqual(productor.datos_lamina('laminas/sintetica.png'), {'src':'laminas/sintetica.png'})

    def test_absent_catalog_and_file_still_distinguishes_sources_and_rejects_empty_identity(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(productor, 'RAIZ', Path(folder)), patch.object(productor.catalogo, 'huella_de', return_value=None):
            self.assertNotEqual(productor.huella_insumo('a.png')[0], productor.huella_insumo('b.png')[0])
            for empty in (None, {}, '', {'src':''}):
                with self.assertRaises(sala.SalaError): productor.huella_insumo(empty)

    def test_published_exact_name_closes_old_rounds_but_not_another_piece(self):
        published={'obra sintética'}
        self.assertTrue(vigencia.publicada({'titulo':'Obra sintética · ronda 3'}, registro=published))
        self.assertFalse(vigencia.publicada({'titulo':'Obra sintética segunda parte · ronda 1'}, registro=published))
        self.assertFalse(vigencia.publicada({'titulo':'Otra obra'}, registro=published))

    def test_published_queue_is_excluded_before_rescue_without_touching_original_or_results(self):
        rows=[{'id':'a','estado':'pendiente','evidencia':{'de':'ronda-antigua','nota':'Conservar'}},
              {'id':'b','estado':'corriendo','evidencia':'{"de":"ronda-antigua"}'},
              {'id':'c','estado':'hecho','evidencia':{'de':'ronda-antigua','drive_id':'original'}},
              {'id':'d','estado':'pendiente','evidencia':{'de':'nueva-pieza'}}]
        before=copy.deepcopy(rows)
        safe,n=vigencia.cola_sin_publicadas(rows,{'propuestas':[{'id':'ronda-antigua','titulo':'Obra sintética · ronda 1'}]}, {'obra sintética'})
        self.assertEqual(n,2)
        self.assertEqual([r['estado'] for r in safe], ['obsoleto','obsoleto','hecho','pendiente'])
        self.assertEqual(rows,before)
        self.assertEqual(safe[0]['evidencia']['nota'],'Conservar')

    def test_planner_never_reopens_published_piece_or_enqueues_empty_input(self):
        def day(title, images):
            return {'propuestas':[{'id':'sintetica-v1','titulo':title,'laminas':images}],
                    'decisiones':{'propuestas':{'sintetica-v1':{'laminas':['si']}}}}
        with patch.object(productor, 'tira_de', return_value=None), patch.object(vigencia,'registro_publicadas',return_value={'obra sintética'}):
            self.assertEqual(productor.planear(day('Obra sintética · ronda 1',['a.png']),[],{},{} )[0], [])
            self.assertEqual(productor.planear(day('Otra obra',[{}]),[],{},{} )[0], [])


if __name__=='__main__':unittest.main()
