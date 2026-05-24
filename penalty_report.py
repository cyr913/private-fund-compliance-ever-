import os
import re
import time
import json
import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import httpx
from openai import OpenAI

# ---------- 配置 ----------
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
FEISHU_WEBHOOK = os.environ["FEISHU_WEBHOOK"]
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
}

def safe_request(url, max_retries=3, timeout=30):
    """带重试的请求"""
    for i in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.encoding = resp.apparent_encoding or 'utf-8'
            if resp.status_code == 200:
                return resp
            else:
                print(f"  状态码 {resp.status_code}，重试 {i+1}/{max_retries}")
        except Exception as e:
            print(f"  请求异常: {e}，重试 {i+1}/{max_retries}")
        time.sleep(2)
    return None

# =============================================
# 一、基金业协会纪律处分
# =============================================

def fetch_amac_discipline_pages(max_pages=5):
    """
    抓取基金业协会纪律处分列表（多页）
    来源：https://www.amac.org.cn/discipline/
    """
    print("=" * 50)
    print("开始抓取【基金业协会纪律处分】")
    print("=" * 50)
    
    all_cases = []
    
    for page in range(1, max_pages + 1):
        print(f"\n正在抓取第 {page} 页...")
        
        if page == 1:
            url = "https://www.amac.org.cn/discipline/"
        else:
            url = f"https://www.amac.org.cn/discipline/index_{page}.html"
        
        resp = safe_request(url)
        if not resp:
            print(f"  第 {page} 页请求失败，停止翻页")
            break
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 尝试多种可能的列表选择器
        items = soup.select('.news-list li, .list-box li, .discipline-list li, .main-list li, .list-item')
        
        if not items:
            print(f"  第 {page} 页未找到列表项，可能已到最后一页")
            break
        
        for item in items:
            try:
                link_tag = item.find('a')
                date_tag = item.find('span', class_='date') or item.find('em') or item.find('time')
                
                if not link_tag:
                    continue
                
                title = link_tag.get('title', '') or link_tag.get_text(strip=True)
                link = link_tag.get('href', '')
                date_str = date_tag.get_text(strip=True) if date_tag else ''
                
                # 补全链接
                if link and not link.startswith('http'):
                    link = 'https://www.amac.org.cn' + link
                
                # 只保留私募相关
                if any(kw in title for kw in ['私募', '基金', '管理人', '处分', '处罚', '纪律']):
                    all_cases.append({
                        'title': title,
                        'link': link,
                        'date': date_str,
                        'source': '基金业协会'
                    })
            except Exception as e:
                print(f"  解析条目异常: {e}")
        
        print(f"  第 {page} 页抓取到 {len(all_cases)} 条累计")
        time.sleep(2)  # 礼貌等待
    
    print(f"\n基金业协会共抓取 {len(all_cases)} 条相关案例")
    return all_cases

# =============================================
# 二、证监会行政处罚
# =============================================

def fetch_csrc_penalties_pages(max_pages=5):
    """
    抓取证监会行政处罚（多页）
    来源：http://www.csrc.gov.cn/csrc/c100028/common_list.shtml
    """
    print("\n" + "=" * 50)
    print("开始抓取【证监会行政处罚】")
    print("=" * 50)
    
    all_cases = []
    
    for page in range(1, max_pages + 1):
        print(f"\n正在抓取第 {page} 页...")
        
        if page == 1:
            url = "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"
        else:
            url = f"http://www.csrc.gov.cn/csrc/c100028/common_list_{page}.shtml"
        
        resp = safe_request(url)
        if not resp:
            print(f"  第 {page} 页请求失败，停止翻页")
            break
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        items = soup.select('.list-item, .news-list li, .common-list li, .list-content li')
        
        if not items:
            print(f"  第 {page} 页未找到列表项")
            break
        
        for item in items:
            try:
                link_tag = item.find('a')
                date_tag = item.find('span', class_='date') or item.find('em')
                
                if not link_tag:
                    continue
                
                title = link_tag.get('title', '') or link_tag.get_text(strip=True)
                link = link_tag.get('href', '')
                date_str = date_tag.get_text(strip=True) if date_tag else ''
                
                if link and not link.startswith('http'):
                    link = 'http://www.csrc.gov.cn' + link
                
                if any(kw in title for kw in ['私募', '基金', '管理人']):
                    all_cases.append({
                        'title': title,
                        'link': link,
                        'date': date_str,
                        'source': '证监会'
                    })
            except Exception as e:
                print(f"  解析条目异常: {e}")
        
        print(f"  第 {page} 页抓取到 {len(all_cases)} 条累计")
        time.sleep(2)
    
    print(f"\n证监会共抓取 {len(all_cases)} 条相关案例")
    return all_cases

# =============================================
# 三、各地方证监局处罚
# =============================================

# 重点关注的私募集中地区证监局
LOCAL_CSRC = {
    "上海证监局": "http://www.csrc.gov.cn/shanghai/c103989/common_list.shtml",
    "深圳证监局": "http://www.csrc.gov.cn/shenzhen/c104110/common_list.shtml",
    "北京证监局": "http://www.csrc.gov.cn/beijing/c104084/common_list.shtml",
    "广东证监局": "http://www.csrc.gov.cn/guangdong/c104084/common_list.shtml",
    "浙江证监局": "http://www.csrc.gov.cn/zhejiang/c104091/common_list.shtml",
    "江苏证监局": "http://www.csrc.gov.cn/jiangsu/c104101/common_list.shtml",
}

def fetch_local_csrc_penalties(max_pages=3):
    """抓取各地方证监局处罚"""
    print("\n" + "=" * 50)
    print("开始抓取【各地证监局处罚】")
    print("=" * 50)
    
    all_cases = []
    
    for bureau_name, base_url in LOCAL_CSRC.items():
        print(f"\n正在抓取【{bureau_name}】...")
        bureau_cases = 0
        
        for page in range(1, max_pages + 1):
            if page == 1:
                url = base_url
            else:
                # 不同证监局的翻页 URL 规则可能不同
                url = base_url.replace('.shtml', f'_{page}.shtml')
            
            resp = safe_request(url)
            if not resp:
                break
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            items = soup.select('.list-item, .news-list li, .common-list li, li')
            
            if not items:
                break
            
            for item in items:
                try:
                    link_tag = item.find('a')
                    date_tag = item.find('span', class_='date') or item.find('em')
                    
                    if not link_tag:
                        continue
                    
                    title = link_tag.get('title', '') or link_tag.get_text(strip=True)
                    link = link_tag.get('href', '')
                    date_str = date_tag.get_text(strip=True) if date_tag else ''
                    
                    if link and not link.startswith('http'):
                        # 补全相对路径
                        if link.startswith('/'):
                            domain = '/'.join(base_url.split('/')[:3])
                            link = domain + link
                    
                    if any(kw in title for kw in ['私募', '基金', '管理人', '处罚', '监管', '警示']):
                        all_cases.append({
                            'title': title,
                            'link': link,
                            'date': date_str,
                            'source': bureau_name
                        })
                        bureau_cases += 1
                except Exception as e:
                    pass
            
            time.sleep(1)
        
        print(f"  {bureau_name} 抓取到 {bureau_cases} 条")
    
    print(f"\n各地证监局共抓取 {len(all_cases)} 条相关案例")
    return all_cases

# =============================================
# 四、抓取案例详情页
# =============================================

def fetch_case_detail(url):
    """抓取单个案例详情页的文本内容"""
    print(f"  抓取详情: {url[:80]}...")
    resp = safe_request(url, timeout=20)
    if not resp:
        return "【详情页访问失败】"
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # 尝试提取正文
    selectors = [
        '.article-content', '.news-content', '.main-content',
        '#content', '.detail-content', '.text-content',
        '.Custom_UnionStyle', '.TRS_Editor', '.content'
    ]
    
    for selector in selectors:
        div = soup.select_one(selector)
        if div:
            text = div.get_text(separator='\n', strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r'\s{2,}', ' ', text)
            return text[:5000]
    
    # 降级：拿 body 全文
    body = soup.body
    if body:
        text = body.get_text(separator='\n', strip=True)
        return text[:3000]
    
    return "【无法提取正文】"

# =============================================
# 五、DeepSeek 提取结构化信息
# =============================================

def extract_structured_info(all_cases):
    """
    将所有案例分批次交给 DeepSeek，提取结构化字段：
    监管主体、被罚机构、处罚日期、违规事实、处罚依据、处罚结果
    """
    http_client = httpx.Client()
    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        http_client=http_client,
        timeout=httpx.Timeout(120.0, connect=15.0)
    )
    
    # 先抓取每个案例的详情
    cases_with_detail = []
    total = len(all_cases)
    
    for i, case in enumerate(all_cases):
        print(f"\n处理案例 {i+1}/{total}: {case['title'][:50]}...")
        detail_text = fetch_case_detail(case['link'])
        case['detail_text'] = detail_text
        cases_with_detail.append(case)
        time.sleep(1)  # 避免请求过快
    
    # 分批交给 DeepSeek（每次10个案例）
    batch_size = 10
    all_results = []
    
    for start in range(0, len(cases_with_detail), batch_size):
        batch = cases_with_detail[start:start + batch_size]
        print(f"\n正在用 AI 处理第 {start+1}-{min(start+batch_size, len(cases_with_detail))} 个案例...")
        
        # 构建这批案例的文本
        batch_text = ""
        for i, case in enumerate(batch):
            batch_text += f"""
---
【案例编号：{start+i+1}】
【来源】{case['source']}
【标题】{case['title']}
【链接】{case['link']}
【日期】{case.get('date', '未知')}
【正文摘要】
{case.get('detail_text', '无')[:2000]}
"""
        
        prompt = f"""你是一名专业的私募基金合规分析师。请从以下处罚案例中，逐个提取关键信息。

对每个案例，输出一个 JSON 对象，包含以下字段：
- penalty_id: 案例编号
- regulator: 监管主体（哪个机构作出的处罚）
- entity: 被罚机构/个人全称
- penalty_date: 处罚日期（格式 YYYY-MM-DD，如无法精确则取年份或标注"日期不详"）
- violation: 违规事实（2-3句话概括核心违法行为）
- legal_basis: 处罚依据（引用的具体法规条款，如《私募投资基金监督管理条例》第X条）
- penalty_result: 处罚结果（出具警示函/罚款XX元/注销登记/市场禁入等）
- source_link: 原文链接

请以 JSON 数组形式输出，只输出 JSON，不要其他解释。
```json
[
  {{
    "penalty_id": "1",
    "regulator": "上海证监局",
    "entity": "XX投资管理有限公司",
    "penalty_date": "2025-03-15",
    "violation": "未按合同约定披露基金净值信息；向非合格投资者募集资金。",
    "legal_basis": "《私募投资基金监督管理条例》第XX条、《私募投资基金信息披露管理办法》第XX条",
    "penalty_result": "出具警示函，并记入证券期货市场诚信档案",
    "source_link": "http://..."
  }}
]
