"""DPAPI current-user protection. No plaintext fallback or machine-wide mode."""
import os
from .crypto import BackupError

def transform(value,protect=True):
    if os.name!='nt':raise BackupError('Automatic encryption credentials require Windows user-bound DPAPI; no plaintext credential was saved.')
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    source=ctypes.create_string_buffer(value)
    incoming=Blob(len(value),ctypes.cast(source,ctypes.POINTER(ctypes.c_ubyte)));outgoing=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[wintypes.HLOCAL];kernel.LocalFree.restype=wintypes.HLOCAL
    function=crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    if not function(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing)):
        raise BackupError('Windows could not protect/read the automatic credential for this Windows user. Reconfigure automatic backups; no plaintext fallback is used.')
    try:return ctypes.string_at(outgoing.data,outgoing.size)
    finally:kernel.LocalFree(outgoing.data)

def protect_password(password):return transform(password.encode('utf-8'))
def read_password(protected):
    try:return transform(protected,False).decode('utf-8')
    except UnicodeError:raise BackupError('Saved Windows credential is invalid; configure it again.') from None
