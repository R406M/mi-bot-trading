from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, User
import os
import threading
import time
import logging

# Configuración del bot
app = Flask(__name__)
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "ROSE")

# Credenciales de la API de KuCoin
API_KEY = os.getenv("KUCOIN_API_KEY")
API_SECRET = os.getenv("KUCOIN_SECRET_KEY")
API_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# Configuración fija
SYMBOL = "DOGE-USDT"
TAKE_PROFIT_PERCENT = 0.2
STOP_LOSS_PERCENT = 0.5
MIN_ORDER_SIZE = 1  # Tamaño mínimo de la orden para DOGE

# Clientes de KuCoin
try:
    trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
    market_client = Market()
    user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
except Exception as e:
    app.logger.error(f"Error inicializando clientes KuCoin: {e}")
    raise SystemExit("Error crítico al conectar con KuCoin")

# Estado del bot
class BotState:
    def __init__(self):
        self.operation_in_progress = False
        self.current_order = {}

state = BotState()

# Configuración de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    logger.info(f"Datos recibidos: {data}")

    if not data or data.get('token') != SECRET_TOKEN:
        logger.error(f"Token inválido recibido: {data.get('token')}")
        return jsonify({"error": "Token inválido"}), 403

    action = data.get('action')

    if action not in ['buy', 'sell']:
        logger.error("Acción inválida recibida.")
        return jsonify({"error": "Acción inválida"}), 400

    if state.operation_in_progress and state.current_order.get('side') != action:
        logger.warning("Operación en curso pero señal opuesta recibida, cerrando operación actual...")
        close_current_operation()

    if state.operation_in_progress:
        logger.warning("Operación en curso, señal rechazada.")
        return jsonify({"status": "busy", "message": "Esperando a que finalice la operación actual"}), 200

    try:
        state.operation_in_progress = True
        ticker = safe_get_ticker(SYMBOL)
        if not ticker:
            raise Exception("No se pudo obtener el ticker")

        current_price = float(ticker['price'])
        logger.info(f"Precio actual del mercado para {SYMBOL}: {current_price}")

        if action == "buy":
            handle_buy(current_price)
        elif action == "sell":
            handle_sell(current_price)

        logger.info(f"Estado actual de la orden: {state.current_order}")

        if "tp_price" not in state.current_order or "sl_price" not in state.current_order:
            raise Exception("Faltan claves 'tp_price' o 'sl_price' en current_order")

        threading.Thread(target=monitor_price, daemon=True).start()

        return jsonify({
            "status": "success",
            "message": f"Orden {action} ejecutada",
            "tp_price": state.current_order['tp_price'],
            "sl_price": state.current_order['sl_price']
        }), 200

    except Exception as e:
        logger.error(f"Error procesando la señal: {e}")
        state.operation_in_progress = False
        return jsonify({"error": str(e)}), 500

def handle_buy(current_price):
    usdt_balance = safe_get_balance("USDT") * 0.85
    if usdt_balance > 0:
        adjusted_amount = usdt_balance / current_price
        adjusted_amount = adjust_to_increment(adjusted_amount, 0.001)
        response = safe_create_order(SYMBOL, "buy", funds=round(usdt_balance, 2))
        logger.info(f"Compra ejecutada: {response}")

        state.current_order.update({
            "side": "buy",
            "tp_price": current_price * (1 + TAKE_PROFIT_PERCENT),
            "sl_price": current_price * (1 - STOP_LOSS_PERCENT)
        })
        logger.info(f"Orden de compra establecida: {state.current_order}")
    else:
        raise Exception("Saldo insuficiente de USDT")

def handle_sell(current_price):
    doge_balance = safe_get_balance("DOGE") * 0.85

    if doge_balance >= MIN_ORDER_SIZE:
        adjusted_amount = adjust_to_increment(doge_balance, 0.001)

        if adjusted_amount < MIN_ORDER_SIZE:
            raise Exception(f"El monto a vender ({adjusted_amount} DOGE) es menor al mínimo permitido ({MIN_ORDER_SIZE} DOGE)")

        response = safe_create_order(SYMBOL, "sell", size=adjusted_amount)
        logger.info(f"Venta ejecutada: {response}")

        state.current_order.update({
            "side": "sell",
            "tp_price": current_price * (1 - TAKE_PROFIT_PERCENT),
            "sl_price": current_price * (1 + STOP_LOSS_PERCENT)
        })
        logger.info(f"Orden de venta establecida: {state.current_order}")
    else:
        raise Exception("Saldo insuficiente de DOGE para realizar la venta")

def close_current_operation():
    if state.current_order.get('side') == "buy":
        sell_all()
        logger.info("Operación de compra cerrada manualmente.")
    elif state.current_order.get('side') == "sell":
        sell_all()
        logger.info("Operación de venta cerrada manualmente.")
    state.current_order.clear()
    state.operation_in_progress = False

def monitor_price():
    start_time = time.time()
    while state.operation_in_progress:
        try:
            if time.time() - start_time > 1800:
                logger.warning("Límite de tiempo alcanzado para monitorear el precio.")
                break

            ticker = safe_get_ticker(SYMBOL)
            if not ticker:
                break
            current_price = float(ticker['price'])
            logger.info(f"Precio actual monitoreado: {current_price}")

            if "side" not in state.current_order or "tp_price" not in state.current_order or "sl_price" not in state.current_order:
                logger.error("Faltan claves en current_order")
                break

            if state.current_order['side'] == "buy":
                if current_price >= state.current_order['tp_price'] or current_price <= state.current_order['sl_price']:
                    sell_all()
                    break
            elif state.current_order['side'] == "sell":
                if current_price <= state.current_order['tp_price'] or current_price >= state.current_order['sl_price']:
                    sell_all()
                    break

            time.sleep(5)  # Aumenta el intervalo a 5 segundos para reducir la carga del sistema

        except Exception as e:
            logger.error(f"Error monitoreando el precio: {e}")
            break

    state.operation_in_progress = False
    state.current_order.clear()

def sell_all():
    doge_balance = safe_get_balance("DOGE") * 0.85
    if doge_balance > 0:
        adjusted_amount = adjust_to_increment(doge_balance, 0.001)
        if adjusted_amount >= MIN_ORDER_SIZE:
            response = safe_create_order(SYMBOL, "sell", size=round(adjusted_amount, 2))
            logger.info(f"Orden de venta ejecutada: {response}")
        else:
            logger.error("El saldo de DOGE es insuficiente para realizar la venta.")
    else:
        logger.error("Saldo insuficiente de DOGE para vender")

def safe_get_balance(asset):
    retries = 3
    for i in range(retries):
        try:
            accounts = user_client.get_account_list()
            for account in accounts:
                if account['currency'] == asset and account['type'] == 'trade':
                    return float(account['balance'])
            return 0
        except Exception as e:
            logger.error(f"Error obteniendo saldo para {asset}: {e}")
            time.sleep(5)
    return 0

def safe_get_ticker(symbol):
    retries = 3
    for i in range(retries):
        try:
            return market_client.get_ticker(symbol)
        except Exception as e:
            logger.error(f"Error obteniendo ticker para {symbol}: {e}")
            time.sleep(5)
    return None

def safe_create_order(symbol, side, **kwargs):
    retries = 3
    for i in range(retries):
        try:
            if side == "buy":
                return trade_client.create_market_order(symbol, side, funds=kwargs['funds'])
            else:
                return trade_client.create_market_order(symbol, side, size=kwargs['size'])
        except Exception as e:
            logger.error(f"Error creando orden {side} para {symbol}: {e}")
            time.sleep(5)
    return None

def adjust_to_increment(amount, increment):
    return round(amount / increment) * increment

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
