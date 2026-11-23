import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Send, X } from "lucide-react";
import "../image-viewer.css";

export default function ImageViewer({
  open,
  result,
  items = [],
  onClose,
  onNavigate,
  onDirectSubmit,
  submitting = false,
  layer = 1,
}) {
  const [answer, setAnswer] = useState("");
  const panel = useRef(null);
  const key = result?.image_url;
  const choices = useMemo(() => [...new Map(items.filter(Boolean).map(item => [item.image_url, item])).values()], [items]);
  const index = choices.findIndex(item => item.image_url === key);
  const navigation = useRef(null);
  useEffect(() => { navigation.current = { choices, index, onNavigate }; }, [choices, index, onNavigate]);
  const move = (delta) => { if (choices[index + delta]) onNavigate?.(choices[index + delta]); };
  useEffect(() => {
    if (!open) return;
    const oldFocus = document.activeElement;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    const handleKey = event => {
      if (event.key === "Escape") onClose();
      const editing = event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement;
      if (!editing && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
        const state = navigation.current;
        const next = state.choices[state.index + (event.key === "ArrowLeft" ? -1 : 1)];
        event.preventDefault();
        if (next) state.onNavigate?.(next);
      }
      if (event.key === "Tab") {
        const qaInput = panel.current.querySelector("#image-viewer-answer:not(:disabled)");
        const submitButton = panel.current.querySelector(".image-viewer-submit:not(:disabled)");
        const navigationButtons = [...panel.current.querySelectorAll(".image-viewer-navigation button:not(:disabled)")];
        const closeButton = panel.current.querySelector("header button:not(:disabled)");
        const tabStops = [qaInput, submitButton, ...navigationButtons, closeButton].filter(Boolean);
        const currentIndex = tabStops.indexOf(document.activeElement);
        const nextIndex = currentIndex === -1
          ? (event.shiftKey ? tabStops.length - 1 : 0)
          : (currentIndex + (event.shiftKey ? -1 : 1) + tabStops.length) % tabStops.length;
        event.preventDefault();
        tabStops[nextIndex]?.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => { document.body.style.overflow = oldOverflow; document.removeEventListener("keydown", handleKey); oldFocus?.focus(); };
  }, [open, onClose]);
  if (!open || !result) return null;
  const filename = result.frame_name || result.filename || result.raw?.filename || result.path;
  function submit(event) {
    event.preventDefault();
    if (!onDirectSubmit || submitting) return;
    const text = answer.trim();
    onDirectSubmit(result, { task: text ? "qa" : "kis", answer: text });
  }
  return <div className="image-viewer-backdrop" style={{ zIndex: 20000 + layer }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="image-viewer" ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="image-viewer-title">
      <header><div><h2 id="image-viewer-title">{filename}</h2><small>{result.path || result.image_id}</small></div><button onClick={onClose} aria-label="Đóng ảnh lớn"><X /></button></header>
      <div className="image-viewer-content">
        <div className="image-viewer-stage">
          <img src={result.image_url} alt={filename} />
        </div>
        <aside className="image-viewer-tools" aria-label="Điều khiển ảnh và submit">
          <div className="image-viewer-navigation">
            <button disabled={index <= 0} onClick={() => move(-1)} aria-label="Ảnh trước"><ArrowLeft /></button>
            <button disabled={index < 0 || index >= choices.length-1} onClick={() => move(1)} aria-label="Ảnh tiếp"><ArrowRight /></button>
          </div>
          <form className="image-viewer-submit-form" onSubmit={submit}>
            <label htmlFor="image-viewer-answer">Câu trả lời (QA, nếu có)</label>
            <textarea
              id="image-viewer-answer"
              value={answer}
              onChange={event => setAnswer(event.target.value)}
              placeholder="Để trống nếu chỉ nộp ảnh KIS"
              rows={4}
              maxLength={4000}
            />
            <small>Để trống để submit ảnh KIS; nhập câu trả lời để submit QA.</small>
            <button className="image-viewer-submit" type="submit" disabled={!onDirectSubmit || submitting}>
              <Send size={16} />{submitting ? "Đang submit..." : answer.trim() ? "Submit QA" : "Submit ảnh"}
            </button>
          </form>
        </aside>
      </div>
    </section>
  </div>;
}
