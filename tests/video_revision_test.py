import base64
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nube'))
import video_revision as m

class VideoTests(unittest.TestCase):
    def test_aes_gcm_authenticates_bytes_and_keeps_key_separate(self):
        data=b'\0\0\0\x14ftypisom'+b'\0'*40
        payload,desc=m.cifrar(data,key=b'k'*32,iv=b'i'*12)
        self.assertNotIn(data,payload)
        self.assertEqual(len(payload),len(data)+16)
        key,iv=base64.b64decode(desc['key']),base64.b64decode(desc['iv'])
        self.assertEqual(m.AESGCM(key).decrypt(iv,payload,None),data)
        with self.assertRaises(Exception):m.AESGCM(key).decrypt(iv,payload[:-1]+bytes([payload[-1]^1]),None)
        self.assertEqual(desc['cipher_sha256'],hashlib.sha256(payload).hexdigest())
    def test_only_exact_drive_cut_identity_is_accepted(self):
        p={'id':'sintetica-corte-nube-'+'a'*12,'video':'https://drive.google.com/file/d/syntheticvideo123/preview'}
        self.assertEqual(m.identidad(p)[2],'syntheticvideo123')
        for bad in ({**p,'id':'otra'},{**p,'video':'https://evil.example/video.mp4'},{**p,'video':p['video']+'?x=1'}):
            with self.assertRaises(m.VideoError):m.identidad(bad)
    def test_changed_original_is_rejected_before_download(self):
        p={'id':'sintetica-corte-nube-'+'a'*12,'video':'https://drive.google.com/file/d/syntheticvideo123/preview'}
        class Response:
            def json(self):return {'mimeType':'video/mp4','trashed':False,'size':100,'md5Checksum':'b'*32}
        with tempfile.TemporaryDirectory() as tmp,patch.object(m.drive,'_peticion',return_value=Response()),patch.object(m.drive,'bajar') as download:
            with self.assertRaises(m.VideoError):m.original(p,Path(tmp)/'original.mp4')
            download.assert_not_called()
    def test_workflow_keeps_previews_private_and_never_decides(self):
        code=Path(m.__file__).read_text()
        self.assertNotIn("sala.post('decidir'",code)
        self.assertNotIn('setSharing',code)
        self.assertIn("'content':base64.b64encode(payload).decode()",code)
        self.assertNotIn("'content':base64.b64encode(data)",code)

if __name__=='__main__':unittest.main()
