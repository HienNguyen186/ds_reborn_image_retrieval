from __future__ import annotations

import os
import threading

import numpy as np

from .config import Config


class SiglipEncoder:
    """Lazy multilingual image/text encoder; no external translation service."""

    def __init__(self, config: Config):
        import torch
        from transformers import AutoModel, AutoProcessor

        self.torch = torch
        if config.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA không khả dụng. Cài PyTorch có CUDA hoặc đặt device='cpu'.")
        self.device = "cuda" if config.device != "cpu" and torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" and config.precision != "fp32" else torch.float32
        if self.device == "cpu":
            torch.set_num_threads(min(8, os.cpu_count() or 1))
        config.cache_root.mkdir(parents=True, exist_ok=True)
        options = dict(cache_dir=str(config.cache_root), revision=config.revision)
        # Prefer an already downloaded snapshot, including while offline. The
        # Hub otherwise retries HEAD requests for optional processor files.
        try:
            self.processor = AutoProcessor.from_pretrained(config.model_id, local_files_only=True, **options)
        except OSError:
            if config.local_files_only:
                raise
            self.processor = AutoProcessor.from_pretrained(config.model_id, local_files_only=False, **options)
        try:
            self.model = AutoModel.from_pretrained(config.model_id, torch_dtype=self.dtype, local_files_only=True, **options)
        except OSError:
            if config.local_files_only:
                raise
            self.model = AutoModel.from_pretrained(config.model_id, torch_dtype=self.dtype, local_files_only=False, **options)
        if self.model.config.model_type not in {"siglip", "siglip2"}:
            raise ValueError("This adapter requires a SigLIP/SigLIP2 checkpoint.")
        self.model = self.model.to(self.device).eval()
        self.batch_size = config.batch_size
        self.max_length = self.model.config.text_config.max_position_embeddings
        self.last_query_truncated = False
        self._lock = threading.Lock()

    def _numpy(self, output):
        # Transformers 4 returns tensors; Transformers 5 can return ModelOutput.
        tensor = output if self.torch.is_tensor(output) else output.pooler_output
        return tensor.detach().float().cpu().numpy()

    def encode_images(self, images):
        chunks, offset = [], 0
        with self._lock, self.torch.inference_mode():
            while offset < len(images):
                size = min(self.batch_size, len(images) - offset)
                try:
                    inputs = self.processor(images=images[offset:offset + size], return_tensors="pt")
                    pixels = inputs["pixel_values"].to(self.device, dtype=self.dtype)
                    chunks.append(self._numpy(self.model.get_image_features(pixel_values=pixels)))
                    offset += size
                except self.torch.cuda.OutOfMemoryError as exc:
                    if size == 1:
                        raise RuntimeError("Không đủ VRAM kể cả batch=1. Đóng ứng dụng dùng GPU hoặc dùng CPU.") from exc
                    self.batch_size = max(1, size // 2)
                    self.torch.cuda.empty_cache()
        return np.concatenate(chunks, axis=0)

    def encode_text(self, text):
        with self._lock, self.torch.inference_mode():
            token_ids = self.processor.tokenizer(text, add_special_tokens=True)["input_ids"]
            self.last_query_truncated = len(token_ids) > self.max_length
            inputs = self.processor(text=[text], padding="max_length", truncation=True,
                                    max_length=self.max_length, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            return self._numpy(self.model.get_text_features(**inputs))
