"""Streaming AES-256-GCM with a fixed, bounded Argon2id KDF profile."""
from pathlib import Path
import os
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

MAGIC=b'RUMIPKG1'
HEADER_SIZE=36
CHUNK=1024*1024
MAX_PACKAGE=8*1024**3

class BackupError(Exception):
    """Only fixed, patient/password-free messages are shown or recorded."""

def key_for(password,salt):
    if not isinstance(password,str) or not password or len(password)>1024:raise BackupError('A recovery password is required (maximum 1024 characters).')
    return Argon2id(salt=salt,length=32,iterations=3,lanes=4,memory_cost=64*1024).derive(password.encode('utf-8'))

def encrypt(source,target,password):
    source,target=Path(source),Path(target)
    if source.stat().st_size>MAX_PACKAGE-HEADER_SIZE-16:raise BackupError('Package exceeds the supported 8 GiB limit.')
    salt,nonce=os.urandom(16),os.urandom(12)
    header=MAGIC+salt+nonce
    cipher=Cipher(algorithms.AES(key_for(password,salt)),modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(header)
    try:
        with source.open('rb') as incoming,target.open('xb') as outgoing:
            os.chmod(target,0o600);outgoing.write(header)
            while block:=incoming.read(CHUNK):outgoing.write(cipher.update(block))
            outgoing.write(cipher.finalize());outgoing.write(cipher.tag);outgoing.flush();os.fsync(outgoing.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise

def decrypt(source,target,password):
    source,target=Path(source),Path(target)
    size=source.stat().st_size
    if not HEADER_SIZE+16<size<=MAX_PACKAGE:raise BackupError('Package is truncated or exceeds the supported size limit.')
    try:
        with source.open('rb') as incoming:
            header=incoming.read(HEADER_SIZE)
            if header[:8]!=MAGIC:raise BackupError('Unsupported encrypted package format.')
            incoming.seek(-16,2);tag=incoming.read(16);incoming.seek(HEADER_SIZE)
            cipher=Cipher(algorithms.AES(key_for(password,header[8:24])),modes.GCM(header[24:36],tag)).decryptor()
            cipher.authenticate_additional_data(header)
            remaining=size-HEADER_SIZE-16
            with target.open('xb') as outgoing:
                os.chmod(target,0o600)
                while remaining:
                    block=incoming.read(min(CHUNK,remaining))
                    if not block:raise BackupError('Package is truncated.')
                    remaining-=len(block);outgoing.write(cipher.update(block))
                outgoing.write(cipher.finalize());outgoing.flush();os.fsync(outgoing.fileno())
    except InvalidTag:
        target.unlink(missing_ok=True)
        raise BackupError('Wrong recovery password or corrupted encrypted package.') from None
    except BaseException:
        target.unlink(missing_ok=True)
        raise
