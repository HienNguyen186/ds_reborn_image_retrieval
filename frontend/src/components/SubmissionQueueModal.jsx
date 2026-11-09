import { useState } from "react";
import { GripVertical, SearchCheck, Send, Trash2, X } from "lucide-react";
import "../image-viewer.css";

const filename = item => item?.frame_name || item?.raw?.filename || item?.filename || item?.path || "";
export default function SubmissionQueueModal({ open, items, onClose, onChange, onSubmit, onPlay, onPreview, submitting }) {
  const [selectedId, setSelectedId] = useState(null);
  const [dragIndex, setDragIndex] = useState(null);
  const [preview, setPreview] = useState(null);
  const [checking, setChecking] = useState(false);
  const selected = items.find(item => item.queue_id === selectedId) || items[0];
  if (!open) return null;
  const verified = preview?.key === selected?.queue_id ? preview : null;
  async function check() {
    if (!selected || checking) return;
    const key = selected.queue_id;
    setChecking(true); setPreview(null);
    try { setPreview({ key, data: await onPreview(selected) }); }
    catch (error) { setPreview({ key, error: error.message }); }
    finally { setChecking(false); }
  }
  function move(from, to) {
    if (from == null || from === to) return;
    const next = [...items], [item] = next.splice(from, 1);
    next.splice(to, 0, item); onChange(next); setDragIndex(null);
  }
  return <div className="submission-queue-backdrop" onClick={onClose}>
    <section className="submission-queue-modal" role="dialog" aria-modal="true" aria-label="Nộp ảnh DRES" onClick={event => event.stopPropagation()}>
      <header><div><h2>Nộp ảnh DRES · KIS</h2><p>{items.length} ảnh trong hàng đợi · mỗi lần nộp một ảnh được chọn</p></div><button onClick={onClose} aria-label="Đóng hàng đợi"><X size={18} /></button></header>
      <div className="submission-queue-list">{items.map((item, index) => <article key={item.queue_id} className={selected?.queue_id === item.queue_id ? "is-selected" : ""} draggable onDragStart={()=>setDragIndex(index)} onDragOver={event=>event.preventDefault()} onDrop={()=>move(dragIndex,index)}>
        <input type="radio" name="dres-image" checked={selected?.queue_id === item.queue_id} onChange={()=>setSelectedId(item.queue_id)} aria-label={`Chọn ảnh ${filename(item)}`} />
        <GripVertical size={16} />
        <button className="submission-frame-preview" onClick={()=>onPlay?.(item)} aria-label={`Phóng to ${filename(item)}`}><img src={item.thumbnail_url || item.image_url} alt={filename(item)} /></button>
        <div><strong>{filename(item)}</strong><span>{item.image_id || item.raw?.image_id || item.path}</span></div>
        <button onClick={()=>onChange(items.filter(value=>value.queue_id !== item.queue_id))} aria-label={`Bỏ ${filename(item)}`}><Trash2 size={16} /></button>
      </article>)}</div>
      {!selected && <p className="submission-empty">Chọn ảnh từ kết quả tìm kiếm để thêm vào hàng đợi.</p>}
      {selected && <div className="submission-preview"><strong>Ảnh đang chọn: {filename(selected)}</strong><p>Kiểm tra task đang hoạt động và payload tên ảnh trước khi nộp.</p>
        <button onClick={check} disabled={checking || submitting}><SearchCheck size={16} />{checking ? "Đang kiểm tra…" : "Kiểm tra payload DRES"}</button>
        {verified?.error && <p role="alert" className="submission-validation-error">{verified.error}</p>}
        {verified?.data && <><p role="status">{verified.data.resolution === "metadata" ? "Đã đối chiếu" : "Tên ảnh theo cấu hình"}: {verified.data.media_item_name} · collection {verified.data.collection_name || "theo task DRES"} · task {verified.data.task_name}</p><pre>{JSON.stringify(verified.data.payload, null, 2)}</pre>{verified.data.warnings?.map(message=><p key={message}>{message}</p>)}<small>Chỉ kiểm tra, chưa nộp đáp án.</small></>}
      </div>}
      <footer><button disabled={!items.length || submitting} onClick={()=>onChange([])}>Xóa hàng đợi</button><button className="submission-send" disabled={!selected || submitting || checking} onClick={()=>onSubmit({ task: "kis", items: [selected], answer: "" })}><Send size={16} />{submitting ? "Đang nộp…" : `Submit ${selected ? filename(selected) : "ảnh"}`}</button></footer>
    </section>
  </div>;
}
