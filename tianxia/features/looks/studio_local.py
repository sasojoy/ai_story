"""本機生圖（功能包 looks；studio.py 是流程、studio_api.py 是雲端那兩家）：用這台機器上的 ComfyUI 跑 FLUX.2 klein 4B。

為什麼要有這一支（企劃者 2026-11-02）：雲端的 Nano Banana 一套形象燒了 56 次生圖、最後還差一張；同一天用 klein 在這台
產四套，十張全數通過機器驗收。單張 12～24 秒、不要錢，所以**重畫可以放寬**（TRIES＝10）——雲端的 MAX_TRIES＝3 是
照「每畫一次都付錢」定的，本機沒有這個限制，而重畫上限正是「一套裡有幾張會停下來等管理者」的關鍵。

顯卡是唯一要小心的地方：klein 要 9～10 GiB，`gemma4:12b` 要 9.1 GiB，這張卡只有 12.2 GiB，兩個同時常駐放不下。
2026-11-02 實測可行的條件是**省電模式**（`keep_alive` 5 分鐘、小模型 gemma3:4b）：沒人講話時 Ollama 不佔卡，klein 等於獨佔；
那天 13:00～15:18 有真人在線、klein 佔著卡，`server_err.log` 一次模型失敗都沒有。所以 run_studio.py 預設
**只在省電模式開著時才動工**（`--anytime` 可以蓋過去）。

ComfyUI（主機端，不進版控）：
- 裝在 C:\\ComfyUI，自己的 .venv；啟動 `.venv/Scripts/python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch`
- 模型三個檔放在 `models/`（Hugging Face `Comfy-Org/flux2-klein-4B` 的 `split_files/`，合計約 12 GB）：
  `diffusion_models/flux-2-klein-4b.safetensors`、`text_encoders/qwen_3_4b_fp4_flux2.safetensors`、`vae/flux2-vae.safetensors`
- 環境變數：`TIANXIA_COMFY_URL`（預設 http://127.0.0.1:8188）、`TIANXIA_COMFY_STEPS`（預設 4）

節點圖照 2026-11-02 實際跑出四套形象的那一份（`Flux2Scheduler` ＋ `BasicGuider` ＋ 參考圖各縮到 1 MP 後用
`ReferenceLatent` 串接）；參考圖走 ComfyUI 的上傳 API，不碰它的資料夾。
"""
from __future__ import annotations

import io
import json
import os
import random
import time

import requests
from PIL import Image

from .studio import PaintBusy

URL_ENV, STEPS_ENV = "TIANXIA_COMFY_URL", "TIANXIA_COMFY_STEPS"
DEFAULT_URL, DEFAULT_STEPS = "http://127.0.0.1:8188", 4
TRIES = 10  # 本機重畫不要錢：上限拉高（實測 40 張裡，上限 3 只有 34 張過、上限 10 有 37 張過）
UNET, CLIP, VAE = "flux-2-klein-4b.safetensors", "qwen_3_4b_fp4_flux2.safetensors", "flux2-vae.safetensors"
# 長寬比 → 畫布（studio.ASPECT 送進來的那幾種；都約 1 MP，klein 的甜蜜點）
SIZES = {"4:1": (2048, 512), "21:9": (1536, 512), "3:2": (1248, 832), "16:9": (1536, 768), "3:4": (896, 1152), "1:1": (1024, 1024)}


def _flat_png(data: bytes) -> bytes:
    """參考圖鋪白、轉 PNG（klein 畫的也是白底；透明送過去會變成黑的）。"""
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    base = Image.new("RGBA", im.size, (255, 255, 255, 255))
    base.alpha_composite(im)
    out = io.BytesIO()
    base.convert("RGB").save(out, "PNG")
    return out.getvalue()


class LocalPainter:
    """這台機器上的 ComfyUI：一段提示詞＋幾張參考圖 → 一張圖（bytes）。介面同 GeminiPainter。"""

    tries = TRIES

    def __init__(self, url: str | None = None, steps: int | None = None, session=None,
                 timeout: float = 30.0, wait: float = 300.0, sleep: float = 1.0):
        self.url = (url or os.environ.get(URL_ENV, "") or DEFAULT_URL).rstrip("/")
        self.steps = steps or _int_env(STEPS_ENV, DEFAULT_STEPS)
        self.session = session or requests.Session()
        self.timeout = timeout  # 單一次 HTTP
        self.wait = wait  # 一張最多等多久（12～24 秒是常態；冷啟動載模型要久一點）
        self.sleep = sleep
        self.model = f"klein（本機 ComfyUI {self.url}）"  # 主控台那一行印得出來

    # ── HTTP ──
    def _post(self, path: str, body: dict) -> dict:
        r = self.session.post(f"{self.url}{path}", json=body, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _upload(self, data: bytes) -> str:
        """把參考圖丟進 ComfyUI 的 input（回它給的檔名）。"""
        name = f"tianxia_{random.randrange(16 ** 8):08x}.png"
        r = self.session.post(f"{self.url}/upload/image", timeout=self.timeout,
                              files={"image": (name, data, "image/png")}, data={"overwrite": "true"})
        r.raise_for_status()
        got = r.json()
        return f"{got.get('subfolder')}/{got['name']}" if got.get("subfolder") else got["name"]

    def graph(self, prompt: str, refs: list[str], w: int, h: int, seed: int) -> dict:
        """2026-11-02 跑出四套形象的那一份節點圖（refs 是已經上傳的檔名，順序＝姿勢表、定裝照）。"""
        g: dict = {
            "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
            "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "flux2", "device": "default"}},
            "vae": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
            "pos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}},
            "guider": {"class_type": "BasicGuider", "inputs": {"model": ["unet", 0], "conditioning": ["pos", 0]}},
            "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "sched": {"class_type": "Flux2Scheduler", "inputs": {"steps": self.steps, "width": w, "height": h}},
            "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
            "empty": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
            "run": {"class_type": "SamplerCustomAdvanced",
                    "inputs": {"noise": ["noise", 0], "guider": ["guider", 0], "sampler": ["sampler", 0],
                               "sigmas": ["sched", 0], "latent_image": ["empty", 0]}},
            "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["run", 0], "vae": ["vae", 0]}},
            "save": {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": "tianxia"}},
        }
        cond = ["pos", 0]
        for i, name in enumerate(refs):
            g[f"li{i}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
            g[f"sc{i}"] = {"class_type": "ImageScaleToTotalPixels",
                           "inputs": {"image": [f"li{i}", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1}}
            g[f"en{i}"] = {"class_type": "VAEEncode", "inputs": {"pixels": [f"sc{i}", 0], "vae": ["vae", 0]}}
            g[f"rf{i}"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": cond, "latent": [f"en{i}", 0]}}
            cond = [f"rf{i}", 0]
        g["guider"]["inputs"]["conditioning"] = cond
        return g

    def paint(self, prompt: str, images: list[bytes], aspect: str, size: str) -> bytes:  # noqa: ARG002  size 是雲端的畫質檔位
        w, h = SIZES.get(aspect, SIZES["1:1"])
        try:
            refs = [self._upload(_flat_png(img)) for img in images]
            pid = self._post("/prompt", {"prompt": self.graph(prompt, refs, w, h, random.randrange(2 ** 31))})["prompt_id"]
            return self._fetch(self._wait(pid))
        except (requests.RequestException, OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            # ComfyUI 沒開、忙不過來、節點圖對不上：這一張不算，下一輪再來（同雲端那邊忙的處理）
            raise PaintBusy(f"{type(exc).__name__}：{exc}") from exc

    def _wait(self, pid: str) -> dict:
        """等這一張畫完，回 history 裡那一筆的 outputs。"""
        end = time.monotonic() + self.wait
        while time.monotonic() < end:
            got = self.session.get(f"{self.url}/history/{pid}", timeout=self.timeout).json().get(pid)
            status = (got or {}).get("status") or {}
            if status.get("completed"):
                return got["outputs"]["save"]["images"][0]
            if status.get("status_str") == "error":
                msgs = [m[1].get("exception_message", "") for m in status.get("messages", []) if m[0] == "execution_error"]
                raise ValueError(str(msgs)[:300] or "ComfyUI 跑不起來")
            time.sleep(self.sleep)
        raise TimeoutError(f"等了 {self.wait:.0f} 秒還沒畫好")

    def _fetch(self, image: dict) -> bytes:
        r = self.session.get(f"{self.url}/view", timeout=self.timeout,
                             params={"filename": image["filename"], "subfolder": image.get("subfolder", ""),
                                     "type": image.get("type", "output")})
        r.raise_for_status()
        return r.content


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default
