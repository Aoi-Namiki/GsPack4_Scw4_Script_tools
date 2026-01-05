import os
import struct
from pathlib import Path

Pad2Len = 128
FileHeadLen = 0x1C4

def extract_scw_file(file_path):
    print(f"Processing {file_path}...")
    try:
        with open(file_path, 'rb') as f:
            # 读取文件头
            magic = f.read(16).rstrip(b'\x00').decode('ascii')
            if magic != 'Scw4.x':
                print(f"  Invalid MAGIC: {magic}, skipping.")
                return
            
            main_version = struct.unpack('<i', f.read(4))[0]
            is_compressed = struct.unpack('<i', f.read(4))[0]
            content_length = struct.unpack('<i', f.read(4))[0]
            compressed_len = struct.unpack('<i', f.read(4))[0]
            minor_version = struct.unpack('<i', f.read(4))[0]
            command_count = struct.unpack('<i', f.read(4))[0]
            string_count = struct.unpack('<i', f.read(4))[0]
            addon_count = struct.unpack('<i', f.read(4))[0]
            command_size = struct.unpack('<i', f.read(4))[0]
            string_size = struct.unpack('<i', f.read(4))[0]
            addon_size = struct.unpack('<i', f.read(4))[0]
            padding1 = struct.unpack('<i', f.read(4))[0]
            text_count = struct.unpack('<i', f.read(4))[0]
            padding2 = f.read(Pad2Len)
            description = f.read(0x100).split(b'\x00')[0].decode('cp932', errors='ignore').strip()
            
            # 检查是否需要提取
            if text_count == 0:
                print("  TEXT_COUNT is 0, skipping.")
                return
            
            # 计算索引区大小
            index_size = (command_count + string_count + addon_count) * 8
            # 读取索引区数据
            f.seek(FileHeadLen)
            index_data = f.read(index_size)
            if len(index_data) != index_size:
                print(f"  Incomplete index data: expected {index_size} bytes, got {len(index_data)}.")
                return
            
            # 计算字符串区起始位置
            string_section_start = FileHeadLen + index_size + command_size
            
            # 提取字符串
            strings = []
            for i in range(string_count):
                # 索引项位置：跳过指令区的索引项
                idx_offset = (command_count + i) * 8
                if idx_offset + 8 > len(index_data):
                    print(f"  Index out of range for string {i}.")
                    break
                start, length = struct.unpack('<II', index_data[idx_offset:idx_offset+8])
                # 计算绝对位置
                abs_pos = string_section_start + start
                f.seek(abs_pos)
                data = f.read(length)
                # 处理字符串
                try:
                    s = data.rstrip(b'\x00').decode('cp932', errors='replace')
                except UnicodeDecodeError:
                    s = '<DECODE_ERROR>'
                strings.append(s)
            
            # 写入输出文件
            output_path = f'{file_path}.txt'
            with open(output_path, 'w', encoding='utf-8') as out_f:
                out_f.write(f"[Header]\nSTRING_COUNT = {string_count}\n")
                out_f.write(f"TEXT_COUNT = {text_count}\n")
                out_f.write(f"FILE_DESCRIPTION = {description}\n\n")
                for idx, s in enumerate(strings, 1):
                    out_f.write(f"[Index={idx}]\n{s}\n\n")
            print(f"  Successfully extracted {len(strings)} strings to {output_path}")
    
    except Exception as e:
        print(f"  Error processing {file_path}: {str(e)}")

def main():
    import sys
    # 自动设置目录结构
    current_dir = Path.cwd()
    scr_dir = current_dir / "SCR"
    txt_dir = current_dir / "TXT"
    
    # 检查SCR目录是否存在
    if not scr_dir.exists():
        print(f"Error: SCR directory not found. Creating SCR directory...")
        scr_dir.mkdir(exist_ok=True)
        print(f"Please place your script files (without extension) in the SCR directory.")
        print(f"Then run this script again.")
        input("Press Enter to exit...")
        return
    
    # 创建TXT输出目录
    txt_dir.mkdir(exist_ok=True)
    
    # 处理SCR目录中的所有无后缀文件
    processed_count = 0
    error_count = 0
    
    for root, dirs, files in os.walk(scr_dir):
        for file in files:
            # 只处理无后缀文件
            if '.' not in file:
                scw_file = Path(root) / file
                try:
                    # 提取文本
                    extract_scw_file(scw_file)
                    
                    # 将生成的.txt文件移动到TXT目录，保持目录结构
                    txt_file = scw_file.with_suffix('.txt')
                    if txt_file.exists():
                        # 计算在TXT目录中的相对路径
                        rel_path = scw_file.relative_to(scr_dir)
                        output_path = txt_dir / rel_path.parent / txt_file.name
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 移动文件
                        txt_file.rename(output_path)
                        processed_count += 1
                        print(f"  Moved to: {output_path.relative_to(current_dir)}")
                    else:
                        print(f"  Warning: No .txt file generated for {file}")
                        error_count += 1
                        
                except Exception as e:
                    print(f"  Error processing {file}: {str(e)}")
                    error_count += 1
    
    # 显示统计信息
    print("\n" + "="*50)
    print(f"Extraction completed!")
    print(f"Input directory: SCR/")
    print(f"Output directory: TXT/")
    print(f"Files processed: {processed_count}")
    print(f"Errors: {error_count}")
    
    if processed_count == 0:
        print("\nNo files were processed. Make sure:")
        print("1. Your script files are placed in the SCR directory")
        print("2. The files have no extension (e.g., 'script' not 'script.scw')")
        print("3. The files are valid SCW4.x format")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()