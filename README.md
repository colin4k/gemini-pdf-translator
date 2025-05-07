# PDF翻译工具

使用Google Gemini API将PDF文件翻译为中文HTML格式，同时提取图像。本工具采用OpenAI兼容方式调用Gemini API。

## 功能

1. 读取`input`目录下的所有PDF文件
2. 使用Google Gemini API将PDF内容翻译为中文
3. 保持原PDF排版的同时，输出为HTML格式
4. 提取PDF中的图像，并根据图片描述文本命名
5. 将HTML和图像保存到`output`目录
6. 支持通过OpenAI兼容接口调用Gemini API
7. 使用config.yml配置API密钥、基础URL和模型

## 使用方法

1. 安装依赖：`pip install -r requirements.txt`
2. 将PDF文件放入`input`目录
3. 编辑`config.yml`文件，设置API密钥、基础URL和模型：
   ```yaml
   # Gemini API配置
   api_key: "your_api_key_here"  # 替换为你的实际API密钥
   base_url: "https://generativelanguage.googleapis.com/v1beta/openai/"
   model: "gemini-2.5-flash-preview-04-17"  # 使用的Gemini模型
   ```
4. 运行脚本：`python pdf_translator.py`
5. 查看`output`目录中的结果文件

## OpenAI兼容接口

本工具使用OpenAI兼容方式调用Gemini API，主要变更：

```python
# 从config.yml加载配置
with open("config.yml", 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    API_KEY = config.get("api_key")
    BASE_URL = config.get("base_url")
    MODEL = config.get("model")

# 创建OpenAI客户端（实际使用Gemini API）
client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)

# 调用API
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "用户内容"}
    ]
)

# 获取结果
result = response.choices[0].message.content
```

## 可用的Gemini模型

在config.yml中可以配置以下模型：

- `gemini-2.5-flash-preview-04-17` - Gemini 2.5 Flash（快速响应）
- `gemini-2.5-pro-preview-04-17` - Gemini 2.5 Pro（更强大的理解能力）
- `gemini-2.0-flash` - Gemini 2.0 Flash
- `gemini-2.0-pro` - Gemini 2.0 Pro

## 注意事项

- 需要Google Gemini API密钥
- 图像提取基于图片下方的描述文本
- 程序会自动创建所需的目录结构
- 依赖OpenAI库而非google-generativeai库
- 配置信息存储在config.yml文件中 