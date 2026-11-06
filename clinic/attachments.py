"""Strict local-file validation and generated-name storage; never public media."""
import hashlib
from io import BytesIO
from pathlib import Path
import uuid
import re
import warnings
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject
from .clinical_services import audit

def validate_upload(upload):
    limit = settings.RUMI_MAX_UPLOAD_BYTES
    if upload.size > limit:
        raise ValidationError('File exceeds the configured upload-size limit.')
    data = upload.read(limit + 1)
    if len(data) > limit or not data:
        raise ValidationError('File is empty or exceeds the configured upload-size limit.')
    suffix = Path(upload.name).suffix.lower()
    if suffix in ['.jpg', '.jpeg', '.png']:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    expected = 'PNG' if suffix == '.png' else 'JPEG'
                    if image.format != expected:
                        raise ValidationError('Image contents do not match the filename extension.')
                    width, height = image.size
                    if max(width, height) > settings.RUMI_MAX_IMAGE_SIDE or width * height > settings.RUMI_MAX_IMAGE_PIXELS:
                        raise ValidationError('Image dimensions exceed the configured limits.')
                    image.verify()
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    thumbnail = ImageOps.exif_transpose(image).copy()
                    thumbnail.thumbnail((512, 512))
                    if thumbnail.mode not in ['RGB', 'RGBA', 'L', 'LA']:
                        thumbnail = thumbnail.convert('RGB')
                    thumbnail.info.clear()
                    output = BytesIO()
                    thumbnail.save(output, format='PNG')
            return data, '.png' if suffix == '.png' else '.jpg', 'image/png' if suffix == '.png' else 'image/jpeg', output.getvalue()
        except ValidationError:
            raise
        except Exception:
            raise ValidationError('Image is malformed or cannot be processed safely.') from None
    if suffix == '.pdf':
        try:
            if not data.startswith(b'%PDF-') or not data.rstrip().endswith(b'%%EOF'):
                raise ValueError
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted or not 0 < len(reader.pages) <= settings.RUMI_MAX_PDF_PAGES:
                raise ValueError
            visited = set()
            dangerous = {'/JS', '/JavaScript', '/AA', '/OpenAction', '/Launch', '/EmbeddedFiles', '/RichMedia', '/XFA', '/AcroForm', '/A'}
            count = 0
            def inspect(value, depth=0):
                nonlocal count
                count += 1
                if count > 20000 or depth > 40:
                    raise ValueError
                if isinstance(value, IndirectObject):
                    key = (value.idnum, value.generation)
                    if key in visited:
                        return
                    visited.add(key)
                    value = value.get_object()
                if isinstance(value, DictionaryObject):
                    if dangerous.intersection(value.keys()):
                        raise ValueError
                    for child in value.values():
                        inspect(child, depth + 1)
                elif isinstance(value, ArrayObject):
                    for child in value:
                        inspect(child, depth + 1)
            inspect(reader.trailer)
            return data, '.pdf', 'application/pdf', None
        except Exception:
            raise ValidationError('PDF must be a valid, unencrypted passive document within the page limit; forms, scripts and embedded actions are unsupported.') from None
    raise ValidationError('Only JPEG, PNG and PDF files are supported. SVG, HTML and executable files are not accepted.')


def stored_path(name):
    if not re.fullmatch(r'(originals|thumbnails)/[0-9a-f]{32}\.(png|jpg|pdf)', name):
        raise ValidationError('Invalid attachment storage reference.')
    root = (settings.DATA_DIR / 'attachments').resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or len(path.relative_to(root).parts) != 2:
        raise ValidationError('Invalid attachment storage reference.')
    return path


from .backups.locks import protected_write

@protected_write
def store_attachment(form, upload, patient, actor):
    data, extension, content_type, thumbnail = validate_upload(upload)
    key = uuid.uuid4().hex
    names = [('originals/' + key + extension, data)]
    if thumbnail is not None:
        names.append(('thumbnails/' + key + '.png', thumbnail))
    created = []
    try:
        with transaction.atomic():
            for name, content in names:
                path = stored_path(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as handle:
                    created.append(path)
                    handle.write(content)
            attachment = form.save(commit=False)
            attachment.patient, attachment.uploader = patient, actor
            attachment.storage_name, attachment.content_type, attachment.size = names[0][0], content_type, len(data)
            attachment.thumbnail_name = names[1][0] if thumbnail is not None else ''
            attachment.full_clean()
            attachment.save()
            audit(actor, patient, 'attachment_upload', attachment)
            return attachment
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
