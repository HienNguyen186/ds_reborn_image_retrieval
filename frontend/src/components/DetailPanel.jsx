import { Copy, ExternalLink, FileImage, Info, Send, X, ZoomIn } from "lucide-react";
import "../image-viewer.css";

export default function DetailPanel({ result, onClose, onSubmit, onPreview }) {
  if (!result) return null;
  const filename = result.frame_name || result.raw?.filename || result.path;
  const imageId = result.raw?.image_id || result.image_id || result.path;
  const score = Number(result.similarity || 0);
  const copy = async value => { try { await navigator.clipboard.writeText(value); } catch { /* user can select the visible path */ } };
  return <aside className="detail-panel">
    <header className="detail-header"><h3><Info size={16} />Thông tin ảnh</h3><button className="detail-close-button" onClick={onClose} aria-label="Đóng thông tin ảnh"><X size={17} /></button></header>
    <button className="image-detail-open" onClick={()=>onPreview?.(result)} aria-label="Xem ảnh kích thước lớn"><img src={result.image_url} alt={filename} /></button>
    <div className="detail-actions">
      <button onClick={()=>onPreview?.(result)}><ZoomIn size={15} />Phóng to</button>
      <button onClick={()=>copy(filename)}><Copy size={15} />Tên ảnh</button>
      <button onClick={()=>copy(imageId)}><Copy size={15} />Mã ảnh</button>
      <a href={result.image_url} target="_blank" rel="noreferrer"><ExternalLink size={15} />Ảnh gốc</a>
      <button onClick={()=>onSubmit?.(result, "queue")}><Send size={15} />Thêm hàng đợi</button>
    </div>
    <div className="detail-section"><h4><FileImage size={14} /> {filename}</h4><p className="detail-path">{imageId}</p><p>Batch: {result.raw?.batch || "—"}</p><p>Độ tương đồng: {(score*100).toFixed(1)}%</p><p>{result.width && result.height ? `${result.width} × ${result.height} px` : ""}</p></div>
    {result.caption && <div className="detail-section"><h4>Mô tả</h4><p>{result.caption}</p></div>}
  </aside>;
}
