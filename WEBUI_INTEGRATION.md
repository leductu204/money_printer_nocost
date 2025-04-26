# Hướng dẫn tích hợp tùy chọn FFMPEG vào WebUI

## Bước 1: Sao chép file ffmpeg_settings.py

Sao chép file `ffmpeg_settings.py` vào thư mục `webui` của MoneyPrinterTurbo:

```
E:\Python\Tool\Auto Gen AI Video\MoneyPrinterTurbo\webui\ffmpeg_settings.py
```

## Bước 2: Chỉnh sửa file Main.py

Mở file `Main.py` trong thư mục `webui` và thêm dòng import sau vào phần đầu file:

```python
from ffmpeg_settings import add_ffmpeg_settings_to_ui
```

## Bước 3: Thêm tùy chọn FFMPEG vào phần Basic Settings

Tìm phần "Basic Settings" trong file `Main.py`. Thường nó sẽ có dạng như sau:

```python
with st.expander("Basic Settings", expanded=False):
    # Các tùy chọn hiện tại
    ...
```

Thêm dòng sau vào cuối phần expander:

```python
    # Thêm tùy chọn FFMPEG
    ffmpeg_settings = add_ffmpeg_settings_to_ui()
```

## Bước 4: Sử dụng các tùy chọn FFMPEG trong code

Để sử dụng các tùy chọn FFMPEG trong code, bạn có thể truy cập chúng thông qua `config.app`:

```python
from app.config import config

# Lấy số luồng FFMPEG
threads = config.app.get("ffmpeg_threads_per_process", 2)

# Sử dụng trong ffmpeg command
cmd = [
    "ffmpeg",
    "-threads", str(threads),
    # Các tham số khác
]
```

## Bước 5: Sửa đổi file video.py

Mở file `app/services/video.py` và tìm các dòng sử dụng tham số `threads`. Thay thế chúng bằng:

```python
threads = config.app.get("ffmpeg_threads_per_process", 2)
```

Ví dụ:

```python
video_clip.write_videofile(
    filename=combined_video_path,
    threads=config.app.get("ffmpeg_threads_per_process", 2),
    # Các tham số khác
)
```

## Kiểm tra

Sau khi thực hiện các bước trên, khởi động lại MoneyPrinterTurbo và kiểm tra phần "Basic Settings". Bạn sẽ thấy các tùy chọn FFMPEG mới được thêm vào.

## Lưu ý

- Các tùy chọn FFMPEG sẽ được lưu vào file config.toml
- Mỗi luồng FFMPEG sẽ sử dụng thêm khoảng 200MB RAM
- Nếu bạn đặt quá nhiều luồng, có thể gây ra lỗi MemoryError
