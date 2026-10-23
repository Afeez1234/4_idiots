"""Grab an app screen for the landing page and save it as a small WebP.

    python landing/tools/shots.py id-card            # from the phone over adb
    python landing/tools/shots.py records --from shot.jpg

Writes landing/img/app-<name>.webp: status bar and gesture bar cropped off,
trimmed to the phone frame's 1080:2170 ratio, 540 px wide. Take screens from
the demo student account only; the page is public.

Needs Pillow. adb is found on PATH or in the Android SDK's platform-tools.
"""

import argparse
import io
import os
import pathlib
import shutil
import subprocess
import sys

from PIL import Image

IMG = pathlib.Path(__file__).resolve().parent.parent / 'img'
FRAME_RATIO = 2170 / 1080  # .phone-screen aspect-ratio in styles.css
WIDTH = 540


def adb():
    found = shutil.which('adb')
    if found:
        return found
    sdk = pathlib.Path(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk',
                       'platform-tools', 'adb.exe')
    if sdk.exists():
        return str(sdk)
    sys.exit('adb not found: install platform-tools or pass --from')


def from_phone():
    png = subprocess.run([adb(), 'exec-out', 'screencap', '-p'],
                         capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png))


def trim(im, top, bottom):
    im = im.convert('RGB').crop((0, top, im.width, im.height - bottom))
    height = round(im.width * FRAME_RATIO)
    if im.height > height:
        cut = (im.height - height) // 2
        im = im.crop((0, cut, im.width, cut + height))
    im.thumbnail((WIDTH, 10_000), Image.LANCZOS)
    return im


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('name', help='saved as img/app-<name>.webp')
    p.add_argument('--from', dest='source', help='an existing screenshot instead of the phone')
    p.add_argument('--top', type=int, help='px to cut from the top (status bar)')
    p.add_argument('--bottom', type=int, help='px to cut from the bottom (gesture bar)')
    args = p.parse_args()

    if args.source:
        im = Image.open(args.source)
        # Shared screenshots usually arrive with the bars already removed.
        top, bottom = args.top or 0, args.bottom or 0
    else:
        im = from_phone()
        top = 120 if args.top is None else args.top      # Galaxy S24 status bar
        bottom = 50 if args.bottom is None else args.bottom

    out = IMG / f'app-{args.name}.webp'
    IMG.mkdir(exist_ok=True)
    trim(im, top, bottom).save(out, 'WEBP', quality=82, method=6)
    print(f'{out}  {out.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
