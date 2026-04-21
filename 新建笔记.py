import os
import re
from datetime import datetime, timezone, timedelta

def create_post():
    print("📝 Chirpy 笔记自动化工具 (增强版)\n")

    # 1. 收集文章基础信息
    title = input("👉 1. 请输入文章标题 (必填): ").strip()
    if not title:
        print("❌ 标题不能为空！")
        return

    cat1 = input("👉 2. 请输入主分类 (默认: 力扣刷题): ").strip() or "力扣刷题"
    cat2 = input("👉 3. 请输入子分类 (可选，直接回车则无子分类): ").strip()
    tags_input = input("👉 4. 请输入标签 (用逗号分隔，默认: leetcode): ").strip() or "leetcode"

    # 2. 获取当前时间 (东八区)
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")
    date_file = now.strftime("%Y-%m-%d")
    date_fm = now.strftime("%Y-%m-%d %H:%M:%S +0800")

    # 3. 构造按月份整理的目录路径
    # 路径格式: _posts/2026/04/
    target_dir = os.path.join("_posts", year_str, month_str)
    
    # 4. 生成合法的文件名
    slug = re.sub(r'[^\w\s-]', '', title).strip().lower()
    slug = re.sub(r'[-\s]+', '-', slug)
    filename = f"{date_file}-{slug}.md"
    filepath = os.path.join(target_dir, filename)

    # 5. 处理分类逻辑
    # 如果子分类为空，则只显示主分类
    if cat2:
        categories_str = f"[{cat1}, {cat2}]"
    else:
        categories_str = f"[{cat1}]"

    # 6. 处理标签
    tags = [t.strip().lower() for t in tags_input.split(',')]
    tags_str = ", ".join(tags)

    # 7. 生成 Front Matter 内容
    content = f"""---
title: {title}
date: {date_fm}
categories: {categories_str}
tags: [{tags_str}]
---

从这里开始记录你的笔记...
"""

    # 8. 执行创建
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n✅ 成功生成！")
        print(f"📂 存放目录: {target_dir}")
        print(f"📄 文件名称: {filename}")
    except Exception as e:
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    create_post()