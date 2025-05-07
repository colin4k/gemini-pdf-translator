#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import glob
import logging
from pathlib import Path
import uuid
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 目录设置
OUTPUT_DIR = "output"
EPUB_DIR = "epub"

def ensure_directories():
    """确保输出目录存在"""
    Path(EPUB_DIR).mkdir(exist_ok=True)

def get_html_files():
    """获取output目录下的所有HTML文件"""
    html_files = glob.glob(f"{OUTPUT_DIR}/*.html")
    # 按文件名自然排序
    html_files.sort(key=lambda f: os.path.basename(f))
    return html_files

def get_images_from_all_html():
    """
    获取所有HTML文件中引用的图像文件
    
    Returns:
        图像文件路径列表
    """
    html_files = get_html_files()
    all_images = set()
    
    for html_path in html_files:
        images = get_images_for_html(html_path)
        all_images.update(images)
    
    return list(all_images)

def get_images_for_html(html_path):
    """
    获取HTML文件中引用的所有图像文件
    
    Args:
        html_path: HTML文件路径
    
    Returns:
        图像文件路径列表
    """
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 解析HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 找出所有img标签
    img_tags = soup.find_all('img')
    
    # 提取src属性
    image_files = []
    for img in img_tags:
        if 'src' in img.attrs:
            image_path = os.path.join(OUTPUT_DIR, img['src'])
            if os.path.exists(image_path):
                image_files.append(image_path)
            else:
                logger.warning(f"图像文件不存在: {image_path}")
    
    return image_files

def get_html_title(html_path):
    """
    从HTML文件中提取标题
    
    Args:
        html_path: HTML文件路径
    
    Returns:
        HTML标题或文件名
    """
    basename = os.path.splitext(os.path.basename(html_path))[0]
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 解析HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 尝试获取title标签内容
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    
    # 尝试获取第一个h1标签内容
    h1 = soup.find('h1')
    if h1 and h1.get_text():
        return h1.get_text().strip()
    
    # 返回文件名作为标题
    return basename

def create_single_epub_from_all_html(output_filename="all_documents"):
    """
    将output目录下的所有HTML文件合并为一个EPUB文件
    
    Args:
        output_filename: 输出的EPUB文件名（不含扩展名）
    
    Returns:
        EPUB文件路径
    """
    html_files = get_html_files()
    
    if not html_files:
        logger.warning(f"在{OUTPUT_DIR}目录下未找到HTML文件")
        return None
    
    logger.info(f"找到{len(html_files)}个HTML文件将合并为一个EPUB")
    
    # 创建EPUB book
    book = epub.EpubBook()
    
    # 设置元数据
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(output_filename)
    book.set_language('zh-CN')
    
    # 创建CSS样式
    style = '''
    body {
        font-family: "Noto Serif CJK SC", "Source Han Serif CN", "Microsoft YaHei", "SimSun", sans-serif;
        line-height: 1.6;
        margin: 0 5%;
        text-align: justify;
    }
    img {
        max-width: 100%;
        height: auto;
        display: block;
        margin: 1em auto;
    }
    h1, h2, h3, h4, h5, h6 {
        margin-top: 1.5em;
        margin-bottom: 0.8em;
        font-weight: bold;
    }
    p {
        margin: 0.8em 0;
        text-indent: 2em;
    }
    table {
        border-collapse: collapse;
        margin: 1em 0;
        width: 100%;
    }
    th, td {
        border: 1px solid #ddd;
        padding: 8px;
    }
    th {
        background-color: #f2f2f2;
        text-align: center;
    }
    code {
        font-family: "Noto Sans Mono CJK SC", monospace;
        background-color: #f5f5f5;
        padding: 2px 4px;
        border-radius: 3px;
    }
    pre {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 5px;
        overflow-x: auto;
        white-space: pre-wrap;
    }
    blockquote {
        border-left: 3px solid #ccc;
        margin: 1em 0;
        padding-left: 1em;
        color: #666;
    }
    .chapter-title {
        text-align: center;
        margin: 2em 0;
        font-size: 1.5em;
        font-weight: bold;
    }
    '''
    
    # 添加CSS文件
    css_file = epub.EpubItem(
        uid="style_default",
        file_name="style/default.css",
        media_type="text/css",
        content=style
    )
    book.add_item(css_file)
    
    # 创建封面
    cover_chapter = epub.EpubHtml(
        title="封面",
        file_name="cover.xhtml",
        lang="zh-CN"
    )
    
    # 设置封面内容
    cover_content = f'''
    <html>
    <head>
        <title>{output_filename}</title>
        <link rel="stylesheet" href="style/default.css" type="text/css" />
    </head>
    <body>
        <div style="text-align: center; padding-top: 20%;">
            <h1>{output_filename}</h1>
            <p style="text-indent: 0; margin-top: 2em;">由PDF翻译生成</p>
        </div>
    </body>
    </html>
    '''
    cover_chapter.content = cover_content
    book.add_item(cover_chapter)
    
    # 创建目录页
    toc_chapter = epub.EpubHtml(
        title="目录",
        file_name="toc.xhtml",
        lang="zh-CN"
    )
    
    toc_content = '''
    <html>
    <head>
        <title>目录</title>
        <link rel="stylesheet" href="style/default.css" type="text/css" />
    </head>
    <body>
        <h1 class="chapter-title">目录</h1>
        <nav>
            <ol>
    '''
    
    # 为每个HTML文件创建一个章节
    chapters = [cover_chapter, toc_chapter]
    chapter_titles = []
    
    for i, html_path in enumerate(html_files):
        # 获取HTML文件标题
        chapter_title = get_html_title(html_path)
        chapter_titles.append(chapter_title)
        
        # 将文件内容读入BeautifulSoup
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 修正HTML结构
        if not soup.html:
            new_soup = BeautifulSoup('<html><head></head><body></body></html>', 'html.parser')
            new_soup.body.extend(soup.contents)
            soup = new_soup
        
        if not soup.head:
            soup.html.insert(0, soup.new_tag('head'))
        
        # 确保有标题
        if not soup.title:
            title_tag = soup.new_tag('title')
            title_tag.string = chapter_title
            soup.head.append(title_tag)
        
        # 替换所有图像路径
        for img in soup.find_all('img'):
            if 'src' in img.attrs:
                img_filename = os.path.basename(img['src'])
                img['src'] = f'images/{img_filename}'
        
        # 添加样式
        link_tag = soup.new_tag('link')
        link_tag['rel'] = 'stylesheet'
        link_tag['href'] = 'style/default.css'
        link_tag['type'] = 'text/css'
        soup.head.append(link_tag)
        
        # 创建章节
        chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=f'chapter_{i+1}.xhtml',
            lang='zh-CN'
        )
        
        # 添加章节标题
        if soup.body and not soup.body.find(['h1', 'h2', 'h3']):
            chapter_heading = soup.new_tag('h1')
            chapter_heading['class'] = 'chapter-title'
            chapter_heading.string = chapter_title
            soup.body.insert(0, chapter_heading)
        
        # 设置章节内容
        chapter.content = str(soup)
        chapter.add_item(css_file)
        
        # 添加到书中
        book.add_item(chapter)
        chapters.append(chapter)
        
        # 添加到目录内容
        toc_content += f'<li><a href="chapter_{i+1}.xhtml">{chapter_title}</a></li>\n'
    
    # 完成目录内容
    toc_content += '''
            </ol>
        </nav>
    </body>
    </html>
    '''
    
    toc_chapter.content = toc_content
    book.add_item(toc_chapter)
    
    # 添加所有图像
    all_images = get_images_from_all_html()
    for image_path in all_images:
        img_filename = os.path.basename(image_path)
        
        # 避免重复添加
        if any(item.file_name == f"images/{img_filename}" for item in book.items):
            continue
            
        try:
            with open(image_path, 'rb') as img_file:
                image_content = img_file.read()
                
            # 根据文件扩展名确定MIME类型
            extension = os.path.splitext(img_filename)[1].lower()
            if extension == '.jpg' or extension == '.jpeg':
                media_type = 'image/jpeg'
            elif extension == '.png':
                media_type = 'image/png'
            elif extension == '.gif':
                media_type = 'image/gif'
            else:
                media_type = 'image/png'  # 默认使用PNG
            
            # 创建图像项
            image_item = epub.EpubItem(
                uid=f"image_{img_filename.replace('.', '_').replace(' ', '_')}",
                file_name=f"images/{img_filename}",
                media_type=media_type,
                content=image_content
            )
            book.add_item(image_item)
        except Exception as e:
            logger.error(f"添加图像 {img_filename} 时出错: {str(e)}")
    
    # 创建导航目录
    book.toc = [epub.Link('toc.xhtml', '目录', 'toc')]
    
    # 添加每个章节到目录
    for i, title in enumerate(chapter_titles):
        book.toc.append(
            epub.Link(f'chapter_{i+1}.xhtml', title, f'chapter_{i+1}')
        )
    
    # 添加默认的NCX和Nav文件
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # 定义书脊
    book.spine = ['nav'] + chapters
    
    # 将EPUB保存到文件
    epub_path = os.path.join(EPUB_DIR, f"{output_filename}.epub")
    epub.write_epub(epub_path, book, {})
    
    logger.info(f"成功创建EPUB文件: {epub_path}")
    return epub_path

def main():
    """主函数"""
    ensure_directories()
    
    try:
        # 创建合并所有HTML的EPUB文件
        epub_path = create_single_epub_from_all_html("合并文档")
        
        if epub_path:
            logger.info(f"成功将所有HTML文件合并为一个EPUB文件: {epub_path}")
        else:
            logger.warning("未能创建EPUB文件")
            
    except Exception as e:
        logger.error(f"创建EPUB文件时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    
    logger.info("处理完成")

if __name__ == "__main__":
    main() 