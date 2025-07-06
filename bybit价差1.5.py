import json
from tabulate import tabulate
import subprocess
import time
import platform
from pybit.unified_trading import HTTP
from pathlib import Path

# === 用户配置 增加网络调用github===
PLATFORM_JSON = "platforms.json"
ARB_RECORD_FILE = "arbitrage_records.json"
UPDATE_JSON = "no"                    
DEVIATION_THRESHOLD = 0.4              
ARBITRAGE_THRESHOLD_CONTRACT = 1      
ARBITRAGE_THRESHOLD_LENDING = 3
CHECK_INTERVAL = 5                     
DISPLAY_CONFIG = {"*": "no"}           

# === 核心功能 ===
def load_platforms():
    """加载多平台配置"""
    try:
        with open(PLATFORM_JSON, 'r') as f:
            platforms = json.load(f)
        
        token_map = {}
        for p in platforms:
            for token in p["pairs"]:
                clean_token = token.strip().upper()
                token_map.setdefault(clean_token, []).append({
                    "platform": p["platform"],
                    "type": p["type"]
                })
        return token_map
    except Exception as e:
        print(f"\n⚠️ 平台配置加载失败: {str(e)}\n")
        return {}

def fetch_bybit_data():
    """获取Bybit永续合约数据"""
    try:
        session = HTTP()
        response = session.get_tickers(category="linear")
        return response['result']['list'] if response['retCode'] == 0 else []
    except Exception as e:
        print(f"\n⚠️ 数据获取失败: {str(e)}\n")
        return []

def process_data(raw_data, token_map):
    """核心数据处理逻辑"""
    main_table = []
    arbitrage_list = []
    platform_list = []
    
    for item in raw_data:
        symbol = item['symbol'].upper()
        base_token = symbol[:-4] if symbol.endswith('USDT') else symbol
        
        try:
            mark_price = float(item['markPrice'])
            index_price = float(item['indexPrice'])
            funding_rate = float(item['fundingRate']) * 100
        except (KeyError, ValueError):
            continue
        
        # 主力合约显示
        if DISPLAY_CONFIG.get(base_token, DISPLAY_CONFIG["*"]) == "yes":
            main_table.append([
                base_token, 
                f"{mark_price:.4f}",
                f"{index_price:.4f}",
                "USDT"
            ])
        
        # 套利机会检测
        deviation = (index_price / mark_price - 1) * 100
        if abs(deviation) > DEVIATION_THRESHOLD:
            arbitrage_entry = {
                'token': base_token,
                'deviation': f"{deviation:.2f}%",
                'funding_rate': f"{funding_rate:.2f}%",
                'index_price': f"{index_price:.4f}",
                'mark_price': f"{mark_price:.4f}"
            }
            arbitrage_list.append(arbitrage_entry)
            
            # 平台匹配
            if base_token in token_map:
                for platform_info in token_map[base_token]:
                    platform_list.append({
                        'pair': f"{base_token}_USDT",
                        'deviation': deviation,
                        'funding_rate': funding_rate,
                        'type': platform_info["type"],
                        'platform': platform_info["platform"]
                    })
    
    # 排序逻辑
    arbitrage_list.sort(key=lambda x: abs(float(x['deviation'][:-1])), reverse=True)
    platform_list.sort(key=lambda x: (-abs(x['deviation']), -abs(x['funding_rate'])))
    
    return main_table, arbitrage_list, platform_list

# === 报警记录功能 ===
def load_arb_records():
    """加载历史报警记录"""
    try:
        return json.loads(Path(ARB_RECORD_FILE).read_text()) if Path(ARB_RECORD_FILE).exists() else []
    except Exception as e:
        print(f"\n⚠️ 记录加载失败: {str(e)}\n")
        return []

def save_arb_records(records):
    """保存报警记录"""
    if UPDATE_JSON.lower() == "yes":
        try:
            Path(ARB_RECORD_FILE).write_text(json.dumps(records, indent=2))
        except Exception as e:
            print(f"\n⚠️ 记录保存失败: {str(e)}\n")

def filter_new_alerts(current_alerts):
    """过滤新增报警"""
    existing = {r['token']: r for r in load_arb_records()}
    new_alerts = []
    
    for alert in current_alerts:
        token = alert['token']
        if token not in existing:
            new_entry = {
                'token': token,
                'timestamp': int(time.time()),
                'message': alert['message']
            }
            new_alerts.append(new_entry)
            existing[token] = new_entry
    
    if new_alerts:
        save_arb_records(list(existing.values()))
    
    return new_alerts

# === 报警提示功能 ===
def speak_alert(message):
    """语音报警"""
    try:
        if platform.system() == 'Darwin':
            subprocess.run(['say', message])
        elif platform.system() == 'Windows':
            import winsound
            winsound.Beep(1000, 500)
            print(f"🔔 {message}")
    except Exception as e:
        print(f"报警失败: {str(e)}")

# === 主监控循环 ===
def main_loop():
    print(f"\n=== Bybit套利监控系统 ===")
    print(f"检测间隔: {CHECK_INTERVAL}s | 版本: 2.1")
    
    token_map = load_platforms()
    last_alert_time = time.time()
    
    try:
        while True:
            start_time = time.time()
            
            # 数据获取与处理
            raw_data = fetch_bybit_data()
            main_table, arbitrage_list, platform_list = process_data(raw_data, token_map)
            
            # 显示主力合约表
            print(f"\n[{time.strftime('%H:%M:%S')}] 主力合约数据:")
            if main_table:
                print(tabulate(
                    main_table,
                    headers=["代币", "标记价格", "指数价格", "结算"],
                    tablefmt="grid",
                    stralign="right"
                ))
            else:
                print("无显示配置的合约")
            
            # 显示套利机会表
            print(f"\n[{time.strftime('%H:%M:%S')}] 检测到{len(arbitrage_list)}个套利机会:")
            if arbitrage_list:
                print(tabulate(
                    [[item['token'], item['deviation'], item['funding_rate'], 
                      item['index_price'], item['mark_price']] 
                     for item in arbitrage_list],
                    headers=["代币", "价格偏离", "资金费率", "指数价", "标记价"],
                    tablefmt="grid",
                    floatfmt=".2f"
                ))
            
            # 显示可操作平台表
            print(f"\n[{time.strftime('%H:%M:%S')}] 可操作平台:")
            if platform_list:
                print(tabulate(
                    [[item['pair'], f"{item['deviation']:.2f}%", 
                      f"{item['funding_rate']:.2f}%", item['type'], item['platform']]
                     for item in platform_list],
                    headers=["交易对", "偏离率", "资金费", "类型", "平台"],
                    tablefmt="grid",
                    stralign="center"
                ))
            
            # 生成报警信息
            critical_alerts = []
            for item in platform_list:
                threshold = ARBITRAGE_THRESHOLD_CONTRACT if item['type'] == "合约" else ARBITRAGE_THRESHOLD_LENDING
                if abs(item['deviation']) >= threshold:
                    alert_msg = (
                        f"套利机会：{item['pair']} "
                        f"偏离率:{abs(item['deviation']):.2f}% "
                        f"资金费率:{item['funding_rate']:.2f}% "
                        f"平台:{item['platform']}"
                    )
                    critical_alerts.append({
                        'token': item['pair'].split('_')[0],
                        'message': alert_msg
                    })
            
            # 处理新报警
            new_alerts = filter_new_alerts(critical_alerts)
            print(f"\n[{time.strftime('%H:%M:%S')}] 套利机会提醒:")
            if new_alerts:
                for alert in new_alerts:
                    print(f"🔔 NEW: {alert['message']}")
                    speak_alert(f"检测到新的套利机会 {alert['token']}")
            elif critical_alerts:
                print("已有记录的机会不重复提醒")
            else:
                print("当前无符合条件的机会")
            
            # 等待下次检测
            elapsed = time.time() - start_time
            sleep_time = max(CHECK_INTERVAL - elapsed, 1)
            print(f"\n{'='*50}\n下次检测于 {time.strftime('%H:%M:%S', time.localtime(time.time()+sleep_time))}")
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\n\n=== 监控系统安全退出 ===")

if __name__ == "__main__":
    main_loop()