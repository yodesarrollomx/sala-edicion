"""Limpia un log ANTES de pegarlo en un issue público (23-sep).

Por qué existe: `enmascarar_en_actions()` imprime `::add-mask::<secreto>` para que Actions tache
esos valores en su propio log. Pero los workflows guardan la salida con `tee x.log`, y el aviso
«Avisar si algo falló» pegaba ese archivo en el issue #3, público. Ahí salieron completas la
llave de Drive, la de Gemini, el token de HF, la clave del agente y la liga /exec; Google y
Hugging Face las desactivaron. Todo log que va a GitHub pasa por aquí.

Uso: python3 nube/limpiar_log.py archivo.log [últimas_N_líneas]
Quita las líneas ::add-mask::, los valores literales de los secretos presentes en el entorno
y todo lo que tenga forma de llave (hf_…, AIza…, AQ.…, llaves privadas, ligas /exec del GAS).
"""
import os
import re
import sys

SECRETOS = ('SALA_CLAVE_AGENTE', 'SALA_GAS_EXEC', 'GDRIVE_SA_JSON', 'HF_TOKEN', 'GEMINI_API_KEY',
            'CF_API_TOKEN', 'CF_ACCOUNT_ID', 'OPENAI_API_KEY')
FORMAS = [
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
    r'"private_key(_id)?"\s*:\s*"[^"]*"',
    r'\bhf_[A-Za-z0-9]{20,}',
    r'\bAIza[0-9A-Za-z_\-]{30,}',
    r'\bAQ\.[0-9A-Za-z_\-\.]{20,}',
    r'\bsk-[A-Za-z0-9_\-]{20,}',
    r'https://script\.google\.com/macros/s/[A-Za-z0-9_\-]+/exec',
    r'([?&](clave|key|token)=)[^&\s"\']+',
]


def limpiar(texto):
    texto = '\n'.join(l for l in texto.splitlines() if '::add-mask::' not in l)
    for var in SECRETOS:
        v = os.environ.get(var, '').strip()
        if len(v) >= 6:
            texto = texto.replace(v, '***')
            for parte in v.splitlines():      # el JSON de la cuenta de servicio, línea por línea
                if len(parte.strip()) >= 12:
                    texto = texto.replace(parte.strip(), '***')
    for f in FORMAS:
        texto = re.sub(f, lambda m: (m.group(1) if m.lastindex and m.group(1) and m.group(1).startswith(('?', '&')) else '') + '***',
                       texto, flags=re.S)
    return texto


def main():
    if len(sys.argv) < 2:
        print('uso: limpiar_log.py archivo.log [N]', file=sys.stderr)
        return 2
    try:
        crudo = open(sys.argv[1], encoding='utf-8', errors='replace').read()
    except OSError:
        return 0
    lineas = limpiar(crudo).splitlines()
    if len(sys.argv) > 2:
        lineas = lineas[-int(sys.argv[2]):]
    print('\n'.join(lineas))
    return 0


if __name__ == '__main__':
    sys.exit(main())
