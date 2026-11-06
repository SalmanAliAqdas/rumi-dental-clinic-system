"""Cross-process leases shared by requests, snapshot workers and recovery."""
from contextlib import contextmanager
from pathlib import Path
import os
import threading

class Busy(Exception):
    pass

_local = threading.local()

def lock_path(data, name):
    data=Path(data).resolve()
    return data.parent / ('.'+data.name+'.rumi-'+name+'.lock')

@contextmanager
def lease(path, exclusive=True):
    path=Path(path).resolve()
    held=getattr(_local,'held',None)
    if held is None:held=_local.held={}
    key=str(path)
    if key in held:
        if exclusive and not held[key]:raise Busy('Cannot upgrade an active read lease.')
        yield
        return
    handle=path.open('a+b')
    locked=False
    try:
        if os.name=='nt':
            import ctypes,msvcrt
            from ctypes import wintypes
            class Overlapped(ctypes.Structure):
                _fields_=[('Internal',ctypes.c_size_t),('InternalHigh',ctypes.c_size_t),('Offset',wintypes.DWORD),('OffsetHigh',wintypes.DWORD),('hEvent',wintypes.HANDLE)]
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.LockFileEx.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(Overlapped)]
            kernel.UnlockFileEx.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(Overlapped)]
            overlapped=Overlapped();native=msvcrt.get_osfhandle(handle.fileno())
            if not kernel.LockFileEx(native,1 | (2 if exclusive else 0),0,1,0,ctypes.byref(overlapped)):
                error=ctypes.get_last_error()
                if error in (32,33):raise Busy('Another application operation holds this lease.')
                raise OSError(error,'Could not acquire the runtime lease.')
            locked=True
        else:
            import fcntl
            try:fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except BlockingIOError:raise Busy('Another application operation holds this lease.') from None
            locked=True
        held[key]=exclusive
        yield
    finally:
        held.pop(key,None)
        if locked:
            if os.name=='nt':kernel.UnlockFileEx(native,0,1,0,ctypes.byref(overlapped))
            else:fcntl.flock(handle,fcntl.LOCK_UN)
        handle.close()

@contextmanager
def runtime_access(data, exclusive=False):
    with lease(lock_path(data,'access'),exclusive=exclusive):yield

def protected_write(function):
    from functools import wraps
    @wraps(function)
    def wrapped(*args,**kwargs):
        from django.conf import settings
        with runtime_access(settings.DATA_DIR):return function(*args,**kwargs)
    return wrapped

class RuntimeBoundaryMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        if request.path.startswith('/static/') or request.path=='/_local/trial-ready/':return self.get_response(request)
        from django.conf import settings
        from django.http import HttpResponse
        try:
            with runtime_access(settings.DATA_DIR):return self.get_response(request)
        except Busy:
            response=HttpResponse('A coordinated backup/maintenance snapshot is in progress. No submission was applied. Retry shortly; keep your form or use Back/Refresh to retry it.',status=503,content_type='text/plain')
            if request.method=='GET':
                response=HttpResponse('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Snapshot in progress</title><link rel="stylesheet" href="/static/clinic.css"></head><body><main><section class="panel"><h1>Coordinated snapshot in progress</h1><p>Clinic writes are paused briefly while the database and attachments are copied. This page will retry shortly.</p><a href="">Refresh</a></section></main><script src="/static/maintenance-retry.js" defer></script></body></html>',status=503)
            response['Retry-After']='3'
            response['Cache-Control']='no-store'
            return response


@contextmanager
def snapshot_access(data,timeout=30):
    import time
    deadline=time.monotonic()+timeout
    while True:
        context=runtime_access(data,exclusive=True)
        try:
            context.__enter__();break
        except Busy:
            if time.monotonic()>=deadline:raise Busy('Snapshot could not obtain a write pause; retry when current requests finish.')
            time.sleep(.05)
    try:yield
    finally:context.__exit__(None,None,None)
