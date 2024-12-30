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
TAKE_PROFIT_PERCENT = 0.2  # Porcentaje de ganancia
STOP_LOSS_PERCENT = 0.5    # Porcentaje de pérdida

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

    # Verificar si una operación está en curso
    if operation_in_progress and current_order.get('side') != action:
        app.logger.warning("Operación en curso pero señal opuesta recibida, cerrando operación actual...")
        close_current_operation()
        operation_in_progress = False

    if operation_in_progress:
        app.logger.warning("Operación en curso, señal rechazada.")
        return jsonify({"status": "busy", "message": "Esperando a que finalice la operación actual"}), 200

    try:
        operation_in_progress = True
        ticker = market_client.get_ticker(SYMBOL)
        current_price = float(ticker['price'])
        app.logger.info(f"Precio actual del mercado para {SYMBOL}: {current_price}")

        if action == "buy":
            usdt_balance = get_balance("USDT") * 0.85  # Usar solo el 85% del saldo USDT
            if usdt_balance > 0:
                min_increment = get_min_increment("buy")
                adjusted_amount = usdt_balance / current_price
                adjusted_amount = adjust_to_increment(adjusted_amount, min_increment)

                response = trade_client.create_market_order(SYMBOL, "buy", funds=round(usdt_balance, 2))
                app.logger.info(f"Compra ejecutada: {response}")
                current_order.update({
                    "side": "buy",
                    "tp_price": current_price * (1 + TAKE_PROFIT_PERCENT),
                    "sl_price": current_price * (1 - STOP_LOSS_PERCENT)
                })
            else:
                raise Exception("Saldo insuficiente de USDT")

        elif action == "sell":
            doge_balance = get_balance("DOGE") * 0.85  # Usar solo el 85% del saldo DOGE
            if doge_balance > 0:
                min_increment = get_min_increment("sell")
                adjusted_amount = adjust_to_increment(doge_balance, min_increment)

                response = trade_client.create_market_order(SYMBOL, "sell", size=adjusted_amount)
                app.logger.info(f"Venta ejecutada: {response}")
                current_order.update({
                    "side": "sell",
                    "tp_price": current_price * (1 - TAKE_PROFIT_PERCENT),
                    "sl_price": current_price * (1 + STOP_LOSS_PERCENT)
                })
            else:
                raise Exception("Saldo insuficiente de DOGE")

        # Iniciar monitoreo para TP/SL en un hilo separado
        threading.Thread(target=monitor_price, daemon=True).start()

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


def close_current_operation():
    """Cerrar la operación actual de manera segura."""
    global current_order, operation_in_progress
    if current_order['side'] == "buy":
        sell_all()
        app.logger.info("Operación de compra cerrada manualmente.")
    elif current_order['side'] == "sell":
        doge_balance = get_balance("DOGE")
        if doge_balance > 0:
            sell_all()
        app.logger.info("Operación de venta cerrada manualmente.")
    operation_in_progress = False
    current_order.clear()

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
                    break
                elif current_price <= current_order['sl_price']:
                    sell_all()
                    app.logger.info("Stop Loss alcanzado.")
                    break
            elif current_order['side'] == "sell":
                if current_price <= current_order['tp_price']:
                    app.logger.info("Take Profit alcanzado.")
                    break
                elif current_price >= current_order['sl_price']:
                    app.logger.info("Stop Loss alcanzado.")
                    break

            time.sleep(1)  # Reducir el tiempo de espera para una mayor rapidez de reacción

        except Exception as e:
            app.logger.error(f"Error monitoreando el precio: {e}")
            break

    operation_in_progress = False
    current_order.clear()

def sell_all():
    """Función para vender todo el DOGE en caso de TP o SL."""
    global operation_in_progress
    doge_balance = get_balance("DOGE") * 0.98
    if doge_balance > 0:
        response = trade_client.create_market_order(SYMBOL, "sell", size=round(doge_balance, 2))
        app.logger.info(f"Orden de venta ejecutada: {response}")
    operation_in_progress = False

def get_balance(asset):
    """Obtener el balance de un activo (USDT o DOGE)."""
    if asset == "USDT":
        balance = user_client.get_balance('USDT')
        return float(balance['available'])
    elif asset == "DOGE":
        balance = user_client.get_balance('DOGE')
        return float(balance['available'])
    return 0

def get_min_increment(action):
    """Obtener el incremento mínimo permitido por KuCoin para comprar/vender."""
    if action == "buy":
        return 0.001  # Ejemplo de incremento mínimo para compra de DOGE
    elif action == "sell":
        return 0.001  # Ejemplo de incremento mínimo para venta de DOGE
    return 0

def adjust_to_increment(amount, min_increment):
    """Ajustar la cantidad a comprar/vender al incremento mínimo permitido."""
    return round(amount / min_increment) * min_increment

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
