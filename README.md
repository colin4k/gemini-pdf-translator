# PDF翻译工具

使用Google Gemini API将PDF文件翻译为中文HTML格式，同时提取图像，并支持生成EPUB电子书。

## 功能

1. 读取`input`目录下的所有PDF文件
2. 使用Google Gemini API将PDF内容翻译为中文
3. 尽可能保持原PDF排版的同时，输出为HTML格式
4. 提取PDF中的图像，并根据图片描述文本命名
5. 将HTML和图像保存到`output`目录
6. 支持将多个HTML文件合并为一个EPUB电子书
7. 使用config.yml配置API密钥和模型

## 使用方法

1. 安装依赖：`pip install -r requirements.txt`
2. 将PDF文件放入`input`目录
3. 复制`config.yml.example`文件为`config.yml`，设置API密钥和模型：
   ```yaml
   # Gemini API配置
   api_key: "your_api_key_here"  # 替换为你的实际API密钥
   base_url: "" #可以不用修改，保持为空
   model: "gemini-2.5-flash-preview-04-17"  # 使用的Gemini模型
   ```
4. 运行翻译脚本：`python pdf_translator.py`
5. 查看`output`目录中的HTML和图像文件
6. 运行EPUB生成脚本：`python html_to_epub.py`
7. 在`epub`目录中查看生成的EPUB文件

## 目录结构

```
.
├── input/          # 存放待翻译的PDF文件
├── output/         # 存放翻译后的HTML和图像文件
├── epub/          # 存放生成的EPUB文件
├── pdf_translator.py  # PDF翻译主程序
├── html_to_epub.py   # EPUB生成程序
├── config.yml     # 配置文件
└── requirements.txt  # 依赖包列表
```

## 可用的Gemini模型

在config.yml中可以配置以下模型：

- `gemini-2.5-flash-preview-04-17` - Gemini 2.5 Flash（快速响应）
- `gemini-2.5-pro-preview-03-25` - Gemini 2.5 Pro（更强大的理解能力）

## EPUB功能

生成的EPUB电子书具有以下特点：

1. 自动合并所有HTML文件为一个EPUB
2. 尽可能保持原文档的排版和样式
3. 支持图片、表格等富媒体内容
4. 自动生成目录
5. 优化的中文排版和字体支持
6. 响应式图片布局

## 注意事项

- 需要Google Gemini API密钥
- 图像提取基于图片下方的描述文本
- 程序会自动创建所需的目录结构
- 使用google-generativeai库直接调用Gemini API
- 配置信息存储在config.yml文件中
- EPUB生成需要安装ebooklib和beautifulsoup4库 