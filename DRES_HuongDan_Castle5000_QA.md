**Hướng dẫn sử dụng DRES** 

Cuộc thi tìm kiếm ảnh Castle5000 \- dành cho thành viên các team 

**1\. DRES là gì và một lượt thi diễn ra thế nào** 

**DRES** (Distributed Retrieval Evaluation Server) https\://github.com/dres-dev/DRES là máy  chủ dùng để tổ chức các cuộc thi tìm kiếm ảnh/video như VBS, LSC. Chức năng của Dres  là **phát câu hỏi**, **nhận bài nộp** và **chấm điểm**. 

Trong cuộc thi này, bộ dữ liệu là **5000 ảnh** camera tĩnh (Castle5000). Cuộc thi có **2 loại câu  hỏi (task)**: 

• **KIS** (Known-Item Search, tên task bắt đầu bằng KIS): câu hỏi là một mô tả bằng chữ về **một hoặc nhiều bức ảnh cho 1 sự kiện trong các ảnh (chỉ cần nộp 1 trong  các ảnh đúng sẽ được tính đúng)**; nhiệm vụ của team là tìm ra đúng ảnh đó và  nộp tên ảnh lên DRES càng nhanh càng tốt. 

• **QA** (Question & Answer, tên task bắt đầu bằng QA): câu hỏi hỏi về một chi tiết trong  các ảnh (ví dụ: có bao nhiêu người, đồ vật màu gì…); team tìm ảnh liên quan rồi nộp  **câu trả lời bằng chữ**. Câu trả lời do **trọng tài chấm**. 

Một lượt thi diễn ra như sau: 

1\. Ban tổ chức (BTC) bấm bắt đầu một task. Tất cả các team nhận cùng một câu hỏi  cùng lúc, đồng hồ bắt đầu đếm ngược (thường **5 phút**). 

2\. Thành viên mở trang **Viewer** trên DRES để đọc câu hỏi. (Trong cuộc thi trực tiếp thì  sẽ nhìn trên TV trên bảng) 

3\. Team dùng hệ thống của mình để tìm ảnh khớp với câu hỏi. 

4\. Team nộp bài lên DRES qua API: **tên ảnh** với task KIS (mục 7), **câu trả lời bằng  chữ** với task QA (mục 8). Task KIS được DRES chấm ngay; task QA chờ trọng tài  chấm. 

5\. Hết giờ, BTC chuyển sang task tiếp theo. Điểm được cộng dồn trên bảng xếp hạng. 

Lưu ý quan trọng: giao diện web của DRES **chỉ để xem câu hỏi và điểm**. Việc nộp bài  được thực hiện **bằng API** từ hệ thống/code của team (hoặc bằng lệnh curl, Postman…). 

**2\. Các thông số cần biết** 

Bảng dưới đây gom tất cả giá trị mà hệ thống của team cần dùng. Hãy điền sẵn chúng vào  file cấu hình (mục 6).

| Thông số  | Giá trị  | Ghi chú |
| :---- | :---- | :---- |
| Địa chỉ web DRES  | https\://dres.2hbread.com  | Mở bằng Chrome, Edge hoặc  Firefox. |
| Địa chỉ API  | https\://dres.2hbread.com/api/v2  | Dùng trong code. Mọi đường  dẫn API trong tài liệu đều bắt  đầu bằng địa chỉ này. |
| Username  | Ví dụ: UIA\_LeMinhQuan  | BTC gửi riêng cho từng   người. Không phân biệt chữ hoa/thường. |
| Password  | BTC gửi riêng  | **Có** phân biệt chữ hoa/thường.  Không chia sẻ cho team khác. |

Trang 1 

| Thông số  | Giá trị  | Ghi chú |
| :---- | :---- | ----- |
| Tên collection  | castle5000  | Tên bộ dữ liệu trên DRES.  Viết thường, đúng chính tả. |
| Tên ảnh khi nộp  (mediaItemName) | Ví dụ: day1\_Kitchen\_10\_1528  | Dùng cho task **KIS**. **Không  phải** tên file. Cách đổi xem  ngay bên dưới. |
| Câu trả lời (text)  | Ví dụ: 3  | Dùng cho task **QA**. Cách viết:  mục 8.4. |
| Loại task   (taskType) | LSC Known-Item Search hoặc LSC  Question & Answer Text | Code dùng để biết task đang  chạy là KIS hay QA (mục 6). |
| Evaluation ID  | Dạng xxxxxxxx-xxxx-xxxx-xxxx xxxxxxxxxxxx | Mã của buổi thi. Cách lấy:  mục 5\. |
| Session ID  | Chuỗi ký tự dài  | “Vé” chứng minh bạn đã đăng  nhập. Cách lấy: mục 4\. |

**Quy tắc đặt tên ảnh khi nộp (task KIS)** 

Ảnh trong thư mục dữ liệu có tên file dạng HH\_frame.jpg (ví dụ 10\_1528.jpg). Trên DRES,  mỗi ảnh được đặt tên theo cột **imageID** trong file metadata, tức là thêm tiền tố day1\_Kitchen\_ và bỏ đuôi .jpg: 

| Tên file trong thư mục  | Tên phải nộp lên DRES |
| :---- | :---- |
| 10\_1528.jpg  | day1\_Kitchen\_10\_1528 |
| 08\_102.jpg  | day1\_Kitchen\_08\_102 |
| 20\_3499.jpg  | day1\_Kitchen\_20\_3499 |

Nộp 10\_1528 hoặc 10\_1528.jpg sẽ bị DRES báo lỗi “Could not find media item”. Nếu hệ thống của team dùng sẵn cột **imageID** trong metadata thì nộp thẳng giá trị đó. 

**3\. Đăng nhập và xem câu hỏi trên web** 

**3.1. Đăng nhập** 

1\. Mở trình duyệt, vào **https\://dres.2hbread.com**. 

2\. Nhập **Username** và **Password** được BTC cung cấp, bấm **Login**. 

3\. Sau khi đăng nhập, bạn được chuyển tới trang **Evaluations** (danh sách các buổi  thi). 

**3.2. Trang Evaluations** 

Mỗi dòng là một buổi thi (evaluation). Các cột quan trọng: 

• **Run ID**: chính là **Evaluation ID**, cần dùng khi nộp bài. 

• **Name**: tên buổi thi. 

• **Status**: trạng thái. Chỉ buổi thi đang ở trạng thái **ACTIVE** mới nhận bài. • **Active Task** và **Time left**: task đang chạy và thời gian còn lại. 

**3.3. Xem câu hỏi (Viewer)** 

Ở cột **Actions**, bấm biểu tượng con mắt có chú thích “Go to evaluation viewer”. Trang  Viewer hiển thị:

Trang 2   
• Tên task (KIS… hoặc QA…) và câu hỏi dạng chữ của task hiện tại. 

• Đồng hồ đếm ngược thời gian còn lại. 

• Bảng điểm của các team. 

Trong lúc task đang chạy, kết quả nộp bài của các team khác được ẩn; bạn vẫn biết kết quả bài của team mình qua phản hồi API (mục 7 và 8). 

**4\. Lấy Session ID** 

Session ID là chuỗi ký tự DRES cấp sau khi bạn đăng nhập. Mỗi lần nộp bài đều phải gửi  kèm Session ID để DRES biết **ai** (và **team nào**) đang nộp. 

**Cách 1: Lấy trên giao diện web** 

1\. Đăng nhập trên web như mục 3.1. 

2\. Mở trang Profile tại **https\://dres.2hbread.com/user**. 

3\. Sao chép giá trị trong ô **SessionId**. 

**Cách 2: Lấy bằng API (khuyên dùng)** 

Gửi yêu cầu đăng nhập; DRES trả về JSON có trường sessionId. Với lệnh curl (chạy trên  macOS/Linux, hoặc Git Bash trên Windows): 

curl \-X POST "https\://dres.2hbread.com/api/v2/login" \\ 

 \-H "Content-Type: application/json" \\   
 \-d '{"username": "UIA\_LeMinhQuan", "password": "MAT\_KHAU\_CUA\_BAN"}' Kết quả trả về có dạng:   
{"id": "...", "username": "uia\_leminhquan", "role": "PARTICIPANT", 

"sessionId": "AbCdEf123..."} 

Session ID sẽ **hết hiệu lực** khi bạn đăng xuất hoặc khi máy chủ DRES khởi động lại. Khi  nộp bài nhận lỗi **401**, chỉ cần đăng nhập lại để lấy Session ID mới. Cách an toàn nhất là để code **tự đăng nhập** mỗi lần khởi động (mục 6). Không gửi Session ID cho người khác: ai  có nó đều nộp bài được dưới tên bạn. 

**5\. Lấy Evaluation ID** 

**Cách 1: Trên giao diện web** 

• Xem cột **Run ID** trên trang Evaluations, hoặc 

• Mở Viewer rồi nhìn thanh địa chỉ: phần cuối của .../evaluation/viewer/\<ID\> chính là  Evaluation ID. 

**Cách 2: Bằng API** 

curl "https\://dres.2hbread.com/api/v2/client/evaluation/list?session=SESSION\_ID\_CUA\_BAN" 

Kết quả là danh sách các buổi thi bạn được tham gia. Lấy trường id của buổi thi có  "status": "ACTIVE". 

**6\. Cài đặt: cấu hình hệ thống của team** 

Hệ thống tìm kiếm của team cần chức năng nộp bài (ví dụ một nút “Submit” cho ảnh và một  ô nhập câu trả lời cho task QA) gọi API của DRES. Dưới đây là đoạn code Python mẫu đầy  đủ, có thể chép nguyên vào dự án. Cần cài thư viện requests trước: pip install requests.

Trang 3   
**6.1. Các giá trị cần điền** 

• DRES\_URL: giữ nguyên https\://dres.2hbread.com/api/v2. 

• USERNAME, PASSWORD: tài khoản của bạn. 

• COLLECTION: giữ nguyên castle5000. 

**6.2. Code mẫu (dres\_client.py)** 

import requests 

DRES\_URL \= "https\://dres.2hbread.com/api/v2"   
USERNAME \= "UIA\_LeMinhQuan" \# thay bằng tài khoản của bạn PASSWORD \= "MAT\_KHAU\_CUA\_BAN" 

COLLECTION \= "castle5000" 

def login():   
 """Đăng nhập và trả về Session ID."""   
 r \= requests.post(f"{DRES\_URL}/login", 

 json={"username": USERNAME, "password": PASSWORD})  r.raise\_for\_status() 

 return r.json()\["sessionId"\] 

def active\_evaluation\_id(session):   
 """Trả về ID của buổi thi đang ACTIVE."""   
 r \= requests.get(f"{DRES\_URL}/client/evaluation/list", 

 params={"session": session}) 

 r.raise\_for\_status()   
 active \= \[e for e in r.json() if e\["status"\] \== "ACTIVE"\]  if not active: 

 raise RuntimeError("Chưa có buổi thi nào đang ACTIVE")  return active\[0\]\["id"\] 

def current\_task\_type(session, evaluation\_id):   
 """Trả về 'KIS', 'QA', hoặc None nếu chưa có task nào."""  r \= requests.get(f"{DRES\_URL}/client/evaluation/currentTask/{evaluation\_id}",  params={"session": session}) 

 if r.status\_code \== 404: 

 return None   
 r.raise\_for\_status()   
 return "QA" if "Question" in r.json()\["taskType"\] else "KIS" 

def to\_item\_name(file\_name): 

 """'10\_1528.jpg' \-\> 'day1\_Kitchen\_10\_1528'"""   
 stem \= file\_name.rsplit("/", 1)\[-1\].rsplit(".", 1)\[0\] 

 if stem.startswith("day1\_Kitchen\_"): 

 return stem   
 return "day1\_Kitchen\_" \+ stem 

def \_post(session, evaluation\_id, answer):   
 body \= {"answerSets": \[{"answers": \[answer\]}\]} 

 r \= requests.post(f"{DRES\_URL}/submit/{evaluation\_id}",   
 params={"session": session}, json=body)  return r.status\_code, r.text 

def submit\_image(session, evaluation\_id, file\_name):   
 """Task KIS: nộp một ảnh.""" 

 return \_post(session, evaluation\_id, {

Trang 4   
 "mediaItemName": to\_item\_name(file\_name),   
 "mediaItemCollectionName": COLLECTION,   
 }) 

def submit\_text(session, evaluation\_id, answer\_text):   
 """Task QA: nộp một câu trả lời bằng chữ."""   
 return \_post(session, evaluation\_id, {"text": answer\_text.strip()}) 

if \_\_name\_\_ \== "\_\_main\_\_":   
 session \= login() 

 evaluation\_id \= active\_evaluation\_id(session)   
 print("Evaluation ID:", evaluation\_id)   
 print("Task hiện tại:", current\_task\_type(session, evaluation\_id))  \# Task KIS: print(submit\_image(session, evaluation\_id, "10\_1528.jpg"))  \# Task QA : print(submit\_text(session, evaluation\_id, "3")) 

Ảnh 10\_1528.jpg và câu trả lời 3 trong ví dụ chỉ để minh hoạ cú pháp. Khi chạy thử, mỗi lần  nộp sai trong lúc task đang chạy đều **bị trừ điểm** (mục 9). Hãy chạy thử khi BTC mở **buổi  luyện tập**, hoặc khi chưa có task nào chạy (DRES sẽ trả lỗi 400 nhưng xác nhận code của  bạn kết nối được). 

**7\. Nộp bài cho task KIS** 

**7.1. Định dạng yêu cầu** 

| Thành phần  | Giá trị |
| :---- | :---- |
| Phương thức  | POST |
| Địa chỉ  | https\://dres.2hbread.com/api/v2/submit/\<EVALUATION\_ID\>?session=\<S ESSION\_ID\> |
| Header  | Content-Type: application/json |
| Nội dung (body)  | JSON như bên dưới |

{ 

 "answerSets": \[   
 {   
 "answers": \[ 

 {   
 "mediaItemName": "day1\_Kitchen\_10\_1528",   
 "mediaItemCollectionName": "castle5000"   
 } 

 \]   
 }   
 \] 

} 

• mediaItemName: tên ảnh theo quy tắc ở mục 2\. **Bắt buộc**. 

• mediaItemCollectionName: luôn là castle5000. 

• Không cần gửi taskId: DRES tự gắn bài nộp vào task đang chạy. 

• Mỗi lần nộp **một ảnh**.

Trang 5   
**7.2. Nộp bằng curl (khi không dùng code)** 

curl \-X POST "https\://dres.2hbread.com/api/v2/submit/EVALUATION\_ID?session=SESSION\_ID" \\  \-H "Content-Type: application/json" \\ 

 \-d  

'{"answerSets":\[{"answers":\[{"mediaItemName":"day1\_Kitchen\_10\_1528","mediaItemCollectionNam e":"castle5000"}\]}\]}' 

Trên Windows, nếu dùng CMD/PowerShell thì cách đặt dấu nháy khác; nên dùng Git Bash,  WSL, Postman hoặc code Python ở mục 6\. 

**7.3. Đọc kết quả trả về** 

| Mã HTTP  | Nội dung phản hồi  | Ý nghĩa và việc cần làm |
| :---- | :---- | :---- |
| 200  | "submission": "CORRECT"  | Đúng ảnh. Team đã có điểm cho task này,  không cần nộp thêm. |
| 200  | "submission": "WRONG"  | Sai ảnh. Team bị trừ điểm phạt, có thể tiếp tục  tìm và nộp lại. |
| 400  | “Run manager is in wrong  state…” | Hiện không có task nào đang chạy (chưa bắt  đầu hoặc đã hết giờ). |
| 400 hoặc   500 | “Could not find media   item…” | Sai tên ảnh hoặc sai tên collection. Kiểm tra  lại quy tắc ở mục 2\. |
| 401  | Unauthorized  | Session ID sai hoặc đã hết hạn. Đăng nhập lại  (mục 4). |
| 404  | “Evaluation … could not be  found” | Sai Evaluation ID, hoặc tài khoản không thuộc  buổi thi này. |
| 412  | “…rejected by filter…”  | Bị từ chối: ảnh này đã được nộp rồi, team đã  nộp đúng cho task này, hoặc đã gửi câu trả lời chữ (text) vào task KIS. |

**8\. Nộp bài cho task QA** 

**8.1. Task QA khác task KIS thế nào**

|  | Task KIS  | Task QA |
| :---- | :---- | :---- |
| Tên task  | KIS01, KIS02…  | QA01, QA02… |
| Nộp cái gì  | Tên một ảnh  | Câu trả lời bằng chữ |
| Trường JSON  | mediaItemName \+   mediaItemCollectionName | Chỉ text |
| Ai chấm  | DRES chấm tự động, ngay lập  tức | Trọng tài (người) chấm |
| Phản hồi khi nộp  | CORRECT hoặc WRONG  | Thường là INDETERMINATE (đang  chờ chấm) |
| Hàm trong code  mẫu | submit\_image(...)  | submit\_text(...) |

Trang 6   
**8.2. Định dạng yêu cầu** 

Phương thức, địa chỉ và header **giống hệt task KIS** (mục 7.1). Chỉ khác nội dung body: 

{ 

 "answerSets": \[   
 {   
 "answers": \[   
 { "text": "3" } 

 \]   
 }   
 \]   
} 

• text: câu trả lời của team. **Bắt buộc**. 

• **Không** gửi kèm mediaItemName hay mediaItemCollectionName. Nếu gửi kèm tên ảnh,  DRES sẽ coi đây là bài nộp ảnh chứ không phải câu trả lời. 

• Không cần gửi taskId: DRES tự gắn bài nộp vào task QA đang chạy. • Mỗi lần nộp **một câu trả lời**. 

**8.3. Nộp bằng curl** 

curl \-X POST "https\://dres.2hbread.com/api/v2/submit/EVALUATION\_ID?session=SESSION\_ID" \\  \-H "Content-Type: application/json" \\ 

 \-d '{"answerSets":\[{"answers":\[{"text":"3"}\]}\]}' 

Nếu dùng code mẫu ở mục 6: submit\_text(session, evaluation\_id, "3"). 

**8.4. Cách viết câu trả lời** 

• **Ngắn gọn, đúng trọng tâm**: chỉ ghi đáp án, không giải thích. Ví dụ hỏi số lượng thì  ghi 3, hỏi màu thì ghi red. 

• Viết theo **ngôn ngữ của câu hỏi**, trừ khi BTC có quy định khác. 

• Không thêm dấu cách thừa ở đầu/cuối. Hàm submit\_text trong code mẫu đã tự cắt  dấu cách. 

• Hai câu trả lời chỉ khác nhau **một ký tự** (ví dụ 3 và 3 người) vẫn là **hai lần nộp khác  nhau**. Nếu cả hai bị chấm sai, team bị trừ điểm hai lần. 

• Nộp lại **y hệt** một câu trả lời đã nộp sẽ bị từ chối (412) và không bị tính thêm. 

**8.5. Quá trình chấm** 

1\. Team nộp câu trả lời. DRES trả về **202** với "submission": "INDETERMINATE", nghĩa là  đã nhận và đang chờ trọng tài chấm. 

2\. Trọng tài xem câu trả lời và chấm **đúng** hoặc **sai**. 

3\. Kết quả được cập nhật vào bảng điểm. 

• Điểm được tính theo **thời điểm team nộp bài**, không phải thời điểm trọng tài chấm.  Vì vậy không cần lo trọng tài chấm chậm. 

• Câu trả lời bị chấm **sai** được tính như **một lần nộp sai** của task KIS (bị trừ điểm). • Trong lúc chờ chấm, **không nên** nộp liên tục nhiều đáp án khác nhau để “thử”: mỗi  đáp án sai đều bị trừ điểm. 

• Nếu một câu trả lời giống hệt đã được chấm trước đó (kể cả của team khác), DRES  có thể trả ngay CORRECT hoặc WRONG thay vì 202\. 

**8.6. Đọc kết quả trả về**

| Mã HTTP  | Nội dung phản hồi  | Ý nghĩa và việc cần làm |
| :---- | :---- | :---- |
| 202  | "submission":   "INDETERMINATE" | Đã nhận, đang chờ trọng tài chấm. Không  cần làm gì thêm. |

Trang 7 

| Mã HTTP  | Nội dung phản hồi  | Ý nghĩa và việc cần làm |
| :---- | :---- | :---- |
| 200  | "submission": "CORRECT" hoặc  "WRONG" | Câu trả lời giống hệt một câu đã được chấm  trước đó; kết quả có ngay. |
| 400  | “Run manager is in wrong  state…” | Hiện không có task nào đang chạy. |
| 412  | “…does not include textual  information…” | Thiếu trường text, hoặc đã gửi tên ảnh thay  vì câu trả lời. |
| 412  | “…Duplicate submission…”  | Câu trả lời này team đã nộp rồi. |
| 412  | “…rejected by filter…” (khác)  | Team đã có câu trả lời được chấm đúng  cho task này. |
| 401 / 404  | Như task KIS  | Xem bảng ở mục 7.3. |

**9\. Cách tính điểm** 

Công thức tính điểm đã được giới thiệu trong buổi 6, mục điểm cho KIS. Task QA cũng  được tính điểm theo cùng công thức đó, với thời điểm nộp bài là lúc team gửi câu trả lời và  mỗi câu trả lời bị trọng tài chấm sai được tính là một lần nộp sai. 

**10\. Lỗi thường gặp và checklist trước giờ thi** 

**10.1. Checklist** 

1\. Đăng nhập được trên web tại https\://dres.2hbread.com. 

2\. Chạy hàm login() trong code mẫu và nhận được Session ID. 

3\. Lấy được Evaluation ID của buổi thi (mục 5). 

4\. Hàm đổi tên ảnh cho ra đúng dạng day1\_Kitchen\_HH\_frame. 

5\. Hệ thống có cả chức năng nộp ảnh (KIS) và nộp câu trả lời bằng chữ (QA). 6\. Đã thử nộp khi chưa có task chạy và nhận lỗi 400 “wrong state” (chứng tỏ kết nối,  đăng nhập, Evaluation ID đều đúng). 

7\. Team đã thống nhất ai là người nộp bài. 

**10.2. Lỗi thường gặp** 

Nếu gặp lỗi không có trong bảng dưới đây, chụp lại mã HTTP và nội dung phản hồi rồi gửi  cho BTC.

| Hiện tượng  | Nguyên nhân thường gặp |
| :---- | :---- |
| Không đăng nhập được  | Sai mật khẩu (có phân biệt hoa/thường), hoặc gõ thừa  dấu cách khi sao chép. |
| 401 khi nộp  | Session hết hạn do máy chủ khởi động lại hoặc bạn đã  đăng xuất. Đăng nhập lại. |
| “Could not find media item”  | Nộp tên file (10\_1528.jpg) thay vì tên ảnh   (day1\_Kitchen\_10\_1528). |
| 400 “wrong state”  | Nộp lúc chưa bắt đầu task hoặc đã hết giờ. |
| 412 “rejected by filter”  | Nộp lại bài đã nộp, hoặc team đã có bài đúng cho task  này. |

Trang 8 

| Hiện tượng  | Nguyên nhân thường gặp |
| :---- | :---- |
| 412 khi nộp ảnh vào task QA,  hoặc nộp chữ vào task KIS | Gửi nhầm loại bài. Kiểm tra tên task (KIS… / QA…) hoặc  dùng current\_task\_type() trong code mẫu. |
| Task QA chỉ nhận được 202  | Bình thường: câu trả lời đang chờ trọng tài chấm. |
| Không thấy buổi thi trong danh  sách | Tài khoản chưa được BTC thêm vào team của buổi thi.  Liên hệ BTC. |

Trang 9