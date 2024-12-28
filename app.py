from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, User  # Asegúrate de importar User
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
user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)  # Cliente para obtener balances

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
    app.logger.info(f"Datos recibidos: {data}")

    if not data or data.get('token') != SECRET_TOKEN:
        app.logger.error("Token inválido recibido.")
        return jsonify({"error": "Token inválido"}), 403

    action = data.get('action')
    amount = float(data.get('amount', 0))

    if not action or amount <= 0:
        app.logger.error("Datos incompletos o inválidos en la señal.")
        return jsonify({"error": "Datos incompletos"}), 400

    # Si hay una operación en curso, rechazar nuevas señales
    if operation_in_progress:
        app.logger.warning("Operación en curso, señal rechazada.")
        return jsonify({"status": "busy", "message": "Esperando a que finalice la operación actual"}), 200

    try:
        operation_in_progress = True
        ticker = market_client.get_ticker(SYMBOL)
        current_price = float(ticker['price'])
        app.logger.info(f"Precio actual del mercado para {SYMBOL}: {current_price}")

        if action == "buy":
            usdt_balance = get_balance("USDT")
            if usdt_balance > 0:
                response = trade_client.create_market_order(SYMBOL, "buy", funds=usdt_balance)
                app.logger.info(f"Compra ejecutada: {response}")
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
                app.logger.info(f"Venta ejecutada: {response}")
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
        app.logger.error(f"Error procesando la señal: {e}")
        operation_in_progress = False
        return jsonify({"error": str(e)}), 500


def get_balance(currency):
    """Obtener balance de una moneda específica utilizando el cliente User."""
    try:
        accounts = user_client.get_account_list()  # Se corrige para usar el cliente `User`
        for account in accounts:
            if account['currency'] == currency and account['type'] == 'trade':
                balance = float(account['balance'])
                app.logger.info(f"Saldo {currency}: {balance}")
                return balance
        return 0.0
    except Exception as e:
        app.logger.error(f"Error obteniendo balance para {currency}: {e}")
        return 0.0


def monitor_price():
    """Monitorear el precio para cerrar posiciones con TP o SL."""
    global operation_in_progress, current_order

    while operation_in_progress:
        try:
            ticker = market_client.get_ticker(SYMBOL)
            current_price = float(ticker['price'])
            app.logger.info(f"Precio actual monitoreado: {current_price}")

            if current_order['side'] == "buy":
                if current_price >= current_order['tp_price']:
                    sell_all()
                    app.logger.info("Take Profit alcanzado.")
                elif current_price <= current_order['sl_price']:
                    sell_all()
                    app.logger.info("Stop Loss alcanzado.")
            elif current_order['side'] == "sell":
                if current_price <= current_order['tp_price']:
                    app.logger.info("Take Profit alcanzado.")
                    operation_in_progress = False
                elif current_price >= current_order['sl_price']:
                    app.logger.info("Stop Loss alcanzado.")
                    operation_in_progress = False

            time.sleep(5)  # Revisar cada 5 segundos

        except Exception as e:
            app.logger.error(f"Error monitoreando el precio: {e}")
            operation_in_progress = False


def sell_all():
    """Función para vender todo el DOGE en caso de TP o SL."""
    global operation_in_progress
    doge_balance = get_balance("DOGE")
    if doge_balance > 0:
        response = trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
        app.logger.info(f"Orden de venta ejecutada: {response}")
    operation_in_progress = False


def buy_all():
    """Función para comprar todo el saldo en USDT en DOGE."""
    global operation_in_progress
    usdt_balance = get_balance("USDT")
    if usdt_balance > 0:
        response = trade_client.create_market_order(SYMBOL, "buy", funds=usdt_balance)
        app.logger.info(f"Compra ejecutada: {response}")
    operation_in_progress = False


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
