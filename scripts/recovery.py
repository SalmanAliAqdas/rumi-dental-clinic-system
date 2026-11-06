"""Offline recovery helper; works before any clinic/settings are initialized."""
import argparse
import getpass
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from clinic.backups.archive import verified_package,BackupError
from clinic.backups.recovery import restore,repair,journal_path
from clinic.backups.locks import Busy


def secret_input(prompt):
    if sys.stdin.isatty():return getpass.getpass(prompt)
    # Private redirected input is used by automated recovery drills. Windows
    # getpass otherwise reads the console even when stdin is a pipe.
    print(prompt+' (private input stream)',file=sys.stderr)
    value=sys.stdin.readline(1026)
    if not value:raise BackupError('Recovery credential input ended; nothing replaced.')
    return value.rstrip('\r\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('verify','restore'):
        p=sub.add_parser(command);p.add_argument('--package',type=Path,required=True)
        if command=='restore':p.add_argument('--data-dir',type=Path,required=True)
    p=sub.add_parser('repair');p.add_argument('--data-dir',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='repair':
            print('Stop all servers for this data directory first. Repair recovers the previous installation.')
            username=input('Current/rollback Owner username (blank only for empty fresh recovery): ')
            owner_password=secret_input('Current/rollback Owner password: ') if username else ''
            if input('Type REPAIR to confirm: ')!='REPAIR':raise BackupError('Repair cancelled.')
            print(repair(args.data_dir,username,owner_password));return 0
        password=secret_input('Backup recovery password: ')
        with verified_package(args.package,password,expected_kind='backup') as (_,manifest):
            print('Verified complete backup:',manifest['created_at'])
            print('App:',manifest['app_version'],'Schema:',manifest['schema_version'])
            print('Staged schema upgrade needed:',manifest['upgrade_required'])
        if args.command=='verify':return 0
        target=args.data_dir.absolute()
        print('Restore target:',target)
        print('Database, matching secret and attachments will be switched together. No merge. Sessions cleared. Stop this runtime server first.')
        username=owner_password=''
        if (target/'clinic.sqlite3').is_file():
            username=input('Existing active Owner username: ')
            owner_password=secret_input('Existing Owner password: ')
        if input('Type RESTORE to confirm replacement/fresh recovery: ')!='RESTORE':raise BackupError('Restore cancelled.')
        result=restore(args.package,password,target,confirmed=True,username=username,owner_password=owner_password)
        print('Verified restoration activated:',result['target'])
        if result['rollback']:print('Verified previous runtime retained:',result['rollback'])
        print('Launch compatible source with this explicit data directory; sign in with restored credentials. Reconfigure destinations/automatic credentials on this computer.')
        return 0
    except (BackupError,Busy) as exc:
        print('Stopped:',str(exc));return 1
    except (OSError,ValueError):
        print('Stopped: filesystem/package operation failed; inspect destinations and any restore journal. No automatic account initialization.');return 1

if __name__=='__main__':raise SystemExit(main())
