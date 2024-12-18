from flask import Flask, request, jsonify
from kucoin.client import Trade, Market
import os
import threading
import time

# Configuración del bot
app = Flask(__name__)
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "ROSE")  # Configurado en las variables de entorno

# Credenciales de la API de KuCoin (cargar desde variables de entorno)
API_KEY = os.getenv("KUCOIN_API_KEY")
API_SECRET = os.getenv("KUCOIN_SECRET_KEY")
API_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# Conexión a los clientes de KuCoin
trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
market_client = Market()

# Configuración fija
SYMBOL = "DOGE-USDT"  # Par de trading
TAKE_PROFIT = 0.2  # Ganancia fija (USDT)
STOP_LOSS = 10.0   # Pérdida fija (USDT)

# Estado del bot
operation_in_progress = False
current_order = {}  # Almacenar información de la orden activa


@app.route('/webhook', methods=['POST'])
def webhook():
    global operation_in_progress, current_order

    # Recibir y validar la señal desde TradingView
    data = request.get_json()
    print(f"Datos recibidos: {data}")

    if not data or data.get('token') != SECRET_TOKEN:
        return jsonify({"error": "Token inválido"}), 403

    action = data.get('action')
    amount = float(data.get('amount', 0))

    if not action or amount <= 0:
        return jsonify({"error": "Datos incompletos"}), 400

    # Si hay una operación en curso, rechazar nuevas señales
    if operation_in_progress:
        return jsonify({"status": "busy", "message": "Esperando a que finalice la operación actual"}), 200

    try:
        operation_in_progress = True
        ticker = market_client.get_ticker(SYMBOL)
        current_price = float(ticker['price'])

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
                raise Exception("Saldo insuficiente de USDT")
        
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
                raise Exception("Saldo insuficiente de DOGE")

        # Iniciar monitoreo para TP/SL en un hilo separado
        threading.Thread(target=monitor_price).start()

        return jsonify({
            "status": "success",
            "message": f"Orden {action} ejecutada",
            "tp_price": current_order['tp_price'],
            "sl_price": current_order['sl_price']
        }), 200

    except Exception as e:
        print(f"Error: {e}")
        operation_in_progress = False
        return jsonify({"error": str(e)}), 500


def get_balance(currency):
    """Obtener balance de una moneda específica."""
    accounts = trade_client.get_accounts()
    for account in accounts:
        if account['currency'] == currency and account['type'] == 'trade':
            return float(account['balance'])
    return 0.0


def monitor_price():
    """Monitorear el precio para cerrar posiciones con TP o SL."""
    global operation_in_progress, current_order

    while operation_in_progress:
        try:
            ticker = market_client.get_ticker(SYMBOL)
            current_price = float(ticker['price'])

            if current_order['side'] == "buy":
                if current_price >= current_order['tp_price']:
                    sell_all()
                    print("Take Profit alcanzado.")
                elif current_price <= current_order['sl_price']:
                    sell_all()
                    print("Stop Loss alcanzado.")
            elif current_order['side'] == "sell":
                if current_price <= current_order['tp_price']:
                    print("Take Profit alcanzado.")
                    operation_in_progress = False
                elif current_price >= current_order['sl_price']:
                    print("Stop Loss alcanzado.")
                    operation_in_progress = False

            time.sleep(5)  # Revisar cada 5 segundos

        except Exception as e:
            print(f"Error monitoreando el precio: {e}")
            operation_in_progress = False


def sell_all():
    """Función para vender todo el DOGE en caso de TP o SL."""
    global operation_in_progress
    doge_balance = get_balance("DOGE")
    if doge_balance > 0:
        trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
        print("Orden de venta ejecutada por TP/SL")
    operation_in_progress = False


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
