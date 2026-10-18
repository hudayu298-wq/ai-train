"""Export platform icon sizes and a filing PNG from the generated brand master."""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / 'mobile/assets/branding/lianban-icon-source.png'


def export():
    image = Image.open(MASTER).convert('RGB')
    if image.width != image.height:
        raise ValueError('App icon master must be square')
    outputs = []

    def save(relative, size, filing=False):
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        result = image.resize((size, size), Image.Resampling.LANCZOS)
        if filing:
            # Palette encoding only; preserve the generated artwork, without redrawing it.
            for colors in (256, 192, 128, 96, 64):
                result.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).save(target, optimize=True)
                if target.stat().st_size < 100_000:
                    break
            else:
                raise ValueError('Filing icon must be below 100 KB')
        else:
            result.save(target, optimize=True)
        with Image.open(target) as verified:
            assert verified.size == (size, size) and verified.format == 'PNG'
            assert 'A' not in verified.getbands() and 'transparency' not in verified.info
        outputs.append({'file': relative, 'size': size, 'bytes': target.stat().st_size})

    save('docs/assets/filing/lianban-icon-512.png', 512, filing=True)
    save('mobile/assets/branding/lianban-icon-1024.png', 1024)
    for density, size in {'mdpi':48, 'hdpi':72, 'xhdpi':96, 'xxhdpi':144, 'xxxhdpi':192}.items():
        save(f'mobile/android/app/src/main/res/mipmap-{density}/ic_launcher.png', size)
    ios_dir = 'mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset'
    contents = json.loads((ROOT / ios_dir / 'Contents.json').read_text())
    for item in contents['images']:
        size = round(float(item['size'].split('x')[0]) * float(item['scale'].rstrip('x')))
        save(f"{ios_dir}/{item['filename']}", size)
    for size in (192, 512):
        save(f'mobile/web/icons/Icon-{size}.png', size)
        save(f'mobile/web/icons/Icon-maskable-{size}.png', size)
    save('mobile/web/favicon.png', 32)
    manifest = ROOT / 'docs/assets/filing/icon-exports.json'
    manifest.write_text(json.dumps({'app_name':'练伴', 'source': MASTER.relative_to(ROOT).as_posix(),
                                   'outputs':outputs}, ensure_ascii=False, indent=2), encoding='utf-8')
    return outputs


if __name__ == '__main__':
    results = export()
    print(json.dumps({'filing':results[0], 'platform_outputs':len(results)}, ensure_ascii=False))
