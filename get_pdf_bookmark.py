from PyPDF2 import PdfReader
import sys
import json
import re

# 启用调试输出
DEBUG = False

def debug_print(*args, **kwargs):
    """调试输出函数"""
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)

def dump_object(obj, max_depth=2, indent=0):
    """递归打印对象的属性，用于调试"""
    if indent > max_depth:
        return "..."
    
    if isinstance(obj, (str, int, float, bool, type(None))):
        return repr(obj)
    
    if isinstance(obj, list):
        if not obj:
            return "[]"
        result = "[\n"
        for item in obj[:3]:  # 只显示前3个元素
            result += " " * (indent + 2) + dump_object(item, max_depth, indent + 2) + ",\n"
        if len(obj) > 3:
            result += " " * (indent + 2) + f"... ({len(obj) - 3} more items)"
        result += "\n" + " " * indent + "]"
        return result
    
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        result = "{\n"
        for k, v in list(obj.items())[:5]:  # 只显示前5个键值对
            result += " " * (indent + 2) + f"{k}: {dump_object(v, max_depth, indent + 2)},\n"
        if len(obj) > 5:
            result += " " * (indent + 2) + f"... ({len(obj) - 5} more items)"
        result += "\n" + " " * indent + "}"
        return result
    
    # 对于其他对象，尝试获取其属性
    result = f"{type(obj).__name__}(\n"
    attrs = {}
    
    # 尝试获取对象的属性
    for attr in dir(obj):
        if not attr.startswith("_") and attr != "title" and attr != "children":
            try:
                value = getattr(obj, attr)
                if not callable(value):
                    attrs[attr] = value
            except Exception:
                attrs[attr] = "<ERROR>"
    
    # 特殊处理title和children
    if hasattr(obj, 'title'):
        try:
            attrs['title'] = getattr(obj, 'title')
        except Exception:
            attrs['title'] = "<ERROR>"
    
    if hasattr(obj, 'children'):
        try:
            children = getattr(obj, 'children')
            if callable(children):
                attrs['children'] = "<callable>"
            else:
                attrs['children'] = children
        except Exception:
            attrs['children'] = "<ERROR>"
    
    # 输出属性
    for k, v in list(attrs.items())[:10]:  # 只显示前10个属性
        result += " " * (indent + 2) + f"{k}: {dump_object(v, max_depth - 1, indent + 2)},\n"
    if len(attrs) > 10:
        result += " " * (indent + 2) + f"... ({len(attrs) - 10} more attributes)"
    result += "\n" + " " * indent + ")"
    
    return result

def get_pdf_bookmarks(pdf_path):
    """获取PDF书签，返回书签列表"""
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        return reader.outline, reader

def is_bookmark_list(item):
    """判断是否为书签列表"""
    return isinstance(item, list)

def get_bookmark_title(bookmark):
    """获取书签标题"""
    return bookmark.title if hasattr(bookmark, 'title') else "无标题"

def get_bookmark_page(bookmark, pdf_reader):
    """尝试获取书签页码"""
    try:
        if hasattr(bookmark, 'page'):
            return bookmark.page
        elif '/Page' in bookmark:
            return pdf_reader.get_destination_page_number(bookmark) + 1
        elif '/D' in bookmark:
            # 处理目标对象
            dest = bookmark['/D']
            if isinstance(dest, list) and len(dest) > 0:
                # 第一个元素通常是页面引用
                page_ref = dest[0]
                # 尝试找到对应的页码
                for i, page in enumerate(pdf_reader.pages):
                    if page.indirect_reference == page_ref:
                        return i + 1
                # 如果未找到匹配，尝试解析引用编号
                if hasattr(page_ref, 'idnum'):
                    for i, page in enumerate(pdf_reader.pages):
                        if hasattr(page.indirect_reference, 'idnum') and page.indirect_reference.idnum == page_ref.idnum:
                            return i + 1
                    # 如果仍未找到，可能需要读取原始对象
                    try:
                        if hasattr(page_ref, 'get_object'):
                            obj = page_ref.get_object()
                            if isinstance(obj, dict) and '/StructParents' in obj:
                                # 这通常是页面对象的一个属性索引
                                return obj['/StructParents'] + 1
                    except Exception as e:
                        debug_print(f"尝试获取对象失败: {e}")
        
        # 如果是IndirectObject对象，尝试转换为实际页码
        if hasattr(bookmark, '__class__') and 'IndirectObject' in bookmark.__class__.__name__:
            # 尝试遍历所有页面，查找对应的引用
            try:
                for i, page in enumerate(pdf_reader.pages):
                    if page.indirect_reference == bookmark:
                        return i + 1
            except Exception as e:
                debug_print(f"通过比较引用查找页码失败: {e}")
                
            # 尝试通过对象ID查找页码
            if hasattr(bookmark, 'idnum'):
                try:
                    for i, page in enumerate(pdf_reader.pages):
                        if hasattr(page.indirect_reference, 'idnum') and page.indirect_reference.idnum == bookmark.idnum:
                            return i + 1
                except Exception as e:
                    debug_print(f"通过对象ID查找页码失败: {e}")
                
            # 如果上述方法都失败，返回对象ID作为页码估计
            if hasattr(bookmark, 'idnum'):
                # 对象ID通常大于实际页码，尝试通过简单算法估计
                estimated_page = min(bookmark.idnum // 2, len(pdf_reader.pages))
                debug_print(f"估计页码: {estimated_page} (基于对象ID: {bookmark.idnum})")
                return estimated_page
        
        return None
    except Exception as e:
        debug_print(f"获取页码出错: {e}")
        return None

def is_child_bookmark(title, parent_title):
    """判断一个书签是否是另一个书签的子书签（基于标题分析）"""
    # 1. 数字前缀法: "1 Chapter" -> "1.1 Section"
    if re.match(r'^\d+(\.\d+)*\s', parent_title) and re.match(r'^\d+(\.\d+)+\s', title):
        parent_prefix = re.match(r'^\d+(\.\d+)*', parent_title).group(0)
        child_prefix = re.match(r'^\d+(\.\d+)+', title).group(0)
        if child_prefix.startswith(parent_prefix + '.'):
            return True
    
    # 2. 嵌套深度: 如果子标题比父标题多一级点号或数字
    parent_parts = len(re.findall(r'\.', parent_title)) + 1
    child_parts = len(re.findall(r'\.', title)) + 1
    if parent_parts + 1 == child_parts and title.startswith(parent_title.split(' ')[0]):
        return True
    
    return False

def infer_bookmark_level(bookmarks):
    """尝试推断书签的层级关系"""
    if not bookmarks:
        return []
    
    result = []
    # 第一遍：复制所有书签，初始层级为0
    for bookmark in bookmarks:
        result.append({
            'title': bookmark.get('title', '无标题'),
            'page': bookmark.get('page'),
            'level': 0,
            'original_index': len(result)
        })
    
    # 第二遍：尝试推断层级关系
    for i in range(1, len(result)):
        for j in range(i):
            if is_child_bookmark(result[i]['title'], result[j]['title']):
                # 如果当前书签是之前某个书签的子书签，设置层级为父书签+1
                result[i]['level'] = result[j]['level'] + 1
                break
    
    # 移除辅助字段
    for item in result:
        if 'original_index' in item:
            del item['original_index']
    
    return result

def get_bookmark_children(bookmark):
    """获取书签的子书签"""
    try:
        if hasattr(bookmark, 'children'):
            if callable(bookmark.children):
                children = bookmark.children()  # 如果是方法
            else:
                children = bookmark.children    # 如果是属性
            
            if isinstance(children, list):
                return children
    except Exception as e:
        debug_print(f"获取子书签出错: {e}")
    return []  # 如果没有子书签或出错，返回空列表

def flatten_bookmarks(bookmarks, pdf_reader, level=0):
    """扁平化处理书签，返回所有书签的列表，每个书签包含层级信息"""
    # 检查书签结构
    if DEBUG:
        debug_print(f"正在处理书签，层级: {level}, 类型: {type(bookmarks)}")
        debug_print(dump_object(bookmarks))
    
    result = []
    
    # 如果是列表，处理每个元素
    if isinstance(bookmarks, list):
        for bookmark in bookmarks:
            result.extend(flatten_bookmarks(bookmark, pdf_reader, level))
        return result
    
    # 处理单个书签
    title = get_bookmark_title(bookmarks)
    page = get_bookmark_page(bookmarks, pdf_reader)
    
    # 添加当前书签
    result.append({
        'title': title,
        'page': page,
        'level': level
    })
    
    # 处理子书签，层级加1
    children = get_bookmark_children(bookmarks)
    if children:
        debug_print(f"书签 '{title}' 有 {len(children)} 个子书签")
    
    for child in children:
        result.extend(flatten_bookmarks(child, pdf_reader, level + 1))
    
    return result

def extract_bookmarks(pdf_path, max_level=None):
    """提取并打印PDF书签"""
    try:
        # 获取书签和PDF阅读器
        bookmarks, reader = get_pdf_bookmarks(pdf_path)
        
        debug_print("原始书签结构:")
        debug_print(dump_object(bookmarks, max_depth=3))
        
        # 扁平化处理书签
        flat_bookmarks = flatten_bookmarks(bookmarks, reader)
        
        debug_print(f"扁平化后获取到 {len(flat_bookmarks)} 个书签")
        for i, bm in enumerate(flat_bookmarks[:5]):
            debug_print(f"书签 {i+1}: {bm}")
        
        # 如果所有书签层级都是0，尝试推断层级
        all_level_zero = all(bm['level'] == 0 for bm in flat_bookmarks)
        if all_level_zero and len(flat_bookmarks) > 1:
            debug_print("所有书签层级都是0，尝试根据标题推断层级")
            flat_bookmarks = infer_bookmark_level(flat_bookmarks)
        
        # 打印书签
        if max_level is None:
            print(f"PDF书签完整结构 ({len(flat_bookmarks)} 个书签):")
        else:
            print(f"PDF书签结构 (最大层级: {max_level}, 共 {len(flat_bookmarks)} 个书签):")
        
        # 根据max_level过滤并打印书签
        displayed_count = 0
        for bookmark in flat_bookmarks:
            level = bookmark['level']
            if max_level is None or level <= max_level:
                indent = "  " * level
                title = bookmark['title']
                page = bookmark['page']
                
                # 增加层级和页码信息的详细输出
                level_info = f"[层级:{level}]"
                page_info = f"[页码:{page}]" if page else "[无页码]"
                print(f"{indent}{level_info} {title} {page_info}")
                displayed_count += 1
        
        print(f"显示了 {displayed_count}/{len(flat_bookmarks)} 个书签")
        return flat_bookmarks
            
    except Exception as e:
        print(f"处理PDF书签时出错: {str(e)}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        return []

# 使用示例
if __name__ == "__main__":
    import argparse
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='提取PDF书签')
    parser.add_argument('pdf_path', help='PDF文件路径')
    parser.add_argument('--max-level', type=int, default=None, 
                        help='最大显示层级，默认显示所有层级，0只显示顶层，1显示一级子标签，以此类推')
    parser.add_argument('--debug', action='store_true', help='开启调试输出')
    parser.add_argument('--infer-levels', action='store_true', help='尝试从标题推断层级关系')
    
    args = parser.parse_args()
    
    # 设置调试模式
    DEBUG = args.debug
    
    # 提取并打印书签
    extract_bookmarks(args.pdf_path, args.max_level)