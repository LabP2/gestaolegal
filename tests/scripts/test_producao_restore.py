"""Integração do fluxo de restore com Docker substituído, sem banco real.

Executa o mover real sobre um volume temporário e confere que conflito impede
subir a aplicação. Migração SQL e comandos Docker são apenas registrados.
"""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('conflito', [False, True])
def test_restore_organiza_volume_antes_de_subir(tmp_path, conflito):
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'dumps').mkdir()
    for name in ['producao_para_local.sh', 'mover_arquivos_tenant.py']:
        shutil.copy(ROOT / 'scripts' / name, tmp_path / 'scripts' / name)
    (tmp_path / '.env').write_text('FLASK_ENV=development\nDB_NAME=restore_test\nDB_USER=test_user\n')
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w') as archive:
        files = {'casos/anexo.pdf': b'original'}
        if conflito:
            files['1/casos/anexo.pdf'] = b'nao sobrescrever'
        for name, content in files.items():
            info = tarfile.TarInfo(name); info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    files = {'gestaolegal.sql.gz': gzip.compress(b'SELECT 1;'), 'uploads.tar': buf.getvalue(), 'info.txt': b'fixture local'}
    files['SHA256SUMS'] = ''.join(f'{hashlib.sha256(v).hexdigest()}  {k}\n' for k,v in files.items()).encode()
    with tarfile.open(tmp_path / 'pacote.tar', 'w') as archive:
        for name, content in files.items():
            info=tarfile.TarInfo(name);info.size=len(content)
            archive.addfile(info,io.BytesIO(content))
    bindir=tmp_path/'bin';bindir.mkdir()
    docker=bindir/'docker'
    docker.write_text('''#!/usr/bin/env python3
import sys,json,subprocess
from pathlib import Path
args=sys.argv[1:]
with open('commands.jsonl','a') as f:f.write(json.dumps(args)+'\\n')
if '--entrypoint' in args:
    code=sys.stdin.read()
    opts=['--raiz-privada',str(Path('uploads').resolve())]
    if '--dry-run' in args:opts.append('--dry-run')
    sys.exit(subprocess.run([sys.executable,'-',*opts],input=code,text=True).returncode)
if 'exec' in args and 'SHOW DATABASES' not in ' '.join(args):sys.stdin.read()
''')
    docker.chmod(0o755)
    env={**os.environ, 'PATH':str(bindir)+os.pathsep+os.environ['PATH'],
         'FLASK_ENV':'development','DB_NAME':'restore_test','DB_USER':'test_user',
         'DEV_UPLOADS_PATH':'./uploads'}
    proc=subprocess.run(['bash',str(tmp_path/'scripts/producao_para_local.sh'),'restaurar','pacote.tar','--sim'],cwd=tmp_path,env=env,capture_output=True,text=True)
    commands=[json.loads(x) for x in (tmp_path/'commands.jsonl').read_text().splitlines()]
    app_up=any(x[-2:]==['up','-d'] for x in commands)
    if conflito:
        assert proc.returncode != 0
        assert not app_up
        assert (tmp_path/'uploads/1/casos/anexo.pdf').read_bytes()==b'nao sobrescrever'
        assert (tmp_path/'uploads/casos/anexo.pdf').exists()
    else:
        assert proc.returncode == 0, proc.stderr
        assert app_up
        assert (tmp_path/'uploads/1/casos/anexo.pdf').read_bytes()==b'original'
        assert not (tmp_path/'uploads/casos').exists()
        moves=[x for x in commands if '--entrypoint' in x]
        assert '--dry-run' in moves[0] and '--dry-run' not in moves[1]
        assert commands.index(moves[1]) < next(i for i,x in enumerate(commands) if x[-2:]==['up','-d'])
