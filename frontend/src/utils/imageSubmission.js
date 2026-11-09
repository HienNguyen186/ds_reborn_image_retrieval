// A still image's identifier comes from its filename, never a video frame index.
export function imageAnswer(item) {
  return {
    image_id: item.image_id || item.raw?.image_id || item.path,
    video_id: item.video_id,
    frame_id: Number(item.frame_id ?? item.raw?.keyframe_id_int ?? 0),
  };
}
