import time
import requests
import joblib
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator, MACD, CCIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator
from sklearn.preprocessing import StandardScaler
from datetime import datetime

# === TELEGRAM AYARLARI ===
TELEGRAM_TOKEN = "7818410555:AAGxzE_W3o10xtRciQux9_xK_sfbbqCSXeI"
TELEGRAM_CHAT_ID = "5733334297"

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram gönderim hatası:", e)

# === VERİ ALMA ===
def get_klines(symbol="ETHUSDT", interval="1h", limit=1000):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_vol', 'taker_buy_quote_vol', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df.astype(float)
    return df[['open', 'high', 'low', 'close', 'volume']]

# === GÖSTERGELERİ EKLE ===
def add_indicators(df):
    df = df.copy()
    df['rsi'] = RSIIndicator(close=df['close']).rsi()
    df['ema_10'] = EMAIndicator(close=df['close'], window=10).ema_indicator()
    df['ema_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df['ema_200'] = EMAIndicator(close=df['close'], window=200).ema_indicator()
    macd = MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()
    bb = BollingerBands(close=df['close'])
    df['bb_high'] = bb.bollinger_hband()
    df['bb_low'] = bb.bollinger_lband()
    df['bb_width'] = df['bb_high'] - df['bb_low']
    df['cci'] = CCIIndicator(high=df['high'], low=df['low'], close=df['close']).cci()
    df['obv'] = OnBalanceVolumeIndicator(close=df['close'], volume=df['volume']).on_balance_volume()
    stoch = StochasticOscillator(high=df['high'], low=df['low'], close=df['close'])
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    df['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close']).average_true_range()
    df['momentum'] = df['close'] - df['close'].shift(5)
    df['return_1h'] = df['close'].pct_change(periods=4)
    df['volatility'] = df['close'].rolling(window=10).std()
    df['log_close'] = np.log(df['close'])
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    df.dropna(inplace=True)
    return df

# === ANA BOT ===
def run_bot(symbol="APTUSDT", tp=0.02, sl=0.02):
    try:
        model = joblib.load("model.pkl")
        scaler = joblib.load("scaler.pkl")
        features = scaler.feature_names_in_
    except Exception as e:
        send_telegram(f"❌ Model/Scaler yüklenemedi: {str(e)}")
        return

    in_position = False
    entry_price = 0.0

    while True:
        try:
            df = get_klines(symbol, limit=1000)
            df = add_indicators(df)

            if df.empty:
                send_telegram("⚠️ Uyarı: Teknik göstergeler sonrası veri boş. Atlanıyor.")
                time.sleep(60)
                continue

            live_data = df.tail(1).copy()

            # Boş veri, eksik sütun, veya sütun değeri boşsa uyarı ver ve geç
            if live_data.empty:
                send_telegram("⚠️ Uyarı: Live data boş. Atlanıyor.")
                time.sleep(60)
                continue
            if 'close' not in live_data.columns:
                send_telegram("⚠️ Uyarı: 'close' sütunu eksik. Atlanıyor.")
                time.sleep(60)
                continue
            if live_data['close'].shape[0] == 0:
                send_telegram("⚠️ Uyarı: 'close' değeri boş. Atlanıyor.")
                time.sleep(60)
                continue

            # Eksik feature varsa sıfırla
            for col in features:
                if col not in live_data.columns:
                    live_data[col] = 0.0

            X = scaler.transform(live_data[features])
            signal = model.predict(X)[0]
            price = live_data['close'].values[0]
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if not in_position and signal == 2:
                entry_price = price
                in_position = True
                send_telegram(f"📈 [{now}] BUY sinyali ({symbol}) - Fiyat: {price:.4f}")

            elif in_position:
                tp_price = entry_price * (1 + tp)
                sl_price = entry_price * (1 - sl)

                if price >= tp_price:
                    send_telegram(f"🎯 [{now}] TP GELDİ ({symbol}) ➤ Fiyat: {price:.4f}")
                    in_position = False
                elif price <= sl_price:
                    send_telegram(f"🛑 [{now}] SL GELDİ ({symbol}) ➤ Fiyat: {price:.4f}")
                    in_position = False
                elif signal == 0:
                    send_telegram(f"📉 [{now}] SELL sinyali ({symbol}) ➤ Fiyat: {price:.4f}")
                    in_position = False

        except Exception as e:
            send_telegram(f"❌ HATA: {str(e)}")

        time.sleep(60)

    
# === BAŞLATICI ===
if __name__ == "__main__":
    send_telegram("✅ Bot başarıyla başlatıldı. Telegram bağlantısı çalışıyor.")
    run_bot()
