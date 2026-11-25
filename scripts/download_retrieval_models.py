"""Download pinned ONNX assets; no model code/pickle or credentials are loaded."""
import argparse
import hashlib
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'backend/data/knowledge_models_manifest.json'


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(2*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def download(directory, components=('embedding','reranker'), *, mirror=False):
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    directory=directory.resolve()
    for component in components:
        spec=manifest[component]
        target=directory/spec['id']
        target.mkdir(parents=True,exist_ok=True)
        for name,metadata in spec['files'].items():
            dest=target/name
            expected=metadata.get('sha256')
            if dest.is_file() and expected and sha256(dest)==expected:
                continue
            origin='https://hf-mirror.com' if mirror else 'https://huggingface.co'
            url=f"{origin}/{spec['repository']}/resolve/{spec['revision']}/{metadata['remote']}"
            partial=dest.with_suffix(dest.suffix+'.partial')
            with httpx.Client(follow_redirects=True,timeout=httpx.Timeout(180,connect=20)) as client:
                with client.stream('GET',url) as response:
                    response.raise_for_status()
                    with partial.open('wb') as output:
                        for block in response.iter_bytes(1024*1024):
                            output.write(block)
            actual=sha256(partial)
            if expected and actual!=expected or metadata.get('size') and partial.stat().st_size!=metadata['size']:
                partial.unlink(missing_ok=True)
                raise ValueError('Model asset checksum/size mismatch: '+component+'/'+name)
            if not expected:
                raise ValueError('Manifest must pin every asset checksum before release')
            partial.replace(dest)
        (target/'provenance.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Verified '+spec['id'],flush=True)
    return manifest['version']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'.tools/retrieval-models')
    parser.add_argument('--mirror',action='store_true',help='Use hf-mirror.com transport; exact upstream revision, size and SHA256 are still mandatory')
    args=parser.parse_args()
    download(args.directory,mirror=args.mirror)
