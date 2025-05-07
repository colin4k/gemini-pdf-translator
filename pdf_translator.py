#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import glob
import base64
import io
import logging
from pathlib import Path
import json
import yaml

import google.generativeai as genai
import requests
from PIL import Image
import fitz  # PyMuPDF

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从config.yml读取配置
def load_config():
    """从config.yml加载配置"""
    config_path = Path("config.yml")
    if not config_path.exists():
        logger.error("未找到config.yml配置文件")
        exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        try:
            config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.error(f"解析config.yml出错: {str(e)}")
            exit(1)

# 加载配置
config = load_config()
API_KEY = config.get("api_key")
BASE_URL = config.get("base_url")
MODEL = config.get("model", "gemini-2.5-flash-preview-04-17")  # 默认模型

# 验证配置
if not API_KEY or API_KEY == "your_api_key_here":
    logger.error("请在config.yml中设置有效的api_key")
    exit(1)

# 配置Google Gemini API
genai.configure(api_key=API_KEY)
if BASE_URL:
    logger.info(f"使用自定义API基础URL: {BASE_URL}")
    genai.configure(transport="rest", client_options={"api_endpoint": BASE_URL})

# 目录设置
INPUT_DIR = "input"
OUTPUT_DIR = "output"

def ensure_directories():
    """确保输入和输出目录存在"""
    Path(INPUT_DIR).mkdir(exist_ok=True)
    Path(OUTPUT_DIR).mkdir(exist_ok=True)

def get_pdf_files():
    """获取input目录下的所有PDF文件"""
    return glob.glob(f"{INPUT_DIR}/*.pdf")

def clean_thinking_output(text):
    """
    清理Thinking模型输出中的思考过程，只保留最终结果
    
    Args:
        text: 模型返回的原始文本
    
    Returns:
        清理后的文本
    """
    # 使用空格替换制表符和多个空格，规范化文本
    result = re.sub(r'\t+| {2,}', ' ', text)
    
    # 检测是否有HTML内容（直接查找<html>、<!DOCTYPE html>或大量的<div>、<p>标签）
    html_pattern = r'<!DOCTYPE\s+html|<html|<body|<div|<p\s|<h[1-6]'
    direct_html = bool(re.search(html_pattern, result, re.IGNORECASE))
    
    # 如果文本看起来直接就是HTML，并且没有明显的思考过程标记，直接返回
    if direct_html and not any(marker in result.lower() for marker in 
                              ['thinking', '思考', '分析', '让我', '我的思路']):
        return result
    
    # 常见的Thinking标记模式
    thinking_patterns = [
        # 标签式标记
        r'<thinking>.*?</thinking>',
        r'\[thinking\].*?\[/thinking\]',
        r'【思考】.*?【\/思考】',
        r'【思考过程】.*?【结果】',
        r'《思考》.*?《\/思考》',
        
        # 文本式标记
        r'Thinking:.*?Answer:',
        r'思考过程:.*?最终答案:',
        r'思考:.*?回答:',
        r'我的思路:.*?最终结果:',
        r'分析:.*?结论:',
        
        # 语句式标记
        r'让我思考一下.*?最终的翻译结果如下:',
        r'我需要先分析.*?最终翻译如下:',
        r'首先，我会分析.*?最终的翻译是:',
        r'我将分步骤思考.*?完整翻译如下:',
        
        # 段落式标记
        r'我的思考过程：[\s\S]*?最终翻译结果：',
        r'分析与思考[\s\S]*?翻译结果[\s\S]*?：'
    ]
    
    # 应用所有模式进行替换
    for pattern in thinking_patterns:
        # re.DOTALL让.匹配包括换行符在内的所有字符
        result = re.sub(pattern, '', result, flags=re.DOTALL | re.IGNORECASE)
    
    # 最终结果标记
    final_markers = [
        # 英文标记
        r'Final answer:', r'Final result:', r'Final translation:',
        r'Final output:', r'Here is the translation:',
        
        # 中文标记
        r'最终答案:', r'最终结果:', r'最终的翻译结果:',
        r'最终输出:', r'最终翻译:', r'完整翻译:',
        r'翻译结果如下:', r'以下是翻译:', r'翻译内容:'
    ]
    
    # 尝试找到最终答案标记
    found_marker = False
    for marker in final_markers:
        if re.search(marker, result, re.IGNORECASE):
            # 找到最后一个标记，并只保留其后内容
            parts = re.split(marker, result, flags=re.IGNORECASE)
            if len(parts) > 1:
                result = parts[-1].strip()
                found_marker = True
                break  # 找到一个就处理并跳出循环
    
    # 如果没有找到明确的最终答案标记，尝试找到HTML内容的开始
    if not found_marker:
        # 寻找HTML结构的开始
        html_starts = [
            r'<!DOCTYPE\s+html', r'<html', r'<body', 
            r'<div', r'<p>', r'<h1>', r'<h2>', r'<h3>'
        ]
        
        for html_start in html_starts:
            html_match = re.search(html_start, result, re.IGNORECASE)
            if html_match:
                result = result[html_match.start():]
                break
    
    # 移除结尾可能的注释或解释
    result = re.sub(r'</html>.*$', '</html>', result, flags=re.DOTALL | re.IGNORECASE)
    
    # 移除可能的前导和尾随空白
    return result.strip()

def translate_pdf_with_gemini(pdf_path, pdf_filename):
    """使用Gemini API翻译PDF并输出HTML"""
    # 加载PDF文件
    with open(pdf_path, 'rb') as f:
        pdf_content = f.read()
    
    # 创建Gemini模型实例
    model = genai.GenerativeModel(MODEL)
    
    # 构建提示词
    prompt = "请在保持排版不变的情况下，将该pdf文件翻译为中文，并输出html格式，涉及到图像资源时需要输出图像资源的链接，例如<img src=\"xxx\" alt=\"xxx\">。不要输出代码块标记，也不要输出如'==Start of OCR for page xx=='等标记处理过程的文本，直接输出HTML内容。"
    
    # 初始化translated_html为None
    translated_html = None
    
    try:
        # 创建请求
        response = model.generate_content([
            prompt,
            {"mime_type": "application/pdf", "data": pdf_content}
        ])
        
        logger.info(f"API响应类型: {type(response)}")
        
        # 改进的响应处理逻辑
        if hasattr(response, 'candidates') and response.candidates and len(response.candidates) > 0:
            # 处理有candidates结构的响应
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts'):
                    # 遍历parts找到最后一个TextPart
                    last_text_part = None
                    for part in candidate.content.parts:
                        if hasattr(part, 'text'):
                            last_text_part = part
                    
                    if last_text_part is not None:
                        translated_html = last_text_part.text
                elif hasattr(candidate.content, 'text'):
                    # 直接获取content.text
                    translated_html = candidate.content.text
        # 检查旧版API格式
        elif hasattr(response, 'text'):
            # 旧版API格式直接有text属性
            translated_html = response.text
        elif hasattr(response, 'content'):
            # 检查content属性
            if hasattr(response.content, 'text'):
                translated_html = response.content.text
            elif hasattr(response.content, 'parts') and response.content.parts:
                # 处理parts列表
                for part in response.content.parts:
                    if hasattr(part, 'text'):
                        translated_html = part.text
                        break
        
        # 如果以上方法都失败，尝试更通用的方法
        if translated_html is None:
            logger.warning("标准方法无法获取响应文本，尝试更通用的方法")
            
            # 尝试将响应对象转为字典
            try:
                if hasattr(response, 'model_dump'):
                    response_dict = response.model_dump()
                elif hasattr(response, '__dict__'):
                    response_dict = vars(response)
                else:
                    response_dict = dict(response)
                
                logger.info(f"响应字典结构: {str(list(response_dict.keys())[:10])}...")
                
                # 尝试从字典中提取文本
                if 'text' in response_dict:
                    translated_html = response_dict['text']
                elif 'candidates' in response_dict and response_dict['candidates']:
                    candidate = response_dict['candidates'][0]
                    if 'content' in candidate and 'parts' in candidate['content']:
                        for part in candidate['content']['parts']:
                            if 'text' in part:
                                translated_html = part['text']
                                break
            except Exception as e:
                logger.error(f"尝试解析响应字典时出错: {str(e)}")
        
        # 如果仍然获取不到文本，尝试更粗暴的方法
        if translated_html is None:
            logger.warning("无法通过结构化方法获取响应文本，尝试字符串解析")
            # 将整个响应转为字符串，尝试找到HTML内容
            response_str = str(response)
            # 尝试查找HTML标记
            html_pattern = r'<!DOCTYPE\s+html|<html|<body|<div\s|<p\s|<h[1-6]\s'
            html_match = re.search(html_pattern, response_str, re.IGNORECASE)
            if html_match:
                # 提取HTML内容
                start_idx = html_match.start()
                # 尝试找到</html>结尾
                end_match = re.search(r'</html>', response_str[start_idx:], re.IGNORECASE)
                if end_match:
                    translated_html = response_str[start_idx:start_idx + end_match.end()]
                else:
                    # 如果没有</html>，就取到字符串结尾
                    translated_html = response_str[start_idx:]
        
        # 如果所有方法都失败，引发异常
        if translated_html is None:
            error_msg = f"无法从响应中提取文本。响应类型: {type(response)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
    except Exception as e:
        logger.error(f"调用API翻译PDF时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    
    # 如果是Thinking模型，清理思考过程
    if "thinking" in MODEL.lower():
        logger.info("检测到Thinking模型，正在清理思考过程...")
        translated_html = clean_thinking_output(translated_html)
        logger.info(f"清理后的内容长度: {len(translated_html)} 字符")
    
    # 去除可能的代码块标记
    if translated_html.startswith("```html") or translated_html.startswith("```HTML"):
        # 找到第一个换行符之后的内容
        translated_html = translated_html.split("\n", 1)[1] if "\n" in translated_html else translated_html
    
    if translated_html.endswith("```"):
        # 去除结尾的```
        translated_html = translated_html.rsplit("```", 1)[0]
    
    # 更彻底的处理：匹配任何```开头的代码块标记
    if re.match(r'^```\w*\s*\n', translated_html):
        # 使用正则表达式去除开头的```语言标记及其后的换行
        translated_html = re.sub(r'^```\w*\s*\n', '', translated_html)
    
    # 记录处理后的HTML内容长度
    logger.info(f"处理后的HTML内容长度: {len(translated_html)} 字符")
    
    return translated_html

def extract_images_from_pdf(pdf_path, output_dir, pdf_basename):
    """
    从PDF中提取图像，并统一命名为"PDF文件名+序号"
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录
        pdf_basename: PDF文件基名（不含扩展名）
    
    Returns:
        生成的图像文件名列表
    """
    # 确保PDF文件存在
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 打开PDF文件
    pdf_document = fitz.open(pdf_path)
    image_files = []
    
    # 图像计数器
    img_counter = 1
    
    # 遍历每一页提取图像
    for page_num in range(len(pdf_document)):
        page = pdf_document[page_num]
        image_list = page.get_images()
        
        # 遍历页面上的每张图片
        for img_index, img in enumerate(image_list):
            # 获取图片信息
            xref = img[0]
            base_image = pdf_document.extract_image(xref)
            image_bytes = base_image["image"]
            
            # 将图片字节转换为PIL Image对象
            pil_image = Image.open(io.BytesIO(image_bytes))
            
            # 生成统一的图像文件名：PDF文件名+序号
            image_filename = f"{pdf_basename}_{img_counter}.png"
            image_path = os.path.join(output_dir, image_filename)
            
            # 保存图片为PNG格式
            pil_image.save(image_path, format="PNG")
            logger.info(f"保存图像: {image_filename}")
            
            # 添加到图像文件列表
            image_files.append(image_filename)
            
            # 增加计数器
            img_counter += 1
    
    pdf_document.close()
    return image_files

def process_html_with_images(html_content, image_files, pdf_basename):
    """
    处理HTML内容，将所有img标签的src属性替换为统一的文件名格式
    
    Args:
        html_content: HTML内容
        image_files: 提取的图像文件名列表
        pdf_basename: PDF文件基名（不含扩展名）
    
    Returns:
        处理后的HTML内容
    """
    # 查找HTML中的所有img标签
    img_tags = re.findall(r'<img[^>]*>', html_content)
    logger.info(f"HTML中找到{len(img_tags)}个图像标签")
    
    # 处理后的HTML内容
    processed_html = html_content
    
    # 如果提取的图像数量与HTML中的img标签数量不匹配，输出警告
    if len(img_tags) != len(image_files):
        logger.warning(f"HTML中的图像标签数量({len(img_tags)})与提取的图像数量({len(image_files)})不匹配")
    
    # 替换所有img标签的src属性
    for i, img_tag in enumerate(img_tags):
        if i < len(image_files):
            # 获取对应的图像文件名
            image_filename = image_files[i]
            
            # 提取alt文本
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', img_tag)
            alt_text = alt_match.group(1) if alt_match else f"图片{i+1}"
            
            # 创建新的img标签
            new_img_tag = f'<img src="{image_filename}" alt="{alt_text}">'
            
            # 替换原始标签
            processed_html = processed_html.replace(img_tag, new_img_tag, 1)
            logger.info(f"替换图像标签: {img_tag} -> {new_img_tag}")
    
    return processed_html

def main():
    """主函数"""
    ensure_directories()
    pdf_files = get_pdf_files()
    
    if not pdf_files:
        logger.warning(f"在{INPUT_DIR}目录下未找到PDF文件")
        return
    
    logger.info(f"找到{len(pdf_files)}个PDF文件待处理")
    
    for pdf_path in pdf_files:
        pdf_filename = os.path.basename(pdf_path)
        pdf_basename = os.path.splitext(pdf_filename)[0]
        logger.info(f"开始处理: {pdf_filename}")
        
        try:
            # 1. 使用Gemini API翻译PDF为HTML
            logger.info(f"使用Gemini API翻译{pdf_filename}")
            translated_html = translate_pdf_with_gemini(pdf_path, pdf_filename)
            
            # 2. 提取图像并统一命名
            logger.info(f"从{pdf_filename}提取图像并统一命名")
            image_files = extract_images_from_pdf(pdf_path, OUTPUT_DIR, pdf_basename)
            
            # 3. 处理HTML，替换图像标签的src属性
            logger.info(f"处理{pdf_filename}的HTML内容")
            final_html = process_html_with_images(translated_html, image_files, pdf_basename)
            
            # 4. 保存HTML文件
            output_html_path = os.path.join(OUTPUT_DIR, f"{pdf_basename}.html")
            with open(output_html_path, 'w', encoding='utf-8') as f:
                f.write(final_html)
            
            logger.info(f"成功处理{pdf_filename}，输出文件：{output_html_path}")
            
        except Exception as e:
            logger.error(f"处理{pdf_filename}时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    logger.info("所有PDF文件处理完成")

if __name__ == "__main__":
    main() 