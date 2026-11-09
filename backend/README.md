# Tìm ảnh — backend và giao diện xem ảnh lớn

Luồng mới xử lý ảnh tĩnh trong `data/Batch*/ảnh.jpg`. Giao diện đã thay trình phát video bằng xem ảnh gần toàn màn hình, zoom 100–400%, chuyển ảnh bằng phím mũi tên và duyệt ảnh theo batch. Lưới mặc định 3 cột dùng thumbnail 640 px; ảnh gốc được tải khi phóng to. Đăng nhập DRES và các công cụ tìm kiếm ảnh được giữ lại.

Bộ dữ liệu hiện được khảo sát có **5.000 ảnh JPG**: `Batch1` 1.853 ảnh, `Batch2` 1.767 ảnh, `Batch3` 1.380 ảnh. Ảnh lấy mẫu cùng góc camera trong bếp; các chi tiết người, màu áo, đồ vật, vị trí thường quan trọng hơn bối cảnh chung.

## Chạy

Từ thư mục gốc `dsreborn`:

```powershell
.\backend\run.ps1 -Mode doctor
.\backend\run.ps1 -Mode index
.\backend\run.ps1 -Mode build
.\backend\run.ps1 -Mode serve
```

Script nằm tại `backend/run.ps1`; nếu terminal đã đứng trong `backend`, dùng `.\run.ps1 -Mode ...` tương ứng.

`doctor` kiểm tra dữ liệu/PyTorch/CUDA, không tải model. `index` tạo hoặc tiếp tục index từ cache. `build` build giao diện gốc với địa chỉ API localhost, không sửa file nguồn hay `.env` của frontend. `serve` chạy API cùng frontend đã build tại **http://127.0.0.1:8000**.

Có thể phát triển backend với `.\backend\run.ps1 -Mode dev` và chạy `.\backend\run.ps1 -Mode frontend` trong terminal khác để mở frontend gốc tại **http://localhost:5173**. Launcher truyền `VITE_API_BASE_URL=http://127.0.0.1:8000` riêng cho tiến trình Vite vì `.env` hiện có đang trỏ đến server từ xa; không sửa file `.env`. Backend hỗ trợ CORS cho hai địa chỉ localhost/127.0.0.1 trên cổng 5173.

```powershell
.\backend\run.ps1 -Mode test
```

Lệnh trên chạy kiểm thử phần mềm bằng encoder giả, không cần tải checkpoint. Không dùng kết quả kiểm thử này để khẳng định chất lượng tìm kiếm trên đề thi.

Phụ thuộc gọn nằm trong `backend/requirements-image-search.txt`. Nếu tạo môi trường mới, từ `dsreborn`:

```powershell
python -m venv env
.\env\Scripts\python.exe -m pip install -r backend\requirements-image-search.txt
```

Môi trường hiện tại đã cài `torch 2.13.0+cu126` và `torchvision 0.28.0+cu126`; `doctor` nhận GPU NVIDIA T1200 4 GB và báo `cuda_available: true`. Cấu hình `device: auto` tự dùng CUDA/FP16. Nếu tạo lại môi trường, cài các phụ thuộc cơ bản trước rồi dùng bộ wheel đã ghi trong `backend/requirements-cuda.txt`:

```powershell
.\env\Scripts\python.exe -m pip install --force-reinstall --no-deps -r backend\requirements-cuda.txt
.\backend\run.ps1 -Mode doctor
```

Các phiên bản CUDA này theo [hướng dẫn PyTorch chính thức](https://pytorch.org/get-started/previous-versions/#v2130); máy có driver/GPU khác nên dùng [bộ chọn cài đặt](https://pytorch.org/get-started/locally/) phù hợp.

## Tạo và cập nhật index

Cấu hình mặc định: `backend/configs/images.json`. Đường dẫn tương đối tính từ `dsreborn`. Có thể chọn file khác bằng biến môi trường `IMAGE_SEARCH_CONFIG`, hoặc tùy chọn toàn cục CLI `--config` đặt trước tên lệnh.

| Khóa | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `model_id` | `google/siglip2-base-patch16-224` | SigLIP2 Base đa ngôn ngữ |
| `device` | `auto` | CUDA nếu PyTorch hỗ trợ, nếu không dùng CPU; có thể chọn `cpu`/`cuda` |
| `precision` | `auto` | FP16 trên CUDA, FP32 trên CPU |
| `batch_size` | `4` | Batch inference; tự giảm khi CUDA hết VRAM |
| `region_mode` | `grid` | Toàn ảnh và 4 crop cố định chồng lấn; `none` chỉ toàn ảnh |
| `data_root` | `data` | Quét đệ quy JPG/JPEG/PNG/WebP |
| `index_root` | `artifacts/image_search` | Index tổng và cache embedding |
| `cache_root` | `models` | Cache checkpoint/processor |
| `local_files_only` | `false` | Chỉ đặt `true` sau khi model đã được tải đủ nếu muốn dùng offline |

Lần đầu cần internet để tải model. Ảnh và câu tiếng Việt dùng hai encoder tương ứng của cùng checkpoint; không cần dịch vụ dịch thuật. `revision` trong cấu hình được ghim vào phiên bản checkpoint cụ thể để cache nhất quán.

`grid` tạo vector cho toàn ảnh và 4 vùng: trên trái, trên phải, dưới trái, dưới phải. Đây là crop cố định, **không phải phát hiện người/đồ vật**. Bản hiện tại chưa tự sinh caption hay trích OCR/ASR.

Vector được chuẩn hóa L2, tìm cosine chính xác bằng FAISS `IndexFlatIP` khi thư viện khả dụng, nếu không dùng NumPy. Kết quả được gộp theo ảnh gốc. Khi dùng vùng, điểm ảnh kết hợp 0,6 × điểm toàn ảnh + 0,4 × điểm vùng tốt nhất.

Cache nằm trong `artifacts/image_search/cache/<signature>`, index tổng là `artifacts/image_search/index.npz`. Chữ ký phụ thuộc model/revision/crop/precision; mỗi ảnh được kiểm tra bằng đường dẫn, kích thước file và mtime. Chạy lại tái sử dụng ảnh không đổi; đổi model hoặc sửa ảnh yêu cầu tạo index tương ứng. Index cuối chỉ được thay khi quá trình hoàn tất. Lỗi/gián đoạn giữ cache đã có để chạy tiếp.

Chỉ khi muốn buộc tính lại toàn bộ:

```powershell
.\backend\run.ps1 -Mode index -Rebuild
```

Không chạy nhiều tiến trình tạo index vào cùng thư mục. Sau khi thêm/thay ảnh, dừng server, chạy lại `index`, rồi mở lại server để nạp index mới. Ảnh hỏng được báo qua `doctor`/status; cần sửa trước khi lập index.

ID giữ đường dẫn tương đối, ví dụ `Batch1/08_1162.jpg`; `filename` giữ `08_1162.jpg`. Không đổi tên ảnh để lập index. Tiền tố tên file không được xem là thời gian video đã xác minh.

## API và frontend gốc

API docs tại **http://127.0.0.1:8000/docs**. Backend vẫn trả contract tương thích; các tên `video_id`/`frame_id` chỉ là định danh nhóm ảnh/tên file. Dùng **Semantic** hoặc **Auto** với mô tả ảnh; `AND` kết hợp các điều kiện trên cùng một ảnh. Các lựa chọn temporal/OCR/ASR chưa có dữ liệu được ẩn khỏi menu chính.

`aic` và `cam` là hai tên tương thích cùng trỏ đến **một bộ `data/Batch*` hiện tại**, không phải hai nguồn dữ liệu khác nhau; mặc định dùng `aic`.

| API tương thích frontend gốc | Hành vi cho bộ ảnh hiện tại |
| --- | --- |
| `GET /api/health`, `/api/config` | Kiểm tra backend và cấu hình dành cho giao diện gốc |
| `GET /api/search/models` | Các tên model tương thích của model đã cấu hình |
| `GET /api/video-ids` | Nhóm ID dạng `Batch1/08`, dùng để lọc ảnh |
| `POST /api/search` | Semantic/Auto và các điều kiện `AND` trên cùng ảnh |
| `POST /api/similarity-search` | Tìm ảnh tương tự theo ID trong contract cũ |
| `GET /api/frame-info` | Thông tin và URL ảnh gốc |
| `GET /api/surrounding-frames` | Ảnh có hậu tố gần nhất khi sắp xếp số trong cùng nhóm, không khẳng định thời gian |
| `POST /api/search/fusion` | Kết hợp các nhánh semantic; không có OCR/ASR |
| `POST /api/search/color` | Tìm theo 25 ô màu trên ảnh thật; tự tạo cache màu, không cần index embedding |
| `POST /api/search/multimodal` | Kết hợp mô tả và ảnh đính kèm bằng cùng encoder; tối đa 8 ảnh, 8 MB/ảnh |

Ví dụ `08_1002.jpg` trong `Batch1` được ánh xạ thành `video_id: "Batch1/08"`, `frame_id: 1002` để UI cũ nhận dạng; đây chỉ là **ID**, không xác minh ảnh thuộc video hoặc vị trí thời gian nào. `timestamp` để `null`, URL video/map để trống. Tên file gốc và `image_id` vẫn được giữ.

Temporal/`THEN`, OCR, ASR và rerank VLM chưa được hỗ trợ bởi luồng ảnh này; các yêu cầu tương ứng trả lỗi 501 rõ ràng. Các nút vẫn hiện trong frontend gốc. Tìm theo màu là so khớp màu chủ đạo từng ô; tìm multimodal là phối hợp vector, không phải VLM xác minh hành động.

### Đăng nhập DRES

`POST /api/dres/login` đã được bật cho `https://dres.2hbread.com`. Địa chỉ và tên tài khoản mặc định đặt trong `backend/configs/dres.json`; mật khẩu không được lưu vào mã nguồn hoặc bản build. Launcher `-Mode build` / `-Mode frontend` truyền các mặc định này cho giao diện cũ, không sửa `.env`.

Mở **Settings → DRES Submission**, kiểm tra DRES URL và Team ID, nhập mật khẩu rồi bấm **Login DRES**. Backend trả session theo contract cũ và chọn evaluation có trạng thái ACTIVE nếu có. Session ở bộ nhớ giao diện, tải lại trang cần đăng nhập lại. Có thể dán cả URL `/evaluation/list`; backend tự lấy địa chỉ gốc.

Đăng nhập website DRES trong trình duyệt và đăng nhập qua ứng dụng là hai session riêng. Mật khẩu chỉ nhập ở Settings, không được ghi vào file cấu hình hoặc bản build.

### Nộp ảnh KIS lên DRES

1. Đăng nhập DRES trong Settings; giữ God Mode tắt để nộp trực tiếp tới máy chủ đã cấu hình.
2. Tìm ảnh, bấm **Queue** để đưa vào hàng đợi. Chọn đúng một ảnh bằng nút radio nếu có nhiều ảnh.
3. Bấm **Kiểm tra payload DRES** để xem tên media, task và JSON thực tế. Bước này không gửi đáp án.
4. Bấm **Submit tên_ảnh.jpg** để nộp ảnh được chọn; nút Submit trên thẻ kết quả cũng nộp đúng ảnh đó.

Backend đối chiếu `image_id` với catalog local và đọc evaluation ACTIVE/current task. Không sử dụng `frame_idx`, timestamp hoặc nhóm `Batch1/08` làm tên media.

Theo `DRES_HuongDan_Castle5000.pdf` của BTC (mục 2 và 7), tên ảnh trên DRES lấy theo cột `imageID` trong metadata: bỏ đuôi `.jpg` và thêm tiền tố **`day1_Kitchen_`**. Collection luôn là **`castle5000`**. Vì vậy `09_1573.jpg` phải nộp thành `day1_Kitchen_09_1573`; nộp `09_1573` hoặc `09_1573.jpg` sẽ gây lỗi “Could not find media item”. Tiền tố chỉ được thêm một lần nếu tên ảnh đã có sẵn.

Cấu hình trong `backend/configs/dres.json`:

```json
{
  "base_url": "https://dres.2hbread.com",
  "username": "DSReborn_NguyenHien",
  "metadata_mode": "participant",
  "media_name_format": "stem",
  "media_name_prefix": "day1_Kitchen_",
  "collection_name": "castle5000"
}
```

Không lưu mật khẩu hoặc session vào file này. Thay đổi lần này chỉ ở backend: dừng server cũ bằng **Ctrl+C** trong terminal đang chạy rồi chạy lại `.\backend\run.ps1 -Mode serve` từ `dsreborn`. Không cần tạo lại index hoặc build frontend. Launcher sẽ giữ nguyên server đang chạy nếu cổng 8000 đã được backend chiếm, nên cần dừng server cũ trước khi khởi động lại.

Preview kiểm tra đăng nhập/task và JSON, nhưng không xác nhận ảnh tồn tại trong catalog DRES khi dùng tài khoản PARTICIPANT; điều đó được server xác thực khi nhận submission. API collection chỉ dành cho ADMIN. Tùy chọn `metadata_mode: "admin"` dành cho tài khoản có quyền đọc collection; tài khoản thi dùng `participant` với quy tắc tên và collection do BTC công bố ở trên.

`POST /api/dres/submit/preview` chỉ đọc metadata và trả payload; `POST /api/dres/submit` gửi một ảnh KIS với JSON theo hướng dẫn Castle5000:

```json
{
  "answerSets": [{
    "answers": [{
      "mediaItemName": "day1_Kitchen_09_1573",
      "mediaItemCollectionName": "castle5000"
    }]
  }]
}
```

Không cần `taskId` hoặc `taskName`: DRES gắn đáp án vào task đang chạy. Payload ảnh không có `start/end` hay timestamp video. API nộp thật là `POST https://dres.2hbread.com/api/v2/submit/<EVALUATION_ID>?session=<SESSION_ID>`. Các phép preview và kiểm thử phần mềm không chứng minh một bài đã được máy chủ chấm thành công. Sau khi preview đúng tên và collection, chỉ bấm Submit cho ảnh bạn chọn làm đáp án; không nộp thử nhiều định dạng trong task đang thi vì mỗi bài sai bị phạt điểm.

Kết quả phân biệt correct/wrong/pending/rejected/error. HTTP 412 là bị bộ lọc từ chối (ví dụ trùng đáp án), không tự coi là Wrong. Khi timeout sau POST, kết quả là unknown và không tự gửi lại; kiểm tra lịch sử DRES trước khi bấm Submit lần nữa. Request có `request_id` được chống gửi trùng trong 5 phút tại tiến trình backend; cơ chế này không phải lưu trữ bền vững qua restart.

API ảnh phục vụ kiểm tra và quản lý index:

| Phương thức | Endpoint | Nội dung |
| --- | --- | --- |
| `GET` | `/api/status` | Số ảnh, batch, model/device, sẵn sàng index, tiến độ và lỗi |
| `GET` | `/api/images?batch=Batch1&offset=0&limit=60` | Duyệt ảnh; bỏ `batch` để duyệt tất cả |
| `GET` | `/api/image/Batch1/08_1162.jpg` | Trả ảnh gốc theo ID đã được catalog phát hiện |
| `POST` | `/api/index/build` | Tạo/cập nhật index nền; body `{"rebuild": false}` dùng lại cache |
| `POST` | `/api/search` | Tìm mô tả; nhận body của frontend gốc và phản hồi theo contract tương thích |
| `POST` | `/api/similar` | Tìm tương tự bằng `image_id` đã có trong index |

`POST /api/index/build` trả 202. Theo dõi `build.state` (`idle`, `running`, `complete`, `failed`), `processed`, `total`, `message` qua `/api/status`. Không có index phù hợp thì tìm trả 503 kèm hướng dẫn cập nhật.

Tìm trực tiếp bằng CLI từ thư mục `backend`:

```powershell
..\env\Scripts\python.exe -m src.image_retrieval.cli search "Người mặc áo xanh đang cầm bát" --top-k 20 --batch Batch1
```

Thêm `--no-regions` để chỉ dùng toàn ảnh. `top-k` từ 1 đến 500. Response có ảnh gốc, ID, tên file, điểm và vùng khớp; mô tả quá dài có thể bị cắt theo giới hạn token và có `warnings` trong API. Không giả định frontend gốc hiển thị mọi trường bổ sung của backend.

## Kiểm thử và giới hạn

Từ thư mục `backend`:

```powershell
..\env\Scripts\python.exe -m unittest discover -s tests -p "test_image*.py" -v
```

54 kiểm thử backend đã đạt, bao gồm submit ảnh cho tài khoản PARTICIPANT, chống gửi trùng, preview không nộp thật, phân loại verdict, và các chức năng tìm ảnh/cache. Frontend có `npm run test:submission` kiểm tra hồi quy lỗi `frame_idx=0` và không đưa timestamp vào đáp án ảnh. Đã đo tìm kiếm với mô hình thật/index đầy đủ 5.000 ảnh trên T1200.

Để đánh giá chất lượng, chuẩn bị truy vấn tiếng Việt có đáp án rồi đo Recall@10/Recall@100. Hiện đã có index 5.000 ảnh; các phép đo tốc độ không khẳng định chất lượng retrieval. Một ảnh tĩnh có thể không phân biệt chắc chắn các hành động như bắt đầu rửa, vừa đặt xuống hoặc chuẩn bị cầm.

## Tối ưu latency

`preload_model: true` trong `configs/images.json` nạp model và làm nóng CUDA trước khi server sẵn sàng. Khởi động vẫn mất vài giây nhưng truy vấn đầu không còn phải trả thêm thời gian tải model. Không cần tạo lại index vì thay đổi này.

Xếp hạng dùng tích ma trận chính xác trên 25.000 vector (5 vùng × 5.000 ảnh), gộp điểm bằng NumPy và chỉ dựng metadata cho top-k. Cache tối đa 256 embedding câu truy vấn; đổi bộ lọc/top-k vẫn tính lại kết quả. Cache thumbnail nằm trong `artifacts/image_search/thumbnails` và tách theo file/thời gian sửa/size.

Đo thử trên máy này: xếp hạng từ khoảng 100 ms xuống 3 ms, truy vấn mới sau warmup từ 154–158 ms xuống khoảng 46 ms, query lặp lại khoảng 3–4 ms. Đây là thời gian backend; tổng thời gian trình duyệt còn gồm mạng, thumbnail và render. Số liệu có thể thay đổi theo độ dài query, số mệnh đề AND và tải máy.

Mặc định `main:app` chạy backend ảnh mới. Entry point `src.api.main:app` cũng là wrapper của backend ảnh mới để tương thích lệnh khởi chạy trước đây. Bootstrap video cũ được giữ tại `src.api.video_main:app`; các cấu hình/phụ thuộc riêng của hệ thống video cũ không nằm trong luồng tối giản này.

