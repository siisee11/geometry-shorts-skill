"""Emblem art for territory fills, made with Qwen-Image on a local ComfyUI (http://127.0.0.1:8188). The picture is
painted on the fill colour itself, so it drops straight onto the territory with no keying. Any image model works the
same way; the prompt and the flat background colour are what matter.

    python3 scripts/emblem_gen.py <out_dir> <name> "<prompt>" [--seeds 1,2,3,4] [--size 1024]
    -> <out_dir>/<name>_s<seed>.png
"""
import argparse
import json
import os
import time
import urllib.request

API = os.environ.get('COMFY', 'http://127.0.0.1:8188')
NEGATIVE = ('text, letters, watermark, signature, frame, border, photo, 3d render, gradient background, shadow, '
            'texture noise, blurry, low quality')


def call(path, data=None):
    req = urllib.request.Request(API + path, data=data, headers={'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def workflow(prompt, seed, size, steps=40, cfg=4.0):
    return {
        '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'qwen_image_2.1_int8_convrot.safetensors', 'weight_dtype': 'default'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'qwen3vl_8b_int8_convrot.safetensors', 'type': 'qwen_image', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'qwen_image_2.1_vae_bf16.safetensors'}},
        '4': {'class_type': 'TextEncodeQwenImage21', 'inputs': {'clip': ['2', 0], 'prompt': prompt, 'negative_prompt': NEGATIVE,
              'resolution': size, 'vae': ['3', 0]}},
        '8': {'class_type': 'EmptyImage', 'inputs': {'width': size, 'height': size, 'batch_size': 1, 'color': 0}},
        '9': {'class_type': 'VAEEncode', 'inputs': {'pixels': ['8', 0], 'vae': ['3', 0]}},
        '5': {'class_type': 'KSampler', 'inputs': {'model': ['1', 0], 'seed': seed, 'steps': steps, 'cfg': cfg,
              'sampler_name': 'euler', 'scheduler': 'simple', 'positive': ['4', 0], 'negative': ['4', 1],
              'latent_image': ['9', 0], 'denoise': 1.0}},
        '6': {'class_type': 'VAEDecode', 'inputs': {'samples': ['5', 0], 'vae': ['3', 0]}},
        '7': {'class_type': 'SaveImage', 'inputs': {'images': ['6', 0], 'filename_prefix': f'emblem/emb_{seed}'}},
    }


def generate(prompt, seed, size):
    pid = json.loads(call('/prompt', json.dumps({'prompt': workflow(prompt, seed, size)}).encode()))['prompt_id']
    while True:
        h = json.loads(call(f'/history/{pid}'))
        if pid in h and h[pid].get('outputs'):
            img = next(iter(h[pid]['outputs'].values()))['images'][0]
            q = f"/view?filename={img['filename']}&subfolder={img['subfolder']}&type={img['type']}"
            return call(q)
        if pid in h and h[pid].get('status', {}).get('status_str') == 'error':
            raise RuntimeError(json.dumps(h[pid]['status'])[:400])
        time.sleep(2)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('out_dir')
    ap.add_argument('name')
    ap.add_argument('prompt')
    ap.add_argument('--seeds', default='1,2,3,4')
    ap.add_argument('--size', type=int, default=1024)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    for s in [int(x) for x in a.seeds.split(',')]:
        t0 = time.time()
        p = os.path.join(a.out_dir, f'{a.name}_s{s}.png')
        open(p, 'wb').write(generate(a.prompt, s, a.size))
        print(p, f'{time.time() - t0:.0f}s', flush=True)
