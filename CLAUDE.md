Thiết kế và code UI cho một Data Validation Platform theo phong cách dark mode hiện đại, high-tech, giống các data tools chuyên nghiệp.

Sử dụng font Inter (primary) và có thể dùng JetBrains Mono cho data.
Màu sắc phải nhất quán:

Background chính: #0F172A
Card / panel: #1E293B
Border: #334155
Text chính: #E2E8F0, phụ: #94A3B8
Accent dùng gradient: linear-gradient(135deg, #6366F1, #22C55E)

Background KHÔNG được flat, phải có chiều sâu:

dùng radial gradient tím + xanh
có grid pattern nhẹ
optional blur shapes để tạo cảm giác system đang chạy

Tất cả component phải custom, không dùng style mặc định của browser.

UI RULES
Layout dùng spacing đều (8–24px), align rõ ràng
Card có radius 12–16px, border nhẹ, shadow subtle
Visual hierarchy rõ: search là primary, filter là secondary
FILTER BAR (bắt buộc chuẩn)

Gồm:
Search theo column name + Dropdown (Sheet, Status, Error Type) + Slider (Missing %)

Rules:

tất cả cùng height
search rộng nhất
đặt trong container glass (semi-transparent + blur)

Dropdown:

nền #1E293B
text #E2E8F0
hover #334155
selected có highlight accent

Slider:

track xám đậm
fill dùng gradient system
thumb màu tím + border trắng
COMPONENT BEHAVIOR
Hover: sáng nhẹ + scale nhẹ
Focus: border tím + glow
Transition: 0.2s ease

Button primary:

gradient tím → xanh
hover sáng hơn
LOGIN PAGE
layout center
background gradient + blur shapes
card login clean, focus vào input + button
tạo cảm giác bước vào một data platform xịn
DASHBOARD
rõ ràng, dễ đọc
table clean
progress bar dùng gradient
status màu:
xanh (OK)
vàng (warning)
đỏ (error)
NGUYÊN TẮC QUAN TRỌNG
không dùng màu ngoài system
không dùng UI mặc định browser
không phá vỡ consistency giữa các trang