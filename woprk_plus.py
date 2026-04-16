# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "httpx",
#     "tqdm",
# ]
# ///
import json
import csv
import os
from datetime import datetime, timezone, timedelta

import httpx
from tqdm import trange

# --- 爬蟲設定 ---
NUMS_OF_WORLDS = 14
NUMS_OF_REGION = 5

HEADERS = {"Content-Type": "application/json"}
RANKING_URI = "https://warsofprasia.beanfun.com/api/Records/PostLiveapiGCRanking"


def fetch_ranking(client: httpx.Client, world_id: int, region_id: int) -> dict:
    """向伺服器發送 API 請求以獲取排行榜資料"""
    padded_world_id: str = f"{world_id:02d}"
    post_data = {
        "world_group_id": f"livegm_w{padded_world_id}",
        "world_id": f"livegm_w{padded_world_id}_r{region_id}",
        "class": None,
    }
    resp = client.post(RANKING_URI, headers=HEADERS, json=post_data)
    return resp.json()


def get_unique_filename(base_name: str, extension: str) -> str:
    """檢查檔名是否重複，若重複則自動加上編號"""
    filename = f"{base_name}{extension}"
    if not os.path.exists(filename):
        return filename
    
    counter = 2
    while True:
        filename = f"{base_name}_{counter}{extension}"
        if not os.path.exists(filename):
            return filename
        counter += 1


if __name__ == "__main__":
    # ==========================
    # 步驟 1：抓取資料
    # ==========================
    print("開始抓取伺服器資料...")
    client = httpx.Client()
    result = {}
    
    for world_id in trange(1, NUMS_OF_WORLDS + 1, leave=False, desc="world"):
        for region_id in trange(1, NUMS_OF_REGION + 1, desc="region"):
            result[f"world-{world_id}-region-{region_id}"] = fetch_ranking(
                client, world_id, region_id
            )
            
    # 原始資料備份檔名也套用自動編號邏輯 (選用)
    json_output = get_unique_filename("output", ".json")
    with open(json_output, "w", encoding='utf8') as file_handle:
        json.dump(result, file_handle, ensure_ascii=False, indent=4)

    # ==========================
    # 步驟 2：資料清洗與整理
    # ==========================
    print("資料抓取完畢，開始轉換格式...")
    header = ["world_name", "gc_name", "gc_level", "gc_exp", "ranking", "guild_name", "grade", "class_name"]
    rows = []

    # 直接使用 result.values() 即可，不需要再抓取 region_key 了
    for region in result.values():
        gc_list = region.get("data", {}).get("gc", [])
        
        for entry in gc_list:
            w_name = entry.get("world_name")
            
            # 【關鍵修改】如果沒有伺服器名稱 (代表伺服器已刪除)，直接跳過這筆資料不處理
            if not w_name:
                continue

            row = [
                w_name,
                entry.get("gc_name", ""),
                entry.get("gc_level", ""),
                entry.get("gc_exp", ""),
                entry.get("ranking", ""),
                entry.get("guild_name", ""),
                entry.get("string_map", {}).get("grade", ""),
                entry.get("class_name", "")
            ]
            rows.append(row)

    # ==========================
    # 步驟 3：輸出 TSV 檔案並自動處理重複檔名
    # ==========================
    # 設定時區為 UTC+8 (台灣時間)
    tw_tz = timezone(timedelta(hours=8))
    today_str = datetime.now(tw_tz).strftime("%m%d")
    
    base_file_name = f"woprk_{today_str}"
    
    # 呼叫自動編號函式
    output_file = get_unique_filename(base_file_name, ".tsv")

    with open(output_file, "w", newline="", encoding="utf-8") as tsvfile:
        writer = csv.writer(tsvfile, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)

    print(f"✅ 執行完成！")
    print(f"👉 表格檔案：{output_file}")
    print(f"👉 原始備份：{json_output}")

    # ==========================
    # 步驟 4：輸出給網頁用的 JS 資料檔
    # ==========================
    # 將 rows (列表陣列) 轉換為帶有鍵值的字典陣列，方便網頁 JavaScript 讀取
    web_data = []
    for r in rows:
        web_data.append({
            "world_name": r[0],
            "gc_name": r[1],
            "gc_level": r[2],
            "gc_exp": r[3],
            "ranking": r[4],
            "guild_name": r[5],
            "grade": r[6],
            "class_name": r[7]
        })
    
    js_output_file = "data.js"
    with open(js_output_file, "w", encoding="utf-8") as js_file:
        # 將資料寫成 JavaScript 變數的形式
        json_str = json.dumps(web_data, ensure_ascii=False)
        js_file.write(f"const woprkData = {json_str};")
        
    print(f"👉 網頁資料已輸出為：{js_output_file}")
