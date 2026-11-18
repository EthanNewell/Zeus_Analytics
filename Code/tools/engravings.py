"""Engravings for the interface: Nano Banana draws the subject in the reference technique,
then every frame is mapped to the one duotone of the site (#0000e8 → #ffffff).

Usage (run outside the app, needs Pillow and a Google AI key file):
    python tools/engravings.py generate --ref path/to/style.jpg --out RAW_DIR [names...]
    python tools/engravings.py duotone RAW_DIR static/img

Keys are read from ~/.config/secrets/google-ai.env (GOOGLE_API_KEY, GOOGLE_API_KEY_2, ...);
a key that hits its monthly spending cap is skipped, 503 moves the request to the next key.
"""

import argparse
import base64
import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "gemini-nano-banana-2.1"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BLUE = (0, 0, 232)

STYLE = (
    "Monochrome engraving illustration: fine stipple dots, halftone screen and line hatching, "
    "bright white linework on a deep dark background, high detail, crisp grain, strong contrast. "
    "Copy the drawing technique, grain and lighting of the reference image exactly, but NOT its "
    "subject: draw only the subject described below. No colour. No text, letters, numbers, "
    "signs, logos, flags, coats of arms or emblems anywhere in the picture. No people's faces."
)

FRAMES = {
    "hero": (
        "1:1",
        "Oblique aerial view of patchwork farmland in the southern Russian steppe beside a winding river: fields divided into land plots by straight boundary lines, one plot's outline drawn brighter; at the edge of the fields a new cottage settlement creeps into farmland. A small bright star-like sun flare in the top right corner.",
    ),
    "m1": (
        "1:1",
        "A land surveyor's theodolite on a wooden tripod standing in a wheat field next to boundary stakes with a stretched measuring tape; flat steppe horizon with a distant power line.",
    ),
    "m2": (
        "1:1",
        "A stack of official paper documents and folders tied with string, a round rubber stamp and a fountain pen on a desk, a rolled cadastral map with a grid partly unrolled. Papers have only blank lines, nothing readable.",
    ),
    "m3": (
        "1:1",
        "A hand-engraved cadastral survey plan seen from directly above, drawn entirely in white lines and stipple on the dark ground (not a photograph): field parcels as clean polygons with small square boundary markers at every corner; in the centre one irregular L-shaped parcel with a long narrow strip reaching toward a winding river; a measuring compass lying on the plan.",
    ),
    "band-cases": (
        "16:9",
        "Wide aerial view over a river valley in the southern steppe: fields cut into rectangular plots, a straight road, and a growing suburb of identical new houses and two construction cranes on former farmland.",
    ),
    "band-map": (
        "16:9",
        "Wide top-down view of a farmland mosaic with river meanders and crisp field boundaries, like an engraved survey map without any labels.",
    ),
    "band-method": (
        "16:9",
        "A long archive corridor with tall shelves full of folders and boxes of land registry files in deep perspective, soft light from a window at the far end.",
    ),
    "band-officials": (
        "16:9",
        "Wide view of an empty municipal commission meeting hall: a long table with chairs, microphones and neat stacks of papers, tall windows with light. Nobody in the room.",
    ),
    "band-upload": (
        "16:9",
        "Close-up on a desk: printed spreadsheets with columns of figures shown as abstract dots and dashes, a magnifying glass lying on them, a steel ruler and a pencil.",
    ),
    "mark": (
        "1:1",
        "A single geodetic triangulation benchmark — a small concrete pyramid survey marker with a metal pin on top — standing in short grass, centred, simple iconic composition on a plain dark background.",
    ),
}


def load_keys():
    path = Path.home() / ".config/secrets/google-ai.env"
    keys = []
    for line in path.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip().startswith("GOOGLE_API_KEY") and value.strip():
            keys.append((name.strip(), value.strip().strip('"')))
    return keys


class Keys:
    def __init__(self, keys):
        self.keys = keys
        self.dead = set()
        self.turn = 0

    def next(self):
        live = [key for key in self.keys if key[0] not in self.dead]
        if not live:
            raise SystemExit("all keys are over their spending cap")
        self.turn += 1
        return live[self.turn % len(live)]


def generate(keys, name, ratio, subject, ref_bytes, out_dir):
    body = {
        "contents": [
            {
                "parts": [
                    {"text": f"{STYLE}\n\nSubject: {subject}"},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64.b64encode(ref_bytes).decode(),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": ratio, "imageSize": "2K"},
        },
    }
    for attempt in range(8):
        key_name, key = keys.next()
        request = urllib.request.Request(
            API.format(model=MODEL),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            message = error.read().decode(errors="replace")
            if (error.code == 429 and ("spending cap" in message or "billing" in message)) or (
                error.code == 400 and "API key not valid" in message
            ):
                keys.dead.add(key_name)
                print(f"{name}: {key_name} unusable ({error.code}), next key", flush=True)
                continue
            print(f"{name}: HTTP {error.code} on {key_name}, retry {attempt + 1}", flush=True)
            time.sleep(4 + attempt * 4)
            continue
        except Exception as error:  # network trouble: retry on another key
            print(f"{name}: {type(error).__name__}, retry {attempt + 1}", flush=True)
            time.sleep(4)
            continue
        for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline:
                path = out_dir / f"{name}.png"
                path.write_bytes(base64.b64decode(inline["data"]))
                print(f"{name}: ok ({key_name})", flush=True)
                return path
        print(f"{name}: no image in answer, retry {attempt + 1}", flush=True)
    print(f"{name}: FAILED", flush=True)
    return None


def duotone(source, target, size):
    from PIL import Image, ImageOps

    image = Image.open(source).convert("L")
    image = ImageOps.autocontrast(image, cutoff=0.5)
    image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    lut_r = [round(BLUE[0] + (255 - BLUE[0]) * (v / 255) ** 1.15) for v in range(256)]
    lut_g = [round(BLUE[1] + (255 - BLUE[1]) * (v / 255) ** 1.15) for v in range(256)]
    lut_b = [round(BLUE[2] + (255 - BLUE[2]) * (v / 255) ** 1.15) for v in range(256)]
    coloured = Image.merge("RGB", (image.point(lut_r), image.point(lut_g), image.point(lut_b)))
    coloured.save(target, quality=64, optimize=True, progressive=True)


def mark(source, target, size=256):
    """White mark on transparency: alpha from luminance, for the header plate."""
    from PIL import Image, ImageOps

    image = Image.open(source).convert("L")
    image = ImageOps.autocontrast(image, cutoff=1)
    # crop to the bright subject itself: the model leaves it small in a dark frame
    box = image.point(lambda v: 255 if v > 215 else 0).getbbox() or (0, 0, *image.size)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    half = max(box[2] - box[0], box[3] - box[1]) * 0.56
    image = image.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    alpha = image.point(lambda v: 0 if v < 80 else min(255, int((v - 80) * 1.5)))
    white = Image.new("L", image.size, 255)
    Image.merge("RGBA", (white, white, white, alpha)).save(target, "WEBP", quality=82)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--ref", required=True)
    gen.add_argument("--out", required=True)
    gen.add_argument("names", nargs="*")
    tone = sub.add_parser("duotone")
    tone.add_argument("raw")
    tone.add_argument("static")
    args = parser.parse_args()
    if args.command == "generate":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        keys = Keys(load_keys())
        ref = Path(args.ref).read_bytes()
        names = args.names or list(FRAMES)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            jobs = [pool.submit(generate, keys, name, *FRAMES[name], ref, out) for name in names]
            results = [job.result() for job in jobs]
        sys.exit(0 if all(results) else 1)
    raw, static = Path(args.raw), Path(args.static)
    static.mkdir(parents=True, exist_ok=True)
    for name, (ratio, _) in FRAMES.items():
        source = raw / f"{name}.png"
        if not source.exists():
            continue
        if name == "mark":
            mark(source, static / "mark.webp")
            continue
        size = (1000, 1000) if ratio == "1:1" else (1600, 900)
        duotone(source, static / f"{name}.jpg", size)
        print(f"{name}: {static / (name + '.jpg')}")


if __name__ == "__main__":
    main()
