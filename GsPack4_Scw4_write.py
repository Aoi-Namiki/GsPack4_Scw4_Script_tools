import os
import sys
import struct
import logging
from logging.handlers import RotatingFileHandler

NewEncode = 'cp932'
Pad2Len = 128
FileHeadLen = 0x1C4

def setup_logger(log_file):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = RotatingFileHandler(log_file, maxBytes=1048576, backupCount=5)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

def parse_txt(txt_path):
    strings = []
    header = {}
    current_index = None
    current_section = None
    
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('['):
                if line == '[Header]':
                    current_section = 'header'
                elif line.startswith('[Index='):
                    current_section = 'index'
                    index_part = line.split('=', 1)[1].rstrip(']')
                    current_index = int(index_part)
                    if current_index != len(strings) + 1:
                        logger.error(f"TXT {txt_path} index {current_index} out of order")
                        return None, None
                    strings.append('')
                else:
                    current_section = None
            else:
                if current_section == 'header':
                    if '=' in line:
                        key, value = line.split('=', 1)
                        header[key.strip()] = value.strip()
                elif current_section == 'index' and current_index is not None:
                    if 1 <= current_index <= len(strings):
                        if strings[current_index - 1]:
                            strings[current_index - 1] += '\n' + line
                        else:
                            strings[current_index - 1] = line
    return header, strings

def process_scw(scw_path, txt_path, output_path):
    try:
        with open(scw_path, 'rb') as f:
            # 读取并解析文件头（456字节）
            header_data = f.read(FileHeadLen)
            magic, main_v, is_compressed, content_len, comp_len, minor_v, cmd_count, str_count, addon_count, cmd_size, str_size, addon_size, pad1, text_count, pad2, desc = struct.unpack(f'<16s13i{Pad2Len}s256s', header_data)
            
            # 直接读取内容区（忽略压缩标志）
            f.seek(FileHeadLen)
            content = f.read(content_len)
            
            # 计算各区域位置
            index_size = (cmd_count + str_count + addon_count) * 8
            index_end = index_size
            cmd_end = index_end + cmd_size
            str_end = cmd_end + str_size
            addon_end = str_end + addon_size
            
            # 分割内容区（确保切片正确）
            index_data = content[:index_end]
            cmd_data = content[index_end:cmd_end]
            str_data = content[cmd_end:str_end]
            addon_data = content[str_end:addon_end]
            
            # 解析文本文件
            header_txt, new_strings = parse_txt(txt_path)
            if not header_txt or not new_strings:
                logger.error(f"Failed to parse {txt_path}")
                return False
            
            # 验证字符串数量
            str_count_txt = int(header_txt.get('STRING_COUNT', -1))
            text_count_txt = int(header_txt.get('TEXT_COUNT', -1))
            if str_count_txt != str_count or text_count_txt != text_count:
                logger.error(f"Count mismatch in {txt_path}: expected {str_count}/{text_count}, got {str_count_txt}/{text_count_txt}")
                return False
            
            # 编码转换
            new_str_list = []
            encoding_errors = False
            for s in new_strings:
                try:
                    encoded = s.encode(NewEncode) + b'\x00'
                except UnicodeEncodeError:
                    encoded = s.encode(NewEncode, errors='replace') + b'\x00'
                    logger.warning(f"Encoding error in string: {s}")
                    encoding_errors = True
                new_str_list.append(encoded)
            
            if encoding_errors:
                logger.warning(f"Some strings in {txt_path} had encoding issues")
            
            # 构建新字符串区
            new_str_data = b''.join(new_str_list)
            new_str_size = len(new_str_data)
            
            # 更新索引区（仅修改字符串部分）
            new_index = bytearray(index_data)
            str_index_start = cmd_count * 8  # 字符串索引起始位置
            
            # 计算字符串区的新偏移量
            current_offset = 0
            for i in range(str_count):
                entry_offset = str_index_start + i * 8
                # 读取原始起始地址（可能已被修改过）
                old_start, old_len = struct.unpack_from('<II', new_index, entry_offset)
                # 更新为新的长度
                new_length = len(new_str_list[i])
                struct.pack_into('<II', new_index, entry_offset, current_offset, new_length)
                current_offset += new_length
            
            # 重组内容区（保持指令区和附加区不变）
            new_content = new_index + cmd_data + new_str_data + addon_data
            new_content_len = len(new_content)
            
            # 更新文件头
            new_header = list(struct.unpack(f'<16s13i{Pad2Len}s256s', header_data))
            new_header[3] = new_content_len  # CONTENT_LENGTH
            new_header[10] = new_str_size    # STRING_SIZE
            
            # 重新打包文件头
            packed_header = struct.pack(f'<16s13i{Pad2Len}s256s', *new_header)
            
            # 写入新文件
            with open(output_path, 'wb') as out_f:
                out_f.write(packed_header)
                out_f.write(new_content)
            
            logger.info(f"Successfully processed {scw_path}")
            return True
    except Exception as e:
        logger.error(f"Error processing {scw_path}: {str(e)}")
        return False

def main():
    # 自动设置目录结构
    current_dir = Path.cwd()
    scr_dir = current_dir / "SCR"
    txt_dir = current_dir / "TXT"
    new_scr_dir = current_dir / "NEW_SCR"
    log_file = current_dir / "output.log"
    
    # 检查必要目录是否存在
    if not scr_dir.exists():
        print(f"Error: SCR directory not found.")
        print(f"Please create SCR directory and place your original script files (without extension) in it.")
        input("Press Enter to exit...")
        return
    
    if not txt_dir.exists():
        print(f"Error: TXT directory not found.")
        print(f"Please create TXT directory and place your translated text files in it.")
        input("Press Enter to exit...")
        return
    
    # 创建输出目录
    new_scr_dir.mkdir(exist_ok=True)
    
    # 设置日志
    global logger
    logger = setup_logger(log_file)
    
    print(f"Input directory: {scr_dir.relative_to(current_dir)}")
    print(f"Text directory: {txt_dir.relative_to(current_dir)}")
    print(f"Output directory: {new_scr_dir.relative_to(current_dir)}")
    print(f"Log file: {log_file.relative_to(current_dir)}")
    print("="*50)
    
    success = 0
    failed = 0
    warnings = 0
    
    # 扫描SCR目录中的所有无后缀文件
    scw_files = {}
    for root, dirs, files in os.walk(scr_dir):
        for file in files:
            if '.' not in file:  # 无后缀文件
                scw_files[file] = os.path.join(root, file)
    
    # 处理所有文件
    for root, dirs, files in os.walk(txt_dir):
        for file in files:
            if file.endswith('.txt'):
                base_name = file[:-4]  # 去掉.txt后缀
                scw_path = scw_files.get(base_name)
                
                if not scw_path:
                    logger.warning(f"No .scw file found for {file}")
                    warnings += 1
                    continue
                
                txt_path = os.path.join(root, file)
                
                # 计算输出路径，保持目录结构
                rel_path = os.path.relpath(txt_path, txt_dir)
                output_path = os.path.join(new_scr_dir, os.path.dirname(rel_path), base_name)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # 处理文件
                if process_scw(scw_path, txt_path, output_path):
                    success += 1
                else:
                    failed += 1
    
    # 显示统计信息
    logger.info(f"Processing completed. Success: {success}, Failed: {failed}, Warnings: {warnings}")
    
    print("\n" + "="*50)
    print(f"Processing completed!")
    print(f"Success: {success}")
    print(f"Failed: {failed}")
    print(f"Warnings: {warnings}")
    print(f"\nOutput directory: {new_scr_dir.relative_to(current_dir)}")
    print(f"Log file: {log_file.relative_to(current_dir)}")
    
    # 显示日志文件最后几行
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                print("\nLast few lines from log file:")
                for line in lines[-5:]:
                    print(f"  {line.rstrip()}")
    except Exception as e:
        print(f"\nCould not read log file: {str(e)}")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    # 添加Path导入
    from pathlib import Path
    main()