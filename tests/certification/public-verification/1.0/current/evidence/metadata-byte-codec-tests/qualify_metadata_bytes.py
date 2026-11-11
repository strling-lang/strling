from pathlib import Path
import base64,copy,gzip,hashlib,json
from metadata_bytes import encode,decode,MAX_RAW,MAX_ENCODED
base=Path(__file__).resolve().parent;source='3e7061271d906251cb17c3eb06b6c748ac3068e7'
raw=b'First\r\nsecond\nno-final-newline'
doc=json.loads(encode(raw,'preparation.log',source));assert decode(doc,source)==raw
mutations={
 'source':lambda d:d.update(source='9'*40),'schema':lambda d:d.update(schema_version='wrong'),
 'kind':lambda d:d.update(document_kind='wrong'),'encoding':lambda d:d.update(encoding='wrong'),
 'name-traversal':lambda d:d.update(original_name='../secret'),'name-empty':lambda d:d.update(original_name=''),
 'missing':lambda d:d.pop('sha256'),'extra':lambda d:d.update(unrecognized=True),
 'negative-size':lambda d:d.update(bytes=-1),'boolean-size':lambda d:d.update(bytes=True),
 'oversize':lambda d:d.update(bytes=MAX_RAW+1),'wrong-size':lambda d:d.update(bytes=d['bytes']+1),
 'hash':lambda d:d.update(sha256='0'*64),'corruption':lambda d:d.update(payload='!'),
 'truncation':lambda d:d.update(payload=base64.b64encode(base64.b64decode(d['payload'])[:-4]).decode()),
 'trailing-stream':lambda d:d.update(payload=base64.b64encode(base64.b64decode(d['payload'])+gzip.compress(b'extra')).decode()),
 'encoded-bound':lambda d:d.update(payload='a'*(MAX_ENCODED+1)),
 'decompression-bound':lambda d:d.update(bytes=1,payload=base64.b64encode(gzip.compress(b'x'*1000000)).decode()),
}
rejected=[]
for name,change in mutations.items():
    bad=copy.deepcopy(doc);change(bad)
    try:decode(bad,source)
    except ValueError:rejected.append(name)
    else:raise AssertionError(name)
report=dict(status='passed-lossless-metadata-codec-and-adversarial-bounds',source=source,
    exact_mixed_newline_roundtrip=True,rejected_mutations=rejected,maximum_decoded_bytes=MAX_RAW,
    maximum_encoded_characters=MAX_ENCODED,codec_sha256=hashlib.sha256((base/'metadata_bytes.py').read_bytes()).hexdigest(),
    source_changed=False,private_key_read=False,publication_authorized=False)
(base/'metadata-bytes-qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
