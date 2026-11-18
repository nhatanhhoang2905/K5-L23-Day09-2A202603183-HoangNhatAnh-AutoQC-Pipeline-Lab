# Báo cáo Day 09 — Hoàng Nhật Anh, 2A202603183

## 1. Kết luận trước

Pipeline kết luận **Hold**, mã thoát **10**. Từ 224 ảnh raw, intake loại 19 ảnh, giữ và xuất 205 ảnh. Sau sửa tự động và người duyệt mô phỏng, không còn lỗi bắt buộc nhưng còn 38/205 ảnh có cảnh báo chưa duyệt, tương đương **18.54%**, cao hơn ngưỡng 10%. Bộ `submission/export/clean_v1/` vì vậy chỉ là bản nháp để thử nghiệm.

Nguồn: `01_intake.csv`, `08_summary.json` và `submission/export/clean_v1/manifest.json`.

## 2. Lỗi và phân việc

`02_error_list_v1.csv` có 208 issue: 55 ERROR và 153 WARN. Số ERROR này gồm 19 lỗi intake và 36 lỗi QC sau intake, nên khác con số 36 in ở terminal. Lỗi intake xét trên 224 ảnh; lỗi QC xét trên 205 ảnh giữ lại. Một ảnh có thể có nhiều issue.

| Mã lỗi | Issue / ảnh | Ai xử lý, cách xử lý |
|---|---:|---|
| CORRUPT_IMAGE | 2 / 2 | Máy: intake loại ảnh hỏng |
| BAD_SIZE | 3 / 3 | Máy: intake loại ảnh quá nhỏ |
| DUP_IMAGE_EXACT | 8 / 8 | Máy: intake loại ảnh trùng byte |
| DUP_IMAGE_NEAR | 2 / 2 | Máy: intake loại ảnh gần trùng |
| LEAK_TEST | 4 / 4 | Máy: intake loại ảnh trùng kho test/val |
| MISSING_LABEL_FILE | 6 / 6 | Người gán; máy ghi needs_label |
| BAD_FORMAT | 3 / 3 | Máy: xóa dòng sai định dạng |
| BAD_CLASS_ID | 6 / 6 | Máy: xóa dòng có ID ngoài danh sách |
| BOX_ZERO | 4 / 4 | Máy: xóa dòng có rộng/cao không dương |
| BOX_OUT_OF_IMAGE | 8 / 8 | Máy: cắt box về trong ảnh |
| DUP_BOX | 7 / 7 | Máy: xóa dòng box trùng phía sau |
| BAD_CLASS_NAME | 2 / cấp dataset | Máy: sửa names trong YAML |
| EMPTY_LABEL | 12 / 12 | Người: xem ảnh nền hay bị thiếu nhãn |
| BOX_TINY | 6 / 4 | Người: kiểm vật nhỏ và box |
| BOX_HUGE | 3 / 3 | Người: kiểm box quá lớn |
| CLASS_RARE | 4 / cấp dataset | Người: kiểm thống kê lớp ít box |
| POSSIBLE_FALSE_POS | 29 / 27 | Người: xác nhận nhãn có thừa không |
| POSSIBLE_LOOSE_BOX | 28 / 24 | Người: kiểm độ khít của box |
| POSSIBLE_MISSING | 53 / 52 | Người: kiểm vật bị bỏ sót |
| POSSIBLE_WRONG_CLASS | 18 / 18 | Người: xác nhận lại lớp |

Các mã POSSIBLE_* mới là nghi ngờ của checker, chưa phải lỗi thật đã được xác nhận. Hai issue BAD_CLASS_NAME cùng thuộc một file YAML; CLASS_RARE là thống kê cấp dataset, không tính là ảnh.

Log autofix có 35 dòng: 20 drop_line, 8 clip_box, 1 rename_classes và 6 needs_label. Có 29 thay đổi thực tế; 6 needs_label chỉ chuyển người gán, không tạo nhãn rỗng.

Hàng đợi có 125 ảnh, xếp theo tổng trọng số cảnh báo, confidence và các sửa tự động cần xem lại. `img_0020` đứng đầu với 11.524 điểm vì có cả FIXED_DROP_LINE, POSSIBLE_MISSING và POSSIBLE_WRONG_CLASS. Tiếp theo là 6 ảnh thiếu nhãn, mỗi ảnh 10 điểm. Người duyệt mô phỏng đã xem 80/125 ảnh. Trong 80 ảnh này, 74 ảnh mang 94/123 cảnh báo ngữ nghĩa của v2: 51 missing, 18 wrong class, 13 false positive và 12 loose box. Đây là số cảnh báo được đưa tới người xem, không phải số lỗi thật đã sửa.

## 3. Calibration hai ngưỡng

Đã chạy hai sweep trên 39 ảnh calib, lưu tại `submission/calibration/`. P/R trong bảng là precision/recall, lấy từ các hàng sweep tương ứng.

| Tham số | Khởi đầu → chọn | P/R trước → sau | Lý do chọn |
|---|---|---|---|
| duplicates.phash_dist | 2 → 4 | Gần trùng: 1.00/0.50 → 1.00/0.67 | Bắt 4/6 thay vì 3/6 lỗi gần trùng, không có FP trên calib; chọn mức nhỏ nhất trong nhóm 4–14 có cùng kết quả |
| second_opinion.conf | 0.25 → 0.6 | Missing: 0.50/1.00 → 0.57/1.00; wrong class: 0.56/0.83 → 0.62/0.83 | Giảm báo động giả, vẫn giữ recall của hai nhóm này |

Đánh đổi là recall box lỏng giảm từ 0.40 xuống 0.20: chỉ bắt được 1/5 lỗi chèn. False positive vẫn có P/R khoảng 0.31/1.00 vì dùng fp_conf riêng. Tôi chọn ưu tiên giữ recall thiếu nhãn, chấp nhận box lỏng cần kiểm thêm bằng mắt.

Không thể chỉ lấy ngưỡng có F1 cao nhất trên calib. Với pHash 16, recall gần trùng đạt 0.83 và precision 1.00 trên calib, nhưng khi kiểm raw, `img_0011` (người chơi tennis) lại bị coi là trùng `img_0008` (hai người trượt tuyết), khoảng cách hash 16. Hai ảnh khác nội dung rõ ràng; nếu dùng ngưỡng đó, intake sẽ loại nhầm ảnh tốt. Đây là lý do tôi giữ pHash 4 dù recall thấp hơn.

## 4. Cửa chặn và điểm mù

Tôi kiểm gate bằng lệnh:

`python -m pipeline.run --budget 0 --work work/gate_cp4 --reports work/reports_gate_cp4 --export-dir work/export_gate_cp4`

Kết quả **Rework**, mã thoát **20**, reviewed = 0 và exported = null. `Test-Path work/export_gate_cp4/clean_v1/manifest.json` trả **False**. Còn 6 lỗi MISSING_LABEL_FILE ở `img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`. Sáu dòng log sau duyệt cũng chỉ là needs_label; máy không tự gán nhãn để vượt gate.

Hai điểm chưa bắt hết:

- **Gần trùng:** pHash 4 bỏ sót 2/6 lỗi chèn ở `calib_037` và `calib_038`. Cần xem thêm các cặp nghi ngờ hoặc dùng phép so sánh bổ sung; tăng ngưỡng có thể gây loại nhầm như ví dụ trên.
- **Box lỏng:** conf 0.6 bỏ sót 4/5 lỗi chèn ở `calib_002`, `calib_006`, `calib_012`, `calib_024`. Cần lấy mẫu cả ảnh không bị cờ để người kiểm box. Không có cảnh báo chưa đủ để kết luận nhãn đúng.

## 5. Train: raw vs clean

Đã train trên Colab T4, cùng model khởi tạo `yolo26n.pt`, 20 epoch, batch 16, imgsz 640 và hai seed 0/1 cho mỗi biến thể. Hai bên dùng chung gold_val 40 ảnh để validation và test 100 ảnh để đánh giá cuối. Kết quả clean khớp checksum của manifest 205 ảnh hiện tại.

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 205 | 2 | 0.700 ± 0.030 | 0.486 ± 0.013 | 0.715 ± 0.073 | 0.615 ± 0.017 |

Chênh mAP50 (clean − raw) = **-0.025**.

mAP50 của raw ở hai seed là 0.7256 và 0.7259; clean là 0.6788 và 0.7219. Chênh trung bình clean − raw là **-0.0254** (khoảng 2.54 điểm phần trăm). Độ lệch chuẩn mAP50 là 0.00021 ở raw và 0.03048 ở clean; bảng trên làm tròn ba chữ số nên độ lệch raw hiển thị 0.000, không phải bằng 0.

Trong lần thử này, clean cho điểm thấp hơn raw. Mức giảm vẫn nhỏ hơn độ lệch giữa hai seed clean, nên với hai seed chưa đủ cơ sở để nói clean kém hơn một cách ổn định, cũng chưa có bằng chứng clean giúp tăng mAP. Hai khả năng cần kiểm tiếp:

- **Raw có rò rỉ dữ liệu:** intake phát hiện 4 ảnh LEAK_TEST trùng kho test/val. Điều này có thể làm điểm raw cao hơn. Cần train thêm một biến thể raw trên bản sao chỉ loại các ảnh rò rỉ, giữ nguyên model, seed, val/test và các thiết lập khác để tách ảnh hưởng này.
- **Clean chưa sạch hoàn toàn và bộ train đã thay đổi:** sau QC vẫn có 38/205 ảnh cảnh báo chưa duyệt, đồng thời ít hơn raw 19 ảnh. AP50 trung bình lớp truck giảm từ 0.6484 xuống 0.5588. Cần xem lại các ảnh/box truck và ảnh còn cảnh báo, đếm box theo lớp, rồi train lại cùng cấu hình sau khi duyệt. Các cảnh báo chưa chứng minh mọi nhãn ở những ảnh đó đều sai.

Bước tiếp theo là bổ sung seed cho cả hai biến thể và giữ cùng cách đánh giá, vì test chỉ có 100 ảnh. Số ảnh 224/205 trong bảng là số file bộ train do script ghi nhận; riêng raw, chưa có số đếm ảnh thực sự được Ultralytics dùng sau khi bỏ ảnh/nhãn hỏng từ log train.

## 6. Quyết định và ghi chú AI

Tôi giữ quyết định **Hold**. Cần tiếp tục xác minh các ảnh chưa duyệt trong đợt xử lý tiếp theo. Muốn Release phải hết ERROR và tỷ lệ ảnh còn cảnh báo chưa duyệt dưới 10%; nếu vẫn giữ 205 ảnh thì phải giảm từ 38 xuống tối đa 20 ảnh. Ngân sách 80 và các ngưỡng cố định của bài giữ nguyên.

Có dùng AI hỗ trợ viết bốn module và đọc kết quả:

- **Yêu cầu chính:** dựa vào docstring và test để viết checks trả Issue, gate trả quyết định; autofix chỉ sửa bản sao và ghi log trước/sau.
- **Cách kiểm:** test từng module và toàn bộ 79 test đều đạt; kiểm thêm ca biên, bản sao calib, ảnh vẽ nhãn và phép thử budget 0.
