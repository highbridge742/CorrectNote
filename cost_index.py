"""Exact derived cost tables; stale or absent data uses the source parser."""
import gzip,hashlib,io,pickle
SOURCE_SHA256 = 'bd9efabf65d326ad46de7757d5ed331a7424b450aa72786f2b629eedb578073e'
INDEX_SHA256 = 'f2cdc9478fa3f6140418aaacacd48800cc6da605a0999f04c519cf576038d1d2'

class _PrimitiveOnly(pickle.Unpickler):
    def find_class(self,module,name):
        raise pickle.UnpicklingError('global objects are not allowed')
    def persistent_load(self,key):
        raise pickle.UnpicklingError('external objects are not allowed')

def load(source_path,index_path):
    try:
        with open(source_path,'rb') as stream:
            if hashlib.sha256(stream.read()).hexdigest()!=SOURCE_SHA256:return None
        with open(index_path,'rb') as stream:packed=stream.read()
        # Pin the complete bundled bytes before decompression/deserialization.
        if hashlib.sha256(packed).hexdigest()!=INDEX_SHA256:return None
        saved=_PrimitiveOnly(io.BytesIO(gzip.decompress(packed))).load()
        if not isinstance(saved,dict) or saved.get('schema')!=1 or saved.get('source_sha256')!=SOURCE_SHA256:return None
        tables=tuple(saved[key] for key in ('readings','costs','surfaces'))
        if not all(isinstance(table,dict) for table in tables):return None
        return tables
    except (OSError,EOFError,pickle.UnpicklingError,ValueError,TypeError,KeyError):
        return None
