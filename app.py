from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, User
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
user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)

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
    
    if action not in ['buy', 'sell']:
        app.logger.error("Acción inválida recibida.")
        return jsonify({"error": "Acción inválida"}), 400

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
            usdt_balance = get_balance("USDT") * 0.98  # Usar solo el 98% del saldo USDT
            if usdt_balance > 0:
                # Obtener el incremento mínimo para la compra
                min_increment = get_min_increment("buy")
                # Ajustar la cantidad de DOGE a comprar
                adjusted_amount = usdt_balance / current_price
                adjusted_amount = adjust_to_increment(adjusted_amount, min_increment)

                response = trade_client.create_market_order(SYMBOL, "buy", funds=round(usdt_balance, 2))
                app.logger.info(f"Compra ejecutada: {response}")
                current_order.update({
                    "side": "buy",
                    "tp_price": current_price + TAKE_PROFIT,
                    "sl_price": current_price - STOP_LOSS
                })
            else:
                raise Exception("Saldo insuficiente de USDT")

        elif action == "sell":
            doge_balance = get_balance("DOGE") * 0.98  # Usar solo el 98% del saldo DOGE
            if doge_balance > 0:
                # Obtener el incremento mínimo para la venta
                min_increment = get_min_increment("sell")
                # Ajustar la cantidad de DOGE a vender
                adjusted_amount = adjust_to_increment(doge_balance, min_increment)

                response = trade_client.create_market_order(SYMBOL, "sell", size=adjusted_amount)
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
        accounts = user_client.get_account_list()
        for account in accounts:
            if account['currency'] == currency and account['type'] == 'trade':
                balance = float(account['balance'])
                app.logger.info(f"Saldo {currency}: {balance}")
                return balance
        return 0.0
    except Exception as e:
        app.logger.error(f"Error obteniendo balance para {currency}: {e}")
        return 0.0


def get_min_increment(order_type):
    """Obtener el incremento mínimo permitido para la operación de compra o venta."""
    try:
        symbol_details = market_client.get_symbol_list()
        for detail in symbol_details:
            if detail['symbol'] == SYMBOL:
                return float(detail['baseIncrement'])
        return 0.01
    except Exception as e:
        app.logger.error(f"Error obteniendo incremento mínimo para {order_type}: {e}")
        return 0.01


def adjust_to_increment(value, increment):
    """Ajustar un valor al múltiplo más cercano del incremento dado."""
    return increment * int(value / increment)


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

            time.sleep(5)

        except Exception as e:
            app.logger.error(f"Error monitoreando el precio: {e}")
            operation_in_progress = False


def sell_all():
    """Función para vender todo el DOGE en caso de TP o SL."""
    global operation_in_progress
    doge_balance = get_balance("DOGE") * 0.98
    if doge_balance > 0:
        response = trade_client.create_market_order(SYMBOL, "sell", size=doge_balance)
        app.logger.info(f"Orden de venta ejecutada: {response}")
    operation_in_progress = False


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
