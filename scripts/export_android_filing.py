"""Verify a signed APK and export public Android filing information (no private keys)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parent.parent


def export(apk, sdk, java, output_directory, api_base):
    tools = sorted((sdk / 'build-tools').iterdir(), key=lambda p: tuple(int(n) for n in re.findall(r'\d+', p.name)))
    tool = next((p for p in reversed(tools) if (p / 'lib/apksigner.jar').is_file()), None)
    if tool is None:
        raise ValueError('Android build-tools with apksigner are required')
    verified = subprocess.run([str(java), '-jar', str(tool / 'lib/apksigner.jar'), 'verify', '--verbose',
        '--print-certs-pem', str(apk)], capture_output=True, check=True)
    output = verified.stdout.decode('utf-8')
    pems = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', output, re.DOTALL)
    if len(pems) != 1:
        raise ValueError('Expected one signing certificate; review multi-signer APKs explicitly')
    certificate = x509.load_pem_x509_certificate(pems[0].encode())
    public_key = certificate.public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError('Expected RSA signing certificate for the current filing workflow')
    expected = x509.load_der_x509_certificate((ROOT / 'docs/assets/filing/android/lianban-signing-cert.der').read_bytes())
    if expected.fingerprint(hashes.SHA256()) != certificate.fingerprint(hashes.SHA256()):
        raise ValueError('APK certificate does not match the generated release key')
    badging = subprocess.check_output([str(tool / 'aapt2.exe'), 'dump', 'badging', str(apk)]).decode('utf-8')
    package = re.search(r"^package: name='([^']+)'", badging, re.MULTILINE).group(1)
    name = re.search(r"^application-label:'([^']+)'", badging, re.MULTILINE).group(1)
    if package != 'com.liftlab.liftlab' or name != '练伴':
        raise ValueError('APK package or display name differs from the filing identity')
    directory = output_directory
    directory.mkdir(parents=True, exist_ok=True)
    numbers = public_key.public_numbers()
    md5 = certificate.fingerprint(hashes.MD5()).hex().upper()
    info = {'app_name': name, 'package_name': package, 'public_key_modulus_decimal': str(numbers.n),
        'public_key_modulus_hex': format(numbers.n, 'X'), 'public_key_exponent': numbers.e,
        'signature_md5': md5, 'signature_sha1': certificate.fingerprint(hashes.SHA1()).hex().upper(),
        'signature_sha256': certificate.fingerprint(hashes.SHA256()).hex().upper(),
        'key_algorithm': 'RSA', 'key_size': public_key.key_size, 'certificate_subject': certificate.subject.rfc4514_string(),
        'not_before_utc': certificate.not_valid_before_utc.isoformat(), 'not_after_utc': certificate.not_valid_after_utc.isoformat(),
        'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(), 'apk_path': str(apk.resolve()),
        'verified_from_release_apk': True, 'api_base_build_argument': api_base,
        'signature_schemes': [line for line in output.splitlines() if line.startswith('Verified using')]}
    (directory / 'lianban-app-identity.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    (directory / 'lianban-public-key-modulus.txt').write_text(str(numbers.n) + '\n', encoding='ascii')
    (directory / 'lianban-public-key-modulus-hex.txt').write_text(format(numbers.n, 'X') + '\n', encoding='ascii')
    (directory / 'lianban-signature-md5.txt').write_text(md5 + '\n', encoding='ascii')
    (directory / 'lianban-signing-cert.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    (directory / 'lianban-public-key.pem').write_bytes(public_key.public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo))
    content = f'''练伴：Android App 备案信息
已从正式签名的 release APK 验证。本文件只包含公开资料。

APP名称：{name}
APP包名：{package}

公钥（APK signature 中 RSA 模数，十进制；复制下面一整行）：
{numbers.n}

签名MD5值（证书指纹，十六进制，无冒号；不是APK文件MD5）：
{md5}

证书主体：{info['certificate_subject']}
算法：RSA-{public_key.key_size} / SHA256withRSA
有效期至（UTC）：{info['not_after_utc']}
APK SHA256（仅用于文件校验，不填入签名MD5字段）：
{info['apk_sha256']}

备案“公钥”字段按华为云要求使用 APK signature 模数，不要复制 PEM 标头或私钥。
以最终实际分发APK的签名为准；更换签名或平台重签后需重新核对特征信息。
构建时接口参数：{api_base}
此文件只核验安装包身份，不代表接口可用；公网备案与私有测试连通性分别验收。
'''
    (directory / 'lianban-app-filing.txt').write_text(content, encoding='utf-8')
    print(json.dumps({'package': package, 'signature_md5': md5, 'key_bits': public_key.key_size,
        'verified': True, 'output': str(directory)}, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT / 'mobile/build/app/outputs/flutter-apk/app-release.apk')
    parser.add_argument('--sdk', type=Path, default=ROOT / '.tools/android-sdk')
    parser.add_argument('--java', type=Path, default=Path('C:/Program Files/Java/jdk-17/bin/java.exe'))
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/assets/filing/android')
    parser.add_argument('--api-base', default='https://api.lianbanfit.top')
    arguments = parser.parse_args()
    export(arguments.apk, arguments.sdk, arguments.java, arguments.output, arguments.api_base)
