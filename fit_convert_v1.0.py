import os
from datetime import datetime, timedelta

try:
    from fitparse import FitFile
except ImportError:
    FitFile = None

def parse_fit_records(file_path):
    """直接解析 .fit 檔案，萃取所有 record（TYPE=2 類別）的資料"""
    if FitFile is None:
        print("❌ 錯誤 (Error): 找不到 'fitparse' 套件，請先執行指令: py -m pip install fitparse")
        return []

    fitfile = FitFile(file_path)
    record_rows = []

    for record in fitfile.get_messages():
        if record.name != "record":
            continue
        
        row_data = {}
        for field in record.fields:
            if field.value is not None:
                val = field.value
                unit = field.units if field.units else ""
                if unit:
                    row_data[field.name] = f"{val}={val} {unit}"
                else:
                    row_data[field.name] = str(val)

        if 'timestamp' in row_data:
            ts_val = record.get_value('timestamp')
            if isinstance(ts_val, datetime):
                row_data['timestamp'] = f"{int(ts_val.timestamp())}={ts_val.strftime('%Y-%m-%dT%H:%M:%SZ')}"

        record_rows.append(row_data)

    return record_rows


def parse_dive_log_only_type2(file_path):
    """解析文字日誌檔，保留 TYPE=2 或 NAME=record 的資料"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    blocks = content.strip().split('==')
    record_rows = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        lines = block.split('\n')
        header_line = lines[0].strip()
        
        row_data = {}
        cleaned_header = header_line.lstrip('=').strip()
        header_tokens = cleaned_header.split()
        for token in header_tokens:
            if '=' in token:
                k, v = token.split('=', 1)
                row_data[k] = v

        is_type_2 = row_data.get('TYPE') == '2'
        is_record_name = row_data.get('NAME') == 'record'
        
        if not (is_type_2 or is_record_name):
            continue

        for line in lines[1:]:
            line = line.strip()
            if line.startswith('---'):
                content_part = line[3:].strip()
                if '=' in content_part:
                    k, v = content_part.split('=', 1)
                    parts_v = v.split('=')
                    row_data[k] = parts_v[-1] if len(parts_v) > 1 else v

        record_rows.append(row_data)

    return record_rows


def convert_fit_to_txt(file_path, current_dir):
    """模式 2：將 Garmin .fit 檔轉換成程式專用的 .txt 格式"""
    if FitFile is None:
        print("❌ 錯誤 (Error): 找不到 'fitparse' 套件，請先執行指令: py -m pip install fitparse")
        return

    base_file_name = os.path.basename(file_path)
    base_name = os.path.splitext(base_file_name)[0]
    output_txt = f"{base_name}_converted.txt"
    output_path = os.path.join(current_dir, output_txt)

    print(f"🔄 正在解析 .fit 檔案 (Parsing .fit file): {base_file_name} ...")
    fitfile = FitFile(file_path)
    
    txt_lines = []
    message_count = 0

    for record in fitfile.get_messages():
        msg_name = record.name
        if not msg_name:
            continue
            
        type_num = "2" if msg_name == "record" else "1"
        txt_lines.append(f"= TYPE={type_num} NAME={msg_name}")

        for field in record.fields:
            if field.value is not None:
                val = field.value
                unit = field.units if field.units else ""
                unit_str = f" {unit}" if unit else ""
                txt_lines.append(f"--- {field.name}={val}={val}{unit_str}")

        txt_lines.append("==")
        txt_lines.append("")
        message_count += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(txt_lines))

    print(f"✨ .fit 轉 .txt 成功 (.fit to .txt succeeded)！已輸出至 (Saved to): {output_txt} (共處理 {message_count} 個區塊 / {message_count} blocks)")


def seconds_to_srt_time(seconds):
    """將秒數轉換為 SRT 時間格式 (HH:MM:SS,mmm)"""
    if seconds < 0:
        seconds = 0
    td = timedelta(seconds=seconds)
    hours = int(td.total_seconds() // 3600)
    minutes = int((td.total_seconds() % 3600) // 60)
    secs = int(td.total_seconds() % 60)
    milliseconds = int((td.total_seconds() % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def parse_offset_input():
    """互動詢問並解析使用者輸入的起始時間"""
    print("\n--- SRT 字幕起始時間設定 (SRT Start Time Configuration) ---")
    offset_input = input("請輸入影片中這段資料要開始的【起始時間】(秒數或 MM:SS，直接按 Enter 預設 0):\n"
                         "Enter start time (Seconds or MM:SS, press Enter for 0): ").strip()
    if not offset_input:
        return 0.0
    try:
        if ':' in offset_input:
            parts = list(map(float, offset_input.split(':')))
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            elif len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            return float(offset_input)
    except Exception:
        print("⚠️ 格式解析失敗，預設起始時間為 0 秒。(Format parse failed, default to 0 seconds.)")
        return 0.0


def generate_srt_file(rows, base_name, current_dir, offset_seconds):
    """共用邏輯：從資料列產生 SRT 檔案"""
    output_srt = f"{base_name}_dive_data.srt"
    output_path = os.path.join(current_dir, output_srt)

    srt_lines = []
    first_timestamp_dt = None

    for i, row in enumerate(rows, start=1):
        timestamp_full = row.get('timestamp', '')
        time_parts = timestamp_full.split('=')
        iso_time_str = time_parts[-1] if len(time_parts) > 1 else timestamp_full

        depth_raw = row.get('depth', 'N/A')
        temp_raw = row.get('temperature', 'N/A')

        depth = depth_raw.split('=')[-1] if '=' in str(depth_raw) else depth_raw
        temp = temp_raw.split('=')[-1] if '=' in str(temp_raw) else temp_raw

        try:
            clean_time_str = iso_time_str.replace('Z', '')
            dt = datetime.fromisoformat(clean_time_str)
            
            if first_timestamp_dt is None:
                first_timestamp_dt = dt
            
            relative_seconds = (dt - first_timestamp_dt).total_seconds() + offset_seconds
        except Exception:
            relative_seconds = ((i - 1) * 1) + offset_seconds

        start_sec = relative_seconds
        end_sec = relative_seconds + 0.999

        start_time_str = seconds_to_srt_time(start_sec)
        end_time_str = seconds_to_srt_time(end_sec)

        subtitle_text = f"Depth: {depth}\nTemp: {temp}"

        srt_lines.append(str(i))
        srt_lines.append(f"{start_time_str} --> {end_time_str}")
        srt_lines.append(subtitle_text)
        srt_lines.append("")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_lines))

    print(f"✨ SRT 字幕檔轉換成功 (SRT generation successful)！已輸出至 (Saved to): {output_srt} (共 {len(rows)} 筆字幕 / {len(rows)} subtitles)")


def convert_to_srt_from_txt(file_path, current_dir):
    """模式 1：將 .txt 轉成 SRT 字幕檔"""
    rows = parse_dive_log_only_type2(file_path)
    if not rows:
        print("⚠️ 檔案中找不到任何有效歷程（record）資料。(No valid record data found in file.)")
        return

    offset_seconds = parse_offset_input()
    print(f"⏱️ 設定的起始偏移時間 (Start offset set to): {offset_seconds} 秒 (seconds)")

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    generate_srt_file(rows, base_name, current_dir, offset_seconds)


def convert_to_srt_from_fit(file_path, current_dir):
    """模式 3：將 .fit 直接轉成 SRT 字幕檔"""
    rows = parse_fit_records(file_path)
    if not rows:
        print("⚠️ .fit 檔案中找不到任何 record 資料。(No record data found in .fit file.)")
        return

    offset_seconds = parse_offset_input()
    print(f"⏱️ 設定的起始偏移時間 (Start offset set to): {offset_seconds} 秒 (seconds)")

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    generate_srt_file(rows, base_name, current_dir, offset_seconds)


def main():
    current_dir = os.getcwd()
    print(f"📂 目前工作資料夾 (Current Working Directory): {current_dir}")

    print("\n--- Garmin 潛水日誌轉換工具 (Garmin Dive Log Conversion Tool) ---")
    print("請選擇要執行的功能 (Please select a function):")
    print("1. 將 .txt 轉換成 SRT 字幕檔（含自訂起始時間）")
    print("   Convert .txt to SRT subtitle file (with custom start time)")
    print("2. 將 Garmin .fit 檔轉換成 .txt 檔")
    print("   Convert Garmin .fit file to .txt file")
    print("3. 將 Garmin .fit 檔【直接】轉換成 SRT 字幕檔")
    print("   Convert Garmin .fit file DIRECTLY to SRT subtitle file")
    print("4. 什麼都不做，離開程式")
    print("   Exit program")
    
    choice = input("\n請輸入選項代號 (Enter option 1 - 4): ").strip()

    # 處理離開程式選項
    if choice == '4':
        print("👋 感謝使用，程式已結束。(Thank you for using, program exited.)")
        return

    if choice in ['2', '3']:
        target_files = [f for f in os.listdir(current_dir) if f.lower().endswith('.fit')]
    elif choice == '1':
        target_files = [f for f in os.listdir(current_dir) if f.lower().endswith('.txt')]
    else:
        print("❌ 輸入錯誤，請重新執行並輸入 1 到 4 的選項。(Invalid input, please run again and enter 1-4.)")
        return

    if not target_files:
        ext = ".fit" if choice in ['2', '3'] else ".txt"
        print(f"⚠️ 找不到任何副檔名為 {ext} 的檔案！(No {ext} files found!)")
        return

    for file_name in target_files:
        file_path = os.path.join(current_dir, file_name)
        try:
            print(f"\n🔄 正在處理檔案 (Processing file): {file_name} ...")
            if choice == '1':
                convert_to_srt_from_txt(file_path, current_dir)
            elif choice == '2':
                convert_fit_to_txt(file_path, current_dir)
            elif choice == '3':
                convert_to_srt_from_fit(file_path, current_dir)
        except Exception as e:
            print(f"❌ 處理檔案 {file_name} 時發生錯誤 (Error processing {file_name}): {e}")

if __name__ == "__main__":
    main()
    input("\n按 Enter 鍵結束程式... (Press Enter to exit...)")
