import os
import glob
import re

def get_latest_post():
    """获取 _posts 目录下最新修改的 Markdown 文件"""
    # 递归查找 _posts 目录下所有的 .md 文件
    list_of_files = glob.glob('_posts/**/*.md', recursive=True)
    if not list_of_files:
        return None
    # 按照文件的最后修改时间排序，拿到最新的一篇
    latest_file = max(list_of_files, key=os.path.getmtime)
    return latest_file

def check_file(filepath):
    print(f"🔍 正在为你体检最新笔记: {filepath}\n")
    issues = 0

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line_num = i + 1
        
        # 1. 检查致命的中文双引号 (常出现在 {:file=“...”} 这种语法里)
        if re.search(r'\{[^\}]*[“”][^\}]*\}', line):
            print(f"❌ [行 {line_num}] 发现全角(中文)引号！请改成英文半角引号 \"\"")
            print(f"   代码: {line.strip()}\n")
            issues += 1

        # 2. 检查图片/链接中的反斜杠 \ (Windows 用户专属天坑)
        if re.search(r'\]\([^)]*\\+[^)]*\)', line):
            print(f"❌ [行 {line_num}] 路径中包含反斜杠 `\\`！网页只认正斜杠 `/`")
            print(f"   代码: {line.strip()}\n")
            issues += 1

        # 3. 检查括号为空的图片或链接 ![]()
        if re.search(r'\]\(\s*\)', line):
            print(f"❌ [行 {line_num}] 存在空的链接/图片括号 ()！会导致编译报错")
            print(f"   代码: {line.strip()}\n")
            issues += 1

        # 4. 检查是否有类似 /src 这种无后缀的假路径测试 (排除代码块内的情况)
        if re.search(r'\]\([a-zA-Z0-9/_-]+\)', line) and not line.strip().startswith('`'):
            # 如果链接没有 .html, .jpg, .png 等后缀，也没有 http，大概率是假路径
            path = re.search(r'\]\((.*?)\)', line).group(1)
            if not path.startswith('http') and not path.startswith('#') and '.' not in path:
                print(f"⚠️ [行 {line_num}] 发现可疑的内部链接 `({path})`，请确认它真实存在！")
                print(f"   代码: {line.strip()}\n")
                issues += 1

    if issues == 0:
        print("✅ 体检通过！没有任何常见格式问题，可以放心上传了。")
        return True
    else:
        print(f"🚨 体检结束，共发现 {issues} 个潜在问题，请在 VS Code 里修复它们后再上传！")
        return False

if __name__ == "__main__":
    latest_post = get_latest_post()
    if latest_post:
        check_file(latest_post)
    else:
        print("🤷 没在 _posts 文件夹里找到任何 markdown 笔记。")