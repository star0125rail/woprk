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
import glob
import re
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
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    
    # 依照你的需求，將檔名格式改為 YYYYMMDDHH (例如: 2024041615)
    today_str = now.strftime("%Y%m%d%H")
    base_file_name = f"woprk_{today_str}"
    
    output_file = get_unique_filename(base_file_name, ".tsv")

    with open(output_file, "w", newline="", encoding="utf-8") as tsvfile:
        writer = csv.writer(tsvfile, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)

    print(f"✅ 執行完成！")
    print(f"👉 表格檔案：{output_file}")
    print(f"👉 原始備份：{json_output}")

    # ==========================
    # 步驟 4：計算「預估日增經驗」並輸出給網頁用的 JS 資料檔
    # ==========================
    # 1. 取得 TSV 列表，改用「檔名」本身來做字母反向排序，確保最新時間在最前面
    tsv_files = glob.glob("woprk_*.tsv")
    tsv_files.sort(reverse=True) 
    
    prev_tsv_file = None
    for f in tsv_files:
        if f != output_file:
            prev_tsv_file = f
            break

    prev_exp_map = {}
    hours_diff = 24.0 # 預設為相差 24 小時

    if prev_tsv_file:
        print(f"👉 找到歷史紀錄：{prev_tsv_file}，開始計算時薪...")
        
        # 2. 利用正規表達式從檔名中萃取 YYYYMMDDHH (例如 woprk_2024041615)
        match = re.search(r"woprk_(\d{10})", prev_tsv_file)
        if match:
            time_str = match.group(1)
            try:
                # 將字串轉換為台灣時間的 datetime 物件
                prev_time = datetime.strptime(time_str, "%Y%m%d%H").replace(tzinfo=tw_tz)
                current_time = datetime.now(tw_tz)
                
                # 計算精確的相差小時數
                hours_diff = (current_time.timestamp() - prev_time.timestamp()) / 3600.0
            except ValueError:
                pass 
                
        # 避免連續點擊執行導致時間差過小，設定最低底線為 0.1 小時 (避免數字暴增)
        if hours_diff < 0.1:
            hours_diff = 0.1
            
        with open(prev_tsv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            next(reader, None)
            for row in reader:
                if len(row) >= 4:
                    try:
                        prev_exp_map[row[1]] = int(row[3])
                    except ValueError:
                        pass
    else:
        print("👉 未找到歷史紀錄，將無法計算本次經驗值增長。")

    # ----- 下方組合 web_data 的邏輯保持不變 -----

    web_data = []
    for r in rows:
        gc_name = r[1]
        try:
            current_exp = int(r[3])
        except ValueError:
            current_exp = 0
            
        prev_exp = prev_exp_map.get(gc_name, current_exp)
        exp_diff = current_exp - prev_exp

        # === 核心運算：時薪回推日薪 ===
        if exp_diff > 0:
            hourly_gain = exp_diff / hours_diff
            daily_gain_estimate = int(hourly_gain * 24)
        else:
            hourly_gain = 0
            daily_gain_estimate = 0

        web_data.append({
            "world_name": r[0],
            "gc_name": gc_name,
            "gc_level": r[2],
            "gc_exp": str(current_exp),
            "ranking": r[4],
            "guild_name": r[5],
            "grade": r[6],
            "class_name": r[7],
            "exp_gain": daily_gain_estimate,
            "hourly_gain": int(hourly_gain)  # 【新增】每小時經驗欄位
        })
    
    js_output_file = "data.js"
    with open(js_output_file, "w", encoding="utf-8") as js_file:
        json_str = json.dumps(web_data, ensure_ascii=False)
        js_file.write(f"const woprkData = {json_str};")
        
    print(f"👉 網頁資料已輸出為：{js_output_file} (與上次比較間隔：{hours_diff:.2f} 小時)")
