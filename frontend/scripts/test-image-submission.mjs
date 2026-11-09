import assert from "node:assert/strict";
import { imageAnswer } from "../src/utils/imageSubmission.js";

const source = { image_id: "Batch1/08_1115.jpg", video_id: "Batch1/08", frame_id: 1115,
  frame_idx: 0, timestamp: 12345, start: 100, end: 200, raw: { frame_idx: null } };
assert.deepEqual(imageAnswer(source), { image_id: "Batch1/08_1115.jpg", video_id: "Batch1/08", frame_id: 1115 });
assert.equal(imageAnswer({ ...source, image_id: undefined, raw: { image_id: source.image_id } }).image_id, source.image_id);
assert.equal(imageAnswer({ ...source, frame_id: undefined, raw: { keyframe_id_int: 1115 } }).frame_id, 1115);
assert.notEqual(imageAnswer(source).image_id, imageAnswer({ ...source, image_id: "Batch2/08_1115.jpg" }).image_id);
assert.deepEqual(Object.keys(imageAnswer(source)).sort(), ["frame_id", "image_id", "video_id"]);
console.log("PASS: image identity ignores frame_idx/timestamps, preserves batch and original suffix.");
