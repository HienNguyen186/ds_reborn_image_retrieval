import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import "../image-viewer.css";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
export default function ImageBrowser({ open, onClose, onOpenImage }) {
  const panel = useRef(null);
  const [page, setPage] = useState(0), [batch, setBatch] = useState("");
  const [data, setData] = useState({ items: [], total: 0 });
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    async function load() {
      setBusy(true); setError("");
      try {
        const response = await fetch(`${API}/api/images?offset=${page*36}&limit=36&batch=${encodeURIComponent(batch)}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Không tải được bộ ảnh");
        const value = await response.json();
        if (!controller.signal.aborted) setData(value);
      } catch (failure) { if (!controller.signal.aborted) setError(failure.message); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    }
    void load(); return () => controller.abort();
  }, [open, page, batch]);
  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector("select")?.focus();
    const handler = event => {
      if (document.querySelector(".image-viewer")) return;
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const targets = [...panel.current.querySelectorAll("button:not(:disabled), select")];
        if (event.shiftKey && document.activeElement === targets[0]) { event.preventDefault(); targets.at(-1)?.focus(); }
        else if (!event.shiftKey && document.activeElement === targets.at(-1)) { event.preventDefault(); targets[0]?.focus(); }
      }
    };
    document.addEventListener("keydown", handler);
    return () => { document.removeEventListener("keydown", handler); document.body.style.overflow = previousOverflow; previousFocus?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  const photos = data.items.map(item => ({ ...item, id: item.image_id, path: item.image_id, frame_name: item.filename, image_url: API + item.image_url, thumbnail_url: API + item.thumbnail_url }));
  return <div className="image-browser-backdrop"><section className="image-browser" ref={panel} role="dialog" aria-modal="true" aria-label="Duyệt bộ ảnh">
    <header><h2>Duyệt ảnh</h2><select value={batch} onChange={event => { setBatch(event.target.value); setPage(0); }} aria-label="Batch ảnh"><option value="">Tất cả batch</option>{[1,2,3].map(i=><option key={i}>Batch{i}</option>)}</select><button onClick={onClose} aria-label="Đóng bộ ảnh"><X /></button></header>
    {error && <p role="alert">{error}</p>}<p role="status">{busy ? "Đang tải…" : `${data.total} ảnh · trang ${page+1}`}</p>
    <div className="image-browser-grid">{photos.map(item=><button key={item.id} onClick={()=>onOpenImage(item, photos)}><img src={item.thumbnail_url} alt={item.filename} loading="lazy" decoding="async" /><span>{item.filename}</span></button>)}</div>
    <footer><button disabled={page === 0 || busy} onClick={()=>setPage(value=>value-1)}><ArrowLeft />Trước</button><button disabled={(page+1)*36>=data.total || busy} onClick={()=>setPage(value=>value+1)}>Tiếp<ArrowRight /></button></footer>
  </section></div>;
}
