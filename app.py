from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, User
import os
import threading
import time

# Configuración del bot
app = Flask(__name__)
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "ROSE")

# Credenciales de la API de KuCoin
API_KEY = os.getenv("KUCOIN_API_KEY")
API_SECRET = os.getenv("KUCOIN_SECRET_KEY")
API_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# Conexión a los clientes de KuCoin
trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
market_client = Market()
user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)  # Nuevo cliente

# Configuración fija
SYMBOL = "DOGE-USDT"  # Par de trading
TAKE_PROFIT = 0.2  # Ganancia fija en USDT
STOP_LOSS = 10.0   # Pérdida fija en USDT

# Estado del bot
operation_in_progress = False
current_order = {}  # Almacenar información de la orden activa

@app.route('/webhook', methods=['POST'])
def webhook():
    global operation_in_progress, current_order

    # Recibir y validar la señal desde TradingView
    try:
        data = request.get_json()
        print(f"Datos recibidos: {data}")

        if not data:
            return jsonify({"error": "No se recibió ningún dato"}), 400

        required_fields = ["token", "action", "amount"]
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify({"error": f"Faltan campos requeridos: {', '.join(missing_fields)}"}), 400

        # Validar el token
        if data.get('token') != SECRET_TOKEN:
            return jsonify({"error": "Token inválido"}), 403

        # Validar acción y monto
        action = data.get('action')
        try:
            amount = float(data.get('amount', 0))
            if amount <= 0:
                raise ValueError
        except ValueError:
            return jsonify({"error": "El campo 'amount' debe ser un número mayor que 0"}), 400

        if action not in ["buy", "sell"]:
            return jsonify({"error": "Acción inválida, debe ser 'buy' o 'sell'"}), 400

        # Si hay una operación en curso, cerrarla antes de continuar
        if operation_in_progress:
            print("Cerrando operación anterior...")
            close_operation()

        # Ejecutar la nueva operación
        operation_in_progress = True
        threading.Thread(target=execute_trade, args=(action,)).start()

        return jsonify({"status": "success", "message": f"Señal {action} recibida y procesada"}), 200

    except Exception as e:
        print(f"Error en el webhook: {e}")
        return jsonify({"error": "Error interno en el servidor"}), 500

def get_balance(currency):
    """Obtener balance de una moneda específica."""
    try:
        accounts = trade_client.get_accounts()
        for account in accounts:
            if account['currency'] == currency and account['type'] == 'trade':
                return float(account['balance'])
    except Exception as e:
        print(f"Error obteniendo balance para {currency}: {e}")
    return 0.0

def execute_trade(action):
    """Ejecutar la operación de compra o venta."""
    global operation_in_progress, current_order

    try:
        ticker = market_client.get_ticker(SYMBOL)
        current_price = float(ticker['price'])
        print(f"Precio actual del mercado para {SYMBOL}: {current_price}")

        if action == "buy":
            usdt_balance = get_balance("USDT")
            print(f"Saldo USDT disponible: {usdt_balance}")
            if usdt_balance > 0:
                response = trade_client.create_market_order(SYMBOL, "buy", funds=usdt_balance)
                print(f"Respuesta de la API para la compra: {response}")
                current_order.update({
                    "side": "buy",
                    "tp_price": current_price + TAKE_PROFIT,
                    "sl_price": current_price - STOP_LOSS
                })
            else:
                print("Saldo insuficiente de USDT.")

        elif action == "sell":
            doge_balance = get_balance("DOGE")
            print(f"Saldo DOGE disponible: {doge_balance}")
            if doge_balance > 0:
                response = trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
                print(f"Respuesta de la API para la venta: {response}")
                current_order.update({
                    "side": "sell",
                    "tp_price": current_price - TAKE_PROFIT,
                    "sl_price": current_price + STOP_LOSS
                })
            else:
                print("Saldo insuficiente de DOGE.")

        # Monitorear TP/SL en un hilo separado
        threading.Thread(target=monitor_price).start()

    except Exception as e:
        print(f"Error ejecutando la operación: {e}")
        operation_in_progress = False

def monitor_price():
    """Monitorear el precio para cerrar posiciones con TP o SL."""
    global operation_in_progress, current_order

    while operation_in_progress:
        try:
            ticker = market_client.get_ticker(SYMBOL)
            current_price = float(ticker['price'])
            print(f"Precio actual monitoreado: {current_price}")

            if current_order['side'] == "buy":
                if current_price >= current_order['tp_price'] or current_price <= current_order['sl_price']:
                    close_operation()
                    return
            elif current_order['side'] == "sell":
                if current_price <= current_order['tp_price'] or current_price >= current_order['sl_price']:
                    close_operation()
                    return

            time.sleep(5)

        except Exception as e:
            print(f"Error monitoreando el precio: {e}")
            operation_in_progress = False

def close_operation():
    """Cerrar cualquier operación activa."""
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
    """Vender todo el DOGE en caso de TP, SL o nueva señal."""
    doge_balance = get_balance("DOGE")
    if doge_balance > 0:
        response = trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
        print(f"Respuesta de la API para vender todo el DOGE: {response}")
        print("Venta ejecutada correctamente.")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
