"""Regresiones: negativa terminal no equivale a envío incierto."""
import copy
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from motores import imagen, imagen_hidream as hi
from motores._comun import MotorError
from sala_recibos import ejecutar, Recibos, digest, canonical
from sala_recibos_test import API, ENV, RID, SOURCE, PLAN, PHOTO

class Negativas(unittest.TestCase):
    def test_terminal_then_later_run_recovers_but_same_attempt_never_repeats(self):
        for reason in ('tarea_fallida', 'tarea_cancelada', 'no_enviado'):
            with self.subTest(reason=reason):
                api=API()
                def run(run_id):
                    store=Recibos(RID, api=api, env=dict(ENV,GITHUB_RUN_ID=run_id))
                    return ejecutar(RID,SOURCE,lambda:copy.deepcopy(PLAN),{},store=store)
                with patch.object(imagen,'generar',side_effect=imagen.RechazoImagen(reason)) as gen:
                    for _ in range(2):
                        with self.assertRaises(imagen.RechazoImagen):run('123')
                    self.assertEqual(gen.call_count,1)
                with patch.object(imagen,'generar',return_value=(PHOTO,'png','hidream_demo',[])) as gen:
                    run('124')
                    self.assertFalse(gen.call_args.args[1]['_imagen_solo_recibo'])
                with patch.object(imagen,'generar',side_effect=AssertionError('resultado se reutiliza')):
                    run('125')
    def test_corrupt_or_foreign_negative_never_authorizes_generation(self):
        for record in ({'estado':'rechazo_sin_imagen','motivo':'timeout'},
                       {'estado':'rechazo_sin_imagen','motivo':'tarea_fallida','extra':True},
                       {'estado':'rechazo_sin_imagen','motivo':'desconocido'}):
            api=API()
            store=Recibos(RID,api=api,env=ENV)
            with patch.object(imagen,'generar',side_effect=MotorError('incierto')):
                with self.assertRaises(MotorError):
                    ejecutar(RID,SOURCE,lambda:copy.deepcopy(PLAN),{},store=store)
            sha=digest(canonical(store.get('plan.zip')[0]))
            store.put('rechazo-123-1.zip',dict(record,plan_sha256=sha))
            with patch.object(imagen,'generar',side_effect=AssertionError('no reenviar')):
                with self.assertRaises(MotorError):
                    ejecutar(RID,SOURCE,lambda:copy.deepcopy(PLAN),{},store=store)
    def test_hidream_status_three_and_four_are_confirmed(self):
        for status,reason in ((3,'tarea_fallida'),(4,'tarea_cancelada')):
            client=Mock()
            client.submit.return_value.result.return_value=(None,123,'Error: Task failed with status %s: Unknown error'%status,None)
            with tempfile.TemporaryDirectory() as td,patch.object(hi,'RAIZ',pathlib.Path(td)),patch.object(hi,'_DETENIDO',''),patch.object(hi,'_FALLOS',0),patch.object(hi,'_client',return_value=client):
                with self.assertRaises(imagen.RechazoImagen) as e:hi.generar('A scale model',{})
                self.assertEqual(e.exception.motivo,reason)
                with self.assertRaises(imagen.RechazoImagen) as e:hi.generar('Another scale model',{})
                self.assertEqual(e.exception.motivo,'no_enviado')
                self.assertEqual(client.submit.call_count,1)
    def test_timeout_and_unknown_response_remain_uncertain(self):
        for result in (TimeoutError('timeout'),(None,123,'Unknown error',None)):
            client=Mock()
            if isinstance(result,Exception):client.submit.return_value.result.side_effect=result
            else:client.submit.return_value.result.return_value=result
            with tempfile.TemporaryDirectory() as td,patch.object(hi,'RAIZ',pathlib.Path(td)),patch.object(hi,'_DETENIDO',''),patch.object(hi,'_FALLOS',0),patch.object(hi,'_client',return_value=client):
                with self.assertRaises(MotorError) as e:hi.generar('A scale model',{})
                self.assertNotIsInstance(e.exception,imagen.RechazoImagen)
    def test_client_failure_does_not_send(self):
        with tempfile.TemporaryDirectory() as td,patch.object(hi,'RAIZ',pathlib.Path(td)),patch.object(hi,'_DETENIDO',''),patch.object(hi,'_client',side_effect=RuntimeError('offline')):
            with self.assertRaises(imagen.RechazoImagen) as e:hi.generar('A scale model',{})
            self.assertEqual(e.exception.motivo,'no_enviado')
    def test_no_implicit_paid_fallback_after_refusal(self):
        paid=Mock()
        with patch.dict(imagen.MOTORES,{'hidream_demo':Mock(side_effect=imagen.RechazoImagen('tarea_fallida')),'openai_broker':paid},clear=True):
            with self.assertRaises(imagen.RechazoImagen):
                imagen.generar('A scale model',{'imagen_motores':'hidream_demo,openai_broker'})
        paid.assert_not_called()

if __name__=='__main__':unittest.main()
