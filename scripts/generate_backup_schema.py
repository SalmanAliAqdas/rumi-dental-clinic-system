"""Maintainer helper: derive public schema metadata from trusted migrations only."""
import argparse,os,sqlite3,subprocess,sys,tempfile
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from clinic.backups.archive import atomic_json,database_structure,known_migrations

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='trusted-backup-schema-',dir=ROOT/'runtime') as temp:
        env={**os.environ,'RUMI_DATA_DIR':temp,'DJANGO_SETTINGS_MODULE':'config.settings'}
        subprocess.run([sys.executable,str(ROOT/'manage.py'),'migrate','--noinput'],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL)
        with closing(sqlite3.connect(Path(temp)/'clinic.sqlite3')) as c:result={'format_version':1,'migrations':known_migrations(),'tables':database_structure(c)}
        if args.write:atomic_json(ROOT/'clinic/backups/schema.json',result)
        print('Trusted schema derived from fresh migrations; no patient data/accounts included.'+(' Source metadata written.' if args.write else ' Use --write to refresh source metadata.'))
if __name__=='__main__':main()
