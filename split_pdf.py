#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from PyPDF2 import PdfReader, PdfWriter
import re
from pathlib import Path

# 导入书签提取模块
from get_pdf_bookmark import extract_bookmarks, debug_print

def create_output_dir(output_dir):
    """创建输出目录"""
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def sanitize_filename(name):
    """处理文件名，移除不合法字符"""
    # 替换不合法的文件名字符
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    # 限制文件名长度
    if len(name) > 150:
        name = name[:147] + "..."
    return name

def convert_to_page_number(page_obj, pdf_reader=None):
    """将页码对象转换为整数页码"""
    try:
        # 如果是可以直接转为整数的对象
        if isinstance(page_obj, int):
            return page_obj
            
        # 如果是字符串，尝试直接转换
        if isinstance(page_obj, str):
            try:
                return int(page_obj)
            except ValueError:
                # 尝试提取数字
                numbers = re.findall(r'\d+', page_obj)
                if numbers:
                    return int(numbers[0])
        
        # 处理IndirectObject类型
        if hasattr(page_obj, '__class__') and 'IndirectObject' in page_obj.__class__.__name__:
            # 尝试通过pdf_reader对象查找对应页码
            if pdf_reader:
                try:
                    # 遍历所有页面，查找匹配的引用
                    for i, page in enumerate(pdf_reader.pages):
                        if page.indirect_reference == page_obj:
                            return i + 1
                except Exception as e:
                    print(f"通过比较引用查找页码失败: {e}")
                
                # 尝试通过对象ID查找页码
                if hasattr(page_obj, 'idnum'):
                    try:
                        for i, page in enumerate(pdf_reader.pages):
                            if hasattr(page.indirect_reference, 'idnum') and page.indirect_reference.idnum == page_obj.idnum:
                                return i + 1
                    except Exception as e:
                        print(f"通过对象ID查找页码失败: {e}")
            
            # 如果有get_object方法，尝试获取实际对象
            if hasattr(page_obj, 'get_object') and callable(page_obj.get_object):
                try:
                    actual_obj = page_obj.get_object()
                    # 递归调用处理实际对象
                    return convert_to_page_number(actual_obj, pdf_reader)
                except Exception as e:
                    print(f"无法解析IndirectObject: {e}")
            
            # 如果上述方法都失败，返回对象ID作为页码估计
            if hasattr(page_obj, 'idnum'):
                if pdf_reader:
                    # 对象ID通常大于实际页码，尝试通过简单算法估计
                    estimated_page = min(page_obj.idnum // 2, len(pdf_reader.pages))
                    print(f"估计页码: {estimated_page} (基于对象ID: {page_obj.idnum})")
                    return estimated_page
                return page_obj.idnum
        
        # 尝试将对象字符串化并提取数字
        page_str = str(page_obj)
        numbers = re.findall(r'\d+', page_str)
        if numbers:
            return int(numbers[0])
            
    except Exception as e:
        print(f"警告: 无法转换页码对象 {type(page_obj)}: {str(e)}")
    
    return None

def get_page_ranges(bookmarks, total_pages, split_level, pdf_reader=None):
    """
    根据指定层级的书签，计算拆分的页面范围
    
    Args:
        bookmarks: 书签列表
        total_pages: PDF总页数
        split_level: 拆分的书签层级
        pdf_reader: PDF阅读器对象，用于解析页码
        
    Returns:
        拆分范围列表，每项包含标题和页面范围(start, end)
    """
    # 筛选指定层级的书签
    level_bookmarks = [b for b in bookmarks if b['level'] == split_level]
    
    # 如果没有指定层级的书签，返回空列表
    if not level_bookmarks:
        print(f"未找到层级为{split_level}的书签，无法拆分")
        return []
    
    # 处理页码对象，转换为整数
    for i, bookmark in enumerate(level_bookmarks):
        page_obj = bookmark.get('page')
        if page_obj is not None:
            # 尝试将页码对象转换为整数
            page_num = convert_to_page_number(page_obj, pdf_reader)
            level_bookmarks[i]['page'] = page_num
            
            if page_num is None:
                print(f"警告: 书签 '{bookmark['title']}' 的页码无法转换 (原始值: {page_obj})")
        else:
            print(f"警告: 书签 '{bookmark['title']}' 没有页码信息")
            level_bookmarks[i]['page'] = None
    
    # 移除没有有效页码的书签
    level_bookmarks = [b for b in level_bookmarks if isinstance(b['page'], int) and b['page'] > 0]
    
    if not level_bookmarks:
        print("警告: 没有包含有效页码的书签")
        return []
    
    # 按页码排序
    level_bookmarks.sort(key=lambda x: x['page'])
    
    # 计算页面范围
    ranges = []
    for i, bookmark in enumerate(level_bookmarks):
        start_page = bookmark['page'] - 1  # 转为0索引
        
        # 结束页面是下一个书签的开始页面-1，或者文档的最后一页
        if i < len(level_bookmarks) - 1:
            end_page = level_bookmarks[i+1]['page'] - 2  # 下一个书签的前一页
        else:
            end_page = total_pages - 1  # 最后一页（0索引）
        
        # 确保范围有效
        if end_page >= start_page:
            ranges.append({
                'title': bookmark['title'],
                'start': start_page,
                'end': end_page
            })
        else:
            print(f"警告: 书签 '{bookmark['title']}' 的页面范围无效 ({start_page+1}-{end_page+1})")
    
    # 检查是否覆盖了所有页面
    if ranges:
        first_range = ranges[0]
        last_range = ranges[-1]
        
        # 如果第一个范围不是从第一页开始，添加一个"前言"范围
        if first_range['start'] > 0:
            ranges.insert(0, {
                'title': '前言部分',
                'start': 0,
                'end': first_range['start'] - 1
            })
        
        # 如果最后一个范围不是到最后一页结束，添加一个"附录"范围
        if last_range['end'] < total_pages - 1:
            ranges.append({
                'title': '附录部分',
                'start': last_range['end'] + 1,
                'end': total_pages - 1
            })
    else:
        # 如果没有有效范围，将整个PDF作为一个范围
        ranges.append({
            'title': '完整文档',
            'start': 0,
            'end': total_pages - 1
        })
        
    return ranges

def split_pdf(input_pdf, output_dir, split_level):
    """
    根据指定层级的书签拆分PDF文件
    
    Args:
        input_pdf: 输入PDF文件路径
        output_dir: 输出目录
        split_level: 拆分的书签层级
    """
    # 创建输出目录
    output_dir = create_output_dir(output_dir)
    
    # 打开PDF文件
    pdf = PdfReader(input_pdf)
    total_pages = len(pdf.pages)
    print(f"PDF文件共有 {total_pages} 页")
    
    # 提取书签
    print(f"正在提取PDF书签 (层级: {split_level})...")
    bookmarks = extract_bookmarks(input_pdf, max_level=None)
    
    # 获取拆分范围 - 传入pdf读取器以协助页码解析
    ranges = get_page_ranges(bookmarks, total_pages, split_level, pdf)
    
    if not ranges:
        print("无法确定拆分范围，退出")
        return
    
    # 检查是否覆盖了所有页面
    covered_pages = set()
    for range_info in ranges:
        for page in range(range_info['start'], range_info['end'] + 1):
            covered_pages.add(page)
    
    if len(covered_pages) != total_pages:
        missing_pages = set(range(total_pages)) - covered_pages
        print(f"警告: 有 {len(missing_pages)} 页未被覆盖!")
        if len(missing_pages) < 20:  # 只显示少量缺失页面
            print(f"缺失的页面: {sorted(missing_pages)}")
    
    # 拆分PDF
    print(f"开始拆分PDF为 {len(ranges)} 个文件...")
    
    for i, range_info in enumerate(ranges):
        title = range_info['title']
        start_page = range_info['start']
        end_page = range_info['end']
        
        # 创建安全的文件名
        safe_title = sanitize_filename(title)
        output_filename = f"{i+1:02d}_{safe_title}.pdf"
        output_path = os.path.join(output_dir, output_filename)
        
        # 创建新的PDF
        pdf_writer = PdfWriter()
        
        # 添加页面
        for page_num in range(start_page, end_page + 1):
            try:
                if 0 <= page_num < total_pages:  # 确保页码在有效范围内
                    pdf_writer.add_page(pdf.pages[page_num])
                else:
                    print(f"警告: 页码 {page_num+1} 超出范围 (1-{total_pages})")
            except Exception as e:
                print(f"无法添加第 {page_num+1} 页: {e}")
                continue
        
        # 如果没有添加任何页面，跳过保存
        if len(pdf_writer.pages) == 0:
            print(f"警告: {output_filename} 没有有效页面，跳过保存")
            continue
        
        # 保存PDF
        try:
            with open(output_path, 'wb') as output_file:
                pdf_writer.write(output_file)
            
            print(f"已创建: {output_filename} (页码: {start_page+1}-{end_page+1}, 共 {end_page-start_page+1} 页)")
        except Exception as e:
            print(f"保存文件 '{output_filename}' 失败: {e}")
    
    print(f"PDF拆分完成，输出目录: {output_dir}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='根据书签层级拆分PDF文件')
    parser.add_argument('pdf_path', help='PDF文件路径')
    parser.add_argument('--level', type=int, default=0, 
                        help='拆分的书签层级，默认为0（顶层书签）')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='输出目录，默认为"split_<pdf文件名>"')
    parser.add_argument('--debug', action='store_true', help='开启调试输出')
    
    args = parser.parse_args()
    
    # 验证文件存在
    if not os.path.exists(args.pdf_path):
        print(f"错误: 文件 '{args.pdf_path}' 不存在")
        return 1
    
    # 设置默认输出目录
    if args.output_dir is None:
        pdf_name = Path(args.pdf_path).stem
        args.output_dir = f"split_{pdf_name}"
    
    # 拆分PDF
    try:
        split_pdf(args.pdf_path, args.output_dir, args.level)
        return 0
    except Exception as e:
        print(f"拆分PDF时出错: {e}")
        import traceback
        print(traceback.format_exc())
        return 1

if __name__ == "__main__":
    sys.exit(main()) 