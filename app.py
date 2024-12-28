from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, User
import os
import threading
import time

app = Flask(__name__)
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "ROSE")

API_KEY = os.getenv("KUCOIN_API_KEY")
API_SECRET = os.getenv("KUCOIN_SECRET_KEY")
API_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
market_client = Market()
user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)

SYMBOL = "DOGE-USDT"
TAKE_PROFIT = 0.2
STOP_LOSS = 10.0

operation_in_progress = False
current_order = {}

def get_balance(currency):
    """Obtener balance de una moneda específica."""
    try:
        accounts = user_client.get_accounts()
        for account in accounts:
            if account['currency'] == currency and account['type'] == 'trade':
                return float(account['balance'])
        return 0.0
    except Exception as e:
        print(f"Error obteniendo balance para {currency}: {e}")
        return 0.0

@app.route('/webhook', methods=['POST'])
def webhook():
    global operation_in_progress, current_order
    try:
        data = request.get_json()
        print(f"Datos recibidos: {data}")

        if not data or data.get('token') != SECRET_TOKEN:
            return jsonify({"error": "Token inválido o datos faltantes"}), 403

        action = data.get('action')
        amount = float(data.get('amount', 0))

        if action not in ["buy", "sell"] or amount <= 0:
            return jsonify({"error": "Acción o cantidad inválida"}), 400

        if operation_in_progress:
            print("Cerrando operación anterior...")
            close_operation()

        operation_in_progress = True
        threading.Thread(target=execute_trade, args=(action,)).start()

        return jsonify({"status": "success", "message": f"Señal {action} recibida y procesada"}), 200

    except Exception as e:
        print(f"Error en el webhook: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

def execute_trade(action):
    global operation_in_progress, current_order
    try:
        ticker = market_client.get_ticker(SYMBOL)
        current_price = float(ticker['price'])
        print(f"Precio actual del mercado para {SYMBOL}: {current_price}")

        if action == "buy":
            usdt_balance = get_balance("USDT")
            if usdt_balance > 0:
                response = trade_client.create_market_order(SYMBOL, "buy", funds=usdt_balance)
                print(f"Compra ejecutada: {response}")
                current_order.update({
                    "side": "buy",
                    "tp_price": current_price + TAKE_PROFIT,
                    "sl_price": current_price - STOP_LOSS
                })
            else:
                print("Saldo insuficiente de USDT.")

        elif action == "sell":
            doge_balance = get_balance("DOGE")
            if doge_balance > 0:
                response = trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
                print(f"Venta ejecutada: {response}")
                current_order.update({
                    "side": "sell",
                    "tp_price": current_price - TAKE_PROFIT,
                    "sl_price": current_price + STOP_LOSS
                })
            else:
                print("Saldo insuficiente de DOGE.")

        threading.Thread(target=monitor_price).start()

    except Exception as e:
        print(f"Error ejecutando la operación: {e}")
        operation_in_progress = False

def monitor_price():
    global operation_in_progress, current_order
    try:
        while operation_in_progress:
            ticker = market_client.get_ticker(SYMBOL)
            current_price = float(ticker['price'])
            print(f"Precio actual monitoreado: {current_price}")

            if current_order['side'] == "buy" and (current_price >= current_order['tp_price'] or current_price <= current_order['sl_price']):
                close_operation()
            elif current_order['side'] == "sell" and (current_price <= current_order['tp_price'] or current_price >= current_order['sl_price']):
                close_operation()
            time.sleep(5)
    except Exception as e:
        print(f"Error monitoreando el precio: {e}")
        operation_in_progress = False

def close_operation():
    global operation_in_progress
    try:
        if current_order['side'] == "buy":
            sell_all()
        elif current_order['side'] == "sell":
            print("Operación de venta completada.")
        operation_in_progress = False
    except Exception as e:
        print(f"Error cerrando la operación: {e}")

def sell_all():
    doge_balance = get_balance("DOGE")
    if doge_balance > 0:
        trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
        print("Venta ejecutada correctamente.")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
