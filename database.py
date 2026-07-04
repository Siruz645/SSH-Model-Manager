import json
import os
import uuid
from typing import List, Dict, Any

CONFIG_FILE = "config.json"
HISTORY_FILE = "history.json"

DEFAULT_CONFIG = {
    "ssh": {
        "host": "",
        "port": 22,
        "username": "root",
        "password": "",
        "key_filename": ""
    },
    "api": {
        "civitai": "",
        "huggingface": ""
    },
    "comfy_root": ""
}

PRELOADED_HISTORY = [
    {
        "id": str(uuid.uuid4()),
        "name": "Flux.2 Klein 9B FP8",
        "url": "https://civitai.com/api/download/models/2606187?fileId=2493583",
        "filename": "flux-2-klein-9b-fp8.safetensors",
        "folder": "checkpoints"
    },
    {
        "id": str(uuid.uuid4()),
        "name": "WAI Illustrious SDXL v1.4.0",
        "url": "https://civitai.com/api/download/models/1761560",
        "filename": "waiIllustriousSDXL_v140.safetensors",
        "folder": "checkpoints"
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Z-Image Turbo BF16",
        "url": "https://huggingface.co/Z-Image/Turbo/resolve/main/z_image_turbo_bf16.safetensors",
        "filename": "z_image_turbo_bf16.safetensors",
        "folder": "checkpoints"
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Qwen 3 8B FP8 Mixed",
        "url": "https://huggingface.co/Qwen/Qwen3-8B/resolve/main/qwen_3_8b_fp8mixed.safetensors",
        "filename": "qwen_3_8b_fp8mixed.safetensors",
        "folder": "clip"
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Flux2 VAE",
        "url": "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors", 
        "filename": "flux2-vae.safetensors",
        "folder": "vae"
    },
    {
        "id": str(uuid.uuid4()),
        "name": "EVA02 CLIP L",
        "url": "https://huggingface.co/QuanSun/EVA-CLIP/resolve/main/EVA02_CLIP_L_336_psz14_s6B.pt",
        "filename": "EVA02_CLIP_L_336_psz14_s6B.pt",
        "folder": "clip"
    }
]


class Database:
    def __init__(self, base_dir="."):
        self.config_path = os.path.join(base_dir, CONFIG_FILE)
        self.history_path = os.path.join(base_dir, HISTORY_FILE)
        self.groups_path = os.path.join(base_dir, "groups.json")
        self._ensure_files()

    def _ensure_files(self):
        if not os.path.exists(self.config_path):
            self.save_config(DEFAULT_CONFIG)
        if not os.path.exists(self.history_path):
            self.save_history(PRELOADED_HISTORY)
        if not os.path.exists(self.groups_path):
            self.save_groups({})

    def load_groups(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            with open(self.groups_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_groups(self, groups: Dict[str, List[Dict[str, Any]]]):
        with open(self.groups_path, "w", encoding="utf-8") as f:
            json.dump(groups, f, indent=4)

    def load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_CONFIG

    def save_config(self, config: Dict[str, Any]):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    def load_logs(self) -> Dict[str, List[str]]:
        logs_path = os.path.join(os.path.dirname(self.config_path), "logs.json")
        try:
            with open(logs_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_logs(self, logs: Dict[str, List[str]]):
        logs_path = os.path.join(os.path.dirname(self.config_path), "logs.json")
        with open(logs_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4)

    def load_history(self) -> List[Dict[str, Any]]:
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return PRELOADED_HISTORY

    def save_history(self, history: List[Dict[str, Any]]):
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)

    def add_history_item(self, item: Dict[str, Any]):
        if "id" not in item:
            item["id"] = str(uuid.uuid4())
        history = self.load_history()
        # Avoid exact duplicates
        for h in history:
            if h.get("url") == item.get("url") and h.get("filename") == item.get("filename"):
                return
        history.append(item)
        self.save_history(history)

    def update_history_item(self, item_id: str, new_filename: str, new_folder: str):
        history = self.load_history()
        for h in history:
            if h.get("id") == item_id:
                h["filename"] = new_filename
                h["folder"] = new_folder
                break
        self.save_history(history)

    def delete_history_item(self, folder: str, filename: str):
        history = self.load_history()
        history = [h for h in history if not (h.get("folder") == folder and h.get("filename") == filename)]
        self.save_history(history)

    def update_history_item_url(self, folder: str, filename: str, new_url: str):
        history = self.load_history()
        for h in history:
            if h.get("folder") == folder and h.get("filename") == filename:
                h["url"] = new_url
                break
        self.save_history(history)

    def update_history_model_data(self, old_folder: str, filename: str, new_name: str, new_folder: str, new_url: str):
        history = self.load_history()
        found = False
        for h in history:
            if h.get("folder") == old_folder and h.get("filename") == filename:
                h["name"] = new_name
                h["folder"] = new_folder
                h["url"] = new_url
                found = True
                break
        if not found:
            import uuid
            history.append({
                "id": str(uuid.uuid4()),
                "name": new_name,
                "url": new_url,
                "filename": filename,
                "folder": new_folder
            })
        self.save_history(history)
