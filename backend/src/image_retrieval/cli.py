from __future__ import annotations

import argparse
import json
import sys
import time

from .catalog import Catalog
from .config import load_config
from .service import ImageSearchService


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Index/search the current still-image dataset.")
    parser.add_argument("--config", help="Config JSON path, relative to dsreborn or absolute")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check files, Python and CUDA; no model download")
    build = commands.add_parser("index", help="Build/update embeddings; resumes cached images")
    build.add_argument("--rebuild", action="store_true", help="Ignore per-image embedding cache")
    search = commands.add_parser("search", help="Run a Vietnamese text query")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=20)
    search.add_argument("--batch", action="append", default=[])
    search.add_argument("--no-regions", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "doctor":
        import torch
        catalog = Catalog(config.data_root)
        print(json.dumps({
            "data_root": str(config.data_root), "image_count": len(catalog.photos), "batches": catalog.batches,
            "damaged_images": [p.image_id for p in catalog.photos if p.error],
            "model_id": config.model_id, "model_cache": str(config.cache_root),
            "region_mode": config.region_mode,
            "torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "note": "CUDA chưa khả dụng; chương trình sẽ dùng CPU." if not torch.cuda.is_available() else "CUDA sẵn sàng.",
        }, ensure_ascii=False, indent=2))
        return 0
    service = ImageSearchService(config)
    try:
        if args.command == "search":
            if not 1 <= args.top_k <= 500:
                parser.error("--top-k must be between 1 and 500")
            print(json.dumps(service.search(args.query, args.top_k, args.batch, not args.no_regions),
                             ensure_ascii=False, indent=2))
            return 0
        service.start_build(args.rebuild)
        previous = None
        while True:
            status = service.status()
            progress = status["build"]
            key = (progress["state"], progress["processed"], progress["message"])
            if key != previous:
                print(progress["message"], flush=True)
                previous = key
            if progress["state"] != "running":
                return 0 if progress["state"] == "complete" else 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping; cached embeddings will be reused on the next run.", flush=True)
        return 130
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
